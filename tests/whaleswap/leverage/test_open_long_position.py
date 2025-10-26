import json
import pytest
from pathlib import Path
from typing import Any
from deep_parse import deep_parse


def test_open_long_success(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test 1: All validations pass → position created successfully."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
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

def demo_open_long_success(alice_addr, foo_name, bar_name):
    # 1. Create a 2-coin pool in this execution context using foo_name and bar_name
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "100"},
            {"denom": bar_name, "amount": "100"}
        ],
        "fee_pct": "0.003",
        "min_collateral_ratio": "1.5",
        "max_leverage_ratio": "20",
        "max_borrow_percent": "0.8"
    })

    print(f"sudo_pool_result: {sudo_pool_result}")
    
    pool_result = sudo_pool_result["results"][0]

    # 2. Open position on the pool (pool exists in this context)
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_result["pool_id"],
        "collateral": {"denom": foo_name, "amount": "100"},
        "borrow_amount": "10",
        "position_type": "POSITION_TYPE_LONG"
    })

    print(f"sudo_position_result: {sudo_position_result}")

    position_result = sudo_position_result["results"][0]

    return {
        "pool_created": pool_result,
        "position_opened": position_result,
        "success": True
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
        "demo_open_long_success",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    result = deep_parse(query_result)
    print(f"result: {result}")
    assert (
        result["result"]["result"]["success"] is True
    ), f"Query script exec failed: {json.dumps(query_result, indent=2)}"
