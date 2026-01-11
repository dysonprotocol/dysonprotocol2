"""
Test UpdateParams message handler for nameservice keeper.

Tests the UpdateParams message which allows authorized accounts (governance)
to update the nameservice module parameters.
"""

import json
import pytest

from deep_parse import deep_parse


def test_update_params_success(chainnet):
    """Test successful parameter update by authorized authority."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_update_params_success():
    # Update parameters with valid values
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),  # gov module address
        "params": {
            "mint_fee_per_coin": "0.02",
            "min_bid_timeout_class": "3600s",  # 1 hour
            "max_bid_timeout_class": "2592000s",  # 30 days
            "min_reject_bid_valuation_fee_percent": "0.01",
            "max_reject_bid_valuation_fee_percent": "0.05",
            "min_minimum_bid_percent_increase": "0.02",
            "max_minimum_bid_percent_increase": "0.10",
            "min_valuation_fee_pct": "0.001",
            "max_valuation_fee_pct": "0.05",
            "min_valuation_period": "7200s",  # 2 hours
            "max_valuation_period": "2592000s",  # 30 days
            "name_suffix": ".dys"
        }
    })

    return {
        "sudo_result": sudo_result
    }
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
        "demo_update_params_success",
        "--extra-code",
        extra_code,
    )

    # Parse and validate response
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        "result" in result
    ), f"result missing 'result' key. Keys: {list(result.keys())}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Validate sudo result
    sudo_result = demo_result["sudo_result"]
    assert isinstance(
        sudo_result, dict
    ), f"sudo_result should be dict, got {type(sudo_result)}"
    assert (
        sudo_result["@type"] == "/dysonprotocol.script.v1.MsgSudoResponse"
    ), f"sudo should return sudo response, got {sudo_result.get('@type')}"
    assert (
        "results" in sudo_result
    ), f"sudo should have results, got {list(sudo_result.keys())}"
    assert (
        len(sudo_result["results"]) == 1
    ), f"sudo should have one result, got {len(sudo_result['results'])}"
    assert (
        sudo_result["results"][0]["@type"]
        == "/dysonprotocol.nameservice.v1.MsgUpdateParamsResponse"
    ), f"sudo should return update params response, got {sudo_result['results'][0].get('@type')}"


def test_update_params_invalid_authority(chainnet):
    """Test parameter update with invalid authority."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    # Use a random address that's not the authority
    invalid_authority = "dyson1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_update_params_invalid_authority(invalid_authority):
    # Try to update parameters with invalid authority - should fail
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": invalid_authority,
        "params": {
            "mint_fee_per_coin": "0.02",
            "min_bid_timeout_class": "3600s",
            "max_bid_timeout_class": "2592000s",
            "min_reject_bid_valuation_fee_percent": "0.01",
            "max_reject_bid_valuation_fee_percent": "0.05",
            "min_minimum_bid_percent_increase": "0.02",
            "max_minimum_bid_percent_increase": "0.10",
            "min_valuation_fee_pct": "0.001",
            "max_valuation_fee_pct": "0.05",
            "min_valuation_period": "7200s",
            "max_valuation_period": "2592000s"
        }
    })

    return {
        "sudo_result": sudo_result
    }
