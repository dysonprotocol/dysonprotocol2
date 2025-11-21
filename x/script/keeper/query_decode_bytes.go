package keeper

import (
	"context"
	"fmt"

	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// DecodeBytes decodes protobuf bytes to JSON string for message inspection.
//
// Semantics:
//   - Creates a message instance from the provided type URL.
//   - Unmarshals the protobuf bytes into the message.
//   - Marshals the message back to JSON for human-readable inspection.
//   - Enforces size limits to prevent abuse.
//
// Validation:
//   - Type URL must be a known message type.
//   - Bytes must be valid protobuf encoding for the specified type.
//   - Bytes length must not exceed 10,000 bytes.
//
// Returns:
//   - *scripttypes.QueryDecodeBytesResponse with the JSON representation.
//
// Errors are returned on unknown types, invalid protobuf, or size limit violations; no panics.
func (k Keeper) DecodeBytes(ctx context.Context, req *scripttypes.QueryDecodeBytesRequest) (*scripttypes.QueryDecodeBytesResponse, error) {

	if len(req.Bytes) > 10_000 {
		return nil, fmt.Errorf("bytes too long")
	}

	msg, err := sdk.GetMsgFromTypeURL(k.cdc, req.TypeUrl)
	if err != nil {
		return nil, fmt.Errorf("failed to get message from type url: %s", req.TypeUrl)
	}

	err = k.cdc.Unmarshal(req.Bytes, msg)
	if err != nil {
		return nil, err
	}

	json, err := k.cdc.MarshalInterfaceJSON(msg)
	if err != nil {
		return nil, err
	}

	return &scripttypes.QueryDecodeBytesResponse{
		Json: string(json),
	}, nil
}
