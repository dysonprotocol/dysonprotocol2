"""
Test AddLiquidity concentrated pool branches using single-block and hybrid approaches.

These tests cover all AddLiquidity branches for concentrated liquidity pools (msg_liquidity.go lines 87-116):

1. Lines 87-91: sp <= sa (price at/below lower bound) - NEAR-BOUNDARY TEST
   - Exact boundary unreachable via swaps (pool validation prevents exceeding band)
   - Tests near-boundary behavior where token1 (base) dominates contribution
   - Uses hybrid approach: tx script exec for setup + query script run for test
    
2. Lines 92-97: sp >= sb (price at/above upper bound) - NEAR-BOUNDARY TEST
   - Exact boundary unreachable via swaps (pool validation prevents exceeding band)
   - Tests near-boundary behavior where token2 (quote) dominates contribution
   - Uses hybrid approach: tx script exec for setup + query script run for test
    
3. Lines 99-106: dL0 <= dL1 (price within band, token1 limiting) - SINGLE-BLOCK ✅
   - Both tokens contribute, token2 (quote) partially refunded
   - dL = dL0 = dx * sp * sb / (sb - sp)

4. Lines 107-115: dL0 > dL1 (price within band, token2 limiting) - SINGLE-BLOCK ✅
   - Both tokens contribute, token1 (base) partially refunded
   - dL = dL1 = dy / (sp - sa)

Strategy: 
- Pure single-block tests for within-band cases (most complex refund logic)
- Hybrid tests for near-boundary behavior (demonstrate token contribution skew)
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


def test_add_liquidity_concentrated_near_lower_bound_hybrid(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AddLiquidity when price is near lower bound - TX SCRIPT EXEC + QUERY.
    
    Tests behavior approaching line 87: if sp.LTE(sa)
    Expected behavior near lower bound:
    - Token1 (base) contributes most of the liquidity
    - Token2 (quote) contributes minimally or is mostly refunded
    
    Note: Exact boundary (sp <= sa) cannot be reached via swaps as pool validation
    prevents price from moving outside [min_price, max_price]. This tests near-boundary behavior.
    
    Approach:
    1. Use tx script exec to create pool and execute swap close to lower bound
    2. Use query script run to test AddLiquidity at the resulting price (single-block test)
    """
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_name = leverage_accounts["bob"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    
    base, quote = sorted([foo_name, bar_name])
    
    # Step 1: Use tx script exec to create pool and push price to lower bound
    setup_code = """
from dys import _msg, get_executor_address

def setup_pool_at_lower_bound(creator, base, quote):
    # Create bounded pool with price bands (min_price = 0.5, max_price = 2.0)
    pool_result = _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": creator,
        "coins": [
            {"denom": base, "amount": "10000"},
            {"denom": quote, "amount": "10000"}
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
    
    pool_id = pool_result["pool_id"]
    
    # Execute swap to push price DOWN near lower bound (sell base)
    # Moderate swap to approach min_price = 0.5 while staying within band
    _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgPoolSwap",
        "trader": creator,
        "legs": [{"pool_id": str(pool_id), "swap_in": {"denom": base, "amount": "3000"}}],
        "max_input": [{"denom": base, "amount": "3000"}],
        "min_output": []
    })
    
    return pool_id
"""
    
    setup_kwargs = json.dumps({"creator": alice_addr, "base": base, "quote": quote})
    setup_tx = dysond(
        "tx", "script", "exec",
        "--script-address", alice_addr,
        "--function-name", "setup_pool_at_lower_bound",
        "--kwargs", setup_kwargs,
        "--extra-code", setup_code,
        "--gas", "5000000",
        "--from", alice_name,
    )
    assert setup_tx.get("code", 1) == 0, f"Setup failed: {json.dumps(setup_tx, indent=2)}"
    
    # Query to find the newly created pool
    pools_query = dysond("query", "whaleswap", "pools")
    pools = pools_query.get("pools", [])
    assert len(pools) > 0, "No pools found after creation"
    pool_id = max(int(p["pool_id"]) for p in pools)
    
    # Verify price has moved toward lower bound
    pool_query = dysond("query", "whaleswap", "pool", "--pool-id", str(pool_id))
    pool = pool_query["pool"]
    coins = pool["coins"]
    denom_to_amount = {c["denom"]: int(c["amount"]) for c in coins}
    
    base_reserve = denom_to_amount[base]
    quote_reserve = denom_to_amount[quote]
    
    # Price should be lower after selling base (base reserve increased, quote decreased)
    assert base_reserve > 10000, f"Base reserve should increase after selling base, got {base_reserve}"
    assert quote_reserve < 10000, f"Quote reserve should decrease after buying quote, got {quote_reserve}"
    
    # Step 3: Use query script run to test AddLiquidity at this price point
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]
    
    test_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_add_liquidity_at_bound(alice_addr, pool_id, base, quote):
    # Query pool before
    pool_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    # Add liquidity with both tokens
    # At lower bound: only base should contribute, quote fully refunded
    sudo_add_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": base, "amount": "1000"},
            {"denom": quote, "amount": "1000"}
        ]
    })
    
    add_result = sudo_add_result["results"][0]
    
    # Query pool after
    pool_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    return {
        "pool_before": pool_before["pool"],
        "add_result": add_result,
        "pool_after": pool_after["pool"]
    }