"""

    kwargs = json.dumps({"invalid_authority": invalid_authority})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_update_params_invalid_authority",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    assert (
        "exception" in result
    ), f"result should have exception. Keys: {list(result.keys())}"

    exception = result["exception"]
    assert (
        exception["class"] == "DysRuntimeError"
    ), f"should be DysRuntimeError, got {exception['class']}"


def test_update_params_reserved_names_blank_preserves_existing(chainnet):
    """Test UpdateParams with blank reserved_names preserves existing value."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_reserved_names_blank_preserves():
    # Step 1: Set reserved_names to a known value
    update_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved1.dys\\nreserved2.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Step 2: Query params to verify reserved_names was set
    params_query1 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    # Step 3: Update params with blank reserved_names (should preserve existing)
    update_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.02",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "",  # Blank - should preserve existing
            "name_suffix": ".dys"
        }
    })
    
    # Step 4: Query params again to verify reserved_names was preserved
    params_query2 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    return {
        "update_result1": update_result1,
        "params_before": params_query1["params"],
        "update_result2": update_result2,
        "params_after": params_query2["params"]
    }
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
        "demo_reserved_names_blank_preserves",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Verify params_before has reserved_names set
    params_before = demo_result["params_before"]
    assert isinstance(
        params_before, dict
    ), f"params_before should be dict, got {type(params_before)}"
    assert (
        "reserved_names" in params_before
    ), f"params_before missing 'reserved_names' key. Keys: {list(params_before.keys())}"
    assert params_before["reserved_names"] == "reserved1.dys\nreserved2.dys", (
        f"Expected reserved_names to be 'reserved1.dys\\nreserved2.dys', got: {params_before['reserved_names']}"
    )

    # Verify params_after preserved reserved_names (mint_fee_per_coin should be updated though)
    params_after = demo_result["params_after"]
    assert isinstance(
        params_after, dict
    ), f"params_after should be dict, got {type(params_after)}"
    assert (
        "reserved_names" in params_after
    ), f"params_after missing 'reserved_names' key. Keys: {list(params_after.keys())}"
    assert params_after["reserved_names"] == "reserved1.dys\nreserved2.dys", (
        f"Expected reserved_names to be preserved as 'reserved1.dys\\nreserved2.dys', got: {params_after['reserved_names']}"
    )
    assert params_after["mint_fee_per_coin"] == "0.02", (
        f"Expected mint_fee_per_coin to be updated to '0.02', got: {params_after['mint_fee_per_coin']}"
    )


def test_update_params_reserved_names_non_blank_updates(chainnet):
    """Test UpdateParams with non-blank reserved_names updates the value."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_reserved_names_updates():
    # Step 1: Set initial reserved_names
    update_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "old1.dys\\nold2.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Step 2: Update with new reserved_names
    update_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "new1.dys\\nnew2.dys\\nnew3.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Step 3: Query params to verify reserved_names was updated
    params_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    return {
        "update_result1": update_result1,
        "update_result2": update_result2,
        "params": params_query["params"]
    }
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
        "demo_reserved_names_updates",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Verify reserved_names was updated
    params = demo_result["params"]
    assert isinstance(
        params, dict
    ), f"params should be dict, got {type(params)}"
    assert (
        "reserved_names" in params
    ), f"params missing 'reserved_names' key. Keys: {list(params.keys())}"
    assert params["reserved_names"] == "new1.dys\nnew2.dys\nnew3.dys", (
        f"Expected reserved_names to be 'new1.dys\\nnew2.dys\\nnew3.dys', got: {params['reserved_names']}"
    )


@pytest.mark.nameservice
def test_update_params_invalid_reserved_name_format(chainnet):
    """Test UpdateParams with invalid reserved name format fails validation."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_invalid_reserved_name_format():
    # Try to update with invalid reserved name format (not ending with .dys)
    # This should fail validation
    update_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "invalid-name",  # Invalid: doesn't end with .dys
            "name_suffix": ".dys"
        }
    })
    
    return {
        "update_result": update_result
    }
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
        "demo_invalid_reserved_name_format",
        "--extra-code",
        extra_code,
    )

    # Script should fail with exception for invalid reserved name format
    assert (
        query_result.get("exception") is not None
    ), f"Expected exception for invalid reserved name format, but script succeeded. Result: {json.dumps(query_result, indent=2)}"
    
    exception = query_result.get("exception", {})
    assert isinstance(
        exception, dict
    ), f"Exception should be dict, got {type(exception)}"
    assert (
        "msg" in exception
    ), f"Exception missing 'msg' key. Keys: {list(exception.keys())}"
    
    error_msg = exception["msg"]
    assert isinstance(
        error_msg, str
    ), f"Exception msg should be string, got {type(error_msg)}"
    assert "invalid reserved name" in error_msg.lower(), (
        f"Expected 'invalid reserved name' in exception message, got: {error_msg}. "
        f"Full exception: {json.dumps(exception, indent=2)}"
    )


