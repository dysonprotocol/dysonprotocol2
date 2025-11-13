# Snail NPC - Design Document

## Overview

The Snail is an autonomous NPC (Non-Player Character) that adds a PvE threat to RPS Grid Battle. It uses Dyson Protocol's crontask module to schedule its movements and hunts the oldest player on the grid.

> **Status:** ✅ **COMPLETE** - Snail NPC system fully implemented and tested. All core mechanics, AI movement, combat, and crontask scheduling are functional. Comprehensive test suite covers all scenarios.

## Core Mechanics

### Snail Properties
- **Type**: "snail" (distinct from rock/paper/scissors)
- **Quantity**: Single persistent snail (piece_id = 0, `SNAIL_ID` constant)
- **Lifecycle**: Spawned at game initialization, never dies, never captured
- **Energy**: Infinite (999999) - never runs out, never needs it
- **Movement**: Dual behavior based on distance
  - **Close (<100 cells)**: 1 cell in random direction toward target (unpredictable)
  - **Far (≥100 cells)**: Straight line at 1% of distance (predictable but fast)
- **Movement Speed**: Dynamic based on distance to target
  - Formula: `speed = max(1, floor(distance * 0.01))`
  - Close range: Always 1 cell (with randomness)
  - Long range: 1-100+ cells (deterministic)
- **Movement Frequency**: Once per block (via heartbeat task that checks every 10 blocks)
- **Movement Cost**: FREE (0 energy)
- **Invulnerability**: Cannot be attacked, captured, or killed by players
- **Target Selection**: Always tracks the oldest player piece (min spawn_block)

### Spawning
```python
Spawn Conditions:
  - Called once during initialize_game()
  - Single snail exists for entire game lifetime
  
Spawn Location: Random empty location on board (same as player pieces)
  - Uses `_find_random_empty_cell()` helper function
  - Up to 20 attempts to find empty cell
  
Initial State:
  - piece_id: 0 (SNAIL_ID constant, reserved ID)
  - type: "snail"
  - is_npc: True
  - energy: 999999 (infinite, unused)
  - spawn_block: current_block
  - x: 0, y: 0
```

### AI Movement Logic

```python
def move_snail_ai():
    1. Query snail piece (piece_id = 0, SNAIL_ID constant)
    2. Get current position (x, y)
    
    3. Find target (oldest player):
       - Query all pieces where is_npc=False
       - If no players exist, return early (heartbeat will reschedule if needed)
       - Select piece with minimum spawn_block
       - Get target position (target_x, target_y)
    
    4. Calculate distance to target:
       dx = target_x - x
       dy = target_y - y
       distance = sqrt(dx² + dy²)  # Euclidean distance
       
    5. Calculate movement speed:
       speed = max(1, floor(distance * 0.01))
       # Close (<100 cells): speed = 1
       # Far (≥100 cells): speed = 1% of distance
       
    6. Calculate new position based on distance:
    
       IF distance < 100:  # CLOSE RANGE - Random movement
           # Generate list of valid directions that move toward target
           directions = []
           for move in [(0,1), (1,0), (0,-1), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]:
               test_x = x + move[0]
               test_y = y + move[1]
               test_dist = sqrt((target_x - test_x)² + (target_y - test_y)²)
               if test_dist < distance:  # This move reduces distance
                   directions.append(move)
           
           # Pick random direction from valid options
          # Use Python random module for selection
          chosen_move = random.choice(directions)
           new_x = x + chosen_move[0]
           new_y = y + chosen_move[1]
       
       ELSE:  # LONG RANGE - Straight line movement
           # Normalize direction vector
           dir_x = dx / distance
           dir_y = dy / distance
           
           # Move in straight line toward target
           new_x = x + floor(dir_x * speed)
           new_y = y + floor(dir_y * speed)
           
           # Clamp to target if we would overshoot
           if abs(new_x - x) > abs(dx):
               new_x = target_x
           if abs(new_y - y) > abs(dy):
               new_y = target_y
    
    7. Execute movement:
       - Update snail position in storage (game/pieces/0000000000)
       - Update grid cells (clear old position, set new position)
       - If new position equals target position:
           * execute_combat() - snail always wins
           * Snail immediately retargets next oldest player
    
    Note: move_snail_ai() does NOT schedule itself. The heartbeat task handles scheduling.
```

### Movement Speed Examples

