package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	cosmossdk_math "cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
)

// obPairKey returns the canonical pair key low|high.
func (k Keeper) obPairKey(denomA, denomB string) string {
	low, high := denomA, denomB
	if low > high {
		low, high = high, low
	}
	return low + "|" + high
}

// shouldReversePairOrder indicates whether the canonical pair key (low|high)
// differs from the requested have/want orientation (i.e. have > want).
func shouldReversePairOrder(haveDenom, wantDenom string) bool {
	return haveDenom > wantDenom
}

// obPriceKeyFromAmounts computes the price key string using the same orientation
// as existing indexing code. The price is derived from have/want amounts but
// normalized to the low|high orientation to maintain a single ordered book.
func (k Keeper) obPriceKeyFromAmounts(haveDenom, wantDenom string, haveAmt, wantAmt cosmossdk_math.Int) (pairKey string, priceKey string) {
	low, high := haveDenom, wantDenom
	if low > high {
		low, high = high, low
	}
	pairKey = low + "|" + high
	// priceHavePerWant = have / want; priceWantPerHave = want / have
	priceHavePerWant := cosmossdk_math.LegacyNewDecFromInt(haveAmt).Quo(cosmossdk_math.LegacyNewDecFromInt(wantAmt))
	priceWantPerHave := cosmossdk_math.LegacyNewDecFromInt(wantAmt).Quo(cosmossdk_math.LegacyNewDecFromInt(haveAmt))
	priceDec := priceWantPerHave
	if low == wantDenom && high == haveDenom {
		priceDec = priceHavePerWant
	}
	priceKey = priceDec.String()
	return
}

// obPriceKeyFromUnits computes the price removal key from unit ints when
// remaining amounts may be zero at close/cancel time.
func (k Keeper) obPriceKeyFromUnits(haveDenom, wantDenom, unitHaveStr, unitWantStr string) (pairKey string, priceKey string) {
	uh, _ := cosmossdk_math.NewIntFromString(unitHaveStr)
	uw, _ := cosmossdk_math.NewIntFromString(unitWantStr)
	return k.obPriceKeyFromAmounts(haveDenom, wantDenom, uh, uw)
}

// indexOfferOpen writes all reverse indexes for an open offer.
func (k Keeper) indexOfferOpen(ctx context.Context, offer whaleswapv1.OfferData) error {
	// have, id -> id
	if err := k.OffersByHave.Set(ctx, collections.Join(offer.RemainingHave.Denom, offer.OfferId), offer.OfferId); err != nil {
		return err
	}
	// want, id -> id
	if err := k.OffersByWant.Set(ctx, collections.Join(offer.RemainingWant.Denom, offer.OfferId), offer.OfferId); err != nil {
		return err
	}
	// price index
	pairKey, priceKey := k.obPriceKeyFromAmounts(
		offer.RemainingHave.Denom,
		offer.RemainingWant.Denom,
		offer.RemainingHave.Amount,
		offer.RemainingWant.Amount,
	)
	if err := k.OffersByPairPrice.Set(ctx, collections.Join3(pairKey, priceKey, offer.OfferId), offer.OfferId); err != nil {
		return err
	}
	// owner+status
	if err := k.OffersByOwnerStatus.Set(ctx, collections.Join3(offer.Maker, offer.Status, offer.OfferId), offer.OfferId); err != nil {
		return err
	}
	return nil
}

// unindexOfferAll removes all reverse indexes for an offer using unit ints for price key.
func (k Keeper) unindexOfferAll(ctx context.Context, offer whaleswapv1.OfferData) {
	_ = k.OffersByHave.Remove(ctx, collections.Join(offer.RemainingHave.Denom, offer.OfferId))
	_ = k.OffersByWant.Remove(ctx, collections.Join(offer.RemainingWant.Denom, offer.OfferId))
	pairKey, priceKey := k.obPriceKeyFromUnits(offer.RemainingHave.Denom, offer.RemainingWant.Denom, offer.UnitHaveInt, offer.UnitWantInt)
	_ = k.OffersByPairPrice.Remove(ctx, collections.Join3(pairKey, priceKey, offer.OfferId))
}

