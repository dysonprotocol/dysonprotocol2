"""
Reproduce exact user scenario that triggers invariant bug.

User scenario (from logs):
- Mint 100000alice.dys
- Create pool: 10000alice.dys + 999998900udys
- Make offer 1: have 1000alice.dys, want 947udys
- Make offer 2: have 99999890udys, want 82174937alice.dys
- Open auction 1: sell 1000alice.dys, bid_denom=udys
- Open auction 2: sell 99999890udys, bid_denom=alice.dys
- Take offer 1 via MakeTrade: take 1 unit (want 947udys)

Result: invariant after MakeTrade: module balance mismatch for udys:
        have=1199997733 expected=1199998680
        Missing: 947 udys (exactly what offer 1 wants)
"""

import json
import random
import string
from tests.whaleswap.amm.normalize_events import normalize_events


def test_make_trade_take_offer_exact_amounts_from_user_logs(
    chainnet, generate_account, faucet
):
    """
    Reproduce user's exact scenario with same amounts and sequence.
    """
    dysond = chainnet[0]

    # Create alice with huge initial balance
    [alice_name, alice_addr] = generate_account(
        "alice_trader", faucet_amount=10_000_000_000
    )

    # Register name and mint coins using script (same as ws_setup_env)
    name = "test" + "".join(random.choices(string.ascii_lowercase, k=4)) + ".dys"
    salt = "s" + "".join(random.choices(string.ascii_lowercase + string.digits, k=7))

    setup_script = """
import json
from dys import _msg, _query, get_executor_address

def register_and_mint(name, salt, amount):
    owner = get_executor_address()
    hexhash = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": owner,
    })["hex_hash"]
    _msg({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "10"},
    })
    _msg({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    })
    _msg({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": owner,
    })
    _msg({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": owner,
        "amount": [{"denom": name, "amount": str(amount)}],
        "mint_fee": {"denom": "udys", "amount": "1000"},
    })
    return {"name": name, "owner": owner}
"""

    mint_tx = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_addr,
        "--function-name",
        "register_and_mint",
        "--args",
        json.dumps([name, salt, 100000]),
        "--from",
        alice_name,
        "--gas",
        "auto",
        "--extra-code",
        setup_script,
    )
    assert mint_tx.get("code", 1) == 0, f"mint failed: {json.dumps(mint_tx, indent=2)}"

    mint_denom = name

    # Create pool: 10000alice.dys + 999998900udys
    pool_tx = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"10000{mint_denom}",
        "--coins",
        "999998900udys",
        "--fee-pct",
        "0.041",
        "--from",
        alice_name,
    )
    assert (
        pool_tx.get("code", 1) == 0
    ), f"create-pool failed: {json.dumps(pool_tx, indent=2)}"

    # Make offer 1: have 1000alice.dys, want 947udys
    offer1_tx = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"1000{mint_denom}",
        "--want",
        "947udys",
        "--from",
        alice_name,
    )
    assert (
        offer1_tx.get("code", 1) == 0
    ), f"offer1 failed: {json.dumps(offer1_tx, indent=2)}"
    ev1 = normalize_events(offer1_tx["events"])
    offer1_id = str(
        int(ev1["dysonprotocol.whaleswap.v1.EventOfferCreated"][0]["offer_id"])
    )

    # Make offer 2: have 99999890udys, want 82174937alice.dys
    offer2_tx = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        "99999890udys",
        "--want",
        f"82174937{mint_denom}",
        "--from",
        alice_name,
    )
    assert (
        offer2_tx.get("code", 1) == 0
    ), f"offer2 failed: {json.dumps(offer2_tx, indent=2)}"

    # Open auction 1: sell 1000alice.dys, bid_denom=udys
    auc1_tx = dysond(
        "tx",
        "whaleswap",
        "open-auction",
        "--sell",
        f"1000{mint_denom}",
        "--bid-denom",
        "udys",
        "--from",
        alice_name,
    )
    assert (
        auc1_tx.get("code", 1) == 0
    ), f"auction1 failed: {json.dumps(auc1_tx, indent=2)}"

    # Open auction 2: sell 99999890udys, bid_denom=alice.dys
    auc2_tx = dysond(
        "tx",
        "whaleswap",
        "open-auction",
        "--sell",
        "99999890udys",
        "--bid-denom",
        mint_denom,
        "--from",
        alice_name,
    )
    assert (
        auc2_tx.get("code", 1) == 0
    ), f"auction2 failed: {json.dumps(auc2_tx, indent=2)}"

    # Alice takes her own offer 1 via MakeTrade
    trade_tx = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--from",
        alice_name,
        "--max-input",
        "10000udys",
        "--op",
        json.dumps({"take": {"offer_id": offer1_id, "take_units": "1"}}),
    )

    # This should fail with invariant error
    code = trade_tx.get("code", 0)
    raw_log = trade_tx.get("raw_log", "")

    assert (
        code != 0
    ), f"Expected invariant error but trade succeeded. Full tx: {json.dumps(trade_tx, indent=2)}"
    assert (
        "invariant after MakeTrade" in raw_log
    ), f"Expected 'invariant after MakeTrade' in error, got: {raw_log}"
    assert (
        "module balance mismatch" in raw_log
    ), f"Expected 'module balance mismatch' in error, got: {raw_log}"
    assert (
        "have=1199997733 expected=1199998680" in raw_log
    ), f"Expected exact balance mismatch values in error, got: {raw_log}"
