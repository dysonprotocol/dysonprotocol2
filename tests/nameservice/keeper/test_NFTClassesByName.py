"""
QueryNFTClassesByName query handler coverage tests.

Validates listing of NFT class IDs under a root name, covering success paths,
pagination combinations (offset, key, reverse, count_total), subclass filtering,
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

def _save_classes(root_name, suffixes):
    owner = get_executor_address()
    created = []
    for suffix in suffixes:
        class_id = root_name + suffix
        _sudo({
            "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
            "name_destination": owner,
            "class_id": class_id,
            "name": class_id,
            "symbol": "CLS",
            "description": class_id,
        })
        created.append(class_id)
    return created
"""


def _random_root_name():
    return f"nft-{secrets.token_hex(4)}.dys"


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
        "class_ids" in query_resp
    ), f"Missing class_ids key. Keys: {list(query_resp.keys())}, full={json.dumps(query_resp, indent=2)}"
    assert (
        "pagination" in query_resp
    ), f"Missing pagination key. Keys: {list(query_resp.keys())}, full={json.dumps(query_resp, indent=2)}"
    return query_resp


def test_nft_classes_by_name_success(chainnet):
    """QueryNFTClassesByName returns all classes under a root name."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    class_suffixes = ["/collection-a", "/collection-b", "/collection-c"]
    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_nft_classes_success(root_name, class_suffixes):
    _register_root_name(root_name)
    _save_classes(root_name, class_suffixes)
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNFTClassesByNameRequest",
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
        "demo_nft_classes_success",
        "--kwargs",
        json.dumps({"root_name": root_name, "class_suffixes": class_suffixes}),
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    class_ids = query_resp["class_ids"]
    expected_ids = sorted([root_name + suffix for suffix in class_suffixes])
    assert isinstance(
        class_ids, list
    ), f"class_ids should be list, got {type(class_ids)}"
    assert set(class_ids) == set(
        expected_ids
    ), f"Mismatch in class IDs. Expected {expected_ids}, got {class_ids}"
    assert isinstance(
        query_resp["pagination"], dict
    ), f"Pagination should be dict, got {type(query_resp['pagination'])}"


def test_nft_classes_by_name_no_classes(chainnet):
    """QueryNFTClassesByName returns empty list when no classes exist."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_nft_classes_no_classes(root_name):
    _register_root_name(root_name)
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNFTClassesByNameRequest",
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
        "demo_nft_classes_no_classes",
        "--kwargs",
        json.dumps({"root_name": root_name}),
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    assert (
        query_resp["class_ids"] == []
    ), f"Expected empty class_ids, got {query_resp['class_ids']}"


