"""
RPS Grid Battle - Dyson Protocol Game Script

A fully on-chain multiplayer Rock-Paper-Scissors battle game.

Phase 1: Core grid & movement (COMPLETED)
Phase 2: Combat & energy economics (IN PROGRESS)
Phase 3: Whaleswap integration (PENDING)
Phase 4: Optimization & features (PENDING)

See spec.md for complete game design.
"""

from typing import Any
import json
import math
import random
import datetime
from dys import (
    _msg,
    _query,
    get_attached_messages,
    get_block_info,
    get_executor_address,
    get_script_address,
)


# ============================================================================
# Configuration
# ============================================================================

JOIN_COST = 100
ATTACK_REWARD = 50
PAYMENT_DENOM = "udys"  # Phase 2: use udys. Phase 3: will use energy token denom

# Board boundaries (dynamic based on number of pieces)

# RPS type relationships
RPS_DEFEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}

# Snail constants
SNAIL_ID = 0  # Single persistent snail (special ID, always 0)
SNAIL_MOVE_BLOCKS = 1  # Snail moves once per block
HEARTBEAT_INTERVAL_BLOCKS = 10  # Heartbeat checks every 10 blocks


# ============================================================================
# Piece Model (Module-Level Functions)
# ============================================================================


def create_piece(
    piece_id: int,
    owner,
    piece_type: str,
    x: int,
    y: int,
    energy: int,
    last_action_block: int,
    is_npc: bool,
    spawn_block: int,
):
    """Create a piece dict with required fields"""
    return {
        "id": piece_id,
        "owner": owner,
        "type": piece_type,
        "x": x,
        "y": y,
        "energy": energy,
        "last_action_block": last_action_block,
        "is_npc": is_npc,
        "spawn_block": spawn_block,
    }


def create_player_piece(
    piece_id: int,
    owner: str,
    piece_type: str,
    x: int,
    y: int,
    energy: int,
    last_action_block: int,
    spawn_block: int,
):
    """Create a player piece (rock/paper/scissors)"""
    if piece_type not in ["rock", "paper", "scissors"]:
        raise ValueError("invalid piece_type for PlayerPiece")
    return create_piece(
        piece_id, owner, piece_type, x, y, energy, last_action_block, False, spawn_block
    )


def create_snail_piece(x: int, y: int, last_action_block: int, spawn_block: int):
    """Create the snail NPC piece"""
    return create_piece(
        SNAIL_ID, None, "snail", x, y, 999999, last_action_block, True, spawn_block
    )


def create_energy_piece(piece_id: int, x: int, y: int, energy: int, spawn_block: int):
    """Create an energy pickup piece (non-moving, collectible)"""
    return create_piece(
        piece_id, None, "energy", x, y, energy, spawn_block, False, spawn_block
    )


def piece_is_collectible(piece: dict) -> bool:
    """Check if piece is collectible"""
    return piece["type"] == "energy"


def piece_can_move(piece: dict) -> bool:
    """Check if piece can move"""
    piece_type = piece["type"]
    return piece_type in ["rock", "paper", "scissors", "snail"]


def piece_can_attack(piece: dict) -> bool:
    """Check if piece can attack"""
    piece_type = piece["type"]
    return piece_type in ["rock", "paper", "scissors", "snail"]


# ============================================================================
# Storage Helper Functions
# ============================================================================


def _get_storage(index: str):
    """Query storage by index"""
    result = _query(
        {
            "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
            "owner": get_script_address(),
            "index_prefix": index,
            "pagination": {"reverse": False, "limit": "1"},
        }
    )
    for entry in result["entries"]:
        if entry["index"] == index and "data" in entry:
            return json.loads(entry["data"])
    return None


def _set_storage(index: str, data: dict):
    """Update storage at index"""
    return _msg(
        {
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": get_script_address(),
            "index": index,
            "data": json.dumps(data),
        }
    )


def _delete_storage(indexes: list):
    """Delete storage entries"""
    return _msg(
        {
            "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
            "owner": get_script_address(),
            "indexes": indexes,
        }
    )


def get_piece(piece_id: int):
    """Get piece from storage"""
    return _get_storage(f"game/pieces/{piece_id:010d}")


def set_piece(piece_id: int, data: dict):
    """Set piece in storage"""
    return _set_storage(f"game/pieces/{piece_id:010d}", data)


def delete_piece(piece_id: int):
    """Delete piece from storage"""
    return _delete_storage([f"game/pieces/{piece_id:010d}"])


