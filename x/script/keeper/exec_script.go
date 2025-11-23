package keeper

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"cosmossdk.io/core/header"
	cosmossdkerrors "cosmossdk.io/errors"
	"dysonprotocol.com/dysvm"
	"dysonprotocol.com/x/script"
	scriptErrors "dysonprotocol.com/x/script/errors"
	scripttypes "dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

type ExecScriptContext struct {
	Msg                    *scripttypes.MsgExec
	Script                 *scripttypes.Script
	AttachedMessageResults []sdk.Msg
}

type ExecScriptResponse struct {
	Result string
}

type scriptDepthKey struct{}

func (k Keeper) execScript(sdkCtx sdk.Context, scriptCtx *ExecScriptContext) (*ExecScriptResponse, error) {

	// Get current depth from context
	depth, ok := sdkCtx.Value(scriptDepthKey{}).(int)
	if !ok {
		depth = 1
	} else {
		depth++
	}

	k.Logger(sdkCtx).Info("current depth", "depth", depth)

	// Create new context with updated depth
	depthCtx := sdkCtx.WithValue(scriptDepthKey{}, depth)

	executorAddr, err := k.addressCodec.StringToBytes(scriptCtx.Msg.ExecutorAddress)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "error getting executor address")
	}

	attachedMsgs, err := script.GetMsgExecMessages(scriptCtx.Msg)

	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "error getting attached messages")
	}

	// assert that the executor address == script address if extra code is provided
	if scriptCtx.Msg.ExtraCode != "" {
		if scriptCtx.Msg.ExecutorAddress != scriptCtx.Script.Address {
			return nil, cosmossdkerrors.Wrapf(scriptErrors.ErrInvalid, "executor address must be the same as the script address if extra code is provided")
		}
	}

	if len(scriptCtx.AttachedMessageResults) > 0 {
		// If the pre-populated AttachedMessageResults are provided, use them
		if len(scriptCtx.AttachedMessageResults) != len(attachedMsgs) {
			return nil, cosmossdkerrors.Wrapf(scriptErrors.ErrInvalid, "pre-populated AttachedMessageResults length (%d) does not match attachedMsgs length (%d)", len(scriptCtx.AttachedMessageResults), len(attachedMsgs))
		}
		k.Logger(depthCtx).Info("Skipping message dispatch, using pre-populated AttachedMessageResults")
	} else {
		// Dispatch messages attached to the script
		results := make([]sdk.Msg, len(attachedMsgs))
		for i, attachedMsg := range attachedMsgs {
			r, err := k.DispatchMessage(depthCtx, executorAddr, attachedMsg)
			if err != nil {
				return nil, cosmossdkerrors.Wrapf(err, "error dispatching attached message index [%d]", i)
			}
			results[i] = r
		}
		scriptCtx.AttachedMessageResults = results
	}

	port, srv, err := k.NewRPCServer(depthCtx, scriptCtx.Script.Address, k.App)

	if err != nil {
		return nil, err
	}

	now := time.Now()
	defer func() {
		k.Logger(depthCtx).Info(fmt.Sprintf("Elapsed time %s", time.Since(now)))

		if err := srv.Shutdown(context.Background()); err != nil {
			fmt.Printf("shutdown error")
			panic(err) // failure/timeout shutting down the server gracefully
		}
		k.Logger(depthCtx).Info("server stopped")
	}()

	msgJSON, err := k.cdc.MarshalInterfaceJSON(scriptCtx.Msg)
	if err != nil {
		return nil, err
	}
	scriptJSON, err := k.cdc.MarshalInterfaceJSON(scriptCtx.Script)
	if err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to marshal script")
	}

	attachedMsgResultsJSON := "["
	for i, m := range scriptCtx.AttachedMessageResults {
		msgJSON, err := k.cdc.MarshalInterfaceJSON(m)
		if err != nil {
			return nil, err
		}
		attachedMsgResultsJSON += string(msgJSON)
		if i < len(scriptCtx.AttachedMessageResults)-1 {
			attachedMsgResultsJSON += ","
		}
	}
	attachedMsgResultsJSON += "]"

	headerInfo := header.Info{
		Height:  depthCtx.BlockHeight(),
		Time:    depthCtx.BlockTime(),
		ChainID: depthCtx.ChainID(),
		AppHash: depthCtx.BlockHeader().AppHash,
		Hash:    depthCtx.BlockHeader().LastBlockId.Hash,
	}
	fmt.Printf("headerInfo: %+v\n", headerInfo)
	headerInfoJSON, err := json.Marshal(headerInfo)
	if err != nil {
		k.Logger(depthCtx).Error("failed to marshal headerInfo", "error", err)
		return nil, err
	}

	out, runErr := dysvm.Exec(
		sdk.WrapSDKContext(depthCtx),
		string(msgJSON),
		string(scriptJSON),
		attachedMsgResultsJSON,
		string(headerInfoJSON),
		port)
	if runErr != nil {
		k.Logger(depthCtx).Error("failed to exec", "error", runErr)
	}

	temp := strings.Split(string(out), "\n")
	response := string(temp[len(temp)-1])
	if response == "exit status 1" {
		response = string(temp[len(temp)-2])
	}

	fmt.Printf("Output: %s\n", out)
	fmt.Printf("Response: %s\n", response)
	fmt.Printf("Error: %v\n", runErr)

	if runErr != nil {
		// if the response is json, we can wrap the error in a json error
		if strings.HasPrefix(response, "{") {
			return nil, cosmossdkerrors.Wrap(scriptErrors.ErrScriptExecution, response)
		}
		return nil, runErr
	}

	return &ExecScriptResponse{Result: response}, nil
}
