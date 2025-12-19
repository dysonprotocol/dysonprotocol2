"""
Mock dys module for testing pow_coin.py locally.
All state kept in memory.
"""

import json
from datetime import datetime, timezone

# In-memory state
_storage = {}
_balances = {}  # {address: {denom: amount}}
_block_time = datetime.now(timezone.utc)
_script_address = "dys1script"
_executor_address = "dys1miner"


def set_executor(addr):
    """Set who is calling."""
    global _executor_address
    _executor_address = addr


def set_block_time(dt):
    """Set current block time."""
    global _block_time
    _block_time = dt


def advance_time(seconds):
    """Advance block time."""
    global _block_time
    from datetime import timedelta

    _block_time = _block_time + timedelta(seconds=seconds)


def get_balance(addr, denom):
    """Get balance for testing."""
    return _balances.get(addr, {}).get(denom, 0)


def get_storage():
    """Get raw storage for testing."""
    return _storage.copy()


def reset():
    """Reset all state."""
    global _storage, _balances, _block_time
    _storage = {}
    _balances = {}
    _block_time = datetime.now(timezone.utc)


# --- dys module interface ---


def get_script_address():
    return _script_address


def get_executor_address():
    return _executor_address


def get_block_info():
    return {
        "height": "12345",
        "time": _block_time.isoformat().replace("+00:00", "Z"),
        "chain_id": "test-chain",
    }


def _query(req):
    """Handle query requests."""
    t = req.get("@type", "")

    if "QueryStorageGetRequest" in t:
        owner = req["owner"]
        index = req["index"]
        key = f"{owner}:{index}"
        if key not in _storage:
            raise Exception(f"key {key} doesn't exist")
        return {"entry": {"data": _storage[key]}}

    if "QueryBalanceRequest" in t:
        addr = req["address"]
        denom = req["denom"]
        amt = _balances.get(addr, {}).get(denom, 0)
        return {"balance": {"denom": denom, "amount": str(amt)}}

    raise Exception(f"Unknown query: {t}")


def _msg(req):
    """Handle message requests."""
    t = req.get("@type", "")

    if "MsgStorageSet" in t:
        owner = req["owner"]
        index = req["index"]
        data = req["data"]
        _storage[f"{owner}:{index}"] = data
        return {}

    if "MsgMintCoins" in t:
        dest = req.get("name_destination") or req.get("minter")  # support both
        amounts = req["amount"] if isinstance(req["amount"], list) else [req["amount"]]
        for coin in amounts:
            denom = coin["denom"]
            amount = int(coin["amount"])
            if dest not in _balances:
                _balances[dest] = {}
            _balances[dest][denom] = _balances[dest].get(denom, 0) + amount
        return {}

    if "MsgSend" in t:
        from_addr = req["from_address"]
        to_addr = req["to_address"]
        for coin in req["amount"]:
            denom = coin["denom"]
            amount = int(coin["amount"])
            # Deduct from sender
            if (
                from_addr not in _balances
                or _balances[from_addr].get(denom, 0) < amount
            ):
                raise Exception(f"insufficient funds")
            _balances[from_addr][denom] -= amount
            # Add to receiver
            if to_addr not in _balances:
                _balances[to_addr] = {}
            _balances[to_addr][denom] = _balances[to_addr].get(denom, 0) + amount
        return {}

    raise Exception(f"Unknown msg: {t}")
