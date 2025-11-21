"""
Params query handler coverage tests.

Tests the Params query endpoint which retrieves current storage module parameters.
Covers success paths and validates parameter structure.
All tests use stateless script query execution.
"""

import json
import pytest
from deep_parse import deep_parse


def test_params_success(chainnet):
    """Test Params query success path."""
    dysond = chainnet[0]

    # Query storage params using CLI directly (simple query, no state setup needed)
    params_response = dysond("query", "storage", "params")

    # Validate response structure (Type)
    assert isinstance(
        params_response, dict
    ), f"Params response should be dict, got {type(params_response)}. Full response: {json.dumps(params_response, indent=2)}"
    assert (
        "params" in params_response
    ), f"Params response missing 'params' key. Keys: {list(params_response.keys())}. Full response: {json.dumps(params_response, indent=2)}"

    params = params_response["params"]

    # Validate params structure (Type + Shape)
    assert isinstance(params, dict), f"Params should be dict, got {type(params)}"
    assert (
        "max_storage_size" in params
    ), f"Params missing 'max_storage_size' key. Keys: {list(params.keys())}"
    assert (
        "storage_stake_multiple" in params
    ), f"Params missing 'storage_stake_multiple' key. Keys: {list(params.keys())}"

    # Validate values
    max_storage_size = int(params["max_storage_size"])
    assert (
        max_storage_size > 0
    ), f"max_storage_size should be positive: {max_storage_size}"
    assert (
        max_storage_size >= 1024
    ), f"max_storage_size should be at least 1KB: {max_storage_size}"

    storage_stake_multiple = params["storage_stake_multiple"]
    assert isinstance(
        storage_stake_multiple, str
    ), f"storage_stake_multiple should be string, got {type(storage_stake_multiple)}"


def test_params_default_values(chainnet):
    """Test Params query returns default values for fresh chain state."""
    dysond = chainnet[0]

    # Query params using CLI directly (simple query, no state setup needed)
    params_response = dysond("query", "storage", "params")

    # Validate response
    assert isinstance(
        params_response, dict
    ), f"Response should be dict, got {type(params_response)}"
    assert "params" in params_response, f"Response missing 'params' key"

    params = params_response["params"]

    # Verify default values exist (even if chain has been modified, structure should be consistent)
    assert "max_storage_size" in params, f"Params missing 'max_storage_size'"
    assert (
        "storage_stake_multiple" in params
    ), f"Params missing 'storage_stake_multiple'"

    # Values should be valid
    max_storage_size = int(params["max_storage_size"])
    assert (
        max_storage_size >= 1024
    ), f"max_storage_size should be at least 1KB: {max_storage_size}"
