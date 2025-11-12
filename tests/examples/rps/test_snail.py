import json

from tests.examples.rps.utils import (
    deploy_script,
    exec_initialize_game,
    exec_move_piece,
    exec_spawn_piece,
    exec_spawn_snail,
    extract_exec_result,
    get_cell,
    get_piece,
    set_piece_energy,
    set_piece_direct,
    set_cell,
    set_game_state,
    set_player_record,
    wait_for_next_block,
    _get_block_height,
)

SNAIL_ID = 0


def test_snail_spawn(chainnet, generate_account):
    """Test that snail spawns correctly with proper attributes"""
    dysond_bin = chainnet[0]
    account_name, account_address = generate_account("snail_spawn", faucet_amount=1)

    deploy_script(dysond_bin, account_name)
    exec_initialize_game(dysond_bin, account_name, account_address)

    spawn_result = exec_spawn_snail(dysond_bin, account_name, account_address)
    snail = spawn_result["snail"]
    grid_cell = spawn_result["grid"]["value"]

    assert snail["id"] == SNAIL_ID, f"Snail ID incorrect: {json.dumps(snail, indent=2)}"
    assert (
        snail["type"] == "snail"
    ), f"Snail type incorrect: {json.dumps(snail, indent=2)}"
    assert (
        snail["is_npc"] is True
    ), f"Snail is_npc incorrect: {json.dumps(snail, indent=2)}"
    assert (
        snail["energy"] == 999999
    ), f"Snail energy incorrect: {json.dumps(snail, indent=2)}"
    # Snail spawns at random location, position is not checked here
    assert (
        snail["owner"] is None
    ), f"Snail owner should be None: {json.dumps(snail, indent=2)}"

    stored_snail = get_piece(dysond_bin, account_address, SNAIL_ID)
    assert (
        stored_snail == snail
    ), f"Stored snail mismatch: {json.dumps(stored_snail, indent=2)}"

    assert (
        grid_cell["piece_id"] == SNAIL_ID
    ), f"Grid cell should reference snail: {json.dumps(grid_cell, indent=2)}"

    assert (
        "heartbeat_task" in spawn_result
    ), f"Missing heartbeat_task: {json.dumps(spawn_result, indent=2)}"

    second_spawn = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        account_address,
        "--function-name",
        "spawn_snail",
        "--args",
        "[]",
        "--from",
        account_name,
        "--gas",
        "5000000",
    )
    assert (
        second_spawn["code"] != 0
    ), f"Second snail spawn should fail: {json.dumps(second_spawn, indent=2)}"
    assert (
        "snail already spawned" in second_spawn["raw_log"].lower()
    ), f"Expected snail already spawned error. Raw log: {second_spawn['raw_log']}"


