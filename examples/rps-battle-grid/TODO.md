# RPS Grid Battle - Implementation TODO

## Phase 1: Core Grid & Movement ⏳

### Storage Schema
- [ ] Implement `initialize_game()` function
  - [x] Define config structure
  - [ ] Test storage initialization
  - [ ] Verify config persistence

### Piece Spawning
- [ ] `spawn_piece(piece_type)` implementation
  - [ ] Validate piece_type ("rock", "paper", "scissors")
  - [ ] Generate unique piece_id (use block height + counter)
  - [ ] Spawn at origin (0, 0)
  - [ ] Store piece entity in `game/pieces/{piece_id}`
  - [ ] Update grid cell in `game/grid/0/0` (multiple pieces can stack at spawn)
  - [ ] Update player stats in `game/players/{address}`
  - [ ] Update global state counter
  - [ ] Return spawn info

### Movement System
- [ ] `move_piece(piece_id, target_x, target_y)` implementation
  - [ ] Query piece data from storage
  - [ ] Validate ownership (`get_executor_address() == piece.owner`)
  - [ ] Validate rate limit (current_block > last_action_block)
  - [ ] Calculate movement type (king vs queen)
  - [x] Calculate movement cost (`calculate_movement_cost()`)
  - [ ] Validate target cell state (empty only in Phase 1)
  - [ ] No bounds checking needed (infinite grid)
  - [ ] Update piece position in storage
  - [ ] Update source grid cell (clear)
  - [ ] Update target grid cell (set piece_id)
  - [ ] Update piece.last_action_block
  - [ ] Return movement result

### Query Functions
- [ ] `get_grid_state(x_start, y_start, x_end, y_end)`
  - [ ] Query grid cells in range
  - [ ] For each cell with piece, query piece details
  - [ ] Return structured grid data for rendering
  - [ ] Optimize with prefix queries

- [x] `get_config()` - basic implementation
- [x] `get_piece_info(piece_id)` - basic implementation
- [x] `get_player_pieces(address)` - basic implementation
- [x] `get_player_stats(address)` - basic implementation

### Testing
- [ ] Write test: `test_initialize_game`
- [ ] Write test: `test_spawn_piece_basic`
- [ ] Write test: `test_spawn_piece_at_origin`
- [ ] Write test: `test_multiple_pieces_at_spawn`
- [ ] Write test: `test_move_piece_king`
- [ ] Write test: `test_move_piece_queen`
- [ ] Write test: `test_move_cost_calculation`
- [ ] Write test: `test_invalid_moves`
- [ ] Write test: `test_rate_limiting`
- [ ] Write test: `test_ownership_validation`

### Documentation
- [x] spec.md - completed
- [x] ARCHITECTURE.md - completed
- [x] README.md - completed
- [ ] Phase 1 completion summary

---

## Phase 2: Combat & Energy Economics 📋

### Combat System
- [ ] `execute_combat(attacker_id, victim_id)`
  - [ ] Query attacker and victim pieces
  - [ ] Validate RPS rules (attacker type beats victim type)
  - [ ] Transfer 50 energy from victim to attacker
  - [ ] Distribute victim remaining energy:
    - [ ] 40% to market (sell on Whaleswap)
    - [ ] 30% place random on grid
    - [ ] 30% burn/remove
  - [ ] Delete victim piece entity
  - [ ] Clear victim grid cell
  - [ ] Update player stats (kills/deaths)
  - [ ] Return combat result

### Movement with Energy Costs
- [ ] Integrate energy costs into `move_piece()`
  - [ ] Validate piece has sufficient energy
  - [ ] Deduct movement cost from piece.energy
  - [ ] Transfer queen-move costs to liquidity pool
  - [ ] Update piece energy in storage

### Energy Pickups
- [ ] `collect_energy(piece_id, x, y)` implementation
  - [ ] Validate piece at location
  - [ ] Transfer energy from cell to piece
  - [ ] Clear cell energy_amount
  - [ ] Return collection result

- [ ] `place_energy_random(amount)` implementation
  - [ ] Find random empty grid cell
  - [ ] Store energy_amount in grid cell
  - [ ] Return placement location

### Combat Integration in Movement
- [ ] Modify `move_piece()` to handle combat
  - [ ] Detect if target cell has enemy piece
  - [ ] Validate enemy piece type (vulnerable to attacker)
  - [ ] Check if target is snail (cannot attack snail)
  - [ ] Call `execute_combat()` on landing
  - [ ] Handle combat success/failure
  - [ ] Update positions after combat

