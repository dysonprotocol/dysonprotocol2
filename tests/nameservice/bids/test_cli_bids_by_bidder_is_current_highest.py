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


def test_cli_bids_by_bidder_is_current_highest(
    chainnet, generate_account, faucet, register_name
):
    dysond_bin = chainnet[0]

    owner_name, owner_addr, class_id, nft_id = _setup_class_and_nft(
        dysond_bin, generate_account, faucet, register_name
    )
    bob_name, bob_addr = generate_account("bob2")
    carol_name, carol_addr = generate_account("carol2")
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
            "700udys",
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
            "900udys",
            "--from",
            carol_name,
        )["code"]
        == 0
    )

    bob_view = dysond_bin(
        "query",
        "nameservice",
        "bids-by-bidder",
        "--bidder",
        bob_addr,
    )
    carol_view = dysond_bin(
        "query",
        "nameservice",
        "bids-by-bidder",
        "--bidder",
        carol_addr,
    )

    bob_bids = [
        b
        for b in bob_view.get("bids", [])
        if b.get("bid", {}).get("class_id") == class_id
        and b.get("bid", {}).get("nft_id") == nft_id
    ]
    carol_bids = [
        b
        for b in carol_view.get("bids", [])
        if b.get("bid", {}).get("class_id") == class_id
        and b.get("bid", {}).get("nft_id") == nft_id
    ]

    assert (
        len(bob_bids) >= 1
    ), f"Bob should see at least one bid. Full: {json.dumps(bob_view, indent=2)}"
    assert (
        len(carol_bids) >= 1
    ), f"Carol should see at least one bid. Full: {json.dumps(carol_view, indent=2)}"

    # Compute highest from returned NFTData to avoid relying on omitted boolean fields
    assert (
        bob_bids[-1]["bid"]["bidder"] != bob_bids[-1]["nft"]["current_bidder"]
    ), f"Bob should not be current highest. Full: {json.dumps(bob_view, indent=2)}"
    assert (
        carol_bids[-1]["bid"]["bidder"] == carol_bids[-1]["nft"]["current_bidder"]
    ), f"Carol should be current highest. Full: {json.dumps(carol_view, indent=2)}"
