import json
from tests.whaleswap.amm.normalize_events import normalize_events


def parse_amounts_multi(s):
    try:
        parts = str(s).split(",")
    except Exception:
        return []
    out = []
    for p in parts:
        t = p.strip()
        j = 0
        m = len(t)
        while j < m and t[j].isdigit():
            j += 1
        if j > 0 and j < m:
            try:
                out.append((int(t[:j]), t[j:]))
            except Exception:
                continue
    return out


# first_event_attrs removed; use normalize_events in tests instead.


def sum_transfers_for_addr(tx, addr):
    debits = []
    credits = []
    evdict = normalize_events(tx.get("events", []) or [])
    rows = evdict.get("transfer", [])
    for attrs in rows:
        coins = parse_amounts_multi(attrs.get("amount", "0"))
        if attrs.get("sender") == addr:
            debits.extend(coins)
        if attrs.get("recipient") == addr:
            credits.extend(coins)
    return debits, credits
