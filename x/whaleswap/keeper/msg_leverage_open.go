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

// OpenPosition creates a leveraged position (long or short).
func (k Keeper) OpenPosition(ctx context.Context, msg *whaleswapv1.MsgOpenPosition) (*whaleswapv1.MsgOpenPositionResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	isLong := msg.PositionType == whaleswapv1.PositionType_POSITION_TYPE_LONG
	sdkCtx.Logger().Info("OpenPosition: called", "trader", msg.Trader, "poolID", msg.PoolId, "positionType", msg.PositionType.String(), "isLong", isLong)

	// Load and validate pool
	pool, err := k.PoolsMap.Get(ctx, msg.PoolId)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "pool %d not found", msg.PoolId)
	}
	sdkCtx.Logger().Info("OpenPosition: loaded pool", "poolID", msg.PoolId, "coin0", pool.Coins[0].Denom, "coin1", pool.Coins[1].Denom, "isLong", isLong)

	if len(pool.Coins) != 2 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool reserves")
	}
	if !msg.Collateral.IsValid() || !msg.Collateral.Amount.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid collateral")
	}
	if !msg.Borrow.IsValid() || !msg.Borrow.Amount.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid borrow")
	}

	// Validate borrow denom is in pool and determine held denom
	var borrowDenom, heldDenom string
	if msg.Borrow.Denom == pool.Coins[0].Denom {
		borrowDenom = pool.Coins[0].Denom
		heldDenom = pool.Coins[1].Denom
	} else if msg.Borrow.Denom == pool.Coins[1].Denom {
		borrowDenom = pool.Coins[1].Denom
		heldDenom = pool.Coins[0].Denom
	} else {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "borrow denom %s not in pool (coins: %s, %s)", msg.Borrow.Denom, pool.Coins[0].Denom, pool.Coins[1].Denom)
	}
	sdkCtx.Logger().Info("OpenPosition: borrow denom validated", "borrowDenom", borrowDenom, "heldDenom", heldDenom, "positionType", msg.PositionType.String())

	// Validate borrow cap
	if err := k.validateBorrowCap(ctx, &pool, borrowDenom, msg.Borrow.Amount); err != nil {
		return nil, err
	}

	// Compute entry price: coin[1] / coin[0]
	price := math.LegacyNewDecFromInt(pool.Coins[1].Amount).Quo(math.LegacyNewDecFromInt(pool.Coins[0].Amount))

	collateralValue := math.LegacyNewDecFromInt(msg.Collateral.Amount)
	debtValue := math.LegacyNewDecFromInt(msg.Borrow.Amount)
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
		return nil, cosmossdkerrors.Wrapf(whaleswapv1.ErrInsufficientCollateral, "CR %s < min_cr %s", cr.String(), minCR.String())
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

	// Transfer collateral to module
	if err := k.sendToModule(ctx, userAddr, sdk.NewCoins(msg.Collateral)); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to transfer collateral")
	}

	// Borrow from pool (update pool.total_borrowed)
	borrowed := sdk.NewCoin(borrowDenom, msg.Borrow.Amount)
	totalBorrowed := sdk.NewCoins(pool.TotalBorrowed...).Add(borrowed)
	pool.TotalBorrowed = totalBorrowed
	if err := k.PoolsMap.Set(ctx, msg.PoolId, pool); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to update pool")
	}

	// Compute held amount from swap
	var heldAmt math.Int
	if isLong {
		heldAmt = math.LegacyNewDecFromInt(msg.Borrow.Amount).Mul(price).TruncateInt()
	} else {
		heldAmt = math.LegacyNewDecFromInt(msg.Borrow.Amount).Quo(price).TruncateInt()
	}
	sdkCtx.Logger().Info("OpenPosition: held amount calculated", "isLong", isLong, "borrowAmount", msg.Borrow.Amount, "price", price.String(), "heldAmt", heldAmt)

	// Create position
	now := sdkCtx.BlockTime()
	posType := whaleswapv1.PositionType_POSITION_TYPE_LONG
	if !isLong {
		posType = whaleswapv1.PositionType_POSITION_TYPE_SHORT
	}
	posTypeStr := "LONG"
	if !isLong {
		posTypeStr = "SHORT"
	}

	pos := whaleswapv1.LeveragePosition{
		PositionId:         posID,
		PoolId:             msg.PoolId,
		User:               msg.Trader,
		PositionType:       posType,
		Borrowed:           sdk.NewCoin(borrowDenom, msg.Borrow.Amount),
		Held:               sdk.NewCoin(heldDenom, heldAmt),
		Collateral:         msg.Collateral,
		BorrowTime:         &now,
		CreatedBlockHeight: uint64(sdkCtx.BlockHeight()),
		LiquidationStatus:  whaleswapv1.LiquidationStatus_LIQUIDATION_STATUS_NONE,
		AccruedInterest:    sdk.NewCoin(borrowDenom, math.ZeroInt()),
	}
	sdkCtx.Logger().Info("OpenPosition: position created", "posID", posID, "posType", posTypeStr, "borrowDenom", pos.Borrowed.Denom, "heldDenom", pos.Held.Denom)

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
		PositionId:       posID,
		User:             msg.Trader,
		PoolId:           msg.PoolId,
		PositionType:     posTypeStr,
		CollateralDenom:  pos.Collateral.Denom,
		CollateralAmount: pos.Collateral.Amount.String(),
		BorrowedDenom:    pos.Borrowed.Denom,
		BorrowedAmount:   pos.Borrowed.Amount.String(),
		HeldDenom:        pos.Held.Denom,
		HeldAmount:       pos.Held.Amount.String(),
	}); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to emit event")
	}

	heldCoin := sdk.NewCoin(heldDenom, heldAmt)
	sdkCtx.Logger().Info("OpenPosition: success", "posID", posID, "heldDenom", heldCoin.Denom, "heldAmount", heldCoin.Amount)

	return &whaleswapv1.MsgOpenPositionResponse{
		PositionId: posID,
		Held:       heldCoin,
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
