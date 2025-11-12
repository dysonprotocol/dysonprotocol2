import json

from tests.examples.rps.utils import (
    deploy_script,
    exec_initialize_game,
    exec_spawn_piece,
    extract_exec_result,
)


def test_spawn_piece_populates_storage(chainnet, generate_account):
    dysond_bin = chainnet[0]
    account_name, account_address = generate_account("rps_spawn", faucet_amount=200)

    deploy_script(dysond_bin, account_name)
    exec_initialize_game(dysond_bin, account_name, account_address)

    spawn_payload = exec_spawn_piece(dysond_bin, account_name, account_address)
    piece = spawn_payload["piece"]
    state = spawn_payload["state"]
    grid_entry = spawn_payload["grid"]["value"]
    player_entry = spawn_payload["player"]["value"]

    assert (
        piece["type"] == "rock"
    ), f"Unexpected piece type. Payload: {json.dumps(spawn_payload, indent=2)}"
    assert (
        piece["owner"] == account_address
    ), f"Piece owner mismatch. Payload: {json.dumps(spawn_payload, indent=2)}"
    assert (
        piece["energy"] == 0
    ), f"Pieces should start with zero energy. Payload: {json.dumps(spawn_payload, indent=2)}"
    # Pieces spawn at random empty locations on the board
    spawn_x = piece["x"]
    spawn_y = piece["y"]
    assert (
        spawn_x is not None and spawn_y is not None
    ), f"Spawn location missing. Payload: {json.dumps(spawn_payload, indent=2)}"

    stored_piece = dysond_bin(
        "query",
        "storage",
        "get",
        account_address,
        "--index",
        f"game/pieces/{piece['id']:010d}",
    )
    stored_piece_data = json.loads(stored_piece["entry"]["data"])
    assert (
        stored_piece_data == piece
    ), f"Stored piece mismatch. Expected: {json.dumps(piece, indent=2)}. Stored: {json.dumps(stored_piece_data, indent=2)}"

    assert (
        grid_entry["piece_id"] == piece["id"]
    ), f"Grid cell should reference spawned piece. Grid: {json.dumps(grid_entry, indent=2)}"

    assert (
        piece["id"] in player_entry["pieces"]
    ), f"Player record missing piece. Player: {json.dumps(player_entry, indent=2)}"
    assert (
        player_entry["total_kills"] == 0
    ), f"Unexpected kills in player record: {json.dumps(player_entry, indent=2)}"
    assert (
        player_entry["total_deaths"] == 0
    ), f"Unexpected deaths in player record: {json.dumps(player_entry, indent=2)}"

    assert (
        state["total_pieces"] == 1
    ), f"State total_pieces incorrect. State: {json.dumps(state, indent=2)}"
    assert (
        state["next_piece_id"] == 2
    ), f"State next_piece_id incorrect. State: {json.dumps(state, indent=2)}"

    payment_msg = json.dumps(
        {
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": account_address,
            "to_address": account_address,
            "amount": [{"denom": "udys", "amount": "100"}],
        }
    )
    second_spawn = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        account_address,
        "--function-name",
        "spawn_piece",
        "--args",
        json.dumps(["rock"]),
        "--attached-message",
        payment_msg,
        "--from",
        account_name,
        "--gas",
        "5000000",
    )
    # With random spawning, pieces can spawn at different locations
    # Second spawn should succeed (different random location)
    assert (
        second_spawn["code"] == 0
    ), f"Second spawn should succeed with random location. Result: {json.dumps(second_spawn, indent=2)}"
    
    # Verify second piece spawned successfully
    second_spawn_result = extract_exec_result(second_spawn)
    second_piece = second_spawn_result["piece"]
    assert (
        second_piece["id"] == 2
    ), f"Second piece should have id 2. Result: {json.dumps(second_piece, indent=2)}"


def test_spawn_payment_validation(chainnet, generate_account):
    dysond_bin = chainnet[0]
    account_name, account_address = generate_account("rps_payment", faucet_amount=200)

    deploy_script(dysond_bin, account_name)
    exec_initialize_game(dysond_bin, account_name, account_address)

    # Test 1: Missing payment (should fail)
    spawn_no_payment = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        account_address,
        "--function-name",
        "spawn_piece",
        "--args",
        json.dumps(["rock"]),
        "--from",
        account_name,
        "--gas",
        "3500000",
    )
    assert (
        spawn_no_payment["code"] != 0
    ), f"Spawn without payment should fail: {json.dumps(spawn_no_payment, indent=2)}"
    assert (
        "spawn requires payment" in spawn_no_payment["raw_log"].lower()
    ), f"Expected payment error. Raw log: {spawn_no_payment['raw_log']}"

    # Test 2: Insufficient payment (< 100 udys) (should fail)
    insufficient_payment_msg = json.dumps(
        {
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": account_address,
            "to_address": account_address,
            "amount": [{"denom": "udys", "amount": "50"}],
        }
    )
    spawn_insufficient = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        account_address,
        "--function-name",
        "spawn_piece",
        "--args",
        json.dumps(["rock"]),
        "--attached-message",
        insufficient_payment_msg,
        "--from",
        account_name,
        "--gas",
        "3500000",
    )
    assert (
        spawn_insufficient["code"] != 0
    ), f"Spawn with insufficient payment should fail: {json.dumps(spawn_insufficient, indent=2)}"
    assert (
        "insufficient payment" in spawn_insufficient["raw_log"].lower()
    ), f"Expected insufficient payment error. Raw log: {spawn_insufficient['raw_log']}"

    # Test 3: Wrong denom (should fail - may fail at bank level or script level)
    wrong_denom_msg = json.dumps(
        {
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": account_address,
            "to_address": account_address,
            "amount": [{"denom": "invalid", "amount": "100"}],
        }
    )
    spawn_wrong_denom = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        account_address,
        "--function-name",
        "spawn_piece",
        "--args",
        json.dumps(["rock"]),
        "--attached-message",
        wrong_denom_msg,
        "--from",
        account_name,
        "--gas",
        "3500000",
    )
    assert (
        spawn_wrong_denom["code"] != 0
    ), f"Spawn with wrong denom should fail: {json.dumps(spawn_wrong_denom, indent=2)}"
    # Error occurs at bank level (invalid denom rejected) or script level (payment validation)
    # Both are valid failures - just verify transaction failed
    assert (
        len(spawn_wrong_denom["raw_log"]) > 0
    ), f"Should have error message. Raw log: {spawn_wrong_denom['raw_log']}"

    # Test 4: Correct payment (should succeed)
    spawn_payload = exec_spawn_piece(dysond_bin, account_name, account_address)
    assert (
        spawn_payload["piece"]["type"] == "rock"
    ), f"Spawn with correct payment should succeed: {json.dumps(spawn_payload, indent=2)}"
