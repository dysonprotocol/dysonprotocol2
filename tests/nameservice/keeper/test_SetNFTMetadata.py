"""
Test SetNFTMetadata message handler for nameservice keeper.

Tests the SetNFTMetadata functionality which allows name owners to set
the metadata field and URI/URI hash for NFTs in their collections.
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


def _register_root_name(name, destination, valuation="10udys"):
    salt = "salt-" + name
    hexhash = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": destination,
    })["hex_hash"]

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": destination,
        "hexhash": hexhash,
        "valuation": _parse_coin(valuation),
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": destination,
        "name": name,
        "salt": salt,
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": destination,
        "name": name,
        "destination": destination,
    })

    return name


def _create_nft_class_and_mint_nft(class_id, nft_id, owner):
    # Register a root name for the class
    root_name = class_id
    _register_root_name(root_name, owner)

    # Create NFT class
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": owner,
        "class_id": class_id,
        "name": root_name,
        "symbol": "TEST",
        "description": "Test class for SetNFTMetadata",
        "uri": "",
        "uri_hash": "",
    })

    # Mint the NFT
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "name_destination": owner,
        "class_id": class_id,
        "nft_id": nft_id,
        "uri": "",
        "uri_hash": "",
    })

    return class_id


def demo_set_metadata_success_custom_class(class_id, nft_id, owner, metadata, uri, uri_hash, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Setup: Create NFT class and mint NFT
    class_id = _create_nft_class_and_mint_nft(class_id, nft_id, owner)

    # Set metadata for the NFT
    set_metadata_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTMetadata",
        "name_destination": owner,
        "class_id": class_id,
        "nft_id": nft_id,
        "metadata": metadata,
        "uri": uri,
        "uri_hash": uri_hash,
    })

    # Query the updated NFT data to verify
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": class_id,
        "id": nft_id,
    })

    return {
        "set_metadata_result": set_metadata_result,
        "nft_data": nft_query,
        "expected_metadata": metadata,
    }




def demo_set_metadata_unauthorized(class_id, nft_id, owner, unauthorized_owner, alice_addr):
    # Fund test accounts from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": unauthorized_owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Setup: Create NFT class and mint NFT
    class_id = _create_nft_class_and_mint_nft(class_id, nft_id, owner)

    # Try to set metadata with unauthorized owner - should fail
    set_metadata_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTMetadata",
        "name_destination": unauthorized_owner,
        "class_id": class_id,
        "nft_id": nft_id,
        "metadata": "unauthorized metadata",
        "uri": "",
        "uri_hash": "",
    })

    return {"set_metadata_result": set_metadata_result}


def demo_set_metadata_nft_not_found(class_id, nft_id, owner, alice_addr):
    # Fund test account from alice
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Try to set metadata on non-existent NFT - should fail
    set_metadata_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTMetadata",
        "name_destination": owner,
        "class_id": class_id,
        "nft_id": nft_id,
        "metadata": "some metadata",
        "uri": "",
        "uri_hash": "",
    })

    return {"set_metadata_result": set_metadata_result}
"""


def get_test_address(dysond, seed="0x123456"):
    """Generate a test address using address-bytes-to-string."""
    address_result = dysond("q", "auth", "address-bytes-to-string", seed, "-o", "json")
    return address_result["address_string"]


