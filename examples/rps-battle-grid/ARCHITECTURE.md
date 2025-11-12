# RPS Grid Battle - Architecture

## System Overview

**Implementation status (2025-01-XX):**
- Core grid, spawning, movement, combat, and energy collection data flows are live in `script.py`.
- Snail NPC automation is complete with full AI movement, combat, and crontask scheduling.
- Energy routing to Whaleswap and UI layers remain TBD.
- Storage operations rely on the deterministic schema seeded during initialization; helper functions no longer perform defensive lookups or `.get()` accessors, surfacing issues early.
- Movement/combat flows now update state exactly once—no redundant reads or writes—making gas usage and reasoning simpler.
- Data loaded from storage is trusted to match the schema; the script omits redundant casts and conversions that previously cluttered hot paths.
- Piece creation uses module-level functions (not classes) for simplicity and AST minimization.
- Storage helpers (`get_piece()`, `set_piece()`, `get_cell()`, `set_cell()`) inline index construction for cleaner code.
- Piece IDs are plain integers; storage indexes use zero-padding (`{piece_id:010d}`) for lexicographic ordering that matches chronological spawn order, enabling efficient oldest-piece queries.

```
┌─────────────────────────────────────────────────────────┐
│                    Client (Browser/CLI)                  │
│  - Grid visualization                                    │
│  - Player actions (spawn, move)                          │
│  - Energy market interface                               │
└────────────────┬────────────────────────────────────────┘
                 │ HTTP / Cosmos TX
                 ▼
┌─────────────────────────────────────────────────────────┐
│                   Dyson Protocol Node                    │
│  ┌─────────────────────────────────────────────────┐   │
│  │          Script Module (Dyslang)                 │   │
│  │  - Game logic execution                          │   │
│  │  - State transitions                             │   │
│  │  - Validation rules                              │   │
│  └──────────┬─────────────────────────┬──────────────┘   │
│             │                         │                  │
│  ┌──────────▼─────────────┐  ┌───────▼───────────┐     │
│  │   Storage Module       │  │  Whaleswap Module │     │
│  │  - Grid state          │  │  - Energy market  │     │
│  │  - Piece data          │  │  - Liquidity pool │     │
│  │  - Player stats        │  │  - Price oracle   │     │
│  └────────────────────────┘  └───────────────────┘     │
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Bank Module                         │   │
│  │  - Energy token transfers                        │   │
│  │  - Payment validation                            │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Data Flow

### Spawn Piece
```
Player → TX[spawn_piece(type)] + attached MsgSend(100 udys)
  → Validate attached MsgSend message exists
  → Validate payment sent to script address
  → Validate payment amount >= 100 udys
  → Validate payment denom == "udys" (Phase 2)
  → Validate piece_type
  → Generate piece_id
  → Find random empty cell on board using `_find_random_empty_cell()` (up to 20 attempts)
  → Storage: game/pieces/{piece_id}
  → Storage: game/grid/{spawn_x}/{spawn_y}
  → Bank: Transfer 100 udys (via attached message)
  → Return piece_info
```

### Move Piece (with Combat)
```
Player → TX[move_piece(piece_id, target_x, target_y)]
  → Query: game/pieces/{piece_id}
  → Validate ownership & rate limit
  → Get dynamic board boundaries: get_board_bounds() → (min, max)
  → Validate target_x, target_y within bounds [min, max]
  → Calculate movement cost (0 or distance²)
  → Validate target cell
  → Query: game/grid/{target_x}/{target_y}
  
  IF target_empty:
    → Bank: Deduct energy cost
    → Whaleswap: Add liquidity (if queen move)
    → Storage: Update piece position
    → Storage: Update grid cells
    
  IF target_has_energy (EnergyPiece):
    → Bank: Deduct energy cost
    → Storage: Collect energy piece (transfer energy, delete piece, clear cell)
    → Storage: Move attacker into cell (land on same cell)
    
  IF target_has_enemy:
    → Query: game/pieces/{target_piece_id}
    → Validate RPS rules (attacker type > victim type)
    → Combat Resolution:
        - Bank: Transfer 50 energy victim→attacker
      - Bank: Transfer 40% victim energy to market (pending_market_energy)
      - Storage: Place EnergyPiece(30%) in rectangle from (0,0) to combat location (5 attempts), then random board (up to 20 attempts)
        - Bank: Burn 30% victim energy
        - Storage: Delete victim piece
        - Storage: Delete victim grid cell
    → Bank: Deduct movement energy cost
    → Storage: Update attacker position
    → Storage: Update stats
