package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// openPosition is the generic implementation for both long and short positions.
func (k Keeper) openPosition(ctx context.Context, trader string, poolID uint64, collateral sdk.Coin, borrowAmount math.Int, isLong bool) (posID uint64, heldCoin sdk.Coin, err error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Load and validate pool
	pool, err := k.PoolsMap.Get(ctx, poolID)
	if err != nil {
		return 0, sdk.Coin{}, cosmossdkerrors.Wrapf(err, "pool %d not found", poolID)
	}
	if len(pool.Coins) != 2 {
		return 0, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool reserves")
	}
	if !collateral.IsValid() || !collateral.Amount.IsPositive() {
		return 0, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid collateral")
	}
	if !borrowAmount.IsPositive() {
		return 0, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid borrow_amount")
	}

	// Select coins based on position type
	var borrowDenom, heldDenom string
	if isLong {
		borrowDenom = pool.Coins[0].Denom
		heldDenom = pool.Coins[1].Denom
	} else {
		borrowDenom = pool.Coins[1].Denom
		heldDenom = pool.Coins[0].Denom
	}

	// Validate borrow cap
	if err := k.validateBorrowCap(ctx, &pool, borrowDenom, borrowAmount); err != nil {
		return 0, sdk.Coin{}, err
	}

	// Compute entry price and collateral ratio
	price := math.LegacyNewDecFromInt(pool.Coins[1].Amount).Quo(math.LegacyNewDecFromInt(pool.Coins[0].Amount))

	collateralValue := math.LegacyNewDecFromInt(collateral.Amount)
	debtValue := math.LegacyNewDecFromInt(borrowAmount)
	cr := collateralValue.Quo(debtValue)

	// Use pool-specific min CR threshold
	minCR := math.LegacyMustNewDecFromStr("1.5")
	if pool.MinCollateralRatio != "" {
		parsed, err := math.LegacyNewDecFromStr(pool.MinCollateralRatio)
		if err == nil {
			minCR = parsed
		}
	}
	if cr.LT(minCR) {
		return 0, sdk.Coin{}, cosmossdkerrors.Wrapf(whaleswapv1.ErrInsufficientCollateral, "CR %s < min_cr %s", cr.String(), minCR.String())
	}

	// Validate max leverage (collateral + borrowed) / collateral
	leverage := collateralValue.Add(debtValue).Quo(collateralValue)
	maxLeverage := math.LegacyMustNewDecFromStr("20.0")
	if pool.MaxLeverageRatio != "" {
		parsed, err := math.LegacyNewDecFromStr(pool.MaxLeverageRatio)
		if err == nil {
			maxLeverage = parsed
		}
	}
	if leverage.GT(maxLeverage) {
		return 0, sdk.Coin{}, cosmossdkerrors.Wrapf(whaleswapv1.ErrInvalidCollateralRatio, "leverage %s exceeds max %s", leverage.String(), maxLeverage.String())
	}

	// Allocate position ID
	posID, err = k.leveragePositionSeq.Next(ctx)
	if err != nil {
		return 0, sdk.Coin{}, cosmossdkerrors.Wrap(err, "failed to allocate position ID")
	}

	userAddr, err := k.addr(ctx, trader)
	if err != nil {
		return 0, sdk.Coin{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidAddress, err.Error())
	}

	// Transfer collateral to module
	if err := k.sendToModule(ctx, userAddr, sdk.NewCoins(collateral)); err != nil {
		return 0, sdk.Coin{}, cosmossdkerrors.Wrap(err, "failed to transfer collateral")
	}

	// Borrow from pool (update pool.total_borrowed)
	borrowed := sdk.NewCoin(borrowDenom, borrowAmount)
	totalBorrowed := sdk.NewCoins(pool.TotalBorrowed...).Add(borrowed)
	pool.TotalBorrowed = totalBorrowed
	if err := k.PoolsMap.Set(ctx, poolID, pool); err != nil {
		return 0, sdk.Coin{}, cosmossdkerrors.Wrap(err, "failed to update pool")
	}

	// Compute held amount from swap
	var heldAmt math.Int
	if isLong {
		heldAmt = math.LegacyNewDecFromInt(borrowAmount).Mul(price).TruncateInt()
	} else {
		heldAmt = math.LegacyNewDecFromInt(borrowAmount).Quo(price).TruncateInt()
	}

	// Create position
	now := sdkCtx.BlockTime()
	posType := whaleswapv1.PositionType_POSITION_TYPE_LONG
	if !isLong {
		posType = whaleswapv1.PositionType_POSITION_TYPE_SHORT
	}

	pos := whaleswapv1.LeveragePosition{
		PositionId:         posID,
		PoolId:             poolID,
		User:               trader,
		PositionType:       posType,
		Borrowed:           sdk.NewCoin(borrowDenom, borrowAmount),
		Held:               sdk.NewCoin(heldDenom, heldAmt),
		Collateral:         collateral,
		BorrowTime:         &now,
		CreatedBlockHeight: uint64(sdkCtx.BlockHeight()),
		LiquidationStatus:  whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_NONE,
		AccruedInterest:    sdk.NewCoin(borrowDenom, math.ZeroInt()),
	}

	if err := k.LeveragePositions.Set(ctx, posID, pos); err != nil {
		return 0, sdk.Coin{}, cosmossdkerrors.Wrap(err, "failed to save position")
	}

	if err := k.PositionsByUserIndex.Set(ctx, collections.Join(trader, posID), posID); err != nil {
		return 0, sdk.Coin{}, cosmossdkerrors.Wrap(err, "failed to index position by user")
	}
	if err := k.PositionsByPoolIndex.Set(ctx, collections.Join(poolID, posID), posID); err != nil {
		return 0, sdk.Coin{}, cosmossdkerrors.Wrap(err, "failed to index position by pool")
	}

	// Emit event
	posTypeStr := "LONG"
	if !isLong {
		posTypeStr = "SHORT"
	}
	if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventLeveragePositionOpened{
		PositionId:       posID,
		User:             trader,
		PoolId:           poolID,
		PositionType:     posTypeStr,
		CollateralDenom:  pos.Collateral.Denom,
		CollateralAmount: pos.Collateral.Amount.String(),
		BorrowedDenom:    pos.Borrowed.Denom,
		BorrowedAmount:   pos.Borrowed.Amount.String(),
		HeldDenom:        pos.Held.Denom,
		HeldAmount:       pos.Held.Amount.String(),
	}); err != nil {
		return 0, sdk.Coin{}, cosmossdkerrors.Wrap(err, "failed to emit event")
	}

	return posID, sdk.NewCoin(heldDenom, heldAmt), nil
}

