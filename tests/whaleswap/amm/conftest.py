import json
import random
import string
import pytest


def _rand_name():
    return "".join(random.choices(string.ascii_lowercase, k=6)) + ".dys"


@pytest.fixture(scope="function")
def ws_setup_env(chainnet, generate_account, faucet):
    """
    Single-tx dyslang setup for whaleswap tests:
    - register 1 name
    - mint 3 denoms name/coin/a, name/coin/b, name/coin/c with 1800 units each
    - distribute to three accounts: for each denom, send 300 base to each

    Returns dict with keys: owner_name, owner_addr, acc1, acc2, acc3, name, denoms
    """
    dysond = chainnet[0]

    # Create owner and recipients
    [owner_name, owner_addr] = generate_account("ws_owner", faucet_amount=2_000_000)
    [a1_name, a1_addr] = generate_account("ws_a1", faucet_amount=1)
    [a2_name, a2_addr] = generate_account("ws_a2", faucet_amount=1)
    [a3_name, a3_addr] = generate_account("ws_a3", faucet_amount=1)

    # Ensure owner has enough udys to pay mint fees and gas
    faucet(owner_addr, amount=5_000_000)

    name = _rand_name()
    salt = "s" + "".join(random.choices(string.ascii_lowercase + string.digits, k=7))

    # Dyslang script executed with --extra-code to avoid persistent script updates
    extra_code = """
import json
from dys import _msg, _query, get_executor_address

def setup(name, salt, acc1, acc2, acc3):
    owner = get_executor_address()

    # Compute commitment hash
    hexhash = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": owner,
    })["hex_hash"]

    # Commit then reveal
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

    # Set destination to owner so MintCoins authz passes (dest == signer)
    _msg({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": owner,
    })

    denoms = [f"{name}/coin/a", f"{name}/coin/b", f"{name}/coin/c"]

    # Compute mint fee = ceil(sum(units) * mint_fee_per_coin)
    params = _query({"@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"})["params"]
    fee_per = float(params["mint_fee_per_coin"]) if params.get("mint_fee_per_coin") else 0.0
    total_units = 1800 * 3
    fee = int(-(-total_units * fee_per // 1))

    # Mint 1800 units of each denom to owner
    _msg({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": owner,
        "amount": [
            {"denom": denoms[0], "amount": "1800"},
            {"denom": denoms[1], "amount": "1800"},
            {"denom": denoms[2], "amount": "1800"},
        ],
        "mint_fee": {"denom": "udys", "amount": str(fee)},
    })

    # Distribute 300 base for each denom to each of the 3 accounts
    for r in [acc1, acc2, acc3]:
        sends = []
        for d in denoms:
            sends.append({"denom": d, "amount": "300"})
        # Coins array must be sorted by denom for Cosmos SDK validation
        sends = sorted(sends, key=lambda x: x["denom"])
        _msg({
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": owner,
            "to_address": r,
            "amount": sends,
        })

    return {
        "name": name,
        "denoms": denoms,
        "owner": owner,
    }
"""

    args = json.dumps([name, salt, a1_addr, a2_addr, a3_addr])
    tx = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        owner_addr,
        "--function-name",
        "setup",
        "--args",
        args,
        "--from",
        owner_name,
        "--gas",
        "auto",
        "--extra-code",
        extra_code,
    )

    assert tx.get("code", 1) == 0, f"setup script failed: {json.dumps(tx, indent=2)}"

    denoms = [f"{name}/coin/a", f"{name}/coin/b", f"{name}/coin/c"]
    return {
        "owner_name": owner_name,
        "owner_addr": owner_addr,
        "acc1": {"name": a1_name, "addr": a1_addr},
        "acc2": {"name": a2_name, "addr": a2_addr},
        "acc3": {"name": a3_name, "addr": a3_addr},
        "name": name,
        "denoms": denoms,
    }


@pytest.fixture()
def ws_create_offer(chainnet):
    from tests.whaleswap.amm.normalize_events import normalize_events

    dysond = chainnet[0]

    def _create(maker_name: str, have: str, want: str) -> int:
        tx = dysond(
            "tx",
            "whaleswap",
            "make-offer",
            "--have",
            have,
            "--want",
            want,
            "--from",
            maker_name,
        )
        assert tx.get("code", 1) == 0, f"make-offer failed: {json.dumps(tx, indent=2)}"
        assert "events" in tx, f"no events in tx: {json.dumps(tx, indent=2)}"
        evdict = normalize_events(tx["events"])  # deep-parsed
        etype = "dysonprotocol.whaleswap.v1.EventOfferCreated"
        assert etype in evdict, f"missing {etype}: {json.dumps(evdict, indent=2)}"
        rows = evdict[etype]
        assert len(rows) == 1, f"expected one {etype}, got {len(rows)}: {rows}"
        attrs = rows[0]
        assert "offer_id" in attrs, f"missing offer_id: {attrs}"
        oid = int(attrs["offer_id"])  # supports int or numeric string
        assert oid > 0, f"invalid offer_id: {oid} attrs={attrs}"
        return oid

    return _create
