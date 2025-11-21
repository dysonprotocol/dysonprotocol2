package keeper

import (
	storagetypes "dysonprotocol.com/x/storage/types"
)

// Interface check: Keeper implements storagetypes.MsgServer
// Message handler implementations are in separate files:
//   - msg_storage_set.go: StorageSet
//   - msg_storage_delete.go: StorageDelete
//   - msg_update_params.go: UpdateParams
var _ storagetypes.MsgServer = Keeper{}