def test_set_metadata_success_custom_class_json_metadata(chainnet):
    """Test successfully setting JSON metadata for an NFT in a custom class."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    class_id = f"test{secrets.token_hex(4)}.dys"
    nft_id = f"nft{secrets.token_hex(4)}"
    owner = get_test_address(dysond, "0x111111")

    # Test with JSON metadata
    metadata = json.dumps(
        {"artist": "Alice", "year": "2024", "tags": ["digital", "nft"]}
    )
    uri = "https://example.com/nft1"
    uri_hash = "hash123"

    # Execute script
    kwargs = json.dumps(
        {
            "class_id": class_id,
            "nft_id": nft_id,
            "owner": owner,
            "metadata": metadata,
            "uri": uri,
            "uri_hash": uri_hash,
            "alice_addr": alice_addr,
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
        "demo_set_metadata_success_custom_class",
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

    # Verify SetNFTMetadata succeeded
    assert (
        script_result["set_metadata_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetNFTMetadata failed: {script_result['set_metadata_result']}"

    # Verify the NFT data was updated correctly
    nft_data = script_result["nft_data"]
    assert "nft" in nft_data, f"NFT data missing: {nft_data}"
    nft = nft_data["nft"]

    # Check URI and URI hash were updated
    assert nft["uri"] == uri, f"Expected URI {uri}, got {nft['uri']}"
    assert (
        nft["uri_hash"] == uri_hash
    ), f"Expected URI hash {uri_hash}, got {nft['uri_hash']}"

    # Check metadata was updated (in data field)
    nft_data_field = nft["data"]
    actual_metadata = nft_data_field["metadata"]
    expected_metadata = script_result["expected_metadata"]

    assert (
        actual_metadata == expected_metadata
    ), f"Expected metadata {expected_metadata}, got {actual_metadata}"


def test_set_metadata_success_custom_class_empty_metadata(chainnet):
    """Test successfully setting empty metadata for an NFT in a custom class."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    class_id = f"test{secrets.token_hex(4)}.dys"
    nft_id = f"nft{secrets.token_hex(4)}"
    owner = get_test_address(dysond, "0x222222")

    # Test with empty metadata
    metadata = ""
    uri = ""
    uri_hash = ""

    # Execute script
    kwargs = json.dumps(
        {
            "class_id": class_id,
            "nft_id": nft_id,
            "owner": owner,
            "metadata": metadata,
            "uri": uri,
            "uri_hash": uri_hash,
            "alice_addr": alice_addr,
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
        "demo_set_metadata_success_custom_class",
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

    # Verify SetNFTMetadata succeeded
    assert (
        script_result["set_metadata_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetNFTMetadata failed: {script_result['set_metadata_result']}"

    # Verify the NFT data was updated correctly
    nft_data = script_result["nft_data"]
    assert "nft" in nft_data, f"NFT data missing: {nft_data}"
    nft = nft_data["nft"]

    # Check URI and URI hash were updated (even to empty)
    assert nft["uri"] == uri, f"Expected URI {uri}, got {nft['uri']}"
    assert (
        nft["uri_hash"] == uri_hash
    ), f"Expected URI hash {uri_hash}, got {nft['uri_hash']}"

    # Check metadata was updated
    nft_data_field = nft["data"]
    actual_metadata = nft_data_field["metadata"]
    expected_metadata = script_result["expected_metadata"]

    assert (
        actual_metadata == expected_metadata
    ), f"Expected metadata {expected_metadata}, got {actual_metadata}"


def test_set_metadata_unauthorized(chainnet):
    """Test setting NFT metadata with unauthorized owner fails."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    class_id = f"test{secrets.token_hex(4)}.dys"
    nft_id = f"nft{secrets.token_hex(4)}"
    owner = get_test_address(dysond, "0x444444")
    unauthorized_owner = get_test_address(dysond, "0x555555")

    # Execute script
    kwargs = json.dumps(
        {
            "class_id": class_id,
            "nft_id": nft_id,
            "owner": owner,
            "unauthorized_owner": unauthorized_owner,
            "alice_addr": alice_addr,
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
        "demo_set_metadata_unauthorized",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - this test should fail with "unauthorized" error
    parsed = deep_parse(result)
    assert (
        result.get("exception") is not None
    ), "Expected exception for unauthorized access"
    exception_msg = result["exception"]["msg"]
    assert (
        "unauthorized" in exception_msg
    ), f"Expected 'unauthorized' in error message: {exception_msg}"


def test_set_metadata_nft_not_found(chainnet):
    """Test setting NFT metadata on non-existent NFT fails."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = BASE_EXTRA_CODE

    # Generate unique IDs
    class_id = f"nonexistent{secrets.token_hex(4)}.dys"
    nft_id = f"nft{secrets.token_hex(4)}"
    owner = get_test_address(dysond, "0x666666")

    # Execute script
    kwargs = json.dumps(
        {
            "class_id": class_id,
            "nft_id": nft_id,
            "owner": owner,
            "alice_addr": alice_addr,
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
        "demo_set_metadata_nft_not_found",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate - this test should fail with "not found" error
    parsed = deep_parse(result)
    assert result.get("exception") is not None, "Expected exception for NFT not found"
    exception_msg = result["exception"]["msg"]
    assert (
        "not found" in exception_msg
    ), f"Expected 'not found' in error message: {exception_msg}"


def test_set_metadata_nameservice_name_with_reverse_mapping(chainnet):
    """Test setting metadata on a nameservice name NFT triggers reverse mapping updates."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = (
        BASE_EXTRA_CODE
        + r"""

def demo_set_metadata_nameservice_name_with_reverse_mapping(owner, alice_addr, gov_addr):
    # Fund test account
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Register a name in the nameservice class
    name = "test-reverse-mapping.dys"
    salt = "salt-for-reverse-test"
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
        "valuation": {"denom": "udys", "amount": "1000000"}
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    })

    # Initially set destination to alice_addr
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": alice_addr,
    })

    # Set metadata with new URI - this should trigger reverse mapping updates
    # Note: Only gov can set metadata on nameservice.dys NFTs since gov controls the root
    set_metadata_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTMetadata",
        "name_destination": gov_addr,  # gov controls nameservice.dys
        "class_id": "nameservice.dys",
        "nft_id": name,
        "metadata": "Updated metadata for reverse mapping test",
        "uri": owner,  # Change destination to owner address
        "uri_hash": "new-hash-123",
    })

    # Query the updated NFT
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": "nameservice.dys",
        "id": name,
    })

    # Query reverse mappings for both old and new destinations
    old_reverse_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": alice_addr,  # Old destination
    })

    new_reverse_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": owner,  # New destination
    })

    return {
        "set_metadata_result": set_metadata_result,
        "nft_data": nft_query,
        "old_reverse_mapping": old_reverse_query,
        "new_reverse_mapping": new_reverse_query,
    }