@pytest.mark.nameservice
def test_update_params_reserved_names_with_comments_and_blank_lines(chainnet):
    """Test UpdateParams with reserved_names containing comments and blank lines."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_reserved_names_with_comments():
    # Update with reserved_names containing comments and blank lines
    update_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "# This is a comment\\n\\nname1.dys\\n# Another comment\\nname2.dys\\n\\nname3.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Query params to verify reserved_names was set correctly (comments/blank lines ignored)
    params_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    return {
        "update_result": update_result,
        "params": params_query["params"]
    }
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
        "demo_reserved_names_with_comments",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Verify reserved_names was set (validation should pass, comments/blank lines ignored)
    params = demo_result["params"]
    assert isinstance(
        params, dict
    ), f"params should be dict, got {type(params)}"
    assert (
        "reserved_names" in params
    ), f"params missing 'reserved_names' key. Keys: {list(params.keys())}"
    # The reserved_names should contain the valid names (comments and blank lines are ignored)
    reserved_names = params["reserved_names"]
    assert "name1.dys" in reserved_names, (
        f"Expected 'name1.dys' in reserved_names, got: {reserved_names}"
    )
    assert "name2.dys" in reserved_names, (
        f"Expected 'name2.dys' in reserved_names, got: {reserved_names}"
    )
    assert "name3.dys" in reserved_names, (
        f"Expected 'name3.dys' in reserved_names, got: {reserved_names}"
    )
    # Verify comments and blank lines are not present
    assert "#" not in reserved_names, (
        f"Expected comments to be filtered out, got: {reserved_names}"
    )


def test_update_params_invalid_params_negative_mint_fee(chainnet):
    """Test parameter update with invalid parameters (negative mint fee)."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_update_params_invalid_params():
    # Try to update parameters with negative mint fee - should fail
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "-0.01",  # Invalid: negative fee
            "min_bid_timeout_class": "3600s",
            "max_bid_timeout_class": "2592000s",
            "min_reject_bid_valuation_fee_percent": "0.01",
            "max_reject_bid_valuation_fee_percent": "0.05",
            "min_minimum_bid_percent_increase": "0.02",
            "max_minimum_bid_percent_increase": "0.10",
            "min_valuation_fee_pct": "0.001",
            "max_valuation_fee_pct": "0.05",
            "min_valuation_period": "7200s",
            "max_valuation_period": "2592000s",
            "name_suffix": ".dys"
        }
    })

    return {
        "sudo_result": sudo_result
    }
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
        "demo_update_params_invalid_params",
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    assert (
        "exception" in result
    ), f"result should have exception. Keys: {list(result.keys())}"

    exception = result["exception"]
    assert (
        exception["class"] == "DysRuntimeError"
    ), f"should be DysRuntimeError, got {exception['class']}"


