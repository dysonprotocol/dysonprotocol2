import json

from tests.examples.rps.utils import (
    _get_block_height,
    deploy_script,
    exec_initialize_game,
    exec_move_piece,
    exec_spawn_piece,
    set_cell,
    set_game_state,
    set_piece_direct,
    set_piece_energy,
    set_player_record,
    wait_for_next_block,
)


def test_combat_rock_beats_scissors(chainnet, generate_account):
    dysond_bin = chainnet[0]
    owner_name, owner_address = generate_account("combat_owner", faucet_amount=200)
    attacker_name, attacker_address = generate_account("combat_attacker", faucet_amount=200)
    victim_name, victim_address = generate_account("combat_victim", faucet_amount=200)

    deploy_script(dysond_bin, owner_name)
    exec_initialize_game(dysond_bin, owner_name, owner_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)
    
    # Place attacker at (0, 1) - rock type
    attacker_piece_id = 1
    attacker_piece = {
        "id": attacker_piece_id,
        "owner": attacker_address,
        "type": "rock",
        "x": 0,
        "y": 1,
        "energy": 0,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, attacker_piece_id, attacker_piece)
    set_cell(dysond_bin, owner_name, owner_address, 0, 1, {"piece_id": attacker_piece_id})
    
    # Place victim at (0, 0) - scissors type
    victim_piece_id = 2
    victim_piece = {
        "id": victim_piece_id,
        "owner": victim_address,
        "type": "scissors",
        "x": 0,
        "y": 0,
        "energy": 150,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 5,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, victim_piece_id, victim_piece)
    set_cell(dysond_bin, owner_name, owner_address, 0, 0, {"piece_id": victim_piece_id})
    
    # Update game state
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
    attacker_record = {
        "pieces": [attacker_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, attacker_address, attacker_record)
    
    victim_record = {
        "pieces": [victim_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, victim_address, victim_record)
    
    wait_for_next_block(dysond_bin, block_height)

    combat_move = exec_move_piece(
        dysond_bin,
        attacker_name,
        owner_address,
        attacker_piece_id,
        0,
        0,
        gas="12000000",
    )
    combat = combat_move["combat"]

    assert combat["status"] == "victory", f"Combat status: {json.dumps(combat, indent=2)}"
    assert (
        combat["victim"]["removed"] is True
    ), f"Victim not removed: {json.dumps(combat, indent=2)}"

    attacker_after = combat_move["piece"]
    assert attacker_after["energy"] == 50, f"Attacker energy incorrect: {json.dumps(attacker_after, indent=2)}"
    assert (
        attacker_after["x"] == 0 and attacker_after["y"] == 0
    ), f"Attacker position incorrect: {json.dumps(attacker_after, indent=2)}"

    destination_cell = combat_move["grid"]["to"]["value"]
    assert (
        destination_cell["piece_id"] == attacker_piece_id
    ), f"Destination cell mismatch: {json.dumps(destination_cell, indent=2)}"

    distribution = combat["distribution"]
    assert distribution["attacker"] == 50, f"Attacker reward incorrect: {json.dumps(distribution, indent=2)}"
    assert distribution["market"] == 40, f"Market share incorrect: {json.dumps(distribution, indent=2)}"
    assert distribution["grid"] == 30, f"Grid share incorrect: {json.dumps(distribution, indent=2)}"
    assert distribution["burn"] == 30, f"Burn share incorrect: {json.dumps(distribution, indent=2)}"

    energy_drop = combat["energy_drop"]
    drop_query = dysond_bin(
        "query",
        "storage",
        "get",
        owner_address,
        "--index",
        energy_drop["index"],
    )
    drop_cell = json.loads(drop_query["entry"]["data"])
    assert (
        drop_cell["energy"] == 30
    ), f"Grid drop incorrect: {json.dumps(drop_cell, indent=2)}"

    state_snapshot = combat["state"]
    assert (
        state_snapshot["pending_market_energy"] == 40
    ), f"Market energy tracking wrong: {json.dumps(state_snapshot, indent=2)}"
    assert (
        state_snapshot["pending_grid_energy"] == 0
    ), f"Grid energy tracking wrong: {json.dumps(state_snapshot, indent=2)}"
    assert (
        state_snapshot["total_pieces"] == 1
    ), f"Total pieces mismatch: {json.dumps(state_snapshot, indent=2)}"
    assert (
        state_snapshot["total_energy_circulation"] == 0
    ), f"Energy circulation mismatch: {json.dumps(state_snapshot, indent=2)}"

    attacker_stats_query = dysond_bin(
        "query",
        "storage",
        "get",
        owner_address,
        "--index",
        f"game/players/{attacker_address}",
    )
    attacker_stats = json.loads(attacker_stats_query["entry"]["data"])
    assert attacker_stats["total_kills"] == 1, f"Attacker stats incorrect: {json.dumps(attacker_stats, indent=2)}"
    assert attacker_piece_id in attacker_stats["pieces"], f"Attacker pieces incorrect: {json.dumps(attacker_stats, indent=2)}"

    victim_stats_query = dysond_bin(
        "query",
        "storage",
        "get",
        owner_address,
        "--index",
        f"game/players/{victim_address}",
    )
    victim_stats = json.loads(victim_stats_query["entry"]["data"])
    assert victim_stats["total_deaths"] == 1, f"Victim stats incorrect: {json.dumps(victim_stats, indent=2)}"
    assert victim_piece_id not in victim_stats["pieces"], f"Victim pieces incorrect: {json.dumps(victim_stats, indent=2)}"


def test_combat_paper_beats_rock(chainnet, generate_account):
    dysond_bin = chainnet[0]
    owner_name, owner_address = generate_account("combat_owner_pr", faucet_amount=200)
    attacker_name, attacker_address = generate_account("combat_attacker_pr", faucet_amount=200)
    victim_name, victim_address = generate_account("combat_victim_pr", faucet_amount=200)

    deploy_script(dysond_bin, owner_name)
    exec_initialize_game(dysond_bin, owner_name, owner_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)
    
    # Place attacker at (0, 1) - paper type
    attacker_piece_id = 1
    attacker_piece = {
        "id": attacker_piece_id,
        "owner": attacker_address,
        "type": "paper",
        "x": 0,
        "y": 1,
        "energy": 0,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, attacker_piece_id, attacker_piece)
    set_cell(dysond_bin, owner_name, owner_address, 0, 1, {"piece_id": attacker_piece_id})
    
    # Place victim at (0, 0) - rock type
    victim_piece_id = 2
    victim_piece = {
        "id": victim_piece_id,
        "owner": victim_address,
        "type": "rock",
        "x": 0,
        "y": 0,
        "energy": 100,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 5,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, victim_piece_id, victim_piece)
    set_cell(dysond_bin, owner_name, owner_address, 0, 0, {"piece_id": victim_piece_id})
    
    # Update game state
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
    attacker_record = {
        "pieces": [attacker_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, attacker_address, attacker_record)
    
    victim_record = {
        "pieces": [victim_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, victim_address, victim_record)
    
    wait_for_next_block(dysond_bin, block_height)

    combat_move = exec_move_piece(
        dysond_bin,
        attacker_name,
        owner_address,
        attacker_piece_id,
        0,
        0,
        gas="12000000",
    )
    combat = combat_move["combat"]

    assert combat["status"] == "victory", f"Combat status: {json.dumps(combat, indent=2)}"
    assert (
        combat["victim"]["removed"] is True
    ), f"Victim not removed: {json.dumps(combat, indent=2)}"

    distribution = combat["distribution"]
    assert distribution["attacker"] == 50, f"Attacker reward incorrect: {json.dumps(distribution, indent=2)}"
    assert distribution["market"] == 20, f"Market share incorrect: {json.dumps(distribution, indent=2)}"
    assert distribution["grid"] == 15, f"Grid share incorrect: {json.dumps(distribution, indent=2)}"
    assert distribution["burn"] == 15, f"Burn share incorrect: {json.dumps(distribution, indent=2)}"


def test_combat_scissors_beats_paper(chainnet, generate_account):
    dysond_bin = chainnet[0]
    owner_name, owner_address = generate_account("combat_owner_sp", faucet_amount=200)
    attacker_name, attacker_address = generate_account("combat_attacker_sp", faucet_amount=200)
    victim_name, victim_address = generate_account("combat_victim_sp", faucet_amount=200)

    deploy_script(dysond_bin, owner_name)
    exec_initialize_game(dysond_bin, owner_name, owner_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)
    
    # Place attacker at (0, 1) - scissors type
    attacker_piece_id = 1
    attacker_piece = {
        "id": attacker_piece_id,
        "owner": attacker_address,
        "type": "scissors",
        "x": 0,
        "y": 1,
        "energy": 0,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, attacker_piece_id, attacker_piece)
    set_cell(dysond_bin, owner_name, owner_address, 0, 1, {"piece_id": attacker_piece_id})
    
    # Place victim at (0, 0) - paper type
    victim_piece_id = 2
    victim_piece = {
        "id": victim_piece_id,
        "owner": victim_address,
        "type": "paper",
        "x": 0,
        "y": 0,
        "energy": 90,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 5,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, victim_piece_id, victim_piece)
    set_cell(dysond_bin, owner_name, owner_address, 0, 0, {"piece_id": victim_piece_id})
    
    # Update game state
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
    attacker_record = {
        "pieces": [attacker_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, attacker_address, attacker_record)
    
    victim_record = {
        "pieces": [victim_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, victim_address, victim_record)
    
    wait_for_next_block(dysond_bin, block_height)

    combat_move = exec_move_piece(
        dysond_bin,
        attacker_name,
        owner_address,
        attacker_piece_id,
        0,
        0,
        gas="12000000",
    )
    combat = combat_move["combat"]

    assert combat["status"] == "victory", f"Combat status: {json.dumps(combat, indent=2)}"
    assert (
        combat["victim"]["removed"] is True
    ), f"Victim not removed: {json.dumps(combat, indent=2)}"

    distribution = combat["distribution"]
    assert distribution["attacker"] == 50, f"Attacker reward incorrect: {json.dumps(distribution, indent=2)}"
    assert distribution["market"] == 16, f"Market share incorrect: {json.dumps(distribution, indent=2)}"
    assert distribution["grid"] == 12, f"Grid share incorrect: {json.dumps(distribution, indent=2)}"
    assert distribution["burn"] == 12, f"Burn share incorrect: {json.dumps(distribution, indent=2)}"


def test_combat_invalid_attack_fails(chainnet, generate_account):
    dysond_bin = chainnet[0]
    owner_name, owner_address = generate_account("combat_owner_fail", faucet_amount=200)
    attacker_name, attacker_address = generate_account("combat_attacker_fail", faucet_amount=200)
    victim_name, victim_address = generate_account("combat_victim_fail", faucet_amount=200)

    deploy_script(dysond_bin, owner_name)
    exec_initialize_game(dysond_bin, owner_name, owner_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)
    
    # Place attacker at (0, 1) - rock type (cannot defeat paper)
    attacker_piece_id = 1
    attacker_piece = {
        "id": attacker_piece_id,
        "owner": attacker_address,
        "type": "rock",
        "x": 0,
        "y": 1,
        "energy": 0,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, attacker_piece_id, attacker_piece)
    set_cell(dysond_bin, owner_name, owner_address, 0, 1, {"piece_id": attacker_piece_id})
    
    # Place victim at (0, 0) - paper type (beats rock)
    victim_piece_id = 2
    victim_piece = {
        "id": victim_piece_id,
        "owner": victim_address,
        "type": "paper",
        "x": 0,
        "y": 0,
        "energy": 100,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 5,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, victim_piece_id, victim_piece)
    set_cell(dysond_bin, owner_name, owner_address, 0, 0, {"piece_id": victim_piece_id})
    
    # Update game state
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
    attacker_record = {
        "pieces": [attacker_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, attacker_address, attacker_record)
    
    victim_record = {
        "pieces": [victim_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, victim_address, victim_record)
    
    wait_for_next_block(dysond_bin, block_height)

    failing_args = json.dumps([attacker_piece_id, 0, 0])
    failing_move = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        owner_address,
        "--function-name",
        "move_piece",
        "--args",
        failing_args,
        "--from",
        attacker_name,
        "--gas",
        "3500000",
    )
    assert failing_move["code"] != 0, f"Expected combat failure: {json.dumps(failing_move, indent=2)}"
    assert (
        "cannot defeat victim type" in failing_move["raw_log"].lower()
    ), f"Missing defeat error: {failing_move['raw_log']}"

    victim_cell_query = dysond_bin(
        "query",
        "storage",
        "get",
        owner_address,
        "--index",
        f"game/grid/0/0",
    )
    victim_cell = json.loads(victim_cell_query["entry"]["data"])
    assert (
        victim_cell["piece_id"] == victim_piece_id
    ), f"Victim displaced unexpectedly: {json.dumps(victim_cell, indent=2)}"


def test_combat_energy_transfer(chainnet, generate_account):
    """Test that attacker gains exactly 50 energy from victim"""
    dysond_bin = chainnet[0]
    owner_name, owner_address = generate_account("combat_energy_owner", faucet_amount=200)
    attacker_name, attacker_address = generate_account("combat_energy_attacker", faucet_amount=200)
    victim_name, victim_address = generate_account("combat_energy_victim", faucet_amount=200)

    deploy_script(dysond_bin, owner_name)
    exec_initialize_game(dysond_bin, owner_name, owner_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)
    
    # Place attacker at (0, 1) - rock type
    attacker_piece_id = 1
    attacker_initial_energy = 0
    attacker_piece = {
        "id": attacker_piece_id,
        "owner": attacker_address,
        "type": "rock",
        "x": 0,
        "y": 1,
        "energy": attacker_initial_energy,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, attacker_piece_id, attacker_piece)
    set_cell(dysond_bin, owner_name, owner_address, 0, 1, {"piece_id": attacker_piece_id})
    
    # Place victim at (0, 0) - scissors type with 200 energy
    victim_piece_id = 2
    victim_piece = {
        "id": victim_piece_id,
        "owner": victim_address,
        "type": "scissors",
        "x": 0,
        "y": 0,
        "energy": 200,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 5,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, victim_piece_id, victim_piece)
    set_cell(dysond_bin, owner_name, owner_address, 0, 0, {"piece_id": victim_piece_id})
    
    # Update game state
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
    attacker_record = {
        "pieces": [attacker_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, attacker_address, attacker_record)
    
    victim_record = {
        "pieces": [victim_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, victim_address, victim_record)
    
    wait_for_next_block(dysond_bin, block_height)

    combat_move = exec_move_piece(
        dysond_bin,
        attacker_name,
        owner_address,
        attacker_piece_id,
        0,
        0,
        gas="12000000",
    )
    combat = combat_move["combat"]
    attacker_after = combat_move["piece"]

    assert (
        attacker_after["energy"] == attacker_initial_energy + 50
    ), f"Attacker should gain 50 energy. Initial: {attacker_initial_energy}, After: {attacker_after['energy']}"
    assert (
        combat["distribution"]["attacker"] == 50
    ), f"Combat distribution attacker reward should be 50: {json.dumps(combat['distribution'], indent=2)}"


def test_combat_energy_distribution(chainnet, generate_account):
    """Test that victim energy is distributed correctly: 50 to attacker, 40% market, 30% grid, 30% burn"""
    dysond_bin = chainnet[0]
    owner_name, owner_address = generate_account("combat_dist_owner", faucet_amount=200)
    attacker_name, attacker_address = generate_account("combat_dist_attacker", faucet_amount=200)
    victim_name, victim_address = generate_account("combat_dist_victim", faucet_amount=200)

    deploy_script(dysond_bin, owner_name)
    exec_initialize_game(dysond_bin, owner_name, owner_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)
    
    # Place attacker at (0, 1) - rock type
    attacker_piece_id = 1
    attacker_piece = {
        "id": attacker_piece_id,
        "owner": attacker_address,
        "type": "rock",
        "x": 0,
        "y": 1,
        "energy": 0,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, attacker_piece_id, attacker_piece)
    set_cell(dysond_bin, owner_name, owner_address, 0, 1, {"piece_id": attacker_piece_id})
    
    # Place victim at (0, 0) - scissors type with 200 energy
    victim_piece_id = 2
    victim_energy = 200
    victim_piece = {
        "id": victim_piece_id,
        "owner": victim_address,
        "type": "scissors",
        "x": 0,
        "y": 0,
        "energy": victim_energy,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 5,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, victim_piece_id, victim_piece)
    set_cell(dysond_bin, owner_name, owner_address, 0, 0, {"piece_id": victim_piece_id})
    
    # Update game state
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
    attacker_record = {
        "pieces": [attacker_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, attacker_address, attacker_record)
    
    victim_record = {
        "pieces": [victim_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, victim_address, victim_record)
    
    wait_for_next_block(dysond_bin, block_height)

    combat_move = exec_move_piece(
        dysond_bin,
        attacker_name,
        owner_address,
        attacker_piece_id,
        0,
        0,
        gas="12000000",
    )
    combat = combat_move["combat"]
    distribution = combat["distribution"]

    remainder = victim_energy - 50
    expected_market = remainder * 40 // 100
    expected_grid = remainder * 30 // 100
    expected_burn = remainder - expected_market - expected_grid

    assert (
        distribution["attacker"] == 50
    ), f"Attacker should get 50: {json.dumps(distribution, indent=2)}"
    assert (
        distribution["market"] == expected_market
    ), f"Market should get 40% of remainder ({expected_market}): {json.dumps(distribution, indent=2)}"
    assert (
        distribution["grid"] == expected_grid
    ), f"Grid should get 30% of remainder ({expected_grid}): {json.dumps(distribution, indent=2)}"
    assert (
        distribution["burn"] == expected_burn
    ), f"Burn should get remaining ({expected_burn}): {json.dumps(distribution, indent=2)}"

    state_snapshot = combat["state"]
    assert (
        state_snapshot["pending_market_energy"] == expected_market
    ), f"State should track market energy: {json.dumps(state_snapshot, indent=2)}"


def test_combat_in_movement_flow(chainnet, generate_account):
    """Test that combat is triggered automatically when moving onto an enemy"""
    dysond_bin = chainnet[0]
    owner_name, owner_address = generate_account("combat_flow_owner", faucet_amount=200)
    attacker_name, attacker_address = generate_account("combat_flow_attacker", faucet_amount=200)
    victim_name, victim_address = generate_account("combat_flow_victim", faucet_amount=200)

    deploy_script(dysond_bin, owner_name)
    exec_initialize_game(dysond_bin, owner_name, owner_address)

    # Set up deterministic scenario using direct storage
    block_height = _get_block_height(dysond_bin)
    
    # Place attacker at (0, 1) - rock type
    attacker_piece_id = 1
    attacker_piece = {
        "id": attacker_piece_id,
        "owner": attacker_address,
        "type": "rock",
        "x": 0,
        "y": 1,
        "energy": 0,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 10,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, attacker_piece_id, attacker_piece)
    set_cell(dysond_bin, owner_name, owner_address, 0, 1, {"piece_id": attacker_piece_id})
    
    # Place victim at (0, 0) - scissors type with 100 energy
    victim_piece_id = 2
    victim_piece = {
        "id": victim_piece_id,
        "owner": victim_address,
        "type": "scissors",
        "x": 0,
        "y": 0,
        "energy": 100,
        "last_action_block": block_height - 1,
        "is_npc": False,
        "spawn_block": block_height - 5,
    }
    set_piece_direct(dysond_bin, owner_name, owner_address, victim_piece_id, victim_piece)
    set_cell(dysond_bin, owner_name, owner_address, 0, 0, {"piece_id": victim_piece_id})
    
    # Update game state
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
    attacker_record = {
        "pieces": [attacker_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, attacker_address, attacker_record)
    
    victim_record = {
        "pieces": [victim_piece_id],
        "total_kills": 0,
        "total_deaths": 0,
    }
    set_player_record(dysond_bin, owner_name, owner_address, victim_address, victim_record)
    
    wait_for_next_block(dysond_bin, block_height)

    combat_move = exec_move_piece(
        dysond_bin,
        attacker_name,
        owner_address,
        attacker_piece_id,
        0,
        0,
        gas="12000000",
    )

    assert (
        "combat" in combat_move
    ), f"Combat should be triggered in movement: {json.dumps(combat_move, indent=2)}"
    assert (
        combat_move["combat"]["status"] == "victory"
    ), f"Combat should be victorious: {json.dumps(combat_move['combat'], indent=2)}"
    assert (
        combat_move["piece"]["x"] == 0 and combat_move["piece"]["y"] == 0
    ), f"Attacker should land on victim's cell: {json.dumps(combat_move['piece'], indent=2)}"
    assert (
        combat_move["combat"]["victim"]["removed"] is True
    ), f"Victim should be removed: {json.dumps(combat_move['combat'], indent=2)}"

