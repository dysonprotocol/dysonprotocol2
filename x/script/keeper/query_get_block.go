package keeper

import (
	"context"

	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// GetBlock returns the current block information.
//
// Semantics:
//   - Extracts block metadata from the current SDK context.
//   - Returns block height, time, chain ID, hashes, and proposer.
//   - Provides essential blockchain state information for scripts.
//   - Useful for time-sensitive operations and block-aware logic.
//
// Validation:
//   - Request must not be nil.
//   - Context must contain a valid SDK context (UnwrapSDKContext can panic if not).
//
// Returns:
//   - *scripttypes.QueryGetBlockResponse with complete block information.
//
// Errors are returned on invalid requests. Panics can occur if context doesn't contain SDK context
// or if proposer address is malformed (should not happen in normal operation).
func (k Keeper) GetBlock(ctx context.Context, req *scripttypes.QueryGetBlockRequest) (*scripttypes.QueryGetBlockResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "request cannot be nil")
	}
	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Get block header from context
	header := sdkCtx.BlockHeader()

	// Extract the block hash from the current block's context
	// Note: We don't have access to the current block's hash from the context,
	// only the previous block's hash
	blockHash := header.AppHash

	return &scripttypes.QueryGetBlockResponse{
		BlockHeight:     header.Height,
		BlockTime:       header.Time,
		ChainId:         header.ChainID,
		BlockHash:       blockHash,
		AppHash:         header.AppHash,
		ProposerAddress: sdk.ConsAddress(header.ProposerAddress).String(),
	}, nil
}