def test_update_params_reserved_names_blank_preserves_existing(chainnet):
    """Test UpdateParams with blank reserved_names preserves existing value."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_reserved_names_blank_preserves():
    # Step 1: Set reserved_names to a known value
    update_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved1.dys\\nreserved2.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Step 2: Query params to verify reserved_names was set
    params_query1 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    # Step 3: Update params with blank reserved_names (should preserve existing)
    update_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.02",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "",  # Blank - should preserve existing
            "name_suffix": ".dys"
        }
    })
    
    # Step 4: Query params again to verify reserved_names was preserved
    params_query2 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    return {
        "update_result1": update_result1,
        "params_before": params_query1["params"],
        "update_result2": update_result2,
        "params_after": params_query2["params"]
    }
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
        "demo_reserved_names_blank_preserves",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Verify params_before has reserved_names set
    params_before = demo_result["params_before"]
    assert isinstance(
        params_before, dict
    ), f"params_before should be dict, got {type(params_before)}"
    assert (
        "reserved_names" in params_before
    ), f"params_before missing 'reserved_names' key. Keys: {list(params_before.keys())}"
    assert params_before["reserved_names"] == "reserved1.dys\nreserved2.dys", (
        f"Expected reserved_names to be 'reserved1.dys\\nreserved2.dys', got: {params_before['reserved_names']}"
    )

    # Verify params_after preserved reserved_names (mint_fee_per_coin should be updated though)
    params_after = demo_result["params_after"]
    assert isinstance(
        params_after, dict
    ), f"params_after should be dict, got {type(params_after)}"
    assert (
        "reserved_names" in params_after
    ), f"params_after missing 'reserved_names' key. Keys: {list(params_after.keys())}"
    assert params_after["reserved_names"] == "reserved1.dys\nreserved2.dys", (
        f"Expected reserved_names to be preserved as 'reserved1.dys\\nreserved2.dys', got: {params_after['reserved_names']}"
    )
    assert params_after["mint_fee_per_coin"] == "0.02", (
        f"Expected mint_fee_per_coin to be updated to '0.02', got: {params_after['mint_fee_per_coin']}"
    )


def test_update_params_reserved_names_non_blank_updates(chainnet):
    """Test UpdateParams with non-blank reserved_names updates the value."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_reserved_names_updates():
    # Step 1: Set initial reserved_names
    update_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "old1.dys\\nold2.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Step 2: Update with new reserved_names
    update_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "new1.dys\\nnew2.dys\\nnew3.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Step 3: Query params to verify reserved_names was updated
    params_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    return {
        "update_result1": update_result1,
        "update_result2": update_result2,
        "params": params_query["params"]
    }
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
        "demo_reserved_names_updates",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Verify reserved_names was updated
    params = demo_result["params"]
    assert isinstance(
        params, dict
    ), f"params should be dict, got {type(params)}"
    assert (
        "reserved_names" in params
    ), f"params missing 'reserved_names' key. Keys: {list(params.keys())}"
    assert params["reserved_names"] == "new1.dys\nnew2.dys\nnew3.dys", (
        f"Expected reserved_names to be 'new1.dys\\nnew2.dys\\nnew3.dys', got: {params['reserved_names']}"
    )
    assert (
        "invalid parameters" in exception["msg"].lower()
    ), f"error should mention invalid parameters, got: {exception['msg']}"


