import json
from tests import utils


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


def test_cli_claim_sets_status_claimed(
    chainnet, generate_account, faucet, register_name
):
    dysond_bin = chainnet[0]
    owner_name, owner_addr, class_id, nft_id = _setup_class_and_nft(
        dysond_bin, generate_account, faucet, register_name
    )
    # set short bid timeout for the class
    assert (
        dysond_bin(
            "tx",
            "nameservice",
            "set-nft-class-bid-timeout",
            "--class-id",
            class_id,
            "--bid-timeout",
            "100ms",
            "--from",
            owner_name,
        )["code"]
        == 0
    )

    bidder_name, bidder_addr = generate_account("claim_bidder")
    faucet(bidder_addr, denom="udys", amount="50000")

    res = dysond_bin(
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
    )
    assert res.get("code", 1) == 0, res

    # wait at least one block for timeout to elapse
    def _after_one_block():
        st = dysond_bin("status")
        return int(st["sync_info"]["latest_block_height"]) > int(res["height"])

    utils.poll_until_condition(
        _after_one_block, timeout=10, error_message="timeout not elapsed"
    )

    cl = dysond_bin(
        "tx",
        "nameservice",
        "claim-bid",
        "--nft-class-id",
        class_id,
        "--nft-id",
        nft_id,
        "--from",
        bidder_name,
    )
    assert cl.get("code", 1) == 0, cl

    st, full = _latest_bid_status_for_nft(dysond_bin, class_id, nft_id)
    assert st in (
        5,
        "BID_CLAIMED",
    ), f"Expected CLAIMED, got {st}. Full: {json.dumps(full, indent=2)}"
