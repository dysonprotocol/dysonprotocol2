"""
Metrics query handler coverage tests.

Tests the Metrics query endpoint which retrieves
storage usage metrics and stake requirements for an owner. Covers all validation paths,
success cases, name resolution, and metrics calculation.
All tests use stateless script query execution.
"""

import json
import pytest
from deep_parse import deep_parse


def test_metrics_success_with_storage(chainnet):
    """Test Metrics query with owner that has storage entries."""
    dysond = chainnet[0]
    owner_addr = "dys216vwht46aw58efaxx"
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_metrics_with_storage(owner_addr, test_index, test_data):
    # Set storage entry using _sudo
    _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": test_index,
        "data": test_data
    })
    
    # Query metrics
    metrics_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryMetricsRequest",
        "owner": owner_addr
    })
    
    return {"metrics_response": metrics_response}
"""

    test_data = "Hello, World!"
    expected_bytes = len(test_data.encode("utf-8"))
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "test_index": "test/greeting",
            "test_data": test_data,
        }
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
        "demo_metrics_with_storage",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    assert isinstance(result, dict), f"Result should be dict, got {type(result)}"
    assert "result" in result

    demo_result = result["result"]["result"]
    metrics_response = demo_result["metrics_response"]

    # Validate response structure (Type)
    assert isinstance(
        metrics_response, dict
    ), f"Metrics response should be dict, got {type(metrics_response)}. Full response: {json.dumps(metrics_response, indent=2)}"
    assert (
        "owner" in metrics_response
    ), f"Metrics response missing 'owner' key. Keys: {list(metrics_response.keys())}. Full response: {json.dumps(metrics_response, indent=2)}"
    assert (
        "total_bytes" in metrics_response
    ), f"Metrics response missing 'total_bytes' key. Keys: {list(metrics_response.keys())}"
    assert (
        "min_stake_amount" in metrics_response
    ), f"Metrics response missing 'min_stake_amount' key. Keys: {list(metrics_response.keys())}"
    assert (
        "current_stake_amount" in metrics_response
    ), f"Metrics response missing 'current_stake_amount' key. Keys: {list(metrics_response.keys())}"

    # Validate values
    assert (
        metrics_response["owner"] == owner_addr
    ), f"Owner mismatch: expected {owner_addr}, got {metrics_response['owner']}"
    assert (
        int(metrics_response["total_bytes"]) == expected_bytes
    ), f"Total bytes mismatch: expected {expected_bytes}, got {metrics_response['total_bytes']}"


def test_metrics_empty_address(chainnet):
    """Test Metrics query with owner that has no storage entries."""
    dysond = chainnet[0]
    owner_addr = "dys216vwmdkmdkcsz2qrh"
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_metrics_empty(owner_addr):
    # Query metrics for address with no storage
    metrics_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryMetricsRequest",
        "owner": owner_addr
    })
    return {"metrics_response": metrics_response}
"""

    kwargs = json.dumps({"owner_addr": owner_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_metrics_empty",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    assert isinstance(result, dict), f"Result should be dict, got {type(result)}"
    assert "result" in result

    demo_result = result["result"]["result"]
    metrics_response = demo_result["metrics_response"]

    # Validate response structure
    assert isinstance(
        metrics_response, dict
    ), f"Response should be dict, got {type(metrics_response)}"
    assert "owner" in metrics_response, f"Response missing 'owner' key"
    assert "total_bytes" in metrics_response, f"Response missing 'total_bytes' key"
    assert (
        "min_stake_amount" in metrics_response
    ), f"Response missing 'min_stake_amount' key"
    assert (
        "current_stake_amount" in metrics_response
    ), f"Response missing 'current_stake_amount' key"

    # Validate zero metrics
    assert (
        metrics_response["owner"] == owner_addr
    ), f"Owner mismatch: expected {owner_addr}, got {metrics_response['owner']}"
    assert (
        metrics_response["total_bytes"] == "0"
    ), f"Total bytes should be 0 for empty address, got {metrics_response['total_bytes']}"
    assert (
        metrics_response["min_stake_amount"] == "0"
    ), f"Min stake should be 0 for 0 bytes, got {metrics_response['min_stake_amount']}"


def test_metrics_name_resolution(chainnet):
    """Test Metrics query with nameservice name resolution."""
    dysond = chainnet[0]
    owner_addr = "dys216vwht46aw58efaxx"

    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address
import re

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def _parse_coin(s):
    m = re.fullmatch(r"(\\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {"denom": m.group(2), "amount": m.group(1)}

def _register_name(name, destination, valuation="10udys"):
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
        "valuation": _parse_coin(valuation),
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
        "destination": destination,
    })

    return name

def demo_metrics_name_resolution(owner_addr, test_index, test_data):
    # Register name and set destination
    ns_name = _register_name("test-metrics-name.dys", owner_addr)

    # Set storage entry
    _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": test_index,
        "data": test_data
    })

    # Query metrics using nameservice name
    metrics_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryMetricsRequest",
        "owner": ns_name
    })
    
    return {"metrics_response": metrics_response}