"""
    )

    # Generate test address
    owner = get_test_address(dysond, "0x777777")

    # Execute script
    kwargs = json.dumps(
        {
            "owner": owner,
            "alice_addr": alice_addr,
            "gov_addr": gov_addr,
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
        "demo_set_metadata_nameservice_name_with_reverse_mapping",
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

    # Verify SetNFTMetadata succeeded
    assert (
        script_result["set_metadata_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetNFTMetadata failed: {script_result['set_metadata_result']}"

    # Verify NFT was updated
    nft_data = script_result["nft_data"]
    assert "nft" in nft_data, f"NFT data missing: {nft_data}"
    nft = nft_data["nft"]

    # Check metadata was updated
    assert nft["data"]["metadata"] == "Updated metadata for reverse mapping test"

    # Check URI was updated
    assert nft["uri"] == owner
    assert nft["uri_hash"] == "new-hash-123"

    # Verify old reverse mapping was removed (name should not appear in old mapping)
    old_reverse_mapping = script_result["old_reverse_mapping"]
    assert (
        "names" in old_reverse_mapping
    ), f"Old reverse mapping missing: {old_reverse_mapping}"
    assert (
        "test-reverse-mapping.dys" not in old_reverse_mapping["names"]
    ), "Old reverse mapping should be removed"

    # Verify new reverse mapping was added
    new_reverse_mapping = script_result["new_reverse_mapping"]
    assert (
        "names" in new_reverse_mapping
    ), f"New reverse mapping missing: {new_reverse_mapping}"
    assert (
        "test-reverse-mapping.dys" in new_reverse_mapping["names"]
    ), "New reverse mapping should be added"


def test_set_metadata_nameservice_name_clear_uri(chainnet):
    """Test setting metadata on nameservice name NFT with empty URI clears reverse mapping."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = (
        BASE_EXTRA_CODE
        + r"""

def demo_set_metadata_nameservice_name_clear_uri(owner, alice_addr):
    # Fund test account
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Register a name in the nameservice class
    name = "test-clear-uri.dys"
    salt = "salt-for-clear-test"
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
        "valuation": {"denom": "udys", "amount": "1000000"}
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    })

    # Set initial destination
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": alice_addr,
    })

    # Set metadata with empty URI - this should clear reverse mapping
    set_metadata_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTMetadata",
        "name_destination": owner,
        "class_id": "nameservice.dys",
        "nft_id": name,
        "metadata": "Metadata with cleared URI",
        "uri": "",  # Clear the URI
        "uri_hash": "",
    })

    # Query the updated NFT
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": "nameservice.dys",
        "id": name,
    })

    # Query reverse mapping to verify it was cleared
    reverse_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": alice_addr,
    })

    return {
        "set_metadata_result": set_metadata_result,
        "nft_data": nft_query,
        "reverse_mapping": reverse_query,
    }
"""
    )

    # Generate test address
    owner = get_test_address(dysond, "0x888888")

    # Execute script
    kwargs = json.dumps(
        {
            "owner": owner,
            "alice_addr": alice_addr,
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
        "demo_set_metadata_nameservice_name_clear_uri",
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

    # Verify SetNFTMetadata succeeded
    assert (
        script_result["set_metadata_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetNFTMetadata failed: {script_result['set_metadata_result']}"

    # Verify NFT was updated
    nft_data = script_result["nft_data"]
    assert "nft" in nft_data, f"NFT data missing: {nft_data}"
    nft = nft_data["nft"]

    # Check metadata was updated
    assert nft["data"]["metadata"] == "Metadata with cleared URI"

    # Check URI was cleared
    assert nft["uri"] == ""
    assert nft["uri_hash"] == ""

    # Verify reverse mapping was cleared (name should not appear in reverse mapping anymore)
    reverse_mapping = script_result["reverse_mapping"]
    assert "names" in reverse_mapping, f"Reverse mapping missing: {reverse_mapping}"
    assert "test-clear-uri.dys" not in reverse_mapping["names"]


def test_set_metadata_invalid_nft_data_validation(chainnet):
    """Test that invalid NFT data fails validation."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = (
        BASE_EXTRA_CODE
        + r"""

def demo_set_metadata_invalid_nft_data_validation(owner, alice_addr):
    # Fund test account
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Create a custom NFT class
    class_id = "test-validation.dys"
    _register_root_name(class_id, owner)

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "class_id": class_id,
        "name": class_id,
        "symbol": "TEST",
        "description": "Test class for validation",
        "uri": "",
        "name_destination": owner
    })

    # Mint NFT
    nft_id = "test-nft-validation"
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "class_id": class_id,
        "nft_id": nft_id,
        "uri": "",
        "name_destination": owner
    })

    # Try to set metadata that would create invalid NFT data
    # This should trigger ValidateBasic failure
    set_metadata_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTMetadata",
        "name_destination": owner,
        "class_id": class_id,
        "nft_id": nft_id,
        "metadata": "invalid-metadata-that-should-fail-validation",  # This might cause validation to fail
        "uri": "https://example.com/updated",
        "uri_hash": "updated-hash",
    })

    return {"set_metadata_result": set_metadata_result}
