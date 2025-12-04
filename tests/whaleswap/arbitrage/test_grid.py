"""
Test grid topology arbitrage scenarios.

Tests an NxN grid of N*N denoms with pools:
- 2*N*(N-1) edge pools connecting adjacent cells (horizontal and vertical)
- 1 diagonal shortcut pool (G1_1 ↔ GN_N) [optional]

Grid layout for N=4:
    G1_1 -- G1_2 -- G1_3 -- G1_4
      |       |       |       |
    G2_1 -- G2_2 -- G2_3 -- G2_4
      |       |       |       |
    G3_1 -- G3_2 -- G3_3 -- G3_4
      |       |       |       |
    G4_1 -- G4_2 -- G4_3 -- G4_4

Plus diagonal: G1_1 ↔ G4_4

When the diagonal pool is imbalanced (via a swap), arbitrage should find
a profitable cycle through the grid edges.

3x2 Grid layout (for independent path testing):
    G1_1 -- G1_2
      |       |
    G2_1 -- G2_2
      |       |
    G3_1 -- G3_2

Middle swap G2_1 → G2_2 creates TWO independent arbitrage paths:
- TOP:    G2_2 ← G1_2 ← G1_1 ← G2_1 (then G2_1 → G2_2)
- BOTTOM: G2_2 ← G3_2 ← G3_1 ← G2_1 (then G2_1 → G2_2)

These paths share only the middle pool, so Nelder-Mead can optimize
the split between them.
"""

import json
import pytest
from deep_parse import deep_parse