def find_oldest_player_piece():
    """
    Find the oldest player piece by querying pieces in index order.
    Bounded: queries with filter (is_npc==false) and limit=1.

    Piece IDs are zero-padded (block_height:010d, next_piece_id:010d) so
    lexicographic index ordering matches chronological spawn order. First piece
    in index order is the oldest player piece.

    Returns:
        Oldest player piece dict, or None if no players exist
    """
    result = _query(
        {
            "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
            "owner": get_script_address(),
            "index_prefix": "game/pieces/",
            "filter": "is_npc==false",
            "pagination": {"reverse": False, "limit": "1"},
        }
    )

    entries = result.get("entries", [])
    if len(entries) == 0:
        return None

    entry = entries[0]
    if "data" in entry:
        piece = json.loads(entry["data"])
        return piece

    return None


def get_cell(x: int, y: int) -> dict[str, Any] | None:
    """Get grid cell from storage"""
    return _get_storage(f"game/grid/{x}/{y}")


def set_cell(x: int, y: int, data: dict[str, Any]):
    """Set grid cell in storage"""
    return _set_storage(f"game/grid/{x}/{y}", data)


def get_board_bounds():
    """
    Get dynamic board boundaries based on number of pieces.

    Returns:
        tuple: (min_bound, max_bound) where:
        - min_bound = -1 * (10 + num_pieces)
        - max_bound = 10 + num_pieces
    """
    state = _get_storage("game/state")
    if state is None:
        num_pieces = 0
    else:
        num_pieces = state.get("total_pieces", 0)

    min_bound = -1 * (10 + num_pieces)
    max_bound = 10 + num_pieces
    return min_bound, max_bound


def _find_random_empty_cell(max_attempts: int = 20):
    """
    Find a random empty cell on the board for spawning.

    Args:
        max_attempts: Maximum number of random attempts before giving up

    Returns:
        tuple: (x, y) coordinates of empty cell, or (None, None) if not found
    """
    board_min, board_max = get_board_bounds()

    for attempt in range(max_attempts):
        x = random.randint(board_min, board_max)
        y = random.randint(board_min, board_max)

        cell = get_cell(x, y)
        if cell is None:
            cell = {"piece_id": None}

        piece_id_value = cell.get("piece_id")
        if piece_id_value is None:
            return (x, y)

    return (None, None)


def _is_excluded_position(x: int, y: int, excluded: list):
    if excluded is None:
        return False
    index = 0
    size = len(excluded)
    while index < size:
        position = excluded[index]
        if position[0] == x and position[1] == y:
            return True
        index += 1
    return False


def _place_energy_on_grid(
    amount: int,
    excluded: list,
    center_x: int | None = None,
    center_y: int | None = None,
):
    """
    Place energy as EnergyPiece in rectangle from (0,0) to combat location
    Tries 5 positions in rectangle, then falls back to random board placement
    """
    if amount <= 0:
        return None

    block_info = get_block_info()
    block_height = block_info["height"]
    state = _get_storage("game/state")
    if state is None:
        raise ValueError("game state missing")

    board_min, board_max = get_board_bounds()

    # Phase 1: Try positions in rectangle from (0,0) to combat location
    if center_x is not None and center_y is not None:
        # Define rectangle bounds (0,0) to (center_x, center_y)
        rect_min_x = min(0, center_x)
        rect_max_x = max(0, center_x)
        rect_min_y = min(0, center_y)
        rect_max_y = max(0, center_y)

        # Clamp to board bounds
        rect_min_x = max(rect_min_x, board_min)
        rect_max_x = min(rect_max_x, board_max)
        rect_min_y = max(rect_min_y, board_min)
        rect_max_y = min(rect_max_y, board_max)

        # Try up to 5 random positions in rectangle
        for attempt in range(5):
            x = random.randint(rect_min_x, rect_max_x)
            y = random.randint(rect_min_y, rect_max_y)

            if not _is_excluded_position(x, y, excluded):
                cell = get_cell(x, y)
                if cell is None:
                    cell = {"piece_id": None}
                piece_id_value = cell.get("piece_id")
                if piece_id_value is None:
                    energy_piece_id = state["next_piece_id"]
                    energy_piece = create_energy_piece(
                        energy_piece_id, x, y, amount, block_height
                    )
                    set_piece(energy_piece_id, energy_piece)
                    cell["piece_id"] = energy_piece_id
                    set_cell(x, y, cell)
                    state["next_piece_id"] += 1
                    state["total_pieces"] += 1
                    _set_storage("game/state", state)
                    return {
                        "index": f"game/pieces/{energy_piece_id:010d}",
                        "piece_id": energy_piece_id,
                        "x": x,
                        "y": y,
                        "amount": amount,
                    }

    # Phase 2: Fallback to random board placement (keep trying until placed)
    attempt = 0
    max_random_attempts = 20  # Reasonable limit to avoid infinite loops
    while attempt < max_random_attempts:
        x = random.randint(board_min, board_max)
        y = random.randint(board_min, board_max)

        if not _is_excluded_position(x, y, excluded):
            cell = get_cell(x, y)
            if cell is None:
                cell = {"piece_id": None}
            piece_id_value = cell.get("piece_id")
            if piece_id_value is None:
                energy_piece_id = state["next_piece_id"]
                energy_piece = create_energy_piece(
                    energy_piece_id, x, y, amount, block_height
                )
                set_piece(energy_piece_id, energy_piece)
                cell["piece_id"] = energy_piece_id
                set_cell(x, y, cell)
                state["next_piece_id"] += 1
                state["total_pieces"] += 1
                _set_storage("game/state", state)
                return {
                    "index": f"game/pieces/{energy_piece_id:010d}",
                    "piece_id": energy_piece_id,
                    "x": x,
                    "y": y,
                    "amount": amount,
                }
        attempt += 1

    # If still not placed after max attempts, return None (energy goes to pending)
    return None


