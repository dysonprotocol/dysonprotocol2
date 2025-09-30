package keeper

import (
	"context"
	"fmt"
	"strings"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

func (k Keeper) ConvertToLiquid(ctx context.Context, msg *whaleswapv1.MsgConvertToLiquid) (*whaleswapv1.MsgConvertToLiquidResponse, error) {
	callerBz, err := k.accKeeper.AddressCodec().StringToBytes(msg.Caller)
	if err != nil {
		return nil, fmt.Errorf("invalid caller")
	}
	caller := sdk.AccAddress(callerBz)
	if strings.TrimSpace(msg.Denom) == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "denom required")
	}
	// Prevent double-wrapping: solid only
	if k.isLiquidDenom(msg.Denom) {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "denom is already liquid")
	}
	amt, ok := math.NewIntFromString(msg.Amount)
	if !ok || !amt.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid amount")
	}
	// Ensure whaleswap root name exists and resolves to the module address so
	// nameservice minting under whaleswap.dys/* is authorized.
	if err := k.ensureWhaleswapRootName(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to ensure whaleswap root name")
	}
	if err := k.bank.SendCoinsFromAccountToModule(ctx, caller, whaleswap.ModuleName, sdk.NewCoins(sdk.NewCoin(msg.Denom, amt))); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to escrow solid %s from %s", sdk.NewCoin(msg.Denom, amt).String(), msg.Caller)
	}
	liquidDenom := whaleswapv1.LiquidDenom(msg.Denom)
	mintMsg := &nameservicev1.MsgMintCoins{
		NameDestination: k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String(),
		Amount:          sdk.NewCoins(sdk.NewCoin(liquidDenom, amt)),
		MintFee:         sdk.NewCoin(whaleswapv1.MintFeeDenom, math.NewInt(0)),
	}
	if _, err := k.nameSvc.MintCoins(ctx, mintMsg); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to mint liquid %s", sdk.NewCoin(liquidDenom, amt).String())
	}
	if err := k.bank.SendCoinsFromModuleToAccount(ctx, whaleswap.ModuleName, caller, sdk.NewCoins(sdk.NewCoin(liquidDenom, amt))); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to send liquid %s to %s", sdk.NewCoin(liquidDenom, amt).String(), msg.Caller)
	}
	return &whaleswapv1.MsgConvertToLiquidResponse{LiquidDenom: liquidDenom, Amount: amt.String()}, nil
}

func (k Keeper) ConvertToSolid(ctx context.Context, msg *whaleswapv1.MsgConvertToSolid) (*whaleswapv1.MsgConvertToSolidResponse, error) {
	callerBz, err := k.accKeeper.AddressCodec().StringToBytes(msg.Caller)
	if err != nil {
		return nil, fmt.Errorf("invalid caller")
	}
	caller := sdk.AccAddress(callerBz)
	if strings.TrimSpace(msg.LiquidDenom) == "" {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "liquid_denom required")
	}
	amt, ok := math.NewIntFromString(msg.Amount)
	if !ok || !amt.IsPositive() {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid amount")
	}
	solid, err := k.decodeLiquidDenom(msg.LiquidDenom)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "invalid liquid denom: %s", msg.LiquidDenom)
	}
	if err := k.bank.SendCoinsFromAccountToModule(ctx, caller, whaleswap.ModuleName, sdk.NewCoins(sdk.NewCoin(msg.LiquidDenom, amt))); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to escrow liquid %s from %s", sdk.NewCoin(msg.LiquidDenom, amt).String(), msg.Caller)
	}
	if _, err := k.nameSvc.BurnCoins(ctx, &nameservicev1.MsgBurnCoins{
		NameDestination: k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String(),
		Amount:          sdk.NewCoins(sdk.NewCoin(msg.LiquidDenom, amt)),
	}); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to burn liquid %s", sdk.NewCoin(msg.LiquidDenom, amt).String())
	}
	// Ensure available solid backing is sufficient: subtract AMM reserves, offer escrow, auctions and pfand
	ammRequired, err := k.tallyAMMReserves(ctx)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "tally AMM reserves")
	}
	escrowRequired, err := k.tallyEscrowRequired(ctx)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "tally escrow required")
	}
	pfandRequired, err := k.tallyPfandRequired(ctx)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "tally pfand required")
	}
	auctionRequired, err := k.tallyAuctionRequired(ctx)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "tally auctions required")
	}
	moduleAddr := k.accKeeper.GetModuleAddress(whaleswap.ModuleName)
	bal := k.bank.GetBalance(ctx, moduleAddr, solid).Amount
	need := ammRequired.AmountOf(solid).Add(escrowRequired.AmountOf(solid)).Add(auctionRequired.AmountOf(solid)).Add(pfandRequired.AmountOf(solid))
	available := bal.Sub(need)
	if available.LT(amt) {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "insufficient backing for %s: available=%s need=%s", solid, available.String(), amt.String())
	}
	if err := k.bank.SendCoinsFromModuleToAccount(ctx, whaleswap.ModuleName, caller, sdk.NewCoins(sdk.NewCoin(solid, amt))); err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to send solid %s to %s", sdk.NewCoin(solid, amt).String(), msg.Caller)
	}
	return &whaleswapv1.MsgConvertToSolidResponse{AmountOut: sdk.NewCoin(solid, amt)}, nil
}
