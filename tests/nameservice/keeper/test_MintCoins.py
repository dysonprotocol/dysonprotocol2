"""
Test MintCoins message handler for nameservice keeper.

Tests the MintCoins functionality which allows name owners to mint custom coins
using their registered names as denominations, with proper fee collection and
authority validation.
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

def demo_mint_coins_success(name, owner, subdenoms, amounts, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Register name and set destination
    _register_root_name(name, owner)

    # Get mint fee parameters
    params = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest",
    })
    mint_fee_per = float(params["params"]["mint_fee_per_coin"])

    # Calculate required fee
    total_units = sum(amounts)
    required_fee = int(total_units * mint_fee_per + 0.99999)  # Ceiling

    # Create coins to mint
    coins_to_mint = []
    for i, subdenom in enumerate(subdenoms):
        denom = name + subdenom if subdenom else name
        amount = amounts[i]
        coins_to_mint.append({"denom": denom, "amount": str(amount)})

    # Mint coins
    mint_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": owner,
        "amount": coins_to_mint,
        "mint_fee": {"denom": "udys", "amount": str(required_fee)},
    })

    return {
        "mint_result": mint_result,
        "coins_minted": coins_to_mint,
        "required_fee": required_fee,
    }

def demo_mint_coins_module_account(name, module_addr, alice_addr):
    # This tests minting to a module account (no fee should be charged)
    # We need to set up a scenario where the destination is a module account

    # For this test, we'll mint to the gov module account
    # First register a name and point it to the module account
    owner = get_executor_address()  # Use executor as owner for setup
    _register_root_name(name, owner)

    # Set destination to module account
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": module_addr,
    })

    # Mint coins (should skip fee for module destination)
    coins_to_mint = [{"denom": name, "amount": "100"}]

    mint_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": module_addr,
        "amount": coins_to_mint,
        "mint_fee": {"denom": "udys", "amount": "0"},  # No fee needed
    })

    return {
        "mint_result": mint_result,
        "coins_minted": coins_to_mint,
    }

def demo_mint_coins_invalid_address(name, owner, invalid_addr, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "1000"}]
    })

    # Register name and set destination
    _register_root_name(name, owner)

    # Try to mint with invalid address
    coins_to_mint = [{"denom": name, "amount": "100"}]

    mint_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": invalid_addr,  # Invalid bech32 address
        "amount": coins_to_mint,
        "mint_fee": {"denom": "udys", "amount": "10"},
    })

    return {
        "mint_result": mint_result,
    }

def demo_mint_coins_empty_amount(name, owner, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "1000"}]
    })

    # Register name and set destination
    _register_root_name(name, owner)

    # Try to mint with empty amount array
    mint_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": owner,
        "amount": [],  # Empty array
        "mint_fee": {"denom": "udys", "amount": "0"},
    })

    return {
        "mint_result": mint_result,
    }

def demo_mint_coins_invalid_denom(name, owner, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "1000"}]
    })

    # Register name and set destination
    _register_root_name(name, owner)

    # Try to mint with invalid denom format
    coins_to_mint = [{"denom": "invalid_denom!", "amount": "100"}]

    mint_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": owner,
        "amount": coins_to_mint,
        "mint_fee": {"denom": "udys", "amount": "10"},
    })

    return {
        "mint_result": mint_result,
    }

def demo_mint_coins_unauthorized_denom(name, owner, other_owner, alice_addr):
    # Fund test accounts from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "1000"}]
    })

    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": other_owner,
        "amount": [{"denom": "udys", "amount": "1000"}]
    })

    # Register name for owner
    _register_root_name(name, owner)

    # Try to mint coins using other_owner (who doesn't control the name)
    coins_to_mint = [{"denom": name, "amount": "100"}]

    mint_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": other_owner,  # Wrong owner
        "amount": coins_to_mint,
        "mint_fee": {"denom": "udys", "amount": "10"},
    })

    return {
        "mint_result": mint_result,
    }

def demo_mint_coins_insufficient_fee(name, owner, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "1000"}]
    })

    # Register name and set destination
    _register_root_name(name, owner)

    # Get mint fee parameters
    params = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest",
    })
    mint_fee_per = float(params["params"]["mint_fee_per_coin"])

    # Calculate what the required fee should be
    total_units = 100  # 100 coins
    required_fee = int(total_units * mint_fee_per + 0.99999)  # Ceiling

    # Try to mint with insufficient fee (provide less than required)
    coins_to_mint = [{"denom": name, "amount": "100"}]
    insufficient_fee = max(0, required_fee - 1)  # 1 less than required, but not negative

    mint_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": owner,
        "amount": coins_to_mint,
        "mint_fee": {"denom": "udys", "amount": str(insufficient_fee)},  # Insufficient
    })

    return {
        "mint_result": mint_result,
        "required_fee": required_fee,
        "provided_fee": insufficient_fee,
    }

def demo_mint_coins_wrong_fee_denom(name, owner, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "1000"}]
    })

    # Register name and set destination
    _register_root_name(name, owner)

    # Try to mint with wrong fee denom
    coins_to_mint = [{"denom": name, "amount": "100"}]

    mint_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": owner,
        "amount": coins_to_mint,
        "mint_fee": {"denom": "invalid", "amount": "10"},  # Wrong denom
    })

    return {
        "mint_result": mint_result,
    }
"""


def get_test_address(dysond, seed="0x123456"):
    """Generate a test address using address-bytes-to-string."""
    address_result = dysond("q", "auth", "address-bytes-to-string", seed, "-o", "json")
    return address_result["address_string"]


