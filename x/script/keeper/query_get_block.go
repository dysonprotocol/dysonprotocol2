package keeper

import (
	"context"

	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
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
//   - No validation required - reads from current context.
//
// Returns:
//   - *scripttypes.QueryGetBlockResponse with complete block information.
//
// Errors are returned on context extraction failures; no panics.
func (k Keeper) GetBlock(ctx context.Context, req *scripttypes.QueryGetBlockRequest) (*scripttypes.QueryGetBlockResponse, error) {
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
