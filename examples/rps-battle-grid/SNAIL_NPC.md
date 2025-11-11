# Snail NPC - Design Document

## Overview

The Snail is an autonomous NPC (Non-Player Character) that adds a PvE threat to RPS Grid Battle. It uses Dyson Protocol's crontask module to schedule its movements and hunts the oldest player on the grid.

## Core Mechanics

### Snail Properties
- **Type**: "snail" (distinct from rock/paper/scissors)
- **Quantity**: Single persistent snail (piece_id = "snail")
- **Lifecycle**: Spawned at game initialization, never dies, never captured
- **Energy**: Infinite (999999) - never runs out, never needs it
- **Movement**: Dual behavior based on distance
  - **Close (<100 cells)**: 1 cell in random direction toward target (unpredictable)
  - **Far (≥100 cells)**: Straight line at 1% of distance (predictable but fast)
- **Movement Speed**: Dynamic based on distance to target
  - Formula: `speed = max(1, floor(distance * 0.01))`
  - Close range: Always 1 cell (with randomness)
  - Long range: 1-100+ cells (deterministic)
- **Movement Frequency**: Once per block (via crontask self-scheduling)
- **Movement Cost**: FREE (0 energy)
- **Invulnerability**: Cannot be attacked, captured, or killed by players
- **Target Selection**: Always tracks the oldest player piece (min spawn_block)

### Spawning
```python
Spawn Conditions:
  - Called once during initialize_game()
  - Single snail exists for entire game lifetime
  
Spawn Location:
  - Always at origin (0, 0)
  - Same as player spawns
  
Initial State:
  - piece_id: "snail" (fixed ID)
  - type: "snail"
  - is_npc: True
  - energy: 999999 (infinite, unused)
  - spawn_block: current_block
  - x: 0, y: 0
```

### AI Movement Logic

```python
def move_snail_ai():
    1. Query snail piece (piece_id = "snail")
    2. Get current position (x, y)
    
    3. Find target (oldest player):
       - Query all pieces where is_npc=False
       - If no players exist, skip to step 7 (still schedule next move)
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
           # Use block hash for deterministic randomness
           random_index = block_hash % len(directions)
           chosen_move = directions[random_index]
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
       - Update snail position in storage (game/pieces/snail)
       - Update grid cells (clear old position, set new position)
       - If new position equals target position:
           * execute_combat() - snail always wins
           * Snail immediately retargets next oldest player
    
    8. Schedule next move:
       - Create crontask for 1 block in future
       - Task calls move_snail_ai() again (no arguments needed)
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
  - Snail gains 50 energy (though it doesn't need it)
  - Player energy distributed normally:
      * 40% sold on Whaleswap
      * 30% placed randomly on grid
      * 30% burned
  
Player vs Snail Combat:
  - FORBIDDEN
  - Players cannot move onto snail's cell
  - Move validation must check is_npc flag
  - Attempting to attack snail fails validation
```

## Crontask Integration

### Self-Scheduling Pattern

The Snail uses a self-perpetuating crontask pattern (similar to crontask_countdown.py example):

```python
def move_snail_ai(snail_id: str):
    # Get current time
    now = datetime.datetime.now()
    
    # Calculate next move time (SNAIL_MOVE_INTERVAL blocks ~= seconds)
    scheduled_time = int((now + datetime.timedelta(seconds=SNAIL_MOVE_INTERVAL)).timestamp())
    expiry_time = int((now + datetime.timedelta(days=1)).timestamp())
    
    # Execute AI movement logic
    # ... (movement code) ...
    
    # Schedule next move
    exec_script_msg = {
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": get_script_address(),  # Script calls itself
        "script_address": get_script_address(),
        "function_name": "move_snail_ai",
        "args": json.dumps([snail_id]),
        "kwargs": "{}"
    }
    
    result = _msg({
        "@type": "/dysonprotocol.crontask.v1.MsgCreateTask",
        "creator": get_script_address(),
        "scheduled_timestamp": str(scheduled_time),
        "expiry_timestamp": str(expiry_time),
        "task_gas_limit": "500000",  # Sufficient for AI movement
        "task_gas_fee": {"denom": "udys", "amount": "1"},
        "msgs": [exec_script_msg]
    })
    
    return {"moved": True, "next_task": result}
```

