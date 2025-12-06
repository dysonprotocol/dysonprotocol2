"""
End-to-end test for the Nameservice module based on the README.

This test demonstrates a complete workflow of the Nameservice module:
1. Name Registration (commit-reveal)
2. Destination Setting
3. Name Valuation Update
4. Creating NFT Classes
5. Minting NFTs
6. NFT Metadata Management
7. Custom Coin Operations
8. Bidding System (place-bid, accept-bid, reject-bid, claim-bid)
"""

import math
import pytest
from decimal import Decimal, ROUND_CEILING
import json
import os
import random
import string
import secrets
import time
import tempfile
from tests.utils import poll_until_condition


def test_nameservice_e2e(chainnet, generate_account, faucet):
    """
    Complete end-to-end test of the Nameservice module.
    Tests all main functionalities described in the Nameservice README.
    """
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1000)
    [bob_name, bob_address] = generate_account("bob", faucet_amount=1000)
    [charlie_name, charlie_address] = generate_account("charlie", faucet_amount=1000)
    faucet(alice_address, denom="udys", amount="25000000")
    faucet(bob_address, denom="udys", amount="1000000")
    faucet(charlie_address, denom="udys", amount="1000000")
    print(f"Alice address: {alice_address}")
    print(f"Bob address: {bob_address}")
    print(f"Charlie address: {charlie_address}")

    # Generate random test values
    timestamp = int(time.time())
    random_suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    test_id = f"{random_suffix}-{timestamp}"

    # Get initial balances to track changes
    initial_alice_balances = dysond_bin("query", "bank", "balances", alice_address)
    initial_bob_balances = dysond_bin("query", "bank", "balances", bob_address)

    # Convert balances to dict for easier access
    alice_balances_dict = {
        b["denom"]: int(b["amount"]) for b in initial_alice_balances.get("balances", [])
    }
    alice_dys_balance = alice_balances_dict.get("udys", 0)
    print(f"Initial Alice DYS balance: {alice_dys_balance}")

    # Step 1: Check module parameters
    params = dysond_bin("query", "nameservice", "params")
    assert "params" in params, "Parameters missing from query result"
    # After refactor, global params expose bounds and mint fee only
    assert (
        "mint_fee_per_coin" in params["params"]
    ), "Parameters missing mint_fee_per_coin"
    print(f"Module parameters: {json.dumps(params, indent=2)}")
    # Per-class timeouts are verified in dedicated tests

    # Step 2: Name Registration
    # Generate a random name and salt
    name = f"test-{test_id}.dys"
    salt = secrets.token_hex(8)
    print(f"Generated salt: {salt} for name: {name}")

    # Compute the hash for commitment
    hash_result = dysond_bin(
        "query",
        "nameservice",
        "compute-hash",
        "--name",
        name,
        "--salt",
        salt,
        "--committer",
        alice_address,
    )
    commitment_hash = hash_result.get("hex_hash")
    assert commitment_hash, "Could not compute commitment hash"
    print(f"Commitment hash: {commitment_hash}")

    # Use random valuation between 10 and 100 DYS
    initial_valuation = random.randint(1000, 2000)

    # Commit to registering the name
    commit_result = dysond_bin(
        "tx",
        "nameservice",
        "commit",
        "--commitment",
        commitment_hash,
        "--valuation",
        f"{initial_valuation}udys",
        "--from",
        alice_name,
    )
    assert commit_result["code"] == 0, "Commit transaction failed"
    print(f"Name commitment successful with valuation {initial_valuation}udys")

    # Reveal the name to complete registration
    reveal_result = dysond_bin(
        "tx",
        "nameservice",
        "reveal",
        "--name",
        name,
        "--salt",
        salt,
        "--from",
        alice_name,
    )
    assert reveal_result["code"] == 0, "Reveal transaction failed"
    print("Name registration successful")

    # Verify the registration
    nft_info = dysond_bin("query", "nft", "nft", "nameservice.dys", name)
    assert "nft" in nft_info, "NFT not found after registration"
    assert nft_info["nft"]["id"] == name, "NFT ID doesn't match registered name"
    assert nft_info["nft"]["class_id"] == "nameservice.dys", "NFT class ID incorrect"

    # Extract NFT data to verify valuation
    nft_data = nft_info["nft"].get("data", {}).get("value", {})
    assert nft_data.get("valuation", {}).get("amount") == str(
        initial_valuation
    ), "Incorrect initial valuation"
    print(f"Initial NFT valuation: {nft_data.get('valuation', {}).get('amount')} udys")

    # Step 3: Destination Setting
    destination_result = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name,
        "--destination",
        alice_address,
        "--from",
        alice_name,
    )
    assert destination_result["code"] == 0, "Set destination transaction failed"
    print("Destination set successfully")

    # Verify the destination was set
    updated_nft_info = dysond_bin("query", "nft", "nft", "nameservice.dys", name)
    assert (
        updated_nft_info["nft"]["uri"] == alice_address
    ), "Destination not set correctly"
    print(f"Verified destination is set to: {updated_nft_info['nft']['uri']}")

    # Step 4: Name Valuation Update
    # Set new valuation higher than the current one
    new_valuation = initial_valuation + random.randint(50, 150)
    valuation_result = dysond_bin(
        "tx",
        "nameservice",
        "set-valuation",
        "--class-id",
        "nameservice.dys",
        "--nft-id",
        name,
        "--valuation",
        f"{new_valuation}udys",
        "--from",
        alice_name,
    )
    assert valuation_result["code"] == 0, (
        "Set valuation transaction failed" + valuation_result["raw_log"]
    )
    print(f"Valuation updated successfully from {initial_valuation} to {new_valuation}")

    # Verify the updated valuation
    revalued_nft_info = dysond_bin("query", "nft", "nft", "nameservice.dys", name)
    updated_valuation = (
        revalued_nft_info["nft"]
        .get("data", {})
        .get("value", {})
        .get("valuation", {})
        .get("amount")
    )
    assert updated_valuation == str(new_valuation), (
        "Valuation not updated correctly" + revalued_nft_info["raw_log"]
    )
    print(f"Updated NFT valuation verified: {updated_valuation} udys")

    # Step 5: Creating NFT Classes
    # Create a main NFT class with randomized names
    collection_name = f"Collection-{test_id}"
    collection_symbol = f"COL{random.randint(100, 999)}"

    main_class_result = dysond_bin(
        "tx",
        "nameservice",
        "save-class",
        "--class-id",
        name,
        "--name",
        collection_name,
        "--symbol",
        collection_symbol,
        "--description",
        f"Test Collection {test_id}",
        "--uri",
        "https://example.com",
        "--from",
        alice_name,
    )
    assert main_class_result["code"] == 0, (
        "Create main NFT class transaction failed" + main_class_result["raw_log"]
    )
    print(f"Main NFT class {name} created successfully")

    # Create a sub-collection with randomized names
    sub_class_id = f"{name}/sub{random.randint(100, 999)}"
    sub_collection_name = f"SubCollection-{test_id}"
    sub_collection_symbol = f"SUB{random.randint(100, 999)}"

    sub_class_result = dysond_bin(
        "tx",
        "nameservice",
        "save-class",
        "--class-id",
        sub_class_id,
        "--name",
        sub_collection_name,
        "--symbol",
        sub_collection_symbol,
        "--description",
        f"Test Sub-Collection {test_id}",
        "--uri",
        "https://example.com/sub",
        "--from",
        alice_name,
    )
    assert sub_class_result["code"] == 0, "Create sub NFT class transaction failed"
    print(f"Sub NFT class {sub_class_id} created successfully")

    # View all NFT classes
    classes = dysond_bin("query", "nft", "classes")
    assert "classes" in classes, "No NFT classes found"

    # Verify our classes were created
    class_ids = [c["id"] for c in classes["classes"]]
    assert name in class_ids, f"Main class {name} not found in class list"
    assert (
        sub_class_id in class_ids
    ), f"Sub class {sub_class_id} not found in class list"
    print(
        f"Verified {len(classes['classes'])} NFT classes exist, including our new ones"
    )

    # Step 6: Minting NFTs
    # Generate random NFT IDs
    nft_id = f"nft-{random.randint(1000, 9999)}"
    mint_result = dysond_bin(
        "tx",
        "nameservice",
        "mint-nft",
        "--class-id",
        name,
        "--nft-id",
        nft_id,
        "--uri",
        f"https://example.com/{nft_id}",
        "--from",
        alice_name,
    )
    assert mint_result["code"] == 0, (
        "Mint NFT transaction failed" + mint_result["raw_log"]
    )
    print(f"NFT {nft_id} minted successfully in class {name}")

    # Mint an NFT in the sub-collection
    sub_nft_id = f"subnft-{random.randint(1000, 9999)}"
    sub_mint_result = dysond_bin(
        "tx",
        "nameservice",
        "mint-nft",
        "--class-id",
        sub_class_id,
        "--nft-id",
        sub_nft_id,
        "--uri",
        f"https://example.com/{sub_nft_id}",
        "--from",
        alice_name,
    )
    assert sub_mint_result["code"] == 0, (
        "Mint sub-NFT transaction failed" + sub_mint_result["raw_log"]
    )
    print(f"NFT {sub_nft_id} minted successfully in class {sub_class_id}")

    # View NFTs in the main collection
    nfts = dysond_bin("query", "nft", "nfts", name)
    assert "nfts" in nfts, "No NFTs found in the main collection"
    assert len(nfts["nfts"]) > 0, "Main collection is empty"
    assert isinstance(
        nfts["nfts"], list
    ), f"Expected list for nfts['nfts'], got {type(nfts.get('nfts'))}"
    nft_ids = [n.get("id") for n in nfts["nfts"]]
    assert (
        nft_id in nft_ids
    ), f"NFT {nft_id} not found in main collection. IDs: {nft_ids}"
    print(f"Verified {len(nfts['nfts'])} NFTs exist in main collection")

    # Step 7: NFT Metadata Management
    # Generate random metadata
    colors = ["Red", "Blue", "Green", "Yellow", "Purple", "Orange"]
    random_color = random.choice(colors)
    random_rarity = random.randint(1, 100)

    metadata = json.dumps(
        {
            "attributes": [
                {"trait_type": "Color", "value": random_color},
                {"trait_type": "Rarity", "value": random_rarity},
            ]
        }
    )

    metadata_result = dysond_bin(
        "tx",
        "nameservice",
        "set-nft-metadata",
        "--class-id",
        name,
        "--nft-id",
        nft_id,
        "--metadata",
        f"'{metadata}'",
        "--from",
        alice_name,
    )
    assert metadata_result["code"] == 0, "Set NFT metadata transaction failed"
    print(f"Metadata set successfully for NFT {nft_id}")

    # Set random extra data for the NFT class
    random_website = f"https://example.com/{test_id}"
    extra_data = json.dumps(
        {"website": random_website, "created_at": timestamp, "creator": "Test Suite"}
    )

    extra_data_result = dysond_bin(
        "tx",
        "nameservice",
        "set-nft-class-extra-data",
        "--class-id",
        name,
        "--extra-data",
        f"'{extra_data}'",
        "--from",
        alice_name,
    )
    assert extra_data_result["code"] == 0, (
        "Set NFT class extra data transaction failed" + extra_data_result["raw_log"]
    )
    print(f"Extra data set successfully for class {name}")

    # View the updated NFT with metadata
    updated_nft = dysond_bin("query", "nft", "nft", name, nft_id)
    assert "nft" in updated_nft, f"NFT {nft_id} not found after metadata update"

    # Check if metadata was added correctly
    nft_metadata = (
        updated_nft["nft"].get("data", {}).get("value", {}).get("metadata", "")
    )
    assert random_color in nft_metadata, "Color metadata not set correctly"
    assert str(random_rarity) in nft_metadata, "Rarity metadata not set correctly"
    print(
        f"Verified metadata was updated with color {random_color} and rarity {random_rarity}"
    )

    # Step 7.1: Test NFT Class Always Listed Setting
    # Test setting always_listed to true
    always_listed_true_result = dysond_bin(
        "tx",
        "nameservice",
        "set-nft-class-always-listed",
        "--class-id",
        name,
        "--always-listed",
        "--from",
        alice_name,
    )
    assert (
        always_listed_true_result["code"] == 0
    ), "Set NFT class always listed (true) transaction failed"
    print(f"Successfully set always_listed=true for class {name}")

    # Query the NFT class to verify always_listed was set
    class_info_after_always_listed = dysond_bin("query", "nft", "class", name)
    assert (
        "class" in class_info_after_always_listed
    ), f"NFT class {name} not found after setting always_listed"
    print(f"Verified always_listed flag was updated for class {name}")

    # Test setting always_listed to false (by omitting the flag)
    always_listed_false_result = dysond_bin(
        "tx",
        "nameservice",
        "set-nft-class-always-listed",
        "--class-id",
        name,
        "--from",
        alice_name,
    )
    assert (
        always_listed_false_result["code"] == 0
    ), "Set NFT class always listed (false) transaction failed"
    print(f"Successfully set always_listed=false for class {name}")

    # Test authorization - Bob should not be able to set always_listed (should fail)
    unauthorized_always_listed_result = dysond_bin(
        "tx",
        "nameservice",
        "set-nft-class-always-listed",
        "--class-id",
        name,
        "--always-listed",
        "--from",
        bob_name,
    )
    # This should fail, but if it returns a code, it should be non-zero
    assert unauthorized_always_listed_result["code"] != 0, (
        "Bob was able to set always_listed for Alice's class"
        + unauthorized_always_listed_result["raw_log"]
    )
    print(
        "Verified authorization: Bob correctly cannot set always_listed for Alice's class"
    )

    # Step 7.2: Test NFT Class Valuation Fee Settings
    test_fee_pcts = [0.0, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
    for pct in test_fee_pcts:
        res = dysond_bin(
            "tx",
            "nameservice",
            "set-nft-class-valuation-fee-pct",
            "--class-id",
            name,
            "--valuation-fee-pct",
            str(pct),
            "--from",
            alice_name,
        )
        params_after = dysond_bin("query", "nameservice", "params")
        info_after = dysond_bin("query", "nft", "class", name)
        assert (
            res["code"] == 0
        ), f"set valuation fee pct ({pct}) failed. Raw log: {res.get('raw_log')}. Params: {params_after}. Class: {info_after}"
        assert (
            "class" in info_after
        ), f"NFT class {name} not found after setting valuation_fee_pct. Full: {info_after}"

    # Test authorization - Bob should not be able to set valuation_fee_pct (should fail)
    unauthorized_res = dysond_bin(
        "tx",
        "nameservice",
        "set-nft-class-valuation-fee-pct",
        "--class-id",
        name,
        "--valuation-fee-pct",
        "0.155",
        "--from",
        bob_name,
    )
    assert unauthorized_res["code"] != 0, (
        "Bob was able to set valuation_fee_pct for Alice's class"
        + unauthorized_res["raw_log"]
    )

    # Test the new settings on the sub-class as well
    sub_always_listed_result = dysond_bin(
        "tx",
        "nameservice",
        "set-nft-class-always-listed",
        "--class-id",
        sub_class_id,
        "--always-listed",
        "--from",
        alice_name,
    )
    assert (
        sub_always_listed_result["code"] == 0
    ), "Set NFT sub-class always listed transaction failed"
    print(f"Successfully set always_listed=true for sub-class {sub_class_id}")

    sub_res = dysond_bin(
        "tx",
        "nameservice",
        "set-nft-class-valuation-fee-pct",
        "--class-id",
        sub_class_id,
        "--valuation-fee-pct",
        "0.0",
        "--from",
        alice_name,
    )
    assert sub_res["code"] == 0, (
        "Set NFT sub-class valuation fee pct failed" + sub_res["raw_log"]
    )

    # Step 7.3: Test Individual NFT Listed Setting
    # Test setting listed=true for the main NFT
    set_listed_true_result = dysond_bin(
        "tx",
        "nameservice",
        "set-listed",
        "--nft-class-id",
        name,
        "--nft-id",
        nft_id,
        "--listed",
        "--from",
        alice_name,
    )
    assert set_listed_true_result["code"] == 0, (
        "Set NFT listed (true) transaction failed" + set_listed_true_result["raw_log"]
    )
    print(f"Successfully set listed=true for NFT {nft_id}")

    # Test setting listed=false for the sub-collection NFT (omit --listed flag)
    set_listed_false_result = dysond_bin(
        "tx",
        "nameservice",
        "set-listed",
        "--nft-class-id",
        sub_class_id,
        "--nft-id",
        sub_nft_id,
        "--from",
        alice_name,
    )
    assert (
        set_listed_false_result["code"] == 0
    ), "Set NFT listed (false) transaction failed"
    print(f"Successfully set listed=false for NFT {sub_nft_id}")

    # Test authorization - Bob should not be able to set listed status for Alice's NFT
    unauthorized_listed_result = dysond_bin(
        "tx",
        "nameservice",
        "set-listed",
        "--nft-class-id",
        name,
        "--nft-id",
        nft_id,
        "--listed",
        "--from",
        bob_name,
    )
    assert unauthorized_listed_result["code"] != 0, (
        "Bob was able to set listed status for Alice's NFT"
        + unauthorized_listed_result["raw_log"]
    )
    print(
        "Verified authorization: Bob correctly cannot set listed status for Alice's NFT"
    )

    # Verify the listed status through NFT queries
    nft_after_listed = dysond_bin("query", "nft", "nft", name, nft_id)
    print(f"Verified listed status updated for NFT {nft_id}")

    sub_nft_after_listed = dysond_bin("query", "nft", "nft", sub_class_id, sub_nft_id)
    print(f"Verified listed status updated for NFT {sub_nft_id}")

    # Test setting listed=true for the registered name NFT (nameservice.dys class)
    name_set_listed_result = dysond_bin(
        "tx",
        "nameservice",
        "set-listed",
        "--nft-class-id",
        "nameservice.dys",
        "--nft-id",
        name,
        "--listed",
        "--from",
        alice_name,
    )
    assert name_set_listed_result["code"] == 0, (
        "Set name NFT listed transaction failed" + name_set_listed_result["raw_log"]
    )
    print(f"Successfully set listed=true for registered name NFT {name}")

    # Verify the name NFT listed status
    name_nft_after_listed = dysond_bin("query", "nft", "nft", "nameservice.dys", name)
    print(f"Verified listed status updated for registered name NFT {name}")

    # Step 8: Custom Coin Operations
    # Generate random coin amounts
    main_coin_amount = random.randint(500, 2000)
    sub_coin_amount = random.randint(100, 500)

    # Mint coins with the name as denomination
    mint_coins_result = dysond_bin(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{main_coin_amount}{name}",
        "--mint-fee",
        f"{math.ceil(main_coin_amount * 0.01)}udys",
        "--from",
        alice_name,
    )
    assert mint_coins_result["code"] == 0, (
        "Mint coins transaction failed" + mint_coins_result["raw_log"]
    )
    print(f"Minted {main_coin_amount} {name} tokens successfully")

    # Mint coins with subdenom
    subdenom = f"{name}/token{random.randint(1, 999)}"
    mint_subdenom_result = dysond_bin(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{sub_coin_amount}{subdenom}",
        "--mint-fee",
        f"{math.ceil(sub_coin_amount * 0.01)}udys",
        "--from",
        alice_name,
    )
    assert mint_subdenom_result["code"] == 0, (
        "Mint subdenom coins transaction failed" + mint_subdenom_result["raw_log"]
    )
    print(f"Minted {sub_coin_amount} {subdenom} tokens successfully")

    # Check balances
    updated_alice_balances = dysond_bin("query", "bank", "balances", alice_address)
    assert "balances" in updated_alice_balances, "No balances found"

    # Verify minted coins are in the balance
    updated_alice_balances_dict = {
        b["denom"]: b["amount"] for b in updated_alice_balances["balances"]
    }
    assert (
        name in updated_alice_balances_dict
    ), f"Minted {name} coins not found in balance"
    assert (
        int(updated_alice_balances_dict[name]) == main_coin_amount
    ), f"Incorrect balance of {name} coins: Expected {main_coin_amount}, got {updated_alice_balances_dict[name]}"

    assert (
        subdenom in updated_alice_balances_dict
    ), f"Minted {subdenom} coins not found in balance"
    assert (
        int(updated_alice_balances_dict[subdenom]) == sub_coin_amount
    ), f"Incorrect balance of {subdenom} coins: Expected {sub_coin_amount}, got {updated_alice_balances_dict[subdenom]}"
    print(f"Verified minted coin balances")

    # Calculate a random transfer amount (between 10% and 50% of total)
    transfer_amount = random.randint(
        int(main_coin_amount * 0.1), int(main_coin_amount * 0.5)
    )

    # Send custom coins to Bob
    send_coins_result = dysond_bin(
        "tx", "bank", "send", alice_address, bob_address, f"{transfer_amount}{name}"
    )
    assert send_coins_result["code"] == 0, (
        "Send coins transaction failed" + send_coins_result["raw_log"]
    )
    print(f"Sent {transfer_amount} {name} tokens to Bob successfully")

    # Check Bob's balance
    bob_updated_balances = dysond_bin("query", "bank", "balances", bob_address)
    bob_balances_dict = {
        b["denom"]: b["amount"] for b in bob_updated_balances["balances"]
    }
    assert name in bob_balances_dict, f"Sent {name} coins not found in Bob's balance"
    assert (
        int(bob_balances_dict[name]) == transfer_amount
    ), f"Incorrect balance of {name} coins in Bob's account: Expected {transfer_amount}, got {bob_balances_dict[name]}"
    print(f"Verified Bob received {transfer_amount} {name} tokens")

    # Check Alice's updated balance
    alice_final_balances = dysond_bin("query", "bank", "balances", alice_address)
    alice_final_balances_dict = {
        b["denom"]: b["amount"] for b in alice_final_balances["balances"]
    }
    expected_alice_balance = main_coin_amount - transfer_amount
    assert (
        int(alice_final_balances_dict[name]) == expected_alice_balance
    ), f"Alice's {name} balance not correctly reduced after transfer. Expected {expected_alice_balance}, got {alice_final_balances_dict[name]}"
    print(f"Verified Alice's {name} balance decreased to {expected_alice_balance}")

    # Step 9: Bidding System Tests
    # Use a new name for bidding tests to keep the original name clean
    bidding_name = f"bid-{test_id}.dys"
    bidding_salt = secrets.token_hex(8)

    # Compute hash for commitment
    bidding_hash_result = dysond_bin(
        "query",
        "nameservice",
        "compute-hash",
        "--name",
        bidding_name,
        "--salt",
        bidding_salt,
        "--committer",
        alice_address,
    )
    bidding_commitment_hash = bidding_hash_result.get("hex_hash")

    # Set bidding name valuation
    bidding_valuation = random.randint(3000, 4000)

    # Commit to registering the bidding test name
    bidding_commit_result = dysond_bin(
        "tx",
        "nameservice",
        "commit",
        "--commitment",
        bidding_commitment_hash,
        "--valuation",
        f"{bidding_valuation}udys",
        "--from",
        alice_name,
    )
    assert bidding_commit_result["code"] == 0, (
        "Bidding name commit transaction failed" + bidding_commit_result["raw_log"]
    )

    # Reveal the bidding test name
    bidding_reveal_result = dysond_bin(
        "tx",
        "nameservice",
        "reveal",
        "--name",
        bidding_name,
        "--salt",
        bidding_salt,
        "--from",
        alice_name,
    )
    assert bidding_reveal_result["code"] == 0, (
        "Bidding name reveal transaction failed" + bidding_reveal_result["raw_log"]
    )
    print(f"Registered bidding test name: {bidding_name}")

    # Verify the NFT exists with correct valuation
    bidding_nft_info = dysond_bin(
        "query", "nft", "nft", "nameservice.dys", bidding_name
    )
    assert "nft" in bidding_nft_info, "Bidding NFT not found after registration"
    assert (
        bidding_nft_info["nft"]["id"] == bidding_name
    ), "Bidding NFT ID doesn't match registered name"

    # Step 9.1: Bob places a bid on the NFT
    bob_bid_amount = bidding_valuation + random.randint(10, 30)
    bob_bid_result = dysond_bin(
        "tx",
        "nameservice",
        "place-bid",
        "--nft-class-id",
        "nameservice.dys",
        "--nft-id",
        bidding_name,
        "--bid-amount",
        f"{bob_bid_amount}udys",
        "--from",
        bob_name,
    )
    assert bob_bid_result["code"] == 0, (
        "Bob's place bid transaction failed" + bob_bid_result["raw_log"]
    )
    print(f"Bob successfully placed a bid of {bob_bid_amount}udys")

    # Verify the bid was recorded
    nft_info_after_bid = dysond_bin(
        "query", "nft", "nft", "nameservice.dys", bidding_name
    )
    nft_data_after_bid = nft_info_after_bid["nft"].get("data", {}).get("value", {})
    assert nft_data_after_bid.get("current_bid", {}).get("amount") == str(
        bob_bid_amount
    ), "Bob's bid not recorded correctly"
    assert (
        nft_data_after_bid.get("current_bidder") == bob_address
    ), "Bob's address not recorded as bidder"
    print(f"Verified current bid is now {bob_bid_amount}udys from Bob")

    # Step 9.2: Alice accepts Bob's bid
    accept_bid_result = dysond_bin(
        "tx",
        "nameservice",
        "accept-bid",
        "--nft-class-id",
        "nameservice.dys",
        "--nft-id",
        bidding_name,
        "--from",
        alice_name,
    )
    assert accept_bid_result["code"] == 0, (
        "Accept bid transaction failed" + accept_bid_result["raw_log"]
    )
    print("Alice successfully accepted Bob's bid")

    # Verify the NFT is now owned by Bob
    nft_owner_after_accept = dysond_bin(
        "query", "nft", "owner", "nameservice.dys", bidding_name
    )
    assert (
        nft_owner_after_accept.get("owner") == bob_address
    ), "NFT not transferred to Bob after bid acceptance"
    print(
        f"Verified NFT ownership transferred to Bob: {nft_owner_after_accept.get('owner')}"
    )

    # Step 9.3: Charlie places a bid on Bob's NFT
    # Check if Charlie has enough DYS balance using list comprehensions
    balances = dysond_bin("query", "bank", "balances", charlie_address)
    dys_balances = [
        b
        for b in balances.get("balances", [])
        if b.get("denom") == "udys" and int(b.get("amount", "0")) > 200
    ]
    has_dys = len(dys_balances) > 0

    # Send funds to Charlie from Alice if needed
    fund_result = (
        dysond_bin("tx", "bank", "send", "alice", charlie_address, "200udys")
        if not has_dys
        else None
    )
    expected_fund_called = not has_dys
    actual_fund_called = fund_result is not None
    assert actual_fund_called == expected_fund_called, (
        f"Funding call mismatch. has_dys={has_dys}, expected_fund_called={expected_fund_called}, "
        f"fund_result={fund_result}"
    )
    expected_code = 0 if expected_fund_called else None
    actual_code = None if fund_result is None else fund_result.get("code")
    assert actual_code == expected_code, "Failed to fund Charlie's account: " + (
        fund_result.get("raw_log", "") if fund_result else ""
    )
    print("Funded Charlie's account with 200udys") if not has_dys else None

    charlie_bid_amount = bob_bid_amount + random.randint(20, 50)
    charlie_bid_result = dysond_bin(
        "tx",
        "nameservice",
        "place-bid",
        "--nft-class-id",
        "nameservice.dys",
        "--nft-id",
        bidding_name,
        "--bid-amount",
        f"{charlie_bid_amount}udys",
        "--from",
        charlie_name,
    )
    assert charlie_bid_result["code"] == 0, (
        "Charlie's place bid transaction failed" + charlie_bid_result["raw_log"]
    )
    print(f"Charlie successfully placed a bid of {charlie_bid_amount}udys")

    # Step 9.4: Bob rejects Charlie's bid with a higher valuation
    # Compute minimum acceptable valuation based on module param (e.g., 1% above current bid)
    params = dysond_bin("query", "nameservice", "params")
    # Use default expected min increase since it is now class-level; pick 0.01 for computation
    min_inc_str = "0.01"
    min_inc = Decimal(min_inc_str)
    min_required = int(
        (Decimal(charlie_bid_amount) * (Decimal(1) + min_inc)).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    new_bidding_valuation = max(
        min_required, charlie_bid_amount + random.randint(10, 30)
    )
    reject_bid_result = dysond_bin(
        "tx",
        "nameservice",
        "reject-bid",
        "--nft-class-id",
        "nameservice.dys",
        "--nft-id",
        bidding_name,
        "--new-valuation",
        f"{new_bidding_valuation}udys",
        "--from",
        bob_name,
    )
    assert reject_bid_result["code"] == 0, (
        "Reject bid transaction failed" + reject_bid_result["raw_log"]
    )
    print(
        f"Bob successfully rejected Charlie's bid and set new valuation to {new_bidding_valuation}udys"
    )

    # Verify Charlie's bid was rejected and valuation was updated
    nft_info_after_reject = dysond_bin(
        "query", "nft", "nft", "nameservice.dys", bidding_name
    )
    nft_data_after_reject = (
        nft_info_after_reject["nft"].get("data", {}).get("value", {})
    )
    assert nft_data_after_reject.get("valuation", {}).get("amount") == str(
        new_bidding_valuation
    ), "New valuation not set correctly"
    assert not nft_data_after_reject.get(
        "current_bidder"
    ), "Bid was not cleared after rejection"
    print("Verified bid was rejected and valuation updated")

    # Step 9.5: Test claim-bid functionality
    # For global tests we skip modifying class-level timeout here

    # Create a separate name for testing bid timeout
    timeout_name = f"timeout-{test_id}.dys"
    timeout_salt = secrets.token_hex(8)

    # Compute hash for commitment
    timeout_hash_result = dysond_bin(
        "query",
        "nameservice",
        "compute-hash",
        "--name",
        timeout_name,
        "--salt",
        timeout_salt,
        "--committer",
        alice_address,
    )
    timeout_commitment_hash = timeout_hash_result.get("hex_hash")

    # Commit to registering the timeout test name
    timeout_commit_result = dysond_bin(
        "tx",
        "nameservice",
        "commit",
        "--commitment",
        timeout_commitment_hash,
        "--valuation",
        f"{bidding_valuation}udys",
        "--from",
        alice_name,
    )
    assert timeout_commit_result["code"] == 0, (
        "Timeout name commit transaction failed" + timeout_commit_result["raw_log"]
    )

    # Reveal the timeout test name
    timeout_reveal_result = dysond_bin(
        "tx",
        "nameservice",
        "reveal",
        "--name",
        timeout_name,
        "--salt",
        timeout_salt,
        "--from",
        alice_name,
    )
    assert timeout_reveal_result["code"] == 0, (
        "Timeout name reveal transaction failed" + timeout_reveal_result["raw_log"]
    )
    print(f"Registered timeout test name: {timeout_name}")

    # Charlie places a bid on the timeout test name
    timeout_bid_amount = bidding_valuation + random.randint(10, 30)
    timeout_bid_result = dysond_bin(
        "tx",
        "nameservice",
        "place-bid",
        "--nft-class-id",
        "nameservice.dys",
        "--nft-id",
        timeout_name,
        "--bid-amount",
        f"{timeout_bid_amount}udys",
        "--from",
        charlie_name,
    )
    assert timeout_bid_result["code"] == 0, (
        "Charlie's place bid on timeout name failed" + timeout_bid_result["raw_log"]
    )
    print(
        f"Charlie successfully placed a bid of {timeout_bid_amount}udys on {timeout_name}"
    )

    # Verify the bid was recorded on the timeout test name
    timeout_nft_info = dysond_bin(
        "query", "nft", "nft", "nameservice.dys", timeout_name
    )
    timeout_nft_data = timeout_nft_info["nft"].get("data", {}).get("value", {})
    assert timeout_nft_data.get("current_bid", {}).get("amount") == str(
        timeout_bid_amount
    ), "Charlie's bid on timeout name not recorded correctly"

    # Wait for bid timeout by polling blocks. Default nameservice.dys timeout is ~5s.
    # With ~500ms block time, wait for >= 12 blocks since the bid.
    bid_block_height = int(timeout_bid_result["height"])

    def timeout_elapsed():
        out = dysond_bin("query", "block")
        current_block = int(out["header"]["height"])
        return (current_block - bid_block_height) >= 12

    poll_until_condition(
        timeout_elapsed, timeout=20, error_message="Bid timeout did not elapse"
    )

    claim_bid_result = dysond_bin(
        "tx",
        "nameservice",
        "claim-bid",
        "--nft-class-id",
        "nameservice.dys",
        "--nft-id",
        timeout_name,
        "--from",
        charlie_name,
    )
    assert claim_bid_result["code"] == 0, (
        "Charlie's claim bid on timeout name failed" + claim_bid_result["raw_log"]
    )
    print("Charlie successfully claimed the NFT after timeout")

    # Verify Charlie now owns the NFT
    owner_data = dysond_bin("query", "nft", "owner", "nameservice.dys", timeout_name)
    assert owner_data, "Failed to get owner data"
    assert "owner" in owner_data, "Owner data missing owner field"
    assert (
        owner_data["owner"] == charlie_address
    ), f"NFT not transferred to Charlie: {owner_data['owner']} != {charlie_address}"
    print(f"Verified NFT ownership transferred to Charlie: {charlie_address}")

    print("Nameservice E2E test completed successfully!")


def test_set_destination_validation(chainnet, generate_account, faucet, register_name):
    """Test that SetDestination properly validates destinations"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1000)

    # Register a name
    valid_name = register_name(dysond_bin, alice_name, alice_address, "1000udys")

    # Test 1: Setting destination to a valid address should work
    set_valid_addr = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        valid_name,
        "--destination",
        alice_address,
        "--from",
        alice_name,
    )
    assert (
        set_valid_addr["code"] == 0
    ), f"Valid address destination failed: {set_valid_addr.get('raw_log', '')}"
    print(f"✓ Valid address destination accepted: {alice_address}")

    # Test 2: Setting destination to empty string should work
    set_empty = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        valid_name,
        "--destination",
        "",
        "--from",
        alice_name,
    )
    assert (
        set_empty["code"] == 0
    ), f"Empty destination failed: {set_empty.get('raw_log', '')}"
    print("✓ Empty destination accepted")

    # Test 3: Setting destination to an existing name should work
    other_name = register_name(dysond_bin, alice_name, alice_address, "1000udys")
    set_dest_addr = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        other_name,
        "--destination",
        alice_address,
        "--from",
        alice_name,
    )
    assert set_dest_addr["code"] == 0

    set_name_dest = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        valid_name,
        "--destination",
        other_name,
        "--from",
        alice_name,
    )
    assert (
        set_name_dest["code"] == 0
    ), f"Existing name destination failed: {set_name_dest.get('raw_log', '')}"
    print(f"✓ Existing name destination accepted: {other_name}")

    # Test 4: Setting destination to non-existent name should fail
    nonexistent_name = f"nonexistent-{int(time.time())}.dys"
    set_invalid = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        valid_name,
        "--destination",
        nonexistent_name,
        "--from",
        alice_name,
    )
    assert (
        set_invalid["code"] != 0
    ), f"Non-existent name destination should have failed but succeeded: {set_invalid}"
    print(f"✓ Non-existent name destination rejected: {nonexistent_name}")

    # Test 5: Setting destination to invalid address should fail
    invalid_address = "invalid-address-123"
    set_invalid_addr = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        valid_name,
        "--destination",
        invalid_address,
        "--from",
        alice_name,
    )
    assert (
        set_invalid_addr["code"] != 0
    ), f"Invalid address destination should have failed but succeeded: {set_invalid_addr}"
    print(f"✓ Invalid address destination rejected: {invalid_address}")


def test_set_destination_cycle_prevention(
    chainnet, generate_account, faucet, register_name
):
    """Test that SetDestination prevents creating cycles"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1000)

    # Register two names
    name1 = register_name(dysond_bin, alice_name, alice_address, "1000udys")
    name2 = register_name(dysond_bin, alice_name, alice_address, "1000udys")

    # Set name1 -> name2 (should work)
    set_dest1 = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name1,
        "--destination",
        name2,
        "--from",
        alice_name,
    )
    assert (
        set_dest1["code"] == 0
    ), f"Setting name1 -> name2 failed: {set_dest1.get('raw_log', '')}"

    # Try to set name2 -> name1 (should fail due to cycle)
    set_dest2 = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name2,
        "--destination",
        name1,
        "--from",
        alice_name,
    )
    assert (
        set_dest2["code"] != 0
    ), f"Creating cycle should have failed but succeeded: {set_dest2}"
    print(f"✓ Cycle prevention: {name1} -> {name2} -> {name1} (rejected)")

    # Verify name1 can still be resolved (points to name2 -> address)
    set_name2_addr = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name2,
        "--destination",
        alice_address,
        "--from",
        alice_name,
    )
    assert set_name2_addr["code"] == 0

    resolution = dysond_bin("query", "nameservice", "resolve", name1)
    assert resolution["address"] == alice_address
    print(f"✓ Name resolution still works: {name1} -> {name2} -> {alice_address}")


