"""
Test MsgAddLiquidity for whaleswap pools after directional bound_percent changes.

Happy-path coverage includes:
- Adding liquidity matching pool ratio
- Token2 (quote) limiting with refunds
- Custom bound_percent persistence through liquidity operations
- Refund handling when inputs deviate from pool ratio
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


def _mint_custom_denoms(dysond, key_name: str, denoms, amount: int = 1_000_000):
    params = dysond("query", "nameservice", "params")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    fee = int(amount * fee_per + 0.99999)
    for denom in denoms:
        tx = dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{amount}{denom}",
            "--mint-fee",
            f"{fee}udys",
            "--from",
            key_name,
        )
        assert tx.get("code", 1) == 0, f"mint-coins failed: {json.dumps(tx, indent=2)}"


@pytest.mark.usefixtures("faucet")
def test_add_liquidity_unbounded_basic(chainnet, generate_account, register_name):
    """Add liquidity to an unbounded pool (bound_percent defaults to 1)."""
    dysond = chainnet[0]
    alice_name, alice_addr = generate_account("addliq_basic", faucet_amount=5_000_000)
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")

    _mint_custom_denoms(dysond, alice_name, [foo_name, bar_name])

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
    denom_a, denom_b = sorted([foo_name, bar_name])
    pool_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        "fee_rate": [
            {"denom": denom_a, "amount": "0.002"},
            {"denom": denom_b, "amount": "0.002"}
        ],
        "min_collateral_ratio": [
            {"denom": denom_a, "amount": "1.5"},
            {"denom": denom_b, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": denom_a, "amount": "20.0"},
            {"denom": denom_b, "amount": "20.0"}
        ],
        "liquidation_threshold": [
            {"denom": denom_a, "amount": "1.2"},
            {"denom": denom_b, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": denom_a, "amount": "0.8"},
            {"denom": denom_b, "amount": "0.8"}
        ]
    })
    pool_id = pool_resp["results"][0]["pool_id"]

    pool_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })

    add_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "5000"},
            {"denom": bar_name, "amount": "5000"}
        ]
    })

    pool_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })

    return {
        "pool_before": pool_before["pool"],
        "add_result": add_resp["results"][0],
        "pool_after": pool_after["pool"],
        "foo_name": foo_name,
        "bar_name": bar_name,
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
        "demo_add_liquidity_unbounded",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Full: {json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed: {json.dumps(query_result['exception'], indent=2)}"

    demo_result = result["result"]["result"]
    pool_before = demo_result["pool_before"]
    pool_after = demo_result["pool_after"]
    add_result = demo_result["add_result"]

    assert (
        "shares" in add_result
    ), f"AddLiquidity response missing shares: {json.dumps(add_result, indent=2)}"
    shares_minted = int(add_result["shares"])
    assert shares_minted > 0, "Shares should be positive"

    denom_before = {coin["denom"]: int(coin["amount"]) for coin in pool_before["coins"]}
    denom_after = {coin["denom"]: int(coin["amount"]) for coin in pool_after["coins"]}

    assert denom_after[foo_name] == denom_before[foo_name] + 5000
    assert denom_after[bar_name] == denom_before[bar_name] + 5000

    bound_percent = {
        entry["denom"]: entry["amount"] for entry in pool_after.get("bound_percent", [])
    }
    assert bound_percent[foo_name] == "1.000000000000000000"
    assert bound_percent[bar_name] == "1.000000000000000000"


@pytest.mark.usefixtures("faucet")
def test_add_liquidity_unbounded_token2_limiting(
    chainnet, generate_account, register_name
):
    """Token2 limits the minted shares causing excess token1 refund."""
    dysond = chainnet[0]
    alice_name, alice_addr = generate_account("addliq_token2", faucet_amount=5_000_000)
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")

    _mint_custom_denoms(dysond, alice_name, [foo_name, bar_name])

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
    denom_a, denom_b = sorted([foo_name, bar_name])
    pool_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "20000"}
        ],
        "fee_rate": [
            {"denom": denom_a, "amount": "0.003"},
            {"denom": denom_b, "amount": "0.003"}
        ],
        "min_collateral_ratio": [
            {"denom": denom_a, "amount": "1.5"},
            {"denom": denom_b, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": denom_a, "amount": "20.0"},
            {"denom": denom_b, "amount": "20.0"}
        ],
        "liquidation_threshold": [
            {"denom": denom_a, "amount": "1.2"},
            {"denom": denom_b, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": denom_a, "amount": "0.8"},
            {"denom": denom_b, "amount": "0.8"}
        ]
    })
    pool_id = pool_resp["results"][0]["pool_id"]

    pool_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })

    add_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "5000"}
        ]
    })

    pool_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })

    return {
        "pool_before": pool_before["pool"],
        "pool_after": pool_after["pool"],
        "add_result": add_resp["results"][0],
        "foo_name": foo_name,
        "bar_name": bar_name,
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
        "demo_add_liquidity_token2_limiting",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Full: {json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed: {json.dumps(query_result['exception'], indent=2)}"

    demo_result = result["result"]["result"]
    add_result = demo_result["add_result"]
    pool_before = demo_result["pool_before"]
    pool_after = demo_result["pool_after"]

    assert (
        "shares" in add_result
    ), f"Response missing shares: {json.dumps(add_result, indent=2)}"
    shares_minted = int(add_result["shares"])
    assert shares_minted > 0

    before = {coin["denom"]: int(coin["amount"]) for coin in pool_before["coins"]}
    after = {coin["denom"]: int(coin["amount"]) for coin in pool_after["coins"]}

    # Quote tokens are limiting (pool ratio 1:2, deposit 10000:5000 -> effective ratio 1:0.5)
    assert after[demo_result["foo_name"]] == before[demo_result["foo_name"]] + 2500
    assert after[demo_result["bar_name"]] == before[demo_result["bar_name"]] + 5000


@pytest.mark.usefixtures("faucet")
def test_add_liquidity_with_custom_bound_percent(
    chainnet, generate_account, register_name
):
    """Add liquidity to a pool configured with asymmetric bound_percent values."""
    dysond = chainnet[0]
    alice_name, alice_addr = generate_account("addliq_bounds", faucet_amount=5_000_000)
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")

    _mint_custom_denoms(dysond, alice_name, [foo_name, bar_name])

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


def demo_add_liquidity_with_bounds(alice_addr, foo_name, bar_name):
    pool_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "15000"},
            {"denom": bar_name, "amount": "15000"}
        ],
        "fee_rate": [
            {"denom": foo_name, "amount": "0.001"},
            {"denom": bar_name, "amount": "0.001"}
        ],
        "bound_percent": [
            {"denom": foo_name, "amount": "0.250000000000000000"},
            {"denom": bar_name, "amount": "1.000000000000000000"}
        ],
        "min_collateral_ratio": [
            {"denom": foo_name, "amount": "1.5"},
            {"denom": bar_name, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": foo_name, "amount": "12.0"},
            {"denom": bar_name, "amount": "12.0"}
        ],
        "liquidation_threshold": [
            {"denom": foo_name, "amount": "1.2"},
            {"denom": bar_name, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": foo_name, "amount": "0.6"},
            {"denom": bar_name, "amount": "0.6"}
        ]
    })
    pool_id = pool_resp["results"][0]["pool_id"]

    add_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "3000"},
            {"denom": bar_name, "amount": "3000"}
        ]
    })

    pool_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })

    return {"pool_after": pool_after["pool"], "add_result": add_resp["results"][0], "foo_name": foo_name, "bar_name": bar_name}
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
        "demo_add_liquidity_with_bounds",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Full: {json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed: {json.dumps(query_result['exception'], indent=2)}"

    demo_result = result["result"]["result"]
    pool_after = demo_result["pool_after"]
    bound_percent = {
        entry["denom"]: entry["amount"] for entry in pool_after.get("bound_percent", [])
    }

    assert bound_percent[demo_result["foo_name"]] == "0.250000000000000000"
    assert bound_percent[demo_result["bar_name"]] == "1.000000000000000000"

    add_result = demo_result["add_result"]
    assert "shares" in add_result and int(add_result["shares"]) > 0


@pytest.mark.usefixtures("faucet")
def test_add_liquidity_with_refund(chainnet, generate_account, register_name):
    """Verify refunds when contribution ratio differs from pool reserves."""
    dysond = chainnet[0]
    alice_name, alice_addr = generate_account("addliq_refund", faucet_amount=5_000_000)
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")

    _mint_custom_denoms(dysond, alice_name, [foo_name, bar_name])

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


def demo_add_liquidity_refund(alice_addr, foo_name, bar_name):
    denom_a, denom_b = sorted([foo_name, bar_name])
    pool_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "12000"},
            {"denom": bar_name, "amount": "12000"}
        ],
        "fee_rate": [
            {"denom": denom_a, "amount": "0.002"},
            {"denom": denom_b, "amount": "0.002"}
        ],
        "min_collateral_ratio": [
            {"denom": denom_a, "amount": "1.5"},
            {"denom": denom_b, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": denom_a, "amount": "20.0"},
            {"denom": denom_b, "amount": "20.0"}
        ],
        "liquidation_threshold": [
            {"denom": denom_a, "amount": "1.2"},
            {"denom": denom_b, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": denom_a, "amount": "0.8"},
            {"denom": denom_b, "amount": "0.8"}
        ]
    })
    pool_id = pool_resp["results"][0]["pool_id"]

    add_resp = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgAddLiquidity",
        "signer": alice_addr,
        "pool_id": pool_id,
        "amounts": [
            {"denom": foo_name, "amount": "5000"},
            {"denom": bar_name, "amount": "8000"}
        ]
    })

    pool_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })

    return {
        "pool_after": pool_after["pool"],
        "add_result": add_resp["results"][0],
        "foo_name": foo_name,
        "bar_name": bar_name,
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
        "demo_add_liquidity_refund",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Full: {json.dumps(query_result, indent=2)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed: {json.dumps(query_result['exception'], indent=2)}"

    demo_result = result["result"]["result"]
    pool_after = demo_result["pool_after"]
    add_result = demo_result["add_result"]

    assert "shares" in add_result
    assert int(add_result["shares"]) > 0

    amounts = {coin["denom"]: int(coin["amount"]) for coin in pool_after["coins"]}
    assert amounts[demo_result["foo_name"]] == 17000  # 12000 + 5000 effective
    assert (
        amounts[demo_result["bar_name"]] == 17000
    )  # 12000 + 5000 effective (3000 refunded)


@pytest.mark.usefixtures("faucet")
def test_add_liquidity_unbalanced_basic(chainnet, generate_account, register_name):
    """Add unbalanced liquidity to an unbounded pool (adds full amounts without refunds)."""
    dysond = chainnet[0]
    alice_name, alice_addr = generate_account("addliq_unbal", faucet_amount=5_000_000)
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")

    _mint_custom_denoms(dysond, alice_name, [foo_name, bar_name])

    # Create unbounded pool
    create_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"12000{foo_name}",
        "--coins",
        f"12000{bar_name}",
        "--min-collateral-ratio",
        "1.5",
        "--max-leverage-ratio",
        "20.0",
        "--liquidation-threshold",
        "1.2",
        "--max-borrow-percent",
        "0.5",
        "--fee-rate",
        f"0.003{foo_name}",
        "--fee-rate",
        f"0.003{bar_name}",
        "--from",
        alice_name,
    )
    assert create_result.get("code", 1) == 0

    pool_id = 1  # First pool

    # Add unbalanced liquidity with unequal amounts
    add_result = dysond(
        "tx",
        "whaleswap",
        "add-liquidity",
        "--pool-id",
        str(pool_id),
        "--amounts",
        f"5000{foo_name}",
        "--amounts",
        f"3000{bar_name}",
        "--unbalanced",
        "--from",
        alice_name,
    )
    assert add_result.get("code", 1) == 0

    # Query pool after add
    pool_query = dysond("query", "whaleswap", "pool", "--pool-id", str(pool_id))
    pool_data = pool_query["pool"]

    # Check reserves increased by full added amounts (no refunds)
    amounts = {coin["denom"]: int(coin["amount"]) for coin in pool_data["coins"]}
    assert amounts[foo_name] == 17000  # 12000 + 5000
    assert amounts[bar_name] == 15000  # 12000 + 3000

    # Check shares minted by querying balance
    balance_query = dysond("query", "bank", "balances", alice_addr)
    balances = {
        coin["denom"]: int(coin["amount"]) for coin in balance_query["balances"]
    }
    shares_denom = pool_data["shares_denom"]
    shares_minted = balances.get(shares_denom, 0) - 12000  # Initial shares were 12000

    # Check shares minted (should be 3000: min(5000, 3000) since R1=R2=12000)
    assert shares_minted == 3000
