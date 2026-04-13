import pytest
import json
from tests import utils
import tempfile

# Helper: Poll until a governance proposal reaches a final state
# Uses dysond_bin for queries


def poll_until_proposal_passes(dysond_bin, proposal_id: str, timeout: int = 60):
    def has_proposal_reached_final_state():
        proposal_result = dysond_bin("query", "gov", "proposal", proposal_id)
        status = proposal_result["proposal"]["status"]
        print(f"Current proposal status: {status}")
        return status in [
            "PROPOSAL_STATUS_PASSED",
            "PROPOSAL_STATUS_REJECTED",
            "PROPOSAL_STATUS_FAILED",
        ]

    utils.poll_until_condition(
        has_proposal_reached_final_state,
        timeout=timeout,
        error_message="Timeout waiting for proposal to reach final state",
    )
    proposal_result = dysond_bin("query", "gov", "proposal", proposal_id)
    final_status = proposal_result["proposal"][
        "status"
    ]  # Fixed: get status from proposal object
    return final_status


# Use the global register_name fixture from tests/conftest.py


def set_class_bid_timeout(
    dysond_bin, signer_name: str, class_id: str, bid_timeout_value: str
):
    """Set per-class bid timeout using the new class-level setter."""
    res = dysond_bin(
        "tx",
        "nameservice",
        "set-nft-class-bid-timeout",
        "--class-id",
        class_id,
        "--bid-timeout",
        bid_timeout_value,
        "--from",
        signer_name,
        "--yes",
    )
    assert res["code"] == 0, res.get("raw_log", "")


def test_update_class_bid_timeout(chainnet, generate_account, faucet, register_name):
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="25000")
    # Create a class Alice controls under her root name
    root_name = register_name(dysond_bin, alice_name, alice_address, "100udys")
    class_id = f"{root_name}/col"
    # Create class
    res = dysond_bin(
        "tx", "nameservice", "save-class", "--class-id", class_id, "--from", alice_name
    )  # signer must be root name owner/destination
    assert res["code"] == 0, res["raw_log"]
    # Set bid timeout to 1s using class-level setter, must be signed by root owner
    set_class_bid_timeout(dysond_bin, alice_name, class_id, "1s")


