package module

import (
	autocliv1 "cosmossdk.io/api/cosmos/autocli/v1"
	whaleswapapiv1 "dysonprotocol.com/api/whaleswap/types"
)

// AutoCLIOptions implements the autocli.HasAutoCLIConfig interface for whaleswap.
func (am AppModule) AutoCLIOptions() *autocliv1.ModuleOptions {
	return &autocliv1.ModuleOptions{
		Query: &autocliv1.ServiceCommandDescriptor{
			Service:              whaleswapapiv1.Query_ServiceDesc.ServiceName,
			EnhanceCustomCommand: true,
			RpcCommandOptions: []*autocliv1.RpcCommandOptions{
				{
					RpcMethod: "Params",
					Use:       "params",
					Short:     "Query the whaleswap module parameters",
					Long:      "Return all current module parameters including pfand_per_offer and auction knobs.",
					Example:   "dysond query whaleswap params",
				},
				{
					RpcMethod: "Pool",
					Use:       "pool <pool-id>",
					Short:     "Get a pool by ID",
					Long:      "Fetch a single AMM pool by its numeric ID.",
					Example:   "dysond query whaleswap pool 1",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{{
						ProtoField: "pool_id",
					}},
				},
				{
					RpcMethod: "Pools",
					Use:       "pools",
					Short:     "List pools with pagination",
					Long:      "List AMM pools. Use pagination flags to page through results.",
					Example:   "dysond query whaleswap pools --limit 50",
				},
				{
					RpcMethod: "Offer",
					Use:       "offer <offer-id>",
					Short:     "Get an offer by ID",
					Long:      "Fetch a single orderbook offer by its numeric ID.",
					Example:   "dysond query whaleswap offer 42",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{{
						ProtoField: "offer_id",
					}},
				},
				{
					RpcMethod: "OffersByOwner",
					Use:       "offers-by-owner <owner>",
					Short:     "List offers by owner with optional status",
					Long:      "List all offers created by an owner address. Optionally filter by status (open/closed/cancelled).",
					Example:   "dysond query whaleswap offers-by-owner $(dysond keys show alice -a) --status=open",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{{
						ProtoField: "owner",
					}},
				},
				{
					RpcMethod: "Offers",
					Use:       "offers",
					Short:     "List offers with optional have/want filters",
					Long:      "List orderbook offers. Optionally filter by have_denom and/or want_denom. Use pagination flags for paging.",
					Example:   "dysond query whaleswap offers --have-denom=udys --want-denom=ufoo --limit 100",
				},
				{
					RpcMethod: "Trade",
					Use:       "trade <trade-id>",
					Short:     "Get a trade by ID",
					Long:      "Fetch a single trade by its numeric ID.",
					Example:   "dysond query whaleswap trade 1",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{{
						ProtoField: "trade_id",
					}},
				},
				{
					RpcMethod: "TradesByOffer",
					Use:       "trades-by-offer <offer-id>",
					Short:     "List trades for an offer",
					Long:      "List all trades executed against a specific offer.",
					Example:   "dysond query whaleswap trades-by-offer 42",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{{
						ProtoField: "offer_id",
					}},
				},
				{
					RpcMethod: "TradesByTaker",
					Use:       "trades-by-taker <taker>",
					Short:     "List trades by taker",
					Long:      "List all trades executed by the given taker address.",
					Example:   "dysond query whaleswap trades-by-taker $(dysond keys show bob -a)",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{{
						ProtoField: "taker",
					}},
				},
				{
					RpcMethod: "TradesByPool",
					Use:       "trades-by-pool <pool-id>",
					Short:     "List trades by pool id",
					Long:      "List all trades executed against the specified pool.",
					Example:   "dysond query whaleswap trades-by-pool 1",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{{
						ProtoField: "pool_id",
					}},
				},
				{
					RpcMethod: "Auction",
					Use:       "auction <auction-id>",
					Short:     "Get an auction by ID",
					Long:      "Fetch a single auction by its numeric ID.",
					Example:   "dysond query whaleswap auction 7",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{{
						ProtoField: "auction_id",
					}},
				},
				{
					RpcMethod: "Auctions",
					Use:       "auctions",
					Short:     "List auctions with optional sell/bid filters",
					Long:      "List auctions. Optionally filter by sell_denom and/or bid_denom. Use pagination flags for paging.",
					Example:   "dysond query whaleswap auctions --sell-denom=udys --bid-denom=ufoo",
				},
			},
		},
		Tx: &autocliv1.ServiceCommandDescriptor{
			Service:              whaleswapapiv1.Msg_ServiceDesc.ServiceName,
			EnhanceCustomCommand: true,
			RpcCommandOptions: []*autocliv1.RpcCommandOptions{
				{
					RpcMethod: "CreatePool",
					Use:       "create-pool --coins <coin> --coins <coin> [--fee-pct=<dec>] [--min-price <coin>] [--min-price <coin>] [--max-price <coin>] [--max-price <coin>]",
					Short:     "Create a new AMM pool",
					Long: "Create a new AMM pool. If no price band is set, the pool behaves as constant product (v2). If a band is set, concentrated liquidity (v3) math is used.\n\n" +
						"Initial reserves are provided via repeated --coins flags (exactly two), one coin per flag. Order doesn't matter; the module canonicalizes by denom.\n" +
						"Price band flags (--min-price/--max-price) each represent a ratio coin_b/coin_a at the band edge and must be provided as TWO separate flags, one coin per flag (no commas, no space-separated pairs).\n" +
						"Example with reserves udys/ufoo: --min-price 1udys --min-price 2ufoo encodes Pmin = 2 ufoo per 1 udys.\n" +
						"Similarly: --max-price 1udys --max-price 3ufoo encodes Pmax = 3 ufoo per 1 udys.\n" +
						"Note: zero-width bands are rejected (max must be strictly greater than min).",
					Example: "dysond tx whaleswap create-pool --coins 1000udys --coins 500ufoo --fee-pct=0.003\n" +
						"dysond tx whaleswap create-pool --coins 1000udys --coins 500ufoo --min-price 1udys --min-price 2ufoo --max-price 1udys --max-price 3ufoo",
				},
				{
					RpcMethod: "UpdatePoolConfig",
					Use:       "update-pool-config --pool-id=<id> [--fee-pct=<dec>] [--min-price <coin>] [--min-price <coin>] [--max-price <coin>] [--max-price <coin>]",
					Short:     "Update pool fee or price band",
					Long: "Update an existing pool's fee percent and/or price band. Only the majority owner (>50% shares) may update.\n\n" +
						"When setting bands, repeat the flag and provide one coin per flag to encode coin_b/coin_a at the edge. Example: --min-price 1udys --min-price 2ufoo.",
					Example: "dysond tx whaleswap update-pool-config --pool-id=1 --fee-pct=0.0025 --min-price 1udys --min-price 2ufoo --max-price 1udys --max-price 3ufoo",
				},
				{
					RpcMethod: "AddLiquidity",
					Use:       "add-liquidity --pool-id=<id> --amount1=<amountdenom> --amount2=<amountdenom>",
					Short:     "Add liquidity to a pool (owner-only)",
					Long: "Provide both coins to add liquidity to the pool.\n\n" +
						"v2 (no band): the pool refunds excess to preserve the current R2/R1 ratio; shares minted are min(pro_rata_by_coin1, pro_rata_by_coin2).\n" +
						"v3 (band set): liquidity math uses sqrt-price band [Pmin,Pmax]; only the side that contributes to ΔL is consumed, the other is refunded.",
					Example: "dysond tx whaleswap add-liquidity --pool-id=1 --amount1=1000udys --amount2=600ufoo",
				},
				{
					RpcMethod: "RemoveLiquidity",
					Use:       "remove-liquidity --pool-id=<id> --shares=<amount>",
					Short:     "Remove liquidity and burn shares",
					Long: "Burn the specified number of shares and receive the underlying coins proportionally (v2) or using band-aware math (v3).\n\n" +
						"Partial exits must keep both reserves positive; a full exit (burning all shares) pays out all reserves and deletes the pool.",
					Example: "dysond tx whaleswap remove-liquidity --pool-id=1 --shares=100",
				},
				{
					RpcMethod: "MakeTrade",
					Use:       "make-trade --max-input <coin> [--max-input <coin> ...] --op '<json>' [--op '<json>' ...] [--min-output <coin> ...]",
					Short:     "Execute mixed operations (pool swaps + order takes) with single settlement",
					Long: "Mix pool swap legs and orderbook takes in one transaction. Caps in --max-input are enforced only at the end; final trader minimums via --min-output.\n" +
						"Each --op is JSON: either {\"swap\":{...SwapLeg...}} or {\"take\":{...TakeItem...}}. Swap leg supports swap_in (exact-in), swap_out (exact-out), or both.",
					Example: "dysond tx whaleswap make-trade --max-input 200udys --op '{\"swap\":{\"pool_id\":1,\"swap_in\":{\"denom\":\"udys\",\"amount\":\"100\"}}}' --op '{\"take\":{\"offer_id\":42,\"take_units\":\"10\"}}' --min-output 1ufoo",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"max_input":  {Name: "max-input", Usage: "Per-denom debit cap (repeatable), e.g. 100udys"},
						"operations": {Name: "op", Usage: "Repeated JSON operation: {\"swap\":{...}} or {\"take\":{...}}"},
						"min_output": {Name: "min-output", Usage: "Final minimum credits (repeatable)"},
					},
				},
				{
					RpcMethod: "PoolSwap",
					Use:       "swap --max-input <coin> [--max-input <coin> ...] --legs '<json>' [--min-output <coin> ...]",
					Short:     "Aggregate multi-leg swaps across pools with end-of-tx settlement",
					Long: "Execute an aggregated swap defined by arbitrary legs. No pre-escrow occurs; caps in --max-input are enforced only at the end. " +
						"Legs may reuse pools, form cycles, and are simulated on pool snapshots; fees accrue per pool. Final minimums are checked via --min-output coins.\n\n" +
						"--legs accepts either a JSON array or multiple flags. Each leg may specify swap_in (exact-in), swap_out (exact-out), or both (rate constraint).\n" +
						"Example leg: '{\"pool_id\":1,\"swap_in\":{\"denom\":\"udys\",\"amount\":\"100\"}}' or '{\"pool_id\":1,\"swap_out\":{\"denom\":\"ufoo\",\"amount\":\"90\"}}'.",
					Example: "dysond tx whaleswap swap --max-input 100udys --legs '[{\"pool_id\":1,\"swap_in\":{\"denom\":\"udys\",\"amount\":\"100\"}}]' --min-output 90ufoo\n" +
						"dysond tx whaleswap swap --max-input 100udys --max-input 50ufoo --legs '[{\"pool_id\":1,\"swap_in\":{\"denom\":\"udys\",\"amount\":\"100\"}},{\"pool_id\":2,\"swap_out\":{\"denom\":\"ubar\",\"amount\":\"120\"}}]'",
					FlagOptions: map[string]*autocliv1.FlagOptions{
						"max_input":  {Name: "max-input", Usage: "Per-denom debit cap (repeatable), e.g. 100udys"},
						"legs":       {Name: "legs", Usage: "JSON array or repeated flag of legs allowing swap_in and/or swap_out"},
						"min_output": {Name: "min-output", Usage: "Final minimum credits (repeatable), e.g. 90ufoo"},
					},
				},
				{
					RpcMethod: "ConvertToLiquid",
					Use:       "convert-to-liquid --denom=<denom> --amount=<amount>",
					Short:     "Wrap a solid denom into its liquid wrapper",
					Long:      "Convert solid denom S into liquid L(S). Nameservice mint fee is skipped for module account minting.",
					Example:   "dysond tx whaleswap convert-to-liquid --denom=udys --amount=1000",
				},
				{
					RpcMethod: "ConvertToSolid",
					Use:       "convert-to-solid --liquid-denom=<liquid-denom> --amount=<amount>",
					Short:     "Unwrap a liquid denom back to solid",
					Long:      "Convert liquid L(S) back to solid S. Burns the liquid and releases the backed solid coin.",
					Example:   "dysond tx whaleswap convert-to-solid --liquid-denom=whaleswap.dys/coins/udys --amount=1000",
				},
				{
					RpcMethod: "MakeOffer",
					Use:       "make-offer --have=<amountdenom> --want=<amountdenom>",
					Short:     "Create an orderbook offer (normal or liquid mode)",
					Long:      "Create an offer. Normal mode escrows the base 'have' in the module. Liquid mode uses liquid have and locks pfand from params.",
					Example: "Normal: dysond tx whaleswap make-offer --have=100udys --want=50ufoo\n" +
						"Liquid: dysond tx whaleswap make-offer --have=100whaleswap.dys/coins/udys --want=50ufoo",
				},
				{
					RpcMethod: "TakeOffer",
					Use:       "take-offer --trades='[{\"offer_id\":1,\"take_units\":\"10\"}]'",
					Short:     "Take one or more offers (batch)",
					Long:      "Execute one or more takes in a single transaction. If the maker-have is liquid, it must be burned by the maker.",
					Example:   "dysond tx whaleswap take-offer --trades='[{\"offer_id\":1,\"take_units\":\"10\"}]'",
				},
				{
					RpcMethod: "CancelOffer",
					Use:       "cancel-offer --offer-id=<id>",
					Short:     "Cancel an offer",
					Long:      "Cancel an offer. The maker can always cancel. A third-party can cancel liquid offers if maker lacks 1 unit of liquid have (pfand rules).",
					Example:   "dysond tx whaleswap cancel-offer --offer-id=42",
				},
				{
					RpcMethod: "OpenAuction",
					Use:       "open-auction --seller=<addr> --bid-denom=<denom> --sell=<amountdenom>",
					Short:     "Open an auction by escrowing a solid coin",
					Long:      "Escrow a solid 'sell' coin and mint an auction NFT in class whaleswap.dys/auction/{bid_denom}. Only bids in bid_denom are allowed.",
					Example:   "dysond tx whaleswap open-auction --seller=$(dysond keys show alice -a) --bid-denom=ufoo --sell=100udys",
				},
				{
					RpcMethod: "RedeemAuction",
					Use:       "redeem-auction --auction-id=<id>",
					Short:     "Redeem auction escrow if no bidder",
					Long:      "Redeem an open auction only if there is no current bidder. Burns the NFT and releases the escrowed sell coin to the caller.",
					Example:   "dysond tx whaleswap redeem-auction --auction-id=7",
				},
				{
					RpcMethod: "UpdateParams",
					Use:       "update-params",
					Short:     "Update whaleswap module params (authority only)",
					Long:      "Update module parameters. Only the gov authority may execute this.",
					Example:   "dysond tx whaleswap update-params --from gov --pfand-per-offer=1udys",
				},
			},
		},
	}
}