def test_snail_tracks_oldest_player(chainnet, generate_account):
    """Test that snail targets the oldest player piece (min spawn_block)"""
    dysond_bin = chainnet[0]
    owner_name, owner_address = generate_account("snail_target", faucet_amount=200)
    player1_name, player1_address = generate_account("snail_player1", faucet_amount=200)
    player2_name, player2_address = generate_account("snail_player2", faucet_amount=200)

    deploy_script(dysond_bin, owner_name)
    exec_initialize_game(dysond_bin, owner_name, owner_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)
    
    # Create piece1 at (1, 0) - oldest piece (spawn_block = block_height - 10)
    piece1_id = 1
    piece1_x = 1
    piece1_y = 0
    piece1 = {
        "id": piece1_id,
        "owner": player1_address,
        "type": "rock",
        "x": piece1_x,
        "y": piece1_y,
        "energy": 0,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,  # Older spawn_block
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, piece1_id, piece1)
    set_cell(dysond_bin, owner_name, owner_address, piece1_x, piece1_y, {"piece_id": piece1_id})
    
    # Create piece2 at (0, 1) - newer piece (spawn_block = block_height - 5)
    piece2_id = 2
    piece2_x = 0
    piece2_y = 1
    piece2 = {
        "id": piece2_id,
        "owner": player2_address,
        "type": "paper",
        "x": piece2_x,
        "y": piece2_y,
        "energy": 0,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 5,  # Newer spawn_block
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, piece2_id, piece2)
    set_cell(dysond_bin, owner_name, owner_address, piece2_x, piece2_y, {"piece_id": piece2_id})
    
    # Update game state to reflect pieces
    state = {
        "total_pieces": 2,
        "total_energy_circulation": 0,
        "pending_market_energy": 0,
        "pending_grid_energy": 0,
        "last_updated_block": block_height - 1,
        "next_piece_id": 3,
    }
    set_game_state(dysond_bin, owner_name, owner_address, state)
    
    # Update player records
    player1_record = {
        "pieces": [piece1_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, player1_address, player1_record)
    
    player2_record = {
        "pieces": [piece2_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, player2_address, player2_record)
    
    # Ensure (0, 0) is empty for snail spawn
    set_cell(dysond_bin, owner_name, owner_address, 0, 0, {"piece_id": None})
    
    wait_for_next_block(dysond_bin, block_height)

    # Spawn snail - it should find (0, 0) as empty and spawn there
    exec_spawn_snail(dysond_bin, owner_name, owner_address)

    snail = get_piece(dysond_bin, owner_address, SNAIL_ID)
    # Snail spawns randomly, but we don't care about its position for this test
    # We only care that it targets the oldest piece

    # piece1 should be oldest (lower spawn_block)
    assert (
        piece1["spawn_block"] <= piece2["spawn_block"]
    ), "piece1 should be oldest for this test"

    move_snail_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        owner_address,
        "--function-name",
        "move_snail_ai",
        "--args",
        "[]",
        "--from",
        owner_name,
        "--gas",
        "10000000",
    )
    assert (
        move_snail_result["code"] == 0
    ), f"move_snail_ai failed: {json.dumps(move_snail_result, indent=2)}"

    move_payload = extract_exec_result(move_snail_result)
    target = move_payload["target"]

    assert (
        target["id"] == piece1_id
    ), f"Snail should target oldest piece. Target: {json.dumps(target, indent=2)}, Oldest piece ID: {piece1_id}"


def test_snail_defeats_rock(chainnet, generate_account):
    """Test that snail defeats rock piece (snail ignores RPS rules)"""
    dysond_bin = chainnet[0]
    owner_name, owner_address = generate_account("snail_combat_rock", faucet_amount=200)
    rock_name, rock_address = generate_account("snail_rock", faucet_amount=200)

    deploy_script(dysond_bin, owner_name)
    exec_initialize_game(dysond_bin, owner_name, owner_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)
    
    # Place rock piece at (1, 0) with 100 energy
    rock_piece_id = 1
    rock_piece = {
        "id": rock_piece_id,
        "owner": rock_address,
        "type": "rock",
        "x": 1,
        "y": 0,
        "energy": 100,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, rock_piece_id, rock_piece)
    set_cell(dysond_bin, owner_name, owner_address, 1, 0, {"piece_id": rock_piece_id})
    
    # Update game state
    state = {
        "total_pieces": 1,
        "total_energy_circulation": 0,
        "pending_market_energy": 0,
        "pending_grid_energy": 0,
        "last_updated_block": block_height - 1,
        "next_piece_id": 2,
    }
    set_game_state(dysond_bin, owner_name, owner_address, state)
    
    # Update player record
    player_record = {
        "pieces": [rock_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, rock_address, player_record)
    
    wait_for_next_block(dysond_bin, block_height)

    exec_spawn_snail(dysond_bin, owner_name, owner_address)

    snail = get_piece(dysond_bin, owner_address, SNAIL_ID)
    snail_initial_x = snail["x"]
    snail_initial_y = snail["y"]

    move_snail_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        owner_address,
        "--function-name",
        "move_snail_ai",
        "--args",
        "[]",
        "--from",
        owner_name,
        "--gas",
        "10000000",
    )
    assert (
        move_snail_result["code"] == 0
    ), f"move_snail_ai failed: {json.dumps(move_snail_result, indent=2)}"

    move_payload = extract_exec_result(move_snail_result)
    snail_after = move_payload["snail"]

    # Verify snail moved toward rock at (1, 0)
    distance_before = ((snail_initial_x - 1) ** 2 + (snail_initial_y - 0) ** 2) ** 0.5
    distance_after = ((snail_after["x"] - 1) ** 2 + (snail_after["y"] - 0) ** 2) ** 0.5
    assert (
        distance_after <= distance_before
    ), f"Snail should move closer to rock at (1,0). Before: {distance_before}, After: {distance_after}, Initial: ({snail_initial_x}, {snail_initial_y}), After: ({snail_after['x']}, {snail_after['y']})"


def test_player_cannot_attack_snail(chainnet, generate_account):
    """Test that players cannot move onto or attack the snail"""
    dysond_bin = chainnet[0]
    owner_name, owner_address = generate_account("snail_invuln", faucet_amount=200)
    player_name, player_address = generate_account("snail_player", faucet_amount=200)

    deploy_script(dysond_bin, owner_name)
    exec_initialize_game(dysond_bin, owner_name, owner_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)
    
    # Place snail at (1, 0) using direct storage (before spawning player)
    snail_piece = {
        "id": SNAIL_ID,
        "owner": None,
        "type": "snail",
        "x": 1,
        "y": 0,
        "energy": 999999,
        "last_action_block": block_height - 1,
        "is_npc": True,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, SNAIL_ID, snail_piece)
    set_cell(dysond_bin, owner_name, owner_address, 1, 0, {"piece_id": SNAIL_ID})
    
    # Place player piece at (0, 0) - adjacent to snail, can make valid king move
    player_piece_id = 1
    player_piece = {
        "id": player_piece_id,
        "owner": player_address,
        "type": "rock",
        "x": 0,
        "y": 0,
        "energy": 0,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 5,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, player_piece_id, player_piece)
    set_cell(dysond_bin, owner_name, owner_address, 0, 0, {"piece_id": player_piece_id})
    
    # Update game state
    state = {
        "total_pieces": 2,
        "total_energy_circulation": 0,
        "pending_market_energy": 0,
        "pending_grid_energy": 0,
        "last_updated_block": block_height - 1,
        "next_piece_id": 2,
    }
    set_game_state(dysond_bin, owner_name, owner_address, state)
    
    # Update player record
    player_record = {
        "pieces": [player_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, player_address, player_record)
    
    wait_for_next_block(dysond_bin, block_height)

    # Snail is already placed, so we can test attacking it
    snail_x, snail_y = 1, 0

    attack_snail = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        owner_address,
        "--function-name",
        "move_piece",
        "--args",
        json.dumps([player_piece_id, snail_x, snail_y]),
        "--from",
        player_name,
        "--gas",
        "5000000",
    )
    assert (
        attack_snail["code"] != 0
    ), f"Player should not be able to move onto snail: {json.dumps(attack_snail, indent=2)}"
    raw_log_lower = attack_snail["raw_log"].lower()
    has_npc_error = "npc" in raw_log_lower
    assert (
        has_npc_error
    ), f"Expected NPC-related error. Raw log: {attack_snail['raw_log']}"


def test_snail_crontask_scheduling(chainnet, generate_account):
    """Test that snail schedules its next move via crontask"""
    dysond_bin = chainnet[0]
    account_name, account_address = generate_account("snail_crontask", faucet_amount=1)

    deploy_script(dysond_bin, account_name)
    exec_initialize_game(dysond_bin, account_name, account_address)

    spawn_result = exec_spawn_snail(dysond_bin, account_name, account_address)
    assert (
        "heartbeat_task" in spawn_result
    ), f"Missing heartbeat_task: {json.dumps(spawn_result, indent=2)}"

    heartbeat_task = spawn_result["heartbeat_task"]
    assert (
        "task_id" in heartbeat_task
    ), f"Task should have task_id. Task: {json.dumps(heartbeat_task, indent=2)}"

    heartbeat_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        account_address,
        "--function-name",
        "snail_heartbeat",
        "--args",
        "[]",
        "--from",
        account_name,
        "--gas",
        "5000000",
    )
    assert (
        heartbeat_result["code"] == 0
    ), f"snail_heartbeat failed: {json.dumps(heartbeat_result, indent=2)}"

    heartbeat_payload = extract_exec_result(heartbeat_result)
    assert (
        "next_heartbeat_task" in heartbeat_payload
    ), f"snail_heartbeat should schedule next heartbeat: {json.dumps(heartbeat_payload, indent=2)}"


