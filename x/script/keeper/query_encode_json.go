package keeper

import (
	"context"
	"fmt"

	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// EncodeJson encodes a JSON string to protobuf bytes for message construction.
//
// Semantics:
//   - Parses the provided JSON string into a Cosmos SDK message.
//   - Marshals the parsed message to protobuf bytes.
//   - Enforces size limits to prevent abuse.
//
// Validation:
//   - JSON string must be valid and parseable into a known message type.
//   - JSON length must not exceed 10,000 characters.
//
// Returns:
//   - *scripttypes.QueryEncodeJsonResponse with the protobuf-encoded bytes.
//
// Errors are returned on invalid JSON, unknown message types, or size limit violations; no panics.
func (k Keeper) EncodeJson(ctx context.Context, req *scripttypes.QueryEncodeJsonRequest) (*scripttypes.QueryEncodeJsonResponse, error) {

	// too long return err
	if len(req.Json) > 10_000 {
		return nil, fmt.Errorf("json too long")
	}

	var msg sdk.Msg

	err := k.cdc.UnmarshalInterfaceJSON([]byte(req.Json), &msg)
	if err != nil {
		return nil, err
	}

	bz, err := k.cdc.Marshal(msg)
	if err != nil {
		return nil, err
	}

	return &scripttypes.QueryEncodeJsonResponse{
		Bytes: bz,
	}, nil
}