# ============================================================================
# Game Logic - Phase 1 (Core Grid & Movement)
# ============================================================================


def initialize_game():
    """
    Initialize game config (run once at deployment)
    """
    existing_config = _get_storage("game/config")
    if existing_config is not None:
        raise ValueError("game already initialized")

    config = {
        "join_cost": JOIN_COST,
        "attack_reward": ATTACK_REWARD,
    }
    _set_storage("game/config", config)

    state = {
        "total_pieces": 0,
        "total_energy_circulation": 0,
        "pending_market_energy": 0,
        "pending_grid_energy": 0,
        "last_updated_block": 0,
        "next_piece_id": 1,  # Start at 1, 0 is reserved for SNAIL_ID
    }
    _set_storage("game/state", state)

    return {
        "status": "initialized",
        "config": config,
        "state": state,
    }


def spawn_piece(piece_type: str):
    """
    Spawn a new piece on the grid at a random empty location

    Args:
        piece_type: "rock", "paper", or "scissors"

    Required:
        Attached MsgSend message with at least JOIN_COST (100) udys sent to script address

    Returns:
        Piece info with spawn location (random empty cell on board)

    Phase 1 responsibilities:
    - Validate piece_type (rock/paper/scissors)
    - Enforce single-piece occupancy per cell
    - Generate unique piece_id
    - Persist piece, grid cell, player stats, and global state

    Phase 2 responsibilities:
    - Validate spawn payment (100 udys)
    """
    normalized_type = piece_type.lower()
    if normalized_type not in ["rock", "paper", "scissors"]:
        raise ValueError("invalid piece_type")

    # Validate payment
    script_address = get_script_address()
    attached_msgs = get_attached_messages()

    if not attached_msgs:
        raise ValueError("spawn requires payment: attach MsgSend with 100 udys")

    msg_send = None
    for msg in attached_msgs:
        if msg.get("@type") == "/cosmos.bank.v1beta1.MsgSend":
            msg_send = msg
            break

    if not msg_send:
        raise ValueError("spawn requires MsgSend payment message")

    to_address = msg_send.get("to_address")
    if to_address != script_address:
        raise ValueError(f"payment must be sent to script address {script_address}")

    amount = msg_send.get("amount")
    if not amount or len(amount) == 0:
        raise ValueError("payment amount missing in MsgSend")

    payment = amount[0]
    denom = payment.get("denom")
    payment_amount = int(payment.get("amount", "0"))

    if denom != PAYMENT_DENOM:
        raise ValueError(f"payment must be in {PAYMENT_DENOM}, got {denom}")

    if payment_amount < JOIN_COST:
        raise ValueError(
            f"insufficient payment: required {JOIN_COST} {PAYMENT_DENOM}, got {payment_amount}"
        )

    state = _get_storage("game/state")
    if state is None:
        raise ValueError("game state missing")

    block_info = get_block_info()
    block_height = block_info["height"]
    piece_id = state["next_piece_id"]

    # Find random empty cell on board
    spawn_x, spawn_y = _find_random_empty_cell(max_attempts=20)
    if spawn_x is None or spawn_y is None:
        raise ValueError("no empty cell found for spawning")

    spawn_cell = get_cell(spawn_x, spawn_y)
    if spawn_cell is None:
        spawn_cell = {"piece_id": None}

    owner = get_executor_address()
    piece = create_player_piece(
        piece_id,
        owner,
        normalized_type,
        spawn_x,
        spawn_y,
        0,
        block_height,
        block_height,
    )
    set_piece(piece_id, piece)

    spawn_cell["piece_id"] = piece_id
    set_cell(spawn_x, spawn_y, spawn_cell)

    player_index = f"game/players/{owner}"
    player_record = _get_storage(player_index)
    if player_record is None:
        player_record = {"pieces": [], "total_kills": 0, "total_deaths": 0}
    player_record["pieces"].append(piece_id)
    _set_storage(player_index, player_record)

    state["total_pieces"] += 1
    state["last_updated_block"] = block_height
    state["next_piece_id"] += 1
    _set_storage("game/state", state)

    return {
        "status": "spawned",
        "piece": piece,
        "grid": {"index": f"game/grid/{spawn_x}/{spawn_y}", "value": spawn_cell},
        "player": {"index": player_index, "value": player_record},
        "state": state,
    }


