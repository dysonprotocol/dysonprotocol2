package keeper

import (
	"context"
	"errors"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
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

// checkAddressMetricsInvariants validates address metrics for consistency and correctness.
func (k Keeper) checkAddressMetricsInvariants(ctx context.Context, metrics whaleswapv1.AddressMetrics) error {
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Logical consistency checks
	if metrics.OffersClosed+metrics.OffersCancelled > metrics.OffersCreated {
		return cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest,
			"offers lifecycle inconsistent: closed(%d) + cancelled(%d) > created(%d)",
			metrics.OffersClosed, metrics.OffersCancelled, metrics.OffersCreated)
	}
	if metrics.PositionsClosed > metrics.PositionsOpened {
		return cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest,
			"positions inconsistent: closed(%d) > opened(%d)",
			metrics.PositionsClosed, metrics.PositionsOpened)
	}
	if metrics.LiquidityRemoves > metrics.LiquidityAdds {
		return cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest,
			"liquidity inconsistent: removes(%d) > adds(%d)",
			metrics.LiquidityRemoves, metrics.LiquidityAdds)
	}

	// Validate coin arrays - all amounts must be positive, denoms valid
	coinArrays := []sdk.Coins{
		metrics.TotalVolumeSent,
		metrics.TotalVolumeReceived,
		metrics.LpFeesEarned,
		metrics.LpInterestEarned,
		metrics.InterestPaid,
		metrics.LeveragePnl,
		metrics.MakerVolume,
		metrics.AuctionVolume,
	}

	for i, coins := range coinArrays {
		for _, coin := range coins {
			if err := sdk.ValidateDenom(coin.Denom); err != nil {
				return cosmossdkerrors.Wrapf(err, "invalid denom in coin array %d: %s", i, coin.Denom)
			}
			if !coin.Amount.IsPositive() {
				return cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest,
					"non-positive coin amount in array %d: %s", i, coin.String())
			}
		}
	}

	// Temporal consistency - block height should not be in the future
	if metrics.BlockHeight > uint64(sdkCtx.BlockHeight()) {
		return cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest,
			"block height in future: %d > %d", metrics.BlockHeight, sdkCtx.BlockHeight())
	}

	return nil
}

// saveMetrics persists metrics and updates block height.
func (k Keeper) saveMetrics(ctx context.Context, metrics whaleswapv1.AddressMetrics) error {
	// Run invariant checks first
	if err := k.checkAddressMetricsInvariants(ctx, metrics); err != nil {
		return cosmossdkerrors.Wrap(err, "address metrics invariants failed")
	}

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
	return k.recordPositionCloseMetrics(ctx, user, interestPaid, pnl, true)
}

// trackPartialCloseMetrics updates interest/PnL without incrementing positions_closed.
func (k Keeper) trackPartialCloseMetrics(ctx context.Context, user string, interestPaid sdk.Coin, pnl sdk.Coin) error {
	return k.recordPositionCloseMetrics(ctx, user, interestPaid, pnl, false)
}

func (k Keeper) recordPositionCloseMetrics(ctx context.Context, user string, interestPaid sdk.Coin, pnl sdk.Coin, incrementClosed bool) error {
	metrics, err := k.getOrCreateMetrics(ctx, user)
	if err != nil {
		return err
	}

	if incrementClosed {
		metrics.PositionsClosed++
	}

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
