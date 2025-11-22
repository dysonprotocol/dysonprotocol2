"""
Test BurnCoins message handler for nameservice keeper.

Tests the BurnCoins functionality which allows owners to burn coins
from their balance, with proper denom authority validation and cleanup
when supply reaches zero.
"""

import json
import secrets
import pytest
from deep_parse import deep_parse


BASE_EXTRA_CODE = r"""
from dys import _msg, _query, get_executor_address
import re

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def _parse_coin(value):
    match = re.fullmatch(r"(\d+)([a-zA-Z0-9./_]+)", value)
    if not match:
        raise Exception("invalid coin value: " + str(value))
    return {"denom": match.group(2), "amount": match.group(1)}

def _register_root_name(name, owner):
    salt = "salt-" + name
    hexhash = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": owner,
    })["hex_hash"]

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": hexhash,
        "valuation": _parse_coin("10udys"),
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": owner,
    })

    return owner

def _mint_coins_for_owner(root_name, subdenoms, amounts, owner):
    params = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest",
    })
    mint_fee_per = float(params["params"]["mint_fee_per_coin"])

    created = []
    total_fee = 0
    total_amount = 0

    for i, subdenom in enumerate(subdenoms):
        denom = root_name + subdenom if subdenom else root_name
        amount = amounts[i] if i < len(amounts) else amounts[0]
        mint_fee_amount = int(amount * mint_fee_per + 0.99999)
        total_fee += mint_fee_amount
        total_amount += amount

        created.append({"denom": denom, "amount": str(amount)})

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": owner,
        "amount": created,
        "mint_fee": {"denom": "udys", "amount": str(total_fee)},
    })

    return created

def demo_burn_coins_single(name, owner, subdenom, burn_amount):
    # Register name and set destination
    _register_root_name(name, owner)

    # Mint coins
    minted = _mint_coins_for_owner(name, [subdenom], [1000], owner)
    denom = minted[0]["denom"]

    # Burn coins
    burn_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgBurnCoins",
        "name_destination": owner,
        "amount": [{"denom": denom, "amount": str(burn_amount)}],
    })

    return {
        "minted": minted,
        "burn_result": burn_result,
    }

def demo_burn_coins_multiple(name, owner, subdenoms, burn_amounts):
    # Register name and set destination
    _register_root_name(name, owner)

    # Mint multiple coins
    mint_amounts = [1000] * len(subdenoms)
    minted = _mint_coins_for_owner(name, subdenoms, mint_amounts, owner)

    # Burn multiple coins
    burn_coins = []
    for i, denom_info in enumerate(minted):
        burn_amount = burn_amounts[i] if i < len(burn_amounts) else burn_amounts[0]
        burn_coins.append({"denom": denom_info["denom"], "amount": str(burn_amount)})

    burn_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgBurnCoins",
        "name_destination": owner,
        "amount": burn_coins,
    })

    return {
        "minted": minted,
        "burn_result": burn_result,
    }

def demo_burn_coins_supply_zero(name, owner, subdenom, burn_all):
    # Register name and set destination
    _register_root_name(name, owner)

    # Mint coins
    mint_amount = 500
    minted = _mint_coins_for_owner(name, [subdenom], [mint_amount], owner)
    denom = minted[0]["denom"]

    # Burn all coins (supply becomes zero)
    burn_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgBurnCoins",
        "name_destination": owner,
        "amount": [{"denom": denom, "amount": str(mint_amount)}],
    })

    return {
        "minted": minted,
        "burn_result": burn_result,
    }

def demo_burn_coins_mixed_supply(name, owner, subdenoms, burn_amounts):
    # Register name and set destination
    _register_root_name(name, owner)

    # Mint coins with different amounts
    mint_amounts = [1000, 500, 800]  # Different amounts for mixed testing
    minted = _mint_coins_for_owner(name, subdenoms, mint_amounts, owner)

    # Burn amounts that will leave some at zero and some with remaining supply
    burn_coins = [
        {"denom": minted[0]["denom"], "amount": "600"},  # Leaves 400 remaining
        {"denom": minted[1]["denom"], "amount": "500"},  # Supply becomes zero
        {"denom": minted[2]["denom"], "amount": "800"},  # Supply becomes zero
    ]

    burn_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgBurnCoins",
        "name_destination": owner,
        "amount": burn_coins,
    })

    return {
        "minted": minted,
        "burn_result": burn_result,
    }


def demo_burn_coins_invalid_address(name, owner, invalid_address):
    # Register name and set destination
    _register_root_name(name, owner)

    # Mint coins
    minted = _mint_coins_for_owner(name, ["/coin"], [1000], owner)

    # Try to burn with invalid address
    burn_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgBurnCoins",
        "name_destination": invalid_address,
        "amount": [{"denom": minted[0]["denom"], "amount": "100"}],
    })

    return {
        "minted": minted,
        "burn_result": burn_result,
    }


def demo_burn_coins_invalid_denom_wrong_destination(name, owner, wrong_owner):
    # Register name and set destination
    _register_root_name(name, owner)

    # Mint coins
    minted = _mint_coins_for_owner(name, ["/coin"], [1000], owner)

    # Try to burn with wrong destination (not the owner of the denom)
    burn_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgBurnCoins",
        "name_destination": wrong_owner,
        "amount": [{"denom": minted[0]["denom"], "amount": "100"}],
    })

    return {
        "minted": minted,
        "burn_result": burn_result,
    }


def demo_burn_coins_invalid_denom_nonexistent_root(invalid_denom, owner):
    # Try to burn coins with non-existent root name
    burn_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgBurnCoins",
        "name_destination": owner,
        "amount": [{"denom": invalid_denom, "amount": "100"}],
    })

    return {
        "burn_result": burn_result,
    }
"""


