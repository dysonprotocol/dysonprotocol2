package keeper

import (
	"context"
	"encoding/base64"
	"strings"

	"cosmossdk.io/collections"
	"cosmossdk.io/errors"
	"dysonprotocol.com/x/storage"
	storagetypes "dysonprotocol.com/x/storage/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/query"
	"github.com/tidwall/gjson"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// Ensure Keeper implements the gRPC interface
var _ storagetypes.QueryServer = Keeper{}

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
//   - Extract path length limited to 100 characters if provided.
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

	if len(req.Extract) > 100 {
		return nil, status.Errorf(codes.InvalidArgument, "extract path too long: max 100 characters")
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

// Params returns the current x/storage module parameters.
//
// Semantics:
//   - Retrieves current parameter values from module state.
//   - Returns default parameters if none have been set (fresh chain state).
//
// Returns:
//   - *storagetypes.QueryParamsResponse containing current MaxStorageSize and StorageStakeMultiple values.
//
// Errors are returned on invalid request or state retrieval failures; no panics.
func (k Keeper) Params(ctx context.Context, req *storagetypes.QueryParamsRequest) (*storagetypes.QueryParamsResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	params := k.GetParams(ctx)
	return &storagetypes.QueryParamsResponse{Params: params}, nil
}

// Metrics returns storage usage metrics and stake requirements for a given owner.
//
// Semantics:
//   - Resolves owner identifier (supports both nameservice names and bech32 addresses).
//   - Retrieves total bytes stored by the owner across all entries.
//   - Calculates minimum stake amount required based on StorageStakeMultiple parameter.
//   - Returns current stake amount from staking module for comparison.
//   - Returns zero metrics if owner has no storage entries.
//
// Validation:
//   - Owner must be resolvable to a valid account address.
//
// Returns:
//   - *storagetypes.QueryMetricsResponse containing total bytes, minimum stake requirement, and current stake.
//
// Errors are returned on unresolvable owner or internal failures; no panics.
func (k Keeper) Metrics(ctx context.Context, req *storagetypes.QueryMetricsRequest) (*storagetypes.QueryMetricsResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "invalid request")
	}

	// Resolve owner (accepts nameservice name or address)
	resolvedOwner, err := k.namesvcKeeper.ResolveNameOrAddress(ctx, req.Owner)
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "failed to resolve owner: %v", err)
	}

	// Get storage metrics for the owner
	metrics, err := k.GetStorageMetrics(ctx, resolvedOwner)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get storage metrics: %v", err)
	}

	// Get current stake amount from staking module
	currentStake, err := k.GetTotalDelegatedStake(ctx, resolvedOwner)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get current stake amount: %v", err)
	}

	return &storagetypes.QueryMetricsResponse{
		Owner:              metrics.Owner,
		TotalBytes:         metrics.TotalBytes,
		MinStakeAmount:     metrics.MinStakeAmount,
		CurrentStakeAmount: currentStake.String(),
	}, nil
}
