package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// ClosePosition closes an open leveraged position and settles collateral/profit.
func (k Keeper) ClosePosition(ctx context.Context, msg *whaleswapv1.MsgClosePosition) (*whaleswapv1.MsgClosePositionResponse, error) {
	pos, err := k.LeveragePositions.Get(ctx, msg.PositionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "position %d not found", msg.PositionId)
	}
	// Ownership check must return before any further logic to avoid side effects or nil derefs
	if pos.User != msg.User {
		// Use a stable message that includes the substring expected by tests
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "unauthorized: not position owner")
	}
	if !k.CanCloseBefore(ctx, &pos) {
		blocks := k.BlocksUntilCloseable(ctx, &pos)
		return nil, cosmossdkerrors.Wrapf(whaleswapv1.ErrBlockDelayNotPassed, "position locked for %d more blocks", blocks)
	}

	pool, err := k.PoolsMap.Get(ctx, pos.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool %d not found", pos.PoolId)
	}

	// Calculate interest
	rate, err := k.GetInterestRateForDenom(ctx, &pool, pos.Borrowed.Denom)
	if err != nil {
		return nil, err
	}
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	if pos.BorrowTime == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrLogic, "invalid position: missing borrow_time")
	}
	elapsed := sdkCtx.BlockTime().Sub(*pos.BorrowTime).Seconds()
	interest, err := k.CalculateInterest(pos.Borrowed.Amount, rate, int64(elapsed))
	if err != nil {
		return nil, err
	}

	// Return collateral and profit to user; pool receives repayment
	userAddr, err := k.addr(ctx, msg.User)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidAddress, err.Error())
	}

	// Swap held back to borrowed denom via PoolSwap using the borrow vault as trader
	borrowVault := k.leverageBorrowVaultBech(ctx)
	ps := &whaleswapv1.MsgPoolSwap{
		Trader:    borrowVault,
		MaxInput:  sdk.NewCoins(pos.Held),
		Legs:      []whaleswapv1.SwapLeg{{PoolId: pos.PoolId, SwapIn: pos.Held}},
		MinOutput: sdk.NewCoins(),
	}
	psResp, psErr := k.PoolSwap(ctx, ps)
	if psErr != nil {
		return nil, cosmossdkerrors.Wrap(psErr, "failed leverage close PoolSwap")
	}
	proceedsBorrow := psResp.AmountOut.AmountOf(pos.Borrowed.Denom)
	if !proceedsBorrow.IsPositive() {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "close swap produced no %s output", pos.Borrowed.Denom)
	}
	repayment := k.ComputeEffectiveRepayment(pos.Borrowed.Amount, interest)
	if proceedsBorrow.LT(repayment) {
		// Insufficient to fully repay: charge remaining from collateral; profit zero
		// TODO: look into allowing to be paid in the borrowed denom via a swap to the collateral denom
		shortfall := repayment.Sub(proceedsBorrow)
		// Burn from collateral denom converted to borrowed denom is not implemented; for now, cap at available collateral value by denom equality requirement
		// Enforcement: collateral denom must equal borrowed denom to permit direct repayment
		if pos.Collateral.Denom != pos.Borrowed.Denom {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "collateral denom must match borrowed denom for repayment shortfall in this version")
		}
		if pos.Collateral.Amount.LT(shortfall) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "insufficient collateral to cover repayment shortfall: have=%s need=%s", pos.Collateral.Amount.String(), shortfall.String())
		}
		// Deduct shortfall from collateral, remaining collateral (if any) returned to user
		pos.Collateral.Amount = pos.Collateral.Amount.Sub(shortfall)
		proceedsBorrow = repayment
	}
	// Net profit in borrowed denom: proceeds - repayment (>= 0 by previous guard)
	pnl := proceedsBorrow.Sub(repayment)
	profit := sdk.NewCoin(pos.Borrowed.Denom, pnl)

	// Move repayment from borrow vault back to whaleswap module, then add to pool reserves
	repaymentCoin := sdk.NewCoin(pos.Borrowed.Denom, repayment)
	if err := k.moveModuleToModule(ctx, whaleswap.LeverageBorrowVaultModuleName, whaleswap.ModuleName, sdk.NewCoins(repaymentCoin)); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to transfer repayment to module")
	}
	if pos.Borrowed.Denom == pool.Coins[0].Denom {
		pool.Coins = sdk.NewCoins(
			sdk.NewCoin(pool.Coins[0].Denom, pool.Coins[0].Amount.Add(repayment)),
			pool.Coins[1],
		)
	} else if pos.Borrowed.Denom == pool.Coins[1].Denom {
		pool.Coins = sdk.NewCoins(
			pool.Coins[0],
			sdk.NewCoin(pool.Coins[1].Denom, pool.Coins[1].Amount.Add(repayment)),
		)
	} else {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "borrowed denom %s not in pool", pos.Borrowed.Denom)
	}
	if err := k.updatePool(ctx, &pool); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update pool after repayment")
	}

	// Repay by depositing borrowed denom into pool reserves (ledger move inside module)
	// Note: tradeApplySwapLeg already decreased borrowed reserve by proceedsBorrow via the exact-in held swap.
	// Add repayment to borrowed reserve so net delta equals -profit.
	if pos.Borrowed.Denom == pool.Coins[0].Denom {
		pool.Coins = sdk.NewCoins(
			sdk.NewCoin(pool.Coins[0].Denom, pool.Coins[0].Amount.Add(repayment)),
			pool.Coins[1],
		)
	} else if pos.Borrowed.Denom == pool.Coins[1].Denom {
		pool.Coins = sdk.NewCoins(
			pool.Coins[0],
			sdk.NewCoin(pool.Coins[1].Denom, pool.Coins[1].Amount.Add(repayment)),
		)
	} else {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrLogic, "borrowed denom %s not in pool", pos.Borrowed.Denom)
	}
	if err := k.updatePool(ctx, &pool); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update pool after repayment")
	}

	// Return remaining collateral to user
	if err := k.sendFromModule(ctx, userAddr, sdk.NewCoins(pos.Collateral)); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to return collateral")
	}

	// Return profit to user (if positive) from borrow vault
	if profit.Amount.IsPositive() {
		if err := k.sendFromBorrowVault(ctx, userAddr, sdk.NewCoins(profit)); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to return profit")
		}
	}

	// Update pool: decrease total_borrowed and add interest earned
	totalBorrowed := sdk.NewCoins(pool.TotalBorrowed...).Sub(pos.Borrowed)
	pool.TotalBorrowed = totalBorrowed
	interestEarned := sdk.NewCoins(pool.InterestEarned...).Add(sdk.NewCoin(pos.Borrowed.Denom, repayment))
	pool.InterestEarned = interestEarned
	if err := k.PoolsMap.Set(ctx, pos.PoolId, pool); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update pool")
	}

	// Delete position
	if err := k.LeveragePositions.Remove(ctx, msg.PositionId); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to delete position")
	}

	// Emit event
	interestCoin := sdk.NewCoin(pos.Borrowed.Denom, interest.TruncateInt())
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeveragePositionClosed{
		PositionId:      msg.PositionId,
		User:            msg.User,
		PoolId:          pos.PoolId,
		Profit:          profit,
		AccruedInterest: interestCoin,
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
	}

	// Invariants after settlement
	if err := k.AssertAMMInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "AMM invariant after ClosePosition")
	}
	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant after ClosePosition")
	}

	return &whaleswapv1.MsgClosePositionResponse{
		Profit:          profit,
		AccruedInterest: interestCoin,
	}, nil
}