def test_update_params_invalid_params_invalid_decimal(chainnet):
    """Test parameter update with invalid parameters (invalid decimal string)."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_update_params_invalid_decimal():
    # Try to update parameters with invalid decimal string - should fail
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "not_a_number",  # Invalid: not a decimal
            "min_bid_timeout_class": "3600s",
            "max_bid_timeout_class": "2592000s",
            "min_reject_bid_valuation_fee_percent": "0.01",
            "max_reject_bid_valuation_fee_percent": "0.05",
            "min_minimum_bid_percent_increase": "0.02",
            "max_minimum_bid_percent_increase": "0.10",
            "min_valuation_fee_pct": "0.001",
            "max_valuation_fee_pct": "0.05",
            "min_valuation_period": "7200s",
            "max_valuation_period": "2592000s"
        }
    })

    return {
        "sudo_result": sudo_result
    }
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
        "demo_update_params_invalid_decimal",
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    assert (
        "exception" in result
    ), f"result should have exception. Keys: {list(result.keys())}"

    exception = result["exception"]
    assert (
        exception["class"] == "DysRuntimeError"
    ), f"should be DysRuntimeError, got {exception['class']}"


def test_update_params_reserved_names_blank_preserves_existing(chainnet):
    """Test UpdateParams with blank reserved_names preserves existing value."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_reserved_names_blank_preserves():
    # Step 1: Set reserved_names to a known value
    update_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved1.dys\\nreserved2.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Step 2: Query params to verify reserved_names was set
    params_query1 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    # Step 3: Update params with blank reserved_names (should preserve existing)
    update_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.02",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "",  # Blank - should preserve existing
            "name_suffix": ".dys"
        }
    })
    
    # Step 4: Query params again to verify reserved_names was preserved
    params_query2 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    return {
        "update_result1": update_result1,
        "params_before": params_query1["params"],
        "update_result2": update_result2,
        "params_after": params_query2["params"]
    }
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
        "demo_reserved_names_blank_preserves",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Verify params_before has reserved_names set
    params_before = demo_result["params_before"]
    assert isinstance(
        params_before, dict
    ), f"params_before should be dict, got {type(params_before)}"
    assert (
        "reserved_names" in params_before
    ), f"params_before missing 'reserved_names' key. Keys: {list(params_before.keys())}"
    assert params_before["reserved_names"] == "reserved1.dys\nreserved2.dys", (
        f"Expected reserved_names to be 'reserved1.dys\\nreserved2.dys', got: {params_before['reserved_names']}"
    )

    # Verify params_after preserved reserved_names (mint_fee_per_coin should be updated though)
    params_after = demo_result["params_after"]
    assert isinstance(
        params_after, dict
    ), f"params_after should be dict, got {type(params_after)}"
    assert (
        "reserved_names" in params_after
    ), f"params_after missing 'reserved_names' key. Keys: {list(params_after.keys())}"
    assert params_after["reserved_names"] == "reserved1.dys\nreserved2.dys", (
        f"Expected reserved_names to be preserved as 'reserved1.dys\\nreserved2.dys', got: {params_after['reserved_names']}"
    )
    assert params_after["mint_fee_per_coin"] == "0.02", (
        f"Expected mint_fee_per_coin to be updated to '0.02', got: {params_after['mint_fee_per_coin']}"
    )


def test_update_params_reserved_names_non_blank_updates(chainnet):
    """Test UpdateParams with non-blank reserved_names updates the value."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_reserved_names_updates():
    # Step 1: Set initial reserved_names
    update_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "old1.dys\\nold2.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Step 2: Update with new reserved_names
    update_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "new1.dys\\nnew2.dys\\nnew3.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Step 3: Query params to verify reserved_names was updated
    params_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    return {
        "update_result1": update_result1,
        "update_result2": update_result2,
        "params": params_query["params"]
    }
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
        "demo_reserved_names_updates",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Verify reserved_names was updated
    params = demo_result["params"]
    assert isinstance(
        params, dict
    ), f"params should be dict, got {type(params)}"
    assert (
        "reserved_names" in params
    ), f"params missing 'reserved_names' key. Keys: {list(params.keys())}"
    assert params["reserved_names"] == "new1.dys\nnew2.dys\nnew3.dys", (
        f"Expected reserved_names to be 'new1.dys\\nnew2.dys\\nnew3.dys', got: {params['reserved_names']}"
    )
    assert (
        "invalid parameters" in exception["msg"].lower()
    ), f"error should mention invalid parameters, got: {exception['msg']}"


def test_update_params_invalid_params_bounds_violation(chainnet):
    """Test parameter update with invalid parameters (min > max bounds)."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_update_params_bounds_violation():
    # Try to update parameters with min > max bounds - should fail
    sudo_result = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.02",
            "min_bid_timeout_class": "2592000s",  # 30 days
            "max_bid_timeout_class": "3600s",     # 1 hour (min > max)
            "min_reject_bid_valuation_fee_percent": "0.01",
            "max_reject_bid_valuation_fee_percent": "0.05",
            "min_minimum_bid_percent_increase": "0.02",
            "max_minimum_bid_percent_increase": "0.10",
            "min_valuation_fee_pct": "0.001",
            "max_valuation_fee_pct": "0.05",
            "min_valuation_period": "7200s",
            "max_valuation_period": "2592000s"
        }
    })

    return {
        "sudo_result": sudo_result
    }
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
        "demo_update_params_bounds_violation",
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    assert (
        "exception" in result
    ), f"result should have exception. Keys: {list(result.keys())}"

    exception = result["exception"]
    assert (
        exception["class"] == "DysRuntimeError"
    ), f"should be DysRuntimeError, got {exception['class']}"