// reindexOfferOnStatusChange updates owner/status mapping and removes open indexes when leaving Open.
func (k Keeper) reindexOfferOnStatusChange(ctx context.Context, prev whaleswapv1.OfferData, next whaleswapv1.OfferData) error {
	if prev.Status != next.Status {
		if err := k.OffersByOwnerStatus.Remove(ctx, collections.Join3(prev.Maker, prev.Status, prev.OfferId)); err != nil {
			return err
		}
		if err := k.OffersByOwnerStatus.Set(ctx, collections.Join3(next.Maker, next.Status, next.OfferId), next.OfferId); err != nil {
			return err
		}
	}
	// Leaving Open → remove reverse indexes
	if prev.Status == whaleswapv1.OfferStatusOpen && next.Status != whaleswapv1.OfferStatusOpen {
		k.unindexOfferAll(ctx, prev)
	}
	// Entering Open (not used today) → add reverse indexes
	if prev.Status != whaleswapv1.OfferStatusOpen && next.Status == whaleswapv1.OfferStatusOpen {
		if err := k.indexOfferOpen(ctx, next); err != nil {
			return err
		}
	}
	return nil
}

// ---- side-effect helpers (escrow / send) ----

// wsMoveCoins duplicates nameservice's moveCoins helper semantics, but allows whaleswap
// to orchestrate a batch multisend for arbitrary denoms between participants via the module.
func (k Keeper) wsMoveCoins(ctx context.Context, inputs []banktypes.Input, outputs []banktypes.Output) error {
	// validate: non-empty, totals match, no negative
	if len(inputs) == 0 || len(outputs) == 0 {
		return cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "inputs/outputs cannot be empty")
	}
	totalIn := sdk.NewCoins()
	for idx, in := range inputs {
		if err := in.ValidateBasic(); err != nil {
			return cosmossdkerrors.Wrapf(err, "invalid input[%d]", idx)
		}
		totalIn = totalIn.Add(in.Coins...)
	}
	totalOut := sdk.NewCoins()
	for idx, out := range outputs {
		if err := out.ValidateBasic(); err != nil {
			return cosmossdkerrors.Wrapf(err, "invalid output[%d]", idx)
		}
		totalOut = totalOut.Add(out.Coins...)
	}
	if !totalIn.Equal(totalOut) {
		return cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "total in %s != total out %s", totalIn.String(), totalOut.String())
	}

	// Execute: first pull all inputs into whaleswap module, then fan out to outputs
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	mod := whaleswap.ModuleName
	for _, in := range inputs {
		from, err := sdk.AccAddressFromBech32(in.Address)
		if err != nil {
			return cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid input address: %s", in.Address)
		}

		modAddr := k.accKeeper.GetModuleAddress(mod)
		if err := k.bank.SendCoins(sdkCtx, from, modAddr, in.Coins); err != nil {
			return err
		}
	}
	for _, out := range outputs {
		to, err := sdk.AccAddressFromBech32(out.Address)
		if err != nil {
			return cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid output address: %s", out.Address)
		}
		modAddr := k.accKeeper.GetModuleAddress(mod)
		if err := k.bank.SendCoins(sdkCtx, modAddr, to, out.Coins); err != nil {
			return err
		}
	}
	return nil
}

// ---- parsing helpers ----

// parseTakeUnits returns the requested take units or remaining if blank.
func (k Keeper) parseTakeUnits(remainingUnits cosmossdk_math.Int, takeUnitsStr string) (cosmossdk_math.Int, error) {
	if !remainingUnits.IsPositive() {
		return cosmossdk_math.Int{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid remaining units")
	}
	tu := remainingUnits
	if len(takeUnitsStr) > 0 {
		u, ok := cosmossdk_math.NewIntFromString(takeUnitsStr)
		if !ok || !u.IsPositive() {
			return cosmossdk_math.Int{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid take_units")
		}
		if u.GT(remainingUnits) {
			return cosmossdk_math.Int{}, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "take_units exceeds remaining")
		}
		tu = u
	}
	return tu, nil
}