// InitializeLiquidation marks a position for liquidation.
func (k Keeper) InitializeLiquidation(ctx context.Context, msg *whaleswapv1.MsgInitializeLiquidation) (*whaleswapv1.MsgInitializeLiquidationResponse, error) {
	pos, err := k.LeveragePositions.Get(ctx, msg.PositionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "position %d not found", msg.PositionId)
	}

	pool, err := k.PoolsMap.Get(ctx, pos.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool %d not found", pos.PoolId)
	}

	// Calculate CR
	rate, _ := k.GetInterestRateForDenom(ctx, &pool, pos.Borrowed.Denom)
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	elapsed := sdkCtx.BlockTime().Sub(*pos.BorrowTime).Seconds()
	interest, _ := k.CalculateInterest(pos.Borrowed.Amount, rate, int64(elapsed))

	collateralValue := math.LegacyNewDecFromInt(pos.Collateral.Amount)
	debtValue := math.LegacyNewDecFromInt(pos.Borrowed.Amount).Add(interest)
	cr, _ := k.ComputeCollateralRatio(collateralValue, debtValue)

	// Use pool-specific liquidation threshold
	liquidationThreshold := math.LegacyMustNewDecFromStr("1.2")
	if pool.LiquidationThreshold != "" {
		parsed, err := math.LegacyNewDecFromStr(pool.LiquidationThreshold)
		if err == nil {
			liquidationThreshold = parsed
		}
	}

	if err := k.InitializeLiquidationInternal(ctx, &pos); err != nil {
		return nil, err
	}
	if err := k.LeveragePositions.Set(ctx, msg.PositionId, pos); err != nil {
		return nil, err
	}

	// Emit event
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeverageLiquidationInitialized{
		PositionId:           msg.PositionId,
		User:                 pos.User,
		PoolId:               pos.PoolId,
		CollateralRatio:      cr.String(),
		LiquidationThreshold: liquidationThreshold.String(),
		BlockHeight:          uint64(sdkCtx.BlockHeight()),
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
	}

	return &whaleswapv1.MsgInitializeLiquidationResponse{
		CollateralRatio:      cr,
		LiquidationThreshold: liquidationThreshold,
	}, nil
}

