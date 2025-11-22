package keeper

import (
	nameservicev1 "dysonprotocol.com/x/nameservice/types"
)

// Ensure Keeper implements the MsgServer interface
var _ nameservicev1.MsgServer = (*Keeper)(nil)