```
Distance to Target    Speed    Travel Time (blocks)
─────────────────────────────────────────────────────
10 cells              1        10 blocks
50 cells              1        50 blocks
100 cells             1        100 blocks
150 cells             1        150 blocks
200 cells             2        100 blocks
500 cells             5        100 blocks
1000 cells            10       100 blocks
10000 cells           100      100 blocks
```

**Key Insights**: 
- **Long range (≥100 cells)**: Snail takes ~100 blocks to reach target (predictable path)
- **Close range (<100 cells)**: Snail is UNPREDICTABLE - random zigzag approach
- **Sweet spot**: No safe zone! Far = fast, close = random
- **Escape strategy**: Must stay mobile, can't rely on perpendicular movement alone

### Combat Rules

```python
Snail vs Player Combat:
  - Snail ALWAYS wins (ignores RPS type)
  - Player piece is destroyed
  - Player energy distributed normally:
      * 50% → Snail (as bank send of energy coins, unused)
      * 25% → Added as unbalanced liquidity to Whaleswap pool
      * 25% → Placed randomly on grid as energy piece
  
Player vs Snail Combat:
  - FORBIDDEN
  - Players cannot move onto snail's cell
  - Move validation must check is_npc flag
  - Attempting to attack snail fails validation
```

## Crontask Integration

### Heartbeat System (Resilience)

The Snail uses a heartbeat task to ensure continuous movement even if `move_snail_ai()` fails:

```python
def snail_heartbeat():
    """
    Heartbeat task that ensures snail keeps moving.
    Runs every 10 blocks (HEARTBEAT_INTERVAL_BLOCKS).
    
    1. Check if snail exists
    2. Check if snail has moved recently (blocks_since_move >= SNAIL_MOVE_BLOCKS)
    3. If movement needed:
       - Schedule move_snail_ai() in same task
    4. Always schedule next heartbeat (ensures continuity)
    """
    block_info = get_block_info()
    block_height = block_info["height"]
    
    snail = get_piece(SNAIL_ID)
    needs_movement = False
    
    if snail is not None:
        last_action_block = snail.get("last_action_block", 0)
        blocks_since_move = block_height - last_action_block
        if blocks_since_move >= SNAIL_MOVE_BLOCKS:
            needs_movement = True
    
    msgs = []
    
    if needs_movement:
        move_msg = {
            "@type": "/dysonprotocol.script.v1.MsgExec",
            "function_name": "move_snail_ai",
            "args": json.dumps([]),
        }
        msgs.append(move_msg)
    
    heartbeat_msg = {
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "function_name": "snail_heartbeat",
        "args": json.dumps([]),
    }
    msgs.append(heartbeat_msg)
    
    # Schedule next heartbeat (always)
    task_result = _msg({
        "@type": "/dysonprotocol.crontask.v1.MsgCreateTask",
        "scheduled_timestamp": str(next_heartbeat_time),
        "task_gas_limit": "300000",
        "msgs": msgs
    })
    
    return {"status": "heartbeat", "scheduled_movement": needs_movement}
```

**Benefits:**
- **Resilience**: If `move_snail_ai()` fails, heartbeat detects it hasn't moved and reschedules
- **Separation of concerns**: Movement logic doesn't handle scheduling
- **Minimal overhead**: Heartbeat runs every 10 blocks, not every block
- **Self-healing**: Even if snail piece is temporarily missing, heartbeat continues checking

**Failure Recovery:**
- If `move_snail_ai()` raises exception → crontask fails → snail doesn't move
- Next heartbeat (within 10 blocks) detects `blocks_since_move >= 1`
- Heartbeat reschedules `move_snail_ai()` → snail resumes movement
- Snail never permanently stops due to transient failures

### Gas Considerations

```
Snail Move Gas Budget (per move_snail_ai call):
  - Query snail piece: ~50K gas
  - Query all player pieces: ~100K gas (depends on player count)
  - Calculate distance & speed: ~20K gas (includes integer sqrt)
  - Calculate direction vector: ~10K gas
  - Update storage (2 cells + piece): ~100K gas
  - Combat (if applicable): ~150K gas
  - Total: ~430K-530K gas per movement

Heartbeat Gas Budget (every 10 blocks):
  - Query snail piece: ~50K gas
  - Check last_action_block: ~10K gas
  - Schedule next heartbeat + move_snail_ai: ~100K gas
  - Total: ~160K gas per heartbeat
  
Gas Limit Recommendations:
  - move_snail_ai task: 10000000 (sufficient for movement + combat)
  - heartbeat task: 300000 (sufficient for check + scheduling)
```

