package whaleswap

import (
	"dysonprotocol.com/x/whaleswap/types"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/msgservice"
)

// RegisterLegacyAminoCodec registers all necessary concrete types for Amino.
func RegisterLegacyAminoCodec(registrar interface{}) {}

// RegisterInterfaces registers interface types with the interface registry.
func RegisterInterfaces(registrar codectypes.InterfaceRegistry) {
	registrar.RegisterImplementations((*sdk.Msg)(nil),
		&types.MsgCreatePool{},
		&types.MsgUpdatePoolConfig{},
		&types.MsgAddLiquidity{},
		&types.MsgRemoveLiquidity{},
		&types.MsgPoolSwap{},
		&types.MsgMakeOffer{},
		&types.MsgTakeOffer{},
		&types.MsgCancelOffer{},
		&types.MsgOpenAuction{},
		&types.MsgRedeemAuction{},
		&types.MsgUpdateParams{},
	)

	registrar.RegisterImplementations(
		(*sdk.Msg)(nil),
		&types.MsgCreatePoolResponse{},
		&types.MsgUpdatePoolConfigResponse{},
		&types.MsgAddLiquidityResponse{},
		&types.MsgRemoveLiquidityResponse{},
		&types.MsgPoolSwapResponse{},
		&types.MsgMakeOfferResponse{},
		&types.MsgTakeOfferResponse{},
		&types.MsgCancelOfferResponse{},
		&types.MsgOpenAuctionResponse{},
		&types.MsgRedeemAuctionResponse{},
		&types.MsgUpdateParamsResponse{},
	)

	msgservice.RegisterMsgServiceDesc(registrar, &types.Msg_serviceDesc)
}
