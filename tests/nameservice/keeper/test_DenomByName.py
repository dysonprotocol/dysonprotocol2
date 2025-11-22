"""
QueryDenomByName query handler coverage tests.

Validates listing of denom details under a root name, covering success paths,
pagination combinations (offset, key, reverse, count_total), subdenom filtering,
and error handling (empty name, missing name, nil request). All tests run via
stateless `dysond query script run`.
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

def _register_root_name(name):
    owner = get_executor_address()
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

def _mint_coins(root_name, subdenoms):
    owner = get_executor_address()
    params = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest",
    })
    mint_fee_per = float(params["params"]["mint_fee_per_coin"])
    
    created = []
    for subdenom in subdenoms:
        denom = root_name + subdenom if subdenom else root_name
        amount = 1000
        mint_fee_amount = int(amount * mint_fee_per + 0.99999)
        
        _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
            "name_destination": owner,
            "amount": [{"denom": denom, "amount": str(amount)}],
            "mint_fee": {"denom": "udys", "amount": str(mint_fee_amount)},
        })
        created.append(denom)
    return created
"""


def _random_root_name():
    return f"denom-{secrets.token_hex(4)}.dys"


def _assert_query_response(query_result):
    parsed = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script exception: {json.dumps(query_result.get('exception'), indent=2)}"
    demo_result = parsed["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Expected dict, got {type(demo_result)} full={json.dumps(demo_result, indent=2)}"
    query_resp = demo_result["query_result"]
    assert isinstance(
        query_resp, dict
    ), f"Query result should be dict, got {type(query_resp)}"
    assert (
        "denoms" in query_resp
    ), f"Missing denoms key. Keys: {list(query_resp.keys())}, full={json.dumps(query_resp, indent=2)}"
    assert (
        "pagination" in query_resp
    ), f"Missing pagination key. Keys: {list(query_resp.keys())}, full={json.dumps(query_resp, indent=2)}"
    return query_resp


def test_denom_by_name_success(chainnet):
    """QueryDenomByName returns all denoms under a root name."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    subdenoms = ["", "/token-a", "/token-b", "/token-c"]
    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_denom_by_name_success(root_name, subdenoms):
    _register_root_name(root_name)
    _mint_coins(root_name, subdenoms)
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryDenomByNameRequest",
        "name": root_name,
    })
    return {"query_result": query_result}
"""
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
        "demo_denom_by_name_success",
        "--kwargs",
        json.dumps({"root_name": root_name, "subdenoms": subdenoms}),
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    denoms = query_resp["denoms"]
    assert isinstance(denoms, list), f"denoms should be list, got {type(denoms)}"
    denom_strings = [d["denom"] for d in denoms]
    expected = sorted([root_name + sub for sub in subdenoms])
    assert set(denom_strings) == set(
        expected
    ), f"Mismatch in denoms. Expected {expected}, got {denom_strings}"
    assert isinstance(
        query_resp["pagination"], dict
    ), f"Pagination should be dict, got {type(query_resp['pagination'])}"


def test_denom_by_name_no_denoms(chainnet):
    """QueryDenomByName returns empty list when no denoms exist."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_denom_by_name_no_denoms(root_name):
    _register_root_name(root_name)
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryDenomByNameRequest",
        "name": root_name,
    })
    return {"query_result": query_result}
"""
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
        "demo_denom_by_name_no_denoms",
        "--kwargs",
        json.dumps({"root_name": root_name}),
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    denoms = query_resp["denoms"]
    assert isinstance(denoms, list), f"denoms should be list, got {type(denoms)}"
    assert len(denoms) == 0, f"Expected empty list, got {len(denoms)} denoms"


def test_denom_by_name_subdenom_prefix(chainnet):
    """Subdenom prefix filtering returns only denoms under the prefix."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    subdenoms = ["/alpha/one", "/alpha/two", "/beta/one"]
    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_denom_by_name_subdenom(root_name, subdenoms):
    _register_root_name(root_name)
    _mint_coins(root_name, subdenoms)
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryDenomByNameRequest",
        "name": root_name,
        "subdenom_prefix": "/alpha",
    })
    return {"query_result": query_result}
"""
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
        "demo_denom_by_name_subdenom",
        "--kwargs",
        json.dumps({"root_name": root_name, "subdenoms": subdenoms}),
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    denom_strings = [d["denom"] for d in query_resp["denoms"]]
    expected = sorted(
        [root_name + sub for sub in subdenoms if sub.startswith("/alpha")]
    )
    assert (
        denom_strings == expected
    ), f"Expected only alpha denoms {expected}, got {denom_strings}"


def test_denom_by_name_pagination_offset(chainnet):
    """Pagination with offset should return the correct window."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    subdenoms = [f"/token-{i}" for i in range(5)]
    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_denom_pagination_offset(root_name, subdenoms):
    _register_root_name(root_name)
    _mint_coins(root_name, subdenoms)
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryDenomByNameRequest",
        "name": root_name,
        "pagination": {
            "limit": 2,
            "offset": 1
        }
    })
    return {"query_result": query_result}
"""
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
        "demo_denom_pagination_offset",
        "--kwargs",
        json.dumps({"root_name": root_name, "subdenoms": subdenoms}),
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    denom_strings = [d["denom"] for d in query_resp["denoms"]]
    expected = sorted([root_name + sub for sub in subdenoms])[1:3]
    assert (
        denom_strings == expected
    ), f"Expected offset slice {expected}, got {denom_strings}"


def test_denom_by_name_pagination_key(chainnet):
    """Pagination with next_key should fetch subsequent pages."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    subdenoms = [f"/token-{i}" for i in range(5)]
    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_denom_pagination_key(root_name, subdenoms):
    _register_root_name(root_name)
    _mint_coins(root_name, subdenoms)
    
    page1 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryDenomByNameRequest",
        "name": root_name,
        "pagination": {
            "limit": 2
        }
    })
    
    page2 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryDenomByNameRequest",
        "name": root_name,
        "pagination": {
            "limit": 2,
            "key": page1["pagination"]["next_key"]
        }
    })
    
    return {"page1": page1, "page2": page2}
"""
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
        "demo_denom_pagination_key",
        "--kwargs",
        json.dumps({"root_name": root_name, "subdenoms": subdenoms}),
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script exception: {json.dumps(query_result.get('exception'), indent=2)}"
    result = parsed["result"]["result"]
    page1 = result["page1"]
    page2 = result["page2"]
    ordered_denoms = sorted([root_name + sub for sub in subdenoms])
    page1_denoms = [d["denom"] for d in page1["denoms"]]
    page2_denoms = [d["denom"] for d in page2["denoms"]]
    assert (
        page1_denoms == ordered_denoms[:2]
    ), f"Page1 mismatch. Expected {ordered_denoms[:2]}, got {page1_denoms}"
    assert (
        page2_denoms == ordered_denoms[2:4]
    ), f"Page2 mismatch. Expected {ordered_denoms[2:4]}, got {page2_denoms}"
    assert (
        page1["pagination"]["next_key"] is not None
    ), f"Expected next_key, got {page1['pagination']}"


def test_denom_by_name_pagination_reverse(chainnet):
    """Reverse pagination returns descending order slice."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    subdenoms = [f"/token-{i}" for i in range(5)]
    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_denom_pagination_reverse(root_name, subdenoms):
    _register_root_name(root_name)
    _mint_coins(root_name, subdenoms)
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryDenomByNameRequest",
        "name": root_name,
        "pagination": {
            "limit": 2,
            "reverse": True
        }
    })
    return {"query_result": query_result}
"""
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
        "demo_denom_pagination_reverse",
        "--kwargs",
        json.dumps({"root_name": root_name, "subdenoms": subdenoms}),
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    denom_strings = [d["denom"] for d in query_resp["denoms"]]
    expected = sorted([root_name + sub for sub in subdenoms], reverse=True)[:2]
    assert (
        denom_strings == expected
    ), f"Expected descending slice {expected}, got {denom_strings}"


def test_denom_by_name_count_total(chainnet):
    """count_total returns the total number of denoms."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    subdenoms = [f"/token-{i}" for i in range(5)]
    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_denom_count_total(root_name, subdenoms):
    _register_root_name(root_name)
    _mint_coins(root_name, subdenoms)
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryDenomByNameRequest",
        "name": root_name,
        "pagination": {
            "count_total": True
        }
    })
    return {"query_result": query_result}
"""
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
        "demo_denom_count_total",
        "--kwargs",
        json.dumps({"root_name": root_name, "subdenoms": subdenoms}),
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    pagination = query_resp["pagination"]
    assert pagination.get("total") == str(
        len(subdenoms)
    ), f"Expected total {len(subdenoms)}, got {json.dumps(pagination, indent=2)}"


def test_denom_by_name_empty_name(chainnet):
    """Empty name should raise invalid argument."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _query

def demo_denom_empty_name():
    try:
        query_result = _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryDenomByNameRequest",
            "name": "",
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
        "demo_denom_empty_name",
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    demo_result = parsed["result"]["result"]
    assert (
        demo_result["expected"] is True
    ), f"Expected error flag, got {json.dumps(demo_result, indent=2)}"
    assert (
        "empty" in demo_result["error"].lower()
    ), f"Error should mention empty. Got {demo_result['error']}"


def test_denom_by_name_name_not_found(chainnet):
    """Missing root name should raise not found."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    extra_code = """
from dys import _query

def demo_denom_name_not_found(root_name):
    try:
        query_result = _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryDenomByNameRequest",
            "name": root_name,
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
        "demo_denom_name_not_found",
        "--kwargs",
        json.dumps({"root_name": root_name}),
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    demo_result = parsed["result"]["result"]
    assert (
        demo_result["expected"] is True
    ), f"Expected not found error, got {json.dumps(demo_result, indent=2)}"
    error_lower = demo_result["error"].lower()
    assert (
        "not found" in error_lower
    ), f"Error should mention not found. Got {demo_result['error']}"


def test_denom_by_name_nil_request(chainnet):
    """Nil request surfaces missing @type error."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _query

def demo_denom_nil_request():
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
        "demo_denom_nil_request",
        "--extra-code",
        extra_code,
    )

    parsed = deep_parse(query_result)
    demo_result = parsed["result"]["result"]
    assert (
        demo_result["expected"] is True
    ), f"Expected nil request error, got {json.dumps(demo_result, indent=2)}"
    assert (
        "@type" in demo_result["error"].lower()
    ), f"Error should mention @type. Got {demo_result['error']}"
