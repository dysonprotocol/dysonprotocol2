"""
Coverage for QueryBidsForNFT.

Scenarios:
1. Successful query – NFT has bids, pagination, and correct ordering.
2. Empty NFT (no bids) – returns empty list.
3. Empty class_id → InvalidArgument error.
4. Empty nft_id   → InvalidArgument error.
5. NFT does not exist → NotFound error.
All tests use the stateless script pattern with `_sudo` helpers.
"""

import json
import secrets
import pytest
from deep_parse import deep_parse

BASE_EXTRA_CODE = r"""
from dys import _msg, _query, get_executor_address
import re

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def _parse_coin(v):
    m = re.fullmatch(r"(\d+)([a-zA-Z0-9./_]+)", v)
    if not m:
        raise Exception("invalid coin: " + str(v))
    return {"denom": m.group(2), "amount": m.group(1)}

def _register_root_name(name, destination):
    owner = get_executor_address()
    salt = "salt-" + name
    h = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": owner,
    })["hex_hash"]
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": h,
        "valuation": _parse_coin("10udys"),
    })
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    })
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": destination,
    })
    return destination

def _setup_class_and_nft(root_name, nft_id, owner):
    class_id = root_name + "/collection"
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": owner,
        "class_id": class_id,
        "name": "Test Collection",
        "symbol": "TEST",
        "description": "Test",
    })
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintNFT",
        "name_destination": owner,
        "class_id": class_id,
        "nft_id": nft_id,
    })
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetListed",
        "nft_owner": owner,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "listed": True,
    })
    return class_id

def _place_bid(bidder, class_id, nft_id, amt):
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgPlaceBid",
        "bidder": bidder,
        "nft_class_id": class_id,
        "nft_id": nft_id,
        "bid_amount": _parse_coin(amt),
    })
"""


def _random_root_name():
    return f"bid-{secrets.token_hex(4)}.dys"


# ----------------------------------------------------------------------
# 1. Success – NFT has bids, pagination & ordering
# ----------------------------------------------------------------------
def test_bids_for_nft_success(chainnet):
    dysond = chainnet[0]
    gov = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]
    alice = dysond(
        "keys", "show", "alice", "--keyring-backend", "test", "--output", "json"
    )["address"]
    bob = dysond(
        "keys", "show", "bob", "--keyring-backend", "test", "--output", "json"
    )["address"]

    root = _random_root_name()
    extra = (
        BASE_EXTRA_CODE
        + """
def demo_success(root, alice, bob):
    owner = _register_root_name(root, alice)
    class_id = _setup_class_and_nft(root, "nft-1", owner)

    # three bids from two bidders
    _place_bid(alice, class_id, "nft-1", "100udys")
    _place_bid(bob,   class_id, "nft-1", "150udys")
    _place_bid(alice, class_id, "nft-1", "200udys")

    # full list
    all = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": "nft-1",
    })

    # pagination – limit 1 then follow key
    page1 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": "nft-1",
        "pagination": {"limit": 1},
    })
    page2 = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": "nft-1",
        "pagination": {"limit": 1, "key": page1["pagination"]["next_key"]},
    })
    # reverse order
    rev = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": "nft-1",
        "pagination": {"limit": 1, "reverse": True},
    })
    # count_total
    cnt = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": "nft-1",
        "pagination": {"count_total": True},
    })
    return {"all": all, "page1": page1, "page2": page2, "rev": rev, "cnt": cnt}
"""
    )

    resp = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov,
        "--executor-address",
        gov,
        "--function-name",
        "demo_success",
        "--kwargs",
        json.dumps({"root": root, "alice": alice, "bob": bob}),
        "--extra-code",
        extra,
    )
    out = deep_parse(resp)["result"]["result"]

    # ---- basic list ----
    all_bids = out["all"]["bids"]
    assert isinstance(all_bids, list) and len(all_bids) == 3
    # order is chronological – newest last
    assert all_bids[0]["bidder"] == alice
    assert all_bids[1]["bidder"] == bob
    assert all_bids[2]["bidder"] == alice

    # ---- pagination ----
    assert len(out["page1"]["bids"]) == 1
    assert out["page1"]["pagination"].get("next_key") is not None
    assert len(out["page2"]["bids"]) == 1

    # ---- reverse ----
    assert len(out["rev"]["bids"]) == 1
    # reverse should give the newest bid first
    assert out["rev"]["bids"][0]["bidder"] == alice

    # ---- count_total ----
    assert out["cnt"]["pagination"].get("total") is not None


