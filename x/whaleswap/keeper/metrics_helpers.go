package keeper

import (
	"context"
	"errors"

	"cosmossdk.io/collections"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// getOrCreateMetrics retrieves existing metrics or creates a new zero-value instance.
func (k Keeper) getOrCreateMetrics(ctx context.Context, address string) (whaleswapv1.AddressMetrics, error) {
	metrics, err := k.AddressMetricsMap.Get(ctx, address)
	if err != nil {
		if !errors.Is(err, collections.ErrNotFound) {
			return whaleswapv1.AddressMetrics{}, err
		}
		// Create new zero-value metrics
		sdkCtx := sdk.UnwrapSDKContext(ctx)
		metrics = whaleswapv1.AddressMetrics{
			Address:             address,
			BlockHeight:         uint64(sdkCtx.BlockHeight()),
			TotalVolumeSent:     sdk.NewCoins(),
			TotalVolumeReceived: sdk.NewCoins(),
			LpFeesEarned:        sdk.NewCoins(),
			LpInterestEarned:    sdk.NewCoins(),
			InterestPaid:        sdk.NewCoins(),
			LeveragePnl:         sdk.NewCoins(),
			MakerVolume:         sdk.NewCoins(),
			AuctionVolume:       sdk.NewCoins(),
		}
	}

	return metrics, nil
}

// saveMetrics persists metrics and updates block height.
func (k Keeper) saveMetrics(ctx context.Context, metrics whaleswapv1.AddressMetrics) error {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	metrics.BlockHeight = uint64(sdkCtx.BlockHeight())
	return k.AddressMetricsMap.Set(ctx, metrics.Address, metrics)
}

// incrementTradeMetrics updates trading metrics for an address.
func (k Keeper) incrementTradeMetrics(ctx context.Context, trader string, sent, received sdk.Coins, numOps uint64) error {
	metrics, err := k.getOrCreateMetrics(ctx, trader)
	if err != nil {
		return err
	}

	metrics.TotalTrades++
	metrics.TotalTradeOps += numOps

	// Filter and add coins with metadata
	filteredSent := k.filterCoinsWithMetadata(ctx, sent)
	filteredReceived := k.filterCoinsWithMetadata(ctx, received)

	metrics.TotalVolumeSent = metrics.TotalVolumeSent.Add(filteredSent...)
	metrics.TotalVolumeReceived = metrics.TotalVolumeReceived.Add(filteredReceived...)

	return k.saveMetrics(ctx, metrics)
}

// incrementPoolCreated increments pools_created counter.
func (k Keeper) incrementPoolCreated(ctx context.Context, creator string) error {
	metrics, err := k.getOrCreateMetrics(ctx, creator)
	if err != nil {
		return err
	}

	metrics.PoolsCreated++

	return k.saveMetrics(ctx, metrics)
}

// incrementLiquidityOp increments liquidity add or remove counter.
func (k Keeper) incrementLiquidityOp(ctx context.Context, signer string, isAdd bool) error {
	metrics, err := k.getOrCreateMetrics(ctx, signer)
	if err != nil {
		return err
	}

	if isAdd {
		metrics.LiquidityAdds++
	} else {
		metrics.LiquidityRemoves++
	}

	return k.saveMetrics(ctx, metrics)
}

// incrementPositionOpened increments positions_opened counter.
func (k Keeper) incrementPositionOpened(ctx context.Context, user string) error {
	metrics, err := k.getOrCreateMetrics(ctx, user)
	if err != nil {
		return err
	}

	metrics.PositionsOpened++

	return k.saveMetrics(ctx, metrics)
}

// incrementPositionClosed increments positions_closed counter and tracks interest/PnL.
func (k Keeper) incrementPositionClosed(ctx context.Context, user string, interestPaid sdk.Coin, pnl sdk.Coin) error {
	metrics, err := k.getOrCreateMetrics(ctx, user)
	if err != nil {
		return err
	}

	metrics.PositionsClosed++

	// Track interest paid (filter by metadata)
	if k.shouldTrackDenom(ctx, interestPaid.Denom) && interestPaid.IsPositive() {
		metrics.InterestPaid = metrics.InterestPaid.Add(interestPaid)
	}

	// Track PnL (filter by metadata)
	if k.shouldTrackDenom(ctx, pnl.Denom) && pnl.IsPositive() {
		metrics.LeveragePnl = metrics.LeveragePnl.Add(pnl)
	}

	return k.saveMetrics(ctx, metrics)
}

// incrementLiquidation increments liquidations counter and tracks interest.
func (k Keeper) incrementLiquidation(ctx context.Context, user string, interestPaid sdk.Coin) error {
	metrics, err := k.getOrCreateMetrics(ctx, user)
	if err != nil {
		return err
	}

	metrics.Liquidations++

	// Track interest paid (filter by metadata)
	if k.shouldTrackDenom(ctx, interestPaid.Denom) && interestPaid.IsPositive() {
		metrics.InterestPaid = metrics.InterestPaid.Add(interestPaid)
	}

	return k.saveMetrics(ctx, metrics)
}

// incrementOfferCreated increments offers_created counter.
func (k Keeper) incrementOfferCreated(ctx context.Context, maker string) error {
	metrics, err := k.getOrCreateMetrics(ctx, maker)
	if err != nil {
		return err
	}

	metrics.OffersCreated++

	return k.saveMetrics(ctx, metrics)
}

// incrementOfferStatusChange increments offers_closed or offers_cancelled and tracks maker volume.
func (k Keeper) incrementOfferStatusChange(ctx context.Context, maker string, newStatus string, volumeTaken sdk.Coin) error {
	metrics, err := k.getOrCreateMetrics(ctx, maker)
	if err != nil {
		return err
	}

	switch newStatus {
	case "closed":
		metrics.OffersClosed++
	case "cancelled":
		metrics.OffersCancelled++
	}

	// Track maker volume (filter by metadata)
	if k.shouldTrackDenom(ctx, volumeTaken.Denom) && volumeTaken.IsPositive() {
		metrics.MakerVolume = metrics.MakerVolume.Add(volumeTaken)
	}

	return k.saveMetrics(ctx, metrics)
}

// incrementAuctionCreated increments auctions_created and tracks volume.
func (k Keeper) incrementAuctionCreated(ctx context.Context, seller string, sellAmount sdk.Coin) error {
	metrics, err := k.getOrCreateMetrics(ctx, seller)
	if err != nil {
		return err
	}

	metrics.AuctionsCreated++

	// Track auction volume (filter by metadata)
	if k.shouldTrackDenom(ctx, sellAmount.Denom) && sellAmount.IsPositive() {
		metrics.AuctionVolume = metrics.AuctionVolume.Add(sellAmount)
	}

	return k.saveMetrics(ctx, metrics)
}
