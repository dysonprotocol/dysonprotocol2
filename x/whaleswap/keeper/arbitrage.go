package keeper

import (
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"cosmossdk.io/log"
	"cosmossdk.io/math"
	whaleswapv1 "dysonprotocol.com/x/whaleswap/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

// LIGHTNING finds multi-path arbitrage by iteratively finding profitable cycles
// on local pool state, then executing all operations in a single MakeTrade.

var (
	DecZero         = math.LegacyZeroDec()
	DecOne          = math.LegacyOneDec()
	errNoOperations = errors.New("no operations generated")
)

// ArbitragePool holds minimal pool info for arbitrage computation.
type ArbitragePool struct {
	PoolID   uint64
	Denom0   string // canonical order: denom0 < denom1
	Denom1   string
	Reserve0 math.Int // for bounds computation
	Reserve1 math.Int
	Fee0     math.LegacyDec // fee when selling denom0
	Fee1     math.LegacyDec // fee when selling denom1
}

// ArbitrageContext holds the pool graph for arbitrage computation.
type ArbitrageContext struct {
	Keeper     *Keeper
	Ctx        sdk.Context
	Trader     string
	Pools      []ArbitragePool
	PoolIndex  map[uint64]int   // pool_id -> index
	DenomPools map[string][]int // denom -> pool indices
	AllDenoms  []string
	RefDenom   string
	MaxDepth   int // max path depth (default: 6)
}

// ArbitrageResult holds the result of simulating/executing arbitrage.
type ArbitrageResult struct {
	Success       bool
	TraderInputs  sdk.Coins
	TraderOutputs sdk.Coins
	Profit        math.Int
	Msg           *whaleswapv1.MsgMakeTrade
	Response      *whaleswapv1.MsgMakeTradeResponse
	Error         error
}

// LocalPool is a mutable copy of pool state for fast local simulation.
type LocalPool struct {
	PoolID   uint64
	Denom0   string
	Denom1   string
	Reserve0 math.LegacyDec // Mutable - updated after simulated swaps
	Reserve1 math.LegacyDec
	Fee0     math.LegacyDec
	Fee1     math.LegacyDec
}

// arbStep represents one step in an arbitrage path
type arbStep struct {
	poolIdx    int
	sellDenom0 bool
	amount     math.LegacyDec
}

// =============================================================================
// Context Building
// =============================================================================

// BuildArbitrageContext constructs the pool graph for arbitrage detection.
func (k *Keeper) BuildArbitrageContext(
	ctx sdk.Context,
	trader string,
	affectedDenoms []string,
	refDenom string,
	depth int,
) (*ArbitrageContext, error) {
	ac := &ArbitrageContext{
		Keeper:     k,
		Ctx:        ctx,
		Trader:     trader,
		Pools:      make([]ArbitragePool, 0),
		PoolIndex:  make(map[uint64]int),
		DenomPools: make(map[string][]int),
		AllDenoms:  make([]string, 0),
		RefDenom:   refDenom,
		MaxDepth:   6, // default
	}

	// BFS to expand the pool graph
	denomQueue := make([]string, len(affectedDenoms))
	copy(denomQueue, affectedDenoms)
	visitedDenoms := make(map[string]bool)
	visitedPools := make(map[uint64]bool)

	for d := 0; d <= depth; d++ {
		nextDenoms := make([]string, 0)

		for _, denom := range denomQueue {
			if visitedDenoms[denom] {
				continue
			}
			visitedDenoms[denom] = true
			ac.AllDenoms = append(ac.AllDenoms, denom)

			poolsResp, err := k.PoolsByDenom(ctx, &whaleswapv1.QueryPoolsByDenomRequest{Denom: denom})
			if err != nil {
				return nil, err
			}

			for _, pool := range poolsResp.Pools {
				if visitedPools[pool.PoolId] {
					continue
				}
				visitedPools[pool.PoolId] = true

				ap, err := poolToArbitragePool(*pool)
				if err != nil {
					continue
				}

				idx := len(ac.Pools)
				ac.Pools = append(ac.Pools, ap)
				ac.PoolIndex[pool.PoolId] = idx
				ac.DenomPools[ap.Denom0] = append(ac.DenomPools[ap.Denom0], idx)
				ac.DenomPools[ap.Denom1] = append(ac.DenomPools[ap.Denom1], idx)

				if !visitedDenoms[ap.Denom0] {
					nextDenoms = append(nextDenoms, ap.Denom0)
				}
				if !visitedDenoms[ap.Denom1] {
					nextDenoms = append(nextDenoms, ap.Denom1)
				}
			}
		}
		denomQueue = nextDenoms
	}

	return ac, nil
}

func poolToArbitragePool(pool whaleswapv1.Pool) (ArbitragePool, error) {
	if len(pool.Coins) != 2 || len(pool.FeeRate) != 2 {
		return ArbitragePool{}, fmt.Errorf("invalid pool structure")
	}

	denom0, denom1 := pool.Coins[0].Denom, pool.Coins[1].Denom
	reserve0, reserve1 := pool.Coins[0].Amount, pool.Coins[1].Amount
	var fee0, fee1 math.LegacyDec

	for _, fr := range pool.FeeRate {
		if fr.Denom == denom0 {
			fee0 = fr.Amount
		} else if fr.Denom == denom1 {
			fee1 = fr.Amount
		}
	}

	if fee0.IsNil() || fee1.IsNil() {
		return ArbitragePool{}, fmt.Errorf("missing fee rates")
	}

	return ArbitragePool{
		PoolID:   pool.PoolId,
		Denom0:   denom0,
		Denom1:   denom1,
		Reserve0: reserve0,
		Reserve1: reserve1,
		Fee0:     fee0,
		Fee1:     fee1,
	}, nil
}

// =============================================================================
// LIGHTNING Algorithm
// =============================================================================

// FindArbitrage runs the LIGHTNING algorithm to find and optimize arbitrage.
// Returns nil if no profitable arbitrage found.
func (ac *ArbitrageContext) FindArbitrage() *ArbitrageResult {
	logger := ac.Keeper.ArbitrageLogger(ac.Ctx)
	startTime := time.Now()

	if len(ac.Pools) < 2 {
		logger.Debug("LIGHTNING: not enough pools")
		return nil
	}

	// STEP 1: Copy pools to local mutable state
	localPools := ac.copyToLocal()

	// STEP 2: Iteratively find paths, updating local state each time
	const maxIterations = 10
	var allOperations []whaleswapv1.TradeOperation
	totalProfit := DecZero
	pathsFound := 0

	for iter := 0; iter < maxIterations; iter++ {
		// Find best cycle using local reserves
		path, profit := ac.findBestCycleLocal(localPools, logger)

		if len(path) == 0 || profit.LTE(DecOne) {
			logger.Debug("LIGHTNING: no more profitable paths",
				"iteration", iter,
				"paths_found", pathsFound,
				"total_profit", totalProfit.TruncateInt().String(),
			)
			break
		}

		// Simulate path on local state and collect operations
		ops := ac.simulatePathLocal(localPools, path, logger)
		if len(ops) == 0 {
			break
		}

		allOperations = append(allOperations, ops...)
		totalProfit = totalProfit.Add(profit)
		pathsFound++

		logger.Debug("LIGHTNING: path found",
			"iteration", iter,
			"path_len", len(path),
			"profit", profit.TruncateInt().String(),
			"ops_added", len(ops),
			"total_ops", len(allOperations),
		)
	}

	if len(allOperations) == 0 {
		logger.Debug("LIGHTNING: no operations collected")
		return nil
	}

	// STEP 3: Build and simulate the combined MsgMakeTrade
	msg := &whaleswapv1.MsgMakeTrade{
		Trader:     ac.Trader,
		Operations: allOperations,
		MaxInput:   nil, // Enforce circularity
		MinOutput:  []sdk.Coin{},
	}

	result := ac.simulateMsg(msg)

	duration := time.Since(startTime)
	if result != nil && result.Success && result.Profit.IsPositive() {
		logger.Debug("LIGHTNING: success",
			"profit", result.Profit.String(),
			"paths", pathsFound,
			"ops", len(allOperations),
			"duration_ms", duration.Milliseconds(),
		)
	} else {
		logger.Debug("LIGHTNING: simulation failed",
			"paths_attempted", pathsFound,
			"ops", len(allOperations),
			"error", func() string {
				if result != nil && result.Error != nil {
					return result.Error.Error()
				}
				return "zero profit or nil"
			}(),
		)
	}

	return result
}

// copyToLocal creates mutable copies of pool state.
func (ac *ArbitrageContext) copyToLocal() []LocalPool {
	local := make([]LocalPool, len(ac.Pools))
	for i, p := range ac.Pools {
		local[i] = LocalPool{
			PoolID:   p.PoolID,
			Denom0:   p.Denom0,
			Denom1:   p.Denom1,
			Reserve0: math.LegacyNewDecFromInt(p.Reserve0),
			Reserve1: math.LegacyNewDecFromInt(p.Reserve1),
			Fee0:     p.Fee0,
			Fee1:     p.Fee1,
		}
	}
	return local
}

// findBestCycleLocal finds the most profitable cycle using local pool state.
func (ac *ArbitrageContext) findBestCycleLocal(
	localPools []LocalPool,
	logger log.Logger,
) ([]arbStep, math.LegacyDec) {
	// Build token index
	tokenIdx := make(map[string]int)
	var tokens []string
	idx := 0

	tokenIdx[ac.RefDenom] = idx
	tokens = append(tokens, ac.RefDenom)
	idx++

	for _, pool := range localPools {
		if _, ok := tokenIdx[pool.Denom0]; !ok {
			tokenIdx[pool.Denom0] = idx
			tokens = append(tokens, pool.Denom0)
			idx++
		}
		if _, ok := tokenIdx[pool.Denom1]; !ok {
			tokenIdx[pool.Denom1] = idx
			tokens = append(tokens, pool.Denom1)
			idx++
		}
	}

	baseIdx := tokenIdx[ac.RefDenom]
	numTokens := len(tokens)

	// Find minimum reserve for starting amount
	minReserve := math.LegacyNewDec(1 << 60)
	for _, pool := range localPools {
		if pool.Reserve0.GT(DecZero) && pool.Reserve0.LT(minReserve) {
			minReserve = pool.Reserve0
		}
		if pool.Reserve1.GT(DecZero) && pool.Reserve1.LT(minReserve) {
			minReserve = pool.Reserve1
		}
	}

	// Try different starting amounts
	var bestPath []arbStep
	bestProfit := DecZero

	maxDepth := ac.MaxDepth
	if maxDepth <= 0 {
		maxDepth = 6
	}

	for _, fracPct := range []int64{10, 25, 50} {
		startAmt := minReserve.MulInt64(fracPct).QuoInt64(100)
		if startAmt.LT(DecOne) {
			startAmt = DecOne
		}
		// Truncate to integer to match MakeTrade execution
		startAmt = math.LegacyNewDecFromInt(startAmt.TruncateInt())

		profit, path := ac.bellmanFordLocal(localPools, tokens, tokenIdx, baseIdx, numTokens, startAmt, maxDepth)

		if profit.GT(bestProfit) && len(path) > 0 {
			bestProfit = profit
			bestPath = path
		}
	}

	return bestPath, bestProfit
}

// bellmanFordLocal runs Bellman-Ford style relaxation using local pool state.
func (ac *ArbitrageContext) bellmanFordLocal(
	localPools []LocalPool,
	tokens []string,
	tokenIdx map[string]int,
	baseIdx, numTokens int,
	startAmt math.LegacyDec,
	maxDepth int,
) (math.LegacyDec, []arbStep) {
	// dist[i] = max reachable amount of token i from base
	dist := make([]math.LegacyDec, numTokens)
	for i := range dist {
		dist[i] = DecZero
	}
	dist[baseIdx] = startAmt

	// parent[i] = how we reached token i
	parent := make([]arbStep, numTokens)
	for i := range parent {
		parent[i] = arbStep{poolIdx: -1}
	}

	for iter := 0; iter < maxDepth; iter++ {
		updated := false
		newDist := make([]math.LegacyDec, numTokens)
		copy(newDist, dist)

		for poolIdx, pool := range localPools {
			for _, sellDenom0 := range []bool{true, false} {
				var tin, tout string
				var rIn, rOut, fee math.LegacyDec

				if sellDenom0 {
					tin, tout = pool.Denom0, pool.Denom1
					rIn, rOut = pool.Reserve0, pool.Reserve1
					fee = pool.Fee0
				} else {
					tin, tout = pool.Denom1, pool.Denom0
					rIn, rOut = pool.Reserve1, pool.Reserve0
					fee = pool.Fee1
				}

				srcIdx, srcOk := tokenIdx[tin]
				dstIdx, dstOk := tokenIdx[tout]
				if !srcOk || !dstOk || dist[srcIdx].LT(DecOne) {
					continue
				}
				if rIn.LT(DecOne) || rOut.LT(DecOne) {
					continue
				}

				// Use truncated amount to match MakeTrade execution
				amtTrunc := dist[srcIdx].TruncateInt()
				if !amtTrunc.IsPositive() {
					continue
				}
				amtDec := math.LegacyNewDecFromInt(amtTrunc)

				// Match MakeTrade's exact formula: q = Ceil(k / (rIn + effIn)), out = rOut - q
				gamma := DecOne.Sub(fee)
				effectiveIn := amtDec.Mul(gamma)
				kDec := rIn.Mul(rOut)
				q := kDec.Quo(rIn.Add(effectiveIn)).Ceil()
				out := rOut.Sub(q)

				if out.GT(newDist[dstIdx]) {
					newDist[dstIdx] = out
					parent[dstIdx] = arbStep{
						poolIdx:    poolIdx,
						sellDenom0: sellDenom0,
						amount:     amtDec,
					}
					updated = true
				}
			}
		}

		dist = newDist

		// Early profit detection
		if dist[baseIdx].GT(startAmt.MulInt64(1001).QuoInt64(1000)) {
			path := ac.reconstructPathLocal(localPools, parent, tokens, tokenIdx, baseIdx, startAmt, maxDepth)
			profit := dist[baseIdx].Sub(startAmt)
			return profit, path
		}

		if !updated {
			break
		}
	}

	return DecZero, nil
}

// reconstructPathLocal reconstructs the path from parent pointers.
func (ac *ArbitrageContext) reconstructPathLocal(
	localPools []LocalPool,
	parent []arbStep,
	tokens []string,
	tokenIdx map[string]int,
	baseIdx int,
	startAmt math.LegacyDec,
	maxDepth int,
) []arbStep {
	// DFS to find profitable cycles
	type dfsState struct {
		tokenIdx int
		amount   math.LegacyDec
		path     []arbStep
		usedDir  map[int]bool
	}

	var bestPath []arbStep
	bestProfit := DecZero

	// Build adjacency list
	type edge struct {
		poolIdx    int
		sellDenom0 bool
		dstIdx     int
	}
	adj := make(map[int][]edge)

	for poolIdx, pool := range localPools {
		srcIdx0, ok0 := tokenIdx[pool.Denom0]
		srcIdx1, ok1 := tokenIdx[pool.Denom1]
		if !ok0 || !ok1 {
			continue
		}
		adj[srcIdx0] = append(adj[srcIdx0], edge{poolIdx, true, srcIdx1})
		adj[srcIdx1] = append(adj[srcIdx1], edge{poolIdx, false, srcIdx0})
	}

	minProfit := math.LegacyNewDec(int64(maxDepth))

	var dfs func(state dfsState, depth int)
	dfs = func(state dfsState, depth int) {
		if depth > maxDepth {
			return
		}

		// Check if we returned to base with profit
		if depth > 0 && state.tokenIdx == baseIdx {
			profit := state.amount.Sub(startAmt)
			if profit.GT(minProfit) && profit.GT(bestProfit) {
				bestProfit = profit
				bestPath = make([]arbStep, len(state.path))
				copy(bestPath, state.path)
			}
			return
		}

		// Explore edges
		for _, e := range adj[state.tokenIdx] {
			pool := localPools[e.poolIdx]
			dirKey := e.poolIdx*2 + map[bool]int{true: 1, false: 0}[e.sellDenom0]

			if state.usedDir[dirKey] {
				continue
			}

			// Compute output
			var rIn, rOut, fee math.LegacyDec
			if e.sellDenom0 {
				rIn, rOut = pool.Reserve0, pool.Reserve1
				fee = pool.Fee0
			} else {
				rIn, rOut = pool.Reserve1, pool.Reserve0
				fee = pool.Fee1
			}

			if rIn.LT(DecOne) || rOut.LT(DecOne) {
				continue
			}

			// Use truncated amount to match MakeTrade execution
			amtTrunc := state.amount.TruncateInt()
			if !amtTrunc.IsPositive() {
				continue
			}
			amtDec := math.LegacyNewDecFromInt(amtTrunc)

			// Match MakeTrade's exact formula: q = Ceil(k / (rIn + effIn)), out = rOut - q
			gamma := DecOne.Sub(fee)
			effectiveIn := amtDec.Mul(gamma)
			kDec := rIn.Mul(rOut)
			q := kDec.Quo(rIn.Add(effectiveIn)).Ceil()
			out := rOut.Sub(q)

			if out.LT(DecOne) {
				continue
			}

			newUsedDir := make(map[int]bool)
			for k, v := range state.usedDir {
				newUsedDir[k] = v
			}
			newUsedDir[dirKey] = true

			newPath := make([]arbStep, len(state.path)+1)
			copy(newPath, state.path)
			newPath[len(state.path)] = arbStep{
				poolIdx:    e.poolIdx,
				sellDenom0: e.sellDenom0,
				amount:     amtDec, // Use truncated amount
			}

			dfs(dfsState{
				tokenIdx: e.dstIdx,
				amount:   out,
				path:     newPath,
				usedDir:  newUsedDir,
			}, depth+1)
		}
	}

	dfs(dfsState{
		tokenIdx: baseIdx,
		amount:   startAmt,
		path:     nil,
		usedDir:  make(map[int]bool),
	}, 0)

	return bestPath
}

// simulatePathLocal applies a path to local pool state and returns operations.
func (ac *ArbitrageContext) simulatePathLocal(
	localPools []LocalPool,
	path []arbStep,
	logger log.Logger,
) []whaleswapv1.TradeOperation {
	if len(path) == 0 {
		return nil
	}

	ops := make([]whaleswapv1.TradeOperation, 0, len(path))
	currentAmount := path[0].amount

	for i, step := range path {
		if step.poolIdx < 0 || step.poolIdx >= len(localPools) {
			return nil
		}

		pool := &localPools[step.poolIdx]
		amt := currentAmount.TruncateInt()
		if !amt.IsPositive() {
			return nil
		}

		// Use truncated amount for all calculations to match MakeTrade exactly
		amtDec := math.LegacyNewDecFromInt(amt)

		// Build operation
		var swapIn sdk.Coin
		var rIn, rOut, fee *math.LegacyDec

		if step.sellDenom0 {
			swapIn = sdk.NewCoin(pool.Denom0, amt)
			rIn, rOut = &pool.Reserve0, &pool.Reserve1
			fee = &pool.Fee0
		} else {
			swapIn = sdk.NewCoin(pool.Denom1, amt)
			rIn, rOut = &pool.Reserve1, &pool.Reserve0
			fee = &pool.Fee1
		}

		ops = append(ops, whaleswapv1.TradeOperation{
			Op: &whaleswapv1.TradeOperation_Swap{
				Swap: &whaleswapv1.SwapLeg{
					PoolId: pool.PoolID,
					SwapIn: swapIn,
				},
			},
		})

		// Compute output using EXACT same formula as MakeTrade (trade_helpers.go:89-92)
		// MakeTrade uses: q = Ceil(k / (rIn + effIn)), out = rOut - q
		gamma := DecOne.Sub(*fee)
		effectiveIn := amtDec.Mul(gamma)
		kDec := (*rIn).Mul(*rOut)
		q := kDec.Quo((*rIn).Add(effectiveIn)).Ceil()
		outputAmount := (*rOut).Sub(q)

		// Update reserves with truncated input
		*rIn = (*rIn).Add(amtDec)
		*rOut = (*rOut).Sub(outputAmount)

		logger.Debug("LIGHTNING: simulated swap",
			"step", i,
			"pool_id", pool.PoolID,
			"sell", swapIn.Denom,
			"amount", amt.String(),
			"output", outputAmount.TruncateInt().String(),
			"new_r0", pool.Reserve0.TruncateInt().String(),
			"new_r1", pool.Reserve1.TruncateInt().String(),
		)

		if i < len(path)-1 {
			currentAmount = outputAmount
		}
	}

	return ops
}

// simulateMsg executes a MsgMakeTrade on a cached context.
func (ac *ArbitrageContext) simulateMsg(msg *whaleswapv1.MsgMakeTrade) *ArbitrageResult {
	if msg == nil || len(msg.Operations) == 0 {
		return &ArbitrageResult{Success: false, Error: errNoOperations}
	}

	cacheCtx, _ := ac.Ctx.CacheContext()
	resp, err := ac.Keeper.MakeTrade(cacheCtx, msg)
	if err != nil {
		return &ArbitrageResult{
			Success: false,
			Msg:     msg,
			Error:   err,
		}
	}

	profit := resp.TraderOutputs.AmountOf(ac.RefDenom).Sub(resp.TraderInputs.AmountOf(ac.RefDenom))

	return &ArbitrageResult{
		Success:       true,
		TraderInputs:  resp.TraderInputs,
		TraderOutputs: resp.TraderOutputs,
		Profit:        profit,
		Msg:           msg,
		Response:      resp,
	}
}

// =============================================================================
// Helper Functions
// =============================================================================

// GetAffectedDenomsFromPool extracts denoms from a pool.
func GetAffectedDenomsFromPool(pool *whaleswapv1.Pool) []string {
	if pool == nil || len(pool.Coins) != 2 {
		return nil
	}
	return []string{pool.Coins[0].Denom, pool.Coins[1].Denom}
}

// FormatSwaps formats swap operations for logging.
func FormatSwaps(ops []whaleswapv1.TradeOperation) string {
	var parts []string
	for _, op := range ops {
		if swap := op.GetSwap(); swap != nil {
			denomSuffix := swap.SwapIn.Denom
			if idx := strings.LastIndex(denomSuffix, "/"); idx >= 0 {
				denomSuffix = denomSuffix[idx+1:]
			}
			parts = append(parts, fmt.Sprintf("pool%d:%s%s",
				swap.PoolId, swap.SwapIn.Amount.String(), denomSuffix))
		}
	}
	return strings.Join(parts, " → ")
}

// ShouldCheckArbitrage returns true if the message type can affect pool state.
func ShouldCheckArbitrage(msg sdk.Msg) bool {
	switch msg.(type) {
	case *whaleswapv1.MsgCreatePool, *whaleswapv1.MsgAddLiquidity,
		*whaleswapv1.MsgRemoveLiquidity, *whaleswapv1.MsgMakeTrade:
		return true
	default:
		return false
	}
}

// GetPoolDenomsFromMsg extracts denoms affected by a message.
func GetPoolDenomsFromMsg(msg sdk.Msg) []string {
	switch m := msg.(type) {
	case *whaleswapv1.MsgCreatePool:
		if len(m.Coins) >= 2 {
			return []string{m.Coins[0].Denom, m.Coins[1].Denom}
		}
	case *whaleswapv1.MsgAddLiquidity:
		if len(m.Amounts) >= 2 {
			return []string{m.Amounts[0].Denom, m.Amounts[1].Denom}
		}
	case *whaleswapv1.MsgRemoveLiquidity:
		// RemoveLiquidity uses pool_id, caller must look up denoms
		return nil
	case *whaleswapv1.MsgMakeTrade:
		denoms := make(map[string]bool)
		for _, op := range m.Operations {
			if swap := op.GetSwap(); swap != nil {
				denoms[swap.SwapIn.Denom] = true
			}
		}
		result := make([]string, 0, len(denoms))
		for d := range denoms {
			result = append(result, d)
		}
		sort.Strings(result)
		return result
	}
	return nil
}