"""
    
    test_kwargs = json.dumps({
        "alice_addr": alice_addr,
        "pool_id": pool_id,
        "base": base,
        "quote": quote
    })
    
    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_add_liquidity_at_bound",
        "--kwargs", test_kwargs,
        "--extra-code", test_code,
    )
    
    # Parse and validate
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}. Full: {json.dumps(query_result, indent=2)}"
    assert query_result.get("exception") is None, f"Script execution failed: {json.dumps(query_result.get('exception'), indent=2)}"
    
    test_result = result["result"]["result"]
    assert isinstance(test_result, dict), f"test_result should be dict, got {type(test_result)}. Content: {json.dumps(test_result, indent=2)}"
    pool_before = test_result["pool_before"]
    add_result = test_result["add_result"]
    pool_after = test_result["pool_after"]
    
    # Verify shares were minted
    assert "shares" in add_result, f"add_result missing 'shares' key. Keys: {list(add_result.keys())}"
    shares_minted = int(add_result["shares"])
    assert shares_minted > 0, f"Shares should be positive, got {shares_minted}"
    
    # Verify reserve changes: base should dominate, quote minimal near lower bound
    coins_before = {c["denom"]: int(c["amount"]) for c in pool_before["coins"]}
    coins_after = {c["denom"]: int(c["amount"]) for c in pool_after["coins"]}
    
    base_added = coins_after[base] - coins_before[base]
    quote_added = coins_after[quote] - coins_before[quote]
    
    assert base_added > 0, f"Base should contribute near lower bound, got {base_added}"
    assert base_added <= 1000, f"Base added should be <= 1000, got {base_added}"
    # Near lower bound: base dominates (contributes significantly more than quote)
    assert base_added > quote_added * 3, f"Base ({base_added}) should dominate over quote ({quote_added}) near lower bound"


def test_add_liquidity_concentrated_near_upper_bound_hybrid(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AddLiquidity when price is near upper bound - TX SCRIPT EXEC + QUERY.
    
    Tests behavior approaching line 92: else if sp.GTE(sb)
    Expected behavior near upper bound:
    - Token2 (quote) contributes most of the liquidity
    - Token1 (base) contributes minimally or is mostly refunded
    
    Note: Exact boundary (sp >= sb) cannot be reached via swaps as pool validation
    prevents price from moving outside [min_price, max_price]. This tests near-boundary behavior.
    
    Approach:
    1. Use tx script exec to create pool and execute swap close to upper bound
    2. Use query script run to test AddLiquidity at the resulting price (single-block test)
    """
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    alice_addr = leverage_accounts["alice"]["addr"]
    bob_name = leverage_accounts["bob"]["name"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    
    base, quote = sorted([foo_name, bar_name])
    
    # Step 1: Use tx script exec to create pool and push price to upper bound
    setup_code = """
from dys import _msg, get_executor_address

def setup_pool_at_upper_bound(creator, base, quote):
    # Create bounded pool with price bands (min_price = 0.5, max_price = 2.0)
    pool_result = _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": creator,
        "coins": [
            {"denom": base, "amount": "10000"},
            {"denom": quote, "amount": "10000"}
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
    
    pool_id = pool_result["pool_id"]
    
    # Execute swap to push price UP near upper bound (sell quote)
    # Moderate swap to approach max_price = 2.0 while staying within band
    _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgPoolSwap",
        "trader": creator,
        "legs": [{"pool_id": str(pool_id), "swap_in": {"denom": quote, "amount": "3000"}}],
        "max_input": [{"denom": quote, "amount": "3000"}],
        "min_output": []
    })
    
    return pool_id
"""
    
    setup_kwargs = json.dumps({"creator": alice_addr, "base": base, "quote": quote})
    setup_tx = dysond(
        "tx", "script", "exec",
        "--script-address", alice_addr,
        "--function-name", "setup_pool_at_upper_bound",
        "--kwargs", setup_kwargs,
        "--extra-code", setup_code,
        "--gas", "5000000",
        "--from", alice_name,
    )
    assert setup_tx.get("code", 1) == 0, f"Setup failed: {json.dumps(setup_tx, indent=2)}"
    
    # Query to find the newly created pool
    pools_query = dysond("query", "whaleswap", "pools")
    pools = pools_query.get("pools", [])
    assert len(pools) > 0, "No pools found after creation"
    pool_id = max(int(p["pool_id"]) for p in pools)
    
    # Verify price has moved toward upper bound
    pool_query = dysond("query", "whaleswap", "pool", "--pool-id", str(pool_id))
    pool = pool_query["pool"]
    coins = pool["coins"]
    denom_to_amount = {c["denom"]: int(c["amount"]) for c in coins}
    
    base_reserve = denom_to_amount[base]
    quote_reserve = denom_to_amount[quote]
    
    # Price should be higher after selling quote (quote reserve increased, base decreased)
    assert quote_reserve > 10000, f"Quote reserve should increase after selling quote, got {quote_reserve}"
    assert base_reserve < 10000, f"Base reserve should decrease after buying base, got {base_reserve}"
    
    # Step 3: Use query script run to test AddLiquidity at this price point
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]
    
    test_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_add_liquidity_at_bound(alice_addr, pool_id, base, quote):
    # Query pool before
    pool_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    # Add liquidity with both tokens
    # At upper bound: only quote should contribute, base fully refunded
    sudo_add_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": base, "amount": "1000"},
            {"denom": quote, "amount": "1000"}
        ]
    })
    
    add_result = sudo_add_result["results"][0]
    
    # Query pool after
    pool_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    return {
        "pool_before": pool_before["pool"],
        "add_result": add_result,
        "pool_after": pool_after["pool"]
    }
