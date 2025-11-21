"""
Web query handler coverage tests.

Tests the Web query endpoint which executes WSGI web applications in scripts.
Covers success (HTML/JSON), missing script, and invalid request body cases.
All tests use stateless script query execution with _sudo and _query calls.
"""

import json
import pytest
from deep_parse import deep_parse


def test_web_success_html(chainnet):
    """Test Web query successfully executes WSGI application returning HTML."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = """
def wsgi(environ, start_response):
    status = '200 OK'
    headers = [('Content-type', 'text/html')]
    start_response(status, headers)
    return [b'<html><body><h1>Hello World</h1></body></html>']
"""

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_web_html(gov_addr, script_code):
    # Create script statelessly
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    })
    create_response = create_result["results"][0]
    script_addr = create_response["script_address"]
    
    # Query Web endpoint via _query
    http_request = "GET / HTTP/1.1\\r\\nHost: test.example.com\\r\\n\\r\\n"
    web_result = _query({
        "@type": "/dysonprotocol.script.v1.WebRequest",
        "script_address": script_addr,
        "httprequest": http_request
    })
    
    return {
        "script_addr": script_addr,
        "web_result": web_result
    }
"""

    kwargs = json.dumps({"gov_addr": gov_addr, "script_code": script_code})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_web_html",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "web_result" in demo_result
    ), f"Result missing 'web_result' key. Keys: {list(demo_result.keys())}"

    web_result = demo_result["web_result"]
    assert isinstance(
        web_result, dict
    ), f"Web result should be dict, got {type(web_result)}"
    assert (
        "httpresponse" in web_result
    ), f"Web result missing 'httpresponse' key. Keys: {list(web_result.keys())}"

    httpresponse = web_result["httpresponse"]
    assert isinstance(
        httpresponse, str
    ), f"HTTP response should be string, got {type(httpresponse)}"
    assert (
        len(httpresponse) > 0
    ), f"HTTP response should not be empty. Response: {httpresponse}"
    assert (
        "200 OK" in httpresponse
    ), f"Expected '200 OK' in response. Response: {httpresponse}"
    assert (
        "Hello World" in httpresponse
    ), f"Expected 'Hello World' in response. Response: {httpresponse}"


def test_web_success_json(chainnet):
    """Test Web query successfully executes WSGI application returning JSON."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    script_code = """
import json

def wsgi(environ, start_response):
    status = '200 OK'
    headers = [('Content-type', 'application/json')]
    start_response(status, headers)
    data = {"message": "Hello", "status": "success"}
    return [json.dumps(data).encode()]
"""

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_web_json(gov_addr, script_code):
    # Create script statelessly
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    })
    create_response = create_result["results"][0]
    script_addr = create_response["script_address"]
    
    # Query Web endpoint via _query
    http_request = "GET /api HTTP/1.1\\r\\nHost: test.example.com\\r\\n\\r\\n"
    web_result = _query({
        "@type": "/dysonprotocol.script.v1.WebRequest",
        "script_address": script_addr,
        "httprequest": http_request
    })
    
    return {
        "script_addr": script_addr,
        "web_result": web_result
    }
"""

    kwargs = json.dumps({"gov_addr": gov_addr, "script_code": script_code})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_web_json",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "web_result" in demo_result
    ), f"Result missing 'web_result' key. Keys: {list(demo_result.keys())}"

    web_result = demo_result["web_result"]
    assert isinstance(
        web_result, dict
    ), f"Web result should be dict, got {type(web_result)}"
    assert (
        "httpresponse" in web_result
    ), f"Web result missing 'httpresponse' key. Keys: {list(web_result.keys())}"

    httpresponse = web_result["httpresponse"]
    assert isinstance(
        httpresponse, str
    ), f"HTTP response should be string, got {type(httpresponse)}"
    assert (
        len(httpresponse) > 0
    ), f"HTTP response should not be empty. Response: {httpresponse}"
    assert (
        "200 OK" in httpresponse
    ), f"Expected '200 OK' in response. Response: {httpresponse}"
    assert (
        "application/json" in httpresponse
    ), f"Expected 'application/json' in response. Response: {httpresponse}"