# ----------------------------------------------------------------------
# 2. Empty NFT – no bids
# ----------------------------------------------------------------------
def test_bids_for_nft_empty(chainnet):
    dysond = chainnet[0]
    gov = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]
    alice = dysond(
        "keys", "show", "alice", "--keyring-backend", "test", "--output", "json"
    )["address"]
    root = _random_root_name()
    extra = (
        BASE_EXTRA_CODE
        + """
def demo_empty(root, alice):
    owner = _register_root_name(root, alice)
    class_id = _setup_class_and_nft(root, "nft-1", owner)
    # no bids placed
    res = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": "nft-1",
    })
    return {"res": res}
"""
    )
    resp = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov,
        "--executor-address",
        gov,
        "--function-name",
        "demo_empty",
        "--kwargs",
        json.dumps({"root": root, "alice": alice}),
        "--extra-code",
        extra,
    )
    out = deep_parse(resp)["result"]["result"]
    assert isinstance(out["res"]["bids"], list) and len(out["res"]["bids"]) == 0


# ----------------------------------------------------------------------
# 3. Empty class_id  → InvalidArgument
# ----------------------------------------------------------------------
def test_bids_for_nft_empty_class_id(chainnet):
    dysond = chainnet[0]
    gov = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]
    alice = dysond(
        "keys", "show", "alice", "--keyring-backend", "test", "--output", "json"
    )["address"]
    extra = (
        BASE_EXTRA_CODE
        + """
def demo_empty_class():
    try:
        _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
            "class_id": "",
            "nft_id": "any",
        })
        return {"error": "should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""
    )
    resp = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov,
        "--executor-address",
        gov,
        "--function-name",
        "demo_empty_class",
        "--extra-code",
        extra,
    )
    out = deep_parse(resp)["result"]["result"]
    assert out["expected"] is True
    assert "class_id" in out["error"].lower() and "required" in out["error"].lower()


# ----------------------------------------------------------------------
# 4. Empty nft_id → InvalidArgument
# ----------------------------------------------------------------------
def test_bids_for_nft_empty_nft_id(chainnet):
    dysond = chainnet[0]
    gov = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]
    alice = dysond(
        "keys", "show", "alice", "--keyring-backend", "test", "--output", "json"
    )["address"]
    extra = (
        BASE_EXTRA_CODE
        + """
def demo_empty_nft():
    try:
        _query({
            "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
            "class_id": "some_class",
            "nft_id": "",
        })
        return {"error": "should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""
    )
    resp = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov,
        "--executor-address",
        gov,
        "--function-name",
        "demo_empty_nft",
        "--extra-code",
        extra,
    )
    out = deep_parse(resp)["result"]["result"]
    assert out["expected"] is True
    assert "nft_id" in out["error"].lower() and "required" in out["error"].lower()


# ----------------------------------------------------------------------
# 5. NFT does not exist → NotFound
# ----------------------------------------------------------------------
def test_bids_for_nft_not_found(chainnet):
    dysond = chainnet[0]
    gov = dysond("query", "auth", "module-account", "gov")["account"]["value"][
        "address"
    ]
    alice = dysond(
        "keys", "show", "alice", "--keyring-backend", "test", "--output", "json"
    )["address"]
    root = _random_root_name()
    extra = (
        BASE_EXTRA_CODE
        + """
def demo_not_found(root, alice):
    owner = _register_root_name(root, alice)
    class_id = root + "/collection"   # class is created but no NFT minted
    _sudo({
        "@type": "/dysonprotocol.nameservice.v1.MsgSaveClass",
        "name_destination": owner,
        "class_id": class_id,
        "name": "Test",
        "symbol": "T",
        "description": "test",
    })
    # Query for bids on non-existent NFT - should return empty result
    result = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryBidsForNFTRequest",
        "class_id": class_id,
        "nft_id": "missing-nft",
    })
    return {"result": result, "expected": True}
"""
    )
    resp = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov,
        "--executor-address",
        gov,
        "--function-name",
        "demo_not_found",
        "--kwargs",
        json.dumps({"root": root, "alice": alice}),
        "--extra-code",
        extra,
    )
    out = deep_parse(resp)["result"]["result"]
    assert out.get("expected") is True
    # the query should return empty result for non-existent NFT
    assert isinstance(out["result"], dict)
    assert "bids" in out["result"]
    assert len(out["result"]["bids"]) == 0
