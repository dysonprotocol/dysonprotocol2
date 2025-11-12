# RPS Grid Battle - Specification v0.1

## Overview

**Implementation Status (2025-11-11)**  
- Phase 1 (core grid & movement) — complete and covered by integration tests.  
- Phase 2 (combat & energy) — in progress: player vs player combat, energy distribution, and energy collection implemented; energy economics and snail AI pending.  
- Phase 3/4 — not yet started.

### Implementation Notes

**Piece ID Format**: Piece IDs are plain integers (not formatted strings). The storage index uses zero-padding (`{piece_id:010d}`) to enable lexicographic ordering that matches chronological spawn order. This allows efficient queries for the oldest piece using `limit=1` with index ordering. The special ID `0` is reserved for the Snail NPC (`SNAIL_ID` constant), and `next_piece_id` starts at 1.
- The on-chain script assumes the storage schema created during `initialize_game()` remains intact; lookups fail fast instead of defensive `.get()` checks.
- Business logic avoids redundant flows—combat updates attacker state once, movement rewrites grid cells directly, and helper functions return concrete types for clarity.
- JSON payloads are written and read symmetrically; we trust the stored types and avoid needless casts (e.g., extra `int()` conversions) to keep the code lean.
- Tests exercise the live CLI path (`dysond tx script exec`), so documentation mirrors the real command usage seen in the integration suite.
- Piece creation uses module-level functions (not classes) for simplicity and AST minimization.
- Storage operations use inline helpers (`get_piece()`, `set_piece()`, `get_cell()`, `set_cell()`) that encapsulate index construction.
- Energy collection happens automatically when a player moves onto a cell containing an energy piece—no separate collection action required.
- Board boundaries are dynamic: `get_board_bounds()` calculates boundaries based on `total_pieces` from game state (`min = -1 * (10 + num_pieces)`, `max = 10 + num_pieces`).
- Spawn payment validation: `spawn_piece()` requires attached `MsgSend` message with at least 100 udys (Phase 2) sent to script address.

A blockchain-based, unlimited multiplayer Rock-Paper-Scissors battle game on a 2D grid. Players command pieces (Rock/Paper/Scissors types) that move and combat using RPS rules. Energy is the core resource—required for entry, movement, and gained through combat. Energy tokens trade on Whaleswap, creating market dynamics around gameplay timing.

## Core Mechanics

### Game Entry
- **Join Cost**: 100 udys (Phase 2) / 100 energy tokens (Phase 3) to spawn a piece on the grid
- **Payment**: Must attach `MsgSend` message with payment to script address when calling `spawn_piece()`
- **Piece Type**: Player chooses Rock, Paper, or Scissors at spawn
- **Spawn Location**: Pieces spawn at a random empty location on the board
- **Computer Pieces**: Autonomous "Snail" pieces spawn periodically and hunt players

### Grid & Movement
- **Grid**: Dynamic 2D grid with boundaries that expand based on number of pieces
  - **Boundaries**: `min = -1 * (10 + num_pieces)`, `max = 10 + num_pieces`
  - Starts at -10 to 10, grows by ±1 per piece spawned
  - Players cannot move outside these boundaries
  - Snail NPC is not restricted by boundaries (can move anywhere)
- **Turn System**: 1 action per piece per block
- **Movement Types**:
  - **King Move** (adjacent, 8 directions): 0 energy cost
  - **Queen Move** (straight line, any distance): distance² energy cost
