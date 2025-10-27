package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// OpenPosition creates a leveraged position (long or short).
func (k Keeper) OpenPosition(ctx context.Context, msg *whaleswapv1.MsgOpenPosition) (*whaleswapv1.MsgOpenPositionResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	sdkCtx.Logger().Info("OpenPosition: called", "trader", msg.Trader, "poolID", msg.PoolId)

	// Load and validate pool
	pool, err := k.PoolsMap.Get(ctx, msg.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool %d not found", msg.PoolId)
	}
	sdkCtx.Logger().Info("OpenPosition: loaded pool", "poolID", msg.PoolId, "coin0", pool.Coins[0].Denom, "coin1", pool.Coins[1].Denom)

	if len(pool.Coins) != 2 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool reserves")
	}
	// Validate collateral
	if !msg.Collateral.IsValid() || !msg.Collateral.Amount.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid collateral")
	}
	if !k.isDenomInPool(&pool, msg.Collateral.Denom) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "collateral denom %s not in pool", msg.Collateral.Denom)
	}

	// Validate borrow
	if !msg.Borrow.IsValid() || !msg.Borrow.Amount.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid borrow")
	}
	if !k.isDenomInPool(&pool, msg.Borrow.Denom) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "borrow denom %s not in pool", msg.Borrow.Denom)
	}

	borrowDenom := msg.Borrow.Denom
	heldDenom, err := k.getOtherDenom(&pool, borrowDenom)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "failed to determine held denom: %v", err)
	}
	sdkCtx.Logger().Info("OpenPosition: borrow validated and held derived", "borrowDenom", borrowDenom, "heldDenom", heldDenom)

	// Validate borrow cap
	if err := k.validateBorrowCap(ctx, &pool, borrowDenom, msg.Borrow.Amount); err != nil {
		return nil, err
	}

	// Compute entry price: held_per_borrow = held_reserve / borrow_reserve
	// Find pool amounts for the specific denoms being borrowed and held using AmountOf
	borrowPoolAmount := pool.Coins.AmountOf(borrowDenom)
	heldPoolAmount := pool.Coins.AmountOf(heldDenom)
	if !borrowPoolAmount.IsPositive() || !heldPoolAmount.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool reserves for price computation")
	}
	priceHeldPerBorrow := math.LegacyNewDecFromInt(heldPoolAmount).Quo(math.LegacyNewDecFromInt(borrowPoolAmount))

	// Normalize CR/leverage in borrow denom units
	collateralValueInBorrow := math.LegacyNewDecFromInt(msg.Collateral.Amount)
	if msg.Collateral.Denom == heldDenom {
		collateralValueInBorrow = collateralValueInBorrow.Quo(priceHeldPerBorrow)
	}
	if msg.Collateral.Denom != borrowDenom && msg.Collateral.Denom != heldDenom {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "collateral denom not in pool")
	}
	if collateralValueInBorrow.IsZero() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "collateral value too small")
	}
	debtValue := math.LegacyNewDecFromInt(msg.Borrow.Amount)
	cr := collateralValueInBorrow.Quo(debtValue)

	// Use pool-specific min CR threshold
	if pool.MinCollateralRatio == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool min_collateral_ratio must be set")
	}
	minCR, err := math.LegacyNewDecFromStr(pool.MinCollateralRatio)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid min_collateral_ratio: %s", pool.MinCollateralRatio)
	}
	if cr.LT(minCR) {
		return nil, cosmossdkerrors.Wrapf(whaleswapv1.ErrInsufficientCollateral, "CR %s < min_cr %s", cr.String(), minCR.String())
	}

	// Validate max leverage: (collateral_in_borrow + borrowed) / collateral_in_borrow
	leverage := collateralValueInBorrow.Add(debtValue).Quo(collateralValueInBorrow)
	if pool.MaxLeverageRatio == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool max_leverage_ratio must be set")
	}
	maxLeverage, err := math.LegacyNewDecFromStr(pool.MaxLeverageRatio)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid max_leverage_ratio: %s", pool.MaxLeverageRatio)
	}
	if leverage.GT(maxLeverage) {
		return nil, cosmossdkerrors.Wrapf(whaleswapv1.ErrInvalidCollateralRatio, "leverage %s exceeds max %s", leverage.String(), maxLeverage.String())
	}

	// Allocate position ID
	posID, err := k.leveragePositionSeq.Next(ctx)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to allocate position ID")
	}

	userAddr, err := k.addr(ctx, msg.Trader)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidAddress, err.Error())
	}

	// Defer collateral escrow until after PoolSwap so invariants inside PoolSwap do not require provisional position state

	// Borrow from pool (update pool.total_borrowed)
	borrowed := sdk.NewCoin(borrowDenom, msg.Borrow.Amount)
	// Reduce pool reserves by the loan amount so that bank balances and pool reserves remain aligned.
	// This makes the subsequent exact-in swap restore the input reserve, preserving AMM invariants.
	currentReserve := pool.Coins.AmountOf(borrowDenom)
	if currentReserve.IsZero() || currentReserve.LT(borrowed.Amount) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "insufficient %s reserve to disburse loan: have=%s need=%s", borrowDenom, currentReserve.String(), borrowed.Amount.String())
	}
	// Update pool reserves using standard SDK coin subtraction
	pool.Coins = pool.Coins.Sub(borrowed)
	// Track outstanding borrowed
	totalBorrowed := sdk.NewCoins(pool.TotalBorrowed...).Add(borrowed)
	pool.TotalBorrowed = totalBorrowed
	if err := k.PoolsMap.Set(ctx, msg.PoolId, pool); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update pool")
	}

	// Loan: move borrowed denom from whaleswap module to borrow vault
	borrowVault := k.leverageBorrowVaultBech(ctx)
	loan := sdk.NewCoin(borrowDenom, msg.Borrow.Amount)
	if err := k.moveModuleToModule(ctx, whaleswap.ModuleName, whaleswap.LeverageBorrowVaultModuleName, sdk.NewCoins(loan)); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to disburse loan to borrow vault: %s", loan.String())
	}

	// Note: do NOT persist a provisional position before PoolSwap.
	// PoolSwap asserts invariants that include leverage collateral from persisted positions.
	// Persisting before escrow would count collateral in expectations while the module doesn't hold it yet.
	now := sdkCtx.BlockTime()

	// Execute MakeTrade with a single swap operation (exact-in borrowed → held). Settlement will use wsMoveCoins.
	mt := &whaleswapv1.MsgMakeTrade{
		Trader:    borrowVault,
		MaxInput:  sdk.NewCoins(loan),
		MinOutput: sdk.NewCoins(),
		Operations: []whaleswapv1.TradeOperation{
			{
				Op: &whaleswapv1.TradeOperation_Swap{
					Swap: &whaleswapv1.SwapLeg{PoolId: msg.PoolId, SwapIn: loan},
				},
			},
		},
		Note: "leverage-open",
	}
	mtResp, mtErr := k.MakeTrade(ctx, mt)
	if mtErr != nil {
		return nil, cosmossdkerrors.Wrap(mtErr, "failed MakeTrade swap for leverage open")
	}
	// Held amount received by borrow vault
	heldAmt := mtResp.TraderOutputs.AmountOf(heldDenom)
	if !heldAmt.IsPositive() {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "swap produced no held output for %s", heldDenom)
	}
	sdkCtx.Logger().Info("OpenPosition: PoolSwap executed", "borrowDenom", borrowDenom, "heldDenom", heldDenom, "borrowAmount", loan.Amount, "heldAmt", heldAmt)

	// Now escrow collateral to module (post-swap) so subsequent invariant checks see both collateral and position state together
	if err := k.sendToModule(ctx, userAddr, sdk.NewCoins(msg.Collateral)); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to transfer collateral")
	}

	// Persist final position after swap and collateral escrow
	pos := whaleswapv1.LeveragePosition{
		PositionId:         posID,
		PoolId:             msg.PoolId,
		User:               msg.Trader,
		Borrowed:           borrowed,
		Held:               sdk.NewCoin(heldDenom, heldAmt),
		Collateral:         msg.Collateral,
		BorrowTime:         &now,
		CreatedBlockHeight: uint64(sdkCtx.BlockHeight()),
		LiquidationStatus:  whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_NONE,
		AccruedInterest:    sdk.NewCoin(borrowDenom, math.ZeroInt()),
	}
	sdkCtx.Logger().Info("OpenPosition: position created", "posID", posID, "borrowDenom", pos.Borrowed.Denom, "heldDenom", pos.Held.Denom)
	if err := k.LeveragePositions.Set(ctx, posID, pos); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to save position")
	}

	if err := k.PositionsByUserIndex.Set(ctx, collections.Join(msg.Trader, posID), posID); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to index position by user")
	}
	if err := k.PositionsByPoolIndex.Set(ctx, collections.Join(msg.PoolId, posID), posID); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to index position by pool")
	}

	// Emit event
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeveragePositionOpened{
		PositionId:              posID,
		User:                    msg.Trader,
		PoolId:                  msg.PoolId,
		CollateralDenom:         pos.Collateral.Denom,
		CollateralAmount:        pos.Collateral.Amount.String(),
		BorrowedDenom:           pos.Borrowed.Denom,
		BorrowedAmount:          pos.Borrowed.Amount.String(),
		EntryPriceHeldPerBorrow: priceHeldPerBorrow.String(),
		CollateralRatio:         cr.String(),
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
	}

	heldCoin := sdk.NewCoin(heldDenom, heldAmt)
	sdkCtx.Logger().Info("OpenPosition: success", "posID", posID, "heldDenom", heldCoin.Denom, "heldAmount", heldCoin.Amount)

	// Invariants: AMM and unified module balances
	if err := k.AssertAMMInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "AMM invariant after OpenPosition")
	}
	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant after OpenPosition")
	}

	return &whaleswapv1.MsgOpenPositionResponse{
		PositionId: posID,
		Held:       heldCoin,
	}, nil
}

