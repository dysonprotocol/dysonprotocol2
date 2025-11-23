"""
VerifyTx query handler coverage tests.

Tests the VerifyTx query endpoint which verifies transaction signatures.
Covers success path, invalid signature, invalid JSON, oversized payload, and nil request error handling.
All tests use stateless script query execution with _query calls.
"""

import json
import pytest
import tempfile
from deep_parse import deep_parse


def test_verify_tx_success(chainnet):
    """Test VerifyTx query successfully verifies a valid signed transaction."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use existing alice key
    alice_name = "alice"
    alice_key_info = dysond("keys", "show", alice_name)
    alice_address = alice_key_info["address"]

    # Create a signed transaction using CLI (offline, no state changes)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=True
    ) as tx_file, tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=True
    ) as signed_tx_file:
        tx_json_path = tx_file.name
        signed_tx_json_path = signed_tx_file.name

        # Construct MsgArbitraryData transaction
        tx_data = {
            "body": {
                "messages": [
                    {
                        "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                        "signer": alice_address,
                        "data": "test data for verification",
                        "app_domain": "testApp/v1.0",
                    }
                ],
                "memo": "",
            },
            "auth_info": {"signer_infos": [], "fee": {"amount": [], "gas_limit": "0"}},
            "signatures": [],
        }
        json.dump(tx_data, tx_file)
        tx_file.flush()

        # Sign the transaction (offline, ADR-036 parameters)
        dysond(
            "tx",
            "sign",
            tx_json_path,
            "--from",
            alice_name,
            "--chain-id",
            "",
            "--account-number",
            "0",
            "--sequence",
            "0",
            "--offline",
            "--output-document",
            signed_tx_json_path,
            "--keyring-backend",
            "test",
        )

        # Read the signed transaction
        with open(signed_tx_json_path, "r") as f:
            signed_tx_json = f.read()

        extra_code = f"""
from dys import _query
import json

def demo_verify_tx():
    # Verify the signed transaction
    signed_tx = json.loads('''{signed_tx_json}''')
    
    verify_result = _query({{
        "@type": "/dysonprotocol.script.v1.QueryVerifyTxRequest",
        "tx_json": json.dumps(signed_tx)
    }})
    
    return {{
        "verify_result": verify_result
    }}
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
            "demo_verify_tx",
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
            "verify_result" in demo_result
        ), f"Result missing 'verify_result' key. Keys: {list(demo_result.keys())}"

        verify_result = demo_result["verify_result"]
        assert isinstance(
            verify_result, dict
        ), f"Verify result should be dict, got {type(verify_result)}"
        assert (
            "signer" in verify_result
        ), f"Verify result missing 'signer' key. Keys: {list(verify_result.keys())}"

        signer = verify_result["signer"]
        assert isinstance(signer, str), f"Signer should be string, got {type(signer)}"
        assert (
            signer == alice_address
        ), f"Expected signer '{alice_address}', got '{signer}'"


def test_verify_tx_invalid_signature(chainnet):
    """Test VerifyTx query handles invalid signature."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Use existing alice key
    alice_name = "alice"
    alice_key_info = dysond("keys", "show", alice_name)
    alice_address = alice_key_info["address"]

    # Create a signed transaction, then tamper with the signature
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=True
    ) as tx_file, tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=True
    ) as signed_tx_file:
        tx_json_path = tx_file.name
        signed_tx_json_path = signed_tx_file.name

        tx_data = {
            "body": {
                "messages": [
                    {
                        "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                        "signer": alice_address,
                        "data": "test data",
                        "app_domain": "testApp/v1.0",
                    }
                ],
                "memo": "",
            },
            "auth_info": {"signer_infos": [], "fee": {"amount": [], "gas_limit": "0"}},
            "signatures": [],
        }
        json.dump(tx_data, tx_file)
        tx_file.flush()

        dysond(
            "tx",
            "sign",
            tx_json_path,
            "--from",
            alice_name,
            "--chain-id",
            "",
            "--account-number",
            "0",
            "--sequence",
            "0",
            "--offline",
            "--output-document",
            signed_tx_json_path,
            "--keyring-backend",
            "test",
        )

        with open(signed_tx_json_path, "r") as f:
            signed_tx_data = json.load(f)

        # Tamper with the signature
        original_sig = signed_tx_data["signatures"][0]
        sig_list = list(original_sig)
        sig_list[10] = "A" if sig_list[10] != "A" else "B"
        signed_tx_data["signatures"][0] = "".join(sig_list)
        tampered_tx_json = json.dumps(signed_tx_data)

        extra_code = f"""