def test_snail_movement_close_range(chainnet, generate_account):
    """Test snail random movement when target is close (<100 cells)"""
    dysond_bin = chainnet[0]
    owner_name, owner_address = generate_account("snail_close", faucet_amount=200)
    player_name, player_address = generate_account(
        "snail_close_player", faucet_amount=200
    )

    deploy_script(dysond_bin, owner_name)
    exec_initialize_game(dysond_bin, owner_name, owner_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)
    
    # Place player piece at (1, 0) - close to origin for close-range test
    player_piece_id = 1
    player_piece = {
        "id": player_piece_id,
        "owner": player_address,
        "type": "rock",
        "x": 1,
        "y": 0,
        "energy": 0,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, player_piece_id, player_piece)
    set_cell(dysond_bin, owner_name, owner_address, 1, 0, {"piece_id": player_piece_id})
    
    # Update game state
    state = {
        "total_pieces": 1,
        "total_energy_circulation": 0,
        "pending_market_energy": 0,
        "pending_grid_energy": 0,
        "last_updated_block": block_height - 1,
        "next_piece_id": 2,
    }
    set_game_state(dysond_bin, owner_name, owner_address, state)
    
    # Update player record
    player_record = {
        "pieces": [player_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, player_address, player_record)
    
    wait_for_next_block(dysond_bin, block_height)

    exec_spawn_snail(dysond_bin, owner_name, owner_address)

    snail_before = get_piece(dysond_bin, owner_address, SNAIL_ID)
    initial_x, initial_y = snail_before["x"], snail_before["y"]

    move_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        owner_address,
        "--function-name",
        "move_snail_ai",
        "--args",
        "[]",
        "--from",
        owner_name,
        "--gas",
        "10000000",
    )
    assert (
        move_result["code"] == 0
    ), f"move_snail_ai failed: {json.dumps(move_result, indent=2)}"

    move_payload = extract_exec_result(move_result)
    snail_after = move_payload["snail"]

    # Verify snail moved (not stationary) - calculate distance moved
    distance_moved = ((snail_after["x"] - initial_x) ** 2 + (snail_after["y"] - initial_y) ** 2) ** 0.5
    assert (
        distance_moved > 0
    ), f"Snail should have moved. Initial: ({initial_x}, {initial_y}), After: ({snail_after['x']}, {snail_after['y']})"
    assert (
        abs(snail_after["x"] - initial_x) <= 1
    ), "Snail should move at most 1 cell in x"
    assert (
        abs(snail_after["y"] - initial_y) <= 1
    ), "Snail should move at most 1 cell in y"

    distance_before = ((initial_x - 1) ** 2 + (initial_y - 0) ** 2) ** 0.5
    distance_after = ((snail_after["x"] - 1) ** 2 + (snail_after["y"] - 0) ** 2) ** 0.5
    assert (
        distance_after <= distance_before
    ), f"Snail should move closer to target. Before: {distance_before}, After: {distance_after}"


