import json

from tests.examples.rps.utils import (
    deploy_script,
    exec_initialize_game,
    exec_move_piece,
    exec_spawn_piece,
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


def test_move_piece_king_move_success(chainnet, generate_account):
    dysond_bin = chainnet[0]
    account_name, account_address = generate_account("rps_move", faucet_amount=200)

    deploy_script(dysond_bin, account_name)
    exec_initialize_game(dysond_bin, account_name, account_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)

    # Place piece at (0, 0) - can move to (0, 1) as king move
    piece_id = 1
    piece = {
        "id": piece_id,
        "owner": account_address,
        "type": "rock",
        "x": 0,
        "y": 0,
        "energy": 0,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(dysond_bin, account_name, account_address, piece_id, piece)
    set_cell(dysond_bin, account_name, account_address, 0, 0, {"piece_id": piece_id})

    # Update game state
    state = {
        "total_pieces": 1,
        "total_energy_circulation": 0,
        "pending_market_energy": 0,
        "pending_grid_energy": 0,
        "last_updated_block": block_height - 1,
        "next_piece_id": 2,
    }
    set_game_state(dysond_bin, account_name, account_address, state)

    # Update player record
    player_record = {
        "pieces": [piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(
        dysond_bin, account_name, account_address, account_address, player_record
    )

    wait_for_next_block(dysond_bin, block_height)

    move_payload = exec_move_piece(
        dysond_bin, account_name, account_address, piece_id, 0, 1
    )
    moved_piece = move_payload["piece"]
    grid_info = move_payload["grid"]

    assert (
        moved_piece["x"] == 0 and moved_piece["y"] == 1
    ), f"Piece position incorrect: {json.dumps(moved_piece, indent=2)}"
    assert (
        move_payload["cost"] == 0
    ), f"King move should cost 0: {json.dumps(move_payload, indent=2)}"
    assert (
        grid_info["from"]["value"]["piece_id"] is None
    ), f"Origin cell not cleared: {json.dumps(grid_info, indent=2)}"
    assert (
        grid_info["to"]["value"]["piece_id"] == piece_id
    ), f"Destination not updated: {json.dumps(grid_info, indent=2)}"
    assert (
        move_payload["state"]["last_updated_block"] == moved_piece["last_action_block"]
    ), f"State not updated: {json.dumps(move_payload['state'], indent=2)}"

    stored_piece = dysond_bin(
        "query",
        "storage",
        "get",
        account_address,
        "--index",
        f"game/pieces/{piece_id:010d}",
    )
    stored_piece_data = json.loads(stored_piece["entry"]["data"])
    assert (
        stored_piece_data == moved_piece
    ), f"Stored piece mismatch. Expected: {json.dumps(moved_piece, indent=2)} Stored: {json.dumps(stored_piece_data, indent=2)}"


def test_move_piece_rate_limit_and_target_occupied(chainnet, generate_account):
    dysond_bin = chainnet[0]
    account_name, account_address = generate_account(
        "rps_move_limit", faucet_amount=200
    )

    deploy_script(dysond_bin, account_name)
    exec_initialize_game(dysond_bin, account_name, account_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)

    # Place first piece at (0, 0)
    first_piece_id = 1
    first_piece = {
        "id": first_piece_id,
        "owner": account_address,
        "type": "rock",
        "x": 0,
        "y": 0,
        "energy": 0,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(
        dysond_bin, account_name, account_address, first_piece_id, first_piece
    )
    set_cell(
        dysond_bin, account_name, account_address, 0, 0, {"piece_id": first_piece_id}
    )

    # Update game state
    state = {
        "total_pieces": 1,
        "total_energy_circulation": 0,
        "pending_market_energy": 0,
        "pending_grid_energy": 0,
        "last_updated_block": block_height - 1,
        "next_piece_id": 2,
    }
    set_game_state(dysond_bin, account_name, account_address, state)

    # Update player record
    player_record = {
        "pieces": [first_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(
        dysond_bin, account_name, account_address, account_address, player_record
    )

    wait_for_next_block(dysond_bin, block_height)

    # Move to adjacent cell (king move) - from (0, 0) to (1, 0)
    target_x = 1
    target_y = 0
    move_payload = exec_move_piece(
        dysond_bin, account_name, account_address, first_piece_id, target_x, target_y
    )

    wait_for_next_block(dysond_bin, move_payload["piece"]["last_action_block"])

    # Test rate limiting - try to move twice in same block
    # First move to another adjacent cell, then to a third cell
    next_x = target_x + 1  # (2, 0)
    next_y = target_y
    final_x = next_x + 1  # (3, 0)
    final_y = next_y

    double_move_code = (
        "def double_move(piece_id, x1, y1, x2, y2):\n"
        "    move_piece(piece_id, x1, y1)\n"
        "    move_piece(piece_id, x2, y2)\n"
    )
    double_move_args = json.dumps([first_piece_id, next_x, next_y, final_x, final_y])
    double_move = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        account_address,
        "--function-name",
        "double_move",
        "--args",
        double_move_args,
        "--extra-code",
        double_move_code,
        "--from",
        account_name,
        "--gas",
        "10000000",
    )
    assert (
        double_move["code"] != 0
    ), f"Rate limit should fail: {json.dumps(double_move, indent=2)}"
    assert (
        "acted this block" in double_move["raw_log"].lower()
    ), f"Missing rate limit error: {double_move['raw_log']}"

    piece_after_fail = dysond_bin(
        "query",
        "storage",
        "get",
        account_address,
        "--index",
        f"game/pieces/{first_piece_id:010d}",
    )
    piece_after_fail_data = json.loads(piece_after_fail["entry"]["data"])
    assert (
        piece_after_fail_data["x"] == target_x
        and piece_after_fail_data["y"] == target_y
    ), f"Piece position changed unexpectedly: {json.dumps(piece_after_fail_data, indent=2)}"

    wait_for_next_block(dysond_bin, piece_after_fail_data["last_action_block"])

    # Queen move: move 2 squares vertically (cost = 2² = 4)
    # Give piece enough energy for the queen move
    set_piece_energy(dysond_bin, account_name, account_address, first_piece_id, 10)
    wait_for_next_block(dysond_bin, piece_after_fail_data["last_action_block"])

    # Move from (1, 0) to (1, 2) - queen move vertically (cost = 2² = 4)
    queen_target_x = target_x  # 1
    queen_target_y = target_y + 2  # 2
    queen_payload = exec_move_piece(
        dysond_bin,
        account_name,
        account_address,
        first_piece_id,
        queen_target_x,
        queen_target_y,
    )
    assert (
        queen_payload["cost"] == 4
    ), f"Expected queen move cost 4: {json.dumps(queen_payload, indent=2)}"

    wait_for_next_block(dysond_bin, queen_payload["piece"]["last_action_block"])

    # Place second piece at (5, 0) using direct storage
    block_height_after_queen = _get_block_height(dysond_bin)
    second_piece_id = 2
    second_piece = {
        "id": second_piece_id,
        "owner": account_address,
        "type": "paper",
        "x": 5,
        "y": 0,
        "energy": 100,
        "last_action_block": block_height_after_queen - 1,
        "is_npc": False,
        "spawn_block": block_height_after_queen - 5,
    }
    set_piece_direct(
        dysond_bin, account_name, account_address, second_piece_id, second_piece
    )
    set_cell(
        dysond_bin, account_name, account_address, 5, 0, {"piece_id": second_piece_id}
    )

    # Update game state
    state_after_second = {
        "total_pieces": 2,
        "total_energy_circulation": 0,
        "pending_market_energy": 0,
        "pending_grid_energy": 0,
        "last_updated_block": block_height_after_queen - 1,
        "next_piece_id": 3,
    }
    set_game_state(dysond_bin, account_name, account_address, state_after_second)

    # Update player record
    player_record_after_second = {
        "pieces": [first_piece_id, second_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(
        dysond_bin,
        account_name,
        account_address,
        account_address,
        player_record_after_second,
    )

    wait_for_next_block(dysond_bin, block_height_after_queen)

    # Try to move second piece to same location as first piece (should fail - occupied)
    # First piece is now at queen_target_x, queen_target_y after the queen move
    # Move second piece closer using a queen move: move horizontally to same column as target
    # From (5, 0) to (1, 0) - horizontal queen move
    intermediate_move = exec_move_piece(
        dysond_bin,
        account_name,
        account_address,
        second_piece_id,
        queen_target_x,  # 1
        0,  # same y as second piece
    )
    wait_for_next_block(dysond_bin, intermediate_move["piece"]["last_action_block"])

    # Give second piece more energy for the final move attempt
    set_piece_energy(dysond_bin, account_name, account_address, second_piece_id, 100)
    wait_for_next_block(dysond_bin, intermediate_move["piece"]["last_action_block"])

    # Now try to move vertically to the target location (should fail - occupied)
    occupied_move_args = json.dumps([second_piece_id, queen_target_x, queen_target_y])
    occupied_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        account_address,
        "--function-name",
        "move_piece",
        "--args",
        occupied_move_args,
        "--from",
        account_name,
        "--gas",
        "3500000",
    )
    assert (
        occupied_result["code"] != 0
    ), f"Occupied cell move should fail: {json.dumps(occupied_result, indent=2)}"
    assert (
        "target cell occupied" in occupied_result["raw_log"].lower()
    ), f"Missing occupied error: {occupied_result['raw_log']}"


def test_move_piece_invalid_direction(chainnet, generate_account):
    dysond_bin = chainnet[0]
    account_name, account_address = generate_account(
        "rps_move_invalid", faucet_amount=200
    )

    deploy_script(dysond_bin, account_name)
    exec_initialize_game(dysond_bin, account_name, account_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)

    # Place piece at (0, 0) - moving to (1, 2) is invalid (not adjacent or straight line)
    piece_id = 1
    piece = {
        "id": piece_id,
        "owner": account_address,
        "type": "rock",
        "x": 0,
        "y": 0,
        "energy": 0,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(dysond_bin, account_name, account_address, piece_id, piece)
    set_cell(dysond_bin, account_name, account_address, 0, 0, {"piece_id": piece_id})

    # Update game state
    state = {
        "total_pieces": 1,
        "total_energy_circulation": 0,
        "pending_market_energy": 0,
        "pending_grid_energy": 0,
        "last_updated_block": block_height - 1,
        "next_piece_id": 2,
    }
    set_game_state(dysond_bin, account_name, account_address, state)

    # Update player record
    player_record = {
        "pieces": [piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(
        dysond_bin, account_name, account_address, account_address, player_record
    )

    wait_for_next_block(dysond_bin, block_height)

    invalid_args = json.dumps([piece_id, 1, 2])
    invalid_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        account_address,
        "--function-name",
        "move_piece",
        "--args",
        invalid_args,
        "--from",
        account_name,
        "--gas",
        "3500000",
    )
    assert (
        invalid_result["code"] != 0
    ), f"Invalid move should fail: {json.dumps(invalid_result, indent=2)}"
    assert (
        "invalid move" in invalid_result["raw_log"].lower()
    ), f"Missing invalid move error: {invalid_result['raw_log']}"


def test_move_piece_wrong_owner(chainnet, generate_account):
    dysond_bin = chainnet[0]
    owner_name, owner_address = generate_account("rps_move_owner", faucet_amount=200)
    intruder_name, intruder_address = generate_account(
        "rps_move_intruder", faucet_amount=200
    )

    deploy_script(dysond_bin, owner_name)
    exec_initialize_game(dysond_bin, owner_name, owner_address)
    spawn_payload = exec_spawn_piece(dysond_bin, owner_name, owner_address)
    piece = spawn_payload["piece"]

    wait_for_next_block(dysond_bin, piece["last_action_block"])

    move_args = json.dumps([piece["id"], 0, 1])
    move_attempt = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        owner_address,
        "--function-name",
        "move_piece",
        "--args",
        move_args,
        "--from",
        intruder_name,
        "--gas",
        "3500000",
    )
    assert (
        move_attempt["code"] != 0
    ), f"Non-owner move should fail: {json.dumps(move_attempt, indent=2)}"
    assert (
        "not owner" in move_attempt["raw_log"].lower()
    ), f"Expected not owner error: {move_attempt['raw_log']}"

    stored_piece = dysond_bin(
        "query",
        "storage",
        "get",
        owner_address,
        "--index",
        f"game/pieces/{piece['id']:010d}",
    )
    stored_piece_data = json.loads(stored_piece["entry"]["data"])
    assert (
        stored_piece_data["x"] == piece["x"] and stored_piece_data["y"] == piece["y"]
    ), (
        "Piece moved despite failure. Original: "
        f"({piece['x']}, {piece['y']}), Stored: ({stored_piece_data['x']}, {stored_piece_data['y']})"
    )


def test_move_piece_queen_energy_deduction(chainnet, generate_account):
    dysond_bin = chainnet[0]
    account_name, account_address = generate_account(
        "rps_move_energy", faucet_amount=200
    )

    deploy_script(dysond_bin, account_name)
    exec_initialize_game(dysond_bin, account_name, account_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)

    # Place piece at (0, 0) with 100 energy - can move to (0, 3) as queen move (cost = 3² = 9)
    piece_id = 1
    piece = {
        "id": piece_id,
        "owner": account_address,
        "type": "rock",
        "x": 0,
        "y": 0,
        "energy": 100,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(dysond_bin, account_name, account_address, piece_id, piece)
    set_cell(dysond_bin, account_name, account_address, 0, 0, {"piece_id": piece_id})

    # Update game state
    state = {
        "total_pieces": 1,
        "total_energy_circulation": 0,
        "pending_market_energy": 0,
        "pending_grid_energy": 0,
        "last_updated_block": block_height - 1,
        "next_piece_id": 2,
    }
    set_game_state(dysond_bin, account_name, account_address, state)

    # Update player record
    player_record = {
        "pieces": [piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(
        dysond_bin, account_name, account_address, account_address, player_record
    )

    wait_for_next_block(dysond_bin, block_height)

    move_payload = exec_move_piece(
        dysond_bin, account_name, account_address, piece_id, 0, 3, gas="12000000"
    )
    moved_piece = move_payload["piece"]
    state_snapshot = move_payload["state"]

    assert (
        moved_piece["energy"] == 91
    ), f"Energy deduction incorrect: {json.dumps(moved_piece, indent=2)}"
    assert (
        state_snapshot["pending_market_energy"] == 9
    ), f"Pending market energy incorrect: {json.dumps(state_snapshot, indent=2)}"

    stored_piece = dysond_bin(
        "query",
        "storage",
        "get",
        account_address,
        "--index",
        f"game/pieces/{piece_id:010d}",
    )
    stored_piece_data = json.loads(stored_piece["entry"]["data"])
    assert (
        stored_piece_data["energy"] == 91
    ), f"Persistent energy mismatch: {json.dumps(stored_piece_data, indent=2)}"


def test_move_piece_insufficient_energy(chainnet, generate_account):
    dysond_bin = chainnet[0]
    account_name, account_address = generate_account(
        "rps_move_no_energy", faucet_amount=200
    )

    deploy_script(dysond_bin, account_name)
    exec_initialize_game(dysond_bin, account_name, account_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)

    # Place piece at (0, 0) with 1 energy - can move to (0, 5) as queen move (cost = 5² = 25, but only has 1 energy)
    piece_id = 1
    piece = {
        "id": piece_id,
        "owner": account_address,
        "type": "rock",
        "x": 0,
        "y": 0,
        "energy": 1,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(dysond_bin, account_name, account_address, piece_id, piece)
    set_cell(dysond_bin, account_name, account_address, 0, 0, {"piece_id": piece_id})

    # Update game state
    state = {
        "total_pieces": 1,
        "total_energy_circulation": 0,
        "pending_market_energy": 0,
        "pending_grid_energy": 0,
        "last_updated_block": block_height - 1,
        "next_piece_id": 2,
    }
    set_game_state(dysond_bin, account_name, account_address, state)

    # Update player record
    player_record = {
        "pieces": [piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(
        dysond_bin, account_name, account_address, account_address, player_record
    )

    wait_for_next_block(dysond_bin, block_height)

    insufficient_args = json.dumps([piece_id, 0, 5])
    insufficient_move = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        account_address,
        "--function-name",
        "move_piece",
        "--args",
        insufficient_args,
        "--from",
        account_name,
        "--gas",
        "12000000",
    )
    assert (
        insufficient_move["code"] != 0
    ), f"Movement should have failed: {json.dumps(insufficient_move, indent=2)}"
    assert (
        "insufficient energy for movement" in insufficient_move["raw_log"].lower()
    ), f"Expected insufficient energy error: {insufficient_move['raw_log']}"

    stored_piece = dysond_bin(
        "query",
        "storage",
        "get",
        account_address,
        "--index",
        f"game/pieces/{piece_id:010d}",
    )
    stored_piece_data = json.loads(stored_piece["entry"]["data"])
    assert (
        stored_piece_data["energy"] == 1
    ), f"Energy changed despite failure: {json.dumps(stored_piece_data, indent=2)}"


def test_energy_pickup_collection(chainnet, generate_account):
    """Test that moving onto an energy piece collects it automatically"""
    dysond_bin = chainnet[0]
    owner_name, owner_address = generate_account(
        "energy_pickup_owner", faucet_amount=200
    )
    collector_name, collector_address = generate_account(
        "energy_pickup_collector", faucet_amount=200
    )

    deploy_script(dysond_bin, owner_name)
    exec_initialize_game(dysond_bin, owner_name, owner_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)

    # Create collector piece at (0, 0) with sufficient energy
    collector_id = 1
    collector_x = 0
    collector_y = 0
    collector_initial_energy = 1000
    collector_piece = {
        "id": collector_id,
        "owner": collector_address,
        "type": "paper",
        "x": collector_x,
        "y": collector_y,
        "energy": collector_initial_energy,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(
        dysond_bin, owner_name, owner_address, collector_id, collector_piece
    )
    set_cell(
        dysond_bin,
        owner_name,
        owner_address,
        collector_x,
        collector_y,
        {"piece_id": collector_id},
    )

    # Create energy piece at (5, 0) - adjacent horizontally for easy collection
    energy_id = 2
    drop_x = 5
    drop_y = 0
    drop_energy = 50
    energy_piece = {
        "id": energy_id,
        "owner": None,
        "type": "energy",
        "x": drop_x,
        "y": drop_y,
        "energy": drop_energy,
        "last_action_block": block_height - 5,
        "is_npc": False,
        "spawn_block": block_height - 5,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, energy_id, energy_piece)
    set_cell(
        dysond_bin, owner_name, owner_address, drop_x, drop_y, {"piece_id": energy_id}
    )

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

    # Update player record
    player_record = {
        "pieces": [collector_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(
        dysond_bin, owner_name, owner_address, collector_address, player_record
    )

    wait_for_next_block(dysond_bin, block_height)

    # Move collector to energy drop location (simple horizontal move)
    collection_move = exec_move_piece(
        dysond_bin,
        collector_name,
        owner_address,
        collector_id,
        drop_x,
        drop_y,
        gas="12000000",
    )

    # Verify collection happened
    assert (
        "collect" in collection_move
    ), f"Collection should happen: {json.dumps(collection_move, indent=2)}"

    collect_result = collection_move["collect"]
    assert (
        collect_result["energy_gained"] == drop_energy
    ), f"Energy gained incorrect: {json.dumps(collect_result, indent=2)}"

    collector_after = collection_move["piece"]
    movement_cost = collection_move["cost"]
    expected_energy = collector_initial_energy - movement_cost + drop_energy
    assert (
        collector_after["energy"] == expected_energy
    ), f"Collector energy incorrect. Initial: {collector_initial_energy}, Movement cost: {movement_cost}, Energy gained: {drop_energy}, Expected: {expected_energy}, Got: {collector_after['energy']}"

    # Verify energy piece was removed and collector is on the cell
    final_x = collector_after["x"]
    final_y = collector_after["y"]
    assert (
        final_x == drop_x and final_y == drop_y
    ), f"Collector should be at drop location ({drop_x}, {drop_y}), got ({final_x}, {final_y})"

    drop_cell_after = get_cell(dysond_bin, owner_address, final_x, final_y)
    assert (
        drop_cell_after["piece_id"] == collector_id
    ), f"Collector should be on cell, energy piece removed: {json.dumps(drop_cell_after, indent=2)}"

    # Verify energy piece was deleted
    piece_index = f"game/pieces/{energy_id:010d}"
    energy_piece_query = dysond_bin(
        "query",
        "storage",
        "get",
        owner_address,
        "--index",
        piece_index,
    )
    # When a storage entry doesn't exist, the query returns an error string
    assert isinstance(
        energy_piece_query, str
    ), f"Expected error string for deleted piece, got: {type(energy_piece_query)}"
    assert (
        "doesn't exist" in energy_piece_query
    ), f"Expected 'doesn't exist' error, got: {energy_piece_query}"