```

### Query Grid State
```
Client → Query[get_grid_state(x_start, y_start, x_end, y_end)]
  → Storage: List game/grid/* with prefix filter
  → For each cell with piece:
      → Storage: Query game/pieces/{piece_id}
  → Return grid_data[]
```

## Storage Schema Details

### Hierarchical Organization

```
game/
├── config
│   ├── join_cost: 100
│   ├── attack_reward: 50
│   ├── spawn_x: 0
│   └── spawn_y: 0
│
├── grid/
│   ├── {x}/{y}                    # Grid cell state
│   │   └── piece_id: int | null  # Piece ID (integer), null if empty (including energy pieces)
│   └── ...
│
├── pieces/
│   ├── {piece_id:010d}            # Piece entity (zero-padded to 10 digits for lexicographic ordering)
│   │   ├── id: int                # Piece ID (same as piece_id in index)
│   │   ├── owner: address
│   │   ├── type: "rock"|"paper"|"scissors"|"snail"|"energy"
│   │   ├── x: int
│   │   ├── y: int
│   │   ├── energy: int
│   │   ├── last_action_block: int
│   │   ├── is_npc: bool
│   │   └── spawn_block: int
│   └── ...
│
├── players/
│   ├── {address}                  # Player stats
│   │   ├── pieces: [piece_id]     # Array of integer piece IDs
│   │   ├── total_kills: int
│   │   └── total_deaths: int
│   └── ...
│
└── state
    ├── total_pieces: int
    ├── total_energy_circulation: int
    ├── pending_market_energy: int
    ├── pending_grid_energy: int
    ├── last_updated_block: int
    └── next_piece_id: int          # Next piece ID counter (starts at 1, 0 reserved for SNAIL_ID)
```

### Storage Helper Functions

The implementation uses inline storage helpers that encapsulate index construction:

- `get_piece(piece_id: int)` - Get piece from `game/pieces/{piece_id:010d}` (zero-padded index)
- `set_piece(piece_id: int, data: dict)` - Set piece at `game/pieces/{piece_id:010d}` (zero-padded index)
- `delete_piece(piece_id: int)` - Delete piece at `game/pieces/{piece_id:010d}` (zero-padded index)
- `get_cell(x: int, y: int)` - Get cell from `game/grid/{x}/{y}`
- `set_cell(x: int, y: int, data: dict)` - Set cell at `game/grid/{x}/{y}`
- `get_board_bounds()` - Get dynamic board boundaries based on `total_pieces`: returns `(min_bound, max_bound)` where `min_bound = -1 * (10 + num_pieces)` and `max_bound = 10 + num_pieces`
- `_find_random_empty_cell(max_attempts: int = 20)` - Find a random empty cell on the board for spawning. Returns `(x, y)` tuple or `(None, None)` if no empty cell found after max attempts
- `_place_energy_on_grid(amount, excluded, center_x, center_y)` - Place energy piece in rectangle from (0,0) to combat location: tries 5 positions in rectangle, then falls back to random board placement (up to 20 attempts)

This approach eliminates repetitive f-string construction and makes the code cleaner and easier to maintain.

### Storage Access Patterns

**High Frequency**:
- `game/pieces/{piece_id:010d}` - Read/Write on every move (zero-padded for lexicographic ordering)
- `game/grid/{x}/{y}` - Read on move validation, Write on position changes

**Medium Frequency**:
- `game/players/{address}` - Read/Write on spawn/death
- `game/grid/*` - Range query for client UI updates

**Low Frequency**:
- `game/config` - Read once at start, rarely updated
- `game/state` - Read for metrics, Write on state changes

## Gas Budget Analysis

### Operation Costs (Estimated)

| Operation | Storage Reads | Storage Writes | Computation | Est. Gas |
|-----------|--------------|----------------|-------------|----------|
| spawn_piece | 3 (config, grid, player) | 3 (piece, grid, player) | Low | ~150K |
| move_piece (king) | 3 (piece, grid src, grid dst) | 3 (piece, grid src, grid dst) | Low | ~180K |
| move_piece (queen) | 4 (+ whaleswap) | 3 | Medium | ~250K |
| combat | 5 (2 pieces, 2 grids, config) | 6 (pieces, grids, stats, random) | High | ~400K |
| get_grid_state | N cells | 0 | Low | ~50K + 10K/cell |

### Optimization Strategies

1. **Batch Grid Queries**: Query multiple cells in single storage list operation
2. **Lazy Loading**: Only query piece details when needed (not on every grid cell)
3. **Computed Fields**: Calculate movement cost without storage, validate before writing
4. **Minimal Updates**: Only update changed fields, avoid full object rewrites

## Security Model

### Access Control
- **Piece Ownership**: Every action validates `get_executor_address() == piece.owner`
- **Rate Limiting**: Check `current_block > piece.last_action_block` (1 action/block/piece)
- **Energy Validation**: Verify sufficient energy before deducting costs

### Attack Vectors & Mitigations

| Attack | Mitigation |
|--------|------------|
| Spawn spam | Requires 100 energy payment per piece |
| Movement spam | 1 action per piece per block rate limit |
| Insufficient energy | Validate balance before deducting |
| Spawn camping | Pieces spawn at random empty locations, reducing spawn camping |
| Concurrent moves | Block-based sequencing ensures determinism |
| Market manipulation | Whaleswap handles slippage & liquidity |
| Piece resurrection | Delete piece entity on death, cannot query |

### Determinism Guarantees

- All randomness uses Python's random module
- Movement order within block is transaction order (deterministic)
- No floating point math (only integers)
- No external API calls (all on-chain)

## Scalability Considerations

### Current Design (Dynamic Bounded Grid)
- **Max Pieces**: Unlimited (constrained by blockchain storage)
- **Board Boundaries**: Dynamic, expands with number of pieces
  - Formula: `min = -1 * (10 + num_pieces)`, `max = 10 + num_pieces`
  - Starts at -10 to 10, grows by ±1 per piece
  - Players restricted to boundaries; Snail NPC not restricted
- **Storage Size**: Grows with active pieces and explored area
- **Query Complexity**: O(n) for grid region queries
- **Block Throughput**: ~10-50 actions/block (depends on gas limit)
- **Coordinate Space**: Integer coordinates within dynamic boundaries (players) or unlimited (snail)
- **NPC Snails**: Autonomous pieces scheduled via crontask, not bound by board limits

### Future Optimizations
- **Spatial Indexing**: Group cells into regions for faster queries
- **Event-Driven Updates**: Use blockchain events for client state sync
- **Off-Chain Rendering**: Move grid visualization off-chain, only store deltas
- **Occupied Region Tracking**: Track min/max coordinates for UI bounds

## Testing Strategy

### Unit Tests (Python)
- Movement validation logic
- Combat resolution rules
- Energy calculations
- RPS type matching

### Integration Tests (Pytest + dysond CLI)
- Spawn piece transaction
- Move piece (king & queen)
- Combat scenario (attack, defend, counter)
- Energy pickup collection
- Market integration (Whaleswap)

### Scenario Tests
- Full game flow: spawn → move → combat → death
- Edge cases: grid boundaries, empty grid, energy exhaustion
- Multi-player: concurrent actions, same block movements
- Economic: energy price impact, liquidity accumulation
- NPC behavior: snail spawning, tracking, combat, heartbeat system for resilience

## Deployment Checklist

- [ ] Register energy token name on nameservice
- [ ] Mint initial energy token supply
- [ ] Create Whaleswap pool (energy/udys)
- [ ] Seed initial liquidity
- [ ] Deploy game script to chain
- [ ] Initialize game config in storage
- [ ] Test spawn on testnet
- [ ] Test movement on testnet
- [ ] Test combat on testnet
- [ ] Deploy client UI
- [ ] Monitor gas usage & optimize
- [ ] Launch mainnet

---

**Document Status**: Architecture draft v0.1  
**Last Updated**: 2025-11-11  
**Next Review**: After Phase 1 implementation