def test_set_destination_max_depth_prevention(
    chainnet, generate_account, faucet, register_name
):
    """Test that SetDestination prevents creating chains that exceed max depth"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1000)

    # Create a chain of 9 names (at the limit)
    names = []
    for i in range(10):
        name = register_name(dysond_bin, alice_name, alice_address, "1000udys")
        names.append(name)

    # Chain first 9 names together
    for i in range(8):
        set_dest = dysond_bin(
            "tx",
            "nameservice",
            "set-destination",
            "--name",
            names[i],
            "--destination",
            names[i + 1],
            "--from",
            alice_name,
        )
        assert (
            set_dest["code"] == 0
        ), f"Setting {names[i]} -> {names[i+1]} failed: {set_dest.get('raw_log', '')}"

    # Set the 9th name to point to alice_address
    set_final = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        names[8],
        "--destination",
        alice_address,
        "--from",
        alice_name,
    )
    assert (
        set_final["code"] == 0
    ), f"Setting {names[8]} -> {alice_address} failed: {set_final.get('raw_log', '')}"

    # Try to set the 10th name to point to the chain start (would exceed depth)
    set_exceed = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        names[9],
        "--destination",
        names[0],
        "--from",
        alice_name,
    )
    assert (
        set_exceed["code"] != 0
    ), f"Exceeding max depth should have failed but succeeded: {set_exceed}"
    print(f"✓ Max depth prevention: chain of 10+ names rejected")

    # Verify the 9-name chain still resolves correctly
    resolution = dysond_bin("query", "nameservice", "resolve", names[0])
    assert resolution["address"] == alice_address
    print(f"✓ 9-name chain still resolves: {names[0]} -> ... -> {alice_address}")


def test_nested_name_resolution(chainnet, generate_account, faucet, register_name):
    """Test iterative resolution of nested name destinations"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1000)
    [bob_name, bob_address] = generate_account("bob", faucet_amount=1000)

    # Register two names using the fixture
    name1 = register_name(dysond_bin, alice_name, alice_address, "1000udys")
    name2 = register_name(dysond_bin, alice_name, alice_address, "1000udys")

    # Set name2 destination to alice_address
    set_dest2 = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name2,
        "--destination",
        alice_address,
        "--from",
        alice_name,
    )
    assert set_dest2["code"] == 0

    # Set name1 destination to name2 (nested)
    set_dest1 = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name1,
        "--destination",
        name2,
        "--from",
        alice_name,
    )
    assert set_dest1["code"] == 0

    # Test resolution: name1 should resolve through name2 to alice_address
    resolution = dysond_bin("query", "nameservice", "resolve", name1)
    assert (
        resolution["address"] == alice_address
    ), f"Expected {alice_address}, got {resolution['address']}"
    print(f"✓ Nested resolution: {name1} -> {name2} -> {alice_address}")