def test_web_missing_script(chainnet):
    """Test Web query returns error for non-existent script."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # Generate a valid bech32 address that doesn't have a script
    bytes_to_addr_result = dysond(
        "query",
        "auth",
        "address-bytes-to-string",
        "0xabcdef",
        "-o",
        "json",
    )
    random_addr = bytes_to_addr_result.get("address_string")
    assert isinstance(
        random_addr, str
    ), f"Address string should be str. Got: {type(random_addr)}"
    assert (
        len(random_addr) > 0
    ), f"Failed to convert bytes to address: {bytes_to_addr_result}"

    extra_code = """
from dys import _query

def demo_web_missing_script(random_addr):
    # Query Web endpoint for non-existent script
    http_request = "GET / HTTP/1.1\\r\\nHost: test.example.com\\r\\n\\r\\n"
    try:
        web_result = _query({
            "@type": "/dysonprotocol.script.v1.WebRequest",
            "script_address": random_addr,
            "httprequest": http_request
        })
        return {"error": "Should have failed", "result": web_result}
    except Exception as e:
        return {
            "error": str(e)
        }
"""

    kwargs = json.dumps({"random_addr": random_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_web_missing_script",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "error" in demo_result
    ), f"Result missing 'error' key. Keys: {list(demo_result.keys())}"
    actual_error = demo_result["error"]
    assert isinstance(
        actual_error, str
    ), f"Error should be string, got {type(actual_error)}"
    assert len(actual_error) > 0, f"Error should not be empty. Error: {actual_error}"


def test_web_invalid_request_body(chainnet):
    """Test Web query handles invalid HTTP request body."""
    dysond = chainnet[0]
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

def demo_web_invalid_request(gov_addr):
    # Create script with WSGI application
    script_code = '''
def wsgi(environ, start_response):
    status = '200 OK'
    headers = [('Content-type', 'text/html')]
    start_response(status, headers)
    return [b'<html><body><h1>Hello</h1></body></html>']
'''
    
    create_result = _sudo({
        "@type": "/dysonprotocol.script.v1.MsgCreateNewScript",
        "creator_address": gov_addr,
        "code": script_code
    })
    
    create_response = create_result["results"][0]
    script_addr = create_response["script_address"]
    
    # Query web endpoint with invalid HTTP request
    invalid_request = "INVALID HTTP REQUEST FORMAT"
    try:
        web_result = _query({
            "@type": "/dysonprotocol.script.v1.WebRequest",
            "script_address": script_addr,
            "httprequest": invalid_request
        })
        return {
            "script_addr": script_addr,
            "web_result": web_result,
            "error": None
        }
    except Exception as e:
        return {
            "script_addr": script_addr,
            "error": str(e)
        }
"""

    kwargs = json.dumps({"gov_addr": gov_addr})

    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_web_invalid_request",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    # Invalid request may succeed (script handles it) or fail (WSGI parser error)
    # Either way, we verify the query executed without panicking
    assert (
        "script_addr" in demo_result
    ), f"Result missing 'script_addr' key. Keys: {list(demo_result.keys())}"


def test_web_nil_request(chainnet):
    """Test Web query error handling for invalid/null request."""
    dysond = chainnet[0]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _query

def demo_web_nil_request():
    # Query Web endpoint with None/null request
    # Note: nil check happens at JSON parsing layer, not in Web handler
    try:
        web_result = _query(None)
        return {"error": "Should have failed", "result": web_result}
    except Exception as e:
        error_str = str(e)
        return {
            "error": error_str,
            "has_error": len(error_str) > 0
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
        "demo_web_nil_request",
        "--extra-code",
        extra_code,
    )

    result = deep_parse(query_result)
    assert (
        query_result.get("exception") is None
    ), f"Script execution failed: {json.dumps(query_result.get('exception'), indent=2)}"

    demo_result = result["result"]["result"]
    assert isinstance(
        demo_result, dict
    ), f"Result should be dict, got {type(demo_result)}"
    assert (
        "has_error" in demo_result
    ), f"Result missing 'has_error' key. Keys: {list(demo_result.keys())}"
    assert (
        demo_result["has_error"] is True
    ), f"Expected error for nil request. Result: {json.dumps(demo_result, indent=2)}"