### Snail NPC System
- [ ] `spawn_snail()` implementation (called once in initialize_game)
  - [ ] Create snail with piece_id = "snail" (fixed ID)
  - [ ] Spawn at (0, 0)
  - [ ] Set type="snail", is_npc=True, energy=999999
  - [ ] Set spawn_block = current_block
  - [ ] Store snail piece in game/pieces/snail
  - [ ] Update grid cell game/grid/0/0
  - [ ] Schedule first move using crontask (1 block from now)
  
- [ ] `move_snail_ai()` implementation (no arguments - single snail)
  - [ ] Query snail piece from storage (piece_id = "snail")
  - [ ] Get current position (x, y)
  - [ ] Query all player pieces (is_npc=False)
  - [ ] If no players exist, skip to scheduling next move
  - [ ] Find oldest player (min spawn_block)
  - [ ] Calculate distance to target
    - [ ] dx = target_x - x, dy = target_y - y
    - [ ] distance = sqrt(dx² + dy²) (euclidean)
  - [ ] Calculate movement speed
    - [ ] speed = max(1, floor(distance * 0.01))
  - [ ] Calculate new position based on distance:
    - [ ] IF distance < 100 (CLOSE RANGE - Random movement):
      - [ ] Generate list of 8 king moves: [(0,1), (1,0), (0,-1), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]
      - [ ] Filter to directions that reduce distance to target
      - [ ] Get block hash for deterministic randomness
      - [ ] Select random direction: block_hash % len(valid_directions)
      - [ ] new_x = x + chosen_direction[0]
      - [ ] new_y = y + chosen_direction[1]
    - [ ] ELSE (LONG RANGE - Straight line):
      - [ ] Normalize direction: (dx/distance, dy/distance)
      - [ ] new_x = x + floor(dir_x * speed)
      - [ ] new_y = y + floor(dir_y * speed)
      - [ ] Clamp to target if overshoot
  - [ ] Execute movement to new position
    - [ ] Update snail piece in storage (game/pieces/snail)
    - [ ] Update grid cells (clear old cell, set new cell)
  - [ ] If new position equals target, execute combat
    - [ ] Snail always wins (ignores RPS rules)
    - [ ] Destroy player piece
    - [ ] Distribute player energy
    - [ ] Snail immediately retargets next oldest player
  - [ ] Schedule next move with crontask
    - [ ] Use MsgCreateTask with MsgExec to call move_snail_ai()
    - [ ] Schedule 1 block in future (SNAIL_MOVE_BLOCKS)

### Payment Validation
- [ ] Validate spawn payment (100 energy)
  - [ ] Check attached messages for energy transfer
  - [ ] Verify transfer amount and denom
  - [ ] Reject spawn if insufficient payment

### Testing
- [ ] Write test: `test_combat_rock_beats_scissors`
- [ ] Write test: `test_combat_scissors_beats_paper`
- [ ] Write test: `test_combat_paper_beats_rock`
- [ ] Write test: `test_combat_energy_transfer`
- [ ] Write test: `test_combat_energy_distribution`
- [ ] Write test: `test_movement_energy_deduction`
- [ ] Write test: `test_energy_pickup_collection`
- [ ] Write test: `test_spawn_payment_validation`
- [ ] Write test: `test_insufficient_energy_movement`
- [ ] Write test: `test_combat_in_movement_flow`
- [ ] Write test: `test_snail_spawn`
- [ ] Write test: `test_snail_tracks_oldest_player`
- [ ] Write test: `test_snail_defeats_any_type`
- [ ] Write test: `test_player_cannot_attack_snail`
- [ ] Write test: `test_snail_crontask_scheduling`

---

## Phase 3: Whaleswap Integration 📋

### Energy Token Setup
- [ ] Register energy token name on nameservice
  - [ ] Choose denom name (e.g., `rpsgrid.energy.dys`)
  - [ ] Commit-reveal registration
  - [ ] Set Harberger valuation
  - [ ] Mint initial supply

### Market Creation
- [ ] Create Whaleswap pool
  - [ ] Pair: energy token / udys
  - [ ] Set fee percentage (e.g., 0.3%)
  - [ ] Seed initial liquidity
  - [ ] Test pool operations

