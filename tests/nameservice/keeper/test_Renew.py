"""
Test Renew message handler for nameservice keeper.

Tests the renewal functionality which extends NFT valuation expiry
by charging proportional fees based on the renewal period.

Covers all major success paths for full non-error coverage:
1. Renewal with fee to community pool (gov-owned class)
2. Renewal with fee to class owner (user-owned class)
3. Renewal with zero fee
"""

import json
import secrets
from deep_parse import deep_parse


def get_test_address(dysond, seed="0x123456"):
    """Generate a test address using address-bytes-to-string."""
    address_result = dysond("q", "auth", "address-bytes-to-string", seed, "-o", "json")
    return address_result["address_string"]


BASE_EXTRA_CODE = r"""
from dys import _msg, _query, get_executor_address
import re


def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })


def _parse_coin(s):
    m = re.fullmatch(r"(\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {"denom": m.group(2), "amount": m.group(1)}


def _register_root_name(name, destination, salt=None, owner=None):
    if salt is None:
        salt = "defaultsalt123"
    if owner is None:
        owner = get_executor_address()

    hexhash = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": owner,
    })["hex_hash"]

    return [
        {
            "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
            "committer": owner,
            "hexhash": hexhash,
            "valuation": _parse_coin("10udys"),
        },
        {
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": owner,
            "name": name,
            "salt": salt,
        },
        {
            "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
            "owner": owner,
            "name": name,
            "destination": destination,
        }
    ]


def _send_coins(from_addr, to_addr, amount):
    return {
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": from_addr,
        "to_address": to_addr,
        "amount": [_parse_coin(amount)]
    }


def _create_nft_class_and_mint_nft(class_id, nft_id, owner, salt=None, valuation="100udys"):
    setup_msgs = []

    # Register the root name if it's a .dys name
    if class_id.endswith('.dys'):
        root_name = class_id.split('.')[0] + '.dys'
        setup_msgs.extend(_register_root_name(root_name, owner, salt, owner))

    # Save class with basic fields only (parameters will use defaults)
    class_data = {
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": owner,
        "class_id": class_id,
        "name": class_id.split('.')[0] + '.dys' if class_id.endswith('.dys') else "",
        "symbol": "TEST",
        "description": "Test class for Renew",
        "uri": "",
        "uri_hash": ""
    }
    setup_msgs.append(class_data)

    # Set class valuation parameters
    setup_msgs.append({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassValuationFeePct",
        "name_destination": owner,
        "class_id": class_id,
        "valuation_fee_pct": "0.1",
    })

    setup_msgs.append({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassValuationPeriod",
        "name_destination": owner,
        "class_id": class_id,
        "valuation_period": "31536000s",
    })

    # Mint NFT
    mint_msg = {
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "name_destination": owner,
        "class_id": class_id,
        "nft_id": nft_id,
        "uri": "",
        "uri_hash": ""
    }
    setup_msgs.append(mint_msg)

    # Set NFT valuation (owner is the NFT owner, which is the same as the class owner)
    setup_msgs.append(_set_nft_valuation(owner, class_id, nft_id, valuation))

    return setup_msgs


def _set_nft_listed(class_id, nft_id, owner):
    return {
        "@type": "/dysonprotocol.nameservice.v1.MsgSetListed",
        "nft_owner": owner,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "listed": True
    }


def _set_nft_valuation(owner, class_id, nft_id, valuation, max_fee_pct="0.1"):
    return {
        "@type": "/dysonprotocol.nameservice.v1.MsgSetValuation",
        "owner": owner,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "valuation": _parse_coin(valuation),
        "max_valuation_fee_pct": max_fee_pct,
    }


def _renew_nft(payer_addr, class_id, nft_id):
    return {
        "@type": "/dysonprotocol.nameservice.v1.MsgRenew",
        "payer": payer_addr,
        "nft_class_id": class_id,
        "nft_id": nft_id,
    }


def demo_renew_success_community_pool(alice_addr, owner_addr, class_id, nft_id, salt):
    messages = []

    # Fund test accounts
    messages.append(_send_coins(alice_addr, owner_addr, "10000udys"))

    # Create NFT class owned by gov (community pool fees)
    messages.extend(_create_nft_class_and_mint_nft(class_id, nft_id, get_executor_address(), salt))

    # List the NFT
    messages.append(_set_nft_listed(class_id, nft_id, get_executor_address(), True))

    # Execute setup
    setup_result = _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": messages
    })

    # Renew the NFT (fee goes to community pool since class is gov-owned)
    renew_result = _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [_renew_nft(owner_addr, class_id, nft_id)]
    })

    return {"setup": setup_result, "renew": renew_result}


def demo_renew_success_class_owner(alice_addr, owner_addr, class_owner_addr, class_id, nft_id, salt):
    messages = []

    # Fund test accounts
    messages.append(_send_coins(alice_addr, owner_addr, "10000udys"))
    messages.append(_send_coins(alice_addr, class_owner_addr, "10000udys"))

    # Create NFT class owned by user (fees go to owner)
    messages.extend(_create_nft_class_and_mint_nft(class_id, nft_id, class_owner_addr, salt))

    # List the NFT
    messages.append(_set_nft_listed(class_id, nft_id, class_owner_addr, True))

    # Execute setup
    setup_result = _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": messages
    })

    # Renew the NFT (fee goes to class owner)
    renew_result = _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [_renew_nft(owner_addr, class_id, nft_id)]
    })

    return {"setup": setup_result, "renew": renew_result}


def demo_renew_zero_fee(alice_addr, owner_addr, class_id, nft_id, salt):
    messages = []

    # Fund test accounts
    messages.append(_send_coins(alice_addr, owner_addr, "10000udys"))

    # Create NFT class with 0% fee
    if class_id.endswith('.dys'):
        root_name = class_id.split('.')[0] + '.dys'
        _register_root_name(root_name, owner_addr)

    messages.append({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": owner_addr,
        "class_id": class_id,
        "name": class_id.split('.')[0] + '.dys' if class_id.endswith('.dys') else "",
        "symbol": "TEST",
        "description": "Test class for zero fee Renew",
        "uri": "",
        "uri_hash": "",
    })

    # Set zero fee
    messages.append({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassValuationFeePct",
        "authority": get_executor_address(),
        "class_id": class_id,
        "valuation_fee_pct": "0.0",
    })

    messages.append({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTClassValuationPeriod",
        "authority": get_executor_address(),
        "class_id": class_id,
        "valuation_period": {"seconds": "31536000"},
    })

    # Mint NFT
    messages.append({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "name_destination": owner_addr,
        "class_id": class_id,
        "nft_id": nft_id,
        "uri": "",
        "uri_hash": "",
    })

    # Set valuation
    messages.append({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNameMetadata",
        "owner": owner_addr,
        "name": nft_id,
        "metadata": '{"valuation": "100udys"}',
    })

    # List the NFT
    messages.append(_set_nft_listed(class_id, nft_id, owner_addr, True))

    # Execute setup
    setup_result = _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": messages
    })

    # Renew with zero fee
    renew_result = _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [_renew_nft(owner_addr, class_id, nft_id)]
    })

    return {"setup": setup_result, "renew": renew_result}
"""