def move_piece(piece_id: int, target_x: int, target_y: int):
    """
    Move piece to target location

    Args:
        piece_id: Unique piece identifier
        target_x: Target x coordinate
        target_y: Target y coordinate

    Returns:
        Movement result with updated state
    """
    piece = get_piece(piece_id)
    if piece is None:
        raise ValueError("piece not found")
    if piece["is_npc"]:
        raise ValueError("cannot move npc piece")
    if piece["owner"] != get_executor_address():
        raise ValueError("not owner")

    current_x = piece["x"]
    current_y = piece["y"]

    board_min, board_max = get_board_bounds()
    if target_x < board_min or target_x > board_max:
        raise ValueError(
            f"target_x {target_x} out of bounds [{board_min}, {board_max}]"
        )
    if target_y < board_min or target_y > board_max:
        raise ValueError(
            f"target_y {target_y} out of bounds [{board_min}, {board_max}]"
        )

    block_info = get_block_info()
    block_height = block_info["height"]

    last_action_block = piece["last_action_block"]
    if block_height <= last_action_block:
        raise ValueError("piece already acted this block")

    movement_cost = calculate_movement_cost(current_x, current_y, target_x, target_y)

    if movement_cost > piece["energy"]:
        raise ValueError("insufficient energy for movement")

    piece["energy"] -= movement_cost
    # Save piece after deducting movement cost so collect_energy/combat read correct energy
    set_piece(piece_id, piece)

    state = _get_storage("game/state")
    if state is None:
        raise ValueError("game state missing")
    if movement_cost > 0:
        state["pending_market_energy"] += movement_cost

    target_cell: dict[str, Any] | None = get_cell(target_x, target_y)
    if target_cell is None:
        target_cell = {"piece_id": None}

    combat_result = None
    collect_result = None
    target_piece_id = target_cell.get("piece_id")
    if target_piece_id is not None:
        if target_piece_id == piece_id:
            raise ValueError("target cell occupied by same piece")
        target_piece = get_piece(target_piece_id)
        if target_piece is None:
            raise ValueError("target piece not found")
        if piece_is_collectible(target_piece):
            collect_result = collect_energy(piece_id, target_x, target_y)
            refreshed_piece = get_piece(piece_id)
            if refreshed_piece is None:
                raise ValueError("collector piece missing after collection")
            piece = refreshed_piece
            target_cell = {"piece_id": None}
        elif target_piece["is_npc"]:
            raise ValueError("target cell occupied by npc")
        elif target_piece["owner"] == piece["owner"]:
            raise ValueError("target cell occupied by ally")
        else:
            combat_result = execute_combat(piece_id, target_piece_id)
            target_cell = {"piece_id": None}
            refreshed_piece = get_piece(piece_id)
            if refreshed_piece is None:
                raise ValueError("attacker piece missing after combat")
            piece = refreshed_piece

    source_cell = get_cell(current_x, current_y)
    if source_cell is None:
        raise ValueError("source cell missing")

    source_cell["piece_id"] = None
    set_cell(current_x, current_y, source_cell)

    target_cell["piece_id"] = piece_id
    set_cell(target_x, target_y, target_cell)

    piece["x"] = target_x
    piece["y"] = target_y
    piece["last_action_block"] = block_height
    set_piece(piece_id, piece)

    state["last_updated_block"] = block_height
    _set_storage("game/state", state)

    move_summary = {
        "status": "moved",
        "piece": piece,
        "cost": movement_cost,
        "grid": {
            "from": {
                "index": f"game/grid/{current_x}/{current_y}",
                "value": source_cell,
            },
            "to": {"index": f"game/grid/{target_x}/{target_y}", "value": target_cell},
        },
        "state": state,
    }
    if combat_result is not None:
        move_summary["combat"] = combat_result
    if collect_result is not None:
        move_summary["collect"] = collect_result
    return move_summary


