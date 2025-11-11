"""
RPS Grid Battle - Dyson Protocol Game Script

A fully on-chain multiplayer Rock-Paper-Scissors battle game.

Phase 1: Core grid & movement (IN PROGRESS)
Phase 2: Combat & energy economics (PENDING)
Phase 3: Whaleswap integration (PENDING)
Phase 4: Optimization & features (PENDING)

See spec.md for complete game design.
"""

import json
from dys import _msg, _query, get_script_address, get_executor_address


# ============================================================================
# Configuration
# ============================================================================

SPAWN_X = 0
SPAWN_Y = 0
JOIN_COST = 100
ATTACK_REWARD = 50

# RPS type relationships
RPS_DEFEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}

# Snail constants
SNAIL_ID = "snail"  # Single persistent snail
SNAIL_MOVE_BLOCKS = 1  # Snail moves once per block


# ============================================================================
# Storage Helper Functions
# ============================================================================


def _get_storage(index: str):
    """Query storage by index"""
    result = _query(
        {
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": get_script_address(),
            "index": index,
        }
    )
    if "entry" in result and "data" in result["entry"]:
        return json.loads(result["entry"]["data"])
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


# ============================================================================
# Game Logic - Phase 1 (Core Grid & Movement)
# ============================================================================


def initialize_game():
    """
    Initialize game config (run once at deployment)
    """
    config = {
        "spawn_x": SPAWN_X,
        "spawn_y": SPAWN_Y,
        "join_cost": JOIN_COST,
        "attack_reward": ATTACK_REWARD,
    }
    _set_storage("game/config", config)

    state = {"total_pieces": 0, "total_energy_circulation": 0, "last_updated_block": 0}
    _set_storage("game/state", state)

    # Spawn the single persistent snail
    snail_result = spawn_snail()

    return {
        "status": "initialized",
        "config": config,
        "state": state,
        "snail": snail_result,
    }


def spawn_piece(piece_type: str):
    """
    Spawn a new piece on the grid at origin (0, 0)

    Args:
        piece_type: "rock", "paper", or "scissors"

    Returns:
        Piece info with spawn location (always 0, 0)

    TODO Phase 1:
    - Validate piece_type (rock/paper/scissors)
    - Generate unique piece_id
    - Spawn at (0, 0)
    - Store piece data
    - Update grid cell (0, 0) - multiple pieces can stack
    - Update player stats
    - Validate energy payment (Phase 2)
    """
    # Placeholder implementation
    return {"status": "not_implemented", "phase": 1}


def move_piece(piece_id: str, target_x: int, target_y: int):
    """
    Move piece to target location

    Args:
        piece_id: Unique piece identifier
        target_x: Target x coordinate
        target_y: Target y coordinate

    Returns:
        Movement result with updated state

    TODO Phase 1:
    - Query piece data
    - Validate ownership
    - Validate rate limit (1 action per block)
    - Calculate movement type & cost
    - Validate target cell
    - Update piece position
    - Update grid cells
    """
    # Placeholder implementation
    return {"status": "not_implemented", "phase": 1}


# ============================================================================
# Game Logic - Phase 2 (Combat & Energy)
# ============================================================================


def execute_combat(attacker_id: str, victim_id: str):
    """
    Resolve RPS combat between pieces

    TODO Phase 2:
    - Validate RPS rules
    - Transfer energy (50 to attacker)
    - Distribute victim energy (40% market, 30% random, 30% burn)
    - Delete victim piece
    - Update stats
    """
    # Placeholder implementation
    return {"status": "not_implemented", "phase": 2}


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
        Snail piece info

    TODO Phase 2:
    - Create snail piece with piece_id = "snail"
    - Spawn at (0, 0)
    - Set type="snail", is_npc=True, energy=999999
    - Set spawn_block = current_block
    - Store snail piece in game/pieces/snail
    - Update grid cell game/grid/0/0
    - Schedule first snail move using crontask (1 block from now)
    """
    # Placeholder implementation
    return {"status": "not_implemented", "phase": 2}


def move_snail_ai():
    """
    AI-controlled snail movement (called by crontask every block)

    Returns:
        Movement result and next crontask

    TODO Phase 2:
    - Query snail piece (piece_id = "snail")
    - Get current position (x, y)
    - Find oldest player piece (min spawn_block, is_npc=False)
    - If no players exist, skip movement but still schedule next move
    - Calculate distance to target: sqrt((target_x-x)² + (target_y-y)²)
    - Calculate movement speed: max(1, floor(distance * 0.01))

    IF distance < 100:  # Close range - random movement
        - Generate list of 8 directions (king moves)
        - Filter to directions that reduce distance to target
        - Use block hash for random selection: block_hash % len(valid_directions)
        - Move 1 cell in chosen random direction

    ELSE:  # Long range - straight line movement
        - Calculate direction vector: (dx/distance, dy/distance)
        - Move in straight line: new_pos = (x + dir_x*speed, y + dir_y*speed)
        - Clamp to target if overshoot

    - If lands on or reaches target cell, execute combat (snail always wins)
    - After combat, snail immediately targets next oldest player
    - Update snail position in storage (game/pieces/snail)
    - Update grid cells (clear old, set new)
    - Schedule next snail move with crontask (1 block from now)
    """
    # Placeholder implementation
    return {"status": "not_implemented", "phase": 2}


# ============================================================================
# Query Functions
# ============================================================================


def get_config():
    """Get game configuration"""
    return _get_storage("game/config")


def get_grid_state(x_start: int, y_start: int, x_end: int, y_end: int):
    """
    Query grid region for rendering

    TODO Phase 1:
    - Query game/grid/* with prefix filter
    - For each cell with piece, query piece data
    - Return structured grid data
    """
    # Placeholder implementation
    return {"status": "not_implemented", "phase": 1}


def get_piece_info(piece_id: str):
    """Get piece details"""
    return _get_storage(f"game/pieces/{piece_id}")


def get_player_pieces(address: str):
    """Get all pieces owned by player"""
    player_data = _get_storage(f"game/players/{address}")
    if player_data:
        return player_data.get("pieces", [])
    return []


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
