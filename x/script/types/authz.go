package types

import (
	"context"

	cdctypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	"github.com/cosmos/cosmos-sdk/types/tx"
	"github.com/cosmos/cosmos-sdk/x/authz"
)

var _ authz.Authorization = &ScriptExecAuthorization{}

// NewScriptExecAuthorization creates a new ScriptExecAuthorization object.
func NewScriptExecAuthorization(scriptAddress string, functionNames []string) *ScriptExecAuthorization {
	return &ScriptExecAuthorization{
		ScriptAddress: scriptAddress,
		FunctionNames: functionNames,
	}
}

// MsgTypeURL implements Authorization.MsgTypeURL.
func (a ScriptExecAuthorization) MsgTypeURL() string {
	return sdk.MsgTypeURL(&MsgExec{})
}

// ValidateBasic implements Authorization.ValidateBasic.
func (a ScriptExecAuthorization) ValidateBasic() error {
	if a.ScriptAddress == "" {
		return sdkerrors.ErrInvalidAddress.Wrap("script address cannot be empty")
	}

	// Validate script address format
	_, err := sdk.AccAddressFromBech32(a.ScriptAddress)
	if err != nil {
		return sdkerrors.ErrInvalidAddress.Wrapf("invalid script address: %s", err)
	}

	// Check for duplicate function names
	seen := make(map[string]bool)
	for _, fn := range a.FunctionNames {
		if fn == "" {
			return sdkerrors.ErrInvalidRequest.Wrap("function name cannot be empty")
		}
		if seen[fn] {
			return sdkerrors.ErrInvalidRequest.Wrapf("duplicate function name: %s", fn)
		}
		seen[fn] = true
	}

	seenMsgTypes := make(map[string]bool)
	for i, anyAuth := range a.AttachedMsgAuthorizations {
		if anyAuth == nil {
			return sdkerrors.ErrInvalidType.Wrapf("attached message authorization at index %d is nil", i)
		}
		cached := anyAuth.GetCachedValue()
		auth, ok := cached.(authz.Authorization)
		if !ok {
			return sdkerrors.ErrInvalidType.Wrapf("expected %T, got %T", (authz.Authorization)(nil), cached)
		}
		if err := auth.ValidateBasic(); err != nil {
			return err
		}
		msgType := auth.MsgTypeURL()
		if msgType == "" {
			return sdkerrors.ErrInvalidRequest.Wrap("attached message authorization has empty msg type url")
		}
		if seenMsgTypes[msgType] {
			return sdkerrors.ErrInvalidRequest.Wrapf("duplicate attached message authorization for %s", msgType)
		}
		seenMsgTypes[msgType] = true
	}

	return nil
}

// Accept implements Authorization.Accept.
func (a ScriptExecAuthorization) Accept(ctx context.Context, msg sdk.Msg) (authz.AcceptResponse, error) {
	execMsg, ok := msg.(*MsgExec)
	if !ok {
		return authz.AcceptResponse{}, sdkerrors.ErrInvalidType.Wrap("type mismatch: expected MsgExec")
	}

	// Check if the script address matches
	if execMsg.ScriptAddress != a.ScriptAddress {
		return authz.AcceptResponse{}, sdkerrors.ErrUnauthorized.Wrapf("script address mismatch: expected %s, got %s", a.ScriptAddress, execMsg.ScriptAddress)
	}

	// Extra code execution is not allowed via authz
	if execMsg.ExtraCode != "" {
		return authz.AcceptResponse{}, sdkerrors.ErrUnauthorized.Wrap("extra_code is not allowed for authorized executions")
	}

	functionAllowed := execMsg.FunctionName == ""
	if !functionAllowed {
		// If a function name is specified, check if it's in the allowed list
		// Empty FunctionNames list means only direct execution is allowed
		if len(a.FunctionNames) == 0 {
			return authz.AcceptResponse{}, sdkerrors.ErrUnauthorized.Wrap("function calls not authorized, only direct script execution allowed")
		}

		for _, allowedFn := range a.FunctionNames {
			if allowedFn == execMsg.FunctionName {
				functionAllowed = true
				break
			}
		}

		if !functionAllowed {
			return authz.AcceptResponse{}, sdkerrors.ErrUnauthorized.Wrapf("function %s is not authorized for execution", execMsg.FunctionName)
		}
	}

	updatedAttachedAuthz, updatedAny, err := a.checkAttachedMessages(ctx, execMsg)
	if err != nil {
		return authz.AcceptResponse{}, err
	}
	if updatedAny {
		updated := ScriptExecAuthorization{
			ScriptAddress:             a.ScriptAddress,
			FunctionNames:             a.FunctionNames,
			AttachedMsgAuthorizations: updatedAttachedAuthz,
		}
		return authz.AcceptResponse{Accept: true, Updated: &updated}, nil
	}

	return authz.AcceptResponse{Accept: true}, nil
}

func (a ScriptExecAuthorization) checkAttachedMessages(ctx context.Context, execMsg *MsgExec) ([]*cdctypes.Any, bool, error) {
	if len(execMsg.AttachedMessages) == 0 {
		return nil, false, nil
	}

	if len(a.AttachedMsgAuthorizations) == 0 {
		return nil, false, sdkerrors.ErrUnauthorized.Wrap("attached_messages are not authorized for executions")
	}

	// NOTE: signer validation is enforced during message dispatch using
	// k.cdc.GetMsgV1Signers in the keeper; Accept only enforces authz semantics.
	msgs, err := tx.GetMsgs(execMsg.AttachedMessages, "Exec")
	if err != nil {
		return nil, false, err
	}

	updatedAuthz := make([]*cdctypes.Any, len(a.AttachedMsgAuthorizations))
	copy(updatedAuthz, a.AttachedMsgAuthorizations)
	updatedAny := false

	for _, attachedMsg := range msgs {

		msgType := sdk.MsgTypeURL(attachedMsg)
		index, embeddedAuth, err := findAttachedAuthorization(updatedAuthz, msgType)
		if err != nil {
			return nil, false, err
		}
		if embeddedAuth == nil {
			return nil, false, sdkerrors.ErrUnauthorized.Wrapf("attached message %s is not authorized", msgType)
		}

		resp, err := embeddedAuth.Accept(ctx, attachedMsg)
		if err != nil {
			return nil, false, err
		}
		if !resp.Accept {
			return nil, false, sdkerrors.ErrUnauthorized.Wrapf("attached message %s not authorized", msgType)
		}

		if resp.Delete {
			updatedAuthz = append(updatedAuthz[:index], updatedAuthz[index+1:]...)
			updatedAny = true
			continue
		}
		if resp.Updated != nil {
			updatedAny = true
			updatedAnyAuth, err := cdctypes.NewAnyWithValue(resp.Updated)
			if err != nil {
				return nil, false, err
			}
			updatedAuthz[index] = updatedAnyAuth
		}
	}

	return updatedAuthz, updatedAny, nil
}

func findAttachedAuthorization(authorizations []*cdctypes.Any, msgType string) (int, authz.Authorization, error) {
	for i, anyAuth := range authorizations {
		if anyAuth == nil {
			return -1, nil, sdkerrors.ErrInvalidType.Wrapf("attached message authorization at index %d is nil", i)
		}
		cached := anyAuth.GetCachedValue()
		auth, ok := cached.(authz.Authorization)
		if !ok {
			return -1, nil, sdkerrors.ErrInvalidType.Wrapf("expected %T, got %T", (authz.Authorization)(nil), cached)
		}
		if auth.MsgTypeURL() == msgType {
			return i, auth, nil
		}
	}
	return -1, nil, nil
}