# ============================================================================
# Game Logic - Phase 2 (Combat & Energy)
# ============================================================================


def collect_energy(piece_id: int, x: int, y: int):
    """
    Collect energy piece from cell

    Args:
        piece_id: Collector piece ID
        x: Cell x coordinate
        y: Cell y coordinate

    Returns:
        Collection result with energy transfer info
    """
    collector = get_piece(piece_id)
    if collector is None:
        raise ValueError("collector piece not found")

    cell = get_cell(x, y)
    if cell is None:
        raise ValueError("cell not found")

    energy_piece_id = cell.get("piece_id")
    if energy_piece_id is None:
        raise ValueError("no piece at cell")

    energy_piece = get_piece(energy_piece_id)
    if energy_piece is None:
        raise ValueError("energy piece not found")

    if not piece_is_collectible(energy_piece):
        raise ValueError("piece at cell is not collectible energy")

    energy_amount = energy_piece["energy"]
    collector["energy"] += energy_amount
    set_piece(piece_id, collector)

    cell["piece_id"] = None
    set_cell(x, y, cell)

    state = _get_storage("game/state")
    if state is None:
        raise ValueError("game state missing")
    state["total_pieces"] = max(0, state["total_pieces"] - 1)
    _set_storage("game/state", state)

    delete_piece(energy_piece_id)

    return {
        "status": "collected",
        "collector": {"index": f"game/pieces/{piece_id:010d}", "value": collector},
        "energy_piece": {
            "index": f"game/pieces/{energy_piece_id:010d}",
            "removed": True,
        },
        "energy_gained": energy_amount,
        "grid": {"cleared": {"index": f"game/grid/{x}/{y}", "value": cell}},
    }


def execute_combat(attacker_id: int, victim_id: int):
    """
    Resolve RPS combat between pieces

    Phase 2 responsibilities:
    - Validate combatants and RPS rules
    - Transfer 50 energy (or victim remainder) to attacker
    - Split remaining victim energy: 40% market, 30% grid, 30% burn
    - Delete victim piece and clear grid cell
    - Update player stats and global state snapshot
    """
    attacker = get_piece(attacker_id)
    if attacker is None:
        raise ValueError("attacker piece not found")

    victim = get_piece(victim_id)
    if victim is None:
        raise ValueError("victim piece not found")

    if attacker_id == victim_id:
        raise ValueError("cannot attack same piece")

    if victim["is_npc"]:
        raise ValueError("cannot attack npc piece")

    attacker_is_npc = attacker["is_npc"]
    attacker_type = attacker["type"]
    victim_type = victim["type"]

    if not attacker_is_npc:
        if attacker_type not in RPS_DEFEATS:
            raise ValueError("unsupported attacker type")
        if RPS_DEFEATS[attacker_type] != victim_type:
            raise ValueError("attacker type cannot defeat victim type")

    block_info = get_block_info()
    block_height = block_info["height"]

    state = _get_storage("game/state")
    if state is None:
        raise ValueError("game state missing")

    victim_energy = victim["energy"]
    attacker_gain = ATTACK_REWARD
    if attacker_gain > victim_energy:
        attacker_gain = victim_energy
    remainder = victim_energy - attacker_gain
    market_share = remainder * 40 // 100
    grid_share = remainder * 30 // 100
    burn_share = remainder - market_share - grid_share

    attacker["energy"] += attacker_gain
    set_piece(attacker_id, attacker)

    attacker_owner = attacker["owner"]
    attacker_player_index = f"game/players/{attacker_owner}"
    attacker_player = _get_storage(attacker_player_index)
    if attacker_player is None:
        attacker_player = {"pieces": [], "total_kills": 0, "total_deaths": 0}
    attacker_player["total_kills"] += 1
    if attacker_id not in attacker_player["pieces"]:
        attacker_player["pieces"].append(attacker_id)
    _set_storage(attacker_player_index, attacker_player)

    victim_owner = victim["owner"]
    victim_player_index = f"game/players/{victim_owner}"
    victim_player = _get_storage(victim_player_index)
    if victim_player is not None:
        victim_player["pieces"] = [
            pid for pid in victim_player["pieces"] if pid != victim_id
        ]
        victim_player["total_deaths"] += 1
        _set_storage(victim_player_index, victim_player)

    victim_cell = get_cell(victim["x"], victim["y"])
    if victim_cell is None:
        victim_cell = {"piece_id": None}
    victim_cell["piece_id"] = None
    set_cell(victim["x"], victim["y"], victim_cell)

    energy_drop = None
    excluded_positions = [
        [attacker["x"], attacker["y"]],
        [victim["x"], victim["y"]],
    ]
    if grid_share > 0:
        # Place energy near combat location (victim's position)
        energy_drop = _place_energy_on_grid(
            grid_share, excluded_positions, victim["x"], victim["y"]
        )
        if energy_drop is None:
            state["pending_grid_energy"] += grid_share

    state["total_pieces"] = max(state["total_pieces"] - 1, 0)
    state["total_energy_circulation"] = max(
        state["total_energy_circulation"] - burn_share, 0
    )
    state["last_updated_block"] = block_height
    state["pending_market_energy"] += market_share
    _set_storage("game/state", state)

    delete_piece(victim_id)

    distribution = {
        "attacker": attacker_gain,
        "market": market_share,
        "grid": grid_share,
        "burn": burn_share,
    }

    combat_result = {
        "status": "victory",
        "attacker": {"index": f"game/pieces/{attacker_id:010d}", "value": attacker},
        "victim": {
            "index": f"game/pieces/{victim_id:010d}",
            "removed": True,
            "snapshot": victim,
        },
        "distribution": distribution,
        "grid": {
            "cleared": {
                "index": f"game/grid/{victim['x']}/{victim['y']}",
                "value": victim_cell,
            }
        },
        "state": {
            "total_pieces": state["total_pieces"],
            "total_energy_circulation": state["total_energy_circulation"],
            "pending_market_energy": state["pending_market_energy"],
            "pending_grid_energy": state["pending_grid_energy"],
        },
    }

    if energy_drop is not None:
        combat_result["energy_drop"] = energy_drop

    return combat_result


