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

// OpenPosition creates a leveraged position (long or short).
//
// Semantics:
//   - Creates a leveraged position by borrowing against escrowed collateral.
//   - Executes an AMM swap to convert borrowed amount to "held" asset.
//   - Persists position with snapshots for interest accrual and liquidation.
//
// Behavior:
//   - Validates pool (must exist, exactly 2 denoms), collateral (positive,
//     pool denom), and borrow (positive, pool denom, within borrow caps).
//   - Computes collateral ratio CR = collateral_value / debt_value in borrow
//     units, where collateral_value accounts for current pool price.
//   - Validates CR >= pool.min_collateral_ratio[borrow_denom] (> 1).
//   - Enforces borrow caps via pool.max_borrow_percent (per-denom).
//   - Reduces pool reserves by borrow amount, updates total_borrowed.
//   - Moves borrowed amount to borrow vault module account.
//   - Executes exact-in swap (borrowed → held) via MakeTrade.
//   - Escrows collateral to whaleswap module after swap.
//   - Creates position with interest rate and min_collateral_ratio snapshots.
//   - Held denom is the pool denom not matching borrow denom.
//
// Validation:
//   - Pool must exist with exactly 2 denoms.
//   - Collateral/borrow amounts must be positive.
//   - Collateral/borrow denoms must match pool denoms.
//   - Collateral ratio must meet pool min_collateral_ratio for borrow denom.
//   - Borrow must respect pool max_borrow_percent for borrow denom.
//   - Borrow amount must not exceed pool borrow cap (max_borrow_percent).
//   - Swap must produce positive held output.
//
// State updates:
//   - Pool reserves reduced by borrowed amount.
//   - Pool total_borrowed increased by borrowed amount.
//   - Borrowed amount moved to borrow vault module.
//   - Held amount received in borrow vault from swap.
//   - Collateral escrowed to whaleswap module.
//   - New position persisted with status OPEN.
//
// Emits:
//   - EventLeveragePositionOpened (position_id, user, pool_id,
//     collateral_denom, collateral_amount, borrowed_denom, borrowed_amount,
//     entry_price_held_per_borrow, collateral_ratio)
//
// Returns:
//   - *whaleswapv1.MsgOpenPositionResponse with PositionId and Held coin.
//
// Errors are returned on validation failures, insufficient liquidity, swap
// failures, or persistence failures; no panics.
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
	if !msg.Collateral.IsValid() || !msg.Collateral.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid collateral")
	}
	if !k.isDenomInPool(&pool, msg.Collateral.Denom) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "collateral denom %s not in pool", msg.Collateral.Denom)
	}

	// Validate borrow
	if !msg.Borrow.IsValid() || !msg.Borrow.IsPositive() {
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

	// Borrow cap based on pool utilization is no longer enforced by max_borrow_percent; capacity checks moved to bands/liquidity

	// Compute entry price: held_per_borrow = held_reserve / borrow_reserve
	// Find pool amounts for the specific denoms being borrowed and held using AmountOf
	borrowPoolAmount := pool.Coins.AmountOf(borrowDenom)
	heldPoolAmount := pool.Coins.AmountOf(heldDenom)
	if !sdk.NewCoin(borrowDenom, borrowPoolAmount).IsPositive() || !sdk.NewCoin(heldDenom, heldPoolAmount).IsPositive() {
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

	// Use pool-specific min CR threshold (per-borrow denom)
	if len(pool.MinInitialCollateralRatio) != 2 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool min_collateral_ratio must be set")
	}
	minCR := pool.MinInitialCollateralRatio.AmountOf(borrowDenom)
	if !minCR.GT(math.LegacyNewDec(1)) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool min_collateral_ratio must be > 1 for borrow denom")
	}
	if cr.LT(minCR) {
		return nil, cosmossdkerrors.Wrapf(whaleswapv1.ErrInsufficientCollateral, "CR %s < min_cr %s", cr.String(), minCR.String())
	}

	// Deprecated max_leverage_ratio removed: leverage clamp is redundant with min_collateral_ratio and max_borrow_percent.

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
	// Enforce per-denom borrow cap configured by pool.MaxBorrowPercent (exactly two DecCoins)
	if len(pool.MaxBorrowPercent) != 2 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool max_borrow_percent must be set with exactly two entries")
	}
	// Compute effective available = reserve - outstanding, then cap additional borrow by cap% of effective available
	outstanding := sdk.NewCoins(pool.TotalBorrowed...).AmountOf(borrowDenom)
	reserveAmt := pool.Coins.AmountOf(borrowDenom)
	if reserveAmt.IsZero() {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "borrow denom %s not in pool", borrowDenom)
	}
	effectiveAvailable := reserveAmt.Sub(outstanding)
	if effectiveAvailable.IsNegative() {
		effectiveAvailable = math.ZeroInt()
	}
	capPct := pool.MaxBorrowPercent.AmountOf(borrowDenom)
	one := math.LegacyNewDec(1)
	if !capPct.IsPositive() || capPct.GTE(one) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool max_borrow_percent must be in (0,1) for borrow denom")
	}
	maxBorrowAmt := math.LegacyNewDecFromInt(effectiveAvailable).Mul(capPct).TruncateInt()
	if msg.Borrow.Amount.GT(maxBorrowAmt) {
		return nil, cosmossdkerrors.Wrapf(whaleswapv1.ErrBorrowCapExceeded, "borrow would exceed cap for %s: available_cap=%s", borrowDenom, maxBorrowAmt.String())
	}
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
		Note: msg.Note,
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
	// Snapshot interest_rate, min_collateral_ratio, liquidation_threshold at open per updated design
	// Use single DecCoin for interest_rate of the borrowed denom
	var snapIR sdk.DecCoin
	if len(pool.InterestRate) == 2 {
		ir := sdk.NewDecCoins(pool.InterestRate...).Sort()
		snapIR = sdk.NewDecCoinFromDec(borrowDenom, ir.AmountOf(borrowDenom))
	} else {
		snapIR = sdk.NewDecCoinFromDec(borrowDenom, math.LegacyNewDec(0))
	}
	pos := whaleswapv1.LeveragePosition{
		PositionId:                 posID,
		PoolId:                     msg.PoolId,
		User:                       msg.Trader,
		Status:                     whaleswapv1.PositionStatus_POSITION_STATUS_OPEN,
		Borrowed:                   borrowed,
		Held:                       sdk.NewCoin(heldDenom, heldAmt),
		Collateral:                 msg.Collateral,
		CreatedHeight:              uint64(sdkCtx.BlockHeight()),
		CreatedTime:                &now,
		UpdatedHeight:              uint64(sdkCtx.BlockHeight()),
		UpdatedTime:                &now,
		LiquidationStatus:          whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_NONE,
		AccruedInterest:            sdk.NewCoin(borrowDenom, math.ZeroInt()),
		AccruedInterestRemainder:   sdk.NewDecCoinFromDec(borrowDenom, math.LegacyZeroDec()),
		InterestRate:               snapIR,
		MinCollateralRatio:         minCR.String(),
		LiquidationThreshold:       pool.LiquidationThreshold.AmountOf(borrowDenom).String(),
		InitialBorrowed:            borrowed,
		InitialHeld:                sdk.NewCoin(heldDenom, heldAmt),
		InitialCollateral:          msg.Collateral,
		TotalInterestPaid:          sdk.NewCoin(borrowDenom, math.ZeroInt()),
		LastInterestSettlementTime: &now,
		TradeIds:                   []uint64{mtResp.TradeId},
	}
	sdkCtx.Logger().Info("OpenPosition: position created", "posID", posID, "borrowDenom", pos.Borrowed.Denom, "heldDenom", pos.Held.Denom)
	if err := k.savePosition(ctx, pos, whaleswapv1.PositionStatus_POSITION_STATUS_UNSPECIFIED); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to save position")
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

	// Update address metrics
	if err := k.incrementPositionOpened(ctx, msg.Trader); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update position metrics")
	}

	return &whaleswapv1.MsgOpenPositionResponse{
		PositionId: posID,
		Held:       heldCoin,
	}, nil
}

// Borrow capacity is enforced via current pool price bands and liquidity; explicit percent caps removed.

func (k Keeper) isDenomInPool(pool *whaleswapv1.Pool, denom string) bool {
	return denom == pool.Coins[0].Denom || denom == pool.Coins[1].Denom
}