"""
    
    test_kwargs = json.dumps({
        "alice_addr": alice_addr,
        "pool_id": pool_id,
        "base": base,
        "quote": quote
    })
    
    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_add_liquidity_at_bound",
        "--kwargs", test_kwargs,
        "--extra-code", test_code,
    )
    
    # Parse and validate
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert query_result.get("exception") is None, f"Script execution failed: {json.dumps(query_result.get('exception'), indent=2)}"
    
    test_result = result["result"]["result"]
    pool_before = test_result["pool_before"]
    add_result = test_result["add_result"]
    pool_after = test_result["pool_after"]
    
    # Verify shares were minted
    assert "shares" in add_result, f"add_result missing 'shares' key"
    shares_minted = int(add_result["shares"])
    assert shares_minted > 0, f"Shares should be positive, got {shares_minted}"
    
    # Verify reserve changes: quote should dominate, base minimal near upper bound
    coins_before = {c["denom"]: int(c["amount"]) for c in pool_before["coins"]}
    coins_after = {c["denom"]: int(c["amount"]) for c in pool_after["coins"]}
    
    base_added = coins_after[base] - coins_before[base]
    quote_added = coins_after[quote] - coins_before[quote]
    
    assert quote_added > 0, f"Quote should contribute near upper bound, got {quote_added}"
    assert quote_added <= 1000, f"Quote added should be <= 1000, got {quote_added}"
    # Near upper bound: quote dominates (contributes significantly more than base)
    assert quote_added > base_added * 3, f"Quote ({quote_added}) should dominate over base ({base_added}) near upper bound"


def test_add_liquidity_concentrated_within_band_token1_limiting(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AddLiquidity when price is within band and token1 is limiting.
    
    Tests line 99: if dL0.LTE(dL1) branch where dL0 is smaller (token1 limiting)
    Expected behavior:
    - Both tokens contribute, but token1 determines liquidity amount
    - Excess token2 (quote) is refunded
    - dL = dL0 = dx * sp * sb / (sb - sp)
    - Required dy = dL * (sp - sa)
    - If add2 > reqDy, refund2 = add2 - reqDy (line 103-105)
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

def demo_add_liquidity_token1_limiting(alice_addr, foo_name, bar_name):
    # Create bounded pool with price mid-band
    # Band: min_price = 0.2, max_price = 5.0 (wide band)
    # Set initial reserves: 10000 base, 10000 quote -> price = 1.0 (within band)
    
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
            {"denom": base, "amount": "5"},      # 5 base = 1 quote
            {"denom": quote, "amount": "1"}      # ratio = 1/5 = 0.2
        ],
        "max_price": [
            {"denom": base, "amount": "1"},      # 1 base = 5 quote
            {"denom": quote, "amount": "5"}      # ratio = 5/1 = 5.0
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
    
    # Add liquidity with much more quote than base
    # This should trigger dL0 < dL1 (token1/base limiting)
    # Provide 500 base but 5000 quote
    sudo_add_liq_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "500"},
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
        "demo_add_liquidity_token1_limiting",
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
    
    # Verify shares were minted
    assert "shares" in add_liq_result, f"add_liq_result missing 'shares' key. Keys: {list(add_liq_result.keys())}"
    shares_minted = int(add_liq_result["shares"])
    assert shares_minted > 0, f"Shares minted should be positive, got {shares_minted}"
    
    # Verify reserve changes: both tokens should be added, but not all of quote
    coins_before = pool_before["coins"]
    coins_after = pool_after["coins"]
    
    denom_to_amount_before = {c["denom"]: int(c["amount"]) for c in coins_before}
    denom_to_amount_after = {c["denom"]: int(c["amount"]) for c in coins_after}
    
    # Determine which is base and quote based on lexicographic order
    base_denom, quote_denom = sorted([foo_name, bar_name])
    
    # Within band, token1 limiting (dL0 <= dL1): both contribute, but quote is partially refunded
    base_added = denom_to_amount_after[base_denom] - denom_to_amount_before[base_denom]
    quote_added = denom_to_amount_after[quote_denom] - denom_to_amount_before[quote_denom]
    
    assert base_added > 0, f"Base should have been added (within band), got {base_added}"
    assert quote_added > 0, f"Quote should have been added (within band), got {quote_added}"
    
    # Key test: quote should be partially refunded (not all 5000 used)
    # Because base (500) is limiting, excess quote is refunded
    assert quote_added < 5000, f"Quote should be partially refunded (dL0 <= dL1), added {quote_added} < 5000"
    
    # Base should be mostly/fully used (it's the limiting factor)
    assert base_added <= 500, f"Base added should be <= 500, got {base_added}"
    
    # The critical verification: quote refund occurred (line 103-105)
    quote_refunded = 5000 - quote_added
    assert quote_refunded > 0, f"Quote should have been refunded (dL0 <= dL1), refund: {quote_refunded}"


def test_add_liquidity_concentrated_within_band_token2_limiting(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Test AddLiquidity when price is within band and token2 is limiting.
    
    Tests line 107: else branch where dL0 > dL1 (dL1 is smaller, so token2 limiting)
    Expected behavior:
    - Both tokens contribute, but token2 determines liquidity amount
    - Excess token1 (base) is refunded
    - dL = dL1 = dy / (sp - sa)
    - Required dx = dL * (sb - sp) / (sp * sb)
    - If add1 > reqDx, refund1 = add1 - reqDx (line 111-113)
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
    # Create bounded pool with price mid-band
    # Band: min_price = 0.2, max_price = 5.0 (wide band)
    # Set initial reserves: 10000 base, 10000 quote -> price = 1.0 (within band)
    
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
            {"denom": base, "amount": "5"},      # 5 base = 1 quote
            {"denom": quote, "amount": "1"}      # ratio = 1/5 = 0.2
        ],
        "max_price": [
            {"denom": base, "amount": "1"},      # 1 base = 5 quote
            {"denom": quote, "amount": "5"}      # ratio = 5/1 = 5.0
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
    
    # Add liquidity with MUCH more base than quote
    # This should trigger dL0 > dL1 (token2/quote limiting)
    # Provide 5000 base but only 500 quote
    # The small quote amount will limit liquidity, causing excess base refund
    sudo_add_liq_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "5000"},
            {"denom": bar_name, "amount": "500"}
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
        "demo_add_liquidity_token2_limiting",
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
    
    # Verify shares were minted
    assert "shares" in add_liq_result, f"add_liq_result missing 'shares' key. Keys: {list(add_liq_result.keys())}"
    shares_minted = int(add_liq_result["shares"])
    assert shares_minted > 0, f"Shares minted should be positive, got {shares_minted}"
    
    # Verify reserve changes: both tokens should be added, but not all of base
    coins_before = pool_before["coins"]
    coins_after = pool_after["coins"]
    
    denom_to_amount_before = {c["denom"]: int(c["amount"]) for c in coins_before}
    denom_to_amount_after = {c["denom"]: int(c["amount"]) for c in coins_after}
    
    # Determine which is base and quote based on lexicographic order
    base_denom, quote_denom = sorted([foo_name, bar_name])
    
    # Within band, token2 limiting (dL0 > dL1): both contribute, but base is partially refunded
    base_added = denom_to_amount_after[base_denom] - denom_to_amount_before[base_denom]
    quote_added = denom_to_amount_after[quote_denom] - denom_to_amount_before[quote_denom]
    
    assert base_added > 0, f"Base should have been added (within band), got {base_added}"
    assert quote_added > 0, f"Quote should have been added (within band), got {quote_added}"
    
    # Key test: base should be partially refunded (not all 5000 used)
    # Because quote (500) is limiting, excess base is refunded
    assert base_added < 5000, f"Base should be partially refunded (dL0 > dL1), added {base_added} < 5000"
    
    # Quote should be mostly/fully used (it's the limiting factor)
    assert quote_added <= 500, f"Quote added should be <= 500, got {quote_added}"
    
    # The critical verification: base refund occurred (line 111-113)
    base_refunded = 5000 - base_added
    assert base_refunded > 0, f"Base should have been refunded (dL0 > dL1), refund: {base_refunded}"