def calculate_movement_cost(from_x: int, from_y: int, to_x: int, to_y: int):
    """
    Calculate energy cost for movement

    Returns:
        - 0 for king move (adjacent)
        - distance² for queen move (straight line)
        - Error for invalid move
    """
    dx = abs(to_x - from_x)
    dy = abs(to_y - from_y)

    # King move (adjacent, including diagonals)
    if dx <= 1 and dy <= 1:
        return 0

    # Queen move (straight line only)
    if dx == 0 or dy == 0:
        distance = max(dx, dy)
        return distance * distance

    # Invalid move (not straight line)
    raise ValueError(
        f"Invalid move: not adjacent or straight line from ({from_x},{from_y}) to ({to_x},{to_y})"
    )


# ============================================================================
# Game Logic - Snail NPC (PvE Threat)
# ============================================================================


def spawn_snail():
    """
    Spawn THE single persistent snail NPC (called once at initialization)

    Returns:
        Snail piece info with crontask scheduling result
    """
    existing_snail = get_piece(SNAIL_ID)
    if existing_snail is not None:
        raise ValueError("snail already spawned")

    block_info = get_block_info()
    block_height = block_info["height"]

    # Find random empty cell on board for snail spawn
    spawn_x, spawn_y = _find_random_empty_cell(max_attempts=20)
    if spawn_x is None or spawn_y is None:
        raise ValueError("no empty cell found for snail spawning")

    snail = create_snail_piece(spawn_x, spawn_y, block_height, block_height)
    set_piece(SNAIL_ID, snail)

    spawn_cell: dict[str, Any] | None = get_cell(spawn_x, spawn_y)
    if spawn_cell is None:
        spawn_cell = {"piece_id": None}
    spawn_cell["piece_id"] = SNAIL_ID
    set_cell(spawn_x, spawn_y, spawn_cell)

    now = datetime.datetime.now()
    scheduled_time = int((now + datetime.timedelta(seconds=1)).timestamp())
    expiry_time = int((now + datetime.timedelta(days=1)).timestamp())

    heartbeat_msg = {
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": get_script_address(),
        "script_address": get_script_address(),
        "function_name": "snail_heartbeat",
        "args": json.dumps([]),
        "kwargs": "{}",
    }

    heartbeat_task = _msg(
        {
            "@type": "/dysonprotocol.crontask.v1.MsgCreateTask",
            "creator": get_script_address(),
            "scheduled_timestamp": str(scheduled_time),
            "expiry_timestamp": str(expiry_time),
            "task_gas_limit": "200000",
            "task_gas_fee": {"denom": "udys", "amount": "1"},
            "msgs": [heartbeat_msg],
        }
    )

    return {
        "status": "spawned",
        "snail": snail,
        "grid": {"index": f"game/grid/{spawn_x}/{spawn_y}", "value": spawn_cell},
        "heartbeat_task": heartbeat_task,
    }


