package dysonprotocol

import (
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// LoggingPostDecorator logs transaction messages and their execution results.
type LoggingPostDecorator struct{}

// NewLoggingPostDecorator creates a new LoggingPostDecorator.
func NewLoggingPostDecorator() LoggingPostDecorator {
	return LoggingPostDecorator{}
}

// PostHandle logs the transaction messages and whether execution succeeded.
func (d LoggingPostDecorator) PostHandle(ctx sdk.Context, tx sdk.Tx, simulate, success bool, next sdk.PostHandler) (sdk.Context, error) {
	logger := ctx.Logger().With("module", "post-handler")

	msgs := tx.GetMsgs()
	for i, msg := range msgs {
		msgType := sdk.MsgTypeURL(msg)
		logger.Info("tx message",
			"index", i,
			"type", msgType,
			"success", success,
			"simulate", simulate,
		)
	}

	if success {
		logger.Info("tx execution succeeded", "msg_count", len(msgs))
	} else {
		logger.Info("tx execution failed", "msg_count", len(msgs))
	}

	return next(ctx, tx, simulate, success)
}
