package script

import (
	"dysonprotocol.com/x/script/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/tx"
	gogoprotoany "github.com/cosmos/gogoproto/types/any"
)

var (
	_ sdk.Msg = &types.MsgUpdateScript{}
	_ sdk.Msg = &types.MsgExec{}
	_ sdk.Msg = &types.MsgSudo{}
)

// GetMsgExecMessages unpacks the Any's into sdk.Msg's
func GetMsgExecMessages(msg *types.MsgExec) ([]sdk.Msg, error) {
	return tx.GetMsgs(msg.AttachedMessages, "Exec")
}

// SetMsgExecMessages packs msgs into Any's in the MsgExec.AttachedMessages field
func SetMsgExecMessages(msg *types.MsgExec, msgs []sdk.Msg) error {
	anys, err := GetAnyMessages(msgs)
	if err != nil {
		// UNREACHABLE: attached messages are validated sdk.Msg values; packing
		// should only fail for non-proto or nil messages.
		return err
	}
	msg.AttachedMessages = anys
	return nil
}

// SetMsgExecResult sets the attached message results for MsgExecResponse
func SetMsgExecResult(resp *types.MsgExecResponse, msgs []sdk.Msg) error {
	anys, err := GetAnyMessages(msgs)
	if err != nil {
		// UNREACHABLE: attached message results are produced by Msg handlers and
		// must be concrete sdk.Msg types; tx.SetMsgs should never fail here.
		return err
	}
	resp.AttachedMessageResults = anys
	return nil
}

// GetAnyMessages converts sdk.Msg slice to Any slice
func GetAnyMessages(msgs []sdk.Msg) ([]*gogoprotoany.Any, error) {
	return tx.SetMsgs(msgs)
}
