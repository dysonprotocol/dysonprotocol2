package keeper

import (
	"fmt"
	"math/bits"
	"net/http"

	scriptv1 "dysonprotocol.com/api/script/types"

	gas "cosmossdk.io/core/gas"
	cosmossdkerrors "cosmossdk.io/errors"
	storetypes "cosmossdk.io/store/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

type ConsumeGasRequest struct {
	Amount int `protobuf:"bytes,1,opt,name=amount,proto3" json:"amount,omitempty"`
}

type ConsumeGasResponse struct {
	GasConsumed  gas.Gas `protobuf:"bytes,1,opt,name=GasConsumed,proto3" json:"GasConsumed,omitempty"`
	GasLimit     gas.Gas `protobuf:"bytes,1,opt,name=GasLimit,proto3" json:"GasLimit,omitempty"`
	GasRemaining gas.Gas `protobuf:"bytes,1,opt,name=GasRemaining,proto3" json:"GasRemaining,omitempty"`
}

// Emit Event from the script
type EmitEventRequest struct {
	Key   string `protobuf:"bytes,1,opt,name=key,proto3" json:"key,omitempty"`
	Value string `protobuf:"bytes,2,opt,name=value,proto3" json:"value,omitempty"`
}

type EmitEventResponse struct {
}

// Using MsgRequest and QueryRequest from keeper.go

func (rpcservice *RpcService) Msg(_ *http.Request, req *MsgRequest, response *string) (err error) {
	defer func() {
		if r := recover(); r != nil {
			err = HandleRunRecovery(r)
		}
	}()

	r, gasused, err := rpcservice.k.HandleJSONAnyMsg(rpcservice.ctx, rpcservice.ScriptAddress, req)

	fmt.Println("Msg", "JsonMsg", req.JsonMsg, "response", r, "err", err, "gasused", gasused)
	if err != nil {
		fmt.Println("RpcService.Msg error", err)

		return err
	}
	*response = r
	return nil
}

// method Query calls the HandleJSONAnyQuery method of the keeper
func (rpcservice *RpcService) Query(_ *http.Request, req *QueryRequest, response *string) (err error) {

	fmt.Println("Query", "jsonReq", req)

	r, err := rpcservice.k.HandleJSONAnyQuery(rpcservice.ctx, req)

	fmt.Println("Query", "response", r, "err", err)

	if err != nil {
		fmt.Println("RpcService.Query error", err)
		return err
	}
	*response = r
	return nil
}

func (rpcservice *RpcService) EmitEvent(_ *http.Request, msg *EmitEventRequest, response *EmitEventResponse) (err error) {
	address := rpcservice.ScriptAddress

	// Get the SDK context and use its event manager directly
	sdkCtx := sdk.UnwrapSDKContext(rpcservice.ctx)
	err = sdkCtx.EventManager().EmitTypedEvent(
		&scriptv1.EventScriptEvent{
			Address: address.String(),
			Key:     msg.Key,
			Value:   msg.Value,
		})
	return
}

func (rpcservice *RpcService) ConsumeGas(_ *http.Request, msg *ConsumeGasRequest, response *ConsumeGasResponse) (err error) {
	sdkCtx := sdk.UnwrapSDKContext(rpcservice.ctx)
	gasMeter := sdkCtx.GasMeter()

	gasLimit := gasMeter.Limit()

	defer func() {
		if r := recover(); r != nil {

			fmt.Printf("Consumegas recovered: %+v\n", r)
			// Check for ErrorOutOfGas type directly, not as error interface
			if _, ok := r.(storetypes.ErrorOutOfGas); ok {
				err = cosmossdkerrors.Wrapf(sdkerrors.ErrOutOfGas,
					"Consumegas script out of gas, gasLimit: %d", gasLimit,
				)
				rpcservice.k.Logger(rpcservice.ctx).Error("Consumegas script out of gas", "gasLimit", gasLimit, "error", r)

			} else {
				// Try to convert to error, but don't assume it implements error interface
				if rerr, ok := r.(error); ok {
					err = rerr
				} else {
					err = fmt.Errorf("panic: %v", r)
				}
			}
		} else {
			currentGasConsumed := gasMeter.GasConsumed()
			if currentGasConsumed > gasLimit {
				err = cosmossdkerrors.Wrapf(sdkerrors.ErrOutOfGas,
					"gasConsumed [%d] > gasLimit [%d] script out of gas, gasLimit: %d: %s",
					currentGasConsumed, gasLimit, gasLimit,
					r,
				)
				rpcservice.k.Logger(rpcservice.ctx).Error("gasConsumed > gasLimit script out of gas", "gasConsumed", currentGasConsumed, "gasLimit", gasLimit, "error", r)
				response = nil
			}
		}

		fmt.Printf("ConsumeGas response: %+v  err: %+v\n", response, err)

	}()

	// Get current depth from context
	depth, ok := sdkCtx.Value(scriptDepthKey{}).(int)
	if !ok {
		depth = 1
	}

	// Validate and compute gasUsed with overflow checks
	if msg.Amount < 0 {
		return cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "amount must be non-negative")
	}
	amountU := uint64(msg.Amount)
	depthU := uint64(depth)
	if hi, _ := bits.Mul64(amountU, depthU); hi != 0 {
		return cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "gasUsed overflow")
	}
	gasUsed := amountU * depthU
	fmt.Printf("gasUsed: %v, currentDepth: %v\n", gasUsed, depth)
	gasMeter.ConsumeGas(gasUsed, "gasUsed")
	//fmt.Printf("gasUsed: %v\n", gasUsed)

	gasConsumed := gasMeter.GasConsumed()
	gasRemaining := gasMeter.GasRemaining()

	*response = ConsumeGasResponse{
		GasConsumed:  gasConsumed,
		GasLimit:     gasLimit,
		GasRemaining: gasRemaining,
	}
	return nil
}

type GasLimitRequest struct {
}

type GasLimitResponse struct {
	GasConsumed  int64 `protobuf:"bytes,1,opt,name=GasConsumed,proto3" json:"GasConsumed,omitempty"`
	GasLimit     int64 `protobuf:"bytes,1,opt,name=GasLimit,proto3" json:"GasLimit,omitempty"`
	GasRemaining int64 `protobuf:"bytes,1,opt,name=GasRemaining,proto3" json:"GasRemaining,omitempty"`
}

func (rpcservice *RpcService) GasLimit(_ *http.Request, msg *GasLimitRequest, response *GasLimitResponse) (err error) {
	sdkCtx := sdk.UnwrapSDKContext(rpcservice.ctx)
	gasMeter := sdkCtx.GasMeter()

	gasConsumed := gasMeter.GasConsumed()
	gasLimit := gasMeter.Limit()
	gasRemaining := gasMeter.GasRemaining()

	*response = GasLimitResponse{
		GasConsumed:  int64(gasConsumed),
		GasLimit:     int64(gasLimit),
		GasRemaining: int64(gasRemaining),
	}
	return nil
}
