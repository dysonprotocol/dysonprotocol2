"""
POW COIN - Work-Based Emission

Goal: Emit 1 POW per hour (24 POW/day)

Formula:
    reward = EMISSION × work / expected_work

    where:
        work           = 2²⁵⁶ / hash_value  (expected hashes to find this proof)
        expected_work  = difficulty × PERIOD
        difficulty     = current target hashrate (H/s), adjusted via EMA
        PERIOD         = 3600s (1 hour)

Expanded:
    reward = EMISSION × work / (difficulty × PERIOD)
           = 1,000,000 × work / (difficulty × 3600)

Examples (at difficulty = 100 H/s, so expected_work = 360,000):
    100 H/s × 0.5hr = 180,000 work → 0.5 POW
    100 H/s × 1.0hr = 360,000 work → 1.0 POW
    200 H/s × 1.0hr = 720,000 work → 2.0 POW
    200 H/s × 2.0hr = 1,440,000 work → 4.0 POW

Difficulty adjusts via weighted EMA to maintain ~1 POW/hour emission.
"""

import hashlib
import json
from datetime import datetime
from string import Template
from dys import _msg, _query, get_script_address, get_executor_address


class SafeTemplate(Template):
    delimiter = "{{"
    pattern = r"\{\{\s*(?P<named>[a-zA-Z_][a-zA-Z_0-9-_]*)\s*\}\}"  # type: ignore


# Config
DENOM = "pow.dys"
EMISSION = 1000000  # 1 POW emitted per TARGET period
TARGET = 3600  # target period (1 hour in seconds)
BASE_TARGET = 278  # starting target: ~278 H/s (≈1M H/hr)
MIN_TARGET = 1  # minimum: 1 H/s (very easy)
WINDOW = 3600  # EMA time constant (1 hour)

MAX_HASH = 2**256


def _get():
    """Get state: [prev_hash, last_time, target_hashrate] or defaults."""
    try:
        r = _query(
            {
                "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
                "owner": get_script_address(),
                "index": "s",
            }
        )
        data = json.loads(r["entry"]["data"])
        prev = data[0]
        last_time = data[1]
        target = data[2] if len(data) > 2 else BASE_TARGET
        return [prev, last_time, target]
    except Exception:
        return ["0" * 64, 0, BASE_TARGET]


def _set(state):
    _msg(
        {
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": get_script_address(),
            "index": "s",
            "data": json.dumps(state),
        }
    )


def _work(hash_hex):
    """Expected hashes to find a hash this small: 2²⁵⁶ / hash."""
    h = int(hash_hex, 16)
    if h == 0:
        return MAX_HASH
    return MAX_HASH // h


def _reward_mult(work, difficulty):
    """
    Reward multiplier: work relative to expected work per period.

    mult = work / expected_work
         = work / (difficulty × PERIOD)

    At target difficulty for one full period: mult = 1.0
    """
    expected_work = difficulty * TARGET  # TARGET is the period (3600s)
    return work / expected_work


def _adjust(work, target, elapsed):
    """
    Adjust target_hashrate based on observed hashrate.

    observed_hashrate = work / elapsed (H/s)
    new_target = EMA(observed, old)
    """
    observed = work / elapsed  # hashes per second
    observed = min(observed, target * 4)
    # EMA weight: more time = more weight, capped at 0.5
    alpha = min(0.5, elapsed / WINDOW)

    new_target = alpha * observed + (1 - alpha) * target
    return max(MIN_TARGET, new_target)


def mine(nonce: str):
    """
    Claim reward based on work done.

    reward = EMISSION × work / (difficulty × PERIOD)
           = EMISSION × work / expected_work
    """
    if len(nonce) > 64:
        raise ValueError("nonce too long")

    miner = get_executor_address()
    prev, last_time, target = _get()
    now = int(datetime.now().timestamp())
    elapsed = max(1, now - last_time) if last_time else TARGET

    # Compute hash and work
    hash_hex = hashlib.sha256(f"{prev}:{nonce}:{miner}".encode()).hexdigest()
    work = _work(hash_hex)

    # Reward: work relative to expected work per period, capped at 4× EMISSION
    mult = _reward_mult(work, target)
    reward = min(4 * EMISSION, int(EMISSION * mult))

    if reward < 1:
        raise ValueError(
            f"reward=0: work={work:,}, target={target:,}, expected={target * TARGET:,}. "
            f"Need more work (find smaller hash)."
        )

    # Mint (fee from chain params)
    s = get_script_address()
    params = _query({"@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"})
    fee_per_coin = float(params["params"]["mint_fee_per_coin"])
    fee = max(1, int(reward * fee_per_coin + 0.99999))  # ceiling
    _msg(
        {
            "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
            "name_destination": s,
            "amount": [{"denom": DENOM, "amount": str(reward)}],
            "mint_fee": {"denom": "udys", "amount": str(fee)},
        }
    )
    _msg(
        {
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": s,
            "to_address": miner,
            "amount": [{"denom": DENOM, "amount": str(reward)}],
        }
    )

    # Adjust target hashrate
    new_target = _adjust(work, target, elapsed)
    _set([hash_hex, now, new_target])

    return {
        "hash": hash_hex,
        "work": work,
        "target_hashrate": target,
        "new_target_hashrate": new_target,
        "reward": reward,
        "reward_mult": round(mult, 4),
        "elapsed": elapsed,
    }



def info():
    """Return config constants only. State is read from storage."""
    return {
        "denom": DENOM,
        "emission": EMISSION,
        "target_period": TARGET,
        "base_target": BASE_TARGET,
        "min_target": MIN_TARGET,
    }


def _fetch_template(name):
    """Fetch template from storage."""
    try:
        r = _query(
            {
                "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
                "owner": get_script_address(),
                "index": f"templates/{name}",
            }
        )
        return r["entry"]["data"]
    except Exception:
        return None


def wsgi(environ, start_response):
    """WSGI application."""
    path = environ.get("PATH_INFO", "/")

    if path == "/info":
        body = json.dumps(info()).encode()
        start_response("200 OK", [("Content-Type", "application/json")])
        return [body]

    if path == "/":
        html = _fetch_template("index.html")
        if html:
            html = SafeTemplate(html).substitute(
                {"SCRIPT_ADDRESS": get_script_address()}
            )
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [html.encode()]
        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [b"Template not found: templates/index.html"]

    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"Not found"]