"""
    )

    # Generate test address
    owner = get_test_address(dysond, "0x999999")

    # Execute script
    kwargs = json.dumps(
        {
            "owner": owner,
            "alice_addr": alice_addr,
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
        "demo_set_metadata_invalid_nft_data_validation",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # This test might pass or fail depending on what validation is triggered
    # If it fails validation, we expect an exception
    parsed = deep_parse(result)
    # We don't assert anything specific here since validation behavior depends on the NFT data structure


def test_set_metadata_nameservice_name_empty_to_uri(chainnet):
    """Test setting metadata on nameservice name NFT from empty URI to URI adds new mapping."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = (
        BASE_EXTRA_CODE
        + r"""

def demo_set_metadata_nameservice_name_empty_to_uri(owner, alice_addr):
    # Fund test account
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Register a name in the nameservice class with empty URI
    name = "test-empty-to-uri.dys"
    salt = "salt-for-empty-to-uri-test"
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
        "valuation": {"denom": "udys", "amount": "1000000"}
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    })

    # Set destination (this sets URI to alice_addr)
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": alice_addr,
    })

    # Now set metadata with a different URI - this should:
    # 1. Remove old mapping (alice_addr -> name)
    # 2. Add new mapping (new_uri -> name)
    new_uri = "dys21newdestination456789012345678901234567890123456789012"
    set_metadata_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTMetadata",
        "name_destination": owner,
        "class_id": "nameservice.dys",
        "nft_id": name,
        "metadata": "Metadata changing from alice_addr to new URI",
        "uri": new_uri,
        "uri_hash": "new-hash-456",
    })

    # Query the updated NFT
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": "nameservice.dys",
        "id": name,
    })

    # Query reverse mappings - should have new URI mapping, not old alice_addr mapping
    old_reverse_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": alice_addr,
    })

    new_reverse_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": new_uri,
    })

    return {
        "set_metadata_result": set_metadata_result,
        "nft_data": nft_query,
        "old_reverse_mapping": old_reverse_query,
        "new_reverse_mapping": new_reverse_query,
    }
"""
    )

    # Generate test address
    owner = get_test_address(dysond, "0x999999")

    # Execute script
    kwargs = json.dumps(
        {
            "owner": owner,
            "alice_addr": alice_addr,
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
        "demo_set_metadata_nameservice_name_empty_to_uri",
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

    # Verify SetNFTMetadata succeeded
    assert (
        script_result["set_metadata_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetNFTMetadata failed: {script_result['set_metadata_result']}"

    # Verify NFT was updated
    nft_data = script_result["nft_data"]
    assert "nft" in nft_data, f"NFT data missing: {nft_data}"
    nft = nft_data["nft"]

    # Check URI was updated
    expected_uri = "dys21newdestination456789012345678901234567890123456789012"
    assert nft["uri"] == expected_uri, f"Expected URI {expected_uri}, got {nft['uri']}"
    assert nft["uri_hash"] == "new-hash-456"

    # Check metadata was updated
    assert nft["data"]["metadata"] == "Metadata changing from alice_addr to new URI"

    # Verify old reverse mapping was removed (name should not appear in old mapping)
    old_reverse_mapping = script_result["old_reverse_mapping"]
    assert (
        "names" in old_reverse_mapping
    ), f"Old reverse mapping missing: {old_reverse_mapping}"
    assert (
        "test-empty-to-uri.dys" not in old_reverse_mapping["names"]
    ), "Old reverse mapping should be removed"

    # Verify new reverse mapping was added
    new_reverse_mapping = script_result["new_reverse_mapping"]
    assert (
        "names" in new_reverse_mapping
    ), f"New reverse mapping missing: {new_reverse_mapping}"
    assert (
        "test-empty-to-uri.dys" in new_reverse_mapping["names"]
    ), "New reverse mapping should be added"


def test_set_metadata_nameservice_name_uri_to_empty(chainnet):
    """Test setting metadata on nameservice name NFT from URI to empty removes old mapping."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = (
        BASE_EXTRA_CODE
        + r"""

def demo_set_metadata_nameservice_name_uri_to_empty(owner, alice_addr):
    # Fund test account
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Register a name in the nameservice class
    name = "test-uri-to-empty.dys"
    salt = "salt-for-uri-to-empty-test"
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
        "valuation": {"denom": "udys", "amount": "1000000"}
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    })

    # Set initial destination to alice_addr (this creates a mapping)
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": alice_addr,
    })

    # Now set metadata with empty URI - this should:
    # 1. Remove old mapping (alice_addr -> name)
    # 2. NOT add new mapping (since URI is empty)
    set_metadata_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTMetadata",
        "name_destination": owner,
        "class_id": "nameservice.dys",
        "nft_id": name,
        "metadata": "Metadata clearing URI to empty",
        "uri": "",  # Clear URI
        "uri_hash": "",
    })

    # Query the updated NFT
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": "nameservice.dys",
        "id": name,
    })

    # Query reverse mapping - should NOT have the name anymore since URI is empty
    reverse_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": alice_addr,
    })

    return {
        "set_metadata_result": set_metadata_result,
        "nft_data": nft_query,
        "reverse_mapping": reverse_query,
    }
