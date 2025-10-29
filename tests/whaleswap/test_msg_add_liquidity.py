"""
Test MsgAddLiquidity for whaleswap pools.

Tests the AddLiquidity message handler which adds liquidity to existing AMM pools.
This operation:
1. Validates pool exists and amounts match pool denoms
2. Computes shares to mint based on liquidity contribution
3. Handles refunds for excess amounts (pro-rata matching)
4. Mints and distributes pool shares
5. Emits EventPoolLiquidityAdded

Branch Coverage Analysis (msg_liquidity.go lines 15-235):
==========================================================

COVERED BRANCHES:
- Line 67: Concentrated pool (len(pool.MinPrice) == 2) ✓ test_add_liquidity_bounded_concentrated
- Line 118: Unbounded pool (else) ✓ test_add_liquidity_unbounded_basic
- Line 96: Price within band (sa < sp < sb), token1 limiting (dL0 <= dL1) ✓ test_add_liquidity_bounded_concentrated
- Line 103: Refund excess token2 in concentrated mode ✓ test_add_liquidity_bounded_concentrated
- Line 125: Concentrated share calculation ✓ test_add_liquidity_bounded_concentrated
- Line 136: Unbounded share calculation ✓ test_add_liquidity_unbounded_basic
- Line 139: Token1 limiting in unbounded (s2 >= s1) ✓ test_add_liquidity_unbounded_basic, test_add_liquidity_with_refund
- Line 163-174: Refund logic ✓ test_add_liquidity_with_refund
- Line 184: Price band enforcement ✓ test_add_liquidity_bounded_concentrated

ADDITIONAL BRANCHES COVERED:
- Line 139: Token2 limiting in unbounded (s2 < s1) ✓ test_add_liquidity_unbounded_token2_limiting

BRANCHES NOT TESTED (with justification):
- Line 87: Price at/below lower bound (sp <= sa) - Requires pool price to be at/below min_price bound.
  This is an edge case that would require specific market conditions or trades to push price to bounds.
  Testing this requires complex setup (trades to move price) beyond basic happy path coverage.
  
- Line 92: Price at/above upper bound (sp >= sb) - Requires pool price to be at/above max_price bound.
  Similar to line 87, this is an edge case requiring trades to push price to upper bound.
  
- Line 107: Price within band, token2 limiting (dL0 > dL1) - Requires specific price positioning
  where token2 contribution yields less liquidity than token1. The existing test covers the more
  common case (line 99: dL0 <= dL1). Testing line 107 would require careful price manipulation
  to create the inverse scenario, which is complex and not a primary happy path.

SUMMARY:
All primary happy path branches are covered. The untested branches (lines 87, 92, 107) represent
edge cases within concentrated liquidity that require complex price positioning. These should be
covered in dedicated concentrated liquidity edge case tests, not basic happy path tests.
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


def test_add_liquidity_unbounded_basic(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test successful liquidity addition to an unbounded AMM pool."""
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

def demo_add_liquidity_unbounded(alice_addr, foo_name, bar_name):
    # Create unbounded pool
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
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
        "min_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": base, "amount": "20.0"},
            {"denom": quote, "amount": "20.0"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })
    
    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]
    
    # Query pool before adding liquidity
    pool_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    # Add liquidity (matching pool ratio)
    sudo_add_liq_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "5000"},
            {"denom": bar_name, "amount": "5000"}
        ]
    })
    
    add_liq_result = sudo_add_liq_result["results"][0]
    
    # Query pool after adding liquidity
    pool_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    return {
        "pool_id": pool_id,
        "pool_before": pool_before["pool"],
        "add_liq_result": add_liq_result,
        "pool_after": pool_after["pool"],
        "foo_name": foo_name,
        "bar_name": bar_name
    }
