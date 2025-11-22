"""
QueryNamesByDestination query handler coverage tests.

Tests the QueryNamesByDestination query endpoint which returns all names pointing to
a given destination address. Supports pagination and validates destination addresses.

Covers success paths (destination has names, no names), pagination (offset, key, reverse, count_total),
and error paths (empty destination, invalid destination, nil request).
All tests use stateless script query execution.
"""

import json
import pytest
import secrets
import re
from deep_parse import deep_parse


def test_query_names_by_destination_success(chainnet, generate_account):
    """Test QueryNamesByDestination successfully returns names for a destination."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    alice_name, alice_addr = generate_account("alice", faucet_amount=1_000_000)

    # Create multiple names pointing to alice_addr
    names = []
    for i in range(3):
        name_suffix = secrets.token_hex(4)
        names.append(f"test-{name_suffix}-{i}.dys")

    extra_code = f"""
from dys import _msg, _query, get_executor_address
import re

def _sudo(msg_dict):
    return _msg({{
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    }})

def _parse_coin(s):
    m = re.fullmatch(r"(\\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {{"denom": m.group(2), "amount": m.group(1)}}

def demo_query_names_by_destination(names, alice_addr):
    owner = get_executor_address()
    
    # Register names and set their destinations to alice_addr
    for name in names:
        salt = "salt" + name
        
        # Compute hash
        hexhash = _query({{
            "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
            "name": name,
            "salt": salt,
            "committer": owner,
        }})["hex_hash"]
        
        # Commit
        _sudo({{
            "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
            "committer": owner,
            "hexhash": hexhash,
            "valuation": _parse_coin("10udys"),
        }})
        
        # Reveal
        _sudo({{
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": owner,
            "name": name,
            "salt": salt,
        }})
        
        # Set destination to alice_addr
        _sudo({{
            "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
            "owner": owner,
            "name": name,
            "destination": alice_addr,
        }})
    
    # Query names by destination
    query_result = _query({{
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": alice_addr
    }})
    
    return {{
        "query_result": query_result
    }}
"""

    kwargs = json.dumps({"names": names, "alice_addr": alice_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_query_names_by_destination",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "query_result" in demo_result
    ), f"Result missing 'query_result' key. Keys: {list(demo_result.keys())}"

    query_resp = demo_result["query_result"]
    assert isinstance(
        query_resp, dict
    ), f"Query result should be dict, got {type(query_resp)}"
    assert (
        "names" in query_resp
    ), f"Query result missing 'names' key. Keys: {list(query_resp.keys())}"
    assert (
        "pagination" in query_resp
    ), f"Query result missing 'pagination' key. Keys: {list(query_resp.keys())}"

    names_list = query_resp["names"]
    assert isinstance(names_list, list), f"Names should be list, got {type(names_list)}"
    assert len(names_list) >= len(
        names
    ), f"Expected at least {len(names)} names, got {len(names_list)}"

    # Verify all created names are in the result
    names_set = set(names_list)
    for name in names:
        assert (
            name in names_set
        ), f"Name {name} not found in query result. Got: {names_list}"


def test_query_names_by_destination_no_names(chainnet, generate_account):
    """Test QueryNamesByDestination returns empty list for destination with no names."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    alice_name, alice_addr = generate_account("alice", faucet_amount=1_000_000)

    extra_code = f"""
from dys import _query

def demo_query_names_by_destination_no_names(alice_addr):
    # Query names for a destination that has no names
    query_result = _query({{
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": alice_addr
    }})
    
    return {{
        "query_result": query_result
    }}
"""

    kwargs = json.dumps({"alice_addr": alice_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_query_names_by_destination_no_names",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    query_resp = demo_result["query_result"]
    names_list = query_resp["names"]
    assert isinstance(names_list, list), f"Names should be list, got {type(names_list)}"
    assert len(names_list) == 0, f"Expected empty list, got {len(names_list)} names"


def test_query_names_by_destination_pagination_offset(chainnet, generate_account):
    """Test QueryNamesByDestination pagination with offset."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    alice_name, alice_addr = generate_account("alice", faucet_amount=1_000_000)

    # Create 5 names
    names = []
    for i in range(5):
        name_suffix = secrets.token_hex(4)
        names.append(f"test-{name_suffix}-{i}.dys")

    extra_code = f"""
from dys import _msg, _query, get_executor_address
import re

def _sudo(msg_dict):
    return _msg({{
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    }})

def _parse_coin(s):
    m = re.fullmatch(r"(\\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {{"denom": m.group(2), "amount": m.group(1)}}

def demo_query_names_pagination_offset(names, alice_addr):
    owner = get_executor_address()
    
    # Register names
    for name in names:
        salt = "salt" + name
        hexhash = _query({{
            "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
            "name": name,
            "salt": salt,
            "committer": owner,
        }})["hex_hash"]
        
        _sudo({{
            "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
            "committer": owner,
            "hexhash": hexhash,
            "valuation": _parse_coin("10udys"),
        }})
        
        _sudo({{
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": owner,
            "name": name,
            "salt": salt,
        }})
        
        _sudo({{
            "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
            "owner": owner,
            "name": name,
            "destination": alice_addr,
        }})
    
    # Query with pagination: limit 2, offset 1
    query_result = _query({{
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": alice_addr,
        "pagination": {{
            "limit": 2,
            "offset": 1
        }}
    }})
    
    return {{
        "query_result": query_result
    }}
"""

    kwargs = json.dumps({"names": names, "alice_addr": alice_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_query_names_pagination_offset",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    query_resp = demo_result["query_result"]
    names_list = query_resp["names"]
    assert isinstance(names_list, list), f"Names should be list, got {type(names_list)}"
    assert len(names_list) == 2, f"Expected 2 names with limit=2, got {len(names_list)}"

    pagination = query_resp["pagination"]
    assert isinstance(
        pagination, dict
    ), f"Pagination should be dict, got {type(pagination)}"


def test_query_names_by_destination_empty_destination(chainnet):
    """Test QueryNamesByDestination returns error for empty destination."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_query_names_empty_destination():
    try:
        query_result = _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
            "destination": ""
        })
        return {"error": "Should have failed", "result": query_result}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_query_names_empty_destination",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "expected" in demo_result
    ), f"Result missing 'expected' key. Keys: {list(demo_result.keys())}"
    assert (
        demo_result["expected"] is True
    ), f"Expected error handling, but got: {json.dumps(demo_result, indent=2)}"
    error_msg = demo_result.get("error", "")
    assert (
        "empty" in error_msg.lower()
    ), f"Error message should mention 'empty'. Got: {error_msg}"


def test_query_names_by_destination_invalid_destination(chainnet):
    """Test QueryNamesByDestination returns error for invalid destination."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_query_names_invalid_destination():
    try:
        query_result = _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
            "destination": "invalid-address-123"
        })
        return {"error": "Should have failed", "result": query_result}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_query_names_invalid_destination",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "expected" in demo_result
    ), f"Result missing 'expected' key. Keys: {list(demo_result.keys())}"
    assert (
        demo_result["expected"] is True
    ), f"Expected error handling, but got: {json.dumps(demo_result, indent=2)}"
    error_msg = demo_result.get("error", "")
    error_lower = error_msg.lower()
    assert (
        "valid" in error_lower
    ), f"Error message should mention 'valid'. Got: {error_msg}"


def test_query_names_by_destination_name_as_destination(chainnet, generate_account):
    """Test QueryNamesByDestination with destination as existing name (not Bech32 address)."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    alice_name, alice_addr = generate_account("alice", faucet_amount=1_000_000)

    # Create two names: source_name and dest_name
    source_name = f"test-source-{secrets.token_hex(4)}.dys"
    dest_name = f"test-dest-{secrets.token_hex(4)}.dys"

    extra_code = f"""
from dys import _msg, _query, get_executor_address
import re

def _sudo(msg_dict):
    return _msg({{
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    }})

def _parse_coin(s):
    m = re.fullmatch(r"(\\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {{"denom": m.group(2), "amount": m.group(1)}}

def demo_query_names_name_as_destination(source_name, dest_name):
    owner = get_executor_address()

    # Register both names
    for name in [source_name, dest_name]:
        salt = "salt" + name
        hexhash = _query({{
            "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
            "name": name,
            "salt": salt,
            "committer": owner,
        }})["hex_hash"]

        _sudo({{
            "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
            "committer": owner,
            "hexhash": hexhash,
            "valuation": _parse_coin("10udys"),
        }})

        _sudo({{
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": owner,
            "name": name,
            "salt": salt,
        }})

    # Set source_name's destination to dest_name (another name, not Bech32 address)
    _sudo({{
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": source_name,
        "destination": dest_name,
    }})

    # Query names pointing to dest_name
    query_result = _query({{
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": dest_name
    }})

    return {{
        "query_result": query_result
    }}
"""

    kwargs = json.dumps({"source_name": source_name, "dest_name": dest_name})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_query_names_name_as_destination",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    query_resp = demo_result["query_result"]
    names_list = query_resp["names"]
    assert isinstance(names_list, list), f"Names should be list, got {type(names_list)}"
    assert len(names_list) == 1, f"Expected 1 name, got {len(names_list)}"
    assert (
        source_name in names_list
    ), f"Source name {source_name} not found in result: {names_list}"


def test_query_names_by_destination_pagination_comprehensive(
    chainnet, generate_account
):
    """Test QueryNamesByDestination comprehensive pagination: offset, key, reverse, count_total."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    alice_name, alice_addr = generate_account("alice", faucet_amount=1_000_000)

    # Create 5 names pointing to alice_addr
    names = []
    for i in range(5):
        name_suffix = secrets.token_hex(4)
        names.append(f"test-{name_suffix}-{i}.dys")

    extra_code = f"""
from dys import _msg, _query, get_executor_address
import re

def _sudo(msg_dict):
    return _msg({{
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    }})

def _parse_coin(s):
    m = re.fullmatch(r"(\\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {{"denom": m.group(2), "amount": m.group(1)}}

def demo_query_names_pagination_comprehensive(names, alice_addr):
    owner = get_executor_address()

    # Register names and set destinations
    for name in names:
        salt = "salt" + name
        hexhash = _query({{
            "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
            "name": name,
            "salt": salt,
            "committer": owner,
        }})["hex_hash"]

        _sudo({{
            "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
            "committer": owner,
            "hexhash": hexhash,
            "valuation": _parse_coin("10udys"),
        }})

        _sudo({{
            "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
            "committer": owner,
            "name": name,
            "salt": salt,
        }})

        _sudo({{
            "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
            "owner": owner,
            "name": name,
            "destination": alice_addr,
        }})

    # Test offset pagination
    offset_result = _query({{
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": alice_addr,
        "pagination": {{
            "limit": 2,
            "offset": 1
        }}
    }})

    # Test key-based pagination
    page1 = _query({{
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": alice_addr,
        "pagination": {{
            "limit": 2
        }}
    }})

    page2 = _query({{
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": alice_addr,
        "pagination": {{
            "limit": 2,
            "key": page1["pagination"]["next_key"]
        }}
    }})

    # Test reverse pagination
    reverse_result = _query({{
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": alice_addr,
        "pagination": {{
            "limit": 2,
            "reverse": True
        }}
    }})

    # Test count_total
    count_total_result = _query({{
        "@type": "/dysonprotocol.nameservice.v1.QueryNamesByDestinationRequest",
        "destination": alice_addr,
        "pagination": {{
            "count_total": True
        }}
    }})

    return {{
        "offset": offset_result,
        "page1": page1,
        "page2": page2,
        "reverse": reverse_result,
        "count_total": count_total_result
    }}
"""

    kwargs = json.dumps({"names": names, "alice_addr": alice_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_query_names_pagination_comprehensive",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]

    # Verify offset pagination
    assert (
        len(demo_result["offset"]["names"]) == 2
    ), f"Offset pagination should return 2 names"

    # Verify key-based pagination
    assert len(demo_result["page1"]["names"]) == 2, f"Page1 should have 2 names"
    assert len(demo_result["page2"]["names"]) == 2, f"Page2 should have 2 names"
    assert (
        demo_result["page1"]["pagination"]["next_key"] is not None
    ), f"Expected next_key, got {demo_result['page1']['pagination']}"

    # Verify reverse pagination
    assert (
        len(demo_result["reverse"]["names"]) == 2
    ), f"Reverse pagination should return 2 names"

    # Verify count_total
    assert demo_result["count_total"]["pagination"].get("total") == str(
        5
    ), f"Expected total 5, got {json.dumps(demo_result['count_total']['pagination'], indent=2)}"


def test_query_names_by_destination_nil_request(chainnet):
    """Test QueryNamesByDestination handles nil request error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_query_names_nil_request():
    try:
        query_result = _query(None)
        return {"error": "Should have failed", "result": query_result}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_query_names_nil_request",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "expected" in demo_result
    ), f"Result missing 'expected' key. Keys: {list(demo_result.keys())}"
    assert (
        demo_result["expected"] is True
    ), f"Expected error handling, but got: {json.dumps(demo_result, indent=2)}"
    error_msg = demo_result.get("error", "")
    assert (
        "@type" in error_msg.lower()
    ), f"Error message should mention '@type'. Got: {error_msg}"
