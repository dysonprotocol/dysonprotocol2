package module

import (
	autocliv1 "cosmossdk.io/api/cosmos/autocli/v1"
	nameservicev1 "dysonprotocol.com/api/nameservice/types"
)

// AutoCLIOptions implements the autocli.HasAutoCLIConfig interface.
func (am AppModule) AutoCLIOptions() *autocliv1.ModuleOptions {
	return &autocliv1.ModuleOptions{
		Query: &autocliv1.ServiceCommandDescriptor{
			Service:              nameservicev1.Query_ServiceDesc.ServiceName,
			EnhanceCustomCommand: true,
			RpcCommandOptions: []*autocliv1.RpcCommandOptions{
				{
					RpcMethod: "DenomByName",
					Use:       "denoms-by-name",
					Short:     "List denoms by root name, optional subdenom prefix",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"name": {
							Name:         "name",
							Usage:        "The root name (e.g. example.dys)",
							DefaultValue: "",
						},
						"subdenom_prefix": {
							Name:         "subdenom-prefix",
							Usage:        "Optional subdenom path prefix (e.g. /foo)",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "NFTClassesByName",
					Use:       "nftclasses-by-name",
					Short:     "List NFT class IDs by root name, optional subclass prefix",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"name": {
							Name:         "name",
							Usage:        "The root name (e.g. example.dys)",
							DefaultValue: "",
						},
						"subclass_prefix": {
							Name:         "subclass-prefix",
							Usage:        "Optional subclass path prefix (e.g. /foo)",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "ComputeHash",
					Use:       "compute-hash",
					Short:     "Compute the hash for a name, salt, and committer address",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"name": {
							Name:         "name",
							Usage:        "Name to compute the hash for",
							DefaultValue: "",
						},
						"salt": {
							Name:         "salt",
							Usage:        "Salt to use for the hash computation",
							DefaultValue: "",
						},
						"committer": {
							Name:         "committer",
							Usage:        "Committer address",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "ResolveName",
					Use:       "resolve [name-or-address]",
					Short:     "Resolve a name to address or return the address if already valid",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{
						{ProtoField: "name_or_address"},
					},
				},
				{
					RpcMethod: "Params",
					Use:       "params",
					Short:     "Query the current nameservice parameters",
				},
			},
		},
		Tx: &autocliv1.ServiceCommandDescriptor{
			Service:              nameservicev1.Msg_ServiceDesc.ServiceName,
			EnhanceCustomCommand: true,
			RpcCommandOptions: []*autocliv1.RpcCommandOptions{
				{
					RpcMethod: "DeleteClass",
					Use:       "delete-class --class-id=<class-id>",
					Short:     "Delete an NFT class (only if empty)",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SetNFTClassBidTimeout",
					Use:       "set-nft-class-bid-timeout --class-id=<class-id> --bid-timeout=<duration>",
					Short:     "Set the per-class bid timeout duration",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID",
							DefaultValue: "",
						},
						"bid_timeout": {
							Name:         "bid-timeout",
							Usage:        "Duration like 2s, 24h, 7d",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SetNFTClassAllowedDenoms",
					Use:       "set-nft-class-allowed-denoms --class-id=<class-id> --allowed-denoms=<denom1,denom2>",
					Short:     "Set the per-class allowed denoms list",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID",
							DefaultValue: "",
						},
						"allowed_denoms": {
							Name:         "allowed-denoms",
							Usage:        "Comma-separated list of allowed denoms",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SetNFTClassRejectBidValuationFeePercent",
					Use:       "set-nft-class-reject-fee --class-id=<class-id> --reject-fee=<dec>",
					Short:     "Set the per-class reject bid fee percent",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID",
							DefaultValue: "",
						},
						"reject_bid_valuation_fee_percent": {
							Name:         "reject-fee",
							Usage:        "Decimal in [0,1]",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SetNFTClassMinimumBidPercentIncrease",
					Use:       "set-nft-class-min-bid-increase --class-id=<class-id> --min-bid-increase=<dec>",
					Short:     "Set the per-class minimum bid percent increase",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID",
							DefaultValue: "",
						},
						"minimum_bid_percent_increase": {
							Name:         "min-bid-increase",
							Usage:        "Decimal >= 0",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "Commit",
					Use:       "commit",
					Short:     "Commit to registering a name",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"hexhash": {
							Name:         "commitment",
							Usage:        "The hex hash of the name commitment",
							DefaultValue: "",
						},
						"valuation": {
							Name:         "valuation",
							Usage:        "The valuation for the name (format: 100dys)",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "Reveal",
					Use:       "reveal",
					Short:     "Reveal a name to complete registration",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"name": {
							Name:         "name",
							Usage:        "The name to reveal",
							DefaultValue: "",
						},
						"salt": {
							Name:         "salt",
							Usage:        "The salt used in the commitment",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SetDestination",
					Use:       "set-destination",
					Short:     "Set the destination address for a name",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"name": {
							Name:         "name",
							Usage:        "The name to set the destination for",
							DefaultValue: "",
						},
						"destination": {
							Name:         "destination",
							Usage:        "The destination address",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SetValuation",
					Use:       "set-valuation",
					Short:     "Set the valuation for an NFT",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"nft_class_id": {
							Name:         "class-id",
							Usage:        "The class ID of the NFT",
							DefaultValue: "",
						},
						"nft_id": {
							Name:         "nft-id",
							Usage:        "The ID of the NFT",
							DefaultValue: "",
						},
						"valuation": {
							Name:         "valuation",
							Usage:        "The new valuation (format: 100udys)",
							DefaultValue: "",
						},
						"max_valuation_fee_pct": {
							Name:         "max-valuation-fee-pct",
							Usage:        "Optional cap on valuation fee percent (decimal, e.g. 0.025)",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "PlaceBid",
					Use:       "place-bid --nft-class-id=<class-id> --nft-id=<nft-id> --bid-amount=<amount>",
					Short:     "Place a bid on an NFT",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"nft_class_id": {
							Name:         "nft-class-id",
							Usage:        "The class ID of the NFT",
							DefaultValue: "",
						},
						"nft_id": {
							Name:         "nft-id",
							Usage:        "The ID of the NFT",
							DefaultValue: "",
						},
						"bid_amount": {
							Name:         "bid-amount",
							Usage:        "The amount to bid (format: 100udys)",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "ClaimBid",
					Use:       "claim-bid --nft-class-id=<class-id> --nft-id=<nft-id>",
					Short:     "Claim an NFT after bid timeout has elapsed",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"nft_class_id": {
							Name:         "nft-class-id",
							Usage:        "The class ID of the NFT",
							DefaultValue: "",
						},
						"nft_id": {
							Name:         "nft-id",
							Usage:        "The ID of the NFT",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "AcceptBid",
					Use:       "accept-bid --nft-class-id=<class-id> --nft-id=<nft-id>",
					Short:     "Accept a bid on an NFT",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"nft_class_id": {
							Name:         "nft-class-id",
							Usage:        "The class ID of the NFT",
							DefaultValue: "",
						},
						"nft_id": {
							Name:         "nft-id",
							Usage:        "The ID of the NFT",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "RejectBid",
					Use:       "reject-bid --nft-class-id=<class-id> --nft-id=<nft-id>",
					Short:     "Reject a bid on an NFT",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"nft_class_id": {
							Name:         "nft-class-id",
							Usage:        "The class ID of the NFT",
							DefaultValue: "",
						},
						"nft_id": {
							Name:         "nft-id",
							Usage:        "The ID of the NFT",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SaveClass",
					Use:       "save-class --class-id=<class-id> --name=<name> --symbol=<symbol> --description=<description> --uri=<uri>",
					Short:     "Create or update an NFT class",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID to create",
							DefaultValue: "",
						},
						"name": {
							Name:         "name",
							Usage:        "The name of the class",
							DefaultValue: "",
						},
						"symbol": {
							Name:         "symbol",
							Usage:        "The symbol of the class",
							DefaultValue: "",
						},
						"description": {
							Name:         "description",
							Usage:        "The description of the class",
							DefaultValue: "",
						},
						"uri": {
							Name:         "uri",
							Usage:        "The URI for the class",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "MintNFT",
					Use:       "mint-nft --class-id=<class-id> --nft-id=<nft-id> --uri=<uri>",
					Short:     "Mint a new NFT",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID of the NFT",
							DefaultValue: "",
						},
						"nft_id": {
							Name:         "nft-id",
							Usage:        "The ID of the NFT to mint",
							DefaultValue: "",
						},
						"uri": {
							Name:         "uri",
							Usage:        "The URI for the NFT",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "MoveNft",
					Use:       "move-nft",
					Short:     "Force move an NFT between two accounts (requires signer to own the NFT class)",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The NFT class ID",
							DefaultValue: "",
						},
						"nft_id": {
							Name:         "nft-id",
							Usage:        "The NFT ID",
							DefaultValue: "",
						},
						"to_address": {
							Name:         "to-address",
							Usage:        "Destination address (Bech32)",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SetNFTMetadata",
					Use:       "set-nft-metadata --class-id=<class-id> --nft-id=<nft-id> --metadata=<metadata>",
					Short:     "Set metadata for an NFT",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID of the NFT",
							DefaultValue: "",
						},
						"nft_id": {
							Name:         "nft-id",
							Usage:        "The ID of the NFT",
							DefaultValue: "",
						},
						"metadata": {
							Name:         "metadata",
							Usage:        "The metadata JSON string",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SetNFTClassExtraData",
					Use:       "set-nft-class-extra-data --class-id=<class-id> --extra-data=<extra-data>",
					Short:     "Set extra data for an NFT class",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID",
							DefaultValue: "",
						},
						"extra_data": {
							Name:         "extra-data",
							Usage:        "The extra data JSON string",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SetNFTClassAlwaysListed",
					Use:       "set-nft-class-always-listed --class-id=<class-id> --always-listed=<always-listed>",
					Short:     "Set the always_listed flag for an NFT class",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID",
							DefaultValue: "",
						},
						"always_listed": {
							Name:         "always-listed",
							Usage:        "Whether NFTs in this class should always be listed for sale",
							DefaultValue: "false",
						},
					},
				},
				{
					RpcMethod: "SetNFTClassValuationFeePct",
					Use:       "set-nft-class-valuation-fee-pct --class-id=<class-id> --valuation-fee-pct=<dec>",
					Short:     "Set the per-class valuation fee percent",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID",
							DefaultValue: "",
						},
						"valuation_fee_pct": {
							Name:         "valuation-fee-pct",
							Usage:        "Decimal in [0,1]",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SetNFTClassValuationPeriod",
					Use:       "set-nft-class-valuation-period --class-id=<class-id> --valuation-period=<duration>",
					Short:     "Set the per-class valuation fee period",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID",
							DefaultValue: "",
						},
						"valuation_period": {
							Name:         "valuation-period",
							Usage:        "Duration like 1h, 24h, 365d",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SetNFTClassBidTimeout",
					Use:       "set-nft-class-bid-timeout --class-id=<class-id> --bid-timeout=<duration>",
					Short:     "Set the per-class bid timeout duration",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID",
							DefaultValue: "",
						},
						"bid_timeout": {
							Name:         "bid-timeout",
							Usage:        "Duration like 2s, 24h, 7d",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SetNFTClassAllowedDenoms",
					Use:       "set-nft-class-allowed-denoms --class-id=<class-id> --allowed-denoms=<denom1,denom2>",
					Short:     "Set the per-class allowed denoms list",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID",
							DefaultValue: "",
						},
						"allowed_denoms": {
							Name:         "allowed-denoms",
							Usage:        "Comma-separated list of allowed denoms",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SetNFTClassRejectBidValuationFeePercent",
					Use:       "set-nft-class-reject-fee --class-id=<class-id> --reject-fee=<dec>",
					Short:     "Set the per-class reject bid fee percent",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID",
							DefaultValue: "",
						},
						"reject_bid_valuation_fee_percent": {
							Name:         "reject-fee",
							Usage:        "Decimal in [0,1]",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SetNFTClassMinimumBidPercentIncrease",
					Use:       "set-nft-class-min-bid-increase --class-id=<class-id> --min-bid-increase=<dec>",
					Short:     "Set the per-class minimum bid percent increase",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"class_id": {
							Name:         "class-id",
							Usage:        "The class ID",
							DefaultValue: "",
						},
						"minimum_bid_percent_increase": {
							Name:         "min-bid-increase",
							Usage:        "Decimal >= 0",
							DefaultValue: "",
						},
					},
				},
				{
					RpcMethod: "SetListed",
					Use:       "set-listed --nft-class-id=<class-id> --nft-id=<nft-id> --listed=<listed>",
					Short:     "Set the listed status for a specific NFT",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"nft_class_id": {
							Name:         "nft-class-id",
							Usage:        "The class ID of the NFT",
							DefaultValue: "",
						},
						"nft_id": {
							Name:         "nft-id",
							Usage:        "The ID of the NFT",
							DefaultValue: "",
						},
						"listed": {
							Name:         "listed",
							Usage:        "Whether the NFT should be listed for sale (true/false)",
							DefaultValue: "false",
						},
					},
				},
				{
					RpcMethod: "Renew",
					Use:       "renew --nft-class-id=<class-id> --nft-id=<nft-id>",
					Short:     "Renew an NFT name registration",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"nft_class_id": {
							Name:         "nft-class-id",
							Usage:        "The class ID of the NFT to renew",
							DefaultValue: "",
						},
						"nft_id": {
							Name:         "nft-id",
							Usage:        "The ID of the NFT to renew",
							DefaultValue: "",
						},
					},
				},
			},
		},
	}
}