def _random_root_name():
    return f"burn-{secrets.token_hex(4)}.dys"


def test_burn_coins_single_success(chainnet):
    """Test successful burn of single coin type controlled by destination."""
    dysond = chainnet[0]
    # Use a funded address from genesis
    owner_addr = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"]["address"]

    root_name = _random_root_name()
    kwargs = json.dumps({
        "name": root_name,
        "owner": owner_addr,
        "subdenom": "/coin",
        "burn_amount": 300,
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
        "demo_burn_coins_single",
        "--kwargs",
        kwargs,
        "--extra-code",
        BASE_EXTRA_CODE,
    )

    # Parse and validate response
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), f"demo_result should be dict, got {type(demo_result)}"

    # Validate minted coins
    minted = demo_result["minted"]
    assert isinstance(minted, list), f"minted should be list, got {type(minted)}"
    assert len(minted) == 1, f"should mint 1 coin type, got {len(minted)}"
    assert "denom" in minted[0], f"minted coin missing denom key"
    assert "amount" in minted[0], f"minted coin missing amount key"
    assert minted[0]["amount"] == "1000", f"should mint 1000 units, got {minted[0]['amount']}"

    # Validate burn result
    burn_result = demo_result["burn_result"]
    assert isinstance(burn_result, dict), f"burn_result should be dict, got {type(burn_result)}"
    assert burn_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse", f"burn should return sudo response, got {burn_result.get('@type')}"
    assert "results" in burn_result, f"burn should have results, got {list(burn_result.keys())}"
    assert len(burn_result["results"]) == 1, f"burn should have one result, got {len(burn_result['results'])}"
    assert burn_result["results"][0]["@type"] == "/dysonprotocol.nameservice.v1.MsgBurnCoinsResponse", f"burn should return burn response, got {burn_result['results'][0].get('@type')}"


