package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
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
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "request cannot be nil")
	}

	if len(req.Bytes) > 10_000 {
		return nil, status.Error(codes.InvalidArgument, "bytes too long")
	}

	msg, err := sdk.GetMsgFromTypeURL(k.cdc, req.TypeUrl)
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "failed to get message from type url: %s", req.TypeUrl)
	}

	err = k.cdc.Unmarshal(req.Bytes, msg)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to unmarshal protobuf bytes")
	}

	json, err := k.cdc.MarshalInterfaceJSON(msg)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to marshal message to JSON")
	}

	return &scripttypes.QueryDecodeBytesResponse{
		Json: string(json),
	}, nil
}
