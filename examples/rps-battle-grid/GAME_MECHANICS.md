# RPS Grid Battle - Game Mechanics Visual Guide

## Rock-Paper-Scissors Combat Matrix

### Player vs Player
```
         TARGET
       R   P   S
    ┌─────────────┐
  R │ ✗   ✗   ✓   │
A P │ ✓   ✗   ✗   │
  S │ ✗   ✓   ✗   │
    └─────────────┘

Legend:
  ✓ = Can attack (attacker wins)
  ✗ = Cannot attack (same type or defender wins)
  
Rules:
  Rock (R) defeats Scissors (S)
  Scissors (S) defeats Paper (P)
  Paper (P) defeats Rock (R)
```

### Snail (NPC) Combat
```
         TARGET
       R   P   S
    ┌─────────────┐
  🐌│ ✓   ✓   ✓   │ Snail defeats ALL types
    └─────────────┘

         ATTACKER
       R   P   S
    ┌─────────────┐
🐌 │ ✗   ✗   ✗   │ Snail is INVULNERABLE
    └─────────────┘

Snail Rules:
  - Snail can attack any player piece (ignores RPS)
  - Players cannot attack or move onto Snail
  - Movement behavior changes with distance:
    * Close (<100 cells): Moves 1 cell RANDOMLY toward target (unpredictable zigzag)
    * Far (≥100 cells): Moves 1% of distance in STRAIGHT line (fast but predictable)
  - Snail tracks the oldest player on the grid
  - Block hash provides deterministic randomness
```

## Movement Patterns

### King Move (Adjacent - FREE)
```
    ╔═══╗
    ║ ░ ║  Moving to any adjacent cell (8 directions)
    ╚═══╝  costs 0 energy

    ░ ░ ░
    ░ P ░  P = Player piece
    ░ ░ ░  ░ = Valid move (cost: 0)
```

### Queen Move (Straight Line - distance²)
```
    ║       Moving in straight lines (4 directions)
  ══╬══     costs distance² energy
    ║
    P       P = Player piece

Examples:
  1 cell  = 1² = 1 energy
  2 cells = 2² = 4 energy
  3 cells = 3² = 9 energy
  5 cells = 5² = 25 energy
```

### Invalid Moves
```
    ░ ╳ ░
    ╳ P ╳  P = Player piece
    ░ ╳ ░  ░ = Valid move
           ╳ = Invalid (diagonal, not adjacent)

Diagonal moves beyond adjacent are INVALID
(not straight line, not adjacent)
```

## Combat Energy Flow

### Successful Attack (50 energy to winner)
```
Before Combat:
┌──────────┐         ┌──────────┐
│ Rock (R) │  →→→    │ Scissors │
│ 100 E    │  Attack │ 150 E    │
└──────────┘         └──────────┘
                     (Vulnerable)

After Combat:
┌──────────┐         ┌──────────┐
│ Rock (R) │         │          │
│ 150 E    │         │ DEFEATED │
└──────────┘         └──────────┘
   +50E                    ↓
                     Remaining 150E
                           ↓
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    40% Market        30% Random         30% Burn
    (60E sold)        (45E on grid)     (45E removed)
```

### Energy Distribution Detail
```
Victim's Total Energy = X
  ↓
├─ 50 → Attacker (fixed reward)
└─ X-50 → Distributed as:
          ├─ 40% → Sold on Whaleswap (market impact)
          ├─ 30% → Placed randomly on grid (pickup)
          └─ 30% → Burned (removed from circulation)
```

## Game Economy Flow

```
          ┌─────────────────────────────────┐
          │      Player joins game           │
          │      (100 energy payment)        │
          └───────────────┬─────────────────┘
                          │
          ┌───────────────▼─────────────────┐
          │     Piece spawns on grid         │
          │     (Random empty location)      │
          └───────────────┬─────────────────┘
                          │
          ┌───────────────▼─────────────────┐
          │      Movement Phase              │
          │  - King move: FREE               │
          │  - Queen move: distance² energy  │
          │    → Goes to liquidity pool      │
          └───────┬─────────────┬────────────┘
                  │             │
         Empty Cell        Enemy Cell
         Collect Pickup    Initiate Combat
                  │             │
                  ▼             ▼
          ┌─────────────────────────────────┐
          │      Combat Resolution           │
          │  - Winner gains 50 energy        │
          │  - Loser energy distributed      │
          │  - Market sale impacts price     │
          └───────────────┬─────────────────┘
                          │
                          ▼
          ┌─────────────────────────────────┐
          │     Energy Market (Whaleswap)    │
          │  - Buy energy (low price)        │
          │  - Sell energy (high price)      │
          │  - Liquidity grows over time     │
          └─────────────────────────────────┘
```

## Strategic Considerations

### Energy Management
```
High Energy (>100):
  ✓ Aggressive play
  ✓ Long-range queen moves
  ✓ Hunt vulnerable enemies
  ✓ Escape from Snail
  
Medium Energy (50-100):
  ~ Balanced play
  ~ Short queen moves
  ~ Defensive positioning
  ~ Monitor Snail location
  
Low Energy (<50):
  ✗ Defensive only
  ✗ King moves only
  ✗ Avoid combat
  ✗ Collect pickups
  ! HIGH RISK from Snail
```

