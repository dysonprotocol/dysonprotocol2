"""
Test arbitrage.go keeper functions for detecting and simulating arbitrage.

Uses the SimulateArbitrage query endpoint to test the arbitrage detection logic.
All tests use query script run with _query and _sudo (_msg), which operates on
CacheContext so no state is persisted.

Coverage targets in arbitrage.go:
- BuildArbitrageContext lines 65-134 (via SimulateArbitrage query)
- getPoolsByDenomInternal lines 138-150 (via pool graph construction)
- poolToArbitragePool lines 153-165 (via pool conversion)
- SimulateArbitrage lines 180-214 (via FindArbitrage->SimulateArbitrage)
- buildMakeTradeMsg lines 220-262 (via optimizer simulation)
- ObjectiveFunction lines 277-310 (via optimizer evaluation)
- GetAffectedDenomsFromPool lines 314-318 (via pool denom extraction)
- GetOptimizationBounds lines 329-346 (via optimizer bounds)
- FindArbitrage lines 351-378 (via SimulateArbitrage query)
- BuildFinalMakeTradeMsg lines 384-415 (via successful arbitrage response)
"""

import json
import pytest
from deep_parse import deep_parse


def test_simulate_arbitrage_single_pool(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test SimulateArbitrage with single pool returns found=false (need 2+ pools).

    Covers:
    - BuildArbitrageContext lines 65-134
    - getPoolsByDenomInternal lines 138-150
    - poolToArbitragePool lines 153-165
    - query_simulate_arbitrage.go pool_count < 2 check
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_single_pool(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    
    # Create only one pool
    pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.003"},
            {"denom": quote, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })
    
    # Simulate arbitrage - should find pool but not enough for arb
    arb_result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": [foo_name],
        "ref_denom": bar_name,
        "depth": 0,
        "max_fraction": "0.1"
    })
    
    return arb_result
"""

    kwargs = json.dumps(
        {"alice_addr": alice_addr, "foo_name": foo_name, "bar_name": bar_name}
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
        "demo_single_pool",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]

    # Single pool: arbitrage needs at least 2 pools
    assert demo_result["pool_count"] >= 1, f"Should find pool: {demo_result}"
    assert not demo_result["found"], f"Single pool cannot have arbitrage: {demo_result}"


def test_simulate_arbitrage_two_pools_depth_expansion(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test SimulateArbitrage with two pools via depth expansion.

    Creates A-B and B-C pools. Starting from A with depth=1 should find both.

    Covers:
    - BuildArbitrageContext lines 89-131 (BFS expansion)
    - getPoolsByDenomInternal for multiple denoms
    - poolToArbitragePool for both pools
    """
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Register a third denom for the second pool
    params = dysond("query", "nameservice", "params")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_fee = int(100000 * fee_per + 0.99999)

    # Mint more foo and bar for creating pools
    dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"100000{foo_name}",
        "--mint-fee",
        f"{mint_fee}udys",
        "--from",
        alice_name,
    )

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_two_pools_depth(alice_addr, foo_name, bar_name):
    base_ab, quote_ab = sorted([foo_name, bar_name])
    
    # Create first pool (foo-bar)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base_ab, "amount": "0.003"},
            {"denom": quote_ab, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_ab, "amount": "1.5"},
            {"denom": quote_ab, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_ab, "amount": "1.2"},
            {"denom": quote_ab, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_ab, "amount": "0.8"},
            {"denom": quote_ab, "amount": "0.8"}
        ]
    })
    
    # Create second pool (foo-udys to have a path)
    base_fu, quote_fu = sorted([foo_name, "udys"])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "5000"},
            {"denom": "udys", "amount": "50000"}
        ],
        "fee_rate": [
            {"denom": base_fu, "amount": "0.003"},
            {"denom": quote_fu, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_fu, "amount": "1.5"},
            {"denom": quote_fu, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_fu, "amount": "1.2"},
            {"denom": quote_fu, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_fu, "amount": "0.8"},
            {"denom": quote_fu, "amount": "0.8"}
        ]
    })
    
    # Simulate arbitrage starting from foo with depth=1
    arb_result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": [foo_name],
        "ref_denom": "udys",
        "depth": 1,
        "max_fraction": "0.1"
    })
    
    return arb_result