from dys import _query
import json

def demo_verify_invalid_sig():
    # Attempt to verify transaction with tampered signature
    try:
        tampered_tx = json.loads('''{tampered_tx_json}''')
        verify_result = _query({{
            "@type": "/dysonprotocol.script.v1.QueryVerifyTxRequest",
            "tx_json": json.dumps(tampered_tx)
        }})
        return {{"error": "Should have failed", "result": verify_result}}
    except Exception as e:
        return {{"error": str(e), "expected": True}}
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
            "demo_verify_invalid_sig",
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
        assert (
            "error" in demo_result
        ), f"Result missing 'error' key. Keys: {list(demo_result.keys())}"
        error_str = demo_result["error"]
        assert isinstance(
            error_str, str
        ), f"Error should be string, got {type(error_str)}"
        assert (
            "verification failed" in error_str.lower()
        ), f"Expected 'verification failed' in error message, got: {error_str}"


def test_verify_tx_invalid_json(chainnet):
    """Test VerifyTx query handles invalid JSON."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_verify_invalid_json():
    # Attempt to verify with invalid JSON
    try:
        verify_result = _query({
            "@type": "/dysonprotocol.script.v1.QueryVerifyTxRequest",
            "tx_json": "{invalid json}"
        })
        return {"error": "Should have failed", "result": verify_result}
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
        "demo_verify_invalid_json",
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
    assert (
        "error" in demo_result
    ), f"Result missing 'error' key. Keys: {list(demo_result.keys())}"
    error_str = demo_result["error"]
    assert isinstance(error_str, str), f"Error should be string, got {type(error_str)}"
    assert (
        "failed to decode" in error_str.lower()
    ), f"Expected 'failed to decode' in error message, got: {error_str}"


def test_verify_tx_empty_json(chainnet):
    """Test VerifyTx query handles empty JSON."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_verify_empty_json():
    # Attempt to verify with empty JSON
    try:
        verify_result = _query({
            "@type": "/dysonprotocol.script.v1.QueryVerifyTxRequest",
            "tx_json": ""
        })
        return {"error": "Should have failed", "result": verify_result}
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
        "demo_verify_empty_json",
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
    assert (
        "error" in demo_result
    ), f"Result missing 'error' key. Keys: {list(demo_result.keys())}"
    error_str = demo_result["error"]
    assert isinstance(error_str, str), f"Error should be string, got {type(error_str)}"
    assert (
        "empty" in error_str.lower()
    ), f"Expected 'empty' in error message, got: {error_str}"


def test_verify_tx_oversized_payload(chainnet):
    """Test VerifyTx query handles oversized payload (>50,000 characters)."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_verify_oversized():
    # Create a transaction JSON > 50,000 characters
    large_tx_json = '{"body": {"messages": [{"@type": "/dysonprotocol.script.v1.MsgArbitraryData", "signer": "dys1test", "data": "' + 'x' * 50001 + '", "app_domain": "test"}]}, "auth_info": {"signer_infos": [], "fee": {"amount": [], "gas_limit": "0"}}, "signatures": []}'
    
    try:
        verify_result = _query({
            "@type": "/dysonprotocol.script.v1.QueryVerifyTxRequest",
            "tx_json": large_tx_json
        })
        return {"error": "Should have failed", "result": verify_result}
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
        "demo_verify_oversized",
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
    assert (
        "error" in demo_result
    ), f"Result missing 'error' key. Keys: {list(demo_result.keys())}"
    error_str = demo_result["error"]
    assert isinstance(error_str, str), f"Error should be string, got {type(error_str)}"
    assert (
        "too large" in error_str.lower()
    ), f"Expected 'too large' in error message, got: {error_str}"


def test_verify_tx_nil_request(chainnet):
    """Test VerifyTx query handles nil request error."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_verify_nil_request():
    # Attempt to query with None/null request
    try:
        verify_result = _query(None)
        return {"error": "Should have failed", "result": verify_result}
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
        "demo_verify_nil_request",
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
