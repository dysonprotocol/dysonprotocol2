package keeper

import (
	storagetypes "dysonprotocol.com/x/storage/types"
)

// Interface check: Keeper implements storagetypes.QueryServer
// Query handler implementations are in separate files:
//   - query_storage_get.go: StorageGet
//   - query_storage_list.go: StorageList
//   - query_params.go: Params
//   - query_metrics.go: Metrics
var _ storagetypes.QueryServer = Keeper{}
