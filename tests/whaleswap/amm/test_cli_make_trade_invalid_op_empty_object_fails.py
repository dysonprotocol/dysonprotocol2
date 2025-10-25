def test_make_trade_invalid_op_empty_object_fails(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env
    taker_name = env["acc1"]["name"]

    out = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--op",
        "{}",
        "--from",
        taker_name,
        "--gas",
        "100000000",  # raw=True requires gas flag
        raw=True,
    )
    # raw=True with --gas returns dict for failed transactions
    assert isinstance(out, dict), f"expected dict response, got: {type(out)}"
    assert out.get("code", 0) != 0, f"expected transaction to fail, got success: {out}"
    raw_log = out.get("raw_log", "").lower()
    assert (
        "operation must be swap, take, or auction" in raw_log
    ), f"unexpected error message: {out}"