def test_cycle_detection(chainnet, generate_account, faucet, register_name):
    """Test cycle detection in name resolution"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1000)

    # Register both names using the fixture
    name1 = register_name(dysond_bin, alice_name, alice_address, "1000udys")
    name2 = register_name(dysond_bin, alice_name, alice_address, "1000udys")

    # Create name1 -> name2 (should work)
    set_dest1 = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name1,
        "--destination",
        name2,
        "--from",
        alice_name,
    )
    assert (
        set_dest1["code"] == 0
    ), f"Setting name1 -> name2 failed: {set_dest1.get('raw_log', '')}"

    # Try to create cycle: name2 -> name1 (should fail due to cycle)
    set_dest2 = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name2,
        "--destination",
        name1,
        "--from",
        alice_name,
    )
    assert (
        set_dest2["code"] != 0
    ), f"Creating cycle should have failed but succeeded: {set_dest2}"
    print(f"✓ Cycle prevention: {name1} -> {name2} -> {name1} (rejected)")

    # Verify name1 can still be resolved (points to name2 -> address)
    set_name2_addr = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name2,
        "--destination",
        alice_address,
        "--from",
        alice_name,
    )
    assert set_name2_addr["code"] == 0

    resolution = dysond_bin("query", "nameservice", "resolve", name1)
    assert resolution["address"] == alice_address
    print(f"✓ Name resolution still works: {name1} -> {name2} -> {alice_address}")


def test_max_depth_exceeded(chainnet, generate_account, faucet, register_name):
    """Test maximum depth protection in name resolution"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1000)

    # Create a chain longer than maxDepth (10)
    names = []
    for i in range(12):
        name = register_name(dysond_bin, alice_name, alice_address, "1000udys")
        names.append(name)

    # Chain them together: names[0] -> names[1] -> ... -> names[10] -> alice_address
    for i in range(len(names) - 1):
        destination = names[i + 1] if i < len(names) - 2 else alice_address
        set_dest = dysond_bin(
            "tx",
            "nameservice",
            "set-destination",
            "--name",
            names[i],
            "--destination",
            destination,
            "--from",
            alice_name,
        )
        assert (
            set_dest["code"] == 0
        ), f"Setting {names[i]} -> {destination} failed: {set_dest.get('raw_log', '')}"

    # Set final name to alice_address
    set_final = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        names[-1],
        "--destination",
        alice_address,
        "--from",
        alice_name,
    )
    assert (
        set_final["code"] == 0
    ), f"Setting {names[-1]} -> {alice_address} failed: {set_final.get('raw_log', '')}"

    # Test that resolution fails with max depth exceeded
    resolution = dysond_bin("query", "nameservice", "resolve", names[0])
    # Should return a string error message
    assert isinstance(
        resolution, str
    ), f"Expected string error, got {type(resolution)}: {resolution}"
    assert (
        "exceeded maximum depth" in resolution
    ), f"Expected depth error, got: {resolution}"
    print(f"✓ Max depth protection: chain of {len(names)} names")


