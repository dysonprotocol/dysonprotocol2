package keeper

import (
	"dysonprotocol.com/x/whaleswap/types"

	"github.com/cosmos/cosmos-sdk/baseapp"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

var _ baseapp.MsgHandlerInterceptor = (*ArbitrageMsgInterceptor)(nil)

// ArbitrageMsgInterceptor detects and executes arbitrage after pool-affecting messages.
type ArbitrageMsgInterceptor struct {
	keeper    *Keeper
	trader    string        // address for arbitrage trades (module account)
	txDecoder sdk.TxDecoder // decodes tx bytes for memo extraction
}

// NewArbitrageMsgInterceptor creates a new arbitrage interceptor.
// refDenom is now read from Params.ArbitrageRefDenom at runtime.
func NewArbitrageMsgInterceptor(keeper *Keeper, trader string, txDecoder sdk.TxDecoder) *ArbitrageMsgInterceptor {
	return &ArbitrageMsgInterceptor{
		keeper:    keeper,
		trader:    trader,
		txDecoder: txDecoder,
	}
}

// extractMemoFromContext decodes tx bytes from context and returns the memo.
func (i *ArbitrageMsgInterceptor) extractMemoFromContext(ctx sdk.Context) string {
	txBytes := ctx.TxBytes()
	if len(txBytes) == 0 || i.txDecoder == nil {
		return ""
	}
	tx, err := i.txDecoder(txBytes)
	if err != nil {
		return ""
	}
	memoTx, ok := tx.(sdk.TxWithMemo)
	if !ok {
		return ""
	}
	return memoTx.GetMemo()
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

	// ═════ AFFILIATE PAYMENT ═════
	memo := i.extractMemoFromContext(ctx)
	affiliateName := ParseAffiliateName(memo)
	if affiliateName == "" {
		return
	}

	// Calculate net profit from trade response
	netProfit, hasNeg := tradeResp.TraderOutputs.SafeSub(tradeResp.TraderInputs...)
	if hasNeg || netProfit.IsZero() || !netProfit.IsAllPositive() {
		return
	}

	remaining, paid, addr, affErr := i.keeper.ProcessAffiliatePayment(ctx, netProfit, affiliateName)
	if affErr != nil {
		// Log error but don't fail - Post handlers are fire-and-forget per SDK design
		// Arbitrage succeeded; affiliate payment is best-effort
		i.keeper.ArbitrageLogger(ctx).Error("affiliate payment failed",
			"error", affErr,
			"name", affiliateName,
			"profit", netProfit)
		return
	}
	if paid.IsZero() {
		return
	}

	// Emit affiliate event
	if emitErr := ctx.EventManager().EmitTypedEvent(&types.EventAffiliatePayment{
		AffiliateName: affiliateName,
		AffiliateAddr: addr,
		Amount:        paid,
		TradeId:       tradeResp.TradeId,
	}); emitErr != nil {
		i.keeper.ArbitrageLogger(ctx).Error("failed to emit affiliate event", "error", emitErr)
	}

	i.keeper.ArbitrageLogger(ctx).Debug("affiliate paid",
		"trade_id", tradeResp.TradeId,
		"name", affiliateName,
		"addr", addr,
		"paid", paid,
		"remaining", remaining,
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
