package keeper

import (
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
)

// Note: ComposeOperations removed from proto; the interface now excludes it.
var _ whaleswapv1.MsgServer = Keeper{}

// Methods are implemented in per-message files to keep scope localized.

// CreatePool: see msg_create_pool.go
// UpdatePoolConfig: see msg_update_pool_config.go

// AddLiquidity: see msg_liquidity.go

// RemoveLiquidity: see msg_liquidity.go

// PoolSwap: see msg_pool_swap.go

// MakeOffer: see msg_orderbook.go

// TakeOffer: see msg_orderbook.go

// CancelOffer: see msg_orderbook.go

// OpenAuction: see msg_auction.go

// RedeemAuction: see msg_auction.go

// ComposeOperations removed from proto; no method required.

// UpdateParams: see msg_update_params.go

// Leverage Message Handlers

// OpenLongPosition: see msg_leverage_open.go
// OpenShortPosition: see msg_leverage_open.go
// ClosePosition: see msg_leverage_handlers.go
// AddCollateral: see leverage_collateral.go
// InitializeLiquidation: see msg_leverage_handlers.go
// FinalizeLiquidation: see msg_leverage_handlers.go
