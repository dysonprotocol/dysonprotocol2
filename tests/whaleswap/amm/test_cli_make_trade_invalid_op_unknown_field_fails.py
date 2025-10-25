def test_make_trade_invalid_op_unknown_field_fails(chainnet, ws_setup_env):
    dysond = chainnet[0]
    env = ws_setup_env
    taker_name = env["acc1"]["name"]

    out = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--op",
        '{"foo": {"bar": 1}}',
        "--from",
        taker_name,
        raw=True,
    )
    low = (out or "").lower()
    assert (
        'unknown field "foo"' in low
    ), f"Expected proto parse error for unknown field. Full: {out}"
