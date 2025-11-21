package keeper

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"

	cosmossdkerrors "cosmossdk.io/errors"
	sdk "github.com/cosmos/cosmos-sdk/types"

	abci "github.com/cometbft/cometbft/abci/types"
)

var rpcRe = regexp.MustCompile(`^(\/.+\.Query)([^/]+)Request$`)

// MsgRequest defines a request to execute a message
type MsgRequest struct {
	JsonMsg  string `json:"json_msg"`
	GasLimit uint64 `json:"gas_limit"`
}

// QueryRequest defines a request to execute a query
type QueryRequest struct {
	JsonQuery string `protobuf:"bytes,2,opt,name=Jsonquery,proto3" json:"json_query,omitempty"`
	GasLimit  uint64 `json:"gas_limit"`
}

func ConvertRPCPath(in string) string {
	if m := rpcRe.FindStringSubmatch(in); m != nil {
		return m[1] + "/" + m[2]
	}
	if in == "/dysonprotocol.script.v1.RunScript" {
		return "/dysonprotocol.script.v1.Query/Run"
	}
	return in
}

func GetResponseTypeURL(reqTypeURL string) string {
	// replace Request with Response
	return strings.Replace(reqTypeURL, "Request", "Response", 1)

}

func (k Keeper) HandleJSONAnyQuery(ctx context.Context, req *QueryRequest) (string, error) {
	// Parse the type URL from the JSON
	var anyMsg map[string]interface{}
	err := json.Unmarshal([]byte(req.JsonQuery), &anyMsg)
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to parse JSON: %s", req.JsonQuery)
	}

	typeURL, ok := anyMsg["@type"].(string)
	if !ok {
		return "", fmt.Errorf("JSON doesn't contain @type field: %s", req.JsonQuery)
	}

	respMsg, err := k.cdc.InterfaceRegistry().Resolve(GetResponseTypeURL(typeURL))
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to resolve response type: %s", typeURL)
	}

	// First try to unmarshal into a specific interface
	var msg sdk.Msg
	err = k.cdc.UnmarshalInterfaceJSON([]byte(req.JsonQuery), &msg)
	if err != nil {
		// If that fails, try a generic approach using the registry
		return "", cosmossdkerrors.Wrapf(err, "failed to unmarshal request")
	}

	// Convert to binary protobuf
	binaryData, err := k.cdc.Marshal(msg)
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to marshal to protobuf")
	}

	// Unwrap the SDK context
	parentCtx := sdk.UnwrapSDKContext(ctx)
	sdkCtx := parentCtx

	// Historical queries are not supported; always use current block context

	path := ConvertRPCPath(typeURL)

	handler := k.QueryRouterService.Route(path)
	if handler == nil {
		return "", fmt.Errorf("no handler found for query message: %s", typeURL)
	}

	abciReqQuery := abci.RequestQuery{
		Data: binaryData,
	}

	remaining := parentCtx.GasMeter().Limit() - parentCtx.GasMeter().GasConsumed()
	childLimit := req.GasLimit
	if childLimit == 0 || childLimit > remaining {
		childLimit = remaining
	}

	branch := &BranchService{sdkCtx: sdkCtx}
	var respQuery *abci.ResponseQuery
	gasUsed, _, execErr := branch.ExecuteWithGasLimit(ctx, childLimit, func(childCtx context.Context) error {
		qctx := sdk.UnwrapSDKContext(childCtx)
		var derr error
		respQuery, derr = handler(qctx, &abciReqQuery)
		return derr
	})

	// Always charge parent
	parentCtx.GasMeter().ConsumeGas(gasUsed, "nested _query gas")
	if execErr != nil {
		return "", cosmossdkerrors.Wrapf(execErr, "failed to execute query; message %v", req.JsonQuery)
	}

	// unmarshal the respQuery.Value into the respMsg
	err = k.cdc.Unmarshal(respQuery.Value, respMsg)
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to unmarshal response")
	}

	// marshal the respMsg into a json string
	respJSON, err := k.cdc.MarshalInterfaceJSON(respMsg)
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to marshal response")
	}

	return string(respJSON), nil
}

func (k Keeper) HandleJSONAnyMsg(ctx context.Context, scriptAddress sdk.AccAddress, req *MsgRequest) (respJSONStr string, gasused uint64, err error) {
	var msg sdk.Msg
	err = k.cdc.UnmarshalInterfaceJSON([]byte(req.JsonMsg), &msg)
	if err != nil {
		err = cosmossdkerrors.Wrapf(err, "failed to UnmarshalInterfaceJSON request: %s", req.JsonMsg)
		return
	}

	sdkCtx := sdk.UnwrapSDKContext(ctx)

	// Determine child gas limit (default to parent's remaining)
	remaining := sdkCtx.GasMeter().Limit() - sdkCtx.GasMeter().GasConsumed()
	childLimit := req.GasLimit
	if childLimit == 0 || childLimit > remaining {
		childLimit = remaining
	}

	branch := &BranchService{sdkCtx: sdkCtx}

	gasUsed, write, execErr := branch.ExecuteWithGasLimit(ctx, childLimit, func(childCtx context.Context) error {
		childSdk := sdk.UnwrapSDKContext(childCtx)
		var derr error
		respJSONStr, derr = k.dispatchJSONMsg(childSdk, scriptAddress, req.JsonMsg)
		return derr
	})

	// Always charge parent meter for child usage
	sdkCtx.GasMeter().ConsumeGas(gasUsed, "nested _msg gas")
	gasused = gasUsed

	// Commit state only if successful
	if execErr == nil {
		write()
	}

	return respJSONStr, gasused, execErr
}

func (k Keeper) dispatchJSONMsg(ctx sdk.Context, scriptAddress sdk.AccAddress, jsonMsg string) (string, error) {
	var msg sdk.Msg
	err := k.cdc.UnmarshalInterfaceJSON([]byte(jsonMsg), &msg)
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to UnmarshalInterfaceJSON message")
	}

	resp, err := k.DispatchMessage(ctx, scriptAddress, msg)
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to DispatchMessage")
	}

	bz, err := k.cdc.MarshalInterfaceJSON(resp)
	if err != nil {
		return "", cosmossdkerrors.Wrapf(err, "failed to MarshalInterfaceJSON response")
	}

	return string(bz), nil
}