### Gas Considerations

```
Snail Move Gas Budget (per block):
  - Query snail piece: ~50K gas
  - Query all player pieces: ~100K gas (depends on player count)
  - Calculate distance & speed: ~20K gas (includes sqrt/division)
  - Calculate direction vector: ~10K gas
  - Update storage (2 cells + piece): ~100K gas
  - Combat (if applicable): ~150K gas
  - Schedule crontask: ~100K gas
  
Total: ~530K gas per move (630K with combat)
Recommendation: Set task_gas_limit to 700000 (buffer for safety)
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
- [ ] Crontask self-scheduling

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

- [ ] Snail spawns at (0,0)
- [ ] Snail has infinite energy
- [ ] Snail tracks oldest player correctly
- [ ] Snail moves one king step per block
- [ ] Snail defeats any player type
- [ ] Players cannot attack snail
- [ ] Players cannot move onto snail cell
- [ ] Crontask schedules next snail move
- [ ] Snail continues moving after initial spawn
- [ ] Multiple snails can coexist
- [ ] Snail handles no-players-exist case
- [ ] Snail energy distribution on kill

## Example Scenario

```
Block 1: initialize_game() called
         spawn_snail() creates single persistent snail at (0,0)
         Crontask scheduled for block 2

Block 2: Crontask executes move_snail_ai()
           Players on grid: 
             - Rock at (5, 5) spawn_block=80 (oldest)
             - Paper at (3, 2) spawn_block=95
             - Scissors at (-2, 1) spawn_block=99
           Snail at (0, 0)
           Distance to Rock: sqrt(25+25) ≈ 7.07 cells (< 100 = RANDOM MODE)
           Valid directions: [(1,0), (0,1), (1,1)] all reduce distance
           Block hash % 3 = 1 → Choose (0, 1)
           Snail moves to (0, 1) [random toward target]
           Crontask scheduled for block 3

Block 3: Snail at (0, 1)
           Distance to Rock: sqrt(25+16) ≈ 6.4 cells (< 100 = RANDOM MODE)
           Valid directions: [(1,0), (0,1), (1,1), (1,-1)] reduce distance
           Block hash % 4 = 2 → Choose (1, 1)
           Snail moves to (1, 2) [unpredictable zigzag]
           Crontask scheduled for block 4

Block 4-8: Snail continues zigzagging toward Rock
           Random path, always reducing distance
           Eventually reaches (5, 5)

Block 9: Snail at (5, 5) - lands on Rock!
         Combat: Snail defeats Rock
         Rock destroyed, energy distributed
         Snail immediately retargets Paper at (3, 2) (new oldest)
         Crontask scheduled for block 10

Block 10: Snail at (5, 5)
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
SNAIL_ID = "snail"         # Single persistent snail
SNAIL_MOVE_BLOCKS = 1      # Moves once per block (via crontask)

# Tuning difficulty (optional)
RANDOM_MODE_THRESHOLD = 100  # Distance threshold for random vs straight movement
SPEED_MULTIPLIER = 0.01      # Speed = floor(distance * SPEED_MULTIPLIER)

# Example difficulty adjustments:
# - Easier: RANDOM_MODE_THRESHOLD = 150, SPEED_MULTIPLIER = 0.005
# - Harder: RANDOM_MODE_THRESHOLD = 50, SPEED_MULTIPLIER = 0.02
```

---

**Document Version**: 1.0  
**Status**: Specification complete  
**Implementation**: Phase 2  
**Last Updated**: 2025-11-11

