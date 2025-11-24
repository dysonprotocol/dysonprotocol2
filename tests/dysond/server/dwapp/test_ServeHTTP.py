"""
ServeHTTP coverage tests for the DWApp handler (HTTP layers only).
"""

import pytest
import requests


def _request(base_url, host, path, method="GET", **kwargs):
    return requests.request(
        method,
        f"{base_url}{path}",
        headers={"Host": host},
        timeout=10,
        allow_redirects=False,
        **kwargs,
    )


def test_ServeHTTP_success_returns_json(dwapp_script_info):
    """
    Visiting the script host root should proxy through the WSGI script and return JSON.
    """

    response = _request(dwapp_script_info["base_url"], dwapp_script_info["host"], "/")
    assert response.status_code == 200, f"Unexpected status: {response.text}"
    body = response.json()
    assert body["path"] == "/"
    assert body["method"] == "GET"
    assert body["host"] == dwapp_script_info["host"]
    assert body["query"] == ""
    assert body["body"] == ""


def test_ServeHTTP_script_exception_propagates(dwapp_script_info):
    """
    Script exceptions should bubble up as HTTP 500 responses with diagnostic text.
    """

    response = _request(
        dwapp_script_info["base_url"],
        dwapp_script_info["host"],
        "/cause-error",
    )
    assert response.status_code == 500, f"Expected 500, got {response.status_code}"
    assert "Error:" in response.text, f"Missing exception details: {response.text}"


def test_ServeHTTP_missing_script_returns_hint(dwapp_script_info):
    """
    Requests for an unknown dys21... host return the onboarding hint text.
    """

    unknown_host = "dys21zzzzzzzzzzzzzzzzzz.localhost"
    response = _request(dwapp_script_info["base_url"], unknown_host, "/")
    assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    assert "Minimal Hello World example" in response.text


def test_ServeHTTP_invalid_host_pattern(dwapp_script_info):
    """
    Hosts that do not match the configured regex should be rejected.
    """

    response = _request(dwapp_script_info["base_url"], "localhost", "/")
    assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    assert "No match for host" in response.text


def test_redirect_to_dwapp_name(dwapp_script_info):
    """
    /redirect-to-dwapp/<name>.dys should issue a 307 to the templated public host.
    """

    response = _request(
        dwapp_script_info["base_url"],
        dwapp_script_info["host"],
        "/redirect-to-dwapp/example.dys/profile?foo=bar",
    )
    assert response.status_code == 307
    expected = "//example.localhost:1317/profile?foo=bar"
    assert response.headers["Location"] == expected


def test_redirect_to_dwapp_address(dwapp_script_info):
    """
    /redirect-to-dwapp/<dys2...> should redirect to the matching address host.
    """

    script_address = dwapp_script_info["script_address"]
    response = _request(
        dwapp_script_info["base_url"],
        dwapp_script_info["host"],
        f"/redirect-to-dwapp/{script_address}",
    )
    assert response.status_code == 307
    expected = f"//{script_address}.localhost:1317"
    assert response.headers["Location"] == expected


def test_redirect_to_dwapp_invalid_identifier(dwapp_script_info):
    """
    Missing .dys suffix or dys2 prefix should be rejected with HTTP 400.
    """

    response = _request(
        dwapp_script_info["base_url"],
        dwapp_script_info["host"],
        "/redirect-to-dwapp/not-valid-id",
    )
    assert response.status_code == 400
    assert "must end with .dys" in response.text


def test_ServeHTTP_preserves_query_string(dwapp_script_info):
    """
    Query parameters should be forwarded to the script unchanged.
    """

    response = _request(
        dwapp_script_info["base_url"],
        dwapp_script_info["host"],
        "/?foo=bar&baz=1",
    )
    body = response.json()
    assert body["query"] == "foo=bar&baz=1"


def test_ServeHTTP_post_body_echo(dwapp_script_info):
    """
    POST bodies should traverse getRawRequest and reach the script intact.
    """

    payload = "message=hello"
    response = _request(
        dwapp_script_info["base_url"],
        dwapp_script_info["host"],
        "/echo",
        method="POST",
        data=payload,
    )
    body = response.json()
    assert body["method"] == "POST"
    assert body["body"] == payload


def test_getRawRequest_replays_body(dwapp_script_info):
    """
    Subsequent reads (after getRawRequest rewinds the body) still observe the payload.
    """

    payload = "alpha=beta"
    response = _request(
        dwapp_script_info["base_url"],
        dwapp_script_info["host"],
        "/inspect",
        method="POST",
        data=payload,
    )
    body = response.json()
    assert body["path"] == "/inspect"
    assert body["body"] == payload


def test_ServeHTTP_unknown_name_redirects(dwapp_script_info):
    """
    /redirect-to-dwapp/<name>.dys resolves to the public host template even if unknown.
    """

    response = _request(
        dwapp_script_info["base_url"],
        dwapp_script_info["host"],
        "/redirect-to-dwapp/foo.dys",
    )
    assert response.status_code == 307
    assert "//foo.localhost:1317" in response.headers["Location"]


def test_ServeHTTP_nameless_address_hint(chainnet, dwapp_script_info):
    """
    Hosts with syntactically valid dys21... addresses but no script should return the setup hint.
    """

    dysond = chainnet[0]
    addr_result = dysond(
        "query",
        "auth",
        "address-bytes-to-string",
        "0xabcdef",
        "-o",
        "json",
    )
    random_addr = addr_result["address_string"]
    response = _request(
        dwapp_script_info["base_url"],
        random_addr + ".localhost",
        "/",
    )
    assert response.status_code == 404
    assert "Hello World example" in response.text


def test_ServeHTTP_invalid_bech32_returns_hint(dwapp_script_info):
    """
    Invalid dys21 hostnames (bad checksum) should yield the onboarding hint text.
    """

    response = _request(
        dwapp_script_info["base_url"],
        "dys21invalidaddress.localhost",
        "/",
    )
    assert response.status_code == 404
    assert "is not a valid Dys script address" in response.text


def test_ServeHTTP_invalid_method(dwapp_script_info):
    """
    Non-GET verbs hitting redirect endpoints should still reject invalid identifiers.
    """

    response = _request(
        dwapp_script_info["base_url"],
        dwapp_script_info["host"],
        "/redirect-to-dwapp/invalid",
        method="POST",
        data="",
    )
    assert response.status_code == 400


def test_ServeHTTP_rpc_proxy_missing(dwapp_script_info):
    response = _request(
        dwapp_script_info["base_url"],
        dwapp_script_info["host"],
        "/rpc/health",
    )
    assert response.status_code in (200, 502)


def test_ServeHTTP_regex_name_redirect(dwapp_script_info):
    response = _request(
        dwapp_script_info["base_url"],
        "foo.dwapp.localhost",
        "/",
    )
    assert response.status_code == 302
    assert "/names/foo.dys" in response.headers["Location"]
