package keeper

import (
	scripttypes "dysonprotocol.com/x/script/types"
)

var _ scripttypes.QueryServer = Keeper{}
