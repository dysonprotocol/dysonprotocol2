package keeper

import (
	"fmt"
	"runtime/debug"

	cosmossdkerrors "cosmossdk.io/errors"
	storetypes "cosmossdk.io/store/types"
	scripttypes "dysonprotocol.com/x/script/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
)

var _ scripttypes.MsgServer = Keeper{}

// HandleRunRecovery is an exported version of handleRunRecovery for testing
func HandleRunRecovery(r interface{}) error {
	return handleRunRecovery(r)
}

func handleRunRecovery(r interface{}) error {
	fmt.Printf("Handle recovery: %+v\n", r)
	stack := string(debug.Stack())
	fmt.Printf("Stack: %s\n", stack)
	switch rec := r.(type) {
	case nil:
		// No panic, just return nil or handle gracefully
		return nil
	case storetypes.ErrorOutOfGas:
		return cosmossdkerrors.Wrapf(sdkerrors.ErrOutOfGas,
			"script ran out of gas (descriptor: %s)", rec.Descriptor,
		)
	case error:
		// Additional checks for other error types
		// if cosmossdkerrors.Is(rec, sdkerrors.ErrXYZ) { ... }
		return sdkerrors.ErrPanic.Wrapf("script panic (error type): %v", rec.Error())
	default:
		// Panic with something that wasn't an error
		return sdkerrors.ErrPanic.Wrapf("script panic (non-error type): %v", rec)
	}
}