def test_update_params_reserved_names_blank_preserves_existing(chainnet):
    """Test UpdateParams with blank reserved_names preserves existing value."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_reserved_names_blank_preserves():
    # Step 1: Set reserved_names to a known value
    update_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved1.dys\\nreserved2.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Step 2: Query params to verify reserved_names was set
    params_query1 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    # Step 3: Update params with blank reserved_names (should preserve existing)
    update_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.02",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "",  # Blank - should preserve existing
            "name_suffix": ".dys"
        }
    })
    
    # Step 4: Query params again to verify reserved_names was preserved
    params_query2 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    return {
        "update_result1": update_result1,
        "params_before": params_query1["params"],
        "update_result2": update_result2,
        "params_after": params_query2["params"]
    }
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
        "demo_reserved_names_blank_preserves",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Verify params_before has reserved_names set
    params_before = demo_result["params_before"]
    assert isinstance(
        params_before, dict
    ), f"params_before should be dict, got {type(params_before)}"
    assert (
        "reserved_names" in params_before
    ), f"params_before missing 'reserved_names' key. Keys: {list(params_before.keys())}"
    assert params_before["reserved_names"] == "reserved1.dys\nreserved2.dys", (
        f"Expected reserved_names to be 'reserved1.dys\\nreserved2.dys', got: {params_before['reserved_names']}"
    )

    # Verify params_after preserved reserved_names (mint_fee_per_coin should be updated though)
    params_after = demo_result["params_after"]
    assert isinstance(
        params_after, dict
    ), f"params_after should be dict, got {type(params_after)}"
    assert (
        "reserved_names" in params_after
    ), f"params_after missing 'reserved_names' key. Keys: {list(params_after.keys())}"
    assert params_after["reserved_names"] == "reserved1.dys\nreserved2.dys", (
        f"Expected reserved_names to be preserved as 'reserved1.dys\\nreserved2.dys', got: {params_after['reserved_names']}"
    )
    assert params_after["mint_fee_per_coin"] == "0.02", (
        f"Expected mint_fee_per_coin to be updated to '0.02', got: {params_after['mint_fee_per_coin']}"
    )


def test_update_params_reserved_names_non_blank_updates(chainnet):
    """Test UpdateParams with non-blank reserved_names updates the value."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_reserved_names_updates():
    # Step 1: Set initial reserved_names
    update_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "old1.dys\\nold2.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Step 2: Update with new reserved_names
    update_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "new1.dys\\nnew2.dys\\nnew3.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Step 3: Query params to verify reserved_names was updated
    params_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    return {
        "update_result1": update_result1,
        "update_result2": update_result2,
        "params": params_query["params"]
    }
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
        "demo_reserved_names_updates",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Verify reserved_names was updated
    params = demo_result["params"]
    assert isinstance(
        params, dict
    ), f"params should be dict, got {type(params)}"
    assert (
        "reserved_names" in params
    ), f"params missing 'reserved_names' key. Keys: {list(params.keys())}"
    assert params["reserved_names"] == "new1.dys\nnew2.dys\nnew3.dys", (
        f"Expected reserved_names to be 'new1.dys\\nnew2.dys\\nnew3.dys', got: {params['reserved_names']}"
    )
    assert (
        "invalid parameters" in exception["msg"].lower()
    ), f"error should mention invalid parameters, got: {exception['msg']}"


def test_update_params_nil_request(chainnet):
    """Test parameter update with nil request."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_nil_request():
    # Try to call with nil message - should fail at framework level
    sudo_result = _sudo(None)

    return {
        "sudo_result": sudo_result
    }
"""

    kwargs = json.dumps({})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_nil_request",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    # Parse and validate error
    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"

    assert (
        "exception" in result
    ), f"result should have exception. Keys: {list(result.keys())}"

    exception = result["exception"]
    assert (
        exception["class"] == "DysRuntimeError"
    ), f"should be DysRuntimeError, got {exception['class']}"