func (k Keeper) validateBorrowCap(ctx context.Context, pool *whaleswapv1.Pool, denom string, borrowAmt math.Int) error {
	if len(pool.Coins) != 2 {
		return cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool state")
	}

	// Use AmountOf() instead of array indexing to avoid positional assumptions
	reserveAmt := pool.Coins.AmountOf(denom)
	if reserveAmt.IsZero() {
		return cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "denom %s not in pool", denom)
	}

	maxBorrowPctStr := pool.MaxBorrowPercent

	if maxBorrowPctStr == "" {
		return cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "borrowing disabled for this denom")
	}

	maxBorrowPct, err := math.LegacyNewDecFromStr(maxBorrowPctStr)
	if err != nil {
		return cosmossdkerrors.Wrapf(err, "invalid max_borrow_percent for %s", denom)
	}

	// Effective available = reserve - outstanding borrows
	outstanding := sdk.NewCoins(pool.TotalBorrowed...).AmountOf(denom)
	effectiveAvailable := reserveAmt.Sub(outstanding)
	if effectiveAvailable.IsNegative() {
		effectiveAvailable = math.ZeroInt()
	}
	maxBorrowAmt := math.LegacyNewDecFromInt(effectiveAvailable).Mul(maxBorrowPct).TruncateInt()
	if outstanding.Add(borrowAmt).Sub(outstanding).GT(maxBorrowAmt) {
		// i.e., borrowAmt > maxBorrowAmt
		return cosmossdkerrors.Wrapf(whaleswapv1.ErrBorrowCapExceeded, "borrow would exceed cap: %s", maxBorrowAmt)
	}

	return nil
}

func (k Keeper) isDenomInPool(pool *whaleswapv1.Pool, denom string) bool {
	return denom == pool.Coins[0].Denom || denom == pool.Coins[1].Denom
}