## Player Validation Updates

### Movement Validation

```python
def is_valid_move(piece: dict, target_x: int, target_y: int) -> bool:
    # Existing validations...
    
    # NEW: Check if target cell has snail
    target_cell = _get_storage(f"game/grid/{target_x}/{target_y}")
    if target_cell:
        target_piece_id = target_cell.get("piece_id")
        if target_piece_id:
            target_piece = _get_storage(f"game/pieces/{target_piece_id}")
            if target_piece and target_piece.get("is_npc"):
                # Cannot move onto snail
                return False
    
    # Continue with other validations...
```

## Strategic Implications

### For Players

**Oldest Player Disadvantage**:
- Being the oldest player makes you the Snail's primary target
- **Distance Paradox**: Fleeing too far makes Snail faster!
  - < 100 cells: Snail moves 1 cell/block (escapable)
  - ≥ 100 cells: Snail moves 1% of distance (faster!)
  - At 500 cells: Snail moves 5 cells/block (5x faster!)
- Must maintain high energy for escape maneuvers
- Consider "retiring" pieces and spawning new ones to reset age

**Defensive Strategies**:
1. **No Safe Zone**: Can't rely on distance alone
   - Close (<100): Snail is unpredictable, zigzags toward you
   - Far (≥100): Snail is fast but predictable
2. **Constant Movement**: Never stay still when Snail is hunting you
3. **Energy Reserve**: Keep enough for emergency queen moves (jump to far position)
4. **Perpendicular Movement**: Still useful at long range (>100), useless at close range
5. **Flee to 150+ cells**: Snail becomes predictable again (straight line pursuit)
6. **Don't Flee Beyond 300**: Speed penalty too severe (3+ cells/block)
7. **Awareness**: Track Snail location via grid queries
8. **Retirement Strategy**: Spawn new pieces to reset age ranking

**Offensive Opportunities**:
1. **Snail as Barrier**: Use Snail to block enemy movements
2. **Distraction**: Attack enemies while they flee from Snail
3. **Timing**: Spawn when Snail is far from origin
4. **Kiting**: Stay just ahead of Snail to use it as moving obstacle

### For Game Balance

**Single Snail Design**:
- One snail = constant threat without overwhelming players
- Never dies = permanent PvE pressure
- Moves every block = relentless pursuit
- Simple to reason about for players

**Movement Frequency**:
- Fixed: 1 move per block (via crontask)
- Cannot be changed (hard-coded in crontask scheduling)
- Provides consistent, predictable pressure

**Tuning Difficulty**:
- To increase difficulty: Decrease random mode threshold (< 100 → < 50)
- To decrease difficulty: Increase random mode threshold (< 100 → < 150)
- Speed formula can be adjusted: floor(distance * 0.01) → floor(distance * 0.005)

## Implementation Phases

### Phase 2A: Basic Snail
- [x] Snail spawn function
- [x] Basic AI movement (toward oldest player)
- [x] Invulnerability validation
- [x] Heartbeat system for resilience

### Phase 2B: Combat Integration
- [ ] Snail combat (always wins)
- [ ] Energy distribution from snail kills
- [ ] Player movement validation (cannot attack snail)

### Phase 2C: Advanced AI
- [ ] Pathfinding around obstacles
- [ ] Multiple snail support
- [ ] Snail despawn conditions (optional)
- [ ] Different snail behaviors (optional)

## Testing Checklist

- [x] Snail spawns at random empty location on board
- [x] Snail has infinite energy
- [x] Snail tracks oldest player correctly
- [x] Snail moves one king step per block (close range) or straight line (long range)
- [x] Snail defeats any player type
- [x] Players cannot attack snail
- [x] Players cannot move onto snail cell
- [x] Crontask schedules next snail move
- [x] Snail continues moving after initial spawn
- [x] Snail handles no-players-exist case
- [x] Snail energy distribution on kill

## Example Scenario

