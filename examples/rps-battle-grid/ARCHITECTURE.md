# RPS Grid Battle - Architecture

## System Overview

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
Player → TX[spawn_piece(type)] 
  → Validate 100 energy payment
  → Validate piece_type
  → Generate piece_id
  → Spawn at (0, 0)
  → Storage: game/pieces/{piece_id}
  → Storage: game/grid/0/0 (append to stack)
  → Bank: Transfer 100 energy
  → Return piece_info
```

### Move Piece (with Combat)
```
Player → TX[move_piece(piece_id, target_x, target_y)]
  → Query: game/pieces/{piece_id}
  → Validate ownership & rate limit
  → Calculate movement cost (0 or distance²)
  → Validate target cell
  → Query: game/grid/{target_x}/{target_y}
  
  IF target_empty:
    → Bank: Deduct energy cost
    → Whaleswap: Add liquidity (if queen move)
    → Storage: Update piece position
    → Storage: Update grid cells
    
  IF target_has_energy:
    → Bank: Deduct energy cost + collect pickup
    → Storage: Update piece position + clear pickup
    
  IF target_has_enemy:
    → Query: game/pieces/{target_piece_id}
    → Validate RPS rules (attacker type > victim type)
    → Combat Resolution:
        - Bank: Transfer 50 energy victim→attacker
        - Bank: Transfer 40% victim energy to market
        - Whaleswap: Sell energy for udys
        - Storage: Place 30% on random grid cell
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
│   │   ├── piece_id: string       # Present if piece on cell
│   │   └── energy_amount: int     # Present if energy pickup
│   └── ...
│
├── pieces/
│   ├── {piece_id}                 # Piece entity
│   │   ├── owner: address
│   │   ├── type: "rock"|"paper"|"scissors"
│   │   ├── x: int
│   │   ├── y: int
│   │   ├── energy: int
│   │   └── last_action_block: int
│   └── ...
│
├── players/
│   ├── {address}                  # Player stats
│   │   ├── pieces: [piece_id]
│   │   ├── total_kills: int
│   │   └── total_deaths: int
│   └── ...
│
└── state/
    ├── total_pieces: int
    ├── total_energy_circulation: int
    └── last_updated_block: int
```

### Storage Access Patterns

**High Frequency**:
- `game/pieces/{piece_id}` - Read/Write on every move
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
| Spawn camping | All pieces spawn at (0,0), must move away |
| Concurrent moves | Block-based sequencing ensures determinism |
| Market manipulation | Whaleswap handles slippage & liquidity |
| Piece resurrection | Delete piece entity on death, cannot query |

### Determinism Guarantees

- All randomness uses block hash as seed (deterministic)
- Movement order within block is transaction order (deterministic)
- No floating point math (only integers)
- No external API calls (all on-chain)

## Scalability Considerations

### Current Design (Infinite Grid)
- **Max Pieces**: Unlimited (constrained by blockchain storage)
- **Storage Size**: Grows with active pieces and explored area
- **Query Complexity**: O(n) for grid region queries
- **Block Throughput**: ~10-50 actions/block (depends on gas limit)
- **Coordinate Space**: Integer coordinates (positive and negative)
- **NPC Snails**: Autonomous pieces scheduled via crontask

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
- NPC behavior: snail spawning, tracking, combat, crontask scheduling

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

