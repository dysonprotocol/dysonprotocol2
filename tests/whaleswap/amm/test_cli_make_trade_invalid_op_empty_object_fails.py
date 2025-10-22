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
        "auto",
        raw=True,
    )
    err = (out or "").lower()
    assert (
        "operation must be swap, take, or auction" in err
    ), f"Expected keeper validation error for empty op. Full: {out}"