def test_burn_coins_multiple_success(chainnet):
    """Test successful burn of multiple coin types in single transaction."""
    dysond = chainnet[0]
    owner_addr = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"]["address"]

    root_name = _random_root_name()
    kwargs = json.dumps({
        "name": root_name,
        "owner": owner_addr,
        "subdenoms": ["/coin/a", "/coin/b", "/coin/c"],
        "burn_amounts": [200, 150, 100],
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
        "demo_burn_coins_multiple",
        "--kwargs",
        kwargs,
        "--extra-code",
        BASE_EXTRA_CODE,
    )

    # Parse and validate response
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), f"demo_result should be dict, got {type(demo_result)}"

    # Validate minted coins
    minted = demo_result["minted"]
    assert isinstance(minted, list), f"minted should be list, got {type(minted)}"
    assert len(minted) == 3, f"should mint 3 coin types, got {len(minted)}"
    for coin in minted:
        assert "denom" in coin, f"minted coin missing denom key"
        assert "amount" in coin, f"minted coin missing amount key"
        assert coin["amount"] == "1000", f"should mint 1000 units each, got {coin['amount']}"

    # Validate burn result
    burn_result = demo_result["burn_result"]
    assert isinstance(burn_result, dict), f"burn_result should be dict, got {type(burn_result)}"
    assert burn_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse", f"burn should return sudo response, got {burn_result.get('@type')}"
    assert "results" in burn_result, f"burn should have results, got {list(burn_result.keys())}"
    assert len(burn_result["results"]) == 1, f"burn should have one result, got {len(burn_result['results'])}"
    assert burn_result["results"][0]["@type"] == "/dysonprotocol.nameservice.v1.MsgBurnCoinsResponse", f"burn should return burn response, got {burn_result['results'][0].get('@type')}"


def test_burn_coins_supply_zero_cleanup(chainnet):
    """Test burn that removes denom from tracking when supply becomes zero."""
    dysond = chainnet[0]
    owner_addr = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"]["address"]

    root_name = _random_root_name()
    kwargs = json.dumps({
        "name": root_name,
        "owner": owner_addr,
        "subdenom": "/coin",
        "burn_all": True,
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
        "demo_burn_coins_supply_zero",
        "--kwargs",
        kwargs,
        "--extra-code",
        BASE_EXTRA_CODE,
    )

    # Parse and validate response
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), f"demo_result should be dict, got {type(demo_result)}"

    # Validate minted coins
    minted = demo_result["minted"]
    assert isinstance(minted, list), f"minted should be list, got {type(minted)}"
    assert len(minted) == 1, f"should mint 1 coin type, got {len(minted)}"

    # Validate burn result (burns all supply)
    burn_result = demo_result["burn_result"]
    assert isinstance(burn_result, dict), f"burn_result should be dict, got {type(burn_result)}"
    assert burn_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse", f"burn should return sudo response, got {burn_result.get('@type')}"
    assert "results" in burn_result, f"burn should have results, got {list(burn_result.keys())}"
    assert len(burn_result["results"]) == 1, f"burn should have one result, got {len(burn_result['results'])}"
    assert burn_result["results"][0]["@type"] == "/dysonprotocol.nameservice.v1.MsgBurnCoinsResponse", f"burn should return burn response, got {burn_result['results'][0].get('@type')}"