def test_nft_classes_by_name_subclass_prefix(chainnet):
    """Subclass prefix filtering should return only classes under the prefix."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    class_suffixes = [
        "/alpha/one",
        "/alpha/two",
        "/beta/one",
    ]
    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_nft_classes_subclass(root_name, class_suffixes):
    _register_root_name(root_name)
    _save_classes(root_name, class_suffixes)
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNFTClassesByNameRequest",
        "name": root_name,
        "subclass_prefix": "/alpha",
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
        "demo_nft_classes_subclass",
        "--kwargs",
        json.dumps({"root_name": root_name, "class_suffixes": class_suffixes}),
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    expected = sorted(
        [root_name + suffix for suffix in class_suffixes if suffix.startswith("/alpha")]
    )
    assert (
        query_resp["class_ids"] == expected
    ), f"Expected only alpha classes, got {query_resp['class_ids']} (expected {expected})"


def test_nft_classes_by_name_subclass_prefix_deep_nested(chainnet):
    """Subclass prefix filtering: deep nested paths must match shorter prefix.

    This test verifies that filtering by "/sub" correctly matches all classes
    starting with "/sub", not just exact matches. If the bug exists (exact match only),
    this test will FAIL because longer paths like "/sub/foo/bar" won't be returned.

    Expected behavior: Filtering by "/sub" should return:
    - "name.dys/sub" (exact match)
    - "name.dys/sub/foo" (one level deeper)
    - "name.dys/sub/foo/bar" (two levels deeper)
    - "name.dys/sub/other" (different branch)

    Bug behavior: Would only return "name.dys/sub" (exact match only).
    """
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    # Create classes with deeper nesting - these should all match "/sub" prefix
    class_suffixes = [
        "/sub",  # Exact match - would work even with bug
        "/sub/foo",  # One level deeper - would FAIL if bug exists
        "/sub/foo/bar",  # Two levels deeper - would FAIL if bug exists
        "/sub/other",  # Different branch - would FAIL if bug exists
        "/other/prefix",  # Different prefix - should NOT match (correct)
    ]
    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_nft_classes_subclass_deep(root_name, class_suffixes):
    _register_root_name(root_name)
    _save_classes(root_name, class_suffixes)
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNFTClassesByNameRequest",
        "name": root_name,
        "subclass_prefix": "/sub",
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
        "demo_nft_classes_subclass_deep",
        "--kwargs",
        json.dumps({"root_name": root_name, "class_suffixes": class_suffixes}),
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    class_ids = query_resp["class_ids"]

    # Explicitly check that longer paths are included (these would be missing if bug exists)
    exact_match = root_name + "/sub"
    longer_path_1 = root_name + "/sub/foo"
    longer_path_2 = root_name + "/sub/foo/bar"
    longer_path_3 = root_name + "/sub/other"
    wrong_prefix = root_name + "/other/prefix"

    # These assertions will FAIL if the bug exists (only exact match would be returned)
    assert (
        exact_match in class_ids
    ), f"BUG: Exact match '{exact_match}' should be in results: {class_ids}"
    assert (
        longer_path_1 in class_ids
    ), f"BUG: Longer path '{longer_path_1}' missing - prefix filtering bug exists! Got: {class_ids}"
    assert (
        longer_path_2 in class_ids
    ), f"BUG: Longer path '{longer_path_2}' missing - prefix filtering bug exists! Got: {class_ids}"
    assert (
        longer_path_3 in class_ids
    ), f"BUG: Longer path '{longer_path_3}' missing - prefix filtering bug exists! Got: {class_ids}"
    assert (
        wrong_prefix not in class_ids
    ), f"Wrong prefix '{wrong_prefix}' should not be in results: {class_ids}"

    # Verify we got exactly the expected classes
    expected = sorted([exact_match, longer_path_1, longer_path_2, longer_path_3])
    assert (
        sorted(class_ids) == expected
    ), f"Expected exactly {expected}, got {sorted(class_ids)}"


def test_nft_classes_by_name_pagination_offset(chainnet):
    """Pagination with offset should return the correct window."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    class_suffixes = [f"/collection-{i}" for i in range(5)]
    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_nft_classes_pagination_offset(root_name, class_suffixes):
    _register_root_name(root_name)
    _save_classes(root_name, class_suffixes)
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNFTClassesByNameRequest",
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
        "demo_nft_classes_pagination_offset",
        "--kwargs",
        json.dumps({"root_name": root_name, "class_suffixes": class_suffixes}),
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    class_ids = query_resp["class_ids"]
    expected_ids = sorted([root_name + suffix for suffix in class_suffixes])[1:3]
    assert (
        class_ids == expected_ids
    ), f"Expected offset slice {expected_ids}, got {class_ids}"


