package keeper

import (
	"dysonprotocol.com/x/whaleswap/types"

	"github.com/cosmos/cosmos-sdk/baseapp"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

var _ baseapp.MsgHandlerInterceptor = (*ArbitrageMsgInterceptor)(nil)

// ArbitrageMsgInterceptor detects and executes arbitrage after pool-affecting messages.
type ArbitrageMsgInterceptor struct {
	keeper *Keeper
	trader string // address for arbitrage trades (module account)
}

// NewArbitrageMsgInterceptor creates a new arbitrage interceptor.
// refDenom is now read from Params.ArbitrageRefDenom at runtime.
func NewArbitrageMsgInterceptor(keeper *Keeper, trader string) *ArbitrageMsgInterceptor {
	return &ArbitrageMsgInterceptor{
		keeper: keeper,
		trader: trader,
	}
}

// Pre is called before message execution. No-op for arbitrage.
func (i *ArbitrageMsgInterceptor) Pre(ctx sdk.Context, msg sdk.Msg) error {
	return nil
}

// Post is called after message execution. Runs arbitrage if message affected pools.
func (i *ArbitrageMsgInterceptor) Post(ctx sdk.Context, msg sdk.Msg, result *sdk.Result, err error) {
	if err != nil || !ShouldCheckArbitrage(msg) {
		return
	}

	params := i.keeper.GetParams(ctx)
	if params.ArbitrageMode != types.ArbitrageMode_ARBITRAGE_MODE_AUTO {
		return
	}

	affectedDenoms := GetPoolDenomsFromMsg(msg)
	if len(affectedDenoms) == 0 {
		return
	}

	// Use shared arbitrage simulation (uses params.ArbitrageRefDenom by default)
	simResp, simErr := i.keeper.SimulateArbitrageInternal(ctx, i.trader, affectedDenoms, "")
	if simErr != nil || !simResp.Found || len(simResp.Operations) == 0 {
		return
	}

	// Execute the arbitrage trade
	tradeResp, execErr := i.keeper.MakeTrade(ctx, &types.MsgMakeTrade{
		Trader:     i.trader,
		Operations: simResp.Operations,
	})
	if execErr != nil {
		i.keeper.ArbitrageLogger(ctx).Error("arbitrage execution failed", "error", execErr)
		return
	}

	i.keeper.ArbitrageLogger(ctx).Debug("arbitrage executed",
		"trade_id", tradeResp.TradeId,
		"profit", simResp.Profit,
		"ops", len(simResp.Operations),
	)
}

// ComposedMsgInterceptor chains multiple interceptors together.
type ComposedMsgInterceptor struct {
	interceptors []baseapp.MsgHandlerInterceptor
}

// NewComposedMsgInterceptor creates a composed interceptor.
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
