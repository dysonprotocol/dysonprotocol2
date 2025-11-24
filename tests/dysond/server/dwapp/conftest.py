"""
Shared fixtures for DWApp server coverage tests.
"""

from textwrap import dedent

import pytest


@pytest.fixture(scope="session")
def dwapp_script_info(chainnet, api_address):
    """
    Deploy a single DWApp script once per test session.
    The fixture performs the lone allowed transaction (`dysond tx script update`)
    and returns connection details for HTTP coverage tests.
    """

    dysond = chainnet[0]

    status_result = dysond("status")
    chain_id = status_result["node_info"]["network"]

    alice_info = dysond(
        "keys",
        "show",
        "alice",
        "--keyring-backend",
        "test",
        "--output",
        "json",
    )
    script_address = alice_info["address"]
    host_header = f"{script_address}.localhost"

    script_code = dedent(
        """
        import json
        from io import BytesIO


        def _encode_payload(environ):
            wsgi_input = environ.get("wsgi.input")
            body_bytes = b""
            if wsgi_input is not None:
                body_bytes = wsgi_input.read()
                environ["wsgi.input"] = BytesIO(body_bytes)
            return json.dumps(
                {
                    "path": environ.get("PATH_INFO", ""),
                    "query": environ.get("QUERY_STRING", ""),
                    "method": environ.get("REQUEST_METHOD", ""),
                    "host": environ.get("HTTP_HOST", ""),
                    "body": body_bytes.decode("utf-8"),
                }
            ).encode("utf-8")


        def wsgi(environ, start_response):
            path = environ.get("PATH_INFO", "/")
            if path == "/cause-error":
                raise RuntimeError("intentional coverage error")
            if path == "/bad-status":
                start_response("BAD", [("Content-Type", "text/plain")])
                return [b"invalid status"]
            start_response("200 OK", [("Content-Type", "application/json")])
            return [_encode_payload(environ)]
        """
    ).strip()

    tx_result = dysond(
        "tx",
        "script",
        "update",
        "--from",
        "alice",
        "--code",
        script_code,
        "--chain-id",
        chain_id,
        "--gas-adjustment",
        "1.3",
    )
    assert tx_result.get("code", 1) == 0, f"DWApp script deployment failed: {tx_result}"

    base_url = f"http://{api_address['host']}:{api_address['port']}"

    return {
        "base_url": base_url,
        "host": host_header,
        "script_address": script_address,
    }
