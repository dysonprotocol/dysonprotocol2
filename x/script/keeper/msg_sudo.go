package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"dysonprotocol.com/x/script"
	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	govtypes "github.com/cosmos/cosmos-sdk/x/gov/types"
)

// Sudo executes arbitrary messages with authority override and no signer validation.
//
// Semantics:
//   - Validates that the signer has governance authority.
//   - Unpacks and executes all provided messages atomically using cached context.
//   - Messages execute without signer validation (authority override).
//   - If any message fails, all state changes are discarded.
//
// Validation:
//   - Authority must match the configured authority (gov module account).
//   - All messages must be valid and unpackable.
//
// State Updates:
//   - Executes all messages and commits their state changes atomically.
//   - Only commits if all messages succeed.
//
// Returns:
//   - *scripttypes.MsgSudoResponse with results from all executed messages.
//
// Errors are returned on invalid authority, message unpacking failures, or any message execution failure; no panics.
func (k Keeper) Sudo(ctx context.Context, msg *scripttypes.MsgSudo) (*scripttypes.MsgSudoResponse, error) {
	// Validate authority
	if k.authority != msg.Authority {
		return nil, cosmossdkerrors.Wrapf(govtypes.ErrInvalidSigner, "invalid authority; expected %s, got %s", k.authority, msg.Authority)
	}

	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Execute all sudo messages atomically using a single CacheContext.
	// If any message fails, discard all state changes and events.
	cacheCtx, write := sdkCtx.CacheContext()

	// Unpack messages
	msgs, err := script.GetMsgExecMessages(&scripttypes.MsgExec{AttachedMessages: msg.Messages})
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to unpack sudo messages")
	}

	// Execute each message without signer validation against the cached context
	// Collect only non-nil results to avoid packing nil messages into response
	results := make([]sdk.Msg, 0, len(msgs))
	for i, execMsg := range msgs {
		result, err := k.DispatchSudoMessage(cacheCtx, execMsg)
		if err != nil {
			// Do not write cache; abort batch atomically with helpful context
			return nil, cosmossdkerrors.Wrapf(err, "sudo message failed (index=%d type=%s)", i, sdk.MsgTypeURL(execMsg))
		}
		if result != nil {
			results = append(results, result)
		}
	}

	// Pack results
	resp := &scripttypes.MsgSudoResponse{}
	err = script.SetMsgExecResult(&scripttypes.MsgExecResponse{}, results)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to pack sudo results")
	}

	// All succeeded: commit cached state and emit aggregated events to parent
	write()

	// Convert to response format
	anyResults, err := script.GetAnyMessages(results)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to convert results to Any")
	}
	resp.Results = anyResults

	return resp, nil
}
