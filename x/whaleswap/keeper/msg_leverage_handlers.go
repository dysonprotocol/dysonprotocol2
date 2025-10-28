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
	if msg == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "message cannot be nil")
	}
	pos, err := k.LeveragePositions.Get(ctx, msg.PositionId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "position %d not found", msg.PositionId)
	}
	// Check for invalid position data before ownership to avoid panics
	if pos.BorrowTime == nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid position: missing borrow_time")
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

	// Swap held back to borrowed denom via MakeTrade using the borrow vault as trader
	borrowVault := k.leverageBorrowVaultBech(ctx)
	mt := &whaleswapv1.MsgMakeTrade{
		Trader:    borrowVault,
		MaxInput:  sdk.NewCoins(pos.Held),
		MinOutput: sdk.NewCoins(),
		Operations: []whaleswapv1.TradeOperation{
			{Op: &whaleswapv1.TradeOperation_Swap{Swap: &whaleswapv1.SwapLeg{PoolId: pos.PoolId, SwapIn: pos.Held}}},
		},
		Note: "leverage-close",
	}
	mtResp, mtErr := k.MakeTrade(ctx, mt)
	if mtErr != nil {
		return nil, cosmossdkerrors.Wrap(mtErr, "failed leverage close MakeTrade")
	}
	proceedsBorrow := mtResp.TraderOutputs.AmountOf(pos.Borrowed.Denom)
	if !proceedsBorrow.IsPositive() {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "close swap produced no %s output", pos.Borrowed.Denom)
	}
	repayment := k.ComputeEffectiveRepayment(pos.Borrowed.Amount, interest)

	// Handle underwater positions (proceeds < repayment) using collateral to cover shortfall.
	// This eliminates moral hazard where users could retrieve full collateral from underwater positions.
	var actualRepayment, poolLoss, pnl math.Int
	var profit sdk.Coin
	var usedCrossDenomSwap bool // Track if we swapped collateral for cross-denom case

	if proceedsBorrow.LT(repayment) {
		shortfall := repayment.Sub(proceedsBorrow)

		// Check if collateral can cover the shortfall
		if pos.Collateral.Denom == pos.Borrowed.Denom {
			// Same denom: use collateral to cover shortfall directly
			if pos.Collateral.Amount.LT(shortfall) {
				// Collateral insufficient: user loses all collateral, pool still takes remaining loss
				poolLoss = shortfall.Sub(pos.Collateral.Amount)
				actualRepayment = proceedsBorrow.Add(pos.Collateral.Amount)
				// Collateral already escrowed in module; it will be used for repayment instead of returned
				// Set to zero so user doesn't get it back
				collateralUsedForShortfall := pos.Collateral.Amount
				pos.Collateral.Amount = math.ZeroInt()
				pnl = math.ZeroInt()
				profit = sdk.NewCoin(pos.Borrowed.Denom, math.ZeroInt())
				sdkCtx.Logger().Info("ClosePosition underwater: collateral insufficient",
					"proceeds", proceedsBorrow,
					"repayment", repayment,
					"collateral_used", collateralUsedForShortfall,
					"pool_loss", poolLoss)
			} else {
				// Collateral sufficient: deduct shortfall from collateral, no pool loss
				// Shortfall amount from escrowed collateral will be used for repayment (stays in module)
				pos.Collateral.Amount = pos.Collateral.Amount.Sub(shortfall)
				actualRepayment = repayment
				poolLoss = math.ZeroInt()
				pnl = math.ZeroInt()
				profit = sdk.NewCoin(pos.Borrowed.Denom, math.ZeroInt())
				sdkCtx.Logger().Info("ClosePosition underwater: collateral covers shortfall",
					"proceeds", proceedsBorrow,
					"repayment", repayment,
					"shortfall", shortfall,
					"collateral_remaining", pos.Collateral.Amount)
			}
		} else {
			// Cross-denom collateral: swap collateral to borrowed denom to cover shortfall
			// Save collateral amount before zeroing it out
			collateralToSwap := pos.Collateral

			// Zero out position collateral and persist BEFORE moving funds
			// This prevents invariant checker from expecting it in module during swap
			pos.Collateral.Amount = math.ZeroInt()
			if err := k.LeveragePositions.Set(ctx, msg.PositionId, pos); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to update position before collateral swap")
			}

			// Now move collateral from module → borrow vault, then swap using borrow vault as trader
			// This keeps fund flows clean: both swaps use borrow vault, proceeds combine there
			if err := k.moveModuleToModule(ctx, whaleswap.ModuleName, whaleswap.LeverageBorrowVaultModuleName, sdk.NewCoins(collateralToSwap)); err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to move collateral to borrow vault for swap")
			}

			collateralSwapMt := &whaleswapv1.MsgMakeTrade{
				Trader:    borrowVault,
				MaxInput:  sdk.NewCoins(collateralToSwap),
				MinOutput: sdk.NewCoins(),
				Operations: []whaleswapv1.TradeOperation{
					{Op: &whaleswapv1.TradeOperation_Swap{
						Swap: &whaleswapv1.SwapLeg{
							PoolId: pos.PoolId,
							SwapIn: collateralToSwap,
						},
					}},
				},
				Note: "leverage-close-collateral-swap",
			}
			collSwapResp, collSwapErr := k.MakeTrade(ctx, collateralSwapMt)
			if collSwapErr != nil {
				return nil, cosmossdkerrors.Wrap(collSwapErr, "failed to swap collateral for shortfall coverage")
			}

			// Reload pool after second swap
			pool, err = k.PoolsMap.Get(ctx, pos.PoolId)
			if err != nil {
				return nil, cosmossdkerrors.Wrapf(err, "failed to reload pool after collateral swap %d", pos.PoolId)
			}

			// Collateral swap proceeds in borrowed denom (now in borrow vault alongside first swap proceeds)
			collateralProceeds := collSwapResp.TraderOutputs.AmountOf(pos.Borrowed.Denom)
			if !collateralProceeds.IsPositive() {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "collateral swap produced no %s output", pos.Borrowed.Denom)
			}

			// Total proceeds from both swaps
			totalProceeds := proceedsBorrow.Add(collateralProceeds)

			// Settle based on total proceeds vs repayment
			if totalProceeds.GTE(repayment) {
				// Total proceeds cover full repayment
				actualRepayment = repayment
				poolLoss = math.ZeroInt()
				pnl = totalProceeds.Sub(repayment)
				profit = sdk.NewCoin(pos.Borrowed.Denom, pnl)
				sdkCtx.Logger().Info("ClosePosition underwater: cross-denom collateral swap covered shortfall",
					"held_proceeds", proceedsBorrow,
					"collateral_proceeds", collateralProceeds,
					"total_proceeds", totalProceeds,
					"repayment", repayment,
					"profit", pnl)
			} else {
				// Even after swapping all collateral, still underwater - pool takes loss
				actualRepayment = totalProceeds
				poolLoss = repayment.Sub(totalProceeds)
				pnl = math.ZeroInt()
				profit = sdk.NewCoin(pos.Borrowed.Denom, math.ZeroInt())
				sdkCtx.Logger().Info("ClosePosition underwater: cross-denom collateral swap insufficient, pool takes loss",
					"held_proceeds", proceedsBorrow,
					"collateral_proceeds", collateralProceeds,
					"total_proceeds", totalProceeds,
					"repayment", repayment,
					"pool_loss", poolLoss)
			}

			// Collateral was entirely consumed in swap, set to zero
			pos.Collateral.Amount = math.ZeroInt()
			usedCrossDenomSwap = true
		}
	} else {
		// Profitable or break-even: full repayment
		actualRepayment = repayment
		poolLoss = math.ZeroInt()
		pnl = proceedsBorrow.Sub(repayment)
		profit = sdk.NewCoin(pos.Borrowed.Denom, pnl)
	}

	// Reload pool to get current state after MakeTrade modified it
	pool, err = k.PoolsMap.Get(ctx, pos.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to reload pool %d", pos.PoolId)
	}

	// Move swap proceeds from borrow vault to module
	// In cross-denom case, actualRepayment includes proceeds from both swaps (both in vault)
	// In other cases, actualRepayment may include collateral from module + proceedsBorrow from vault
	var proceedsToMove math.Int
	if usedCrossDenomSwap {
		// Both swaps executed in borrow vault, move total proceeds
		proceedsToMove = actualRepayment
	} else {
		// Only first swap in vault; any collateral contribution is already in module
		proceedsToMove = proceedsBorrow
	}
	proceedsCoin := sdk.NewCoin(pos.Borrowed.Denom, proceedsToMove)
	if err := k.moveModuleToModule(ctx, whaleswap.LeverageBorrowVaultModuleName, whaleswap.ModuleName, sdk.NewCoins(proceedsCoin)); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to transfer proceeds to module")
	}

	// Restore pool reserves by adding back the full actualRepayment amount
	// actualRepayment = proceedsBorrow (from vault, just moved) + collateral used (already in module)
	// In OpenPosition we subtracted pos.Borrowed; here we add back actualRepayment.
	// If actualRepayment < pos.Borrowed, pool.Coins ends up permanently lower (pool absorbs the loss).
	repaymentCoin := sdk.NewCoin(pos.Borrowed.Denom, actualRepayment)
	pool.Coins = pool.Coins.Add(repaymentCoin)
	if err := k.updatePool(ctx, &pool); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update pool after repayment")
	}

	// Return remaining collateral to user (if any left after covering shortfall)
	if pos.Collateral.Amount.IsPositive() {
		if err := k.sendFromModule(ctx, userAddr, sdk.NewCoins(pos.Collateral)); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to return collateral")
		}
	}

	// Return profit to user (if positive) from borrow vault
	// Both standard and cross-denom cases have proceeds/profit in borrow vault
	if profit.Amount.IsPositive() {
		if err := k.sendFromBorrowVault(ctx, userAddr, sdk.NewCoins(profit)); err != nil {
			return nil, cosmossdkerrors.Wrap(err, "failed to return profit")
		}
	}

	// Update pool: decrease total_borrowed and add interest earned (actual repayment, not expected)
	totalBorrowed := sdk.NewCoins(pool.TotalBorrowed...).Sub(pos.Borrowed)
	pool.TotalBorrowed = totalBorrowed
	interestEarned := sdk.NewCoins(pool.InterestEarned...).Add(sdk.NewCoin(pos.Borrowed.Denom, actualRepayment))
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
