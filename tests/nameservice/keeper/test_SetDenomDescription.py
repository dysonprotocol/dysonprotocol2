"""
Test SetDenomDescription message handler for nameservice keeper.

Tests the SetDenomDescription functionality which allows name owners to set
the description field of bank denom metadata for denoms they control.
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


def demo_set_denom_description(name, owner, description, alice_addr):
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

    # Set denom description
    set_desc_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDenomDescription",
        "name_destination": owner,
        "denom": name,
        "description": description,
    })

    # Query the updated metadata to verify
    metadata_query = _query({
        "@type": "/cosmos.bank.v1beta1.QueryDenomMetadataRequest",
        "denom": name,
    })

    return {
        "set_desc_result": set_desc_result,
        "metadata": metadata_query,
    }
"""


def get_test_address(dysond, seed="0x123456"):
    """Generate a test address using address-bytes-to-string."""
    address_result = dysond("q", "auth", "address-bytes-to-string", seed, "-o", "json")
    return address_result["address_string"]


def test_set_denom_description_success(chainnet):
    """Test successful denom description setting by authorized owner."""
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
    description = "This is a test description for the denom metadata."

    # Execute script
    kwargs = json.dumps({
        "name": name,
        "owner": owner,
        "description": description,
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
        "demo_set_denom_description",
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

    # Verify SetDenomDescription succeeded
    assert (
        script_result["set_desc_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetDenomDescription failed: {script_result['set_desc_result']}"

    # Verify the description was set correctly
    metadata = script_result["metadata"]
    assert metadata["metadata"]["description"] == description, (
        f"Expected description '{description}', got '{metadata['metadata']['description']}'"
    )

    # Verify denom metadata structure
    assert metadata["metadata"]["base"] == name
    assert metadata["metadata"]["display"] == name.replace(".dys", "")
    assert metadata["metadata"]["symbol"] == name.replace(".dys", "")
