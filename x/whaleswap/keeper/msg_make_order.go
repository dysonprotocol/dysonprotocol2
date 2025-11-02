package keeper

import (
	"context"
	"strconv"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

// MakeOffer creates an orderbook offer of a given amount of "have" for a given amount of "want".
// ESCROW: base "have" is escrowed in the module.
// LIQUID: lock PFAND in the module; settlement draws from maker balance at take. Units are
// derived via GCD for partial fills.
//
// Semantics:
//   - Validates maker address, have/want coins (different denoms, positive amounts).
//   - For ESCROW mode: escrows base have from maker to module.
//   - For LIQUID mode: locks PFAND from maker to module (if configured).
//   - Computes GCD of have/want amounts to establish unit_have/unit_want ratios.
//   - Creates offer with remaining_units = GCD, status = open.
//   - Persists offer and indexes it for queries.
//
// Validation:
//   - Maker address must be valid.
//   - Have/want denoms must be valid and different.
//   - Have/want amounts must be positive.
//   - Maker must hold sufficient have amount (for escrow check).
//   - For LIQUID mode: maker must hold sufficient PFAND if configured.
//
// State Updates:
//   - For ESCROW: transfers have from maker to module.
//   - For LIQUID: transfers PFAND from maker to module.
//   - Allocates new offer ID from sequence.
//   - Persists offer to OffersMap.
//   - Indexes offer for open status queries.
//
// Emits:
//   - EventOfferCreated with offer_id
//   - EventPfandLocked with amount, offer_id (if PFAND locked)
//
// Returns:
//   - *whaleswapv1.MsgMakeOfferResponse with offer_id.
//
// Errors are returned on validation failures (invalid maker, denoms/amounts,
// insufficient balance) or execution failures (transfers, persistence, indexing,
// invariant violations); no panics.
func (k Keeper) MakeOffer(ctx context.Context, msg *whaleswapv1.MsgMakeOffer) (*whaleswapv1.MsgMakeOfferResponse, error) {
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	logger := k.Logger(sdkCtx)

	logger.Info("MakeOffer starting", "maker", msg.Maker, "have", msg.Have, "want", msg.Want)

	// Parse maker
	makerBz, err := k.accKeeper.AddressCodec().StringToBytes(msg.Maker)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid maker: %s", err.Error())
	}
	maker := sdk.AccAddress(makerBz)

	have := msg.Have
	want := msg.Want
	if err := sdk.ValidateDenom(have.Denom); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid have denom: %s", have.Denom)
	}
	if err := sdk.ValidateDenom(want.Denom); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid want denom: %s", want.Denom)
	}
	if have.Denom == want.Denom {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "have and want denoms must differ: %s", have.Denom)
	}
	if !have.Amount.IsPositive() || !want.Amount.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "amounts must be > 0")
	}

	// Any denoms allowed (including pfand); remove want supply gating
	// Per-offer balance check: maker must currently hold at least `have` amount
	balHaveCoin := k.bank.GetBalance(ctx, maker, have.Denom)
	logger.Info("MakeOffer balance check", "maker_balance", balHaveCoin, "required_have", have)
	if !balHaveCoin.IsGTE(have) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "have exceeds maker balance: %s < %s", balHaveCoin.String(), have.String())
	}

	logger.Info("MakeOffer processing escrow/pfand")
	pfandCoin := sdk.NewCoin(k.GetParams(ctx).PfandPerOffer.Denom, math.NewInt(0))
	// Determine settlement mode: explicit only
	mode := msg.SettlementMode
	if mode == whaleswapv1.SettlementMode_SETTLEMENT_LIQUID {
		// Liquid settlement mode: lock pfand (if > 0), do not escrow base have
		req := k.GetParams(ctx).PfandPerOffer
		if !req.Amount.IsZero() {
			bal := k.bank.GetBalance(ctx, maker, req.Denom)
			if !bal.IsGTE(req) {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "insufficient pfand: %s < %s", bal.String(), req.String())
			}
			if err := k.bank.SendCoinsFromAccountToModule(ctx, maker, whaleswap.ModuleName, sdk.NewCoins(req)); err != nil {
				return nil, cosmossdkerrors.Wrapf(err, "failed to lock pfand %s from maker %s", req.String(), msg.Maker)
			}
		}
		pfandCoin = k.GetParams(ctx).PfandPerOffer
		logger.Info("MakeOffer pfand locked", "pfand_amount", pfandCoin)
	} else {
		// Escrow mode: escrow base have in module
		if err := k.bank.SendCoinsFromAccountToModule(ctx, maker, whaleswap.ModuleName, sdk.NewCoins(have)); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to escrow have %s from maker %s", have.String(), msg.Maker)
		}
		logger.Info("MakeOffer have escrowed", "escrowed_amount", have)
	}

	// GCD-first units: reduce ratio to simplest terms
	logger.Info("MakeOffer calculating units", "have_amount", have.Amount, "want_amount", want.Amount)
	g := k.gcdInt(have.Amount, want.Amount)
	if !g.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid gcd")
	}
	unitHave := have.Amount.Quo(g)
	unitWant := want.Amount.Quo(g)
	if unitHave.IsZero() || unitWant.IsZero() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid unit ints")
	}
	remainingUnits := g
	if remainingUnits.IsZero() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "remaining units is zero")
	}

	id, err := k.offerSeq.Next(ctx)
	if err != nil {
		return nil, err
	}
	t := sdkCtx.BlockTime()
	logger.Info("MakeOffer creating offer", "offer_id", id, "unit_have", unitHave, "unit_want", unitWant, "remaining_units", remainingUnits, "pfand_locked", pfandCoin)
	offer := whaleswapv1.OfferData{
		OfferId:        id,
		Status:         whaleswapv1.OfferStatusOpen,
		Maker:          msg.Maker,
		CreatedHeight:  uint64(sdkCtx.BlockHeight()),
		CreatedTime:    &t,
		UpdatedHeight:  uint64(sdkCtx.BlockHeight()),
		UpdatedTime:    &t,
		InitialHave:    have,
		InitialWant:    want,
		RemainingHave:  have,
		RemainingWant:  want,
		UnitHaveInt:    unitHave.String(),
		UnitWantInt:    unitWant.String(),
		RemainingUnits: remainingUnits.String(),
		PfandLocked:    pfandCoin,
		SettlementMode: mode,
	}
	if err := k.OffersMap.Set(ctx, id, offer); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to save offer %d", id)
	}
	logger.Info("MakeOffer offer saved", "offer_id", id)
	if err := k.indexOfferOpen(ctx, offer); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to index offer %d", id)
	}
	logger.Info("MakeOffer offer indexed", "offer_id", id)
	// Emit EventOfferCreated with plain numeric string (no extra quotes) for offer_id
	sdkCtx.EventManager().EmitEvent(
		sdk.NewEvent(
			"dysonprotocol.whaleswap.v1.EventOfferCreated",
			sdk.NewAttribute("offer_id", strconv.FormatUint(id, 10)),
		),
	)
	if pfandCoin.Amount.IsPositive() {
		logger.Info("MakeOffer emitting pfand locked event", "offer_id", id, "pfand_amount", pfandCoin)
		if err := sdkCtx.EventManager().EmitTypedEvent(&whaleswapv1.EventPfandLocked{
			Amount:  pfandCoin,
			OfferId: id,
		}); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to emit EventPfandLocked")
		}
	}
	logger.Info("MakeOffer checking invariants")
	if err := k.AssertInvariants(ctx); err != nil {
		logger.Error("MakeOffer invariant check failed", "error", err)
		return nil, cosmossdkerrors.Wrap(err, "invariant failed after MakeOffer")
	}
	logger.Info("MakeOffer completed successfully", "offer_id", id)
	return &whaleswapv1.MsgMakeOfferResponse{OfferId: id}, nil
}