def test_mint_coins_success(chainnet):
    """Test successful coin minting with fee."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    name = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x111111")

    # Execute script
    kwargs = json.dumps({
        "name": name,
        "owner": owner,
        "subdenoms": ["", "/token1"],  # Root denom and subdenom
        "amounts": [100, 50],
        "alice_addr": alice_addr,
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
        "demo_mint_coins_success",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate
    parsed = deep_parse(result)
    assert (
        result.get("exception") is None
    ), f"Script exception: {json.dumps(result.get('exception'), indent=2)}"
    script_result = parsed["result"]["result"]

    # Verify minting succeeded
    assert (
        script_result["mint_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"Minting failed: {script_result['mint_result']}"

    # Verify coins were minted
    assert len(script_result["coins_minted"]) == 2
    assert script_result["required_fee"] > 0


def test_mint_coins_module_account(chainnet):
    """Test coin minting to module account (no fee charged)."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    name = f"test{secrets.token_hex(4)}.dys"

    # Execute script
    kwargs = json.dumps({
        "name": name,
        "module_addr": gov_addr,
        "alice_addr": alice_addr,
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
        "demo_mint_coins_module_account",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate
    parsed = deep_parse(result)
    assert (
        result.get("exception") is None
    ), f"Script exception: {json.dumps(result.get('exception'), indent=2)}"
    script_result = parsed["result"]["result"]

    # Verify minting succeeded
    assert (
        script_result["mint_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"Minting failed: {script_result['mint_result']}"


def test_mint_coins_invalid_address(chainnet):
    """Test minting with invalid destination address."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    name = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x333333")
    invalid_addr = "invalid_address"

    # Execute script
    kwargs = json.dumps({
        "name": name,
        "owner": owner,
        "invalid_addr": invalid_addr,
        "alice_addr": alice_addr,
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
        "demo_mint_coins_invalid_address",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - should fail with exception
    parsed = deep_parse(result)
    assert (
        result.get("exception") is not None
    ), "Expected exception for invalid address, but none occurred"

    # Verify the exception contains the expected error message
    exception_msg = result["exception"]["msg"]
    assert "invalid name_destination address" in exception_msg, f"Unexpected error message: {exception_msg}"

    # The sudo response should contain error information
    # We can't easily check the exact error without parsing the response deeply,
    # but the fact that it's a sudo response means the transaction was submitted


def test_mint_coins_empty_amount(chainnet):
    """Test minting with empty amount array."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    name = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x444444")

    # Execute script
    kwargs = json.dumps({
        "name": name,
        "owner": owner,
        "alice_addr": alice_addr,
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
        "demo_mint_coins_empty_amount",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - should fail with exception
    parsed = deep_parse(result)
    assert (
        result.get("exception") is not None
    ), "Expected exception for empty amount, but none occurred"

    # Verify the exception contains the expected error message
    exception_msg = result["exception"]["msg"]
    assert "no coins to mint" in exception_msg, f"Unexpected error message: {exception_msg}"


def test_mint_coins_invalid_denom(chainnet):
    """Test minting with invalid denom format."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    name = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x555555")

    # Execute script
    kwargs = json.dumps({
        "name": name,
        "owner": owner,
        "alice_addr": alice_addr,
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
        "demo_mint_coins_invalid_denom",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - should fail with exception
    parsed = deep_parse(result)
    assert (
        result.get("exception") is not None
    ), "Expected exception for invalid denom, but none occurred"

    # Verify the exception contains the expected error message
    exception_msg = result["exception"]["msg"]
    assert "invalid denom format" in exception_msg, f"Unexpected error message: {exception_msg}"


def test_mint_coins_unauthorized_denom(chainnet):
    """Test minting with unauthorized denom (wrong owner)."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    name = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x666666")
    other_owner = get_test_address(dysond, "0x777777")

    # Execute script
    kwargs = json.dumps({
        "name": name,
        "owner": owner,
        "other_owner": other_owner,
        "alice_addr": alice_addr,
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
        "demo_mint_coins_unauthorized_denom",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - should fail with exception
    parsed = deep_parse(result)
    assert (
        result.get("exception") is not None
    ), "Expected exception for unauthorized denom, but none occurred"

    # Verify the exception contains the expected error message
    exception_msg = result["exception"]["msg"]
    assert "you do not control destination" in exception_msg, f"Unexpected error message: {exception_msg}"


def test_mint_coins_insufficient_fee(chainnet):
    """Test minting with insufficient fee amount."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    name = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x888888")

    # Execute script
    kwargs = json.dumps({
        "name": name,
        "owner": owner,
        "alice_addr": alice_addr,
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
        "demo_mint_coins_insufficient_fee",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - should fail with insufficient fee
    assert result.get("exception") is not None, "Expected exception for insufficient fee"

    # Verify the exception contains the expected error message
    exception_msg = result["exception"]["msg"]
    assert "insufficient fee" in exception_msg, f"Unexpected error message: {exception_msg}"


def test_mint_coins_wrong_fee_denom(chainnet):
    """Test minting with wrong fee denomination."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    name = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x999999")

    # Execute script
    kwargs = json.dumps({
        "name": name,
        "owner": owner,
        "alice_addr": alice_addr,
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
        "demo_mint_coins_wrong_fee_denom",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - should fail with exception
    parsed = deep_parse(result)
    assert (
        result.get("exception") is not None
    ), "Expected exception for wrong fee denom, but none occurred"

    # Verify the exception contains the expected error message
    exception_msg = result["exception"]["msg"]
    assert "mint_fee denom must be 'udys'" in exception_msg, f"Unexpected error message: {exception_msg}"
