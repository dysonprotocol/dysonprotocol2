"""
ServeHTTP coverage tests for the DWApp handler (HTTP layers only).
"""

import pytest
import requests


def _request(base_url, host, path, method="GET", headers=None, **kwargs):
    all_headers = {"Host": host} | (headers or {})
    return requests.request(
        method,
        f"{base_url}{path}",
        headers=all_headers,
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
    assert response.status_code == 404
    assert 'Name "foo.dys" could not be resolved.' in response.text


# =============================================================================
# Content Negotiation Tests (PBI-42)
# =============================================================================


def test_404_missing_script_returns_json(dwapp_script_info):
    """Verify 404 returns JSON structure when Accept: application/json."""
    unknown_host = "dys21zzzzzzzzzzzzzzzzzz.localhost"
    response = _request(
        dwapp_script_info["base_url"],
        unknown_host,
        "/",
        headers={"Host": unknown_host, "Accept": "application/json"},
    )

    assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    content_type = response.headers.get("Content-Type", "")
    assert "application/json" in content_type, f"Expected JSON, got {content_type}"

    body = response.json()
    assert isinstance(body, dict), f"Expected dict, got {type(body)}"
    assert body["error"] == "not_found", f"Wrong error: {body}"
    assert body["code"] == 404, f"Wrong code: {body}"
    assert "input" in body, f"Missing input: {body}"
    assert "message" in body, f"Missing message: {body}"
    assert "hint" in body, f"Missing hint: {body}"
    # Verify hint includes the public host template
    assert "yourname" in body["hint"], f"Hint should include template URL: {body['hint']}"


def test_404_invalid_bech32_returns_json(dwapp_script_info):
    """Verify invalid bech32 returns JSON when requested."""
    response = _request(
        dwapp_script_info["base_url"],
        "dys21invalidaddress.localhost",
        "/",
        headers={"Host": "dys21invalidaddress.localhost", "Accept": "application/json"},
    )

    assert response.status_code == 404
    assert "application/json" in response.headers.get("Content-Type", "")
    body = response.json()
    assert body["error"] == "not_found"
    assert "dys21invalidaddress" in body["input"]
    assert "yourname" in body["hint"]


def test_404_unresolved_name_returns_json(dwapp_script_info):
    """Verify unresolved name returns JSON when requested."""
    response = _request(
        dwapp_script_info["base_url"],
        "foo.dwapp.localhost",
        "/",
        headers={"Host": "foo.dwapp.localhost", "Accept": "application/json"},
    )

    assert response.status_code == 404
    assert "application/json" in response.headers.get("Content-Type", "")
    body = response.json()
    assert body["error"] == "not_found"
    assert "foo.dys" in body["input"]
    assert "yourname" in body["hint"]


def test_404_invalid_host_returns_json(dwapp_script_info):
    """Verify invalid host pattern returns JSON when requested."""
    response = _request(
        dwapp_script_info["base_url"],
        "localhost",
        "/",
        headers={"Host": "localhost", "Accept": "application/json"},
    )

    assert response.status_code == 404
    assert "application/json" in response.headers.get("Content-Type", "")
    body = response.json()
    assert body["error"] == "not_found"
    assert "localhost" in body["input"]


def test_404_missing_script_returns_html(dwapp_script_info):
    """Verify 404 returns HTML when Accept: text/html."""
    unknown_host = "dys21zzzzzzzzzzzzzzzzzz.localhost"
    response = _request(
        dwapp_script_info["base_url"],
        unknown_host,
        "/",
        headers={"Host": unknown_host, "Accept": "text/html"},
    )

    assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    content_type = response.headers.get("Content-Type", "")
    assert "text/html" in content_type, f"Expected HTML, got {content_type}"

    body = response.text
    assert "<!DOCTYPE html>" in body, f"Missing DOCTYPE: {body[:200]}"
    assert "<title>404 Not Found" in body, f"Missing title: {body[:500]}"
    assert "How to Fix" in body, f"Missing hint section: {body}"
    assert "yourname" in body, f"Missing template URL: {body}"


def test_404_invalid_bech32_returns_html(dwapp_script_info):
    """Verify invalid bech32 returns HTML when requested."""
    response = _request(
        dwapp_script_info["base_url"],
        "dys21invalidaddress.localhost",
        "/",
        headers={"Host": "dys21invalidaddress.localhost", "Accept": "text/html"},
    )

    assert response.status_code == 404
    assert "text/html" in response.headers.get("Content-Type", "")
    body = response.text
    assert "<!DOCTYPE html>" in body
    assert "dys21invalidaddress" in body
    assert "yourname" in body


def test_404_unresolved_name_returns_html(dwapp_script_info):
    """Verify unresolved name returns HTML when requested."""
    response = _request(
        dwapp_script_info["base_url"],
        "foo.dwapp.localhost",
        "/",
        headers={"Host": "foo.dwapp.localhost", "Accept": "text/html"},
    )

    assert response.status_code == 404
    assert "text/html" in response.headers.get("Content-Type", "")
    body = response.text
    assert "<!DOCTYPE html>" in body
    assert "foo.dys" in body
    assert "yourname" in body


def test_404_invalid_host_returns_html(dwapp_script_info):
    """Verify invalid host pattern returns HTML when requested."""
    response = _request(
        dwapp_script_info["base_url"],
        "localhost",
        "/",
        headers={"Host": "localhost", "Accept": "text/html"},
    )

    assert response.status_code == 404
    assert "text/html" in response.headers.get("Content-Type", "")
    body = response.text
    assert "<!DOCTYPE html>" in body
    assert "localhost" in body


def test_404_missing_script_plain_text_default(dwapp_script_info):
    """Verify 404 returns plain text when no Accept header."""
    unknown_host = "dys21zzzzzzzzzzzzzzzzzz.localhost"
    response = _request(
        dwapp_script_info["base_url"],
        unknown_host,
        "/",
        # No Accept header override
    )

    assert response.status_code == 404
    content_type = response.headers.get("Content-Type", "")
    assert "text/plain" in content_type, f"Expected plain text, got {content_type}"
    assert "Hello World example" in response.text
    assert "yourname" in response.text, f"Missing template URL: {response.text}"


def test_404_explicit_plain_text_accept(dwapp_script_info):
    """Verify 404 returns plain text when Accept: text/plain."""
    unknown_host = "dys21zzzzzzzzzzzzzzzzzz.localhost"
    response = _request(
        dwapp_script_info["base_url"],
        unknown_host,
        "/",
        headers={"Host": unknown_host, "Accept": "text/plain"},
    )

    assert response.status_code == 404
    content_type = response.headers.get("Content-Type", "")
    assert "text/plain" in content_type
    assert "Hello World example" in response.text
    assert "yourname" in response.text
