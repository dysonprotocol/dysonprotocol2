package keeper

import (
	"context"
	"strings"

	"cosmossdk.io/collections"
	"cosmossdk.io/errors"
	storagetypes "dysonprotocol.com/x/storage/types"
	"github.com/tidwall/gjson"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// StorageGet retrieves a single storage entry by owner and index with optional GJSON extraction.
//
// Semantics:
//   - Resolves owner identifier (supports both nameservice names and bech32 addresses).
//   - Retrieves storage entry using composite key of resolved_owner/index.
//   - Applies optional GJSON path extraction to filter returned data.
//   - Normalizes index in response by removing owner prefix for cleaner API.
//
// Validation:
//   - Owner must be resolvable to a valid account address.
//   - Extract path length limited to 256 characters if provided.
//
// Returns:
//   - *storagetypes.QueryStorageGetResponse containing the storage entry with extracted data if applicable.
//
// Errors are returned on unresolvable owner, non-existent entry, invalid extract path, or internal failures; no panics.
func (k Keeper) StorageGet(ctx context.Context, req *storagetypes.QueryStorageGetRequest) (*storagetypes.QueryStorageGetResponse, error) {
	// Resolve owner which can be a dys name or address
	resolvedOwner, err := k.namesvcKeeper.ResolveNameOrAddress(ctx, req.Owner)
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "failed to resolve owner: %v", err)
	}

	if len(req.Extract) > 256 {
		return nil, status.Errorf(codes.InvalidArgument, "extract path too long: max 256 characters")
	}

	// Create the combined key (normalize incoming index to avoid redundant owner)
	ownerPrefix := resolvedOwner + "/"
	normalizedIndex := strings.TrimPrefix(req.Index, ownerPrefix)
	combinedKey := resolvedOwner + "/" + normalizedIndex
	record, err := k.StorageMap.Get(ctx, combinedKey)
	if err == nil {
		// Apply optional GJSON extract if provided
		if req.Extract != "" {
			res := gjson.Get(record.Data, req.Extract)
			if res.Exists() {
				record.Data = res.Raw
			} else {
				// If extraction path not found, return not found error for clarity
				return nil, status.Errorf(codes.NotFound, "extract path '%s' not found in storage entry", req.Extract)
			}
		}
		// Normalize index to exclude owner prefix if present
		if strings.HasPrefix(record.Index, resolvedOwner+"/") {
			record.Index = strings.TrimPrefix(record.Index, resolvedOwner+"/")
		}
		return &storagetypes.QueryStorageGetResponse{
			Entry: &record, // single struct
		}, nil
	}
	if errors.IsOf(err, collections.ErrNotFound) {
		return nil, status.Errorf(codes.NotFound, "storage entry for (owner=%s,index=%s) doesn't exist", resolvedOwner, req.Index)
	}
	return nil, status.Error(codes.Internal, err.Error())
}