def test_mixed_name_types(chainnet, generate_account, faucet, register_name):
    """Test resolution with mixed name types (not just .dys)"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1000)

    # Register all names using the fixture
    name_dys = register_name(dysond_bin, alice_name, alice_address, "1000udys")
    name_custom = register_name(dysond_bin, alice_name, alice_address, "1000udys")
    name_test = register_name(dysond_bin, alice_name, alice_address, "1000udys")

    # Chain: name_dys -> name_custom -> name_test -> alice_address
    set_dest1 = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name_dys,
        "--destination",
        name_custom,
        "--from",
        alice_name,
    )
    assert (
        set_dest1["code"] == 0
    ), f"Setting {name_dys} -> {name_custom} failed: {set_dest1.get('raw_log', '')}"
    set_dest2 = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name_custom,
        "--destination",
        name_test,
        "--from",
        alice_name,
    )
    assert (
        set_dest2["code"] == 0
    ), f"Setting {name_custom} -> {name_test} failed: {set_dest2.get('raw_log', '')}"
    set_dest3 = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name_test,
        "--destination",
        alice_address,
        "--from",
        alice_name,
    )
    assert (
        set_dest3["code"] == 0
    ), f"Setting {name_test} -> {alice_address} failed: {set_dest3.get('raw_log', '')}"

    # Test resolution through mixed name types
    resolution = dysond_bin("query", "nameservice", "resolve", name_dys)
    assert (
        resolution["address"] == alice_address
    ), f"Expected {alice_address}, got {resolution['address']}"
    print(
        f"✓ Mixed types: {name_dys} -> {name_custom} -> {name_test} -> {alice_address}"
    )


def test_invalid_intermediate_destination(
    chainnet, generate_account, faucet, register_name
):
    """Test error handling for invalid intermediate destinations"""
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=1000)

    # Create valid name using the fixture
    valid_name = register_name(dysond_bin, alice_name, alice_address, "1000udys")

    # Set destination to non-existent name - this should now fail at transaction level
    nonexistent_name = f"nonexistent-{int(time.time())}.dys"
    set_dest = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        valid_name,
        "--destination",
        nonexistent_name,
        "--from",
        alice_name,
    )
    assert (
        set_dest["code"] != 0
    ), f"Setting destination to non-existent name should fail, but got: {set_dest}"
    print(
        f"✓ Invalid destination rejected at transaction level: {valid_name} -> {nonexistent_name}"
    )

    # Also test invalid address format
    invalid_address = "invalid-address-format"
    set_invalid_addr = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        valid_name,
        "--destination",
        invalid_address,
        "--from",
        alice_name,
    )
    assert (
        set_invalid_addr["code"] != 0
    ), f"Setting destination to invalid address should fail, but got: {set_invalid_addr}"
    print(f"✓ Invalid address format rejected: {valid_name} -> {invalid_address}")


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

    poll_until_condition(
        has_proposal_reached_final_state,
        timeout=timeout,
        error_message="Timeout waiting for proposal to reach final state",
    )
    proposal_result = dysond_bin("query", "gov", "proposal", proposal_id)
    final_status = proposal_result.get("status", "")
    return final_status


def set_bid_timeout_via_gov(dysond_bin, proposer_name, bid_timeout_value: str):
    """Set bid timeout via governance proposal"""
    # Get current params
    current_params = dysond_bin("query", "nameservice", "params")
    current_allowed_denoms = current_params.get("params", {}).get(
        "allowed_denoms", ["udys"]
    )
    current_reject_fee_percent = current_params.get("params", {}).get(
        "reject_bid_valuation_fee_percent", "0.03"
    )
    current_minimum_bid_percent_increase = current_params.get("params", {}).get(
        "minimum_bid_percent_increase", "0.01"
    )
    current_mint_fee_per_coin = current_params.get("params", {}).get(
        "mint_fee_per_coin", "0.01"
    )

    # Query gov module account address
    gov_module_response = dysond_bin("query", "auth", "module-account", "gov")
    gov_address = (
        gov_module_response.get("account", {}).get("value", {}).get("address", "")
    )
    assert gov_address

    # Get validator operator address
    validators = dysond_bin("query", "staking", "validators")
    validator_operator = validators["validators"][0]["operator_address"]

    # Delegate tokens from Alice to validator so Alice has voting power
    delegate_result = dysond_bin(
        "tx",
        "staking",
        "delegate",
        validator_operator,
        "50000000udys",
        "--from",
        "alice",
        "--yes",
    )
    assert (
        delegate_result["code"] == 0
    ), f"Failed to delegate: {delegate_result['raw_log']}"

    proposal = {
        "messages": [
            {
                "@type": "/dysonprotocol.nameservice.v1.MsgUpdateParams",
                "authority": gov_address,
                "params": {
                    "bid_timeout": bid_timeout_value,
                    "allowed_denoms": current_allowed_denoms,
                    "reject_bid_valuation_fee_percent": current_reject_fee_percent,
                    "minimum_bid_percent_increase": current_minimum_bid_percent_increase,
                    "mint_fee_per_coin": current_mint_fee_per_coin,
                },
            }
        ],
        "metadata": "ipfs://CID",
        "deposit": "1udys",
        "title": "Update Nameservice Parameters",
        "summary": f"Update bid_timeout to {bid_timeout_value} for testing",
    }

    # Submit proposal using Alice (who now has voting power)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as f:
        json.dump(proposal, f)
        f.flush()  # Ensure data is written to disk
        tx_result = dysond_bin(
            "tx",
            "gov",
            "submit-proposal",
            f.name,
            "--from",
            "alice",
            "--keyring-backend",
            "test",
            "--yes",
        )

    print(f"Submit proposal result: {tx_result}")
    tx_result = dysond_bin("query", "wait-tx", tx_result["txhash"])
    print(f"Proposal result: {tx_result}")

    # Extract proposal ID using list comprehensions
    submit_proposal_events = [
        e for e in tx_result.get("events", []) if e.get("type") == "submit_proposal"
    ]
    proposal_id_attrs = [
        a
        for e in submit_proposal_events
        for a in e.get("attributes", [])
        if a.get("key") == "proposal_id"
    ]
    proposal_id = proposal_id_attrs[0].get("value") if proposal_id_attrs else None
    assert proposal_id, "Could not extract proposal ID"

    # Vote with Alice (who has voting power through delegation)
    vote_result = dysond_bin(
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
    vote_tx_result = dysond_bin("query", "wait-tx", vote_result["txhash"])
    print(f"Vote result: {vote_tx_result}")
    assert vote_tx_result["code"] == 0, vote_tx_result["raw_log"]

    # Wait for proposal to pass
    poll_until_proposal_passes(dysond_bin, proposal_id)

    # Check final proposal status
    final_proposal = dysond_bin("query", "gov", "proposal", proposal_id)
    final_status = final_proposal["proposal"]["status"]
    assert (
        final_status == "PROPOSAL_STATUS_PASSED"
    ), f"Governance proposal failed with status: {final_status}"

    # Verify params were updated
    params_result = dysond_bin("query", "nameservice", "params")
    print(f"Final nameservice params: {params_result}")
    assert (
        params_result["params"]["bid_timeout"] == bid_timeout_value
    ), f"Bid timeout not updated correctly"