def test_grid_NxN_arbitrage_after_diagonal_swap(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test NxN grid arbitrage detection after diagonal swap creates imbalance.

    Creates an NxN grid with balanced pools, then swaps on the diagonal
    (G1_1 → GN_N), creating an imbalance. The arbitrage system should
    find a profitable cycle through the grid.

    Expected cycle: G1_1 → (grid path) → GN_N → G1_1 (via diagonal)

    NOTE: Cycle length = 2*(N-1) + 1 (grid path + diagonal).
    With ArbMaxCycleLen=6, only N<=3 works. N=4 requires cycle length 7.
    """
    # === Grid configuration ===
    # N=3: cycle length = 2*(3-1)+1 = 5 ≤ 6 ✓
    # N=4: cycle length = 2*(4-1)+1 = 7 > 6 ✗
    GRID_SIZE = 3  # Max 3 with ArbMaxCycleLen=6
    POOL_AMOUNT = 100000  # Initial liquidity per pool (larger = less rounding impact)
    SWAP_AMOUNT = 50000  # Amount to swap on diagonal to create imbalance

    # Derived constants
    NUM_DENOMS = GRID_SIZE * GRID_SIZE
    HORIZONTAL_POOLS = GRID_SIZE * (GRID_SIZE - 1)
    VERTICAL_POOLS = (GRID_SIZE - 1) * GRID_SIZE
    EDGE_POOLS = HORIZONTAL_POOLS + VERTICAL_POOLS
    TOTAL_POOLS = EDGE_POOLS + 1  # +1 for diagonal

    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use foo_name as the base for subdenoms
    base_denom = foo_name.replace("/", ".")  # e.g., alice.dys

    extra_code = f'''
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({{
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    }})

def _create_pool(creator, denom_a, amount_a, denom_b, amount_b):
    base, quote = sorted([denom_a, denom_b])
    result = _sudo({{
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": creator,
        "coins": [
            {{"denom": denom_a, "amount": str(amount_a)}},
            {{"denom": denom_b, "amount": str(amount_b)}}
        ],
        "fee_rate": [
            {{"denom": base, "amount": "0.001"}},
            {{"denom": quote, "amount": "0.001"}}
        ],
        "min_initial_collateral_ratio": [
            {{"denom": base, "amount": "1.5"}},
            {{"denom": quote, "amount": "1.5"}}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {{"denom": base, "amount": "1.2"}},
            {{"denom": quote, "amount": "1.2"}}
        ],
        "max_borrow_percent": [
            {{"denom": base, "amount": "0.8"}},
            {{"denom": quote, "amount": "0.8"}}
        ]
    }})
    # Extract pool_id from sudo response
    return result.get("results", [{{}}])[0].get("pool_id", 0)

def demo_grid_arbitrage(alice_addr, gov_addr, base_denom, grid_size, pool_amount, swap_amount):
    """Create NxN grid, swap on diagonal, check for arbitrage."""
    
    # Generate denom names
    def denom_name(row, col):
        return f"{{base_denom}}/G{{row+1}}_{{col+1}}"
    
    subdenoms = [denom_name(r, c) for r in range(grid_size) for c in range(grid_size)]
    
    # Mint all subdenoms at once (need extra for swap)
    params = _query({{"@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"}})
    mint_fee_per = float(params["params"]["mint_fee_per_coin"])
    
    mint_amount = pool_amount * 10
    coins_to_mint = [{{"denom": sd, "amount": str(mint_amount)}} for sd in subdenoms]
    coins_to_mint.sort(key=lambda c: c["denom"])
    total_units = mint_amount * len(coins_to_mint)
    required_fee = int(total_units * mint_fee_per + 0.99999)
    
    _sudo({{
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": alice_addr,
        "amount": coins_to_mint,
        "mint_fee": {{"denom": "udys", "amount": str(required_fee)}},
    }})
    
    pool_ids = []
    
    # Create horizontal pools: (row, col) ↔ (row, col+1)
    for r in range(grid_size):
        for c in range(grid_size - 1):
            pool_id = _create_pool(alice_addr, denom_name(r, c), pool_amount, denom_name(r, c + 1), pool_amount)
            pool_ids.append(pool_id)
    
    # Create vertical pools: (row, col) ↔ (row+1, col)
    for r in range(grid_size - 1):
        for c in range(grid_size):
            pool_id = _create_pool(alice_addr, denom_name(r, c), pool_amount, denom_name(r + 1, c), pool_amount)
            pool_ids.append(pool_id)
    
    # Create diagonal shortcut: G1_1 ↔ GN_N
    d_start, d_end = denom_name(0, 0), denom_name(grid_size - 1, grid_size - 1)
    diagonal_pool_id = _create_pool(alice_addr, d_start, pool_amount, d_end, pool_amount)
    pool_ids.append(diagonal_pool_id)
    
    # Set arbitrage_ref_denom to G1_1 so interceptor can find cycles in this grid
    params_resp = _query({{"@type": "/dysonprotocol.whaleswap.v1.QueryParamsRequest"}})
    current_params = params_resp.get("params", {{}})
    _sudo({{
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": {{
            "pfand_per_offer": current_params.get("pfand_per_offer", {{"denom": "udys", "amount": "1"}}),
            "valuation_fee_pct": current_params.get("valuation_fee_pct", "0"),
            "valuation_period": current_params.get("valuation_period", "3600s"),
            "bid_timeout": current_params.get("bid_timeout", "5s"),
            "minimum_bid_percent_increase": current_params.get("minimum_bid_percent_increase", "0"),
            "max_note_length": current_params.get("max_note_length", 128),
            "block_delay_before_close": current_params.get("block_delay_before_close", 1),
            "block_delay_before_liquidation": current_params.get("block_delay_before_liquidation", 1),
            "arbitrage_mode": "ARBITRAGE_MODE_AUTO",
            "arbitrage_ref_denom": d_start  # G1_1
        }}
    }})
    
    # Get trade count BEFORE swap
    trades_before_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradesRequest",
        "pagination": {{"limit": "1", "reverse": True}}
    }})
    trades_before = trades_before_resp.get("trades", [])
    trade_count_before = int(trades_before[0]["trade_id"]) if len(trades_before) > 0 else 0
    
    # Execute swap on diagonal: G1_1 → GN_N (creates imbalance)
    # After swap: diagonal pool will have more G1_1 and less GN_N
    _sudo({{
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "operations": [{{
            "swap": {{
                "pool_id": str(diagonal_pool_id),
                "swap_in": {{"denom": d_start, "amount": str(swap_amount)}},
                "swap_out": {{"denom": d_end, "amount": "0"}}
            }}
        }}],
        "max_input": [{{"denom": d_start, "amount": str(swap_amount * 2)}}],
        "min_output": []
    }})
    
    # Query diagonal pool state after swap+arbitrage
    diagonal_pool_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": str(diagonal_pool_id)
    }})
    diagonal_pool = diagonal_pool_resp.get("pool", {{}})
    coins = diagonal_pool.get("coins", [])
    reserves = {{c["denom"]: int(c["amount"]) for c in coins}}
    
    # Get alice's trade ID
    alice_trades_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradesByTakerRequest",
        "taker": alice_addr,
        "pagination": {{"limit": "10", "reverse": True}}
    }})
    alice_trades = alice_trades_resp.get("trades", [])
    alice_trade_id = int(alice_trades[0]["trade_id"]) if len(alice_trades) > 0 else 0
    
    # Find interceptor trades (trades after alice's)
    all_trades_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradesRequest",
        "pagination": {{"limit": "100", "reverse": True}}
    }})
    all_trades = all_trades_resp.get("trades", [])
    interceptor_trades = []
    for trade in all_trades:
        trade_id = int(trade.get("trade_id", 0))
        is_after_alice = trade_id > alice_trade_id
        interceptor_trades.append(trade) if is_after_alice else None
    
    # Calculate interceptor profit
    interceptor_trade = interceptor_trades[0] if len(interceptor_trades) > 0 else None
    interceptor_ops = len(interceptor_trade.get("operations", [])) if interceptor_trade else 0
    interceptor_profit = 0
    total_sent = interceptor_trade.get("total_sent", []) if interceptor_trade else []
    total_recv = interceptor_trade.get("total_received", []) if interceptor_trade else []
    sent_map = {{c["denom"]: int(c["amount"]) for c in total_sent}}
    recv_map = {{c["denom"]: int(c["amount"]) for c in total_recv}}
    denoms_traded = set(list(sent_map.keys()) + list(recv_map.keys()))
    for d in denoms_traded:
        interceptor_profit = interceptor_profit + recv_map.get(d, 0) - sent_map.get(d, 0)
    
    # Query arbitrage simulation
    arb_result = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": [d_start, d_end],
        "ref_denom": d_start,
    }})
    
    return {{
        "grid_size": grid_size,
        "subdenoms": subdenoms,
        "pool_count": len(pool_ids),
        "diagonal_pool_id": diagonal_pool_id,
        "d_start": d_start,
        "d_end": d_end,
        "diagonal_reserves": reserves,
        "trade_count_before": trade_count_before,
        "alice_trade_id": alice_trade_id,
        "interceptor_trades_count": len(interceptor_trades),
        "interceptor_ops": interceptor_ops,
        "interceptor_profit": interceptor_profit,
        "arb_found": arb_result.get("found", False),
        "arb_pool_count": arb_result.get("pool_count", 0),
        "arb_profit": arb_result.get("profit", "0"),
        "arb_denoms": arb_result.get("denoms", []),
    }}
'''

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "gov_addr": gov_addr,
            "base_denom": base_denom,
            "grid_size": GRID_SIZE,
            "pool_amount": POOL_AMOUNT,
            "swap_amount": SWAP_AMOUNT,
        }
    )
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_grid_arbitrage",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result}"

    r = result["result"]["result"]

    # === Type assertions ===
    assert isinstance(r, dict), f"Result must be dict: {type(r)}"
    assert isinstance(
        r["subdenoms"], list
    ), f"subdenoms must be list: {type(r['subdenoms'])}"
    assert isinstance(
        r["pool_count"], int
    ), f"pool_count must be int: {type(r['pool_count'])}"
    assert isinstance(
        r["diagonal_pool_id"], (int, str)
    ), f"diagonal_pool_id must be int/str"
    assert isinstance(r["d_start"], str), f"d_start must be str"
    assert isinstance(r["d_end"], str), f"d_end must be str"
    assert isinstance(r["diagonal_reserves"], dict), f"diagonal_reserves must be dict"
    assert isinstance(
        r["interceptor_trades_count"], int
    ), f"interceptor_trades_count must be int"
    assert isinstance(r["interceptor_ops"], int), f"interceptor_ops must be int"
    assert isinstance(r["interceptor_profit"], int), f"interceptor_profit must be int"

    # === Shape assertions ===
    assert (
        r["pool_count"] == TOTAL_POOLS
    ), f"Expected {TOTAL_POOLS} pools ({EDGE_POOLS} edges + 1 diagonal): {r['pool_count']}"
    assert (
        len(r["subdenoms"]) == NUM_DENOMS
    ), f"Expected {NUM_DENOMS} subdenoms: {len(r['subdenoms'])}"
    assert (
        int(r["diagonal_pool_id"]) > 0
    ), f"diagonal_pool_id must be positive: {r['diagonal_pool_id']}"
    assert (
        len(r["diagonal_reserves"]) == 2
    ), f"Pool must have 2 reserves: {r['diagonal_reserves']}"
    assert (
        r["d_start"] in r["diagonal_reserves"]
    ), f"d_start not in reserves: {r['d_start']}"
    assert r["d_end"] in r["diagonal_reserves"], f"d_end not in reserves: {r['d_end']}"

    # === Content assertions: grid structure ===
    d_start = r["d_start"]
    d_end = r["d_end"]
    assert d_start.endswith("/G1_1"), f"d_start should be G1_1: {d_start}"
    assert d_end.endswith(
        f"/G{GRID_SIZE}_{GRID_SIZE}"
    ), f"d_end should be G{GRID_SIZE}_{GRID_SIZE}: {d_end}"

    # === Content assertions: pool imbalance ===
    reserve_start = r["diagonal_reserves"][d_start]
    reserve_end = r["diagonal_reserves"][d_end]
    assert (
        reserve_start > POOL_AMOUNT
    ), f"d_start reserve should exceed {POOL_AMOUNT} after swap: {reserve_start}"
    assert (
        reserve_end < POOL_AMOUNT
    ), f"d_end reserve should be below {POOL_AMOUNT} after swap: {reserve_end}"
    # AMM constant-product: x * y = k. After swap, k is preserved (minus fees).
    initial_k = POOL_AMOUNT * POOL_AMOUNT
    product = reserve_start * reserve_end
    assert product >= initial_k * 0.99, f"AMM product invariant (x*y≥k): {product}"

    # === CRITICAL: Verify auto-arbitrage executed ===
    # After alice's swap, interceptor should execute exactly 1 arbitrage trade
    interceptor_count = r["interceptor_trades_count"]
    interceptor_ops = r["interceptor_ops"]
    interceptor_profit = r["interceptor_profit"]

    assert interceptor_count == 1, (
        f"Expected exactly 1 interceptor trade after alice's swap. "
        f"Got {interceptor_count}. Full result: {r}"
    )

    # Cycle length = 2*(N-1)+1 for NxN grid with diagonal
    # For N=3: 5 ops (4 grid edges + 1 diagonal)
    min_expected_ops = 2 * (GRID_SIZE - 1) + 1
    assert interceptor_ops >= min_expected_ops, (
        f"Arbitrage should use at least {min_expected_ops} ops for {GRID_SIZE}x{GRID_SIZE} grid. "
        f"Got {interceptor_ops}."
    )

    # Arbitrage should capture meaningful profit
    assert interceptor_profit >= 100, (
        f"Arbitrage profit was only {interceptor_profit}. "
        f"Expected >= 100 from exploiting diagonal imbalance."
    )

    # Reserves should show arbitrage partially restored balance
    expected_no_arb_start = POOL_AMOUNT + SWAP_AMOUNT
    expected_no_arb_end = (POOL_AMOUNT * POOL_AMOUNT) // expected_no_arb_start
    assert (
        reserve_start < expected_no_arb_start
    ), f"Arbitrage should reduce G1_1: {reserve_start} < {expected_no_arb_start}"
    assert (
        reserve_end > expected_no_arb_end
    ), f"Arbitrage should increase G{GRID_SIZE}_{GRID_SIZE}: {reserve_end} > {expected_no_arb_end}"

    # The query correctly reports pool/denom counts
    assert (
        r["arb_pool_count"] == TOTAL_POOLS
    ), f"Should see all {TOTAL_POOLS} pools: {r['arb_pool_count']}"
    assert (
        len(r["arb_denoms"]) == NUM_DENOMS
    ), f"Should see all {NUM_DENOMS} denoms: {len(r['arb_denoms'])}"


def test_grid_3x2_independent_paths(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test 3x2 grid with diagonal swap creating TWO independent arbitrage paths.

    Grid layout with diagonal:
        G1_1 -- G1_2
          |  \\    |
        G2_1 -- G2_2
          |       \\|
        G3_1 -- G3_2

    Swap G1_1 → G3_2 on diagonal creates imbalance. Two independent cycles exist:
    - LEFT:  G1_1 → G2_1 → G3_1 → G3_2 → G1_1 (via left column + bottom)
    - RIGHT: G1_1 → G1_2 → G2_2 → G3_2 → G1_1 (via top row + right column)

    These paths share ONLY the diagonal pool (G1_1-G3_2), allowing
    multi-path optimization to split flow between routes.
    """
    # === Grid configuration ===
    ROWS = 3
    COLS = 2
    POOL_AMOUNT = 100000
    SWAP_AMOUNT = 50000  # Swap on diagonal to create imbalance

    # Derived constants
    NUM_DENOMS = ROWS * COLS  # 6 denoms
    HORIZONTAL_POOLS = ROWS * (COLS - 1)  # 3 pools
    VERTICAL_POOLS = (ROWS - 1) * COLS  # 4 pools
    EDGE_POOLS = HORIZONTAL_POOLS + VERTICAL_POOLS  # 7 edge pools
    TOTAL_POOLS = EDGE_POOLS + 1  # +1 for diagonal

    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    base_denom = foo_name.replace("/", ".")

    extra_code = f'''
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({{
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    }})

def _create_pool(creator, denom_a, amount_a, denom_b, amount_b):
    base, quote = sorted([denom_a, denom_b])
    result = _sudo({{
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": creator,
        "coins": [
            {{"denom": denom_a, "amount": str(amount_a)}},
            {{"denom": denom_b, "amount": str(amount_b)}}
        ],
        "fee_rate": [
            {{"denom": base, "amount": "0.001"}},
            {{"denom": quote, "amount": "0.001"}}
        ],
        "min_initial_collateral_ratio": [
            {{"denom": base, "amount": "1.5"}},
            {{"denom": quote, "amount": "1.5"}}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {{"denom": base, "amount": "1.2"}},
            {{"denom": quote, "amount": "1.2"}}
        ],
        "max_borrow_percent": [
            {{"denom": base, "amount": "0.8"}},
            {{"denom": quote, "amount": "0.8"}}
        ]
    }})
    return result.get("results", [{{}}])[0].get("pool_id", 0)

def demo_3x2_grid(alice_addr, gov_addr, base_denom, rows, cols, pool_amount, swap_amount):
    """Create 3x2 grid with diagonal, swap G1_1 → G3_2, check for arbitrage."""
    
    def denom_name(row, col):
        return f"{{base_denom}}/G{{row+1}}_{{col+1}}"
    
    subdenoms = [denom_name(r, c) for r in range(rows) for c in range(cols)]
    
    # Mint all subdenoms
    params = _query({{"@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"}})
    mint_fee_per = float(params["params"]["mint_fee_per_coin"])
    
    mint_amount = pool_amount * 10
    coins_to_mint = [{{"denom": sd, "amount": str(mint_amount)}} for sd in subdenoms]
    coins_to_mint.sort(key=lambda c: c["denom"])
    total_units = mint_amount * len(coins_to_mint)
    required_fee = int(total_units * mint_fee_per + 0.99999)
    
    _sudo({{
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": alice_addr,
        "amount": coins_to_mint,
        "mint_fee": {{"denom": "udys", "amount": str(required_fee)}},
    }})
    
    pool_ids = []
    
    # Create horizontal pools: (row, col) <-> (row, col+1)
    for r in range(rows):
        for c in range(cols - 1):
            pool_id = _create_pool(alice_addr, denom_name(r, c), pool_amount, denom_name(r, c + 1), pool_amount)
            pool_ids.append(pool_id)
    
    # Create vertical pools: (row, col) <-> (row+1, col)
    for r in range(rows - 1):
        for c in range(cols):
            pool_id = _create_pool(alice_addr, denom_name(r, c), pool_amount, denom_name(r + 1, c), pool_amount)
            pool_ids.append(pool_id)
    
    # Create diagonal shortcut: G1_1 ↔ G3_2 (top-left to bottom-right)
    d_start = denom_name(0, 0)           # G1_1
    d_end = denom_name(rows - 1, cols - 1)  # G3_2
    diagonal_pool_id = _create_pool(alice_addr, d_start, pool_amount, d_end, pool_amount)
    pool_ids.append(diagonal_pool_id)
    
    # Set arbitrage_ref_denom to G1_1 for this test
    params_resp = _query({{"@type": "/dysonprotocol.whaleswap.v1.QueryParamsRequest"}})
    current_params = params_resp.get("params", {{}})
    _sudo({{
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": {{
            "pfand_per_offer": current_params.get("pfand_per_offer", {{"denom": "udys", "amount": "1"}}),
            "valuation_fee_pct": current_params.get("valuation_fee_pct", "0"),
            "valuation_period": current_params.get("valuation_period", "3600s"),
            "bid_timeout": current_params.get("bid_timeout", "5s"),
            "minimum_bid_percent_increase": current_params.get("minimum_bid_percent_increase", "0"),
            "max_note_length": current_params.get("max_note_length", 128),
            "block_delay_before_close": current_params.get("block_delay_before_close", 1),
            "block_delay_before_liquidation": current_params.get("block_delay_before_liquidation", 1),
            "arbitrage_mode": "ARBITRAGE_MODE_AUTO",
            "arbitrage_ref_denom": d_start  # G1_1
        }}
    }})
    
    # Verify arbitrage mode is AUTO and ref_denom is set
    params_resp = _query({{"@type": "/dysonprotocol.whaleswap.v1.QueryParamsRequest"}})
    arb_mode = params_resp.get("params", {{}}).get("arbitrage_mode", "")
    
    # Get trade count BEFORE alice's swap
    trades_before_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradesRequest",
        "pagination": {{"limit": "1", "reverse": True}}
    }})
    trades_before = trades_before_resp.get("trades", [])
    trade_count_before = int(trades_before[0]["trade_id"]) if len(trades_before) > 0 else 0
    
    # Swap on diagonal: G1_1 → G3_2
    _sudo({{
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "operations": [{{
            "swap": {{
                "pool_id": str(diagonal_pool_id),
                "swap_in": {{"denom": d_start, "amount": str(swap_amount)}},
                "swap_out": {{"denom": d_end, "amount": "0"}}
            }}
        }}],
        "max_input": [{{"denom": d_start, "amount": str(swap_amount * 2)}}],
        "min_output": []
    }})
    
    # Query diagonal pool reserves after swap+arbitrage
    diagonal_pool_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": str(diagonal_pool_id)
    }})
    diagonal_pool = diagonal_pool_resp.get("pool", {{}})
    coins = diagonal_pool.get("coins", [])
    diagonal_reserves = {{c["denom"]: int(c["amount"]) for c in coins}}
    
    # Get alice's trade ID (she made the initial swap)
    alice_trades_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradesByTakerRequest",
        "taker": alice_addr,
        "pagination": {{"limit": "10", "reverse": True}}
    }})
    alice_trades = alice_trades_resp.get("trades", [])
    alice_trade_id = int(alice_trades[0]["trade_id"]) if len(alice_trades) > 0 else 0
    
    # Query all trades to find trades AFTER alice's trade
    # These should be the interceptor's arbitrage trades
    all_trades_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradesRequest",
        "pagination": {{"limit": "100", "reverse": True}}
    }})
    all_trades = all_trades_resp.get("trades", [])
    
    # Find trades after alice's trade (interceptor trades)
    interceptor_trades = []
    for trade in all_trades:
        trade_id = int(trade.get("trade_id", 0))
        is_after_alice = trade_id > alice_trade_id
        interceptor_trades.append(trade) if is_after_alice else None
    
    # Get the first interceptor trade details
    interceptor_trade = interceptor_trades[0] if len(interceptor_trades) > 0 else None
    interceptor_trader = interceptor_trade.get("trader", "") if interceptor_trade else ""
    interceptor_ops = len(interceptor_trade.get("operations", [])) if interceptor_trade else 0
    
    # Calculate profit from the interceptor trade
    interceptor_profit = 0
    interceptor_pools_used = []
    ops = interceptor_trade.get("operations", []) if interceptor_trade else []
    for op in ops:
        swap = op.get("swap", {{}})
        pool_id = swap.get("pool_id", "")
        interceptor_pools_used.append(pool_id) if pool_id else None
    total_sent = interceptor_trade.get("total_sent", []) if interceptor_trade else []
    total_recv = interceptor_trade.get("total_received", []) if interceptor_trade else []
    sent_map = {{c["denom"]: int(c["amount"]) for c in total_sent}}
    recv_map = {{c["denom"]: int(c["amount"]) for c in total_recv}}
    denoms_traded = set(list(sent_map.keys()) + list(recv_map.keys()))
    for d in denoms_traded:
        interceptor_profit = interceptor_profit + recv_map.get(d, 0) - sent_map.get(d, 0)
    
    # Query arbitrage simulation
    arb_result = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": [d_start, d_end],
        "ref_denom": d_start,
    }})
    
    return {{
        "arbitrage_mode": arb_mode,
        "trade_count_before": trade_count_before,
        "rows": rows,
        "cols": cols,
        "subdenoms": subdenoms,
        "pool_count": len(pool_ids),
        "pool_ids": pool_ids,
        "diagonal_pool_id": diagonal_pool_id,
        "d_start": d_start,
        "d_end": d_end,
        "diagonal_reserves": diagonal_reserves,
        "alice_trade_id": alice_trade_id,
        "interceptor_trades_count": len(interceptor_trades),
        "interceptor_trader": interceptor_trader,
        "interceptor_ops": interceptor_ops,
        "interceptor_profit": interceptor_profit,
        "interceptor_pools_used": interceptor_pools_used,
        "arb_found": arb_result.get("found", False),
        "arb_pool_count": arb_result.get("pool_count", 0),
        "arb_profit": arb_result.get("profit", "0"),
        "arb_denoms": arb_result.get("denoms", []),
        "arb_trader_inputs": arb_result.get("trader_inputs", []),
        "arb_trader_outputs": arb_result.get("trader_outputs", []),
    }}
'''

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "gov_addr": gov_addr,
            "base_denom": base_denom,
            "rows": ROWS,
            "cols": COLS,
            "pool_amount": POOL_AMOUNT,
            "swap_amount": SWAP_AMOUNT,
        }
    )
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_3x2_grid",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert query_result.get("exception") is None, f"Script failed: {query_result}"

    r = result["result"]["result"]

    # === Type assertions ===
    assert isinstance(r, dict), f"Result must be dict: {type(r)}"
    assert (
        r["pool_count"] == TOTAL_POOLS
    ), f"Expected {TOTAL_POOLS} pools: {r['pool_count']}"
    assert (
        len(r["subdenoms"]) == NUM_DENOMS
    ), f"Expected {NUM_DENOMS} subdenoms: {len(r['subdenoms'])}"

    # === Content assertions: diagonal pool imbalance ===
    d_start = r["d_start"]
    d_end = r["d_end"]
    assert d_start.endswith("/G1_1"), f"d_start should be G1_1: {d_start}"
    assert d_end.endswith(
        f"/G{ROWS}_{COLS}"
    ), f"d_end should be G{ROWS}_{COLS}: {d_end}"

    diagonal_reserves = r["diagonal_reserves"]
    reserve_start = diagonal_reserves[d_start]
    reserve_end = diagonal_reserves[d_end]

    # After swap: G1_1 increased, G3_2 decreased
    expected_no_arb_start = POOL_AMOUNT + SWAP_AMOUNT  # 150000
    expected_no_arb_end = (POOL_AMOUNT * POOL_AMOUNT) // expected_no_arb_start  # ~66666

    # Interceptor should have executed arbitrage
    assert (
        reserve_start <= expected_no_arb_start
    ), f"Interceptor should reduce G1_1: {reserve_start} <= {expected_no_arb_start}"
    assert (
        reserve_end >= expected_no_arb_end
    ), f"Interceptor should increase G{ROWS}_{COLS}: {reserve_end} >= {expected_no_arb_end}"

    # === Verify ARBITRAGE_MODE_AUTO is enabled and triggers interceptor ===
    arb_mode = r["arbitrage_mode"]
    trade_count_before = r["trade_count_before"]
    alice_trade_id = r["alice_trade_id"]

    assert (
        arb_mode == "ARBITRAGE_MODE_AUTO"
    ), f"Arbitrage mode should be AUTO, got: {arb_mode}"

    # Alice's trade should be trade_count_before + 1
    # Interceptor's trade should be trade_count_before + 2
    assert (
        alice_trade_id == trade_count_before + 1
    ), f"Alice's trade should be #{trade_count_before + 1}, got #{alice_trade_id}"

    # === CRITICAL: Verify auto-arbitrage executed ===
    # After alice's swap, there should be exactly 1 interceptor trade
    interceptor_count = r["interceptor_trades_count"]
    interceptor_ops = r["interceptor_ops"]
    interceptor_profit = r["interceptor_profit"]
    interceptor_pools = r["interceptor_pools_used"]

    # Exactly 1 interceptor trade (not multiple) - proves auto-arbitrage fired
    assert interceptor_count == 1, (
        f"Expected exactly 1 interceptor trade after alice's swap. "
        f"Got {interceptor_count}."
    )

    # That trade should use at least 4 operations (single best path uses 4 pools)
    # A cycle through the grid: G1_1 → edge pools → G3_2 → diagonal → G1_1
    assert interceptor_ops >= 4, (
        f"Arbitrage trade used only {interceptor_ops} ops. "
        f"Expected >= 4 (at least one circular path). "
        f"Pools used: {interceptor_pools}"
    )

    # That trade should capture profit from the arbitrage opportunity
    assert interceptor_profit >= 1000, (
        f"Arbitrage profit was only {interceptor_profit}. "
        f"Expected >= 1000 from efficient arbitrage trade."
    )

    # Verify arbitrage used pools (should see 8 pools, 6 denoms)
    assert (
        r["arb_pool_count"] == TOTAL_POOLS
    ), f"Should see {TOTAL_POOLS} pools: {r['arb_pool_count']}"
    assert (
        len(r["arb_denoms"]) == NUM_DENOMS
    ), f"Should see {NUM_DENOMS} denoms: {len(r['arb_denoms'])}"