def move_snail_ai():
    """
    AI-controlled snail movement (called by crontask every block)

    Returns:
        Movement result and next crontask
    """
    snail = get_piece(SNAIL_ID)
    if snail is None:
        raise ValueError("snail piece not found")

    x = snail["x"]
    y = snail["y"]

    oldest_player = find_oldest_player_piece()

    board_min, board_max = get_board_bounds()
    if oldest_player is None:
        target_x = random.randint(board_min, board_max)
        target_y = random.randint(board_min, board_max)
        target_id = None
    else:
        target_x = oldest_player["x"]
        target_y = oldest_player["y"]
        target_id = oldest_player["id"]

    dx = target_x - x
    dy = target_y - y
    distance_squared = dx * dx + dy * dy

    distance = 0
    if distance_squared > 0:
        distance = math.isqrt(distance_squared)

    speed = max(1, distance // 100)

    new_x = x
    new_y = y

    if distance < 100:
        directions = []
        king_moves = [
            (0, 1),
            (1, 0),
            (0, -1),
            (-1, 0),
            (1, 1),
            (1, -1),
            (-1, 1),
            (-1, -1),
        ]
        for move in king_moves:
            test_x = x + move[0]
            test_y = y + move[1]
            test_dx = target_x - test_x
            test_dy = target_y - test_y
            test_dist_sq = test_dx * test_dx + test_dy * test_dy
            test_dist = 0
            if test_dist_sq > 0:
                test_dist = math.isqrt(test_dist_sq)
            if test_dist < distance:
                directions.append(move)
        if len(directions) > 0:
            chosen_move = directions[random.randint(0, len(directions) - 1)]
            new_x = x + chosen_move[0]
            new_y = y + chosen_move[1]
    else:
        if distance > 0:
            new_x = x + (dx * speed // distance)
            new_y = y + (dy * speed // distance)
            if abs(new_x - x) > abs(dx):
                new_x = target_x
            if abs(new_y - y) > abs(dy):
                new_y = target_y

    block_info = get_block_info()
    block_height = block_info["height"]

    combat_result = None
    target_cell: dict[str, Any] | None = get_cell(new_x, new_y)
    if target_cell is None:
        target_cell = {"piece_id": None}

    target_piece_id = target_cell.get("piece_id")
    if target_piece_id == target_id and target_id is not None:
        combat_result = execute_combat(SNAIL_ID, target_id)
        refreshed_snail = get_piece(SNAIL_ID)
        if refreshed_snail is None:
            raise ValueError("snail piece missing after combat")
        snail = refreshed_snail
        target_cell = {"piece_id": None}
    elif target_piece_id is not None and target_piece_id != SNAIL_ID:
        target_piece = get_piece(target_piece_id)
        if target_piece is not None:
            if piece_is_collectible(target_piece):
                collect_energy(SNAIL_ID, new_x, new_y)
                refreshed_snail = get_piece(SNAIL_ID)
                if refreshed_snail is None:
                    raise ValueError("snail piece missing after energy collection")
                snail = refreshed_snail
                target_cell = get_cell(new_x, new_y)
                if target_cell is None:
                    target_cell = {"piece_id": None}
            elif not target_piece.get("is_npc", False):
                combat_result = execute_combat(SNAIL_ID, target_piece_id)
                refreshed_snail = get_piece(SNAIL_ID)
                if refreshed_snail is None:
                    raise ValueError("snail piece missing after combat")
                snail = refreshed_snail
                target_cell = {"piece_id": None}

    source_cell = get_cell(x, y)
    if source_cell is None:
        raise ValueError("source cell missing")

    source_cell["piece_id"] = None
    set_cell(x, y, source_cell)

    target_cell["piece_id"] = SNAIL_ID
    set_cell(new_x, new_y, target_cell)

    snail["x"] = new_x
    snail["y"] = new_y
    snail["last_action_block"] = block_height
    set_piece(SNAIL_ID, snail)

    result = {
        "status": "moved",
        "snail": snail,
        "target": {"id": target_id, "x": target_x, "y": target_y},
        "distance": distance,
        "speed": speed,
        "from": {"x": x, "y": y},
        "to": {"x": new_x, "y": new_y},
    }

    if combat_result is not None:
        result["combat"] = combat_result

    return result


def snail_heartbeat():
    """
    Heartbeat task that ensures snail keeps moving.
    Checks if snail exists and has moved recently, reschedules move_snail_ai if needed.
    Always schedules next heartbeat.

    Returns:
        Heartbeat result with rescheduling info
    """
    block_info = get_block_info()
    block_height = block_info["height"]

    snail = get_piece(SNAIL_ID)
    needs_movement = False
    blocks_since_move = 0

    if snail is not None:
        last_action_block = snail.get("last_action_block", 0)
        blocks_since_move = block_height - last_action_block
        if blocks_since_move >= SNAIL_MOVE_BLOCKS:
            needs_movement = True

    now = datetime.datetime.now()
    heartbeat_interval_seconds = HEARTBEAT_INTERVAL_BLOCKS
    next_heartbeat_time = int(
        (now + datetime.timedelta(seconds=heartbeat_interval_seconds)).timestamp()
    )
    expiry_time = int((now + datetime.timedelta(days=1)).timestamp())

    msgs = []

    if needs_movement:
        move_msg = {
            "@type": "/dysonprotocol.script.v1.MsgExec",
            "executor_address": get_script_address(),
            "script_address": get_script_address(),
            "function_name": "move_snail_ai",
            "args": json.dumps([]),
            "kwargs": "{}",
        }
        msgs.append(move_msg)

    heartbeat_msg = {
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": get_script_address(),
        "script_address": get_script_address(),
        "function_name": "snail_heartbeat",
        "args": json.dumps([]),
        "kwargs": "{}",
    }
    msgs.append(heartbeat_msg)

    task_result = _msg(
        {
            "@type": "/dysonprotocol.crontask.v1.MsgCreateTask",
            "creator": get_script_address(),
            "scheduled_timestamp": str(next_heartbeat_time),
            "expiry_timestamp": str(expiry_time),
            "task_gas_limit": "300000",
            "task_gas_fee": {"denom": "udys", "amount": "1"},
            "msgs": msgs,
        }
    )

    return {
        "status": "heartbeat",
        "snail_exists": snail is not None,
        "blocks_since_move": blocks_since_move,
        "scheduled_movement": needs_movement,
        "next_heartbeat_task": task_result,
    }


# ============================================================================
# Query Functions
# ============================================================================


def get_config():
    """Get game configuration"""
    return _get_storage("game/config")


def get_piece_info(piece_id: int):
    """Get piece details"""
    return get_piece(piece_id)


def get_player_pieces(address: str):
    """Get all pieces owned by player"""
    player_data = _get_storage(f"game/players/{address}")
    if player_data is None:
        return []
    return list(player_data["pieces"])


def get_player_stats(address: str):
    """Get player statistics"""
    return _get_storage(f"game/players/{address}")


# ============================================================================
# Utility Functions
# ============================================================================


def get_game_status():
    """
    Get overall game status and metrics
    """
    config = _get_storage("game/config")
    state = _get_storage("game/state")

    return {
        "config": config,
        "state": state,
        "implementation_status": {
            "phase_1": "IN PROGRESS - Core grid & movement",
            "phase_2": "PENDING - Combat & energy economics",
            "phase_3": "PENDING - Whaleswap integration",
            "phase_4": "PENDING - Optimization & features",
        },
    }


# ============================================================================
# WSGI Interface (for web access)
# ============================================================================


def wsgi(environ, start_response):
    """
    Web interface for game visualization

    TODO: Implement grid visualization and player actions
    """
    status = "200 OK"
    headers = [("Content-Type", "text/html")]
    start_response(status, headers)

    game_status = get_game_status()

    html = f"""
    <html>
    <head>
        <title>RPS Grid Battle</title>
        <style>
            body {{ font-family: monospace; padding: 20px; }}
            .status {{ background: #f0f0f0; padding: 10px; margin: 10px 0; }}
            .grid {{ border: 1px solid #ccc; }}
        </style>
    </head>
    <body>
        <h1>RPS Grid Battle</h1>
        <div class="status">
            <h2>Game Status</h2>
            <pre>{json.dumps(game_status, indent=2)}</pre>
        </div>
        <p><em>Grid visualization coming in Phase 1 implementation</em></p>
    </body>
    </html>
    """

    return [html.encode()]
