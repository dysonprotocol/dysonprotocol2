package keeper

import (
	"context"
	"encoding/base64"
	"strings"

	"cosmossdk.io/collections"
	"dysonprotocol.com/x/storage"
	storagetypes "dysonprotocol.com/x/storage/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/query"
	"github.com/tidwall/gjson"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// incrementLastByte increments the last byte of a string to create an exclusive end key
func incrementLastByte(s string) string {
	if len(s) == 0 {
		return ""
	}
	b := []byte(s)
	for i := len(b) - 1; i >= 0; i-- {
		if b[i] < 0xFF {
			b[i]++
			return string(b)
		}
		b[i] = 0
	}
	// All bytes were 0xFF, return empty string for unbounded end
	return ""
}

// StorageList lists storage entries for an owner under a given index prefix with optional filtering and extraction.
//
// Semantics:
//   - Resolves owner identifier (supports both nameservice names and bech32 addresses).
//   - Lists entries with composite keys starting with resolved_owner/index_prefix.
//   - Applies optional GJSON filter to include only matching entries.
//   - Applies optional GJSON extract to transform returned data.
//   - Supports full pagination with offset/key-based navigation and reverse iteration.
//   - Normalizes index fields in response by removing owner prefix.
//
// Validation:
//   - Owner must be resolvable to a valid account address.
//   - Filter and extract path lengths limited to 100 characters if provided.
//   - Pagination parameters must be valid (no both offset and key specified).
//
// Returns:
//   - *storagetypes.QueryStorageListResponse containing matching entries and pagination metadata.
//
// Errors are returned on unresolvable owner, invalid pagination, malformed filter/extract paths, or internal failures; no panics.
func (k Keeper) StorageList(ctx context.Context, req *storagetypes.QueryStorageListRequest) (*storagetypes.QueryStorageListResponse, error) {
	// Create response structure
	resp := &storagetypes.QueryStorageListResponse{
		Entries:    []*storagetypes.Storage{},
		Pagination: &query.PageResponse{},
	}

	// Resolve owner (accepts nameservice name or address)
	sdkCtx := sdk.UnwrapSDKContext(ctx)
	k.Logger(sdkCtx).Info("StorageList", "req", req)
	resolvedOwner, err := k.namesvcKeeper.ResolveNameOrAddress(ctx, req.Owner)
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "failed to resolve owner: %v", err)
	}

	if len(req.Filter) > 100 {
		return nil, status.Errorf(codes.InvalidArgument, "filter path too long: max 100 characters")
	}
	if len(req.Extract) > 100 {
		return nil, status.Errorf(codes.InvalidArgument, "extract path too long: max 100 characters")
	}

	// Initialize pagination defaults
	if req.Pagination == nil {
		req.Pagination = &query.PageRequest{}
	}
	if req.Pagination.Limit == 0 {
		req.Pagination.Limit = 100
	}

	// Extract pagination parameters
	pagKey := req.Pagination.GetKey()
	offset := req.Pagination.GetOffset()
	limit := req.Pagination.GetLimit()
	reverse := req.Pagination.GetReverse()
	countTotal := req.Pagination.GetCountTotal()

	// Basic debug log
	k.Logger(sdkCtx).Info("StorageList pagination start",
		"pagKeyLen", len(pagKey),
		"pagKeyStr", string(pagKey),
		"offset", offset,
		"limit", limit,
		"reverse", reverse)

	if offset > 0 && len(pagKey) > 0 {
		return nil, status.Errorf(codes.InvalidArgument, "invalid request, either offset or key is expected, got both")
	}

	ownerPrefix := resolvedOwner + "/"
	fullPrefix := ownerPrefix + req.IndexPrefix

	// Build range for iteration - either with pagination key or full prefix
	var ranger collections.Ranger[string]

	// Process pagination key if provided
	if len(pagKey) > 0 {
		k.Logger(sdkCtx).Info("Pagination key processing",
			"module", storage.ModuleName,
			"pagKey", string(pagKey),
			"fullPrefix", fullPrefix,
		)

		// The pagination key is now always raw bytes:
		// - CLI decodes base64 before sending
		// - Script system sends raw bytes (protobuf JSON unmarshaling handles base64 automatically)
		decodedKey := string(pagKey)
		startKey := fullPrefix + decodedKey

		k.Logger(sdkCtx).Info("Pagination DEBUG",
			"module", storage.ModuleName,
			"pagKey", string(pagKey),
			"decodedKey", decodedKey,
			"fullPrefix", fullPrefix,
			"ownerPrefix", ownerPrefix,
			"reverse", reverse,
			"startKey", startKey,
		)

		if reverse {
			// For reverse pagination, we need to iterate from ownerPrefix to the pagination key (inclusive)
			ranger = (&collections.Range[string]{}).StartInclusive(fullPrefix).EndInclusive(startKey).Descending()
			k.Logger(sdkCtx).Info("Reverse range constructed with endKey",
				"module", storage.ModuleName,
				"startInclusive", fullPrefix,
				"endInclusive", startKey,
			)
		} else {
			// For forward pagination, use StartInclusive range with prefix end
			endExclusive := incrementLastByte(fullPrefix)
			ranger = (&collections.Range[string]{}).StartInclusive(startKey).EndExclusive(endExclusive)
			k.Logger(sdkCtx).Info("Forward range constructed with endKey",
				"module", storage.ModuleName,
				"startInclusive", startKey,
				"endExclusive", endExclusive,
			)
		}
	} else {
		// No pagination key - use full prefix range
		if reverse {
			ranger = (&collections.Range[string]{}).Prefix(fullPrefix).Descending()
		} else {
			ranger = (&collections.Range[string]{}).Prefix(fullPrefix)
		}
	}

	iter, err := k.StorageMap.Iterate(ctx, ranger)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}
	defer iter.Close()

	// Define predicate and transform functions
	predicateFunc := func(key string, val storagetypes.Storage) (bool, error) {
		k.Logger(sdkCtx).Info("Filter", "req.Filter", req.Filter)
		if req.Filter == "" {
			k.Logger(sdkCtx).Info("No Filter", "req.Filter", req.Filter)
			return true, nil
		}
		wrappedData := "[" + val.Data + "]"
		result := gjson.Get(wrappedData, "#("+req.Filter+")")
		k.Logger(sdkCtx).Info("Result", "result", result)
		return result.Exists() && len(result.Array()) > 0, nil
	}

	transformFunc := func(key string, val storagetypes.Storage) (*storagetypes.Storage, error) {
		k.Logger(sdkCtx).Info("TransformFunc", "val", val)

		if req.Extract != "" {
			k.Logger(sdkCtx).Info("Extract", "req.Extract", req.Extract)
			res := gjson.Get(val.Data, req.Extract)
			if res.Exists() {
				val.Data = res.Raw
			} else {
				k.Logger(sdkCtx).Info("Extract", "req.Extract", req.Extract)
				val.Data = ""
			}
		}
		// Normalize index in response to exclude owner prefix if present
		if strings.HasPrefix(val.Index, resolvedOwner+"/") {
			val.Index = strings.TrimPrefix(val.Index, resolvedOwner+"/")
		}
		// create a copy to return its address safely
		return &val, nil
	}

	var skipped uint64
	var collected uint64
	var total uint64

	for iter.Valid() {
		key, err := iter.Key()
		if err != nil {
			return nil, status.Error(codes.Internal, err.Error())
		}
		val, err := iter.Value()
		if err != nil {
			return nil, status.Error(codes.Internal, err.Error())
		}

		// Debug logging for iteration
		k.Logger(sdkCtx).Info("Iteration DEBUG",
			"module", storage.ModuleName,
			"key", key,
			"collected", collected,
			"limit", limit,
		)

		include, err := predicateFunc(key, val)
		if err != nil {
			return nil, status.Error(codes.Internal, err.Error())
		}
		if !include {
			iter.Next()
			continue
		}

		total++

		if len(pagKey) == 0 && skipped < offset {
			skipped++
			iter.Next()
			continue
		}

		if collected < limit {
			transformed, err := transformFunc(key, val)
			if err != nil {
				return nil, status.Error(codes.Internal, err.Error())
			}
			resp.Entries = append(resp.Entries, transformed)
			collected++
			iter.Next()
			continue
		}

		if collected >= uint64(limit) {
			// Compute next key once
			if len(resp.Pagination.NextKey) == 0 {
				// The next key should be just the item part (after fullPrefix)
				nextKey := strings.TrimPrefix(key, fullPrefix)
				resp.Pagination.NextKey = []byte(nextKey)
				k.Logger(sdkCtx).Info("Generated next pagination key",
					"module", storage.ModuleName,
					"lastIteratedKey", key,
					"fullPrefix", fullPrefix,
					"nextKey", nextKey,
					"nextKeyBase64WillBe", base64.StdEncoding.EncodeToString([]byte(nextKey)),
				)
			}
			// If no total requested or page key is provided, stop here like SDK
			if !countTotal || len(pagKey) > 0 {
				break
			}
			// Otherwise continue iterating to count remaining matches
			iter.Next()
			continue
		}

		iter.Next()
	}

	// Set total count only if requested and no page key is used (SDK behavior)
	if req.Pagination != nil && req.Pagination.CountTotal && len(pagKey) == 0 {
		resp.Pagination.Total = total
	}

	return resp, nil
}