### Survival Priority (Oldest Player = Snail Target)
```
Being the oldest player makes you the Snail's target!

⚠️  DUAL THREAT SYSTEM:
    Close Range (<100 cells):
      - Snail moves 1 cell/block (slow) BUT UNPREDICTABLE
      - Random zigzag approach - can't be predicted
      - Perpendicular movement doesn't help
      
    Long Range (≥100 cells):
      - Snail moves 1% of distance (FAST)
      - Straight line pursuit (predictable)
      - At 500 cells: Snail moves 5x faster!

Strategies for oldest player:
  - NO SAFE ZONE: Both close and far are dangerous
  - CONSTANT MOVEMENT: Never stay still
  - Keep high energy for emergency queen moves
  - Flee to 150-200 cells: Predictable but manageable speed
  - DON'T flee beyond 300 cells (speed too high)
  - Consider "retiring" and respawning to reset age
  
Strategies for newer players:
  - Let oldest player absorb Snail attention
  - Stay ~150 cells from Snail (not too close, not too far)
  - Spawn often to reset your "age"
  - Exploit Snail as moving obstacle
```

### Market Timing
```
Energy Price Chart:
      High │     ▲
           │    ╱ ╲
     Price │   ╱   ╲
           │  ╱     ╲▁
      Low  │▁╯       ╲
           └────────────→ Time

Strategy:
  Low Price:  Buy energy → Spawn pieces → Play aggressive
  High Price: Sell energy → Reduce activity → Wait for dip
```

### Positioning Strategy

#### Aggressive Positioning (Hunter)
```
    S   P   R      Hunt vulnerable types
    · · · · ·      Explore outward from spawn
    · · X · ·      X = Your piece
    · · · · ·      Cover maximum area
```

#### Defensive Positioning (Scavenger)
```
    · · · · S      Explore far from spawn
    · · · · ·      Collect pickups in outer regions
    · · · · ·      Avoid enemy types
    · · · · X      X = Your piece (far from 0,0)
```

#### Territorial Control (Farmer)
```
    R · · · R      Control region far from spawn
    · · · · ·      Guard energy spawns
    · · ◆ · ·      ◆ = Energy pickup
    · · · · ·      Defend territory
    R · · · R      Note: Origin (0,0) is spawn chaos zone
```

## Type Selection Strategy

### Rock
- **Hunts**: Scissors (abundant beginners)
- **Flees**: Paper (experienced players)
- **Strategy**: Aggressive early game

### Paper  
- **Hunts**: Rock (aggressive players)
- **Flees**: Scissors (counters)
- **Strategy**: Counter-aggressive play

### Scissors
- **Hunts**: Paper (passive players)
- **Flees**: Rock (most common threat)
- **Strategy**: Opportunistic, evasive

### Meta-game Evolution
```
Early Game:     Many Rocks → Play Paper
Mid Game:       Many Papers → Play Scissors  
Late Game:      Balanced types → Tactical positioning
```

## Example Game Scenario

```
Block 1: Player A spawns Rock - Pays 100 energy
       Grid: [0,0] = Rock(A) with 100 energy

Block 2: Player B spawns Scissors - Pays 100 energy
       Grid: [0,0] = Rock(A, 100E), Scissors(B, 100E)

Block 3: Player A moves Rock to (1, 0) - King move (FREE)
       Grid: [0,0]  = Scissors(B, 100E)
             [1,0]  = Rock(A, 100E)

Block 4: Player B moves Scissors to (0, 1) - King move (FREE)
       Grid: [0,1]  = Scissors(B, 100E)
             [1,0]  = Rock(A, 100E)

Block 5: Player A moves Rock to (0, 1) - Attacks Scissors!
       Combat: Rock defeats Scissors
       - Rock(A): 100 → 150 energy (+50)
       - Scissors(B): DEFEATED
       - 50E distributed: 20E→market, 15E→grid, 15E→burn
       Grid: [0,1] = Rock(A, 150E)
             [3,2] = 15E pickup (random)

Block 6: Player C spawns Paper - Pays 100 energy
       Grid: [0,0]  = Paper(C, 100E)
             [0,1]  = Rock(A, 150E)
             [3,2]  = 15E pickup

Block 7: Player C moves Paper to (0, 1) - Attacks Rock!
       Combat: Paper defeats Rock
       - Paper(C): 100 → 150 energy (+50)
       - Rock(A): DEFEATED (was 150E)
       - 100E distributed: 40E→market, 30E→grid, 30E→burn
       
       Market Impact: 40E energy sold → Price drops 5%
       
       Grid: [0,1]  = Paper(C, 150E)
             [-5,3] = 30E pickup (random)
             [3,2]  = 15E pickup (from earlier)
```

## Winning Conditions

There is no single "winner" - success is measured by:

1. **Survival Time**: How long your pieces survive
2. **Combat Record**: Kills vs Deaths ratio
3. **Energy Accumulated**: Total energy earned
4. **Economic Profit**: Buy low, sell high on market
5. **Territory Control**: Dominate regions of the grid

The game is perpetual - players can join anytime and play indefinitely!

---

**Visual Guide Version**: 0.1  
**Last Updated**: 2025-11-11  
**See Also**: spec.md, ARCHITECTURE.md

