package keeper

import (
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
)

// Interface check: Keeper implements whaleswapv1.QueryServer
// Query handler implementations are in separate files:
//   - query_offer.go: Offer
//   - query_metrics.go: Metrics
//   - query_positions_by_address.go: PositionsByAddress
//   - query_positions_by_pool.go: PositionsByPool
var _ whaleswapv1.QueryServer = Keeper{}