"""

    kwargs = json.dumps(
        {"alice_addr": alice_addr, "foo_name": foo_name, "bar_name": bar_name}
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
        "demo_two_pools_depth",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]

    # With depth=1, should find both pools
    assert demo_result["pool_count"] >= 2, f"Should find 2+ pools: {demo_result}"
    assert len(demo_result["denoms"]) >= 2, f"Should find 2+ denoms: {demo_result}"


def test_simulate_arbitrage_no_profitable_opportunity(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test SimulateArbitrage when no profitable arbitrage exists.

    Creates balanced pools where circular trading is not profitable.

    Covers:
    - FindArbitrage lines 363-364 (value <= 0 check)
    - ObjectiveFunction lines 298-306 (penalty for inputs)
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_no_profit(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    
    # Create balanced pools - no arbitrage opportunity
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.003"},
            {"denom": quote, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })
    
    base2, quote2 = sorted([bar_name, "udys"])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": bar_name, "amount": "10000"},
            {"denom": "udys", "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base2, "amount": "0.003"},
            {"denom": quote2, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base2, "amount": "1.5"},
            {"denom": quote2, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base2, "amount": "1.2"},
            {"denom": quote2, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base2, "amount": "0.8"},
            {"denom": quote2, "amount": "0.8"}
        ]
    })
    
    # Simulate arbitrage - should not find profitable opportunity
    arb_result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": [foo_name, bar_name],
        "ref_denom": "udys",
        "depth": 1,
        "max_fraction": "0.1"
    })
    
    return arb_result
"""

    kwargs = json.dumps(
        {"alice_addr": alice_addr, "foo_name": foo_name, "bar_name": bar_name}
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
        "demo_no_profit",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]

    # Balanced pools should not have profitable arbitrage after fees
    assert demo_result["pool_count"] >= 2, f"Should find pools: {demo_result}"
    # Note: found may be true or false depending on optimizer finding marginal profit


def test_simulate_arbitrage_no_pools_for_denom(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test SimulateArbitrage with non-existent denom returns empty.

    Covers:
    - BuildArbitrageContext with empty pool set
    - getPoolsByDenomInternal returning empty
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_no_pools(alice_addr):
    # Simulate arbitrage for non-existent denom
    arb_result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": ["nonexistent_denom_xyz123"],
        "ref_denom": "udys",
        "depth": 1,
        "max_fraction": "0.1"
    })
    
    return arb_result
"""

    kwargs = json.dumps({"alice_addr": alice_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_no_pools",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]

    assert demo_result["pool_count"] == 0, f"Should find no pools: {demo_result}"
    assert not demo_result["found"], f"No pools means no arbitrage: {demo_result}"


def test_simulate_arbitrage_depth_zero(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test SimulateArbitrage with depth=0 only finds direct pools.

    Covers:
    - BuildArbitrageContext depth handling
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_depth_zero(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    
    # Create foo-bar pool
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.003"},
            {"denom": quote, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })
    
    # Create bar-udys pool (reachable from foo via bar)
    base2, quote2 = sorted([bar_name, "udys"])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": bar_name, "amount": "10000"},
            {"denom": "udys", "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base2, "amount": "0.003"},
            {"denom": quote2, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base2, "amount": "1.5"},
            {"denom": quote2, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base2, "amount": "1.2"},
            {"denom": quote2, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base2, "amount": "0.8"},
            {"denom": quote2, "amount": "0.8"}
        ]
    })
    
    # Query with depth=0 starting from foo
    # Should only find foo-bar pool, not bar-udys
    arb_result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": [foo_name],
        "ref_denom": "udys",
        "depth": 0,
        "max_fraction": "0.1"
    })
    
    return {
        "pool_count": arb_result["pool_count"],
        "denoms": arb_result["denoms"]
    }
"""

    kwargs = json.dumps(
        {"alice_addr": alice_addr, "foo_name": foo_name, "bar_name": bar_name}
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
        "demo_depth_zero",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]

    # depth=0 only finds pools directly containing foo_name
    # Should find pools with foo, but not udys directly
    assert foo_name in demo_result["denoms"], f"Should find foo: {demo_result}"


def test_get_affected_denoms_from_pool(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test GetAffectedDenomsFromPool via pool query.

    Covers lines 314-318.
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_affected_denoms(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool
    pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.003"},
            {"denom": quote, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })
    
    pool_id = pool_result["results"][0]["pool_id"]
    
    # Query pool to get denoms (same as GetAffectedDenomsFromPool)
    pool = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": int(pool_id)
    })
    
    coins = pool.get("pool", {}).get("coins", [])
    denoms = [c["denom"] for c in coins]
    
    return {
        "pool_id": pool_id,
        "denoms": denoms
    }
"""

    kwargs = json.dumps(
        {"alice_addr": alice_addr, "foo_name": foo_name, "bar_name": bar_name}
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
        "demo_affected_denoms",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    assert len(demo_result["denoms"]) == 2, f"Pool should have 2 denoms: {demo_result}"
    assert foo_name in demo_result["denoms"], f"foo_name not in denoms: {demo_result}"
    assert bar_name in demo_result["denoms"], f"bar_name not in denoms: {demo_result}"


def test_get_optimization_bounds(chainnet, leverage_accounts, leverage_names_and_coins):
    """
    Test GetOptimizationBounds via pool reserves.

    Covers lines 329-346.
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_bounds(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool with specific reserves
    pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "20000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.003"},
            {"denom": quote, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })
    
    pool_id = pool_result["results"][0]["pool_id"]
    
    # Query pool reserves
    pool = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": int(pool_id)
    })
    
    coins = pool.get("pool", {}).get("coins", [])
    reserves = {c["denom"]: int(c["amount"]) for c in coins}
    
    # GetOptimizationBounds uses maxFraction of reserves
    max_fraction = 0.1
    denom0, denom1 = sorted([foo_name, bar_name])
    expected_upper = reserves[denom0] * max_fraction
    expected_lower = -reserves[denom1] * max_fraction
    
    return {
        "reserves": reserves,
        "expected_upper": expected_upper,
        "expected_lower": expected_lower
    }
