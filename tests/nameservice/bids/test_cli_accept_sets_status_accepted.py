import json


def _setup_class_and_nft(dysond_bin, generate_account, faucet, register_name):
    owner_name, owner_addr = generate_account("owner_bids2")
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

    nft_id = "nft-bids-2"
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


def _latest_bid_status_for_nft(dysond_bin, class_id, nft_id):
    view = dysond_bin(
        "query",
        "nameservice",
        "bids-for-nft",
        "--class-id",
        class_id,
        "--nft-id",
        nft_id,
    )
    bids = view.get("bids", [])
    assert len(bids) >= 1, f"Expected at least one bid: {json.dumps(view, indent=2)}"
    return bids[-1].get("status"), view


def test_cli_accept_sets_status_accepted(
    chainnet, generate_account, faucet, register_name
):
    dysond_bin = chainnet[0]
    owner_name, owner_addr, class_id, nft_id = _setup_class_and_nft(
        dysond_bin, generate_account, faucet, register_name
    )
    bidder_name, bidder_addr = generate_account("accept_bidder")
    faucet(bidder_addr, denom="udys", amount="50000")

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
            "2000udys",
            "--from",
            bidder_name,
        )["code"]
        == 0
    )

    # owner accepts
    acc = dysond_bin(
        "tx",
        "nameservice",
        "accept-bid",
        "--nft-class-id",
        class_id,
        "--nft-id",
        nft_id,
        "--from",
        owner_name,
    )
    assert acc.get("code", 1) == 0, acc

    # status should be ACCEPTED (3)
    st, full = _latest_bid_status_for_nft(dysond_bin, class_id, nft_id)
    assert st in (
        3,
        "BID_ACCEPTED",
    ), f"Expected ACCEPTED, got {st}. Full: {json.dumps(full, indent=2)}"
