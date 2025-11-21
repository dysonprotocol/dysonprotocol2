package keeper

import (
	"context"

	"cosmossdk.io/collections"
	cosmossdkerrors "cosmossdk.io/errors"
	scripttypes "dysonprotocol.com/x/script/types"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// ScriptInfo queries script information by address or nameservice name.
//
// Semantics:
//   - Resolves the provided address/name using nameservice if needed.
//   - Retrieves script data including code, version, and update metadata.
//   - Returns NotFound error if script doesn't exist.
//
// Validation:
//   - Address/name parameter must be non-empty.
//   - Resolved address must be a valid bech32 address.
//
// Returns:
//   - *scripttypes.QueryScriptInfoResponse with complete script information.
//   - NotFound error if script doesn't exist at resolved address.
//
// Errors are returned on empty parameters, resolution failures, or storage errors; no panics.
func (k Keeper) ScriptInfo(ctx context.Context, req *scripttypes.QueryScriptInfoRequest) (*scripttypes.QueryScriptInfoResponse, error) {
	if req.Address == "" {
		return nil, status.Error(codes.InvalidArgument, "empty script address")
	}

	resolvedAddress, err := k.NameserviceKeeper.ResolveNameOrAddress(ctx, req.Address)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to resolve address or name: %s", req.Address)
	}

	script, err := k.ScriptMap.Get(ctx, resolvedAddress)
	if err == nil {
		return &scripttypes.QueryScriptInfoResponse{
			Script: &scripttypes.Script{
				Address:      script.Address,
				Version:      script.Version,
				Code:         script.Code,
				UpdateHeight: script.UpdateHeight,
			},
		}, nil
	}
	if cosmossdkerrors.IsOf(err, collections.ErrNotFound) {
		return nil, status.Errorf(codes.NotFound, "script with address %s doesn't exist", resolvedAddress)
	}
	return nil, status.Error(codes.Internal, err.Error())
}