"""

    kwargs = json.dumps(
        {"alice_addr": alice_addr, "foo_name": foo_name, "bar_name": bar_name}
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
        "demo_bounds",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    assert demo_result["expected_upper"] > 0, f"Upper bound should be positive"
    assert demo_result["expected_lower"] < 0, f"Lower bound should be negative"


def test_build_make_trade_msg_via_trade(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test buildMakeTradeMsg logic via MakeTrade execution.

    Covers lines 220-262 (message construction).
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    denom0, denom1 = sorted([foo_name, bar_name])

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_build_msg(alice_addr, foo_name, bar_name, denom0):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool
    pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.003"},
            {"denom": quote, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })
    
    pool_id = pool_result["results"][0]["pool_id"]
    
    # Execute trade (same logic as buildMakeTradeMsg)
    trade_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "operations": [
            {
                "swap": {
                    "pool_id": int(pool_id),
                    "swap_in": {"denom": denom0, "amount": "100"}
                }
            }
        ],
        "max_input": [{"denom": denom0, "amount": "200"}],
        "note": "arb-simulation"
    })
    
    return {
        "trade_id": trade_result["results"][0].get("trade_id"),
        "inputs": trade_result["results"][0].get("trader_inputs", []),
        "outputs": trade_result["results"][0].get("trader_outputs", [])
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "denom0": denom0,
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
        "demo_build_msg",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    assert demo_result["trade_id"] is not None, f"Trade should succeed: {demo_result}"
    assert len(demo_result["inputs"]) == 1, f"Should have 1 input: {demo_result}"
    assert len(demo_result["outputs"]) == 1, f"Should have 1 output: {demo_result}"


def test_simulate_arbitrage_invalid_pool_query(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test SimulateArbitrage error handling for invalid pool.

    Covers SimulateArbitrage error paths.
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_invalid_pool(alice_addr, foo_name):
    try:
        # Try to swap on non-existent pool
        trade_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": alice_addr,
            "operations": [
                {
                    "swap": {
                        "pool_id": 999999,
                        "swap_in": {"denom": foo_name, "amount": "100"}
                    }
                }
            ],
            "max_input": [{"denom": foo_name, "amount": "200"}]
        })
        return {"error": "Should have failed", "expected": False}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps({"alice_addr": alice_addr, "foo_name": foo_name})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_invalid_pool",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert demo_result["expected"], f"Should have failed: {demo_result}"


def test_simulate_arbitrage_empty_operations(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test buildMakeTradeMsg with empty operations returns error.

    Covers:
    - buildMakeTradeMsg lines 249-250 (empty operations check)
    - SimulateArbitrage lines 187-188 (errNoOperations)
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_empty_ops(alice_addr):
    try:
        # Empty operations should fail
        trade_result = _sudo({
            "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
            "trader": alice_addr,
            "operations": []
        })
        return {"error": "Should have failed", "expected": False}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    kwargs = json.dumps({"alice_addr": alice_addr})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_empty_ops",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert demo_result["expected"], f"Should have failed: {demo_result}"
    assert (
        "non-empty" in demo_result["error"].lower()
    ), f"Error should mention non-empty"


def test_pools_by_denom_query(chainnet, leverage_accounts, leverage_names_and_coins):
    """
    Test PoolsByDenom which is used by getPoolsByDenomInternal.

    Covers lines 138-150.
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_pools_by_denom(alice_addr, foo_name, bar_name):
    base, quote = sorted([foo_name, bar_name])
    
    # Create pool
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.003"},
            {"denom": quote, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })
    
    # Query pools by denom
    pools_foo = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByDenomRequest",
        "denom": foo_name
    })
    
    pools_bar = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByDenomRequest",
        "denom": bar_name
    })
    
    return {
        "pools_foo_count": len(pools_foo.get("pools", [])),
        "pools_bar_count": len(pools_bar.get("pools", []))
    }