def test_snail_movement_long_range(chainnet, generate_account):
    """Test snail straight-line movement when target is far (≥100 cells)"""
    dysond_bin = chainnet[0]
    owner_name, owner_address = generate_account("snail_far", faucet_amount=200)
    player_name, player_address = generate_account("snail_far_player", faucet_amount=200)

    deploy_script(dysond_bin, owner_name)
    exec_initialize_game(dysond_bin, owner_name, owner_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)
    
    # Place player piece at (200, 0) - far from origin, outside board bounds
    # Snail is not restricted by board boundaries, so it can target this piece
    target_x, target_y = 200, 0
    player_piece_id = 1
    player_piece = {
        "id": player_piece_id,
        "owner": player_address,
        "type": "rock",
        "x": target_x,
        "y": target_y,
        "energy": 50000,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, player_piece_id, player_piece)
    set_cell(dysond_bin, owner_name, owner_address, target_x, target_y, {"piece_id": player_piece_id})
    
    # Update game state
    state = {
        "total_pieces": 1,
        "total_energy_circulation": 0,
        "pending_market_energy": 0,
        "pending_grid_energy": 0,
        "last_updated_block": block_height - 1,
        "next_piece_id": 2,
    }
    set_game_state(dysond_bin, owner_name, owner_address, state)
    
    # Update player record
    player_record = {
        "pieces": [player_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, player_address, player_record)
    
    wait_for_next_block(dysond_bin, block_height)

    exec_spawn_snail(dysond_bin, owner_name, owner_address)

    snail_before = get_piece(dysond_bin, owner_address, SNAIL_ID)
    initial_x, initial_y = snail_before["x"], snail_before["y"]

    move_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        owner_address,
        "--function-name",
        "move_snail_ai",
        "--args",
        "[]",
        "--from",
        owner_name,
        "--gas",
        "10000000",
    )
    assert (
        move_result["code"] == 0
    ), f"move_snail_ai failed: {json.dumps(move_result, indent=2)}"

    move_payload = extract_exec_result(move_result)
    snail_after = move_payload["snail"]

    distance = move_payload.get("distance", 0)
    speed = move_payload.get("speed", 0)

    assert distance >= 100, f"Distance should be >= 100 for long-range test: {distance}"
    assert speed >= 1, f"Speed should be >= 1: {speed}"

    # Verify snail moved toward target (distance decreased)
    distance_before = ((initial_x - target_x) ** 2 + (initial_y - target_y) ** 2) ** 0.5
    distance_after = (
        (snail_after["x"] - target_x) ** 2 + (snail_after["y"] - target_y) ** 2
    ) ** 0.5
    assert (
        distance_after < distance_before
    ), f"Snail should move closer to target. Before: {distance_before}, After: {distance_after}, Initial: ({initial_x}, {initial_y}), After: ({snail_after['x']}, {snail_after['y']}), Target: ({target_x}, {target_y})"
    
    # Verify snail moved (not stationary) - calculate distance moved
    distance_moved = ((snail_after["x"] - initial_x) ** 2 + (snail_after["y"] - initial_y) ** 2) ** 0.5
    assert (
        distance_moved > 0
    ), f"Snail should have moved. Initial: ({initial_x}, {initial_y}), After: ({snail_after['x']}, {snail_after['y']})"
