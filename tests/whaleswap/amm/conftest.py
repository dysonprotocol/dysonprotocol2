import json
import random
import string
import pytest


def _rand_name():
    return "".join(random.choices(string.ascii_lowercase, k=6)) + ".dys"


@pytest.fixture(scope="session")
def ws_setup_env(chainnet, generate_account, faucet):
    """
    Single-tx dyslang setup for whaleswap tests:
    - register 1 name
    - mint 3 denoms name/coin/a, name/coin/b, name/coin/c with 1800 units each
    - convert 900 units of each to liquid (keep 900 solid, 900 liquid)
    - distribute to three accounts: for each denom, send 300 solid and 300 liquid to each

    Returns dict with keys: owner_name, owner_addr, acc1, acc2, acc3, name, denoms, liquid_denoms
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

    # Convert 900 units of each denom to liquid (wrap)
    for d in denoms:
        _msg({
            "@type": "/dysonprotocol.whaleswap.v1.MsgConvertToLiquid",
            "caller": owner,
            "denom": d,
            "amount": "900",
        })

    # Helper to build liquid denom
    def L(solid):
        return "whaleswap.dys/coins/" + solid

    # Distribute 300 solid + 300 liquid for each denom to each of the 3 accounts
    for r in [acc1, acc2, acc3]:
        sends = []
        for d in denoms:
            sends.append({"denom": d, "amount": "300"})
            sends.append({"denom": L(d), "amount": "300"})
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
        "liquid_denoms": [L(x) for x in denoms],
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
    lprefix = "whaleswap.dys/coins/"

    return {
        "owner_name": owner_name,
        "owner_addr": owner_addr,
        "acc1": {"name": a1_name, "addr": a1_addr},
        "acc2": {"name": a2_name, "addr": a2_addr},
        "acc3": {"name": a3_name, "addr": a3_addr},
        "name": name,
        "denoms": denoms,
        "liquid_denoms": [lprefix + d for d in denoms],
    }
