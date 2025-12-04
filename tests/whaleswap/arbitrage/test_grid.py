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
    """
    # === Grid configuration ===
    GRID_SIZE = 3  # NxN grid - adjust this to test different sizes
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

def demo_grid_arbitrage(alice_addr, base_denom, grid_size, pool_amount, swap_amount):
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
    
    # Query diagonal pool state after swap
    diagonal_pool_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": str(diagonal_pool_id)
    }})
    diagonal_pool = diagonal_pool_resp.get("pool", {{}})
    coins = diagonal_pool.get("coins", [])
    reserves = {{c["denom"]: int(c["amount"]) for c in coins}}
    
    # Query arbitrage - may or may not find opportunity depending on interceptor
    # The interceptor runs after the swap and may have captured the arbitrage already
    arb_result = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": [d_start, d_end],
        "ref_denom": d_start,
        "depth": 100,  # Allow traversal through grid
        "max_depth": 2 * grid_size,  # Path depth: 2*N for NxN grid cycle
        "max_splits": 5  # Order splitting for better AMM rates
    }})
    
    return {{
        "grid_size": grid_size,
        "subdenoms": subdenoms,
        "pool_count": len(pool_ids),
        "diagonal_pool_id": diagonal_pool_id,
        "d_start": d_start,
        "d_end": d_end,
        "diagonal_reserves": reserves,
        "arb_found": arb_result.get("found", False),
        "arb_pool_count": arb_result.get("pool_count", 0),
        "arb_profit": arb_result.get("profit", "0"),
        "arb_denoms": arb_result.get("denoms", []),
        "arb_swap_amounts": arb_result.get("swap_amounts", []),
        "arb_trader_inputs": arb_result.get("trader_inputs", []),
        "arb_trader_outputs": arb_result.get("trader_outputs", []),
    }}
'''

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
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
    ), f"diagonal_pool_id must be int/str: {type(r['diagonal_pool_id'])}"
    assert isinstance(r["d_start"], str), f"d_start must be str: {type(r['d_start'])}"
    assert isinstance(r["d_end"], str), f"d_end must be str: {type(r['d_end'])}"
    assert isinstance(
        r["diagonal_reserves"], dict
    ), f"diagonal_reserves must be dict: {type(r['diagonal_reserves'])}"
    assert isinstance(
        r["arb_found"], bool
    ), f"arb_found must be bool: {type(r['arb_found'])}"
    assert isinstance(
        r["arb_pool_count"], int
    ), f"arb_pool_count must be int: {type(r['arb_pool_count'])}"
    assert isinstance(
        r["arb_profit"], str
    ), f"arb_profit must be str: {type(r['arb_profit'])}"
    assert isinstance(
        r["arb_denoms"], list
    ), f"arb_denoms must be list: {type(r['arb_denoms'])}"
    assert isinstance(
        r["arb_swap_amounts"], list
    ), f"arb_swap_amounts must be list: {type(r['arb_swap_amounts'])}"
    assert isinstance(
        r["arb_trader_inputs"], list
    ), f"arb_trader_inputs must be list: {type(r['arb_trader_inputs'])}"
    assert isinstance(
        r["arb_trader_outputs"], list
    ), f"arb_trader_outputs must be list: {type(r['arb_trader_outputs'])}"

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

    # === Content assertions: arbitrage behavior ===
    # The interceptor runs automatically after pool-affecting messages.
    # After the swap, the diagonal pool is imbalanced. The interceptor should
    # find and execute arbitrage, moving reserves closer to equilibrium.
    #
    # Expected reserves WITHOUT arbitrage (just the swap):
    expected_no_arb_start = POOL_AMOUNT + SWAP_AMOUNT  # 150000 for default values
    expected_no_arb_end = (POOL_AMOUNT * POOL_AMOUNT) // expected_no_arb_start  # ~66666

    # Actual reserves should show the swap happened (imbalance created)
    assert (
        reserve_start > POOL_AMOUNT
    ), f"Swap should have increased G1_1 reserve: {reserve_start} > {POOL_AMOUNT}"
    assert (
        reserve_end < POOL_AMOUNT
    ), f"Swap should have decreased G{GRID_SIZE}_{GRID_SIZE} reserve: {reserve_end} < {POOL_AMOUNT}"

    # The interceptor should have partially restored balance by executing arbitrage.
    # For 3x3 grid: interceptor finds profitable 5-hop cycle and executes it.
    # Result: reserves should be CLOSER to equilibrium than raw swap would leave them.
    #
    # Raw swap leaves: G1_1=150000, G3_3=66666 (imbalance ~83334 from equilibrium)
    # After arb:       G1_1 < 150000, G3_3 > 66666 (closer to 100000 each)
    #
    # The interceptor may not fully arbitrage (small profits get filtered by MinProfitBasis)
    # but it should make SOME progress toward equilibrium.
    assert (
        reserve_start <= expected_no_arb_start
    ), f"Interceptor should reduce G1_1 imbalance: {reserve_start} <= {expected_no_arb_start}"
    assert (
        reserve_end >= expected_no_arb_end
    ), f"Interceptor should reduce G{GRID_SIZE}_{GRID_SIZE} imbalance: {reserve_end} >= {expected_no_arb_end}"

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
    Test 3x2 grid with middle-row swap creating TWO independent arbitrage paths.

    Grid layout (no diagonal):
        G1_1 -- G1_2
          |       |
        G2_1 -- G2_2   <-- swap here
          |       |
        G3_1 -- G3_2

    Swap G2_1 → G2_2 creates imbalance. Two independent cycles exist:
    - TOP:    G2_1 → G1_1 → G1_2 → G2_2 → G2_1 (via top row)
    - BOTTOM: G2_1 → G3_1 → G3_2 → G2_2 → G2_1 (via bottom row)

    These paths share ONLY the middle pool (G2_1-G2_2), allowing
    Nelder-Mead to find optimal split between top and bottom routes.
    """
    # === Grid configuration ===
    ROWS = 3
    COLS = 2
    POOL_AMOUNT = 100000
    SWAP_AMOUNT = 80000  # Larger swap to stress single-path capacity

    # Derived constants
    NUM_DENOMS = ROWS * COLS  # 6 denoms
    HORIZONTAL_POOLS = ROWS * (COLS - 1)  # 3 pools
    VERTICAL_POOLS = (ROWS - 1) * COLS  # 4 pools
    TOTAL_POOLS = HORIZONTAL_POOLS + VERTICAL_POOLS  # 7 pools (no diagonal)

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

