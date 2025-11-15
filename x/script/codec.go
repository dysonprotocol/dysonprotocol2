package script

import (
	scripttypes "dysonprotocol.com/x/script/types"
	"github.com/cosmos/cosmos-sdk/codec"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/msgservice"

	"github.com/cosmos/cosmos-sdk/codec/legacy"

	feegrant "cosmossdk.io/x/feegrant"
	nft "dysonprotocol.com/x/nft"
	authz "github.com/cosmos/cosmos-sdk/x/authz"

	govtypesv1 "github.com/cosmos/cosmos-sdk/x/gov/types/v1"
	govv1beta "github.com/cosmos/cosmos-sdk/x/gov/types/v1beta1"

	// all the types from the other modules
	evidencetypes "cosmossdk.io/x/evidence/types"
	upgradetypes "cosmossdk.io/x/upgrade/types"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	bank "github.com/cosmos/cosmos-sdk/x/bank/types"
	consensustypes "github.com/cosmos/cosmos-sdk/x/consensus/types"
	distributiontypes "github.com/cosmos/cosmos-sdk/x/distribution/types"
	minttypes "github.com/cosmos/cosmos-sdk/x/mint/types"
	protocolpooltypes "github.com/cosmos/cosmos-sdk/x/protocolpool/types"
	slashingtypes "github.com/cosmos/cosmos-sdk/x/slashing/types"
	stakingtypes "github.com/cosmos/cosmos-sdk/x/staking/types"
	interchainaccountstypes "github.com/cosmos/ibc-go/v10/modules/apps/27-interchain-accounts/controller/types"
	icahosttypes "github.com/cosmos/ibc-go/v10/modules/apps/27-interchain-accounts/host/types"
	ibctransfertypes "github.com/cosmos/ibc-go/v10/modules/apps/transfer/types"

	nameservicetypes "dysonprotocol.com/x/nameservice/types"
	storagetypes "dysonprotocol.com/x/storage/types"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	gogoprotoany "github.com/cosmos/gogoproto/types/any"

	crontasktypes "dysonprotocol.com/x/crontask/types"
)

// RegisterLegacyAminoCodec registers all the necessary group module concrete
// types and interfaces with the provided codec reference.
// These types are used for Amino JSON serialization.
func RegisterLegacyAminoCodec(cdc *codec.LegacyAmino) {
	legacy.RegisterAminoMsg(cdc, &scripttypes.MsgExec{}, "dys/script/MsgExec")
	legacy.RegisterAminoMsg(cdc, &scripttypes.MsgUpdateScript{}, "dys/script/MsgUpdateScript")
	legacy.RegisterAminoMsg(cdc, &scripttypes.MsgCreateNewScript{}, "dys/script/MsgCreateNewScript")
	legacy.RegisterAminoMsg(cdc, &scripttypes.MsgUpdateParams{}, "dys/script/MsgUpdateParams")
	legacy.RegisterAminoMsg(cdc, &scripttypes.MsgSudo{}, "dys/script/MsgSudo")

	// Register ScriptExecAuthorization
	cdc.RegisterConcrete(&scripttypes.ScriptExecAuthorization{}, "dys/script/ScriptExecAuthorization", nil)
}