- **Movement Restrictions**:
  - Cannot move to cell occupied by same type (Rock can't land on Rock)
  - Cannot move to cell occupied by defending type (Rock can't land on Paper)
  - Can only move to empty cells or vulnerable type

### Combat (Rock-Paper-Scissors)

#### Player vs Player Combat
- **Attack Trigger**: Landing on enemy piece of vulnerable type
  - Rock defeats Scissors
  - Scissors defeats Paper  
  - Paper defeats Rock
- **Attack Outcome**:
  - Attacker gains 50 energy from victim
  - Victim's remaining energy distribution:
    - 40% sold on Whaleswap market
    - 30% placed randomly on grid as collectible
    - 30% burned/removed
  - Victim piece is destroyed

#### Snail (Computer Piece)
- **Type**: Autonomous NPC that hunts players
- **Spawning**: Single snail spawned at game initialization
- **Persistence**: Never dies, never captured, exists permanently
- **Movement**: Behavior changes based on distance to target
  - **Close range (<100 cells)**: Moves 1 cell randomly toward target (unpredictable)
  - **Long range (≥100 cells)**: Moves `floor(distance * 0.01)` cells in straight line (predictable)
- **Movement Speed**: `max(1, floor(distance * 0.01))` cells per move
- **Movement Frequency**: Once per block (via heartbeat task that checks every 10 blocks)
- **Boundaries**: Not restricted by board boundaries (can move anywhere, unlike players)
- **Energy**: Infinite energy, never runs out
- **AI Behavior**: Tracks and moves toward the oldest player piece on the grid
- **Combat**: Can attack ANY piece type (ignores RPS rules)
- **Attack Outcome**: 
  - Snail gains 50 energy from victim (unused)
  - Victim energy distributed same as normal combat
  - Snail continues to next oldest player
- **Invulnerability**: Cannot be attacked or captured by players

### Energy Economics
- **Energy Token**: Tradeable on Whaleswap AMM
- **Movement Revenue**: Queen-move costs (distance² energy) added to Whaleswap liquidity pool
- **Market Dynamics**: Players time moves based on energy price fluctuations
- **Energy Pickups**: Energy from defeated pieces placed in rectangle from origin (0,0) to combat location, creating scavenging gameplay
- **Energy Collection**: Players collect energy by moving onto cells containing energy pieces. Collection happens automatically during movement—the energy piece is deleted, its energy is transferred to the collector, and the player lands on that cell.

## State Management

### On-Chain Storage Schema

```
game/config
  join_cost: int
  attack_reward: int
  spawn_x: int  # Always 0
  spawn_y: int  # Always 0
  
game/grid/{x}/{y}
  piece_id: int | null       # Piece ID (integer), null if empty. Energy is represented as an energy piece occupying the cell
  
game/pieces/{piece_id:010d}
  id: int                    # Piece ID (same as piece_id in index, stored in data for reference)
  owner: address
  type: "rock" | "paper" | "scissors" | "snail" | "energy"
  x: int
  y: int
  energy: int
  last_action_block: int
  is_npc: bool  # True for snail pieces
  spawn_block: int  # Block height when spawned
  
game/players/{address}
  pieces: [piece_id]         # Array of integer piece IDs
  total_kills: int
  total_deaths: int
```

## Piece Model (Module-Level Functions)

Piece creation uses module-level functions (not classes) for simplicity and AST minimization. All functions return plain dicts for storage.

- **Core Functions**:
  - `create_piece(...)` - Base piece creation with all required fields
  - `create_player_piece(...)` - Creates rock/paper/scissors pieces (validates type)
  - `create_snail_piece(...)` - Creates snail NPC piece
  - `create_energy_piece(...)` - Creates energy pickup piece
- **Utility Functions**:
  - `piece_is_collectible(piece: dict) -> bool` - Checks if piece is collectible energy
  - `piece_can_move(piece: dict) -> bool` - Checks if piece can move
  - `piece_can_attack(piece: dict) -> bool` - Checks if piece can attack

**Piece Types**:
- **PlayerPiece**: types = {"rock","paper","scissors"}; CAN_MOVE=True; CAN_ATTACK=True; IS_COLLECTIBLE=False
- **SnailPiece**: type="snail"; owner=None; is_npc=True; CAN_MOVE=True; CAN_ATTACK=True; IS_COLLECTIBLE=False
- **EnergyPiece**: type="energy"; owner=None; CAN_MOVE=False; CAN_ATTACK=False; IS_COLLECTIBLE=True

Energy is a first-class piece (immobile, collectible). Cells with energy contain an EnergyPiece id.

## Core Functions (Dyslang)

### Player Actions

```python
def spawn_piece(piece_type: str) -> dict:
    """
    Spawn new piece for 100 energy payment
    - Validate payment (100 energy transfer)
    - Validate piece_type (rock/paper/scissors)
    - Generate unique piece_id
    - Spawn at a random empty location on the board
    - Store piece in game/pieces/{piece_id}
    - Update game/grid/{spawn_x}/{spawn_y} with piece_id
    - Return spawn info
    """

def move_piece(piece_id: int, target_x: int, target_y: int) -> dict:
    """
    Move piece to target cell
    - Validate piece ownership
    - Validate 1 action per block
    - Calculate movement type and cost
    - Validate target cell (empty, energy piece, or vulnerable enemy)
    - Execute energy payment for queen moves (adds to pending_market_energy)
    - If target has energy piece: automatically collect_energy() then land on cell
    - If target has enemy: execute_combat() then land on cell
    - Update piece position
    - Update grid state
    """

def spawn_snail() -> dict:
    """
    Spawn THE autonomous snail NPC (called once at game initialization)
    - Create piece_id = "snail"
    - Spawn at a random empty location on the board
    - Set type = "snail", is_npc = True, energy = infinite
    - Schedule first snail move with crontask (1 block from now)
    - Return snail info
    """

def move_snail_ai() -> dict:
    """
    AI-controlled snail movement (called by crontask every block)
    - Query snail piece (piece_id = 0, SNAIL_ID constant)
    - Find oldest player piece (min spawn_block, is_npc=False)
    - If no players exist, stay at current position
    - Calculate distance to target (euclidean)
    - Calculate movement speed: max(1, floor(distance * 0.01))
    - If distance < 100: Move 1 cell in random direction toward target
        * Choose from 3-5 directions that reduce distance
        * Use Python's random module for randomness
    - If distance >= 100: Move N steps in straight line toward target
    - If lands on or passes target cell, execute combat (snail always wins)
    - After combat, immediately target next oldest player
    - Schedule next snail move with crontask (1 block from now)
    - Return movement result
    """
```

### Internal Game Logic

```python
def execute_combat(attacker_id: str, victim_id: str) -> dict:
    """
    Resolve RPS combat
    - Validate RPS rules (attacker type beats victim type)
    - Transfer 50 energy from victim to attacker
    - Distribute victim remaining energy:
        * 40% sell on Whaleswap (tracked as pending_market_energy)
        * 30% place EnergyPiece in rectangle from (0,0) to combat location (falls back to random board if needed)
        * 30% burn
    - Delete victim piece
    - Update stats
    """

def calculate_movement_cost(from_x: int, from_y: int, to_x: int, to_y: int) -> int:
    """
    Calculate energy cost for movement
    - King move (adjacent): 0
    - Queen move (straight): distance²
    - Invalid move: raise error
    """

def is_valid_move(piece: dict, target_x: int, target_y: int) -> bool:
    """
    Validate move legality
    - Check target in bounds
    - Check target is empty OR vulnerable enemy
    - Check not same type or defending type
    - Check piece has sufficient energy
    """

def _place_energy_on_grid(amount: int, excluded: list, center_x: int, center_y: int) -> dict:
    """
    Place energy pickup in rectangle from (0,0) to combat location
    - Try 5 random positions in rectangle from (0,0) to (center_x, center_y)
    - If all fail, fall back to random board placement (up to 20 attempts)
    - Returns None if placement fails (energy goes to pending_grid_energy)
    """
```

### Query Functions

```python
def get_grid_state(x_start: int, y_start: int, x_end: int, y_end: int) -> dict:
    """Query grid region for client rendering"""

def get_piece_info(piece_id: int) -> dict:
    """Get piece details"""

def get_player_pieces(address: str) -> list:
    """Get all pieces owned by player"""

def get_leaderboard(limit: int) -> list:
    """Get top players by kills"""
```

## Whaleswap Integration

### Energy Token Market
- **Token Name**: `rpsgrid.energy.dys` (or similar registered name)
- **Initial Pool**: Seed liquidity pool with energy/udys pair
- **Movement Revenue**: `distance² * energy_cost` added to pool via `MsgAddLiquidity`
- **Combat Sales**: 40% of victim energy sold via `MsgSwap` (energy → udys)

### Economic Flow
```
Player Movement (Queen) → Energy Cost → Liquidity Pool → Increased Market Depth
Combat Victory → 40% Victim Energy → Market Sale → Price Impact
Price Fluctuation → Player Strategy → Timing of Moves
```

## Implementation Phases

### Phase 1: Core Grid & Movement (Minimal Viable Game)
- Grid state storage
- Piece spawning (basic validation)
- King movement only (0 cost)
- Basic collision detection
- Simple query functions for testing

### Phase 2: Combat & Energy Economics
- Full RPS combat system ✅
- Queen movement with distance² cost ✅
- Energy pickups on grid ✅
- Victory energy transfer ✅
- Basic market integration (manual testing) ✅
- Snail NPC spawning and AI movement ✅

### Phase 3: Whaleswap Integration
- Energy token on Whaleswap
- Automated liquidity additions from movement
- Automated market sales from combat
- Energy price queries in UI

### Phase 4: Optimization & Features
- Efficient grid queries (spatial indexing)
- Player statistics & leaderboard
- Gas optimizations
- Frontend/UI improvements

## Technical Considerations

### Gas & Performance
- **Per-Move Gas**: ~300K-500K (storage updates, combat resolution)
- **Grid Queries**: Use prefix-based storage queries for efficient region loading
- **State Minimization**: Store only essential data, derive computed values

### Security & Validation
- **Ownership**: Validate piece ownership on every action
- **Rate Limiting**: 1 action per piece per block (check `last_action_block`)
- **Energy Balance**: Validate sufficient energy before movements
- **Atomic Operations**: Use storage transactions to prevent race conditions

### Edge Cases
- **Infinite Coordinates**: No boundary validation needed
- **Spawn Stacking**: Multiple pieces can occupy (0,0) initially
- **Energy Exhaustion**: Piece with 0 energy is stuck (can't move)
- **Concurrent Actions**: Block-based turns prevent same-block conflicts
- **Snail Target**: If no players exist, snail stays at current location
- **Snail Invulnerability**: Players cannot move onto snail's cell

## Future Extensions

- **Team Battles**: Alliance mechanics, shared resources
- **Power-Ups**: Temporary buffs on grid cells
- **Territory Control**: Zone ownership mechanics
- **NFT Pieces**: Unique pieces with special abilities
- **Tournaments**: Scheduled competitive events with prizes
- **Grid Evolution**: Expanding/shrinking grid based on player count

## Success Metrics

- **Active Players**: Unique addresses with pieces on grid
- **Daily Moves**: Total movement transactions per day
- **Market Volume**: Energy token trading volume on Whaleswap
- **Combat Rate**: Battles per block
- **Energy Circulation**: Total energy in game vs. market

---

**Status**: Specification complete, implementation pending

**Next Steps**: 
1. Review spec with stakeholders
2. Create storage schema tests
3. Implement Phase 1 core functions
4. Deploy testnet for balancing

