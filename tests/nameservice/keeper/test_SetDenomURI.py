"""
Test SetDenomURI message handler for nameservice keeper.

Tests the SetDenomURI functionality which allows name owners to set
URI and URIHash for bank denom metadata.
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


def demo_set_denom_uri_existing_metadata(name, owner, alice_addr):
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

    # First set full metadata to ensure it exists with Symbol and Name set
    base_name = name[:-4]  # Remove .dys suffix
    display_name = base_name
    symbol_name = base_name.upper()

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDenomMetadata",
        "authority": get_executor_address(),  # Use gov authority
        "metadata": {
            "base": name,
            "display": display_name,
            "symbol": symbol_name,
            "name": "Test " + name + " Token",
            "description": "Test description for " + name + " token",
            "uri": "",
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

    # Now set URI - this tests updating existing metadata with Symbol/Name already set
    set_uri_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDenomURI",
        "name_destination": owner,
        "denom": name,
        "uri": "https://example.com/" + name,
        "uri_hash": "hash123",
    })

    # Query the updated metadata to verify
    metadata_query = _query({
        "@type": "/cosmos.bank.v1beta1.QueryDenomMetadataRequest",
        "denom": name,
    })

    return {
        "set_uri_result": set_uri_result,
        "metadata": metadata_query,
    }


def demo_set_denom_uri_new_metadata(name, owner, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Register name and set destination
    _register_root_name(name, owner)

    # Set URI directly without pre-existing metadata - this tests ensureDenomMetadata path
    # and the default Symbol/Name setting
    set_uri_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDenomURI",
        "name_destination": owner,
        "denom": name,
        "uri": "https://example.com/new-" + name,
        "uri_hash": "",
    })

    # Query the updated metadata to verify
    metadata_query = _query({
        "@type": "/cosmos.bank.v1beta1.QueryDenomMetadataRequest",
        "denom": name,
    })

    return {
        "set_uri_result": set_uri_result,
        "metadata": metadata_query,
    }


def demo_set_denom_uri_empty_uri_hash(name, owner, alice_addr):
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

    # Set URI with empty URI hash
    set_uri_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDenomURI",
        "name_destination": owner,
        "denom": name,
        "uri": "https://example.com/empty-hash-" + name,
        "uri_hash": "",
    })

    # Query the updated metadata to verify
    metadata_query = _query({
        "@type": "/cosmos.bank.v1beta1.QueryDenomMetadataRequest",
        "denom": name,
    })

    return {
        "set_uri_result": set_uri_result,
        "metadata": metadata_query,
    }
"""


def get_test_address(dysond, seed="0x123456"):
    """Generate a test address using address-bytes-to-string."""
    address_result = dysond("q", "auth", "address-bytes-to-string", seed, "-o", "json")
    return address_result["address_string"]


def test_set_denom_uri_existing_metadata(chainnet):
    """Test setting URI on existing metadata with Symbol and Name already set."""
    dysond = chainnet[0]

    # Get gov address for authority (needed for SetDenomMetadata)
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
        "demo_set_denom_uri_existing_metadata",
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

    # Verify SetDenomURI succeeded
    assert (
        script_result["set_uri_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetDenomURI failed: {script_result['set_uri_result']}"

    # Verify the URI was set correctly and existing fields preserved
    metadata = script_result["metadata"]
    base_name = name[:-4]  # Remove .dys suffix
    display_name = base_name
    symbol_name = base_name.upper()

    assert metadata["metadata"]["base"] == name
    assert metadata["metadata"]["display"] == display_name
    assert metadata["metadata"]["symbol"] == symbol_name  # Should be preserved
    assert metadata["metadata"]["name"] == "Test " + name + " Token"  # Should be preserved
    assert metadata["metadata"]["uri"] == "https://example.com/" + name
    assert metadata["metadata"]["uri_hash"] == "hash123"


def test_set_denom_uri_new_metadata(chainnet):
    """Test setting URI on new metadata, triggering ensureDenomMetadata and default Symbol/Name setting."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    name = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x222222")

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
        "demo_set_denom_uri_new_metadata",
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

    # Verify SetDenomURI succeeded
    assert (
        script_result["set_uri_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetDenomURI failed: {script_result['set_uri_result']}"

    # Verify the URI was set and default Symbol/Name were applied
    metadata = script_result["metadata"]
    base_name = name[:-4]  # Remove .dys suffix

    assert metadata["metadata"]["base"] == name
    assert metadata["metadata"]["display"] == base_name  # Default from ensureDenomMetadata
    assert metadata["metadata"]["symbol"] == base_name  # Should be set to base name (line 30-32 in SetDenomURI)
    assert metadata["metadata"]["name"] == base_name.capitalize()  # Should be title-cased (line 34-36 in SetDenomURI, from ensureDenomMetadata)
    assert metadata["metadata"]["uri"] == "https://example.com/new-" + name
    assert metadata["metadata"]["uri_hash"] == ""


def test_set_denom_uri_empty_uri_hash(chainnet):
    """Test setting URI with empty URI hash."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    name = f"test{secrets.token_hex(4)}.dys"
    owner = get_test_address(dysond, "0x333333")

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
        "demo_set_denom_uri_empty_uri_hash",
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

    # Verify SetDenomURI succeeded
    assert (
        script_result["set_uri_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetDenomURI failed: {script_result['set_uri_result']}"

    # Verify the URI was set correctly with empty hash
    metadata = script_result["metadata"]
    assert metadata["metadata"]["uri"] == "https://example.com/empty-hash-" + name
    assert metadata["metadata"]["uri_hash"] == ""