```
Block 1: initialize_game() called
         spawn_snail() creates single persistent snail at (0,0)
         Heartbeat task scheduled for block 2

Block 2: Heartbeat executes, detects snail needs to move
         Schedules move_snail_ai() + next heartbeat
         move_snail_ai() executes:
           Players on grid: 
             - Rock at (5, 5) spawn_block=80 (oldest)
             - Paper at (3, 2) spawn_block=95
             - Scissors at (-2, 1) spawn_block=99
           Snail at (0, 0)
           Distance to Rock: sqrt(25+25) ≈ 7.07 cells (< 100 = RANDOM MODE)
           Valid directions: [(1,0), (0,1), (1,1)] all reduce distance
           Random choice → Choose (0, 1)
           Snail moves to (0, 1) [random toward target]

Block 3: Heartbeat executes, detects snail needs to move
         Schedules move_snail_ai() + next heartbeat
         Snail at (0, 1)
         Distance to Rock: sqrt(25+16) ≈ 6.4 cells (< 100 = RANDOM MODE)
         Valid directions: [(1,0), (0,1), (1,1), (1,-1)] reduce distance
         Random choice → Choose (1, 1)
         Snail moves to (1, 2) [unpredictable zigzag]

Block 4-12: Heartbeat continues checking every 10 blocks
            Snail continues zigzagging toward Rock
            Random path, always reducing distance
            Eventually reaches (5, 5)

Block 13: Snail at (5, 5) - lands on Rock!
          Combat: Snail defeats Rock
          Rock destroyed, energy distributed
          Snail immediately retargets Paper at (3, 2) (new oldest)

Block 14: Heartbeat executes, detects snail needs to move
          Schedules move_snail_ai() + next heartbeat
          Snail at (5, 5)
          Distance to Paper at (3, 2): sqrt(4+9) ≈ 3.6 cells
          Speed: 1 cell
          Snail moves toward (3, 2)
          ...and so on...

Alternative scenario with distant player:

Block 100: Snail at (0, 0)
           Rock at (500, 500) spawn_block=50 (oldest)
           Distance: sqrt(250000+250000) ≈ 707 cells (> 100 = STRAIGHT LINE MODE)
           Speed: max(1, floor(707 * 0.01)) = 7 cells
           Snail moves ~7 cells in straight line toward target
           
Block 101-200: Snail continues straight-line pursuit
               Speed gradually decreases as distance closes
               At 100 cells away, switches to RANDOM MODE
               Takes ~100-120 blocks to reach distant target!
```

## Configuration

```python
# Snail constants (fixed)
SNAIL_ID = 0                # Single persistent snail (reserved piece ID)
SNAIL_MOVE_BLOCKS = 1      # Moves once per block (when heartbeat detects need)
HEARTBEAT_INTERVAL_BLOCKS = 10  # Heartbeat checks every 10 blocks

# Tuning difficulty (optional)
RANDOM_MODE_THRESHOLD = 100  # Distance threshold for random vs straight movement
SPEED_MULTIPLIER = 0.01      # Speed = floor(distance * SPEED_MULTIPLIER)

# Example difficulty adjustments:
# - Easier: RANDOM_MODE_THRESHOLD = 150, SPEED_MULTIPLIER = 0.005
# - Harder: RANDOM_MODE_THRESHOLD = 50, SPEED_MULTIPLIER = 0.02
```

---

## Testing

Comprehensive test suite implemented in `tests/examples/rps/test_snail.py`:

- ✅ **`test_snail_spawn`** - Verifies snail spawns correctly with proper attributes (ID=0, type="snail", is_npc=True, energy=999999, grid placement, crontask scheduling)
- ✅ **`test_snail_tracks_oldest_player`** - Verifies snail targets the oldest player piece (min spawn_block) using bounded queries
- ✅ **`test_snail_defeats_rock`** - Verifies snail defeats player pieces regardless of type (ignores RPS rules)
- ✅ **`test_player_cannot_attack_snail`** - Verifies players cannot move onto or attack the snail (NPC invulnerability)
- ✅ **`test_snail_crontask_scheduling`** - Verifies snail schedules its next move via crontask after each movement
- ✅ **`test_snail_movement_close_range`** - Verifies random king-move behavior when target is close (<100 cells)
- ✅ **`test_snail_movement_long_range`** - Verifies straight-line movement with speed calculation when target is far (≥100 cells)

All tests passing. Implementation uses integer square root (`_isqrt`) for distance calculations to comply with Dyslang's no-float-arithmetic constraint.

---

**Document Version**: 1.1  
**Status**: ✅ Implementation Complete & Tested  
**Implementation**: Phase 2 - Complete  
**Last Updated**: 2025-01-XX

