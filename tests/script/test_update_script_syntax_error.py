import json


def test_update_script_rejects_syntax_error(chainnet, generate_account):
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1)

    # Intentionally invalid Python code (missing closing parenthesis)
    bad_code = """
def add(a, b:
    return a + b
"""

    # Broadcast tx raw to get txhash reliably
    tx_broadcast = dysond_bin(
        "tx",
        "script",
        "update",
        "--code",
        bad_code,
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--gas",
        "2000000",  # script update needs significant gas for validation/formatting
        "--yes",
        raw=True,
    )
    assert (
        "txhash" in tx_broadcast
    ), f"Expected txhash in broadcast response. Full: {json.dumps(tx_broadcast, indent=2)}"

    # Wait for inclusion - script update should fail with syntax error
    wait = dysond_bin("query", "wait-tx", tx_broadcast["txhash"])
    assert (
        wait.get("code", 0) != 0
    ), f"Expected failure for invalid code. Full: {json.dumps(wait, indent=2)}"
    assert "failed to format code" in wait.get(
        "raw_log", ""
    ), f"Missing formatting error. Full: {json.dumps(wait, indent=2)}"