def test_claim_before_timeout_fails(chainnet, generate_account, faucet, register_name):
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="25000")

    # Create a test class under Alice and set per-class bid timeout to 10s
    root_name = register_name(dysond_bin, alice_name, alice_address, "100udys")
    test_class = f"{root_name}/col"
    res = dysond_bin(
        "tx",
        "nameservice",
        "save-class",
        "--class-id",
        test_class,
        "--from",
        alice_name,
    )  # signer must control root
    assert res["code"] == 0, res["raw_log"]
    set_class_bid_timeout(dysond_bin, alice_name, test_class, "10s")

    [bob_name, bob_address] = generate_account("bob")
    faucet(bob_address, denom="udys", amount="1000")
    registered_name = {"name": f"nft-{bob_address[:8]}", "alice_address": alice_address}
    # Mint an NFT in the test class and list it
    nft_id = registered_name["name"]
    mint_res = dysond_bin(
        "tx",
        "nameservice",
        "mint-nft",
        "--class-id",
        test_class,
        "--nft-id",
        nft_id,
        "--from",
        alice_name,
    )  # use root owner
    assert mint_res["code"] == 0, mint_res["raw_log"]
    list_res = dysond_bin(
        "tx",
        "nameservice",
        "set-listed",
        "--nft-class-id",
        test_class,
        "--nft-id",
        nft_id,
        "--listed",
        "--from",
        alice_name,
    )  # use root owner
    assert list_res["code"] == 0, list_res["raw_log"]

    # Place a bid from Bob
    bid_amount = "500udys"
    print(f"Placing bid of {bid_amount} from Bob")
    tx_result = dysond_bin(
        "tx",
        "nameservice",
        "place-bid",
        "--nft-class-id",
        test_class,
        "--nft-id",
        nft_id,
        "--bid-amount",
        bid_amount,
        "--from",
        bob_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert tx_result["code"] == 0, tx_result["raw_log"]

    print(f"Attempting to claim immediately (should fail)")
    # Attempt to claim immediately (should fail)
    claim_result = dysond_bin(
        "tx",
        "nameservice",
        "claim-bid",
        "--nft-class-id",
        test_class,
        "--nft-id",
        nft_id,
        "--from",
        bob_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    print(f"Claim result: {claim_result}")

    # Check that the transaction failed with the expected error
    assert (
        claim_result["code"] != 0
    ), "Expected claim transaction to fail, but it succeeded"
    assert (
        "bid timeout has not elapsed" in claim_result["raw_log"]
    ), f"Expected 'bid timeout has not elapsed' error, but got: {claim_result['raw_log']}"

    # Verify ownership was not transferred
    nft_info = dysond_bin(
        "query", "nft", "owner", test_class, nft_id, "--output", "json"
    )
    # Owner should still be the class root owner who minted/listed the NFT
    assert nft_info["owner"] == alice_address


def test_claim_after_timeout_community_pool_fee(
    chainnet, generate_account, faucet, register_name
):
    """Test ClaimBid fee routing for governance-owned class (nameservice.dys).

    When claiming a bid on a .dys name (nameservice.dys class), the fee goes to
    the community pool since governance owns that class. We verify this by checking
    that Alice receives (bid - fee), not the full bid amount.
    """
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="25000")

    [bob_name, bob_address] = generate_account("bob")
    faucet(bob_address, denom="udys", amount="1000")

    # Register a .dys name (this creates NFT in governance-owned nameservice.dys class)
    # Using low valuation so we can bid higher and trigger surplus fee
    dys_name = register_name(dysond_bin, alice_name, alice_address, "100udys")
    class_id = "nameservice.dys"
    nft_id = dys_name  # The NFT ID is the name itself

    # Record Alice's initial balance (she's the name owner/seller)
    alice_bal_before = dysond_bin("query", "bank", "balances", alice_address)
    alice_coins_before = {
        b["denom"]: int(b["amount"]) for b in alice_bal_before.get("balances", [])
    }
    alice_udys_before = alice_coins_before.get("udys", 0)

    # Place a bid from Bob (higher than valuation to trigger surplus fee)
    # Bid 500 vs valuation 100, so surplus = 400
    bid_amount = "500udys"
    print(f"Placing bid of {bid_amount} from Bob on {dys_name}")
    bid_result = dysond_bin(
        "tx",
        "nameservice",
        "place-bid",
        "--nft-class-id",
        class_id,
        "--nft-id",
        nft_id,
        "--bid-amount",
        bid_amount,
        "--from",
        bob_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert bid_result["code"] == 0, bid_result["raw_log"]

    # Wait for bid timeout to elapse
    # Default nameservice.dys timeout is ~2s. With ~250ms block time, wait for >= 10 blocks.
    bid_block_height = int(bid_result["height"])

    def timeout_elapsed():
        out = dysond_bin("query", "block")
        current_block = int(out["header"]["height"])
        return (current_block - bid_block_height) >= 10

    utils.poll_until_condition(
        timeout_elapsed, timeout=15, error_message="Bid timeout did not elapse"
    )

    print(f"Attempting to claim after timeout (should succeed)")
    claim_result = dysond_bin(
        "tx",
        "nameservice",
        "claim-bid",
        "--nft-class-id",
        class_id,
        "--nft-id",
        nft_id,
        "--from",
        bob_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    print(f"Claim result: {claim_result}")

    assert (
        claim_result["code"] == 0
    ), f"Expected claim transaction to succeed, but got error: {claim_result.get('raw_log', 'Unknown error')}"

    # Alice should receive (bid - fee), not the full 500
    # Fee = surplus_fee + renewal_fee
    # surplus_fee = (500 - 100) * 0.01 * remaining/period ≈ 4
    # renewal_fee = 500 * 0.01 = 5
    # So Alice should receive ~491 (500 - 9)
    alice_bal_after = dysond_bin("query", "bank", "balances", alice_address)
    alice_coins_after = {
        b["denom"]: int(b["amount"]) for b in alice_bal_after.get("balances", [])
    }
    alice_udys_after = alice_coins_after.get("udys", 0)
    alice_received = alice_udys_after - alice_udys_before
    print(
        f"Alice: before={alice_udys_before}, after={alice_udys_after}, received={alice_received}"
    )

    # Alice should receive between 450 and 500 (bid minus fee)
    # Not exactly 500 proves fee was deducted
    assert (
        alice_received > 450
    ), f"Alice should have received ~491, but received {alice_received}"
    assert (
        alice_received < 500
    ), f"Alice should have received less than 500 (fee deducted), but received {alice_received}"

    fee_amount = 500 - alice_received
    print(
        f"Fee deducted: {fee_amount}udys (routed to community pool for gov-owned class)"
    )

    # Verify that Bob now owns the name
    owner_result = dysond_bin(
        "query", "nft", "owner", class_id, nft_id, "--output", "json"
    )
    assert (
        owner_result["owner"] == bob_address
    ), f"Expected Bob to own the NFT, but owner is {owner_result['owner']}"


def test_claim_after_timeout_succeeds(
    chainnet, generate_account, faucet, register_name
):
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="25000")

    # Create a test class and set bid timeout to 100ms for fast test
    root_name = register_name(dysond_bin, alice_name, alice_address, "100udys")
    test_class = f"{root_name}/col"
    res = dysond_bin(
        "tx",
        "nameservice",
        "save-class",
        "--class-id",
        test_class,
        "--from",
        alice_name,
    )  # signer must control root
    assert res["code"] == 0, res["raw_log"]
    set_class_bid_timeout(dysond_bin, alice_name, test_class, "100ms")

    [bob_name, bob_address] = generate_account("bob")
    faucet(bob_address, denom="udys", amount="1000")
    # Mint and list an NFT in the test class
    nft_id = f"nft-{bob_address[:8]}"
    mint_res = dysond_bin(
        "tx",
        "nameservice",
        "mint-nft",
        "--class-id",
        test_class,
        "--nft-id",
        nft_id,
        "--from",
        alice_name,
    )  # use root owner
    assert mint_res["code"] == 0, mint_res["raw_log"]
    list_res = dysond_bin(
        "tx",
        "nameservice",
        "set-listed",
        "--nft-class-id",
        test_class,
        "--nft-id",
        nft_id,
        "--listed",
        "--from",
        alice_name,
    )  # use root owner
    assert list_res["code"] == 0, list_res["raw_log"]

    # Record Alice's initial udys balance (owner who minted/listed via reg)
    alice_bal_before = dysond_bin("query", "bank", "balances", alice_address)
    alice_udys_before = next(
        (
            int(b.get("amount"))
            for b in alice_bal_before.get("balances", [])
            if b.get("denom") == "udys"
        ),
        0,
    )

    # Place a bid from Bob
    bid_amount = "500udys"
    print(f"Placing bid of {bid_amount} from Bob")
    bid_result = dysond_bin(
        "tx",
        "nameservice",
        "place-bid",
        "--nft-class-id",
        test_class,
        "--nft-id",
        nft_id,
        "--bid-amount",
        bid_amount,
        "--from",
        bob_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert bid_result["code"] == 0, bid_result["raw_log"]

    # Wait for bid timeout to elapse by waiting for blocks to pass
    # With 100ms timeout and ~500ms block time, should pass after 1 block
    def timeout_elapsed():
        status_result = dysond_bin("status")
        current_block = int(status_result["sync_info"]["latest_block_height"])
        bid_block = int(bid_result["height"])
        # Wait for at least 1 block to pass to ensure timeout has elapsed
        return (current_block - bid_block) >= 1

    utils.poll_until_condition(
        timeout_elapsed, timeout=10, error_message="Bid timeout did not elapse"
    )

    print(f"Attempting to claim after timeout (should succeed)")
    # Attempt to claim after timeout (should succeed)
    claim_result = dysond_bin(
        "tx",
        "nameservice",
        "claim-bid",
        "--nft-class-id",
        test_class,
        "--nft-id",
        nft_id,
        "--from",
        bob_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    print(f"Claim result: {claim_result}")

    # Check that the transaction succeeded
    assert (
        claim_result["code"] == 0
    ), f"Expected claim transaction to succeed, but got error: {claim_result.get('raw_log', 'Unknown error')}"

    # Verify Alice received the escrowed bid amount (check reg's alice)
    alice_bal_after = dysond_bin("query", "bank", "balances", alice_address)
    alice_udys_after = next(
        (
            int(b.get("amount"))
            for b in alice_bal_after.get("balances", [])
            if b.get("denom") == "udys"
        ),
        0,
    )
    assert (
        alice_udys_after - alice_udys_before >= 500
    ), f"Alice did not receive bid funds: before={alice_udys_before}, after={alice_udys_after}"

    # Verify that Bob now owns the NFT
    owner_result = dysond_bin(
        "query", "nft", "owner", test_class, nft_id, "--output", "json"
    )
    assert (
        owner_result["owner"] == bob_address
    ), f"Expected Bob to own the NFT, but owner is {owner_result['owner']}"
