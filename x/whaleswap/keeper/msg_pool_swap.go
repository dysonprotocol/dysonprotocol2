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

// PoolSwap executes one or more pool swap legs with a single end-of-tx
// settlement. Each leg is either exact-in (swap_in) or exact-out (swap_out),
// never both. Output-side fees are applied per leg based on the output denom.
//
// Semantics:
//   - Per-leg execution: for each SwapLeg, validates the pool and denoms,
//     computes the out amount using either the concentrated-liquidity band
//     formulas (when a band is configured) or constant-product math, applies
//     output-side fee, and updates pool reserves in-memory.
//   - Aggregate caps/guarantees: after all legs, enforces per-denom debit caps
//     (max_input) and minimum outputs (min_output) on the net settlement.
//   - Settlement: performs a single bank move between trader and module using
//     the net debits/credits across all legs.
//   - Invariants: asserts AMM invariants and general module invariants.
//   - Recording: records one Trade containing all operations.
//
// Validation:
//   - msg.Legs must be non-empty; each leg must specify exactly one of
//     swap_in or swap_out with a positive amount.
//   - Pool must exist and have exactly two reserves; input/output denoms must
//     belong to the pool.
//   - Concentrated-liquidity: resulting price must remain within the configured
//     [min_price, max_price] band; exact-out must not exceed band capacity.
//   - Constant-product: swaps must not deplete any reserve; exact-out must not
//     exceed capacity.
//   - Aggregate constraints: required debits must not exceed max_input caps;
//     final credits must satisfy min_output per denom.
//
// Emits:
//   - EventPoolSwap per executed leg (with pool_id, trade_id, operation_index)
//     emitted by recordTradeWithOperations.
//   - EventTradeRecorded once after all legs are recorded.
//
// Returns:
//   - *whaleswapv1.MsgPoolSwapResponse with AmountOut set to the net coins
//     credited to the trader across all legs (cosmos-sdk Coins).
//
// Errors are returned for any validation failure, capacity/band violations,
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

		// Select per-denom fee based on the output denom (fee applied on outputs)
		fee := pool.FeeRate.AmountOf(pool.Coins[outputIdx].Denom)

		if len(pool.MinPrice) == 2 {
			// concentrated liquidity path
			sa, sb, err := k.bandSqrt(pool)
			if err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to compute band sqrt prices")
			}
			sp, err := k.poolSqrtPrice(pool, pool.Coins[0].Denom, pool.Coins[1].Denom)
			if err != nil {
				return nil, cosmossdkerrors.Wrap(err, "failed to compute current sqrt price")
			}
			Lcur, _, _, err := k.liquidityForReserves(pool)
			if err != nil {
				return nil, cosmossdkerrors.Wrap(err, "invalid pool liquidity")
			}
			if !Lcur.IsPositive() {
				return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "invalid pool liquidity")
			}
			L := Lcur
			if hasIn {
				// exact-in: apply fee on output side (not on input)
				effIn := math.LegacyNewDecFromInt(actualInCoin.Amount)
				if inputIdx == 0 {
					invSpPrime := math.LegacyOneDec().Quo(sp).Add(effIn.Quo(L))
					if invSpPrime.LTE(math.LegacyZeroDec()) {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "insufficient liquidity")
					}
					spPrime, err := k.sqrtPrice(math.LegacyOneDec().Quo(invSpPrime))
					if err != nil {
						return nil, cosmossdkerrors.Wrap(err, "failed to compute next sqrt price")
					}
					if spPrime.LT(sa) {
						spPrime = sa
					}
					outDec := L.Mul(sp.Sub(spPrime))
					outAmt = outDec.TruncateInt()
				} else {
					spPrime := sp.Add(effIn.Quo(L))
					if spPrime.GT(sb) {
						spPrime = sb
					}
					outDec := L.Mul(math.LegacyOneDec().Quo(sp).Sub(math.LegacyOneDec().Quo(spPrime)))
					outAmt = outDec.TruncateInt()
				}
				// Apply output-side fee: reduce output by fee and accrue fee in output denom
				feeInt := math.LegacyNewDecFromInt(outAmt).Mul(fee).TruncateInt()
				if feeInt.IsPositive() {
					pool.FeesEarned = sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(pool.Coins[outputIdx].Denom, feeInt))
				}
				outAmt = outAmt.Sub(feeInt)
			} else {
				// exact-out: compute minimal input to achieve targetOutAmt
				if !targetOutAmt.IsPositive() {
					return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap_out must be > 0")
				}
				if outputIdx == 1 { // out denom is coin[1] => token0-in
					// Inflate required gross output so that net (after fee) >= targetOutAmt
					grossOut := math.LegacyNewDecFromInt(targetOutAmt).Quo(one.Sub(fee)).Ceil().TruncateInt()
					outDec := math.LegacyNewDecFromInt(grossOut)
					spPrime := sp.Sub(outDec.Quo(L))
					if spPrime.LT(sa) {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "exact-out exceeds band capacity")
					}
					effInDec := L.Mul(math.LegacyOneDec().Quo(spPrime).Sub(math.LegacyOneDec().Quo(sp)))
					// Input has no fee; take ceiling of required input
					gross := effInDec.Ceil().TruncateInt()
					if !gross.IsPositive() {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "computed input not positive")
					}
					effInActual := math.LegacyNewDecFromInt(gross)
					invSpPrime := math.LegacyOneDec().Quo(sp).Add(effInActual.Quo(L))
					spPrimeAct, err := k.sqrtPrice(math.LegacyOneDec().Quo(invSpPrime))
					if err != nil {
						return nil, cosmossdkerrors.Wrap(err, "failed to compute next sqrt price")
					}
					outAct := L.Mul(sp.Sub(spPrimeAct)).TruncateInt()
					// Ensure net >= targetOutAmt after output fee
					for {
						feeInt := math.LegacyNewDecFromInt(outAct).Mul(fee).TruncateInt()
						net := outAct.Sub(feeInt)
						if !net.LT(targetOutAmt) {
							break
						}
						gross = gross.AddRaw(1)
						effInActual = math.LegacyNewDecFromInt(gross)
						invSpPrime = math.LegacyOneDec().Quo(sp).Add(effInActual.Quo(L))
						spPrimeAct, err = k.sqrtPrice(math.LegacyOneDec().Quo(invSpPrime))
						if err != nil {
							return nil, cosmossdkerrors.Wrap(err, "failed to compute next sqrt price (recheck)")
						}
						outAct = L.Mul(sp.Sub(spPrimeAct)).TruncateInt()
						// loop continues until net >= targetOutAmt or failure above
					}
					// Apply output-side fee using DecCoins scaling and update reserves: token0-in
					grossCoin := sdk.NewCoin(pool.Coins[1].Denom, outAct)
					netDec := sdk.NewDecCoinsFromCoins(grossCoin).MulDecTruncate(one.Sub(fee))
					netCoins, _ := netDec.TruncateDecimal()
					netOut := netCoins.AmountOf(grossCoin.Denom)
					feeIntOut := outAct.Sub(netOut)
					if feeIntOut.IsPositive() {
						pool.FeesEarned = sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(grossCoin.Denom, feeIntOut))
					}
					new0 := pool.Coins[0].Amount.Add(gross)
					// subtract net out only
					new1 := pool.Coins[1].Amount.Sub(netOut)
					if !new1.IsPositive() {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap would deplete quote reserve to zero")
					}
					pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, new0), sdk.NewCoin(pool.Coins[1].Denom, new1))
					outAmt = netOut
					outDenom = pool.Coins[1].Denom
					actualInCoin = sdk.NewCoin(pool.Coins[0].Denom, gross)
				} else { // outputIdx == 0 => token1-in
					grossOut := math.LegacyNewDecFromInt(targetOutAmt).Quo(one.Sub(fee)).Ceil().TruncateInt()
					outDec := math.LegacyNewDecFromInt(grossOut)
					denom := math.LegacyOneDec().Quo(sp).Sub(outDec.Quo(L))
					if !denom.IsPositive() {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "exact-out exceeds pool capacity")
					}
					spPrime := math.LegacyOneDec().Quo(denom)
					if spPrime.GT(sb) {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInsufficientFunds, "exact-out exceeds band capacity")
					}
					effInDec := L.Mul(spPrime.Sub(sp))
					gross := effInDec.Ceil().TruncateInt()
					if !gross.IsPositive() {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "computed input not positive")
					}
					effInActual := math.LegacyNewDecFromInt(gross)
					spPrimeAct := sp.Add(effInActual.Quo(L))
					outAct := L.Mul(math.LegacyOneDec().Quo(sp).Sub(math.LegacyOneDec().Quo(spPrimeAct))).TruncateInt()
					for {
						feeInt := math.LegacyNewDecFromInt(outAct).Mul(fee).TruncateInt()
						net := outAct.Sub(feeInt)
						if !net.LT(targetOutAmt) {
							break
						}
						gross = gross.AddRaw(1)
						effInActual = math.LegacyNewDecFromInt(gross)
						spPrimeAct = sp.Add(effInActual.Quo(L))
						outAct = L.Mul(math.LegacyOneDec().Quo(sp).Sub(math.LegacyOneDec().Quo(spPrimeAct))).TruncateInt()
					}
					// Apply output-side fee using DecCoins scaling and update reserves: token1-in
					grossCoin := sdk.NewCoin(pool.Coins[0].Denom, outAct)
					netDec := sdk.NewDecCoinsFromCoins(grossCoin).MulDecTruncate(one.Sub(fee))
					netCoins, _ := netDec.TruncateDecimal()
					netOut := netCoins.AmountOf(grossCoin.Denom)
					feeIntOut := outAct.Sub(netOut)
					if feeIntOut.IsPositive() {
						pool.FeesEarned = sdk.NewCoins(pool.FeesEarned...).Add(sdk.NewCoin(grossCoin.Denom, feeIntOut))
					}
					// Update reserves: token1-in
					new0 := pool.Coins[0].Amount.Sub(netOut)
					new1 := pool.Coins[1].Amount.Add(gross)
					if !new0.IsPositive() {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap would deplete base reserve to zero")
					}
					pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, new0), sdk.NewCoin(pool.Coins[1].Denom, new1))
					outAmt = netOut
					outDenom = pool.Coins[0].Denom
					actualInCoin = sdk.NewCoin(pool.Coins[1].Denom, gross)
				}
			}
			// When exact-in path, set outDenom and reserves update
			if hasIn {
				if inputIdx == 0 {
					new0 := pool.Coins[0].Amount.Add(actualInCoin.Amount)
					new1 := pool.Coins[1].Amount.Sub(outAmt)
					if !new1.IsPositive() {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap would deplete quote reserve to zero")
					}
					pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, new0), sdk.NewCoin(pool.Coins[1].Denom, new1))
					outDenom = pool.Coins[1].Denom
				} else {
					new0 := pool.Coins[0].Amount.Sub(outAmt)
					new1 := pool.Coins[1].Amount.Add(actualInCoin.Amount)
					if !new0.IsPositive() {
						return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "swap would deplete base reserve to zero")
					}
					pool.Coins = sdk.NewCoins(sdk.NewCoin(pool.Coins[0].Denom, new0), sdk.NewCoin(pool.Coins[1].Denom, new1))
					outDenom = pool.Coins[0].Denom
				}
			}
			// Band check post swap
			rBase := pool.Coins[0].Amount
			rQuote := pool.Coins[1].Amount
			denomA, denomB := pool.Coins[0].Denom, pool.Coins[1].Denom
			minBase := pool.MinPrice.AmountOf(denomA)
			minQuote := pool.MinPrice.AmountOf(denomB)
			maxBase := pool.MaxPrice.AmountOf(denomA)
			maxQuote := pool.MaxPrice.AmountOf(denomB)
			if rQuote.Mul(minBase).LT(rBase.Mul(minQuote)) {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "resulting price below band after swap")
			}
			if rQuote.Mul(maxBase).GT(rBase.Mul(maxQuote)) {
				return nil, cosmossdkerrors.Wrapf(sdkerrors.ErrInvalidRequest, "resulting price above band after swap")
			}
		} else {
			// constant product path
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
