# New test covering allowed / disallowed denom behaviour, implementing backlog task 8-6
import json
import random
import string
import tempfile
from typing import List

import pytest

from tests import utils


# -----------------------------------------------------------------------------
# Helper: governance proposal to update allowed_denoms param
# -----------------------------------------------------------------------------


def _update_allowed_denoms_via_gov(
    dysond_bin, proposer_name: str, allowed_denoms: List[str]
):
    """Submit + pass a gov proposal setting the full AllowedDenoms list."""

    # Fetch current params so we can keep the other fields unchanged
    current = dysond_bin("query", "nameservice", "params")
    current_params = current["params"]
    bid_timeout = current_params["bid_timeout"]
    reject_fee = current_params["reject_bid_valuation_fee_percent"]
    min_bid_inc = current_params["minimum_bid_percent_increase"]

    # Look up gov module account address (required authority field)
    gov_addr = (
        dysond_bin("query", "auth", "module-account", "gov")
        .get("account", {})
        .get("value", {})
        .get("address", "")
    )
    assert gov_addr, "Gov module account address not found"

    # Get validator operator address
    validators = dysond_bin("query", "staking", "validators")
    val_op = validators["validators"][0]["operator_address"]

    # Delegate tokens from Alice to validator so Alice has voting power
    delegate_result = dysond_bin(
        "tx",
        "staking",
        "delegate",
        val_op,
        "50000000udys",
        "--from",
        "alice",
        "--yes",
    )
    assert (
        delegate_result["code"] == 0
    ), f"Failed to delegate: {delegate_result['raw_log']}"

    # Construct proposal JSON
    proposal = {
        "messages": [
            {
                "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
                "authority": gov_addr,
                "params": {
                    "bid_timeout": bid_timeout,
                    "allowed_denoms": allowed_denoms,
                    "reject_bid_valuation_fee_percent": reject_fee,
                    "minimum_bid_percent_increase": min_bid_inc,
                },
            }
        ],
        "metadata": "ipfs://CID",
        "deposit": "1udys",
        "title": "Update AllowedDenoms for tests",
        "summary": f"Set AllowedDenoms to {allowed_denoms}",
    }

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=True) as fp:
        json.dump(proposal, fp)
        fp.flush()
        # Submit proposal using Alice (who now has voting power)
        submit = dysond_bin(
            "tx",
            "gov",
            "submit-proposal",
            fp.name,
            "--from",
            "alice",
            "--keyring-backend",
            "test",
            "--yes",
        )

    # Wait for tx and extract proposal id
    tx_result = dysond_bin("query", "wait-tx", submit["txhash"])
    proposal_id = None
    for ev in tx_result.get("events", []):
        if ev.get("type") == "submit_proposal":
            for attr in ev.get("attributes", []):
                if attr.get("key") == "proposal_id":
                    proposal_id = attr.get("value")
                    break
    assert proposal_id, "proposal_id not found"

    # Vote with Alice (who has voting power through delegation)
    vote = dysond_bin(
        "tx",
        "gov",
        "vote",
        proposal_id,
        "yes",
        "--from",
        "alice",
        "--keyring-backend",
        "test",
        "--yes",
    )
    dysond_bin("query", "wait-tx", vote["txhash"])

    # Wait until proposal finalises
    def _passed():
        st = dysond_bin("query", "gov", "proposal", proposal_id)["proposal"]["status"]
        return st in (
            "PROPOSAL_STATUS_PASSED",
            "PROPOSAL_STATUS_REJECTED",
            "PROPOSAL_STATUS_FAILED",
        )

    utils.poll_until_condition(
        _passed, timeout=60, error_message="gov proposal timeout"
    )

    final = dysond_bin("query", "gov", "proposal", proposal_id)["proposal"]["status"]
    assert final == "PROPOSAL_STATUS_PASSED", f"Gov proposal failed with status {final}"

    # Sanity-check params updated
    updated = dysond_bin("query", "nameservice", "params")["params"]["allowed_denoms"]
    assert set(updated) == set(allowed_denoms), f"AllowedDenoms not updated: {updated}"


def _random_suffix(n: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=n))


