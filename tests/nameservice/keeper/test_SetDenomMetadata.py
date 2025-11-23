"""
Test SetDenomMetadata message handler for nameservice keeper.

Tests the SetDenomMetadata functionality which allows governance to set
bank denom metadata for denoms in the system.
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

    return name


def demo_set_denom_metadata(name, owner, authority, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Register name and set destination
    _register_root_name(name, owner)

    # Mint coins to create denom metadata
    coins_to_mint = [{"denom": name, "amount": "100"}]

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": owner,
        "amount": coins_to_mint,
        "mint_fee": {"denom": "udys", "amount": "1"},
    })

    # Set denom metadata - this should be called by governance
    # Extract base name without .dys suffix
    base_name = name[:-4]  # Remove .dys suffix
    display_name = base_name
    symbol_name = base_name.upper()

    set_metadata_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDenomMetadata",
        "authority": authority,
        "metadata": {
            "base": name,
            "display": display_name,
            "symbol": symbol_name,
            "name": "Test " + name + " Token",
            "description": "Test description for " + name + " token",
            "uri": "https://example.com/" + name,
            "uri_hash": "",
            "denom_units": [
                {
                    "denom": name,
                    "exponent": 0,
                    "aliases": []
                },
                {
                    "denom": display_name,
                    "exponent": 6,
                    "aliases": []
                }
            ]
        }
    })

    # Query the updated metadata to verify
    metadata_query = _query({
        "@type": "/cosmos.bank.v1beta1.QueryDenomMetadataRequest",
        "denom": name,
    })

    return {
        "set_metadata_result": set_metadata_result,
        "metadata": metadata_query,
    }
"""


def get_test_address(dysond, seed="0x123456"):
    """Generate a test address using address-bytes-to-string."""
    address_result = dysond("q", "auth", "address-bytes-to-string", seed, "-o", "json")
    return address_result["address_string"]


def test_set_denom_metadata_success(chainnet):
    """Test successful denom metadata setting by authorized governance."""
    dysond = chainnet[0]

    # Get gov address for authority - this is the only authorized address
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
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
        "authority": gov_addr,
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
        "demo_set_denom_metadata",
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

    # Verify SetDenomMetadata succeeded
    assert (
        script_result["set_metadata_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetDenomMetadata failed: {script_result['set_metadata_result']}"

    # Verify the metadata was set correctly
    metadata = script_result["metadata"]
    base_name = name[:-4]  # Remove .dys suffix
    display_name = base_name
    symbol_name = base_name.upper()

    assert metadata["metadata"]["base"] == name
    assert metadata["metadata"]["display"] == display_name
    assert metadata["metadata"]["symbol"] == symbol_name
    assert metadata["metadata"]["name"] == "Test " + name + " Token"
    assert metadata["metadata"]["description"] == "Test description for " + name + " token"
    assert metadata["metadata"]["uri"] == "https://example.com/" + name

    # Verify denom_units structure
    denom_units = metadata["metadata"]["denom_units"]
    assert len(denom_units) == 2

    # Base unit (must be first)
    assert denom_units[0]["denom"] == name
    assert denom_units[0]["exponent"] == 0

    # Display unit
    assert denom_units[1]["denom"] == display_name
    assert denom_units[1]["exponent"] == 6