// FinalizeLiquidation completes position liquidation.
func (k Keeper) FinalizeLiquidation(ctx context.Context, msg *whaleswapv1.MsgFinalizeLiquidation) (*whaleswapv1.MsgFinalizeLiquidationResponse, error) {
	pos, err := k.LeveragePositions.Get(ctx, msg.PositionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "position %d not found", msg.PositionId)
	}

	if pos.LiquidationStatus != whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_INITIALIZED {
		return nil, cosmossdkerrors.Wrap(whaleswapv1.ErrPositionNotLiquidatable, "liquidation not initialized")
	}

	if !k.CanFinalizeLiquidationBefore(ctx, &pos) {
		return nil, cosmossdkerrors.Wrap(whaleswapv1.ErrBlockDelayNotPassed, "liquidation block delay not passed")
	}

	pool, err := k.PoolsMap.Get(ctx, pos.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool %d not found", pos.PoolId)
	}

	// Calculate final repayment
	rate, _ := k.GetInterestRateForDenom(ctx, &pool, pos.Borrowed.Denom)
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	elapsed := sdkCtx.BlockTime().Sub(*pos.BorrowTime).Seconds()
	interest, _ := k.CalculateInterest(pos.Borrowed.Amount, rate, int64(elapsed))
	repayment := k.ComputeEffectiveRepayment(pos.Borrowed.Amount, interest)

	// Liquidator sends repayment to module
	liquidatorAddr, err := k.addr(ctx, msg.Liquidator)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidAddress, "invalid liquidator address")
	}
	repaymentCoin := sdk.NewCoin(pos.Borrowed.Denom, repayment)
	if err := k.sendToModule(ctx, liquidatorAddr, sdk.NewCoins(repaymentCoin)); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to collect repayment from liquidator")
	}

	// Pool loss if collateral < repayment
	poolLossInt := repayment.Sub(pos.Collateral.Amount)
	if poolLossInt.IsNegative() {
		poolLossInt = math.ZeroInt()
	}
	poolLossCoin := sdk.NewCoin(pos.Borrowed.Denom, poolLossInt)
	interestCoin := sdk.NewCoin(pos.Borrowed.Denom, interest.TruncateInt())

	// Send all collateral to liquidator
	if err := k.sendFromModule(ctx, liquidatorAddr, sdk.NewCoins(pos.Collateral)); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to send collateral to liquidator")
	}

	// Update pool
	totalBorrowed := sdk.NewCoins(pool.TotalBorrowed...).Sub(pos.Borrowed)
	pool.TotalBorrowed = totalBorrowed
	pool.InterestEarned = sdk.NewCoins(pool.InterestEarned...).Add(
		sdk.NewCoin(pos.Borrowed.Denom, repayment),
	)
	if err := k.PoolsMap.Set(ctx, pos.PoolId, pool); err != nil {
		return nil, err
	}

	// Delete position
	if err := k.LeveragePositions.Remove(ctx, msg.PositionId); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to delete position")
	}

	// Emit event
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeverageLiquidationFinalized{
		PositionId:         msg.PositionId,
		User:               pos.User,
		Liquidator:         msg.Liquidator,
		PoolId:             pos.PoolId,
		CollateralReceived: pos.Collateral,
		RepaymentAmount:    repaymentCoin,
		AccruedInterest:    interestCoin,
		PoolLoss:           poolLossCoin,
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
	}

	return &whaleswapv1.MsgFinalizeLiquidationResponse{
		CollateralReceived: pos.Collateral,
		RepaymentAmount:    repaymentCoin,
		AccruedInterest:    interestCoin,
		PoolLoss:           poolLossCoin,
	}, nil
}