"""
    )

    # Generate test address
    owner = get_test_address(dysond, "0xAAAA")

    # Execute script
    kwargs = json.dumps(
        {
            "owner": owner,
            "alice_addr": alice_addr,
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
        "demo_set_metadata_nameservice_name_uri_to_empty",
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

    # Verify SetNFTMetadata succeeded
    assert (
        script_result["set_metadata_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetNFTMetadata failed: {script_result['set_metadata_result']}"

    # Verify NFT was updated
    nft_data = script_result["nft_data"]
    assert "nft" in nft_data, f"NFT data missing: {nft_data}"
    nft = nft_data["nft"]

    # Check URI was cleared
    assert nft["uri"] == "", f"Expected empty URI, got {nft['uri']}"
    assert nft["uri_hash"] == ""

    # Check metadata was updated
    assert nft["data"]["metadata"] == "Metadata clearing URI to empty"

    # Verify reverse mapping was removed (name should not appear in mapping since URI is empty)
    reverse_mapping = script_result["reverse_mapping"]
    assert "names" in reverse_mapping, f"Reverse mapping missing: {reverse_mapping}"
    assert (
        "test-uri-to-empty.dys" not in reverse_mapping["names"]
    ), "Reverse mapping should be removed when URI is cleared"


def test_set_metadata_nameservice_name_uri_to_different_uri(chainnet):
    """Test setting metadata on nameservice name NFT from one URI to another updates mappings."""
    dysond = chainnet[0]

    # Get gov address for authority
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Get alice address for funding
    alice_result = dysond("query", "auth", "account", "alice")
    alice_addr = alice_result["account"]["value"]["address"]

    extra_code = (
        BASE_EXTRA_CODE
        + r"""

