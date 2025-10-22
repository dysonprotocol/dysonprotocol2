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

// DEPRECATED: This function is no longer needed since MsgExec now implements UnpackInterfacesMessage
// UnpackExecInterfaces implements UnpackInterfacesMessage.UnpackInterfaces
func UnpackExecInterfaces(msg *types.MsgExec, unpacker gogoprotoany.AnyUnpacker) error {
	for _, x := range msg.AttachedMessages {
		var m sdk.Msg
		err := unpacker.UnpackAny(x, &m)
		if err != nil {
			return err
		}
	}

	return nil
}

// GetMsgExecMessages unpacks the Any's into sdk.Msg's
func GetMsgExecMessages(msg *types.MsgExec) ([]sdk.Msg, error) {
	return tx.GetMsgs(msg.AttachedMessages, "Exec")
}

// SetMsgExecMessages packs msgs into Any's in the MsgExec.AttachedMessages field
func SetMsgExecMessages(msg *types.MsgExec, msgs []sdk.Msg) error {
	anys, err := tx.SetMsgs(msgs)
	if err != nil {
		return err
	}
	msg.AttachedMessages = anys
	return nil
}

// SetMsgExecResult sets the attached message results for MsgExecResponse
func SetMsgExecResult(resp *types.MsgExecResponse, msgs []sdk.Msg) error {
	anys, err := tx.SetMsgs(msgs)
	if err != nil {
		return err
	}
	resp.AttachedMessageResults = anys
	return nil
}

// GetAnyMessages converts sdk.Msg slice to Any slice
func GetAnyMessages(msgs []sdk.Msg) ([]*gogoprotoany.Any, error) {
	return tx.SetMsgs(msgs)
}
