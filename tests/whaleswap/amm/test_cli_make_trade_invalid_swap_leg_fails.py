import json
import pytest


def test_make_trade_invalid_swap_leg_pool_id_zero_fails(chainnet, ws_setup_env):
    """Verify that MakeTrade rejects swap operations with pool_id == 0."""
    dysond = chainnet[0]
    env = ws_setup_env
    a, b = env["denoms"][0], env["denoms"][1]
    taker_name = env["acc1"]["name"]

    # Create a valid pool first to establish the test environment
    txp = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"100{a}",
        "--coins",
        f"100{b}",
        "--from",
        taker_name,
    )
    assert txp["code"] == 0, f"create-pool failed: {json.dumps(txp, indent=2)}"

    # Attempt swap with pool_id = 0 - should fail
    invalid_swap = {"swap": {"pool_id": 0, "swap_in": {"denom": a, "amount": "5"}}}

    out = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--op",
        json.dumps(invalid_swap),
        "--from",
        taker_name,
        "--gas",
        "100000000",  # raw=True requires gas flag
        raw=True,
    )

    # Expect failure with a helpful error mentioning swap leg invalid
    # raw=True with --gas returns dict for failed transactions
    assert isinstance(out, dict), f"expected dict response, got: {type(out)}"
    assert out.get("code", 0) != 0, f"expected transaction to fail, got success: {out}"
    raw_log = out.get("raw_log", "").lower()
    assert "swap leg invalid" in raw_log, f"unexpected error message: {out}"


def test_make_trade_invalid_swap_leg_empty_object_fails(chainnet, ws_setup_env):
    """Verify that MakeTrade rejects swap operations with empty swap objects."""
    dysond = chainnet[0]
    env = ws_setup_env
    a, b = env["denoms"][0], env["denoms"][1]
    taker_name = env["acc1"]["name"]

    # Create a valid pool first to establish the test environment
    txp = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"100{a}",
        "--coins",
        f"100{b}",
        "--from",
        taker_name,
    )
    assert txp["code"] == 0, f"create-pool failed: {json.dumps(txp, indent=2)}"

    # Attempt swap with empty swap object - should fail (pool_id defaults to 0)
    invalid_swap = {"swap": {}}

    out = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--op",
        json.dumps(invalid_swap),
        "--from",
        taker_name,
        "--gas",
        "100000000",  # raw=True requires gas flag
        raw=True,
    )

    # Expect failure with a helpful error mentioning swap leg invalid
    # raw=True with --gas returns dict for failed transactions
    assert isinstance(out, dict), f"expected dict response, got: {type(out)}"
    assert out.get("code", 0) != 0, f"expected transaction to fail, got success: {out}"
    raw_log = out.get("raw_log", "").lower()
    assert "swap leg invalid" in raw_log, f"unexpected error message: {out}"