// OpenPosition creates a leveraged position (long or short).
func (k Keeper) OpenPosition(ctx context.Context, msg *whaleswapv1.MsgOpenPosition) (*whaleswapv1.MsgOpenPositionResponse, error) {
	isLong := msg.PositionType == whaleswapv1.PositionType_POSITION_TYPE_LONG
	posID, held, err := k.openPosition(ctx, msg.Trader, msg.PoolId, msg.Collateral, msg.BorrowAmount, isLong)
	if err != nil {
		return nil, err
	}

	return &whaleswapv1.MsgOpenPositionResponse{
		PositionId: posID,
		Held:       held,
	}, nil
}

func (k Keeper) validateBorrowCap(ctx context.Context, pool *whaleswapv1.Pool, denom string, borrowAmt math.Int) error {
	if len(pool.Coins) != 2 {
		return cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool state")
	}

	var maxBorrowPctStr string
	var reserveAmt math.Int

	if denom == pool.Coins[0].Denom {
		maxBorrowPctStr = pool.MaxBorrowPercent
		reserveAmt = pool.Coins[0].Amount
	} else if denom == pool.Coins[1].Denom {
		maxBorrowPctStr = pool.MaxBorrowPercent
		reserveAmt = pool.Coins[1].Amount
	} else {
		return cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "denom not in pool")
	}

	if maxBorrowPctStr == "" {
		return cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "borrowing disabled for this denom")
	}

	maxBorrowPct, err := math.LegacyNewDecFromStr(maxBorrowPctStr)
	if err != nil {
		return cosmossdkerrors.Wrapf(err, "invalid max_borrow_percent for %s", denom)
	}

	maxBorrowAmt := math.LegacyNewDecFromInt(reserveAmt).Mul(maxBorrowPct).TruncateInt()
	totalBorrows := sdk.NewCoins(pool.TotalBorrowed...).AmountOf(denom)
	if totalBorrows.Add(borrowAmt).GT(maxBorrowAmt) {
		return cosmossdkerrors.Wrapf(whaleswapv1.ErrBorrowCapExceeded, "borrow would exceed cap: %s", maxBorrowAmt)
	}

	return nil
}