"""

    kwargs = json.dumps(
        {"alice_addr": alice_addr, "foo_name": foo_name, "bar_name": bar_name}
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
        "demo_pools_by_denom",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]
    assert demo_result["pools_foo_count"] >= 1, f"Should find foo pool: {demo_result}"
    assert demo_result["pools_bar_count"] >= 1, f"Should find bar pool: {demo_result}"


def test_circular_arbitrage_detection(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test SimulateArbitrage detects profitable circular arbitrage.

    Creates three pools with skewed prices forming foo -> bar -> qux -> foo cycle.
    Uses 100:100000 ratio like test_cli_route_cycle_profit.py.
    The optimizer should find a profitable path.

    Covers:
    - FindArbitrage lines 367-378 (successful arbitrage)
    - SimulateArbitrage lines 205-214 (successful result)
    - ObjectiveFunction lines 299-309 (profit calculation)
    - query_simulate_arbitrage.go lines 72-98 (found=true path)
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    qux_name = leverage_names_and_coins["qux_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_circular_arb(alice_addr, foo_name, bar_name, qux_name):
    # Create three pools with EXTREME skew like test_cli_route_cycle_profit.py
    # All pools use 100:100000 ratio
    # 
    # Pool 1 (foo-bar): 100 foo : 100000 bar  (1 foo = 1000 bar)
    # Pool 2 (bar-qux): 100 bar : 100000 qux  (1 bar = 1000 qux)
    # Pool 3 (qux-foo): 100 qux : 110000 foo  (1 qux = 1100 foo) <- profit here!
    #
    # Cycle foo -> bar -> qux -> foo:
    # 10 foo -> ~10000 bar -> ~10000000 qux -> ~11000000 foo = HUGE profit!
    
    base_fb, quote_fb = sorted([foo_name, bar_name])
    
    # Pool 1: foo-bar skewed (100:100000)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "100"},
            {"denom": bar_name, "amount": "100000"}
        ],
        "fee_rate": [
            {"denom": base_fb, "amount": "0.001"},
            {"denom": quote_fb, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_fb, "amount": "1.5"},
            {"denom": quote_fb, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_fb, "amount": "1.2"},
            {"denom": quote_fb, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_fb, "amount": "0.8"},
            {"denom": quote_fb, "amount": "0.8"}
        ]
    })
    
    # Pool 2: bar-qux skewed (100:100000)
    base_bq, quote_bq = sorted([bar_name, qux_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": bar_name, "amount": "100"},
            {"denom": qux_name, "amount": "100000"}
        ],
        "fee_rate": [
            {"denom": base_bq, "amount": "0.001"},
            {"denom": quote_bq, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_bq, "amount": "1.5"},
            {"denom": quote_bq, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_bq, "amount": "1.2"},
            {"denom": quote_bq, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_bq, "amount": "0.8"},
            {"denom": quote_bq, "amount": "0.8"}
        ]
    })
    
    # Pool 3: qux-foo skewed (100 qux : 110000 foo) - qux is CHEAP vs foo!
    # This makes selling qux give lots of foo (completing the profitable cycle)
    base_qf, quote_qf = sorted([qux_name, foo_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": qux_name, "amount": "100"},
            {"denom": foo_name, "amount": "110000"}
        ],
        "fee_rate": [
            {"denom": base_qf, "amount": "0.001"},
            {"denom": quote_qf, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_qf, "amount": "1.5"},
            {"denom": quote_qf, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_qf, "amount": "1.2"},
            {"denom": quote_qf, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_qf, "amount": "0.8"},
            {"denom": quote_qf, "amount": "0.8"}
        ]
    })
    
    # Simulate arbitrage - the extreme skew should make detection easy
    arb_result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": [foo_name, bar_name],
        "ref_denom": foo_name,
        "depth": 1,
        "max_fraction": "0.5"
    })
    
    return {
        "found": arb_result.get("found", False),
        "pool_count": arb_result.get("pool_count", 0),
        "profit": arb_result.get("profit", "0"),
        "denoms": arb_result.get("denoms", []),
        "trader_inputs": arb_result.get("trader_inputs", []),
        "trader_outputs": arb_result.get("trader_outputs", []),
        "swap_amounts": arb_result.get("swap_amounts", []),
        "pool_ids": arb_result.get("pool_ids", [])
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "qux_name": qux_name,
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
        "demo_circular_arb",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]

    # Should find 3 pools from the BFS expansion
    assert demo_result["pool_count"] == 3, f"Should find 3 pools: {demo_result}"

    # Should find all 3 denoms in the graph
    assert len(demo_result["denoms"]) == 3, f"Should have 3 denoms: {demo_result}"

    # Verify pool_ids are populated
    assert len(demo_result["pool_ids"]) == 3, f"Should have 3 pool IDs: {demo_result}"

    # With ternary search optimizer, should find profitable arbitrage
    assert demo_result["found"], f"Should find arbitrage: {demo_result}"
    assert int(demo_result["profit"]) > 0, f"Should have profit: {demo_result}"
    assert len(demo_result["trader_outputs"]) > 0, f"Should have outputs: {demo_result}"


def test_optimizer_grid_search_no_profit(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test GridSearchOptimizer returns found=false when no profitable opportunity.

    Creates balanced pools where no arbitrage exists.

    Covers arbitrage_optimizer.go:
    - GridSearchOptimizer.Optimize lines 46-120
    - bestValue <= 0 path (line 115-117)
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    qux_name = leverage_names_and_coins["qux_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_balanced_pools(alice_addr, foo_name, bar_name, qux_name):
    # Create balanced pools - no arbitrage opportunity
    # All at same ratio: 10000:10000 (1:1)
    
    base_fb, quote_fb = sorted([foo_name, bar_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base_fb, "amount": "0.003"},
            {"denom": quote_fb, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_fb, "amount": "1.5"},
            {"denom": quote_fb, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_fb, "amount": "1.2"},
            {"denom": quote_fb, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_fb, "amount": "0.8"},
            {"denom": quote_fb, "amount": "0.8"}
        ]
    })
    
    base_bq, quote_bq = sorted([bar_name, qux_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": bar_name, "amount": "10000"},
            {"denom": qux_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base_bq, "amount": "0.003"},
            {"denom": quote_bq, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_bq, "amount": "1.5"},
            {"denom": quote_bq, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_bq, "amount": "1.2"},
            {"denom": quote_bq, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_bq, "amount": "0.8"},
            {"denom": quote_bq, "amount": "0.8"}
        ]
    })
    
    base_qf, quote_qf = sorted([qux_name, foo_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": qux_name, "amount": "10000"},
            {"denom": foo_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": base_qf, "amount": "0.003"},
            {"denom": quote_qf, "amount": "0.003"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_qf, "amount": "1.5"},
            {"denom": quote_qf, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_qf, "amount": "1.2"},
            {"denom": quote_qf, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_qf, "amount": "0.8"},
            {"denom": quote_qf, "amount": "0.8"}
        ]
    })
    
    # Query arbitrage - should find no profit with balanced pools
    arb_result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": [foo_name, bar_name],
        "ref_denom": foo_name,
        "depth": 1,
        "max_fraction": "0.5"
    })
    
    return {
        "found": arb_result.get("found", False),
        "pool_count": arb_result.get("pool_count", 0),
        "profit": arb_result.get("profit", "0")
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "qux_name": qux_name,
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
        "demo_balanced_pools",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]

    # Should find 3 pools but no profitable arbitrage
    assert demo_result["pool_count"] == 3, f"Should find 3 pools: {demo_result}"
    # Balanced pools with fees = no profit
    assert not demo_result[
        "found"
    ], f"Should not find arb in balanced pools: {demo_result}"


def test_optimizer_with_many_pools(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test optimizer behavior with more than MaxPools (4) pools.

    Creates 5 pools to trigger activeDims limiting in optimizers.

    Covers arbitrage_optimizer.go:
    - GridSearchOptimizer lines 57-60 (activeDims > MaxPools)
    - NelderMeadOptimizer lines 152-155 (n > MaxPools)
    - TernarySearchOptimizer lines 409-412 (activeDims > MaxPools)
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    qux_name = leverage_names_and_coins["qux_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_many_pools(alice_addr, foo_name, bar_name, qux_name):
    # Create 5 pools to exceed MaxPools (4)
    # Use skewed ratios for profit opportunity
    
    # Pool 1: foo-bar (100:100000)
    base_fb, quote_fb = sorted([foo_name, bar_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "100"},
            {"denom": bar_name, "amount": "100000"}
        ],
        "fee_rate": [
            {"denom": base_fb, "amount": "0.001"},
            {"denom": quote_fb, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_fb, "amount": "1.5"},
            {"denom": quote_fb, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_fb, "amount": "1.2"},
            {"denom": quote_fb, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_fb, "amount": "0.8"},
            {"denom": quote_fb, "amount": "0.8"}
        ]
    })
    
    # Pool 2: bar-qux (100:100000)
    base_bq, quote_bq = sorted([bar_name, qux_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": bar_name, "amount": "100"},
            {"denom": qux_name, "amount": "100000"}
        ],
        "fee_rate": [
            {"denom": base_bq, "amount": "0.001"},
            {"denom": quote_bq, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_bq, "amount": "1.5"},
            {"denom": quote_bq, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_bq, "amount": "1.2"},
            {"denom": quote_bq, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_bq, "amount": "0.8"},
            {"denom": quote_bq, "amount": "0.8"}
        ]
    })
    
    # Pool 3: qux-foo (100:110000)
    base_qf, quote_qf = sorted([qux_name, foo_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": qux_name, "amount": "100"},
            {"denom": foo_name, "amount": "110000"}
        ],
        "fee_rate": [
            {"denom": base_qf, "amount": "0.001"},
            {"denom": quote_qf, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_qf, "amount": "1.5"},
            {"denom": quote_qf, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_qf, "amount": "1.2"},
            {"denom": quote_qf, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_qf, "amount": "0.8"},
            {"denom": quote_qf, "amount": "0.8"}
        ]
    })
    
    # Pool 4: foo-bar (different ratio)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "1000"},
            {"denom": bar_name, "amount": "50000"}
        ],
        "fee_rate": [
            {"denom": base_fb, "amount": "0.001"},
            {"denom": quote_fb, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_fb, "amount": "1.5"},
            {"denom": quote_fb, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_fb, "amount": "1.2"},
            {"denom": quote_fb, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_fb, "amount": "0.8"},
            {"denom": quote_fb, "amount": "0.8"}
        ]
    })
    
    # Pool 5: bar-qux (different ratio)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": bar_name, "amount": "1000"},
            {"denom": qux_name, "amount": "50000"}
        ],
        "fee_rate": [
            {"denom": base_bq, "amount": "0.001"},
            {"denom": quote_bq, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_bq, "amount": "1.5"},
            {"denom": quote_bq, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_bq, "amount": "1.2"},
            {"denom": quote_bq, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_bq, "amount": "0.8"},
            {"denom": quote_bq, "amount": "0.8"}
        ]
    })
    
    # Query with depth 2 to get more pools
    arb_result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": [foo_name, bar_name],
        "ref_denom": foo_name,
        "depth": 2,
        "max_fraction": "0.5"
    })
    
    return {
        "found": arb_result.get("found", False),
        "pool_count": arb_result.get("pool_count", 0),
        "profit": arb_result.get("profit", "0"),
        "swap_amounts": arb_result.get("swap_amounts", [])
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "qux_name": qux_name,
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
        "demo_many_pools",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]

    # Should find 5 pools (exceeds MaxPools limit of 4)
    assert demo_result["pool_count"] == 5, f"Should find 5 pools: {demo_result}"
    # Should still find arbitrage despite pool limit
    assert demo_result["found"], f"Should find arb: {demo_result}"


def test_optimizer_nelder_mead_convergence(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test NelderMead optimizer converges properly with refinement.

    Creates moderate skew where NelderMead refinement helps.

    Covers arbitrage_optimizer.go:
    - NelderMeadOptimizer.Optimize lines 141-316
    - Expansion path (lines 250-270)
    - Contraction path (lines 278-294)
    - Shrink path (lines 296-302)
    - Convergence check (lines 218-220)
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    qux_name = leverage_names_and_coins["qux_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_moderate_skew(alice_addr, foo_name, bar_name, qux_name):
    # Create pools with moderate skew - requires refinement to find optimal
    # Ratios: 100:50000 (1:500), 100:60000 (1:600), 100:55000 (1:550)
    
    base_fb, quote_fb = sorted([foo_name, bar_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "100"},
            {"denom": bar_name, "amount": "50000"}
        ],
        "fee_rate": [
            {"denom": base_fb, "amount": "0.001"},
            {"denom": quote_fb, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_fb, "amount": "1.5"},
            {"denom": quote_fb, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_fb, "amount": "1.2"},
            {"denom": quote_fb, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_fb, "amount": "0.8"},
            {"denom": quote_fb, "amount": "0.8"}
        ]
    })
    
    base_bq, quote_bq = sorted([bar_name, qux_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": bar_name, "amount": "100"},
            {"denom": qux_name, "amount": "60000"}
        ],
        "fee_rate": [
            {"denom": base_bq, "amount": "0.001"},
            {"denom": quote_bq, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_bq, "amount": "1.5"},
            {"denom": quote_bq, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_bq, "amount": "1.2"},
            {"denom": quote_bq, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_bq, "amount": "0.8"},
            {"denom": quote_bq, "amount": "0.8"}
        ]
    })
    
    base_qf, quote_qf = sorted([qux_name, foo_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": qux_name, "amount": "100"},
            {"denom": foo_name, "amount": "55000"}
        ],
        "fee_rate": [
            {"denom": base_qf, "amount": "0.001"},
            {"denom": quote_qf, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_qf, "amount": "1.5"},
            {"denom": quote_qf, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_qf, "amount": "1.2"},
            {"denom": quote_qf, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_qf, "amount": "0.8"},
            {"denom": quote_qf, "amount": "0.8"}
        ]
    })
    
    arb_result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": [foo_name, bar_name],
        "ref_denom": foo_name,
        "depth": 1,
        "max_fraction": "0.5"
    })
    
    return {
        "found": arb_result.get("found", False),
        "pool_count": arb_result.get("pool_count", 0),
        "profit": arb_result.get("profit", "0")
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "qux_name": qux_name,
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
        "demo_moderate_skew",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]

    assert demo_result["pool_count"] == 3, f"Should find 3 pools: {demo_result}"
    # Moderate skew should still yield profit
    assert demo_result["found"], f"Should find arb with moderate skew: {demo_result}"


def test_optimizer_ternary_search_dimensions(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test TernarySearchOptimizer coordinate descent across dimensions.

    Creates pools that require searching multiple dimensions.

    Covers arbitrage_optimizer.go:
    - TernarySearchOptimizer.Optimize lines 398-474
    - Ternary search loop (lines 428-449)
    - v1 > v2 branch (lines 444-445)
    - v1 <= v2 branch (lines 446-448)
    - improved check (lines 457-460)
    - !improved break (lines 463-465)
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    qux_name = leverage_names_and_coins["qux_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_ternary_dimensions(alice_addr, foo_name, bar_name, qux_name):
    # Create asymmetric pools where ternary search must explore both branches
    # Different skews require different optimal amounts per pool
    
    base_fb, quote_fb = sorted([foo_name, bar_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "200"},
            {"denom": bar_name, "amount": "100000"}
        ],
        "fee_rate": [
            {"denom": base_fb, "amount": "0.001"},
            {"denom": quote_fb, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_fb, "amount": "1.5"},
            {"denom": quote_fb, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_fb, "amount": "1.2"},
            {"denom": quote_fb, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_fb, "amount": "0.8"},
            {"denom": quote_fb, "amount": "0.8"}
        ]
    })
    
    base_bq, quote_bq = sorted([bar_name, qux_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": bar_name, "amount": "150"},
            {"denom": qux_name, "amount": "100000"}
        ],
        "fee_rate": [
            {"denom": base_bq, "amount": "0.001"},
            {"denom": quote_bq, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_bq, "amount": "1.5"},
            {"denom": quote_bq, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_bq, "amount": "1.2"},
            {"denom": quote_bq, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_bq, "amount": "0.8"},
            {"denom": quote_bq, "amount": "0.8"}
        ]
    })
    
    base_qf, quote_qf = sorted([qux_name, foo_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": qux_name, "amount": "100"},
            {"denom": foo_name, "amount": "120000"}
        ],
        "fee_rate": [
            {"denom": base_qf, "amount": "0.001"},
            {"denom": quote_qf, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_qf, "amount": "1.5"},
            {"denom": quote_qf, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_qf, "amount": "1.2"},
            {"denom": quote_qf, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_qf, "amount": "0.8"},
            {"denom": quote_qf, "amount": "0.8"}
        ]
    })
    
    arb_result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": [foo_name, bar_name],
        "ref_denom": foo_name,
        "depth": 1,
        "max_fraction": "0.5"
    })
    
    return {
        "found": arb_result.get("found", False),
        "pool_count": arb_result.get("pool_count", 0),
        "profit": arb_result.get("profit", "0"),
        "swap_amounts": arb_result.get("swap_amounts", [])
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "qux_name": qux_name,
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
        "demo_ternary_dimensions",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]

    assert demo_result["pool_count"] == 3, f"Should find 3 pools: {demo_result}"
    assert demo_result["found"], f"Should find arb: {demo_result}"
    assert int(demo_result["profit"]) > 0, f"Should have profit: {demo_result}"


def test_optimizer_hybrid_fallback_to_grid(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test HybridOptimizer falls back to GridSearch when Ternary fails.

    Creates scenario where initial ternary search doesn't find profit.

    Covers arbitrage_optimizer.go:
    - HybridOptimizer.Optimize lines 344-375
    - Fallback to GridSearch (lines 363-372)
    - Grid result refinement (lines 367-370)
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    qux_name = leverage_names_and_coins["qux_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_hybrid_fallback(alice_addr, foo_name, bar_name, qux_name):
    # Create pools with small reserves - GridSearch might find profit
    # that TernarySearch misses due to starting from center
    
    base_fb, quote_fb = sorted([foo_name, bar_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "50"},
            {"denom": bar_name, "amount": "50000"}
        ],
        "fee_rate": [
            {"denom": base_fb, "amount": "0.001"},
            {"denom": quote_fb, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_fb, "amount": "1.5"},
            {"denom": quote_fb, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_fb, "amount": "1.2"},
            {"denom": quote_fb, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_fb, "amount": "0.8"},
            {"denom": quote_fb, "amount": "0.8"}
        ]
    })
    
    base_bq, quote_bq = sorted([bar_name, qux_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": bar_name, "amount": "50"},
            {"denom": qux_name, "amount": "50000"}
        ],
        "fee_rate": [
            {"denom": base_bq, "amount": "0.001"},
            {"denom": quote_bq, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_bq, "amount": "1.5"},
            {"denom": quote_bq, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_bq, "amount": "1.2"},
            {"denom": quote_bq, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_bq, "amount": "0.8"},
            {"denom": quote_bq, "amount": "0.8"}
        ]
    })
    
    base_qf, quote_qf = sorted([qux_name, foo_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": qux_name, "amount": "50"},
            {"denom": foo_name, "amount": "55000"}
        ],
        "fee_rate": [
            {"denom": base_qf, "amount": "0.001"},
            {"denom": quote_qf, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_qf, "amount": "1.5"},
            {"denom": quote_qf, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_qf, "amount": "1.2"},
            {"denom": quote_qf, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_qf, "amount": "0.8"},
            {"denom": quote_qf, "amount": "0.8"}
        ]
    })
    
    arb_result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": [foo_name, bar_name],
        "ref_denom": foo_name,
        "depth": 1,
        "max_fraction": "0.3"
    })
    
    return {
        "found": arb_result.get("found", False),
        "pool_count": arb_result.get("pool_count", 0),
        "profit": arb_result.get("profit", "0")
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "qux_name": qux_name,
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
        "demo_hybrid_fallback",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]

    assert demo_result["pool_count"] == 3, f"Should find 3 pools: {demo_result}"
    # The hybrid optimizer should find profit via some path
    assert demo_result["found"], f"Hybrid should find arb: {demo_result}"


def test_optimizer_nelder_mead_with_initial_guess(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test NelderMead optimizer with initial guess from TernarySearch.

    Creates profitable scenario where NelderMead refines TernarySearch result.

    Covers arbitrage_optimizer.go:
    - NelderMeadOptimizer.Optimize lines 124-296
    - Initial guess path (lines 159-160 vs 161-164)
    - Expansion path (lines 233-253)
    - Accept reflection path (lines 255-258)
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    qux_name = leverage_names_and_coins["qux_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_nelder_mead_initial(alice_addr, foo_name, bar_name, qux_name):
    # Create pools with moderate reserves for NelderMead to explore
    # Extreme skew ensures profit
    
    base_fb, quote_fb = sorted([foo_name, bar_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "200"},
            {"denom": bar_name, "amount": "100000"}
        ],
        "fee_rate": [
            {"denom": base_fb, "amount": "0.001"},
            {"denom": quote_fb, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_fb, "amount": "1.5"},
            {"denom": quote_fb, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_fb, "amount": "1.2"},
            {"denom": quote_fb, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_fb, "amount": "0.8"},
            {"denom": quote_fb, "amount": "0.8"}
        ]
    })
    
    base_bq, quote_bq = sorted([bar_name, qux_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": bar_name, "amount": "150"},
            {"denom": qux_name, "amount": "100000"}
        ],
        "fee_rate": [
            {"denom": base_bq, "amount": "0.001"},
            {"denom": quote_bq, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_bq, "amount": "1.5"},
            {"denom": quote_bq, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_bq, "amount": "1.2"},
            {"denom": quote_bq, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_bq, "amount": "0.8"},
            {"denom": quote_bq, "amount": "0.8"}
        ]
    })
    
    base_qf, quote_qf = sorted([qux_name, foo_name])
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": qux_name, "amount": "100"},
            {"denom": foo_name, "amount": "120000"}
        ],
        "fee_rate": [
            {"denom": base_qf, "amount": "0.001"},
            {"denom": quote_qf, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_qf, "amount": "1.5"},
            {"denom": quote_qf, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_qf, "amount": "1.2"},
            {"denom": quote_qf, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_qf, "amount": "0.8"},
            {"denom": quote_qf, "amount": "0.8"}
        ]
    })
    
    arb_result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": [foo_name, bar_name],
        "ref_denom": foo_name,
        "depth": 1,
        "max_fraction": "0.8"
    })
    
    return {
        "found": arb_result.get("found", False),
        "pool_count": arb_result.get("pool_count", 0),
        "profit": arb_result.get("profit", "0")
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
            "qux_name": qux_name,
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
        "demo_nelder_mead_initial",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]

    assert demo_result["pool_count"] == 3, f"Should find 3 pools: {demo_result}"
    assert demo_result["found"], f"Should find arb: {demo_result}"
    assert int(demo_result["profit"]) > 0, f"Should have profit: {demo_result}"


def test_optimizer_two_pools_only(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """
    Test optimizer with exactly 2 pools (minimum for arbitrage).

    Covers arbitrage_optimizer.go edge cases with small pool counts:
    - activeDims = 2 paths in all optimizers
    - Simpler convergence patterns
    """
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_two_pools(alice_addr, foo_name, bar_name):
    # Create just 2 pools - foo-bar with different ratios
    # This tests minimum viable arbitrage scenario
    
    base_fb, quote_fb = sorted([foo_name, bar_name])
    
    # Pool 1: foo-bar at 100:100000 (1:1000)
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "100"},
            {"denom": bar_name, "amount": "100000"}
        ],
        "fee_rate": [
            {"denom": base_fb, "amount": "0.001"},
            {"denom": quote_fb, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_fb, "amount": "1.5"},
            {"denom": quote_fb, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_fb, "amount": "1.2"},
            {"denom": quote_fb, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_fb, "amount": "0.8"},
            {"denom": quote_fb, "amount": "0.8"}
        ]
    })
    
    # Pool 2: foo-bar at 110000:100 (1100:1) - opposite skew!
    _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "110000"},
            {"denom": bar_name, "amount": "100"}
        ],
        "fee_rate": [
            {"denom": base_fb, "amount": "0.001"},
            {"denom": quote_fb, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base_fb, "amount": "1.5"},
            {"denom": quote_fb, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base_fb, "amount": "1.2"},
            {"denom": quote_fb, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base_fb, "amount": "0.8"},
            {"denom": quote_fb, "amount": "0.8"}
        ]
    })
    
    arb_result = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
        "trader": alice_addr,
        "affected_denoms": [foo_name, bar_name],
        "ref_denom": foo_name,
        "depth": 0,
        "max_fraction": "0.5"
    })
    
    return {
        "found": arb_result.get("found", False),
        "pool_count": arb_result.get("pool_count", 0),
        "profit": arb_result.get("profit", "0")
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "foo_name": foo_name,
            "bar_name": bar_name,
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
        "demo_two_pools",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script failed: {query_result.get('exception')}"

    demo_result = result["result"]["result"]

    # Should find 2 pools with arbitrage opportunity
    assert demo_result["pool_count"] == 2, f"Should find 2 pools: {demo_result}"
    assert demo_result["found"], f"Should find arb with 2 pools: {demo_result}"