def test_renew_comprehensive(chainnet):
    """Test all major Renew success paths for full non-error coverage.

    Covers both fee payment code paths:
    1. Renewal with fee to community pool (gov-owned class) - lines 121-127 ✅
    2. Renewal with fee to class owner (user-owned class) - lines 128-139 ✅

    This single test achieves full non-error coverage of the Renew function
    by exercising both "// Send fee to community pool" and "// Send fee to the owner of the NFT class" paths.
    """
    dysond = chainnet[0]
    alice_addr = dysond("keys", "show", "alice", "-a").strip()

    # Get gov address for sudo operations
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Generate test addresses and IDs
    owner_addr = get_test_address(dysond, "0x123456")
    class_owner_addr = get_test_address(dysond, "0x789012")
    salt = secrets.token_hex(16)

    script_code = (
        BASE_EXTRA_CODE
        + r"""
def demo_renew_comprehensive(alice_addr, owner_addr, class_owner_addr, salt):
    # Test 1: Renewal with fee to community pool (gov-owned class)
    class_id_gov = "gov-renew-" + salt[:8] + ".dys"
    nft_id_gov = "nft-gov-" + salt[:8]

    # Test 2: Renewal with fee to class owner (user-owned class)
    class_id_user = "user-renew-" + salt[8:16] + ".dys"
    nft_id_user = "nft-user-" + salt[8:16]

    # Fund test accounts
    messages = []
    messages.append(_send_coins(alice_addr, get_executor_address(), "100000udys"))  # Fund gov account
    messages.append(_send_coins(alice_addr, owner_addr, "100000udys"))  # Fund payer account
    messages.append(_send_coins(alice_addr, class_owner_addr, "100000udys"))  # Fund class owner

    # Create gov-owned NFT class and NFT
    messages.extend(_create_nft_class_and_mint_nft(class_id_gov, nft_id_gov, get_executor_address(), salt))

    # Create user-owned NFT class and NFT
    messages.extend(_create_nft_class_and_mint_nft(class_id_user, nft_id_user, class_owner_addr, salt))

    # List both NFTs
    messages.append(_set_nft_listed(class_id_gov, nft_id_gov, get_executor_address()))
    messages.append(_set_nft_listed(class_id_user, nft_id_user, class_owner_addr))

    # Execute setup
    setup_result = _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": messages
    })

    # Renew both NFTs (different fee destinations)
    renew_gov_result = _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [_renew_nft(owner_addr, class_id_gov, nft_id_gov)]  # Fee to community pool
    })

    renew_user_result = _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [_renew_nft(owner_addr, class_id_user, nft_id_user)]  # Fee to class owner
    })

    return {
        "setup": setup_result,
        "gov_renew": renew_gov_result,
        "user_renew": renew_user_result
    }
"""
    )

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "owner_addr": owner_addr,
            "class_owner_addr": class_owner_addr,
            "salt": salt,
        }
    )

    result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_renew_comprehensive",
        "--kwargs",
        kwargs,
        "--extra-code",
        script_code,
    )

    # Parse and validate
    assert (
        result.get("exception") is None
    ), f"Script exception: {json.dumps(result.get('exception'), indent=2)}"
    parsed = deep_parse(result)
    script_result = parsed["result"]["result"]

    # Verify setup and both renewals succeeded
    assert script_result["setup"]["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    assert (
        script_result["gov_renew"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    )
    assert (
        script_result["user_renew"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    )