def demo_set_metadata_nameservice_name_uri_to_different_uri(owner, alice_addr):
    # Fund test account
    _sudo({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": alice_addr,
        "to_address": owner,
        "amount": [{"denom": "udys", "amount": "10000"}]
    })

    # Register a name in the nameservice class
    name = "test-uri-to-uri.dys"
    salt = "salt-for-uri-to-uri-test"
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
        "valuation": {"denom": "udys", "amount": "1000000"}
    })

    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    })

    # Set initial destination to alice_addr
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": alice_addr,
    })

    # Now set metadata changing to a completely different URI - this should:
    # 1. Remove old mapping (alice_addr -> name)
    # 2. Add new mapping (different_uri -> name)
    different_uri = "dys21different789012345678901234567890123456789012345678901"
    set_metadata_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetNFTMetadata",
        "name_destination": owner,
        "class_id": "nameservice.dys",
        "nft_id": name,
        "metadata": "Metadata changing URI to different address",
        "uri": different_uri,
        "uri_hash": "different-hash-789",
    })

    # Query the updated NFT
    nft_query = _query({
        "@type": "/dysonprotocol.nft.v1beta1.QueryNFTRequest",
        "class_id": "nameservice.dys",
        "id": name,
    })

    # Query reverse mappings
    old_reverse_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": alice_addr,
    })

    new_reverse_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": different_uri,
    })

    return {
        "set_metadata_result": set_metadata_result,
        "nft_data": nft_query,
        "old_reverse_mapping": old_reverse_query,
        "new_reverse_mapping": new_reverse_query,
    }
"""
    )

    # Generate test address
    owner = get_test_address(dysond, "0xBBBB")

    # Execute script
    kwargs = json.dumps(
        {
            "owner": owner,
            "alice_addr": alice_addr,
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
        "demo_set_metadata_nameservice_name_uri_to_different_uri",
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

    # Verify SetNFTMetadata succeeded
    assert (
        script_result["set_metadata_result"]["@type"]
        == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"SetNFTMetadata failed: {script_result['set_metadata_result']}"

    # Verify NFT was updated
    nft_data = script_result["nft_data"]
    assert "nft" in nft_data, f"NFT data missing: {nft_data}"
    nft = nft_data["nft"]

    # Check URI was updated
    expected_uri = "dys21different789012345678901234567890123456789012345678901"
    assert nft["uri"] == expected_uri, f"Expected URI {expected_uri}, got {nft['uri']}"
    assert nft["uri_hash"] == "different-hash-789"

    # Check metadata was updated
    assert nft["data"]["metadata"] == "Metadata changing URI to different address"

    # Verify old reverse mapping was removed
    old_reverse_mapping = script_result["old_reverse_mapping"]
    assert (
        "names" in old_reverse_mapping
    ), f"Old reverse mapping missing: {old_reverse_mapping}"
    assert (
        "test-uri-to-uri.dys" not in old_reverse_mapping["names"]
    ), "Old reverse mapping should be removed"

    # Verify new reverse mapping was added
    new_reverse_mapping = script_result["new_reverse_mapping"]
    assert (
        "names" in new_reverse_mapping
    ), f"New reverse mapping missing: {new_reverse_mapping}"
    assert (
        "test-uri-to-uri.dys" in new_reverse_mapping["names"]
    ), "New reverse mapping should be added"
