package keeper

import (
	"dysonprotocol.com/x/nameservice/types"
)

// Ensure Keeper implements QueryServer interface
var _ types.QueryServer = Keeper{}
