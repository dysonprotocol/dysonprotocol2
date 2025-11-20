import json


def _extract_exec_result(tx):
    events_by_type = {e.get("type"): e for e in tx.get("events", [])}
    ev = events_by_type["dysonprotocol.script.v1.EventExecScript"]
    attrs = {a.get("key"): a.get("value") for a in ev.get("attributes", [])}
    resp = json.loads(attrs.get("response", "{}"))
    return json.loads(resp.get("result", "{}")).get("result")


def _script_update(dysond, owner_name: str, code: str):
    res = dysond(
        "tx",
        "script",
        "update",
        "--code",
        code,
        "--from",
        owner_name,
    )
    assert res.get("code", 1) == 0, f"script update failed: {json.dumps(res, indent=2)}"


def test_ob_script_take_ring_solid(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]
    [ma_name, ma_addr] = generate_account("ob_scr_mA")
    [mb_name, mb_addr] = generate_account("ob_scr_mB")
    [mc_name, mc_addr] = generate_account("ob_scr_mC")
    [taker_name, taker_addr] = generate_account("ob_scr_taker")
    faucet(ma_addr, amount=2_000_000)
    faucet(mb_addr, amount=2_000_000)
    faucet(mc_addr, amount=2_000_000)
    faucet(taker_addr, amount=1_000_000)

    coin_a = register_name(dysond, ma_name, ma_addr, "1000udys")
    coin_b = register_name(dysond, mb_name, mb_addr, "1000udys")
    coin_c = register_name(dysond, mc_name, mc_addr, "1000udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])  # e.g. 0.01
    units = 200
    required_fee = int(units * fee_per_unit)
    assert (
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{units}{coin_a}",
            "--mint-fee",
            f"{required_fee}udys",
            "--from",
            ma_name,
        ).get("code", 1)
        == 0
    )
    assert (
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{units}{coin_b}",
            "--mint-fee",
            f"{required_fee}udys",
            "--from",
            mb_name,
        ).get("code", 1)
        == 0
    )
    assert (
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{units}{coin_c}",
            "--mint-fee",
            f"{required_fee}udys",
            "--from",
            mc_name,
        ).get("code", 1)
        == 0
    )

    tx_a = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"2{coin_a}",
        "--want",
        f"1{coin_b}",
        "--from",
        ma_name,
    )
    tx_b = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"2{coin_b}",
        "--want",
        f"1{coin_c}",
        "--from",
        mb_name,
    )
    tx_c = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"2{coin_c}",
        "--want",
        f"1{coin_a}",
        "--from",
        mc_name,
    )
    assert (
        tx_a.get("code", 1) == 0
        and tx_b.get("code", 1) == 0
        and tx_c.get("code", 1) == 0
    )

    def _oid(tx):
        evs = [
            e
            for e in tx.get("events", [])
            if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
        ]
        attrs = evs[0].get("attributes", [])
        val = [a for a in attrs if a.get("key") == "offer_id"][0].get("value")
        return int(val)

    offer_a = _oid(tx_a)
    offer_b = _oid(tx_b)
    offer_c = _oid(tx_c)

    script_code = """
from dys import _msg, _query, get_script_address

def ob_take(trades):
    # Convert old MsgTakeOffer format to new MsgMakeTrade format
    operations = []
    for trade in trades:
        operations.append({
            "take": {
                "offer_id": trade["offer_id"]
            }
        })
    
    msg = {
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": get_script_address(),
        "max_input": [],  # Take operations handle funds automatically
        "operations": operations,
        "min_output": []
    }
    _msg(msg)
    return {"ok": True, "taker": get_script_address(), "n": len(trades)}

def ob_query_offer(offer_id):
    return _query({"@type": "/dysonprotocol.whaleswap.v1.QueryOfferRequest", "offer_id": int(offer_id)})
"""
    _script_update(dysond, taker_name, script_code)

    args = json.dumps(
        [[{"offer_id": offer_a}, {"offer_id": offer_b}, {"offer_id": offer_c}]]
    )
    take = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        taker_addr,
        "--function-name",
        "ob_take",
        "--args",
        args,
        "--from",
        taker_name,
        "--gas",
        "auto",
    )
    assert take.get("code", 1) == 0, f"script take failed: {json.dumps(take, indent=2)}"

    qa = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_a))
    qb = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_b))
    qc = dysond("query", "whaleswap", "offer", "--offer-id", str(offer_c))
    assert qa.get("offer", {}).get("status") == "closed"
    assert qb.get("offer", {}).get("status") == "closed"
    assert qc.get("offer", {}).get("status") == "closed"


def test_ob_script_partial_take_and_query(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [maker_name, maker_addr] = generate_account("ob_scr_pf_m")
    [taker_name, taker_addr] = generate_account("ob_scr_pf_t")
    faucet(maker_addr, amount=2_000_000)
    faucet(taker_addr, amount=1_000_000)

    coin_x = register_name(dysond, maker_name, maker_addr, "1000udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])  # e.g. 0.01
    units = 200
    required_fee = int(units * fee_per_unit)
    assert (
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{units}{coin_x}",
            "--mint-fee",
            f"{required_fee}udys",
            "--from",
            maker_name,
        ).get("code", 1)
        == 0
    )
    tx = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"8{coin_x}",
        "--want",
        "4udys",
        "--from",
        maker_name,
    )
    assert tx.get("code", 1) == 0
    evs = [
        e
        for e in tx.get("events", [])
        if e.get("type") == "dysonprotocol.whaleswap.v1.EventOfferCreated"
    ]
    oid = int(
        [a for a in evs[0].get("attributes", []) if a.get("key") == "offer_id"][0][
            "value"
        ]
    )

    script_code = """
from dys import _msg, _query, get_script_address

def ob_take_partial_and_query(offer_id, take_units, have_denom):
    _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": get_script_address(),
        "max_input": [{"denom": "udys", "amount": "1000"}],
        "operations": [{
            "take": {
                "offer_id": int(offer_id),
                "take_units": str(int(take_units))
            }
        }],
        "min_output": []
    })
    bal = _query({
        "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
        "address": get_script_address(),
        "denom": str(have_denom),
    })
    return bal
"""
    _script_update(dysond, taker_name, script_code)

    args = json.dumps([oid, 2, coin_x])
    take = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        taker_addr,
        "--function-name",
        "ob_take_partial_and_query",
        "--args",
        args,
        "--from",
        taker_name,
        "--gas",
        "auto",
    )
    assert take.get("code", 1) == 0, (
        f"script partial take failed: {json.dumps(take, indent=2)}"
    )
    result = _extract_exec_result(take)
    assert (
        isinstance(result, dict)
        and result.get("@type") == "/cosmos.bank.v1beta1.QueryBalanceResponse"
    )
    amount = int(result.get("balance", {}).get("amount", "0"))
    assert amount >= 4
