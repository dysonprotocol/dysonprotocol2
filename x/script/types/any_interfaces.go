package types

import (
	sdk "github.com/cosmos/cosmos-sdk/types"
	authz "github.com/cosmos/cosmos-sdk/x/authz"
	gogoprotoany "github.com/cosmos/gogoproto/types/any"
)

// Ensure our types implement the UnpackInterfacesMessage interface
var (
	_ gogoprotoany.UnpackInterfacesMessage = (*MsgExec)(nil)
	_ gogoprotoany.UnpackInterfacesMessage = (*MsgExecResponse)(nil)
	_ gogoprotoany.UnpackInterfacesMessage = (*MsgSudo)(nil)
	_ gogoprotoany.UnpackInterfacesMessage = (*MsgSudoResponse)(nil)
	_ gogoprotoany.UnpackInterfacesMessage = (*RunScript)(nil)
	_ gogoprotoany.UnpackInterfacesMessage = (*ResponseRunScript)(nil)
	_ gogoprotoany.UnpackInterfacesMessage = (*ScriptExecAuthorization)(nil)
)

// UnpackInterfaces implements the UnpackInterfacesMessage.UnpackInterfaces method
func (msg *MsgExec) UnpackInterfaces(unpacker gogoprotoany.AnyUnpacker) error {
	for _, x := range msg.AttachedMessages {
		var m sdk.Msg
		err := unpacker.UnpackAny(x, &m)
		if err != nil {
			return err
		}
	}
	return nil
}

// UnpackInterfaces implements the UnpackInterfacesMessage.UnpackInterfaces method
func (msg *MsgExecResponse) UnpackInterfaces(unpacker gogoprotoany.AnyUnpacker) error {
	for _, x := range msg.AttachedMessageResults {
		var m sdk.Msg
		err := unpacker.UnpackAny(x, &m)
		if err != nil {
			return err
		}
	}
	return nil
}

// UnpackInterfaces implements the UnpackInterfacesMessage.UnpackInterfaces method
func (msg *MsgSudo) UnpackInterfaces(unpacker gogoprotoany.AnyUnpacker) error {
	for _, x := range msg.Messages {
		var m sdk.Msg
		err := unpacker.UnpackAny(x, &m)
		if err != nil {
			return err
		}
	}
	return nil
}

// UnpackInterfaces implements the UnpackInterfacesMessage.UnpackInterfaces method
func (msg *MsgSudoResponse) UnpackInterfaces(unpacker gogoprotoany.AnyUnpacker) error {
	for _, x := range msg.Results {
		var m sdk.Msg
		err := unpacker.UnpackAny(x, &m)
		if err != nil {
			return err
		}
	}
	return nil
}

func (msg *RunScript) UnpackInterfaces(unpacker gogoprotoany.AnyUnpacker) error {
	for _, x := range msg.AttachedMessages {
		var m sdk.Msg
		err := unpacker.UnpackAny(x, &m)
		if err != nil {
			return err
		}
	}
	return nil
}

func (msg *ResponseRunScript) UnpackInterfaces(unpacker gogoprotoany.AnyUnpacker) error {
	for _, x := range msg.AttachedMessageResults {
		var m sdk.Msg
		err := unpacker.UnpackAny(x, &m)
		if err != nil {
			return err
		}
	}
	return nil
}

func (msg *ScriptExecAuthorization) UnpackInterfaces(unpacker gogoprotoany.AnyUnpacker) error {
	for _, x := range msg.AttachedMsgAuthorizations {
		var a authz.Authorization
		err := unpacker.UnpackAny(x, &a)
		if err != nil {
			return err
		}
	}
	return nil
}