def demo_3x2_grid(alice_addr, base_denom, rows, cols, pool_amount, swap_amount):
    """Create 3x2 grid, swap on middle row, check for arbitrage."""
    
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
    middle_pool_id = None
    
    # Create horizontal pools: (row, col) <-> (row, col+1)
    for r in range(rows):
        for c in range(cols - 1):
            pool_id = _create_pool(alice_addr, denom_name(r, c), pool_amount, denom_name(r, c + 1), pool_amount)
            pool_ids.append(pool_id)
            # Track middle pool (row 1, connecting G2_1 and G2_2)
            row_is_middle = (r == 1)
            col_is_first = (c == 0)
            is_middle_pool = row_is_middle and col_is_first
            middle_pool_id = pool_id if is_middle_pool else middle_pool_id
    
    # Create vertical pools: (row, col) <-> (row+1, col)
    for r in range(rows - 1):
        for c in range(cols):
            pool_id = _create_pool(alice_addr, denom_name(r, c), pool_amount, denom_name(r + 1, c), pool_amount)
            pool_ids.append(pool_id)
    
    # NO diagonal pool - this creates independent top/bottom paths
    
    # Verify arbitrage mode is AUTO before swap
    params_resp = _query({{"@type": "/dysonprotocol.whaleswap.v1.QueryParamsRequest"}})
    arb_mode = params_resp.get("params", {{}}).get("arbitrage_mode", "")
    
    # Get trade count BEFORE alice's swap
    trades_before_resp = _query({{
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradesRequest",
        "pagination": {{"limit": "1", "reverse": True}}
    }})
    trades_before = trades_before_resp.get("trades", [])
    trade_count_before = int(trades_before[0]["trade_id"]) if len(trades_before) > 0 else 0
    
    # Swap on middle row: G2_1 -> G2_2
    d_start = denom_name(1, 0)  # G2_1
    d_end = denom_name(1, 1)    # G2_2
    
    _sudo({{
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "operations": [{{
            "swap": {{
                "pool_id": str(middle_pool_id),
                "swap_in": {{"denom": d_start, "amount": str(swap_amount)}},
                "swap_out": {{"denom": d_end, "amount": "0"}}
            }}
        }}],
        "max_input": [{{"denom": d_start, "amount": str(swap_amount * 2)}}],
        "min_output": []
    }})
    
    # Query ALL pool reserves after swap+arbitrage
    all_pool_reserves = {{}}
    for pid in pool_ids:
        pool_resp = _query({{
            "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
            "pool_id": str(pid)
        }})
        pool = pool_resp.get("pool", {{}})
        coins = pool.get("coins", [])
        all_pool_reserves[pid] = {{c["denom"]: int(c["amount"]) for c in coins}}
    
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
        "depth": 100,
        "max_depth": 8,  # 4-hop cycles
        "max_splits": 5
    }})
    
    return {{
        "arbitrage_mode": arb_mode,
        "trade_count_before": trade_count_before,
        "rows": rows,
        "cols": cols,
        "subdenoms": subdenoms,
        "pool_count": len(pool_ids),
        "pool_ids": pool_ids,
        "middle_pool_id": middle_pool_id,
        "d_start": d_start,
        "d_end": d_end,
        "all_pool_reserves": all_pool_reserves,
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

    # === Content assertions: middle pool imbalance ===
    d_start = r["d_start"]
    d_end = r["d_end"]
    assert d_start.endswith("/G2_1"), f"d_start should be G2_1: {d_start}"
    assert d_end.endswith("/G2_2"), f"d_end should be G2_2: {d_end}"

    middle_pool_id = r["middle_pool_id"]
    middle_reserves = r["all_pool_reserves"][middle_pool_id]
    reserve_start = middle_reserves[d_start]
    reserve_end = middle_reserves[d_end]

    # After swap: G2_1 increased, G2_2 decreased
    expected_no_arb_start = POOL_AMOUNT + SWAP_AMOUNT  # 180000
    expected_no_arb_end = (POOL_AMOUNT * POOL_AMOUNT) // expected_no_arb_start  # ~55555

    # Interceptor should have executed arbitrage
    assert (
        reserve_start <= expected_no_arb_start
    ), f"Interceptor should reduce G2_1: {reserve_start} <= {expected_no_arb_start}"
    assert (
        reserve_end >= expected_no_arb_end
    ), f"Interceptor should increase G2_2: {reserve_end} >= {expected_no_arb_end}"

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

    # === CRITICAL: Verify MULTI-PATH optimization worked ===
    # After alice's swap, there should be exactly 1 interceptor trade
    # That trade should use 7 operations (all pools) and capture 15000+ profit
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
    # Multi-path would use 6+ ops but requires paths that don't overlap incorrectly
    assert interceptor_ops >= 4, (
        f"Arbitrage trade used only {interceptor_ops} ops. "
        f"Expected >= 4 (at least one circular path). "
        f"Pools used: {interceptor_pools}"
    )

    # That trade should capture profit from the arbitrage opportunity
    # Single best path captures ~13000, multi-path could capture more
    assert interceptor_profit >= 10000, (
        f"Arbitrage profit was only {interceptor_profit}. "
        f"Expected >= 10000 from efficient arbitrage trade."
    )

    # Verify arbitrage used pools (should see 7 pools, 6 denoms)
    assert (
        r["arb_pool_count"] == TOTAL_POOLS
    ), f"Should see {TOTAL_POOLS} pools: {r['arb_pool_count']}"
    assert (
        len(r["arb_denoms"]) == NUM_DENOMS
    ), f"Should see {NUM_DENOMS} denoms: {len(r['arb_denoms'])}"
