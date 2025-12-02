package keeper

import (
	"dysonprotocol.com/x/whaleswap/types"

	"github.com/cosmos/cosmos-sdk/baseapp"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// Ensure ArbitrageMsgInterceptor implements baseapp.MsgHandlerInterceptor.
var _ baseapp.MsgHandlerInterceptor = (*ArbitrageMsgInterceptor)(nil)

// ArbitrageMsgInterceptor detects and executes arbitrage after pool-affecting messages.
type ArbitrageMsgInterceptor struct {
	keeper   *Keeper
	runner   *ArbitrageRunner
	trader   string // address to use for arbitrage trades (e.g., module account)
	refDenom string // reference denom for profit measurement
	enabled  bool   // can be toggled at runtime
}

// NewArbitrageMsgInterceptor creates a new arbitrage interceptor.
//
// Parameters:
//   - keeper: the whaleswap keeper
//   - trader: address to use for arbitrage trades (typically a module account)
//   - refDenom: denom to measure profit in (e.g., "udys")
func NewArbitrageMsgInterceptor(keeper *Keeper, trader string, refDenom string) *ArbitrageMsgInterceptor {
	return &ArbitrageMsgInterceptor{
		keeper:   keeper,
		runner:   NewArbitrageRunner(keeper),
		trader:   trader,
		refDenom: refDenom,
		enabled:  true,
	}
}

// SetEnabled enables or disables arbitrage detection.
func (i *ArbitrageMsgInterceptor) SetEnabled(enabled bool) {
	i.enabled = enabled
}

// Pre is called before message execution.
// Currently a no-op for arbitrage detection.
func (i *ArbitrageMsgInterceptor) Pre(ctx sdk.Context, msg sdk.Msg) error {
	return nil
}

// Post is called after message execution.
// If the message affected pools and succeeded, runs arbitrage detection.
func (i *ArbitrageMsgInterceptor) Post(ctx sdk.Context, msg sdk.Msg, result *sdk.Result, err error) {
	// Skip if disabled, failed, or not a pool-affecting message
	if !i.enabled || err != nil || !ShouldCheckArbitrage(msg) {
		return
	}

	// Check ArbitrageMode param - only run auto-execution in AUTO mode
	params := i.keeper.GetParams(ctx)
	if params.ArbitrageMode != types.ArbitrageMode_ARBITRAGE_MODE_AUTO {
		return
	}

	logger := i.keeper.ArbitrageLogger(ctx)

	// Get affected denoms from the message
	affectedDenoms := GetPoolDenomsFromMsg(msg)
	if len(affectedDenoms) == 0 {
		return
	}

	logger.Debug("arbitrage check triggered",
		"msg_type", sdk.MsgTypeURL(msg),
		"affected_denoms", affectedDenoms,
		"ref_denom", i.refDenom,
	)

	// Run arbitrage detection and execution
	// Always use configured refDenom (udys) - only execute if there's profit in udys terms
	arbResult, arbErr := i.runner.CheckAndExecuteArbitrage(
		ctx,
		i.trader,
		affectedDenoms,
		i.refDenom,
	)

	if arbErr != nil {
		logger.Error("arbitrage check error", "error", arbErr)
		return
	}

	if arbResult != nil && arbResult.Success {
		logger.Info("arbitrage executed",
			"profit", arbResult.Profit.String(),
			"ref_denom", i.refDenom,
			"inputs", arbResult.TraderInputs.String(),
			"outputs", arbResult.TraderOutputs.String(),
		)
	}
}

// ComposedMsgInterceptor chains multiple interceptors together.
// Pre calls are executed in order; Post calls are executed in reverse order.
type ComposedMsgInterceptor struct {
	interceptors []baseapp.MsgHandlerInterceptor
}

// NewComposedMsgInterceptor creates a composed interceptor from multiple interceptors.
func NewComposedMsgInterceptor(interceptors ...baseapp.MsgHandlerInterceptor) *ComposedMsgInterceptor {
	return &ComposedMsgInterceptor{interceptors: interceptors}
}

// Pre calls all interceptors' Pre methods in order.
func (c *ComposedMsgInterceptor) Pre(ctx sdk.Context, msg sdk.Msg) error {
	for _, i := range c.interceptors {
		if err := i.Pre(ctx, msg); err != nil {
			return err
		}
	}
	return nil
}

// Post calls all interceptors' Post methods in reverse order.
func (c *ComposedMsgInterceptor) Post(ctx sdk.Context, msg sdk.Msg, result *sdk.Result, err error) {
	for j := len(c.interceptors) - 1; j >= 0; j-- {
		c.interceptors[j].Post(ctx, msg, result, err)
	}
}