def test_nft_classes_by_name_pagination_key(chainnet):
    """Pagination with next_key should fetch subsequent pages."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    class_suffixes = [f"/page-{i}" for i in range(4)]
    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_nft_classes_pagination_key(root_name, class_suffixes):
    _register_root_name(root_name)
    _save_classes(root_name, class_suffixes)
    page1 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNFTClassesByNameRequest",
        "name": root_name,
        "pagination": {
            "limit": 2
        }
    })
    next_key = page1["pagination"].get("next_key")
    page2 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNFTClassesByNameRequest",
        "name": root_name,
        "pagination": {
            "limit": 2,
            "key": next_key
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
        "demo_nft_classes_pagination_key",
        "--kwargs",
        json.dumps({"root_name": root_name, "class_suffixes": class_suffixes}),
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
    ordered_ids = sorted([root_name + suffix for suffix in class_suffixes])
    assert (
        page1["class_ids"] == ordered_ids[:2]
    ), f"Page1 mismatch. Expected {ordered_ids[:2]}, got {page1['class_ids']}"
    assert (
        page2["class_ids"] == ordered_ids[2:4]
    ), f"Page2 mismatch. Expected {ordered_ids[2:4]}, got {page2['class_ids']}"
    assert (
        page1["pagination"]["next_key"] is not None
    ), f"Expected next_key, got {page1['pagination']}"


def test_nft_classes_by_name_pagination_reverse(chainnet):
    """Reverse pagination returns descending order slice."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    class_suffixes = [f"/rev-{i}" for i in range(4)]
    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_nft_classes_pagination_reverse(root_name, class_suffixes):
    _register_root_name(root_name)
    _save_classes(root_name, class_suffixes)
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNFTClassesByNameRequest",
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
        "demo_nft_classes_pagination_reverse",
        "--kwargs",
        json.dumps({"root_name": root_name, "class_suffixes": class_suffixes}),
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    expected = sorted([root_name + suffix for suffix in class_suffixes], reverse=True)[
        :2
    ]
    assert (
        query_resp["class_ids"] == expected
    ), f"Expected descending slice {expected}, got {query_resp['class_ids']}"


def test_nft_classes_by_name_count_total(chainnet):
    """count_total returns the total number of classes."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    class_suffixes = [f"/total-{i}" for i in range(3)]
    extra_code = (
        BASE_EXTRA_CODE
        + """
def demo_nft_classes_count_total(root_name, class_suffixes):
    _register_root_name(root_name)
    _save_classes(root_name, class_suffixes)
    query_result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryNFTClassesByNameRequest",
        "name": root_name,
        "pagination": {
            "count_total": True,
            "limit": 50
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
        "demo_nft_classes_count_total",
        "--kwargs",
        json.dumps({"root_name": root_name, "class_suffixes": class_suffixes}),
        "--extra-code",
        extra_code,
    )

    query_resp = _assert_query_response(query_result)
    pagination = query_resp["pagination"]
    assert pagination.get("total") == str(
        len(class_suffixes)
    ), f"Expected total {len(class_suffixes)}, got {json.dumps(pagination, indent=2)}"


def test_nft_classes_by_name_empty_name(chainnet):
    """Empty name should raise invalid argument."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _query

def demo_nft_classes_empty_name():
    try:
        query_result = _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryNFTClassesByNameRequest",
            "name": ""
        })
        return {"error": "expected failure", "result": query_result}
    except Exception as exc:
        return {"error": str(exc), "expected": True}
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
        "demo_nft_classes_empty_name",
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


def test_nft_classes_by_name_name_not_found(chainnet):
    """Missing root name should raise not found."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    root_name = _random_root_name()
    extra_code = """
from dys import _query

def demo_nft_classes_name_not_found(root_name):
    try:
        query_result = _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryNFTClassesByNameRequest",
            "name": root_name
        })
        return {"error": "expected failure", "result": query_result}
    except Exception as exc:
        return {"error": str(exc), "expected": True}
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
        "demo_nft_classes_name_not_found",
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


def test_nft_classes_by_name_nil_request(chainnet):
    """Nil request surface missing @type error."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _query

def demo_nft_classes_nil_request():
    try:
        query_result = _query(None)
        return {"error": "expected failure", "result": query_result}
    except Exception as exc:
        return {"error": str(exc), "expected": True}
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
        "demo_nft_classes_nil_request",
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