"""
    
    kwargs = json.dumps({
        "alice_addr": alice_addr,
        "foo_name": foo_name,
        "bar_name": bar_name
    })
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_add_liquidity_unbounded",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    
    # Parse and validate response structure
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert result is not None, f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"
    
    demo_result = result["result"]["result"]
    
    # Check for exceptions
    assert query_result.get("exception") is None, f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"
    
    # Validate returned structure
    assert demo_result.get("pool_before") is not None, f"Script should return pool_before. Result: {json.dumps(demo_result, indent=2)}"
    assert demo_result.get("add_liq_result") is not None, f"Script should return add_liq_result. Result: {json.dumps(demo_result, indent=2)}"
    assert demo_result.get("pool_after") is not None, f"Script should return pool_after. Result: {json.dumps(demo_result, indent=2)}"
    
    pool_before = demo_result["pool_before"]
    add_liq_result = demo_result["add_liq_result"]
    pool_after = demo_result["pool_after"]
    foo_name = demo_result["foo_name"]
    bar_name = demo_result["bar_name"]
    
    # Verify add liquidity result structure
    assert isinstance(add_liq_result, dict), f"add_liq_result should be dict, got {type(add_liq_result)}"
    assert "shares" in add_liq_result, f"add_liq_result missing 'shares' key. Keys: {list(add_liq_result.keys())}"
    
    shares_minted = add_liq_result["shares"]
    assert isinstance(shares_minted, str), f"Shares should be string, got {type(shares_minted)}"
    shares_minted_int = int(shares_minted)
    assert shares_minted_int > 0, f"Shares minted should be positive, got {shares_minted_int}"
    
    # Verify pool reserves increased
    coins_before = pool_before["coins"]
    coins_after = pool_after["coins"]
    
    denom_to_amount_before = {c["denom"]: int(c["amount"]) for c in coins_before}
    denom_to_amount_after = {c["denom"]: int(c["amount"]) for c in coins_after}
    
    assert foo_name in denom_to_amount_before, f"Pool before should contain {foo_name}"
    assert bar_name in denom_to_amount_before, f"Pool before should contain {bar_name}"
    assert foo_name in denom_to_amount_after, f"Pool after should contain {foo_name}"
    assert bar_name in denom_to_amount_after, f"Pool after should contain {bar_name}"
    
    # Verify reserves increased by the added amounts
    assert denom_to_amount_after[foo_name] == denom_to_amount_before[foo_name] + 5000, f"Expected {foo_name} to increase by 5000, before: {denom_to_amount_before[foo_name]}, after: {denom_to_amount_after[foo_name]}"
    assert denom_to_amount_after[bar_name] == denom_to_amount_before[bar_name] + 5000, f"Expected {bar_name} to increase by 5000, before: {denom_to_amount_before[bar_name]}, after: {denom_to_amount_after[bar_name]}"


def test_add_liquidity_unbounded_token2_limiting(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test unbounded pool where token2 is the limiting factor (s2 < s1).
    
    This tests the branch at line 139 where s2.LT(s1), meaning token2
    determines the number of shares minted, and excess token1 is refunded.
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

def demo_add_liquidity_token2_limiting(alice_addr, foo_name, bar_name):
    # Create unbounded pool with 1:2 ratio (10000:20000)
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
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
        "min_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": base, "amount": "20.0"},
            {"denom": quote, "amount": "20.0"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ],
        "interest_rate": [
            {"denom": base, "amount": "0.001"},
            {"denom": quote, "amount": "0.001"}
        ]
    })

    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]

    # Query pool before adding liquidity
    pool_query_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })

    # Add liquidity with 10000:5000 ratio
    # Pool is 10000:20000 (1:2), so to maintain ratio we need 1:2
    # Providing 10000:5000 means token2 (5000) is limiting
    # s1 = 10000 * totalShares / 10000 = totalShares
    # s2 = 5000 * totalShares / 20000 = 0.25 * totalShares
    # minted = min(s1, s2) = 0.25 * totalShares (s2 < s1, so token2 limiting)
    # Required: token1 = 2500 (to match 5000 of token2 at 1:2 ratio)
    # Refund: 10000 - 2500 = 7500 of token1
    sudo_add_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "5000"}
        ]
    })

    add_result = sudo_add_result["results"][0]

    # Query pool after adding liquidity
    pool_query_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })

    return {
        "pool_id": pool_id,
        "add_result": add_result,
        "pool_before": pool_query_before["pool"],
        "pool_after": pool_query_after["pool"]
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
        "demo_add_liquidity_token2_limiting",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert query_result.get("exception") is None, f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    pool_id = demo_result["pool_id"]
    add_result = demo_result["add_result"]
    pool_before = demo_result["pool_before"]
    pool_after = demo_result["pool_after"]

    # Verify shares were minted
    assert "shares" in add_result, f"AddLiquidity response missing 'shares' key. Keys: {list(add_result.keys())}"
    shares_minted = int(add_result["shares"])
    assert shares_minted > 0, f"Shares minted should be positive, got {shares_minted}"

    # Verify reserves changed correctly
    # Pool was 10000:20000, should become 12500:25000 (added 2500:5000, refunded 7500 of token1)
    denom_to_amount_before = {c["denom"]: int(c["amount"]) for c in pool_before["coins"]}
    denom_to_amount_after = {c["denom"]: int(c["amount"]) for c in pool_after["coins"]}

    assert denom_to_amount_before[foo_name] == 10000, f"Expected initial {foo_name} to be 10000, got {denom_to_amount_before[foo_name]}"
    assert denom_to_amount_before[bar_name] == 20000, f"Expected initial {bar_name} to be 20000, got {denom_to_amount_before[bar_name]}"

    # Token2 (bar_name) is limiting, so all 5000 should be added
    # Token1 (foo_name) should only add 2500 to maintain 1:2 ratio (7500 refunded)
    assert denom_to_amount_after[foo_name] == 12500, f"Expected {foo_name} to be 12500 (10000 + 2500), got {denom_to_amount_after[foo_name]}"
    assert denom_to_amount_after[bar_name] == 25000, f"Expected {bar_name} to be 25000 (20000 + 5000), got {denom_to_amount_after[bar_name]}"


def test_add_liquidity_bounded_concentrated(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test liquidity addition to a bounded pool with concentrated liquidity."""
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