def test_nft_allowed_denoms_param(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]

    # ------------------------------------------------------------------
    # Scenario 1 – Happy paths with default denom (dys)
    # ------------------------------------------------------------------
    owner_name, owner_addr = generate_account("owner")
    faucet(owner_addr, denom="udys", amount=5000)

    # Register a root name so owner can create NFT classes under it
    root_name = register_name(dysond, owner_name, owner_addr)

    nft_class_id = f"{root_name}/col-{_random_suffix()}"
    nft_id = f"nft-{_random_suffix()}"

    # Create class (always_listed defaults to false)
    res = dysond(
        "tx",
        "nameservice",
        "save-class",
        "--class-id",
        nft_class_id,
        "--name",
        "Test Col",
        "--symbol",
        "TCOL",
        "--description",
        "Test Collection",
        "--uri",
        "https://example.com",
        "--from",
        owner_name,
    )
    assert res["code"] == 0

    # Mint NFT
    res = dysond(
        "tx",
        "nameservice",
        "mint-nft",
        "--class-id",
        nft_class_id,
        "--nft-id",
        nft_id,
        "--uri",
        "https://example.com/nft",
        "--from",
        owner_name,
    )
    assert res["code"] == 0, res["raw_log"]

    # Valuation 1000udys
    res = dysond(
        "tx",
        "nameservice",
        "set-valuation",
        "--class-id",
        nft_class_id,
        "--nft-id",
        nft_id,
        "--valuation",
        "1000udys",
        "--from",
        owner_name,
    )
    assert res["code"] == 0, res["raw_log"]

    # List the NFT
    res = dysond(
        "tx",
        "nameservice",
        "set-listed",
        "--nft-class-id",
        nft_class_id,
        "--nft-id",
        nft_id,
        "--listed",
        "--from",
        owner_name,
    )
    assert res["code"] == 0, res["raw_log"]

    # Bid with dys should succeed
    bidder_name, bidder_addr = generate_account("bidder")
    faucet(bidder_addr, denom="udys", amount=2000)
    res = dysond(
        "tx",
        "nameservice",
        "place-bid",
        "--nft-class-id",
        nft_class_id,
        "--nft-id",
        nft_id,
        "--bid-amount",
        "1000udys",
        "--from",
        bidder_name,
    )
    assert res["code"] == 0, res["raw_log"]

    # Toggle listing off (omit --listed flag) – should succeed
    res = dysond(
        "tx",
        "nameservice",
        "set-listed",
        "--nft-class-id",
        nft_class_id,
        "--nft-id",
        nft_id,
        "--from",
        owner_name,
    )
    assert res["code"] == 0, res["raw_log"]

    # ------------------------------------------------------------------
    # Scenario 2 – Disallowed denom 'nope'
    # ------------------------------------------------------------------
    # Attempt to set valuation with disallowed denom – expect failure
    res = dysond(
        "tx",
        "nameservice",
        "set-valuation",
        "--class-id",
        nft_class_id,
        "--nft-id",
        nft_id,
        "--valuation",
        "1000nope",
        "--from",
        owner_name,
    )
    assert res["code"] != 0, f"Expected set-valuation with disallowed denom to fail"
    assert "allowed denoms" in res["raw_log"].lower()

    # Attempt to bid with disallowed denom – expect failure
    res = dysond(
        "tx",
        "nameservice",
        "place-bid",
        "--nft-class-id",
        nft_class_id,
        "--nft-id",
        nft_id,
        "--bid-amount",
        "100nope",
        "--from",
        bidder_name,
    )
    assert res["code"] != 0, f"Expected place-bid with disallowed denom to fail"
    raw = res.get("raw_log", "").lower()
    assert "allowed denoms" in raw, f"Expected allowed denoms error, got: {raw}"

    # ------------------------------------------------------------------
    # Scenario 3 – Update Params to add a custom denom and verify behaviour
    # ------------------------------------------------------------------
    custom_name = register_name(dysond, owner_name, owner_addr)  # e.g. fooabcd.dys
    custom_denom = custom_name  # denom is same as root name

    # Update params via governance to include new denom
    _update_allowed_denoms_via_gov(dysond, owner_name, ["udys", custom_denom])

    # Mint some custom denom coins for owner and bidder
    dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"10000{custom_denom}",
        "--from",
        owner_name,
    )

    dysond(
        "tx",
        "bank",
        "send",
        owner_addr,
        bidder_addr,
        f"2000{custom_denom}",
        "--yes",
    )

    # Create new NFT in a new class and set valuation in custom denom
    nft_class2 = f"{custom_name}/col-{_random_suffix()}"
    nft2_id = f"nft-{_random_suffix()}"

    dysond(
        "tx",
        "nameservice",
        "save-class",
        "--class-id",
        nft_class2,
        "--name",
        "CD",
        "--symbol",
        "CD",
        "--description",
        "Custom denom col",
        "--uri",
        "https://example.com",
        "--from",
        owner_name,
    )

    dysond(
        "tx",
        "nameservice",
        "mint-nft",
        "--class-id",
        nft_class2,
        "--nft-id",
        nft2_id,
        "--uri",
        "https://example.com/nft",
        "--from",
        owner_name,
    )

    dysond(
        "tx",
        "nameservice",
        "set-valuation",
        "--class-id",
        nft_class2,
        "--nft-id",
        nft2_id,
        "--valuation",
        f"100{custom_denom}",
        "--from",
        owner_name,
    )

    # List the NFT before trying to bid on it
    dysond(
        "tx",
        "nameservice",
        "set-listed",
        "--nft-class-id",
        nft_class2,
        "--nft-id",
        nft2_id,
        "--listed",
        "--from",
        owner_name,
    )

    # Bid with dys (wrong denom) should fail
    res = dysond(
        "tx",
        "nameservice",
        "place-bid",
        "--nft-class-id",
        nft_class2,
        "--nft-id",
        nft2_id,
        "--bid-amount",
        "100udys",
        "--from",
        bidder_name,
    )
    assert res["code"] != 0, f"Expected place-bid with wrong denom to fail"
    raw = res.get("raw_log", "").lower()
    assert "denom" in raw, f"Expected denom mismatch error, got: {raw}"

    # Bid with custom denom should succeed
    dysond(
        "tx",
        "nameservice",
        "place-bid",
        "--nft-class-id",
        nft_class2,
        "--nft-id",
        nft2_id,
        "--bid-amount",
        f"100{custom_denom}",
        "--from",
        bidder_name,
    )

    # Owner updates valuation in custom denom – should succeed
    dysond(
        "tx",
        "nameservice",
        "set-valuation",
        "--class-id",
        nft_class2,
        "--nft-id",
        nft2_id,
        "--valuation",
        f"200{custom_denom}",
        "--from",
        owner_name,
    )

    # Final sanity check: params still include the custom denom
    final_denoms = dysond("query", "nameservice", "params")["params"]["allowed_denoms"]
    assert custom_denom in final_denoms