"""

    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "test_index": "test/name_metrics",
            "test_data": '{"test": "name"}',
        }
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
        "demo_metrics_name_resolution",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    assert isinstance(result, dict), f"Result should be dict, got {type(result)}"
    assert "result" in result

    demo_result = result["result"]["result"]
    metrics_response = demo_result["metrics_response"]

    assert isinstance(
        metrics_response, dict
    ), f"Response should be dict, got {type(metrics_response)}"
    assert "owner" in metrics_response, f"Response missing 'owner' key"

    # Owner should be resolved address
    assert (
        metrics_response["owner"] == owner_addr
    ), f"Owner should be resolved address: expected {owner_addr}, got {metrics_response['owner']}"


def test_metrics_invalid_owner(chainnet):
    """Test Metrics query with invalid/unresolvable owner."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_metrics_invalid_owner(invalid_owner):
    # Query with invalid owner address
    try:
        metrics_response = _query({
            "@type": "/dysonprotocol.storage.v1.QueryMetricsRequest",
            "owner": invalid_owner
        })
        return {"metrics_response": metrics_response, "error": None}
    except Exception as e:
        return {"error": str(e)}
"""

    kwargs = json.dumps({"invalid_owner": "invalid_address"})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_metrics_invalid_owner",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert isinstance(result, dict), f"Result should be dict, got {type(result)}"
    assert (
        "result" in result
    ), f"Result missing 'result' key. Keys: {list(result.keys())}"
    demo_result = result["result"]["result"]

    # Should have error
    assert (
        demo_result.get("error") is not None
    ), f"Expected error for invalid owner, got: {json.dumps(demo_result, indent=2)}"
    error_str = str(demo_result["error"]).lower()
    assert (
        "failed to resolve owner" in error_str
    ), f"Expected resolution error containing 'failed to resolve owner', got: {demo_result['error']}"


def test_metrics_stake_calculation(chainnet):
    """Test Metrics query calculates min_stake_amount correctly."""
    dysond = chainnet[0]
    owner_addr = "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej"
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_metrics_stake_calculation(owner_addr, test_index, test_data):
    # Get params to check storage_stake_multiple
    params_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryParamsRequest"
    })
    stake_multiple = float(params_response["params"]["storage_stake_multiple"])
    
    # Set storage entry
    _sudo({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner_addr,
        "index": test_index,
        "data": test_data
    })
    
    # Query metrics
    metrics_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryMetricsRequest",
        "owner": owner_addr
    })
    
    return {
        "metrics_response": metrics_response,
        "stake_multiple": stake_multiple
    }
"""

    test_data = "x" * 1000  # 1000 bytes
    kwargs = json.dumps(
        {
            "owner_addr": owner_addr,
            "test_index": "test/stake_calc",
            "test_data": test_data,
        }
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
        "demo_metrics_stake_calculation",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"

    assert isinstance(result, dict), f"Result should be dict, got {type(result)}"
    assert "result" in result

    demo_result = result["result"]["result"]
    metrics_response = demo_result["metrics_response"]
    stake_multiple = demo_result["stake_multiple"]

    # Validate stake calculation
    assert isinstance(
        metrics_response, dict
    ), f"Response should be dict, got {type(metrics_response)}"
    assert "total_bytes" in metrics_response, f"Response missing 'total_bytes' key"
    assert (
        "min_stake_amount" in metrics_response
    ), f"Response missing 'min_stake_amount' key"

    total_bytes = int(metrics_response["total_bytes"])
    min_stake = int(metrics_response["min_stake_amount"])

    # Calculate expected min stake
    expected_min_stake = int(total_bytes * stake_multiple)
    assert (
        min_stake == expected_min_stake
    ), f"Min stake mismatch: expected {expected_min_stake} (total_bytes={total_bytes} * multiplier={stake_multiple}), got {min_stake}"


def test_metrics_current_stake(chainnet):
    """Test Metrics query retrieves current stake amount from staking module."""
    dysond = chainnet[0]
    owner_addr = "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e"
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_metrics_current_stake(owner_addr, validator_addr):
    # Delegate tokens using _sudo
    _sudo({
        "@type": "/cosmos.staking.v1beta1.MsgDelegate",
        "delegator_address": owner_addr,
        "validator_address": validator_addr,
        "amount": {"denom": "udys", "amount": "1000000"}
    })
    
    # Query metrics
    metrics_response = _query({
        "@type": "/dysonprotocol.storage.v1.QueryMetricsRequest",
        "owner": owner_addr
    })
    
    return {"metrics_response": metrics_response}
"""

    # Get validator address
    validators_result = dysond("query", "staking", "validators")
    assert len(validators_result["validators"]) > 0, "Need at least one validator"
    validator_addr = validators_result["validators"][0]["operator_address"]

    kwargs = json.dumps({"owner_addr": owner_addr, "validator_addr": validator_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_metrics_current_stake",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"
    assert isinstance(result, dict), f"Result should be dict, got {type(result)}"
    assert "result" in result

    demo_result = result["result"]["result"]
    metrics_response = demo_result["metrics_response"]

    # Validate current stake amount
    assert isinstance(
        metrics_response, dict
    ), f"Response should be dict, got {type(metrics_response)}"
    assert (
        "current_stake_amount" in metrics_response
    ), f"Response missing 'current_stake_amount' key"

    current_stake = int(metrics_response["current_stake_amount"])
    assert (
        current_stake >= 1000000
    ), f"Current stake should be at least delegated amount (1000000), got {current_stake}"