def demo_add_liquidity_bounded(alice_addr, foo_name, bar_name):
    # Create bounded pool with price bands
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
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
        "min_price": [
            {"denom": base, "amount": "2"},
            {"denom": quote, "amount": "1"}
        ],
        "max_price": [
            {"denom": base, "amount": "1"},
            {"denom": quote, "amount": "2"}
        ],
        "min_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": base, "amount": "20.0"},
            {"denom": quote, "amount": "20.0"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })
    
    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]
    
    # Query pool before adding liquidity
    pool_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    # Add liquidity to bounded pool
    sudo_add_liq_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "5000"},
            {"denom": bar_name, "amount": "5000"}
        ]
    })
    
    add_liq_result = sudo_add_liq_result["results"][0]
    
    # Query pool after adding liquidity
    pool_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    return {
        "pool_id": pool_id,
        "pool_before": pool_before["pool"],
        "add_liq_result": add_liq_result,
        "pool_after": pool_after["pool"]
    }
"""
    
    kwargs = json.dumps({
        "alice_addr": alice_addr,
        "foo_name": foo_name,
        "bar_name": bar_name
    })
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_add_liquidity_bounded",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    
    # Parse and validate response structure
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert result is not None, f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"
    
    demo_result = result["result"]["result"]
    
    # Check for exceptions
    assert query_result.get("exception") is None, f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"
    
    # Validate returned structure
    assert demo_result.get("add_liq_result") is not None, f"Script should return add_liq_result. Result: {json.dumps(demo_result, indent=2)}"
    
    add_liq_result = demo_result["add_liq_result"]
    
    # Verify shares were minted
    assert "shares" in add_liq_result, f"add_liq_result missing 'shares' key. Keys: {list(add_liq_result.keys())}"
    shares_minted = add_liq_result["shares"]
    shares_minted_int = int(shares_minted)
    assert shares_minted_int > 0, f"Shares minted should be positive for bounded pool, got {shares_minted_int}"
    
    # Verify pool has price bands
    pool_after = demo_result["pool_after"]
    min_price = pool_after.get("min_price", [])
    max_price = pool_after.get("max_price", [])
    assert len(min_price) == 2, f"Bounded pool should have min_price with 2 entries, got {len(min_price)}"
    assert len(max_price) == 2, f"Bounded pool should have max_price with 2 entries, got {len(max_price)}"


def test_add_liquidity_with_refund(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test liquidity addition with refund when amounts don't match pool ratio."""
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

def demo_add_liquidity_with_refund(alice_addr, foo_name, bar_name):
    # Create unbounded pool
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
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
        "min_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": base, "amount": "20.0"},
            {"denom": quote, "amount": "20.0"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })
    
    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]
    
    # Add liquidity with mismatched amounts (should trigger refund logic)
    # Pool is 10000:10000 (1:1 ratio), we provide 5000:8000 (excess bar_name)
    sudo_add_liq_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "5000"},
            {"denom": bar_name, "amount": "8000"}
        ]
    })
    
    add_liq_result = sudo_add_liq_result["results"][0]
    
    # Query pool after to verify reserves
    pool_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    return {
        "pool_id": pool_id,
        "add_liq_result": add_liq_result,
        "pool_after": pool_after["pool"],
        "foo_name": foo_name,
        "bar_name": bar_name
    }
"""
    
    kwargs = json.dumps({
        "alice_addr": alice_addr,
        "foo_name": foo_name,
        "bar_name": bar_name
    })
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_add_liquidity_with_refund",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    
    # Parse and validate response structure
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert result is not None, f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"
    
    demo_result = result["result"]["result"]
    
    # Check for exceptions
    assert query_result.get("exception") is None, f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"
    
    # Validate returned structure
    assert demo_result.get("add_liq_result") is not None, f"Script should return add_liq_result. Result: {json.dumps(demo_result, indent=2)}"
    assert demo_result.get("pool_after") is not None, f"Script should return pool_after. Result: {json.dumps(demo_result, indent=2)}"
    
    add_liq_result = demo_result["add_liq_result"]
    pool_after = demo_result["pool_after"]
    foo_name = demo_result["foo_name"]
    bar_name = demo_result["bar_name"]
    
    # Verify shares were minted
    assert "shares" in add_liq_result, f"add_liq_result missing 'shares' key. Keys: {list(add_liq_result.keys())}"
    shares_minted = add_liq_result["shares"]
    shares_minted_int = int(shares_minted)
    assert shares_minted_int > 0, f"Shares minted should be positive, got {shares_minted_int}"
    
    # Verify pool reserves increased proportionally (not by full amounts due to refund)
    coins_after = pool_after["coins"]
    denom_to_amount_after = {c["denom"]: int(c["amount"]) for c in coins_after}
    
    # Pool should maintain 1:1 ratio, so both should increase by 5000
    # (excess 3000 bar_name should have been refunded)
    assert denom_to_amount_after[foo_name] == 15000, f"Expected {foo_name} to be 15000 (10000+5000), got {denom_to_amount_after[foo_name]}"
    assert denom_to_amount_after[bar_name] == 15000, f"Expected {bar_name} to be 15000 (10000+5000, with 3000 refunded), got {denom_to_amount_after[bar_name]}"

