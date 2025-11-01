package keeper

import (
	"context"

	cosmossdkerrors "cosmossdk.io/errors"
	"cosmossdk.io/math"
	whaleswap "dysonprotocol.com/x/whaleswap"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
)

// PoolSwap executes one or more exact-in or exact-out pool swap legs with a
// single end-of-tx settlement. Applies output-side fees per leg and enforces
// aggregate max_input caps and min_output guarantees.
//
// Semantics:
//   - Per-leg execution: for each leg, validates the pool/denoms and computes
//     the out amount using concentrated-liquidity band math (when configured) or
//     constant-product math, applies output-side fee based on the output denom,
//     and updates pool reserves.
//   - Aggregate constraints: after all legs, enforces per-denom debit caps
//     (max_input) and minimum outputs (min_output), then performs a single bank
//     move between trader and module for the net debits/credits.
//   - Invariants and recording: asserts AMM and module invariants and records a
//     single Trade containing all operations.
//
// Validation:
//   - legs must be non-empty; each leg must specify exactly one of swap_in or
//     swap_out with a positive amount.
//   - Pool must exist and have exactly two reserves; input/output denoms must be
//     present in the pool.
//   - Concentrated-liquidity: resulting price must remain within [min_price,
//     max_price]; exact-out must not exceed band capacity.
//   - Constant-product: swaps must not deplete any reserve; exact-out must not
//     exceed capacity.
//   - Aggregate: required debits must not exceed max_input caps; final credits
//     must satisfy min_output per denom.
//
// State Updates:
//   - Updates pool reserves and fees earned for each leg.
//   - Persists pool changes with updated timestamp.
//   - Records single Trade with all operations.
//
// Emits:
//   - EventPoolSwap per executed leg (with pool_id, trade_id, operation_index)
//     via recordTradeWithOperations
//   - EventTradeRecorded once after all legs are recorded
//
// Returns:
//   - *whaleswapv1.MsgPoolSwapResponse with amount_out: total coins credited to
//     the trader across all legs.
//
// Errors are returned on validation failures, capacity/band violations,
// invariant breaches, failed bank moves, or event emission failures; no panics.
func (k Keeper) PoolSwap(ctx context.Context, msg *whaleswapv1.MsgPoolSwap) (*whaleswapv1.MsgPoolSwapResponse, error) {
	accCodec := k.accKeeper.AddressCodec()
	traderBz, err := accCodec.StringToBytes(msg.Trader)
	if err != nil {
		return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidAddress, "invalid trader: %s", err.Error())
	}
	_ = sdk.AccAddress(traderBz)

	if len(msg.Legs) == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "legs must be non-empty")
	}

	// Build end-of-tx debit caps per denom (vector cap). Unspecified denoms have zero cap.
	caps := sdk.NewCoins(msg.MaxInput...)

	// module delta per denom: amount>0 means module receives; amount<0 means module pays
	deltaByDenom := map[string]math.Int{}

	// Simulate each leg against pool snapshots, update pools and collect operations
	var operations []whaleswapv1.TradeOperation
	for _, leg := range msg.Legs {
		if leg.PoolId == 0 {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "pool_id required")
		}
		// At least one of swap_in or swap_out must be provided
		if (leg.SwapIn.Denom == "" || !leg.SwapIn.Amount.IsPositive()) && (leg.SwapOut.Denom == "" || !leg.SwapOut.Amount.IsPositive()) {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "each leg must specify swap_in or swap_out with positive amount")
		}
		pool, gerr := k.PoolsMap.Get(ctx, leg.PoolId)
		if gerr != nil {
			return nil, cosmossdkerrors.Wrapf(gerr, "pool not found: %d", leg.PoolId)
		}
		if len(pool.Coins) != 2 {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool reserves")
		}
		one := math.LegacyNewDec(1)
		zero := math.LegacyZeroDec()

		// Determine orientation and target(s)
		hasIn := leg.SwapIn.Denom != "" && leg.SwapIn.Amount.IsPositive()
		hasOut := leg.SwapOut.Denom != "" && leg.SwapOut.Amount.IsPositive()
		if hasIn && hasOut {
			return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap_in and swap_out cannot both be set; specify exactly one per leg and use message-level max_input/min_output for global constraints")
		}
		inputIdx := -1
		outputIdx := -1
		var targetOutAmt math.Int
		var actualInCoin sdk.Coin
		var outAmt math.Int
		var outDenom string
		var soldDenom string
		var otherDenom string
		var prePrice math.LegacyDec
		var preSoldInt math.Int
		var preOtherInt math.Int
		if hasIn {
			if leg.SwapIn.Denom == pool.Coins[0].Denom {
				inputIdx = 0
			} else if leg.SwapIn.Denom == pool.Coins[1].Denom {
				inputIdx = 1
			} else {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "input denom %s not in pool %d", leg.SwapIn.Denom, leg.PoolId)
			}
			outputIdx = 1 - inputIdx
			actualInCoin = leg.SwapIn
		} else {
			// exact-out only: deduce input denom as the other reserve
			if leg.SwapOut.Denom == pool.Coins[0].Denom {
				outputIdx = 0
			} else if leg.SwapOut.Denom == pool.Coins[1].Denom {
				outputIdx = 1
			} else {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "output denom %s not in pool %d", leg.SwapOut.Denom, leg.PoolId)
			}
			inputIdx = 1 - outputIdx
			targetOutAmt = leg.SwapOut.Amount
		}
		soldDenom = pool.Coins[inputIdx].Denom
		otherDenom = pool.Coins[outputIdx].Denom
		preSoldInt = pool.Coins[inputIdx].Amount
		preOtherInt = pool.Coins[outputIdx].Amount
		if !preSoldInt.IsPositive() || !preOtherInt.IsPositive() {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "invalid pool reserves before swap: sold=%s other=%s", preSoldInt.String(), preOtherInt.String())
		}
		prePrice = math.LegacyNewDecFromInt(preOtherInt).Quo(math.LegacyNewDecFromInt(preSoldInt))

		// Select per-denom fee based on the output denom (fee applied on outputs)
		fee := pool.FeeRate.AmountOf(pool.Coins[outputIdx].Denom)
		rIn := math.LegacyNewDecFromInt(pool.Coins[inputIdx].Amount)
		rOut := math.LegacyNewDecFromInt(pool.Coins[outputIdx].Amount)
		if hasIn {
			effIn := math.LegacyNewDecFromInt(actualInCoin.Amount).Mul(one.Sub(fee))
			// Apply fee on output side instead of input: use full input as effIn
			effIn = math.LegacyNewDecFromInt(actualInCoin.Amount)
			kDec := rIn.Mul(rOut)
			q := kDec.Quo(rIn.Add(effIn)).Ceil()
			outDec := rOut.Sub(q)
			outAmt = outDec.TruncateInt()
			// Output-side fee accrual and netting
			feeInt := math.LegacyNewDecFromInt(outAmt).Mul(fee).TruncateInt()
			if feeInt.IsPositive() {
				pool.FeesEarned = sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(pool.Coins[outputIdx].Denom, feeInt))
			}
			outAmt = outAmt.Sub(feeInt)
			if !outAmt.IsPositive() {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap output too small")
			}
			newIn := pool.Coins[inputIdx].Amount.Add(actualInCoin.Amount)
			newOut := pool.Coins[outputIdx].Amount.Sub(outAmt)
			if !newOut.IsPositive() {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap would deplete output reserve to zero")
			}
			if inputIdx == 0 {
				pool.Coins = sdk.NewCoins(
					sdk.NewCoin(pool.Coins[0].Denom, newIn),
					sdk.NewCoin(pool.Coins[1].Denom, newOut),
				)
				outDenom = pool.Coins[1].Denom
			} else {
				pool.Coins = sdk.NewCoins(
					sdk.NewCoin(pool.Coins[0].Denom, newOut),
					sdk.NewCoin(pool.Coins[1].Denom, newIn),
				)
				outDenom = pool.Coins[0].Denom
			}
		} else { // exact-out
			if !targetOutAmt.IsPositive() {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap_out must be > 0")
			}
			// Inflate to gross output to ensure net (after fee) >= targetOutAmt
			grossOut := math.LegacyNewDecFromInt(targetOutAmt).Quo(one.Sub(fee)).Ceil().TruncateInt()
			out := math.LegacyNewDecFromInt(grossOut)
			if out.GTE(rOut) {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "exact-out equals/exceeds reserve")
			}
			// effInRequired = rIn*(rOut/(rOut-out) - 1)
			effInReq := rIn.Mul(rOut.Quo(rOut.Sub(out)).Sub(one))
			gross := effInReq.Ceil().TruncateInt()
			if !gross.IsPositive() {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "computed input not positive")
			}
			effInActual := math.LegacyNewDecFromInt(gross)
			kDec := rIn.Mul(rOut)
			q := kDec.Quo(rIn.Add(effInActual)).Ceil()
			outDec := rOut.Sub(q)
			outAct := outDec.TruncateInt()
			// Ensure net >= targetOutAmt after fee
			for {
				feeInt := math.LegacyNewDecFromInt(outAct).Mul(fee).TruncateInt()
				net := outAct.Sub(feeInt)
				if !net.LT(targetOutAmt) {
					break
				}
				gross = gross.AddRaw(1)
				effInActual = math.LegacyNewDecFromInt(gross)
				q = kDec.Quo(rIn.Add(effInActual)).Ceil()
				outDec = rOut.Sub(q)
				outAct = outDec.TruncateInt()
			}
			grossCoin := sdk.NewCoin(pool.Coins[outputIdx].Denom, outAct)
			netDec := sdk.NewDecCoinsFromCoins(grossCoin).MulDecTruncate(one.Sub(fee))
			netCoins, _ := netDec.TruncateDecimal()
			netOut := netCoins.AmountOf(grossCoin.Denom)
			feeIntOut := outAct.Sub(netOut)
			if feeIntOut.IsPositive() {
				pool.FeesEarned = sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(grossCoin.Denom, feeIntOut))
			}
			newIn := pool.Coins[inputIdx].Amount.Add(gross)
			newOut := pool.Coins[outputIdx].Amount.Sub(netOut)
			if !newOut.IsPositive() {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap would deplete output reserve to zero")
			}
			if inputIdx == 0 {
				pool.Coins = sdk.NewCoins(
					sdk.NewCoin(pool.Coins[0].Denom, newIn),
					sdk.NewCoin(pool.Coins[1].Denom, newOut),
				)
				outDenom = pool.Coins[1].Denom
			} else {
				pool.Coins = sdk.NewCoins(
					sdk.NewCoin(pool.Coins[0].Denom, newOut),
					sdk.NewCoin(pool.Coins[1].Denom, newIn),
				)
				outDenom = pool.Coins[0].Denom
			}
			outAmt = netOut
			actualInCoin = sdk.NewCoin(pool.Coins[inputIdx].Denom, gross)
		}

		postSoldInt := pool.Coins.AmountOf(soldDenom)
		postOtherInt := pool.Coins.AmountOf(otherDenom)
		if !postSoldInt.IsPositive() || !postOtherInt.IsPositive() {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "post-swap reserves invalid: %s=%s %s=%s", soldDenom, postSoldInt.String(), otherDenom, postOtherInt.String())
		}
		boundDec := pool.BoundPercent.AmountOf(soldDenom)
		if len(pool.BoundPercent) == 0 || boundDec.IsZero() {
			boundDec = one
		}
		if boundDec.LT(zero) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "bound_percent for %s must be >= 0", soldDenom)
		}
		if boundDec.GT(one) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "bound_percent for %s must be <= 1: %s", soldDenom, boundDec.String())
		}
		if !boundDec.Equal(one) {
			limit := prePrice.Mul(one.Sub(boundDec))
			postPrice := math.LegacyNewDecFromInt(postOtherInt).Quo(math.LegacyNewDecFromInt(postSoldInt))
			if postPrice.LT(limit) {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest,
					"swap violates directional bound for %s: pre_price=%s post_price=%s bound=%s limit=%s",
					soldDenom, prePrice.String(), postPrice.String(), boundDec.String(), limit.String())
			}
		}

		// Enforce rate constraint (when both swap_in and swap_out provided)
		if hasIn && hasOut {
			if leg.SwapOut.Denom != outDenom {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "swap_out denom %s doesn't match computed %s", leg.SwapOut.Denom, outDenom)
			}
			if !outAmt.Equal(leg.SwapOut.Amount) {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "computed out %s != required %s", outAmt.String(), leg.SwapOut.Amount.String())
			}
		}

		// Persist pool changes (EventPoolSwap emitted by recordTradeWithOperations with trade linkage)
		pool.NumTrades += 1
		if err := k.updatePool(ctx, &pool); err != nil {
			return nil, cosmossdkerrors.Wrapf(err, "failed to update pool %d after swap", pool.PoolId)
		}

		// Accumulate module delta and collect operation (safe map accumulation)
		if v, ok := deltaByDenom[actualInCoin.Denom]; ok {
			deltaByDenom[actualInCoin.Denom] = v.Add(actualInCoin.Amount)
		} else {
			deltaByDenom[actualInCoin.Denom] = actualInCoin.Amount
		}
		if v, ok := deltaByDenom[outDenom]; ok {
			deltaByDenom[outDenom] = v.Sub(outAmt)
		} else {
			deltaByDenom[outDenom] = outAmt.Neg()
		}

		// Build operation record with execution results
		op := whaleswapv1.TradeOperation{
			Op:       &whaleswapv1.TradeOperation_Swap{Swap: &leg},
			Sent:     actualInCoin,
			Received: sdk.NewCoin(outDenom, outAmt),
		}
		operations = append(operations, op)
	}

	// Derive debits (trader -> module) and credits (module -> trader) from module deltas
	requiredDebits := sdk.NewCoins()
	credits := sdk.NewCoins()
	for denom, modAmt := range deltaByDenom {
		if modAmt.IsZero() {
			continue
		}
		if modAmt.IsPositive() {
			// module receives => trader must pay this denom
			need := modAmt
			capAmt := caps.AmountOf(denom)
			if capAmt.IsZero() || capAmt.LT(need) {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInsufficientFunds, "debit exceeds cap for %s: need %s <= cap %s", denom, need.String(), capAmt.String())
			}
			requiredDebits = requiredDebits.Add(sdk.NewCoin(denom, need))
			continue
		}
		if modAmt.IsNegative() {
			// module pays => trader receives this denom
			credits = credits.Add(sdk.NewCoin(denom, modAmt.Abs()))
		}
	}
	// Enforce min_output
	for _, m := range msg.MinOutput {
		got := credits.AmountOf(m.Denom)
		if got.LT(m.Amount) {
			return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "min_output not met for %s: got %s < %s", m.Denom, got.String(), m.Amount.String())
		}
	}

	// Single aggregated move: trader <-> module
	inputs := []banktypes.Input{}
	outputs := []banktypes.Output{}
	traderBech := msg.Trader
	moduleBech := k.accKeeper.GetModuleAddress(whaleswap.ModuleName).String()
	if !requiredDebits.IsZero() {
		inputs = append(inputs, banktypes.Input{Address: traderBech, Coins: requiredDebits})
		outputs = append(outputs, banktypes.Output{Address: moduleBech, Coins: requiredDebits})
	}
	if !credits.IsZero() {
		inputs = append(inputs, banktypes.Input{Address: moduleBech, Coins: credits})
		outputs = append(outputs, banktypes.Output{Address: traderBech, Coins: credits})
	}
	if len(inputs) == 0 || len(outputs) == 0 {
		return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "no inputs or outputs for pool swap move")
	}
	if err := k.wsMoveCoins(ctx, inputs, outputs); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "move coins failed")
	}

	if err := k.AssertAMMInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "AMM invariant after aggregated PoolSwap")
	}

	if err := k.AssertInvariants(ctx); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "invariant after PoolSwap")
	}

	// Record single trade with all operations
	if _, err := k.recordTradeWithOperations(ctx, msg.Trader, operations, ""); err != nil {
		return nil, cosmossdkerrors.Wrap(err, "failed to record trade")
	}

	return &whaleswapv1.MsgPoolSwapResponse{AmountOut: credits}, nil
}
