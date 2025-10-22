package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

func (k Keeper) CreatePool(ctx context.Context, msg *whaleswapv1.MsgCreatePool) (*whaleswapv1.MsgCreatePoolResponse, error) {
	if len(msg.Coins) != 2 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "coins must contain exactly 2 entries, got %d", len(msg.Coins))
	}

	msg.Coins.Sort()
	msg.MinPrice.Sort()
	msg.MaxPrice.Sort()
	err := msg.Coins.Validate()
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid coins: %v", err)
	}
	// Bands are optional; validate only when provided
	if len(msg.MinPrice) > 0 {
		if err = msg.MinPrice.Validate(); err != nil {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid min_price: %v", err)
		}
	}
	if len(msg.MaxPrice) > 0 {
		if err = msg.MaxPrice.Validate(); err != nil {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid max_price: %v", err)
		}
	}
	denom1, denom2 := msg.Coins[0].Denom, msg.Coins[1].Denom

	if msg.FeePct != "" {
		fee, err := math.LegacyNewDecFromStr(msg.FeePct)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid fee_pct: %v", err)
		}
		if fee.IsNegative() || fee.GTE(math.LegacyNewDec(1)) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "fee_pct must satisfy 0 <= fee < 1: %s", fee.String())
		}
	}

	hasBounds := len(msg.MinPrice) > 0 || len(msg.MaxPrice) > 0
	if hasBounds != (len(msg.MinPrice) > 0 && len(msg.MaxPrice) > 0) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "min_price and max_price must both be set or both unset")
	}

	if len(msg.Coins) != 2 {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "coins must have exactly 2 coins")
	}

	if msg.Coins[0].Amount.IsZero() || msg.Coins[1].Amount.IsZero() {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "initial reserves must be positive: msg: %+v coins: %+v", msg, msg.Coins)
	}

	if hasBounds {
		if len(msg.MinPrice) != 2 || len(msg.MaxPrice) != 2 {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "min_price and max_price must each have exactly two coins")
		}
		// the denoms must be the same as the coins and each other (canonical order)
		if msg.MinPrice[0].Denom != denom1 || msg.MinPrice[1].Denom != denom2 || msg.MaxPrice[0].Denom != denom1 || msg.MaxPrice[1].Denom != denom2 {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "min_price and max_price must have the same denoms as coins")
		}
		// integer cross-multiplication comparisons (avoid Decs):
		// price = R_quote / R_base; min = minQuote/minBase; max = maxQuote/maxBase
		minBase := msg.MinPrice[0].Amount
		minQuote := msg.MinPrice[1].Amount
		maxBase := msg.MaxPrice[0].Amount
		maxQuote := msg.MaxPrice[1].Amount
		// disallow equality; if user swapped, normalize by swapping
		if maxQuote.Mul(minBase).Equal(minQuote.Mul(maxBase)) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "max_price must be greater than min_price")
		}
		// Normalize order so that min <= max
		if minQuote.Mul(maxBase).GT(maxQuote.Mul(minBase)) {
			msg.MinPrice, msg.MaxPrice = msg.MaxPrice, msg.MinPrice
			minBase = msg.MinPrice[0].Amount
			minQuote = msg.MinPrice[1].Amount
			maxBase = msg.MaxPrice[0].Amount
			maxQuote = msg.MaxPrice[1].Amount
		}
		// Initial price must be strictly within (min, max)
		rBase := msg.Coins[0].Amount
		rQuote := msg.Coins[1].Amount
		if rQuote.Mul(minBase).LTE(rBase.Mul(minQuote)) || rQuote.Mul(maxBase).GTE(rBase.Mul(maxQuote)) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "initial price must be within min and max bounds: coins=%s min=%s max=%s", msg.Coins.String(), msg.MinPrice.String(), msg.MaxPrice.String())
		}
	}

	from, err := k.addr(ctx, msg.Creator)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to get creator address: %s", msg.Creator)
	}

	if err := k.sendToModule(ctx, from, msg.Coins); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to send funds to module: %s: %+v", from.String(), msg)
	}

	id, err := k.poolSeq.Next(ctx)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to allocate new pool id: %+v", msg)
	}
	sharesDenom := whaleswapv1.PoolSharesDenom(id)

	sdkCtx := sdk.UnwrapSDKContext(ctx)
	t := sdkCtx.BlockTime()
	pool := whaleswapv1.Pool{
		PoolId:      id,
		Coins:       msg.Coins,
		SharesDenom: sharesDenom,
		FeePct:      msg.FeePct,
		MinPrice:    msg.MinPrice,
		MaxPrice:    msg.MaxPrice,
		BlockHeight: uint64(sdkCtx.BlockHeight()),
		Created:     &t,
		Updated:     &t,
		NumTrades:   0,
	}

	var initialShares math.Int
	if hasBounds {
		L, _, _, err := k.liquidityForReserves(pool)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to compute initial liquidity: %+v", msg)
		}
		initialShares = L.TruncateInt()
	} else {
		prod := math.LegacyNewDecFromInt(msg.Coins[0].Amount).Mul(math.LegacyNewDecFromInt(msg.Coins[1].Amount))
		sqrt, err := prod.ApproxSqrt()
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to compute sqrt of initial product: %+v", msg)
		}
		initialShares = sqrt.TruncateInt()
	}
	if !initialShares.IsPositive() {
		initialShares = math.NewInt(1)
	}

	if err := k.PoolsMap.Set(ctx, id, pool); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to set pool: %+v", msg)
	}

	if err := k.ensureWhaleswapRootName(ctx); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed ensuring whaleswap.dys root before minting shares for pool %d: %+v", id, msg)
	}

	mintMsg := &nameservicev1.MsgMintCoins{
		NameDestination: k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String(),
		Amount:          sdk.NewCoins(sdk.NewCoin(sharesDenom, initialShares)),
		MintFee:         sdk.NewCoin(whaleswapv1.MintFeeDenom, math.NewInt(0)),
	}
	if _, err := k.nameSvc.MintCoins(ctx, mintMsg); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to mint shares: %+v", msg)
	}

	if err := k.sendFromModule(ctx, from, sdk.NewCoins(sdk.NewCoin(sharesDenom, initialShares))); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to send minted shares: %+v", msg)
	}

	sdkCtx.EventManager().EmitTypedEvents(
		&whaleswapv1.EventPoolCreated{PoolId: id},
		&whaleswapv1.EventPoolUpdate{PoolId: id},
	)

	if err := k.AssertAMMInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "AMM invariant failed after CreatePool: pool_id=%d coins=%s shares_denom=%s", id, msg.Coins.String(), sharesDenom)
	}

	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invariant after CreatePool")
	}

	return &whaleswapv1.MsgCreatePoolResponse{PoolId: id}, nil
}
