import json


def test_make_trade_v3_boundary_fail(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env

    a = env["denoms"][0]
    b = env["denoms"][1]
    taker_name = env["acc3"]["name"]

    # Initial price is 1.0 (100b/100a). Set band edges equal to 1.0 to enforce boundary fail.
    out = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"100{a}",
        "--coins",
        f"100{b}",
        "--min-price",
        f"1{a}",
        "--min-price",
        f"1{b}",
        "--max-price",
        f"1{a}",
        "--max-price",
        f"1{b}",
        "--from",
        taker_name,
        raw=True,
    )
    # raw=True with --gas returns dict for failed transactions
    assert isinstance(out, dict), f"expected dict response, got: {type(out)}"
    assert out.get("code", 0) != 0, f"expected transaction to fail, got success: {out}"
    raw_log = out.get("raw_log", "").lower()
    assert (
        "max_price must be greater than min_price" in raw_log
    ), f"unexpected error: {out}"
