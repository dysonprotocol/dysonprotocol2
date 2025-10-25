import json
import random
import string
import pytest


def _rand_name():
    return "".join(random.choices(string.ascii_lowercase, k=6)) + ".dys"


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
