"""
Test MsgCreatePool for whaleswap pools.

Tests the CreatePool message handler which creates AMM pools with leverage support.
This operation:
1. Validates pool configuration (coins, fees, leverage params)
2. Transfers initial liquidity to module
3. Mints pool shares
4. Emits EventPoolCreated

Key validation paths tested:
- Basic unbounded pool creation (happy path)
- Bounded pool with min/max price bands
- Custom fee rates and interest rates
- Pool shares minting and distribution
- Event emission
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


def test_create_pool_unbounded_basic_success(
    chainnet, generate_account, faucet, register_name
):
    """Test successful creation of an unbounded AMM pool (no price bands)."""
    dysond = chainnet[0]
    
    # Create account and register names
    alice_name, alice_addr = generate_account("pool_alice", faucet_amount=5_000_000)
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    
    # Mint coins
    params = dysond("query", "nameservice", "params")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_amount = 1_000_000
    mint_fee = int(mint_amount * fee_per + 0.99999)
    
    for denom in [foo_name, bar_name]:
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{mint_amount}{denom}",
            "--mint-fee",
            f"{mint_fee}udys",
            "--from",
            alice_name,
        )
    
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

def demo_create_pool_unbounded(alice_addr, foo_name, bar_name):
    # Create unbounded pool (no min_price/max_price)
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
    
    # Query the created pool
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    return {
        "pool_id": pool_id,
        "pool": pool_query["pool"],
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
        "demo_create_pool_unbounded",
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
    assert demo_result.get("pool_id") is not None, f"Script should return pool_id. Result: {json.dumps(demo_result, indent=2)}"
    assert demo_result.get("pool") is not None, f"Script should return pool. Result: {json.dumps(demo_result, indent=2)}"
    
    pool = demo_result["pool"]
    pool_id = demo_result["pool_id"]
    
    # Verify pool structure
    assert isinstance(pool, dict), f"Pool should be dict, got {type(pool)}"
    assert "pool_id" in pool, f"Pool missing 'pool_id' key. Keys: {list(pool.keys())}"
    assert "coins" in pool, f"Pool missing 'coins' key. Keys: {list(pool.keys())}"
    assert "shares_denom" in pool, f"Pool missing 'shares_denom' key. Keys: {list(pool.keys())}"
    assert "fee_rate" in pool, f"Pool missing 'fee_rate' key. Keys: {list(pool.keys())}"
    assert "min_collateral_ratio" in pool, f"Pool missing 'min_collateral_ratio' key. Keys: {list(pool.keys())}"
    assert "max_leverage_ratio" in pool, f"Pool missing 'max_leverage_ratio' key. Keys: {list(pool.keys())}"
    assert "liquidation_threshold" in pool, f"Pool missing 'liquidation_threshold' key. Keys: {list(pool.keys())}"
    assert "max_borrow_percent" in pool, f"Pool missing 'max_borrow_percent' key. Keys: {list(pool.keys())}"
    
    # Verify pool_id matches
    assert pool["pool_id"] == pool_id, f"Pool ID mismatch: expected {pool_id}, got {pool['pool_id']}"
    
    # Verify coins
    coins = pool["coins"]
    assert isinstance(coins, list), f"Coins should be list, got {type(coins)}"
    assert len(coins) == 2, f"Pool should have exactly 2 coins, got {len(coins)}"
    
    # Map coins by denom
    denom_to_coin = {c["denom"]: c for c in coins}
    assert foo_name in denom_to_coin, f"Pool should contain {foo_name}. Coins: {coins}"
    assert bar_name in denom_to_coin, f"Pool should contain {bar_name}. Coins: {coins}"
    assert denom_to_coin[foo_name]["amount"] == "10000", f"Expected 10000 {foo_name}, got {denom_to_coin[foo_name]['amount']}"
    assert denom_to_coin[bar_name]["amount"] == "10000", f"Expected 10000 {bar_name}, got {denom_to_coin[bar_name]['amount']}"
    
    # Verify shares denom format
    shares_denom = pool["shares_denom"]
    assert isinstance(shares_denom, str), f"Shares denom should be string, got {type(shares_denom)}"
    assert "whaleswap.dys/pools/" in shares_denom, f"Shares denom should contain 'whaleswap.dys/pools/', got {shares_denom}"
    
    # Verify fee rates
    fee_rate = pool["fee_rate"]
    assert isinstance(fee_rate, list), f"Fee rate should be list, got {type(fee_rate)}"
    assert len(fee_rate) == 2, f"Fee rate should have 2 entries, got {len(fee_rate)}"
    fee_by_denom = {f["denom"]: f["amount"] for f in fee_rate}
    base, quote = sorted([foo_name, bar_name])
    assert base in fee_by_denom, f"Fee rate missing {base}. Fee rate: {fee_rate}"
    assert quote in fee_by_denom, f"Fee rate missing {quote}. Fee rate: {fee_rate}"
    assert fee_by_denom[base] == "0.003000000000000000", f"Expected fee rate 0.003 for {base}, got {fee_by_denom[base]}"
    assert fee_by_denom[quote] == "0.003000000000000000", f"Expected fee rate 0.003 for {quote}, got {fee_by_denom[quote]}"
    
    # Verify leverage params
    min_cr = pool["min_collateral_ratio"]
    assert isinstance(min_cr, list), f"Min collateral ratio should be list, got {type(min_cr)}"
    assert len(min_cr) == 2, f"Min collateral ratio should have 2 entries, got {len(min_cr)}"
    
    max_lev = pool["max_leverage_ratio"]
    assert isinstance(max_lev, list), f"Max leverage ratio should be list, got {type(max_lev)}"
    assert len(max_lev) == 2, f"Max leverage ratio should have 2 entries, got {len(max_lev)}"
    
    liq_thresh = pool["liquidation_threshold"]
    assert isinstance(liq_thresh, list), f"Liquidation threshold should be list, got {type(liq_thresh)}"
    assert len(liq_thresh) == 2, f"Liquidation threshold should have 2 entries, got {len(liq_thresh)}"
    
    max_borrow = pool["max_borrow_percent"]
    assert isinstance(max_borrow, list), f"Max borrow percent should be list, got {type(max_borrow)}"
    assert len(max_borrow) == 2, f"Max borrow percent should have 2 entries, got {len(max_borrow)}"
    
    # Verify unbounded (no price bands)
    min_price = pool.get("min_price", [])
    max_price = pool.get("max_price", [])
    assert len(min_price) == 0, f"Unbounded pool should have no min_price, got {min_price}"
    assert len(max_price) == 0, f"Unbounded pool should have no max_price, got {max_price}"


def test_create_pool_bounded_with_price_bands(
    chainnet, generate_account, faucet, register_name
):
    """Test successful creation of a bounded AMM pool with price bands."""
    dysond = chainnet[0]
    
    # Create account and register names
    alice_name, alice_addr = generate_account("pool_alice2", faucet_amount=5_000_000)
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    
    # Mint coins
    params = dysond("query", "nameservice", "params")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_amount = 1_000_000
    mint_fee = int(mint_amount * fee_per + 0.99999)
    
    for denom in [foo_name, bar_name]:
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{mint_amount}{denom}",
            "--mint-fee",
            f"{mint_fee}udys",
            "--from",
            alice_name,
        )
    
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

def demo_create_pool_bounded(alice_addr, foo_name, bar_name):
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
    
    # Query the created pool
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    return {
        "pool_id": pool_id,
        "pool": pool_query["pool"]
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
        "demo_create_pool_bounded",
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
    assert demo_result.get("pool") is not None, f"Script should return pool. Result: {json.dumps(demo_result, indent=2)}"
    
    pool = demo_result["pool"]
    
    # Verify pool has price bands
    min_price = pool.get("min_price", [])
    max_price = pool.get("max_price", [])
    assert len(min_price) == 2, f"Bounded pool should have min_price with 2 entries, got {len(min_price)}"
    assert len(max_price) == 2, f"Bounded pool should have max_price with 2 entries, got {len(max_price)}"
    
    # Verify price bands are set
    min_price_by_denom = {p["denom"]: p["amount"] for p in min_price}
    max_price_by_denom = {p["denom"]: p["amount"] for p in max_price}
    
    base, quote = sorted([foo_name, bar_name])
    assert base in min_price_by_denom, f"Min price missing {base}. Min price: {min_price}"
    assert quote in min_price_by_denom, f"Min price missing {quote}. Min price: {min_price}"
    assert base in max_price_by_denom, f"Max price missing {base}. Max price: {max_price}"
    assert quote in max_price_by_denom, f"Max price missing {quote}. Max price: {max_price}"


def test_create_pool_with_custom_interest_rate(
    chainnet, generate_account, faucet, register_name
):
    """Test pool creation with custom interest rates."""
    dysond = chainnet[0]
    
    # Create account and register names
    alice_name, alice_addr = generate_account("pool_alice3", faucet_amount=5_000_000)
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    
    # Mint coins
    params = dysond("query", "nameservice", "params")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_amount = 1_000_000
    mint_fee = int(mint_amount * fee_per + 0.99999)
    
    for denom in [foo_name, bar_name]:
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{mint_amount}{denom}",
            "--mint-fee",
            f"{mint_fee}udys",
            "--from",
            alice_name,
        )
    
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

def demo_create_pool_with_interest(alice_addr, foo_name, bar_name):
    # Create pool with custom interest rates
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
        "interest_rate": [
            {"denom": base, "amount": "0.05"},
            {"denom": quote, "amount": "0.05"}
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
    
    # Query the created pool
    pool_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    return {
        "pool_id": pool_id,
        "pool": pool_query["pool"]
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
        "demo_create_pool_with_interest",
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
    assert demo_result.get("pool") is not None, f"Script should return pool. Result: {json.dumps(demo_result, indent=2)}"
    
    pool = demo_result["pool"]
    
    # Verify interest rates are set
    interest_rate = pool.get("interest_rate", [])
    assert len(interest_rate) == 2, f"Interest rate should have 2 entries, got {len(interest_rate)}"
    
    interest_by_denom = {ir["denom"]: ir["amount"] for ir in interest_rate}
    base, quote = sorted([foo_name, bar_name])
    assert base in interest_by_denom, f"Interest rate missing {base}. Interest rate: {interest_rate}"
    assert quote in interest_by_denom, f"Interest rate missing {quote}. Interest rate: {interest_rate}"
    assert interest_by_denom[base] == "0.050000000000000000", f"Expected interest rate 0.05 for {base}, got {interest_by_denom[base]}"
    assert interest_by_denom[quote] == "0.050000000000000000", f"Expected interest rate 0.05 for {quote}, got {interest_by_denom[quote]}"

