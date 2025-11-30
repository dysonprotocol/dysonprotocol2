package dysonprotocol

import (
	"github.com/cosmos/cosmos-sdk/baseapp"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// Ensure LoggingMsgInterceptor implements baseapp.MsgHandlerInterceptor.
var _ baseapp.MsgHandlerInterceptor = (*LoggingMsgInterceptor)(nil)

// LoggingMsgInterceptor logs message execution with request and response details.
type LoggingMsgInterceptor struct{}

// NewLoggingMsgInterceptor creates a new logging interceptor.
func NewLoggingMsgInterceptor() *LoggingMsgInterceptor {
	return &LoggingMsgInterceptor{}
}

// Pre logs the message before execution.
func (l *LoggingMsgInterceptor) Pre(ctx sdk.Context, msg sdk.Msg) error {
	logger := ctx.Logger().With("module", "msg-interceptor")
	logger.Info("msg pre-execution",
		"type", sdk.MsgTypeURL(msg),
		"height", ctx.BlockHeight(),
	)
	return nil
}

// Post logs the message result after execution.
func (l *LoggingMsgInterceptor) Post(ctx sdk.Context, msg sdk.Msg, result *sdk.Result, err error) {
	logger := ctx.Logger().With("module", "msg-interceptor")

	if err != nil {
		logger.Info("msg post-execution",
			"type", sdk.MsgTypeURL(msg),
			"success", false,
			"error", err.Error(),
		)
		return
	}

	// Log successful execution with response details
	var responseType string
	if result != nil && len(result.MsgResponses) > 0 && result.MsgResponses[0] != nil {
		responseType = result.MsgResponses[0].TypeUrl
	}

	logger.Info("msg post-execution",
		"type", sdk.MsgTypeURL(msg),
		"success", true,
		"response_type", responseType,
		"events_count", len(result.Events),
		"data_len", len(result.Data),
	)
}

// LoggingPostDecorator logs transaction-level results (kept for PostHandler chain).
type LoggingPostDecorator struct{}

// NewLoggingPostDecorator creates a new LoggingPostDecorator.
func NewLoggingPostDecorator() LoggingPostDecorator {
	return LoggingPostDecorator{}
}

// PostHandle logs the transaction summary after all messages executed.
func (d LoggingPostDecorator) PostHandle(ctx sdk.Context, tx sdk.Tx, simulate, success bool, next sdk.PostHandler) (sdk.Context, error) {
	logger := ctx.Logger().With("module", "post-handler")
	gasMeter := ctx.GasMeter()

	logger.Info("tx result",
		"success", success,
		"simulate", simulate,
		"msg_count", len(tx.GetMsgs()),
		"gas_used", gasMeter.GasConsumed(),
		"gas_limit", gasMeter.Limit(),
	)

	return next(ctx, tx, simulate, success)
}