def test_update_params_reserved_names_blank_preserves_existing(chainnet):
    """Test UpdateParams with blank reserved_names preserves existing value."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_reserved_names_blank_preserves():
    # Step 1: Set reserved_names to a known value
    update_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "reserved1.dys\\nreserved2.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Step 2: Query params to verify reserved_names was set
    params_query1 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    # Step 3: Update params with blank reserved_names (should preserve existing)
    update_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.02",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "",  # Blank - should preserve existing
            "name_suffix": ".dys"
        }
    })
    
    # Step 4: Query params again to verify reserved_names was preserved
    params_query2 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    return {
        "update_result1": update_result1,
        "params_before": params_query1["params"],
        "update_result2": update_result2,
        "params_after": params_query2["params"]
    }
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
        "demo_reserved_names_blank_preserves",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Verify params_before has reserved_names set
    params_before = demo_result["params_before"]
    assert isinstance(
        params_before, dict
    ), f"params_before should be dict, got {type(params_before)}"
    assert (
        "reserved_names" in params_before
    ), f"params_before missing 'reserved_names' key. Keys: {list(params_before.keys())}"
    assert params_before["reserved_names"] == "reserved1.dys\nreserved2.dys", (
        f"Expected reserved_names to be 'reserved1.dys\\nreserved2.dys', got: {params_before['reserved_names']}"
    )

    # Verify params_after preserved reserved_names (mint_fee_per_coin should be updated though)
    params_after = demo_result["params_after"]
    assert isinstance(
        params_after, dict
    ), f"params_after should be dict, got {type(params_after)}"
    assert (
        "reserved_names" in params_after
    ), f"params_after missing 'reserved_names' key. Keys: {list(params_after.keys())}"
    assert params_after["reserved_names"] == "reserved1.dys\nreserved2.dys", (
        f"Expected reserved_names to be preserved as 'reserved1.dys\\nreserved2.dys', got: {params_after['reserved_names']}"
    )
    assert params_after["mint_fee_per_coin"] == "0.02", (
        f"Expected mint_fee_per_coin to be updated to '0.02', got: {params_after['mint_fee_per_coin']}"
    )


def test_update_params_reserved_names_non_blank_updates(chainnet):
    """Test UpdateParams with non-blank reserved_names updates the value."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_reserved_names_updates():
    # Step 1: Set initial reserved_names
    update_result1 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "old1.dys\\nold2.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Step 2: Update with new reserved_names
    update_result2 = _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": {
            "mint_fee_per_coin": "0.01",
            "min_bid_timeout_class": "0s",
            "max_bid_timeout_class": "7776000s",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_valuation_period": "3600s",
            "max_valuation_period": "31536000s",
            "reserved_names": "new1.dys\\nnew2.dys\\nnew3.dys",
            "name_suffix": ".dys"
        }
    })
    
    # Step 3: Query params to verify reserved_names was updated
    params_query = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"
    })
    
    return {
        "update_result1": update_result1,
        "update_result2": update_result2,
        "params": params_query["params"]
    }
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
        "demo_reserved_names_updates",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(
        result, dict
    ), f"deep_parse should return dict. Got: {type(result)}"
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"demo_result should be dict, got {type(demo_result)}"

    # Verify reserved_names was updated
    params = demo_result["params"]
    assert isinstance(
        params, dict
    ), f"params should be dict, got {type(params)}"
    assert (
        "reserved_names" in params
    ), f"params missing 'reserved_names' key. Keys: {list(params.keys())}"
    assert params["reserved_names"] == "new1.dys\nnew2.dys\nnew3.dys", (
        f"Expected reserved_names to be 'new1.dys\\nnew2.dys\\nnew3.dys', got: {params['reserved_names']}"
    )
