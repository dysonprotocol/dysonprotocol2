package keeper

import (
	"bytes"
	"fmt"

	cosmossdkerrors "cosmossdk.io/errors"
	scriptErrors "dysonprotocol.com/x/script/errors"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// DispatchMessage dispatches a message for execution and returns the result
func (k Keeper) DispatchMessage(sdkCtx sdk.Context, executor sdk.AccAddress, msg sdk.Msg) (sdk.Msg, error) {
	err := validateMsg(msg)
	if err != nil {
		return nil, err
	}

	// Use the MsgServiceRouter to route and handle the message
	handler := k.MsgRouterService.Handler(msg)
	if handler == nil {
		return nil, fmt.Errorf("no message handler found for %s", sdk.MsgTypeURL(msg))
	}

	// Get the response and convert back to sdk.Msg
	resp, err := handler(sdkCtx, msg)

	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to dispatch message")
	}

	// Get signers using the codec
	signers, _, err := k.cdc.GetMsgV1Signers(msg)
	if err != nil {
		return nil, err
	}

	// Verify signer count
	if len(signers) != 1 {
		return nil, cosmossdkerrors.Wrap(scriptErrors.ErrUnauthorized, "incorrect number of signers")
	}

	// Verify executor
	if !bytes.Equal(signers[0], executor) {
		return nil, cosmossdkerrors.Wrap(scriptErrors.ErrUnauthorized, "the first signer must be the message creator")
	}

	// Extract message from response
	var respMsg sdk.Msg
	if resp != nil && len(resp.MsgResponses) > 0 {
		err = k.cdc.UnpackAny(resp.MsgResponses[0], &respMsg)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to unpack response message")
		}
	}

	// Forward events produced by the message execution into the current context
	// so they are visible to the outer cache context and ultimately to ABCI once committed.
	if resp != nil && len(resp.Events) > 0 {
		for _, event := range resp.Events {
			// Print the event in debug mode and format it verbose for debugging
			sdkCtx.EventManager().EmitEvent(sdk.Event{
				Type:       event.Type,
				Attributes: event.Attributes,
			})
		}
	}

	return respMsg, nil
}

// DispatchSudoMessage dispatches a message without signer validation (for governance use)
func (k Keeper) DispatchSudoMessage(sdkCtx sdk.Context, msg sdk.Msg) (sdk.Msg, error) {
	err := validateMsg(msg)
	if err != nil {
		return nil, err
	}

	// Use the MsgServiceRouter to route and handle the message
	handler := k.MsgRouterService.Handler(msg)
	if handler == nil {
		return nil, fmt.Errorf("no message handler found for %s", sdk.MsgTypeURL(msg))
	}

	// Get the response and convert back to sdk.Msg
	resp, err := handler(sdkCtx, msg)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(err, "failed to dispatch sudo message")
	}

	// Extract message from response
	var respMsg sdk.Msg
	if resp != nil && len(resp.MsgResponses) > 0 {
		err = k.cdc.UnpackAny(resp.MsgResponses[0], &respMsg)
		if err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to unpack response message")
		}
	}

	// Forward events produced by the message execution into the current context
	if resp != nil && len(resp.Events) > 0 {
		for _, event := range resp.Events {
			sdkCtx.EventManager().EmitEvent(sdk.Event{
				Type:       event.Type,
				Attributes: event.Attributes,
			})
		}
	}

	return respMsg, nil
}

func validateMsg(msg sdk.Msg) error {
	m, ok := msg.(sdk.HasValidateBasic)
	if !ok {
		return nil
	}

	if err := m.ValidateBasic(); err != nil {
		return err
	}

	return nil
}