### Automated Market Integration
- [ ] Movement → Liquidity Addition
  - [ ] Calculate energy cost from queen moves
  - [ ] Call Whaleswap `MsgAddLiquidity`
  - [ ] Add energy + proportional udys to pool
  - [ ] Track liquidity added

- [ ] Combat → Market Sale
  - [ ] Calculate 40% of victim energy
  - [ ] Call Whaleswap `MsgSwap` (energy → udys)
  - [ ] Handle slippage and price impact
  - [ ] Distribute sale proceeds

### Price Oracle
- [ ] Query energy price from pool
  - [ ] Calculate current exchange rate
  - [ ] Display in UI for player strategy
  - [ ] Cache price to reduce queries

### Testing
- [ ] Write test: `test_energy_token_creation`
- [ ] Write test: `test_whaleswap_pool_setup`
- [ ] Write test: `test_movement_liquidity_addition`
- [ ] Write test: `test_combat_market_sale`
- [ ] Write test: `test_energy_price_impact`
- [ ] Write test: `test_market_integration_flow`

---

## Phase 4: Optimization & Features 📋

### Performance Optimizations
- [ ] Optimize grid queries
  - [ ] Implement spatial indexing (region grouping)
  - [ ] Batch storage operations
  - [ ] Minimize redundant queries
  
- [ ] Gas optimizations
  - [ ] Profile gas usage per operation
  - [ ] Reduce storage writes
  - [ ] Optimize data structures
  - [ ] Target < 300K gas per action

### Player Features
- [ ] Leaderboard system
  - [ ] Track kills/deaths globally
  - [ ] Sort by kills descending
  - [ ] Display top 10 players
  
- [ ] Player statistics
  - [ ] Total pieces spawned
  - [ ] Total energy earned/spent
  - [ ] Win/loss ratio
  - [ ] Average piece lifetime

### UI Improvements
- [ ] WSGI web interface
  - [ ] Grid visualization (HTML canvas or SVG)
  - [ ] Real-time updates (polling or events)
  - [ ] Player action forms (spawn, move)
  - [ ] Energy market display
  - [ ] Player stats dashboard

- [ ] Client-side rendering
  - [ ] Query grid state efficiently
  - [ ] Display pieces with types
  - [ ] Show energy pickups
  - [ ] Highlight valid moves
  - [ ] Show energy prices

### Advanced Features (Optional)
- [ ] Territory control mechanics
  - [ ] Zone ownership
  - [ ] Passive energy generation
  
- [ ] Team battles
  - [ ] Alliance system
  - [ ] Shared resources
  
- [ ] Power-ups
  - [ ] Temporary buffs
  - [ ] Special abilities
  
- [ ] NFT pieces
  - [ ] Unique pieces with perks
  - [ ] Tradeable on marketplace

### Testing
- [ ] Write test: `test_grid_query_performance`
- [ ] Write test: `test_gas_usage_benchmarks`
- [ ] Write test: `test_leaderboard_sorting`
- [ ] Write test: `test_concurrent_players`
- [ ] Write test: `test_full_game_scenario`

---

## Deployment Checklist 📋

### Testnet Deployment
- [ ] Deploy script to testnet
- [ ] Initialize game config
- [ ] Test spawn with multiple accounts
- [ ] Test movement scenarios
- [ ] Test combat scenarios
- [ ] Test market integration
- [ ] Monitor gas usage
- [ ] Collect user feedback

### Mainnet Preparation
- [ ] Security audit
  - [ ] Review access control
  - [ ] Verify rate limiting
  - [ ] Test edge cases
  - [ ] Validate economic model
  
- [ ] Documentation
  - [ ] Player guide
  - [ ] API documentation
  - [ ] Deployment guide
  
- [ ] Monitoring
  - [ ] Set up metrics tracking
  - [ ] Configure alerts
  - [ ] Dashboard for game state

### Launch
- [ ] Deploy to mainnet
- [ ] Initialize game
- [ ] Seed energy market
- [ ] Announce to community
- [ ] Monitor initial gameplay
- [ ] Hot fixes if needed

---

## Notes

**Priority**: Phase 1 → Phase 2 → Phase 3 → Phase 4

**Blockers**: None currently

**Dependencies**: 
- Dyson Protocol node running
- Test accounts with funds
- Whaleswap module available (Phase 3)

**Next Action**: Implement `initialize_game()` and write first test

**Last Updated**: 2025-11-11