// RegisterInterfaces registers the interfaces types with the interface registry.
// This is a little unique in that we MUST register ALL interface that the script module depends on so they can be
// decoded automatically in the dyslang scripts.
func RegisterInterfaces(registrar codectypes.InterfaceRegistry) {
	// Register ScriptExecAuthorization as Authorization implementation
	registrar.RegisterImplementations(
		(*authz.Authorization)(nil),
		&scripttypes.ScriptExecAuthorization{},
	)

	// Register UnpackInterfacesMessage implementations
	registrar.RegisterImplementations((*gogoprotoany.UnpackInterfacesMessage)(nil),
		&scripttypes.MsgExec{},
		&scripttypes.MsgExecResponse{},
		&scripttypes.MsgSudo{},
		&scripttypes.MsgSudoResponse{},
		&scripttypes.RunScript{},
		&scripttypes.ResponseRunScript{},
	)

	// Register SDK message implementations
	registrar.RegisterImplementations((*sdk.Msg)(nil),
		&scripttypes.MsgExec{}, &scripttypes.MsgExecResponse{},
		&scripttypes.MsgUpdateScript{}, &scripttypes.MsgUpdateScriptResponse{},
		&scripttypes.MsgCreateNewScript{}, &scripttypes.MsgCreateNewScriptResponse{},
		&scripttypes.MsgUpdateParams{}, &scripttypes.MsgUpdateParamsResponse{},
		&scripttypes.MsgSudo{}, &scripttypes.MsgSudoResponse{},
		&scripttypes.Script{},
		&scripttypes.MsgArbitraryData{},

		// For Query
		&scripttypes.QueryScriptInfoRequest{}, &scripttypes.QueryScriptInfoResponse{},
		&scripttypes.QueryEncodeJsonRequest{}, &scripttypes.QueryEncodeJsonResponse{},
		&scripttypes.QueryDecodeBytesRequest{}, &scripttypes.QueryDecodeBytesResponse{},
		&scripttypes.QueryVerifyTxRequest{}, &scripttypes.QueryVerifyTxResponse{},
		&scripttypes.QueryParamsRequest{}, &scripttypes.QueryParamsResponse{},
		&scripttypes.QueryGetBlockRequest{}, &scripttypes.QueryGetBlockResponse{},
		&scripttypes.RunScript{}, &scripttypes.ResponseRunScript{},

		// script web service
		&scripttypes.WebRequest{}, &scripttypes.WebResponse{},

		// crontask queries
		&crontasktypes.QueryTaskByIDRequest{}, &crontasktypes.QueryTaskByIDResponse{},
		&crontasktypes.QueryTasksByAddressRequest{}, &crontasktypes.QueryTasksResponse{},
		&crontasktypes.QueryTasksByStatusTimestampRequest{}, &crontasktypes.QueryTasksResponse{},
		&crontasktypes.QueryTasksByStatusGasPriceRequest{}, &crontasktypes.QueryTasksResponse{},
		&crontasktypes.QueryAllTasksRequest{}, &crontasktypes.QueryTasksResponse{},
		&crontasktypes.QueryParamsRequest{}, &crontasktypes.QueryParamsResponse{},
		&crontasktypes.QueryMetricsRequest{}, &crontasktypes.QueryMetricsResponse{},
		&crontasktypes.QuerySubscriptionByIDRequest{}, &crontasktypes.QuerySubscriptionByIDResponse{},
		&crontasktypes.QuerySubscriptionsByCreatorRequest{}, &crontasktypes.QuerySubscriptionsResponse{},
		&crontasktypes.QuerySubscriptionsAllRequest{}, &crontasktypes.QuerySubscriptionsResponse{},

		// nameservice
		&nameservicetypes.QueryResolveNameRequest{}, &nameservicetypes.QueryResolveNameResponse{},
		&nameservicetypes.QueryParamsRequest{}, &nameservicetypes.QueryParamsResponse{},
		&nameservicetypes.QueryComputeHashRequest{}, &nameservicetypes.QueryComputeHashResponse{},

		// storage
		&storagetypes.QueryStorageGetRequest{}, &storagetypes.QueryStorageGetResponse{},
		&storagetypes.QueryStorageListRequest{}, &storagetypes.QueryStorageListResponse{},

		// auth
		&authtypes.QueryAccountsRequest{}, &authtypes.QueryAccountsResponse{},
		&authtypes.QueryAccountRequest{}, &authtypes.QueryAccountResponse{},
		&authtypes.QueryParamsRequest{}, &authtypes.QueryParamsResponse{},
		&authtypes.QueryModuleAccountsRequest{}, &authtypes.QueryModuleAccountsResponse{},
		&authtypes.QueryModuleAccountByNameRequest{}, &authtypes.QueryModuleAccountByNameResponse{},
		&authtypes.QueryAccountAddressByIDRequest{}, &authtypes.QueryAccountAddressByIDResponse{},
		&authtypes.QueryAccountInfoRequest{}, &authtypes.QueryAccountInfoResponse{},

		// authz
		&authz.QueryGrantsRequest{}, &authz.QueryGrantsResponse{},
		&authz.QueryGranterGrantsRequest{}, &authz.QueryGranterGrantsResponse{},
		&authz.QueryGranteeGrantsRequest{}, &authz.QueryGranteeGrantsResponse{},

		// bank
		&bank.QueryBalanceRequest{}, &bank.QueryBalanceResponse{},
		&bank.QueryAllBalancesRequest{}, &bank.QueryAllBalancesResponse{},
		&bank.QuerySpendableBalancesRequest{}, &bank.QuerySpendableBalancesResponse{},
		&bank.QuerySpendableBalanceByDenomRequest{}, &bank.QuerySpendableBalanceByDenomResponse{},
		&bank.QueryTotalSupplyRequest{}, &bank.QueryTotalSupplyResponse{},
		&bank.QuerySupplyOfRequest{}, &bank.QuerySupplyOfResponse{},
		&bank.QueryParamsRequest{}, &bank.QueryParamsResponse{},
		&bank.QueryDenomsMetadataRequest{}, &bank.QueryDenomsMetadataResponse{},
		&bank.QueryDenomMetadataRequest{}, &bank.QueryDenomMetadataResponse{},
		&bank.QueryDenomMetadataByQueryStringRequest{}, &bank.QueryDenomMetadataByQueryStringResponse{},
		&bank.QueryDenomOwnersRequest{}, &bank.QueryDenomOwnersResponse{},
		&bank.QueryDenomOwnersByQueryRequest{}, &bank.QueryDenomOwnersByQueryResponse{},
		&bank.QuerySendEnabledRequest{}, &bank.QuerySendEnabledResponse{},
		// bank msg response
		&bank.MsgSendResponse{},

		// circuit

		// consensus
		&consensustypes.QueryParamsRequest{}, &consensustypes.QueryParamsResponse{},

		// distribution
		&distributiontypes.QueryParamsRequest{}, &distributiontypes.QueryParamsResponse{},
		&distributiontypes.QueryValidatorDistributionInfoRequest{}, &distributiontypes.QueryValidatorDistributionInfoResponse{},
		&distributiontypes.QueryValidatorOutstandingRewardsRequest{}, &distributiontypes.QueryValidatorOutstandingRewardsResponse{},
		&distributiontypes.QueryValidatorCommissionRequest{}, &distributiontypes.QueryValidatorCommissionResponse{},
		&distributiontypes.QueryValidatorSlashesRequest{}, &distributiontypes.QueryValidatorSlashesResponse{},
		&distributiontypes.QueryDelegationRewardsRequest{}, &distributiontypes.QueryDelegationRewardsResponse{},
		&distributiontypes.QueryDelegationTotalRewardsRequest{}, &distributiontypes.QueryDelegationTotalRewardsResponse{},
		&distributiontypes.QueryDelegatorValidatorsRequest{}, &distributiontypes.QueryDelegatorValidatorsResponse{},
		&distributiontypes.QueryDelegatorWithdrawAddressRequest{}, &distributiontypes.QueryDelegatorWithdrawAddressResponse{},
		//&distributiontypes.QueryCommunityPoolRequest{}, &distributiontypes.QueryCommunityPoolResponse{},

		// evidence
		&evidencetypes.QueryEvidenceRequest{}, &evidencetypes.QueryEvidenceResponse{},
		&evidencetypes.QueryAllEvidenceRequest{}, &evidencetypes.QueryAllEvidenceResponse{},

		// feegrant
		&feegrant.QueryAllowanceRequest{}, &feegrant.QueryAllowanceResponse{},
		&feegrant.QueryAllowancesRequest{}, &feegrant.QueryAllowancesResponse{},
		&feegrant.QueryAllowancesByGranterRequest{}, &feegrant.QueryAllowancesByGranterResponse{},

		// gov v1
		&govtypesv1.QueryConstitutionRequest{}, &govtypesv1.QueryConstitutionResponse{},
		&govtypesv1.QueryProposalRequest{}, &govtypesv1.QueryProposalResponse{},
		&govtypesv1.QueryProposalsRequest{}, &govtypesv1.QueryProposalsResponse{},
		&govtypesv1.QueryVoteRequest{}, &govtypesv1.QueryVoteResponse{},
		&govtypesv1.QueryVotesRequest{}, &govtypesv1.QueryVotesResponse{},
		&govtypesv1.QueryParamsRequest{}, &govtypesv1.QueryParamsResponse{},
		&govtypesv1.QueryDepositRequest{}, &govtypesv1.QueryDepositResponse{},
		&govtypesv1.QueryDepositsRequest{}, &govtypesv1.QueryDepositsResponse{},
		&govtypesv1.QueryTallyResultRequest{}, &govtypesv1.QueryTallyResultResponse{},

		// gov v1beta1
		&govv1beta.QueryProposalRequest{}, &govv1beta.QueryProposalResponse{},
		&govv1beta.QueryProposalsRequest{}, &govv1beta.QueryProposalsResponse{},
		&govv1beta.QueryVoteRequest{}, &govv1beta.QueryVoteResponse{},
		&govv1beta.QueryVotesRequest{}, &govv1beta.QueryVotesResponse{},
		&govv1beta.QueryParamsRequest{}, &govv1beta.QueryParamsResponse{},
		&govv1beta.QueryDepositRequest{}, &govv1beta.QueryDepositResponse{},
		&govv1beta.QueryDepositsRequest{}, &govv1beta.QueryDepositsResponse{},
		&govv1beta.QueryTallyResultRequest{}, &govv1beta.QueryTallyResultResponse{},

		// ibc
		&interchainaccountstypes.QueryInterchainAccountRequest{}, &interchainaccountstypes.QueryInterchainAccountResponse{},
		&interchainaccountstypes.QueryParamsRequest{}, &interchainaccountstypes.QueryParamsResponse{},
		&icahosttypes.MsgModuleQuerySafeResponse{},

		&ibctransfertypes.QueryParamsRequest{}, &ibctransfertypes.QueryParamsResponse{},
		&ibctransfertypes.QueryDenomsRequest{}, &ibctransfertypes.QueryDenomsResponse{},
		&ibctransfertypes.QueryDenomRequest{}, &ibctransfertypes.QueryDenomResponse{},
		&ibctransfertypes.QueryDenomHashRequest{}, &ibctransfertypes.QueryDenomHashResponse{},
		&ibctransfertypes.QueryEscrowAddressRequest{}, &ibctransfertypes.QueryEscrowAddressResponse{},
		&ibctransfertypes.QueryTotalEscrowForDenomRequest{}, &ibctransfertypes.QueryTotalEscrowForDenomResponse{},

		&ibctransfertypes.MsgTransferResponse{},

		// mint
		&minttypes.QueryParamsRequest{}, &minttypes.QueryParamsResponse{},
		&minttypes.QueryInflationRequest{}, &minttypes.QueryInflationResponse{},
		&minttypes.QueryAnnualProvisionsRequest{}, &minttypes.QueryAnnualProvisionsResponse{},

		// nft
		&nft.QueryBalanceRequest{}, &nft.QueryBalanceResponse{},
		&nft.QueryOwnerRequest{}, &nft.QueryOwnerResponse{},
		&nft.QuerySupplyRequest{}, &nft.QuerySupplyResponse{},
		&nft.QueryNFTsRequest{}, &nft.QueryNFTsResponse{},
		&nft.QueryNFTRequest{}, &nft.QueryNFTResponse{},
		&nft.QueryClassRequest{}, &nft.QueryClassResponse{},
		&nft.QueryClassesRequest{}, &nft.QueryClassesResponse{},

		// protocolpool
		&protocolpooltypes.QueryCommunityPoolRequest{}, &protocolpooltypes.QueryCommunityPoolResponse{},

		// slashing
		&slashingtypes.QuerySigningInfoRequest{}, &slashingtypes.QuerySigningInfoResponse{},
		&slashingtypes.QuerySigningInfosRequest{}, &slashingtypes.QuerySigningInfosResponse{},
		&slashingtypes.QueryParamsRequest{}, &slashingtypes.QueryParamsResponse{},

		// staking
		&stakingtypes.QueryValidatorsRequest{}, &stakingtypes.QueryValidatorsResponse{},
		&stakingtypes.QueryValidatorRequest{}, &stakingtypes.QueryValidatorResponse{},
		&stakingtypes.QueryValidatorDelegationsRequest{}, &stakingtypes.QueryValidatorDelegationsResponse{},
		&stakingtypes.QueryValidatorUnbondingDelegationsRequest{}, &stakingtypes.QueryValidatorUnbondingDelegationsResponse{},
		&stakingtypes.QueryDelegationRequest{}, &stakingtypes.QueryDelegationResponse{},
		&stakingtypes.QueryUnbondingDelegationRequest{}, &stakingtypes.QueryUnbondingDelegationResponse{},
		&stakingtypes.QueryDelegatorDelegationsRequest{}, &stakingtypes.QueryDelegatorDelegationsResponse{},
		&stakingtypes.QueryDelegatorUnbondingDelegationsRequest{}, &stakingtypes.QueryDelegatorUnbondingDelegationsResponse{},
		&stakingtypes.QueryRedelegationsRequest{}, &stakingtypes.QueryRedelegationsResponse{},
		&stakingtypes.QueryDelegatorValidatorsRequest{}, &stakingtypes.QueryDelegatorValidatorsResponse{},
		&stakingtypes.QueryDelegatorValidatorRequest{}, &stakingtypes.QueryDelegatorValidatorResponse{},
		&stakingtypes.QueryPoolRequest{}, &stakingtypes.QueryPoolResponse{},
		&stakingtypes.QueryParamsRequest{}, &stakingtypes.QueryParamsResponse{},

		// upgrade
		&upgradetypes.QueryCurrentPlanRequest{}, &upgradetypes.QueryCurrentPlanResponse{},
		&upgradetypes.QueryAppliedPlanRequest{}, &upgradetypes.QueryAppliedPlanResponse{},
		&upgradetypes.QueryModuleVersionsRequest{}, &upgradetypes.QueryModuleVersionsResponse{},
		&upgradetypes.QueryAuthorityRequest{}, &upgradetypes.QueryAuthorityResponse{},

		// whaleswap (register both Msg responses and Query requests/responses for dyslang)
		&whaleswapv1.QueryAddressMetricsRequest{}, &whaleswapv1.QueryAddressMetricsResponse{},

		&whaleswapv1.QueryOfferRequest{}, &whaleswapv1.QueryOfferResponse{},
		&whaleswapv1.QueryOffersRequest{}, &whaleswapv1.QueryOffersResponse{},
		&whaleswapv1.QueryOffersByOwnerRequest{}, &whaleswapv1.QueryOffersByOwnerResponse{},
		&whaleswapv1.QueryOffersByDenomRequest{}, &whaleswapv1.QueryOffersByDenomResponse{},
		&whaleswapv1.QueryOffersByPairPriceRangeRequest{}, &whaleswapv1.QueryOffersByPairPriceRangeResponse{},
		&whaleswapv1.QueryOffersBestRequest{}, &whaleswapv1.QueryOffersBestResponse{},
		&whaleswapv1.QueryTradesByOfferRequest{}, &whaleswapv1.QueryTradesByOfferResponse{},
		&whaleswapv1.QueryTradesByTakerRequest{}, &whaleswapv1.QueryTradesByTakerResponse{},
		&whaleswapv1.QueryParamsRequest{}, &whaleswapv1.QueryParamsResponse{},
		&whaleswapv1.QueryMetricsRequest{}, &whaleswapv1.QueryMetricsResponse{},

		// Offer queries
		&whaleswapv1.QueryOfferRequest{}, &whaleswapv1.QueryOfferResponse{},
		&whaleswapv1.QueryOffersRequest{}, &whaleswapv1.QueryOffersResponse{},
		&whaleswapv1.QueryOffersByOwnerRequest{}, &whaleswapv1.QueryOffersByOwnerResponse{},
		&whaleswapv1.QueryOffersByDenomRequest{}, &whaleswapv1.QueryOffersByDenomResponse{},
		&whaleswapv1.QueryOffersByPairPriceRangeRequest{}, &whaleswapv1.QueryOffersByPairPriceRangeResponse{},
		&whaleswapv1.QueryOffersBestRequest{}, &whaleswapv1.QueryOffersBestResponse{},

		// Trade queries
		&whaleswapv1.QueryTradeRequest{}, &whaleswapv1.QueryTradeResponse{},
		&whaleswapv1.QueryTradesRequest{}, &whaleswapv1.QueryTradesResponse{},
		&whaleswapv1.QueryTradesByOfferRequest{}, &whaleswapv1.QueryTradesByOfferResponse{},
		&whaleswapv1.QueryTradesByTakerRequest{}, &whaleswapv1.QueryTradesByTakerResponse{},
		&whaleswapv1.QueryTradesByPoolRequest{}, &whaleswapv1.QueryTradesByPoolResponse{},
		&whaleswapv1.QueryTradesByAuctionRequest{}, &whaleswapv1.QueryTradesByAuctionResponse{},

		// Pool queries
		&whaleswapv1.QueryPoolRequest{}, &whaleswapv1.QueryPoolResponse{},
		&whaleswapv1.QueryPoolsRequest{}, &whaleswapv1.QueryPoolsResponse{},
		&whaleswapv1.QueryPoolsByDenomRequest{}, &whaleswapv1.QueryPoolsByDenomResponse{},
		&whaleswapv1.QueryPoolBySharesDenomRequest{}, &whaleswapv1.QueryPoolBySharesDenomResponse{},
		&whaleswapv1.QueryPoolsByPairPriceRangeRequest{}, &whaleswapv1.QueryPoolsByPairPriceRangeResponse{},
		&whaleswapv1.QueryPoolsByOwnerRequest{}, &whaleswapv1.QueryPoolsByOwnerResponse{},
		&whaleswapv1.QueryPoolsByPairRequest{}, &whaleswapv1.QueryPoolsByPairResponse{},

		// Auction queries
		&whaleswapv1.QueryAuctionRequest{}, &whaleswapv1.QueryAuctionResponse{},
		&whaleswapv1.QueryAuctionsRequest{}, &whaleswapv1.QueryAuctionsResponse{},
		&whaleswapv1.QueryAuctionsBySellerRequest{}, &whaleswapv1.QueryAuctionsBySellerResponse{},
		&whaleswapv1.QueryAuctionByNFTRequest{}, &whaleswapv1.QueryAuctionByNFTResponse{},
		&whaleswapv1.QueryAuctionsByPairPriceRangeRequest{}, &whaleswapv1.QueryAuctionsByPairPriceRangeResponse{},

		// Leverage queries
		&whaleswapv1.QueryPositionRequest{}, &whaleswapv1.QueryPositionResponse{},
		&whaleswapv1.QueryPositionsByAddressRequest{}, &whaleswapv1.QueryPositionsByAddressResponse{},
		&whaleswapv1.QueryPositionsByPoolRequest{}, &whaleswapv1.QueryPositionsByPoolResponse{},
		&whaleswapv1.QueryMetricsRequest{}, &whaleswapv1.QueryMetricsResponse{},
	)

	msgservice.RegisterMsgServiceDesc(registrar, &scripttypes.Msg_serviceDesc)
}
