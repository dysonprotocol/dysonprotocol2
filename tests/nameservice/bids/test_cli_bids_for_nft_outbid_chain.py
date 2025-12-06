import json


def _setup_class_and_nft(dysond_bin, generate_account, faucet, register_name):
    owner_name, owner_addr = generate_account("owner_bids")
    faucet(owner_addr, denom="udys", amount="50000")

    class_root = register_name(dysond_bin, owner_name, owner_addr)
    class_id = f"{class_root}/col"
    assert (
        dysond_bin(
            "tx",
            "nameservice",
            "save-class",
            "--class-id",
            class_id,
            "--from",
            owner_name,
        )["code"]
        == 0
    )

    nft_id = "nft-bids-1"
    assert (
        dysond_bin(
            "tx",
            "nameservice",
            "mint-nft",
            "--class-id",
            class_id,
            "--nft-id",
            nft_id,
            "--from",
            owner_name,
        )["code"]
        == 0
    )
    assert (
        dysond_bin(
            "tx",
            "nameservice",
            "set-listed",
            "--nft-class-id",
            class_id,
            "--nft-id",
            nft_id,
            "--listed",
            "--from",
            owner_name,
        )["code"]
        == 0
    )

    return owner_name, owner_addr, class_id, nft_id


def test_cli_bids_for_nft_outbid_chain(
    chainnet, generate_account, faucet, register_name
):
    dysond_bin = chainnet[0]

    owner_name, owner_addr, class_id, nft_id = _setup_class_and_nft(
        dysond_bin, generate_account, faucet, register_name
    )

    bob_name, bob_addr = generate_account("bob")
    carol_name, carol_addr = generate_account("carol")
    faucet(bob_addr, denom="udys", amount="50000")
    faucet(carol_addr, denom="udys", amount="50000")

    assert (
        dysond_bin(
            "tx",
            "nameservice",
            "place-bid",
            "--nft-class-id",
            class_id,
            "--nft-id",
            nft_id,
            "--bid-amount",
            "1000udys",
            "--from",
            bob_name,
        )["code"]
        == 0
    )
    assert (
        dysond_bin(
            "tx",
            "nameservice",
            "place-bid",
            "--nft-class-id",
            class_id,
            "--nft-id",
            nft_id,
            "--bid-amount",
            "1200udys",
            "--from",
            carol_name,
        )["code"]
        == 0
    )

    resp = dysond_bin(
        "query",
        "nameservice",
        "bids-for-nft",
        "--class-id",
        class_id,
        "--nft-id",
        nft_id,
    )
    bids = resp.get("bids", [])
    assert (
        len(bids) >= 2
    ), f"Expected >=2 bids, got {len(bids)}. Full: {json.dumps(resp, indent=2)}"

    b0, b1 = bids[0], bids[1]
    assert (
        b0.get("bidder") == bob_addr
    ), f"First bid should be Bob. Full: {json.dumps(resp, indent=2)}"
    assert (
        b1.get("bidder") == carol_addr
    ), f"Second bid should be Carol. Full: {json.dumps(resp, indent=2)}"

    # Status check: OUTBID then ACTIVE (accept numeric or string enum)
    assert b0.get("status") in (
        2,
        "BID_OUTBID",
    ), f"b0.status not OUTBID. Full: {json.dumps(resp, indent=2)}"
    assert b1.get("status") in (
        1,
        "BID_ACTIVE",
    ), f"b1.status not ACTIVE. Full: {json.dumps(resp, indent=2)}"

    # Linkage check
    assert b0.get("replaced_by_bid_id") == b1.get(
        "bid_id"
    ), f"b0->replaced_by must link to b1. Full: {json.dumps(resp, indent=2)}"
    assert b1.get("replaces_bid_id") == b0.get(
        "bid_id"
    ), f"b1->replaces must link to b0. Full: {json.dumps(resp, indent=2)}"
