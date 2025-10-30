package keeper

import (
	"context"
	"fmt"

	cosmossdk_math "cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// MigrateWhaleswapV1ToV2 migrates pools and trades from deprecated fields to new format.
// This should be called ONCE during chain upgrade.
func (k Keeper) MigrateWhaleswapV1ToV2(ctx context.Context) error {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)

	logger.Info("Starting whaleswap v1→v2 migration")

	params := k.GetParams(ctx)
	migratedParams := whaleswapv1.MigrateParams(params)
	paramsChanged := migratedParams.ValuationPeriod != params.ValuationPeriod ||
		migratedParams.BidTimeout != params.BidTimeout ||
		migratedParams.BlockDelayBeforeClose != params.BlockDelayBeforeClose ||
		migratedParams.BlockDelayBeforeLiquidation != params.BlockDelayBeforeLiquidation
	if paramsChanged {
		logger.Info("Migrating whaleswap params to new defaults",
			"old_bid_timeout", params.BidTimeout.String(),
			"new_bid_timeout", migratedParams.BidTimeout.String(),
			"old_valuation_period", params.ValuationPeriod.String(),
			"new_valuation_period", migratedParams.ValuationPeriod.String(),
			"old_block_delay_before_close", params.BlockDelayBeforeClose,
			"new_block_delay_before_close", migratedParams.BlockDelayBeforeClose,
			"old_block_delay_before_liquidation", params.BlockDelayBeforeLiquidation,
			"new_block_delay_before_liquidation", migratedParams.BlockDelayBeforeLiquidation,
		)
	}
	if err := k.SetParams(ctx, migratedParams); err != nil {
		return fmt.Errorf("failed to migrate whaleswap params: %w", err)
	}

	// Migrate all pools: fee_pct → fee_rate
	poolCount := 0
	if err := k.PoolsMap.Walk(ctx, nil, func(poolId uint64, pool whaleswapv1.Pool) (bool, error) {
		migrated := false
		origFeeRate := sdk.NewDecCoins(pool.FeeRate...)
		origMinCR := sdk.NewDecCoins(pool.MinCollateralRatio...)
		origMaxLev := sdk.NewDecCoins(pool.MaxLeverageRatio...)
		origLiq := sdk.NewDecCoins(pool.LiquidationThreshold...)
		origMaxBorrow := sdk.NewDecCoins(pool.MaxBorrowPercent...)
		origIR := sdk.NewDecCoins(pool.InterestRate...)

		// Migrate if needed
		if len(pool.FeeRate) == 0 && pool.FeePct != "" {
			feeDec, err := cosmossdk_math.LegacyNewDecFromStr(pool.FeePct)
			if err != nil {
				logger.Error("pool migration failed: invalid fee_pct", "pool_id", poolId, "fee_pct", pool.FeePct, "error", err)
				return false, nil // continue iteration
			}

			// Create two DecCoins, one per reserve denom in canonical order
			if len(pool.Coins) != 2 {
				logger.Error("pool migration failed: must have exactly 2 reserve coins", "pool_id", poolId)
				return false, nil // continue iteration
			}

			pool.FeeRate = sdk.DecCoins{
				sdk.NewDecCoinFromDec(pool.Coins[0].Denom, feeDec),
				sdk.NewDecCoinFromDec(pool.Coins[1].Denom, feeDec),
			}
			migrated = true
		}

		whaleswapv1.MigratePool(&pool)
		if !pool.FeeRate.Equal(origFeeRate) ||
			!pool.MinCollateralRatio.Equal(origMinCR) ||
			!pool.MaxLeverageRatio.Equal(origMaxLev) ||
			!pool.LiquidationThreshold.Equal(origLiq) ||
			!pool.MaxBorrowPercent.Equal(origMaxBorrow) ||
			!pool.InterestRate.Equal(origIR) {
			migrated = true
		}

		if migrated {
			if err := k.PoolsMap.Set(ctx, poolId, pool); err != nil {
				return false, fmt.Errorf("failed to save migrated pool %d: %w", poolId, err)
			}
			poolCount++
			logger.Info("Migrated pool", "pool_id", poolId)
		}

		return false, nil // continue iteration
	}); err != nil {
		return fmt.Errorf("failed to walk pools: %w", err)
	}

	logger.Info("Pool migration complete", "migrated_count", poolCount)

	// Migrate all trades: deprecated fields → new fields
	tradeCount := 0
	if err := k.TradesMap.Walk(ctx, nil, func(tradeId uint64, trade whaleswapv1.Trade) (bool, error) {
		// Skip if already migrated
		if trade.Trader != "" && len(trade.Operations) > 0 {
			return false, nil // continue iteration
		}

		// Migrate trader
		if trade.Trader == "" && trade.Taker != "" {
			trade.Trader = trade.Taker
		}

		// Migrate height/timestamp
		if trade.Height == 0 && trade.HeightDeprecated > 0 {
			trade.Height = trade.HeightDeprecated
		}
		if trade.Timestamp == nil && trade.TimestampDeprecated != nil {
			trade.Timestamp = trade.TimestampDeprecated
		}

		// Migrate sent/received
		if len(trade.TotalSent) == 0 && trade.Sent.IsValid() && trade.Sent.Amount.IsPositive() {
			trade.TotalSent = sdk.NewCoins(trade.Sent)
		}
		if len(trade.TotalReceived) == 0 && trade.Received.IsValid() && trade.Received.Amount.IsPositive() {
			trade.TotalReceived = sdk.NewCoins(trade.Received)
		}

		// Migrate note
		if trade.Note == "" && trade.NoteDeprecated != "" {
			trade.Note = trade.NoteDeprecated
		}

		// Reconstruct operations
		if len(trade.Operations) == 0 {
			operations := []whaleswapv1.TradeOperation{}

			if trade.OfferId > 0 {
				takeOp := whaleswapv1.TradeOperation{
					Op: &whaleswapv1.TradeOperation_Take{
						Take: &whaleswapv1.TakeItem{OfferId: trade.OfferId},
					},
				}
				if trade.Sent.IsValid() {
					takeOp.Sent = trade.Sent
				}
				if trade.Received.IsValid() {
					takeOp.Received = trade.Received
				}
				operations = append(operations, takeOp)
			}

			if trade.PoolId > 0 {
				swapOp := whaleswapv1.TradeOperation{
					Op: &whaleswapv1.TradeOperation_Swap{
						Swap: &whaleswapv1.SwapLeg{PoolId: trade.PoolId},
					},
				}
				if trade.Sent.IsValid() {
					swapOp.Sent = trade.Sent
				}
				if trade.Received.IsValid() {
					swapOp.Received = trade.Received
				}
				operations = append(operations, swapOp)
			}

			if trade.AuctionId > 0 {
				auctionOp := whaleswapv1.TradeOperation{
					Op: &whaleswapv1.TradeOperation_Auction{
						Auction: &whaleswapv1.AuctionRedeem{AuctionId: trade.AuctionId},
					},
				}
				if trade.Sent.IsValid() {
					auctionOp.Sent = trade.Sent
				}
				if trade.Received.IsValid() {
					auctionOp.Received = trade.Received
				}
				operations = append(operations, auctionOp)
			}

			if len(operations) == 0 {
				logger.Warn("Trade has no operations after migration", "trade_id", tradeId)
			}

			trade.Operations = operations
		}

		// Save migrated trade
		if err := k.TradesMap.Set(ctx, tradeId, trade); err != nil {
			return false, fmt.Errorf("failed to save migrated trade %d: %w", tradeId, err)
		}

		tradeCount++
		logger.Info("Migrated trade", "trade_id", tradeId)
		return false, nil // continue iteration
	}); err != nil {
		return fmt.Errorf("failed to walk trades: %w", err)
	}

	logger.Info("Trade migration complete", "migrated_count", tradeCount)
	logger.Info("Whaleswap v1→v2 migration complete", "pools", poolCount, "trades", tradeCount)

	return nil
}