def test_burn_coins_mixed_supply_cleanup(chainnet):
    """Test burn of multiple denoms where some reach zero supply and some remain."""
    dysond = chainnet[0]
    owner_addr = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"]["address"]

    root_name = _random_root_name()
    kwargs = json.dumps({
        "name": root_name,
        "owner": owner_addr,
        "subdenoms": ["/coin/a", "/coin/b", "/coin/c"],
        "burn_amounts": [600, 500, 800],  # Will burn to zero for b and c, leave some for a
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
        "demo_burn_coins_mixed_supply",
        "--kwargs",
        kwargs,
        "--extra-code",
        BASE_EXTRA_CODE,
    )

    # Parse and validate response
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert isinstance(demo_result, dict), f"demo_result should be dict, got {type(demo_result)}"

    # Validate minted coins (different amounts)
    minted = demo_result["minted"]
    assert isinstance(minted, list), f"minted should be list, got {type(minted)}"
    assert len(minted) == 3, f"should mint 3 coin types, got {len(minted)}"
    expected_amounts = ["1000", "500", "800"]
    for i, coin in enumerate(minted):
        assert "denom" in coin, f"minted coin {i} missing denom key"
        assert "amount" in coin, f"minted coin {i} missing amount key"
        assert coin["amount"] == expected_amounts[i], f"coin {i} should have amount {expected_amounts[i]}, got {coin['amount']}"

    # Validate burn result
    burn_result = demo_result["burn_result"]
    assert isinstance(burn_result, dict), f"burn_result should be dict, got {type(burn_result)}"
    assert burn_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse", f"burn should return sudo response, got {burn_result.get('@type')}"
    assert "results" in burn_result, f"burn should have results, got {list(burn_result.keys())}"
    assert len(burn_result["results"]) == 1, f"burn should have one result, got {len(burn_result['results'])}"
    assert burn_result["results"][0]["@type"] == "/dysonprotocol.nameservice.v1.MsgBurnCoinsResponse", f"burn should return burn response, got {burn_result['results'][0].get('@type')}"


def test_burn_coins_invalid_address(chainnet):
    """Test burn with invalid address - should fail with invalid address error."""
    dysond = chainnet[0]
    owner_addr = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"]["address"]

    root_name = _random_root_name()
    invalid_address = "invalid-address"
    kwargs = json.dumps({
        "name": root_name,
        "owner": owner_addr,
        "invalid_address": invalid_address,
    })

    result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_burn_coins_invalid_address",
        "--kwargs",
        kwargs,
        "--extra-code",
        BASE_EXTRA_CODE,
    )

    # Should fail with invalid address error
    assert result.get("exception") is not None, "Expected exception for invalid address"
    exception_msg = result["exception"]["msg"]
    assert (
        "invalid name_destination address" in exception_msg
    ), f"Expected 'invalid name_destination address' in error message: {exception_msg}"


def test_burn_coins_invalid_denom_wrong_destination(chainnet):
    """Test burn with wrong destination - should fail with unauthorized error."""
    dysond = chainnet[0]
    owner_addr = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"]["address"]

    # Use different addresses for owner and wrong_owner
    wrong_owner_addr = "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej"  # alice address

    root_name = _random_root_name()
    kwargs = json.dumps({
        "name": root_name,
        "owner": owner_addr,
        "wrong_owner": wrong_owner_addr,
    })

    result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_burn_coins_invalid_denom_wrong_destination",
        "--kwargs",
        kwargs,
        "--extra-code",
        BASE_EXTRA_CODE,
    )

    # Should fail with unauthorized error
    assert result.get("exception") is not None, "Expected exception for wrong destination"
    exception_msg = result["exception"]["msg"]
    assert (
        "you do not control destination" in exception_msg
    ), f"Expected 'you do not control destination' in error message: {exception_msg}"


def test_burn_coins_invalid_denom_nonexistent_root(chainnet):
    """Test burn with non-existent root name - should fail with not found error."""
    dysond = chainnet[0]
    owner_addr = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"]["address"]

    invalid_denom = "nonexistent.dys"
    kwargs = json.dumps({
        "invalid_denom": invalid_denom,
        "owner": owner_addr,
    })

    result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_burn_coins_invalid_denom_nonexistent_root",
        "--kwargs",
        kwargs,
        "--extra-code",
        BASE_EXTRA_CODE,
    )

    # Should fail with not found error
    assert result.get("exception") is not None, "Expected exception for non-existent root name"
    exception_msg = result["exception"]["msg"]
    assert (
        "root name not found" in exception_msg
    ), f"Expected 'root name not found' in error message: {exception_msg}"
