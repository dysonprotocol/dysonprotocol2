# RPS Grid Battle - Implementation TODO

## Phase 1: Core Grid & Movement ⏳

### Storage Schema
- [x] Implement `initialize_game()` function
  - [x] Define config structure
  - [x] Test storage initialization
  - [x] Verify config persistence

### Piece Spawning
- [x] `spawn_piece(piece_type)` implementation
  - [x] Validate piece_type ("rock", "paper", "scissors")
  - [x] Generate unique piece_id (use block height + counter)
  - [x] Spawn at random empty location on board (using `_find_random_empty_cell()`)
  - [x] Store piece entity in `game/pieces/{piece_id}`
  - [x] Update grid cell in `game/grid/{spawn_x}/{spawn_y}` (single-piece occupancy)
  - [x] Update player stats in `game/players/{address}`
  - [x] Update global state counter
  - [x] Return spawn info

### Movement System
- [x] `move_piece(piece_id, target_x, target_y)` implementation
  - [x] Query piece data from storage
  - [x] Validate ownership (`get_executor_address() == piece.owner`)
  - [x] Validate rate limit (current_block > last_action_block)
  - [x] Calculate movement type (king vs queen)
  - [x] Calculate movement cost (`calculate_movement_cost()`)
  - [x] Validate target cell state (empty only in Phase 1)
  - [x] No bounds checking needed (infinite grid)
  - [x] Update piece position in storage
  - [x] Update source grid cell (clear)
  - [x] Update target grid cell (set piece_id)
  - [x] Update piece.last_action_block
  - [x] Return movement result

### Query Functions


- [x] `get_config()` - basic implementation
- [x] `get_piece_info(piece_id)` - basic implementation
- [x] `get_player_pieces(address)` - basic implementation
- [x] `get_player_stats(address)` - basic implementation

### Testing
- [x] Write test: `test_initialize_game`
- [x] Write test: `test_spawn_piece_basic`
- [x] Write test: `test_spawn_piece_populates_storage` (verifies random spawn location)
- [x] Write test: `test_multiple_pieces_at_spawn`
  - [x] Write test: `test_move_piece_king`
  - [x] Write test: `test_move_piece_queen`
  - [x] Write test: `test_move_cost_calculation`
  - [x] Write test: `test_invalid_moves`
  - [x] Write test: `test_rate_limiting`
  - [x] Write test: `test_ownership_validation`

### Documentation
- [x] spec.md - completed
- [x] ARCHITECTURE.md - completed
- [x] README.md - completed
- [ ] Phase 1 completion summary

---

## Phase 2: Combat & Energy Economics 📋

### Combat System
- [x] `execute_combat(attacker_id, victim_id)`
  - [x] Query attacker and victim pieces
  - [x] Validate RPS rules (attacker type beats victim type)
  - [x] Transfer 50 energy from victim to attacker
  - [x] Distribute victim remaining energy:
    - [x] 40% to market (sell on Whaleswap)
    - [x] 30% place random on grid
    - [x] 30% burn/remove
  - [x] Delete victim piece entity
  - [x] Clear victim grid cell
  - [x] Update player stats (kills/deaths)
  - [x] Return combat result
  - [x] Create EnergyPiece for grid energy drops (30% of victim remainder)

### Movement with Energy Costs
- [x] Integrate energy costs into `move_piece()`
  - [x] Validate piece has sufficient energy
  - [x] Deduct movement cost from piece.energy
  - [x] Transfer queen-move costs to pending_market_energy
  - [x] Update piece energy in storage

### Energy Pickups
- [x] Energy collection integrated into `move_piece()`
  - [x] Automatically collect energy when landing on energy piece cell
  - [x] Transfer energy from energy piece to collector
  - [x] Delete energy piece
  - [x] Clear cell (energy piece removed, player lands on cell)
  - [x] Return collection result in move summary

- [x] `_place_energy_on_grid(amount, excluded, center_x, center_y)` implementation
  - [x] Try 5 positions in rectangle from (0,0) to combat location
  - [x] Fall back to random board placement (up to 20 attempts) if rectangle fails
  - [x] Create EnergyPiece and store in game/pieces/{piece_id}
  - [x] Set cell.piece_id to energy piece id
  - [x] Return placement location

### Code Refactoring
- [x] Refactor piece model from classes to module-level functions
- [x] Add storage helper functions (get_piece, set_piece, get_cell, set_cell)
- [x] Remove redundant `.get()` calls and `int()` casts
- [x] Simplify logic flows

### Combat Integration in Movement
- [x] Modify `move_piece()` to handle combat
  - [x] Detect if target cell has enemy piece
  - [x] Validate enemy piece type (vulnerable to attacker)
  - [x] Check if target is snail (cannot attack snail)
  - [x] Call `execute_combat()` on landing
  - [x] Handle combat success/failure
  - [x] Update positions after combat

### Snail NPC System
- [x] `spawn_snail()` implementation (called once in initialize_game)
  - [x] Create snail with piece_id = 0 (SNAIL_ID constant, reserved ID)
  - [x] Spawn at (0, 0)
  - [x] Set type="snail", is_npc=True, energy=999999
  - [x] Set spawn_block = current_block
  - [x] Store snail piece in game/pieces/0000000000 (zero-padded index)
  - [x] Update grid cell game/grid/0/0
  - [x] Schedule first move using crontask (1 block from now)
  
- [x] `move_snail_ai()` implementation (no arguments - single snail)
  - [x] Query snail piece from storage (piece_id = 0, SNAIL_ID constant)
  - [x] Get current position (x, y)
  - [x] Query all player pieces (is_npc=False)
  - [x] If no players exist, skip to scheduling next move
  - [x] Find oldest player (min spawn_block) using bounded query with filter
  - [x] Calculate distance to target
    - [x] dx = target_x - x, dy = target_y - y
    - [x] distance = sqrt(dx² + dy²) using integer square root (_isqrt)
  - [x] Calculate movement speed
    - [x] speed = max(1, floor(distance * 0.01))
  - [x] Calculate new position based on distance:
    - [x] IF distance < 100 (CLOSE RANGE - Random movement):
      - [x] Generate list of 8 king moves: [(0,1), (1,0), (0,-1), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]
      - [x] Filter to directions that reduce distance to target
    - [x] Select random direction via Python's random module
      - [x] new_x = x + chosen_direction[0]
      - [x] new_y = y + chosen_direction[1]
    - [x] ELSE (LONG RANGE - Straight line):
      - [x] Normalize direction: (dx/distance, dy/distance)
      - [x] new_x = x + floor(dir_x * speed)
      - [x] new_y = y + floor(dir_y * speed)
      - [x] Clamp to target if overshoot
  - [x] Execute movement to new position
    - [x] Update snail piece in storage (game/pieces/0000000000)
    - [x] Update grid cells (clear old cell, set new cell)
  - [x] If new position equals target, execute combat
    - [x] Snail always wins (ignores RPS rules)
    - [x] Destroy player piece
    - [x] Distribute player energy
    - [x] Snail immediately retargets next oldest player
  - [x] Heartbeat system for resilience
    - [x] Implement snail_heartbeat() function
    - [x] Heartbeat checks if snail needs to move (every 10 blocks)
    - [x] Heartbeat schedules move_snail_ai() if needed
    - [x] Heartbeat always schedules itself (ensures continuity)
    - [x] move_snail_ai() no longer self-schedules

### Payment Validation
- [x] Validate spawn payment (100 udys)
  - [x] Check attached messages for energy transfer
  - [x] Verify transfer amount and denom
  - [x] Reject spawn if insufficient payment

### Testing
- [x] Write test: `test_combat_rock_beats_scissors`
- [x] Write test: `test_combat_scissors_beats_paper`
- [x] Write test: `test_combat_paper_beats_rock`
- [x] Write test: `test_combat_energy_transfer`
- [x] Write test: `test_combat_energy_distribution`
- [x] Write test: `test_movement_energy_deduction`
- [x] Write test: `test_energy_pickup_collection` (may need fixes for complex movement scenarios)
- [x] Write test: `test_spawn_payment_validation`
- [x] Write test: `test_insufficient_energy_movement`
- [x] Write test: `test_combat_in_movement_flow`
- [x] Write test: `test_snail_spawn`
- [x] Write test: `test_snail_tracks_oldest_player`
- [x] Write test: `test_snail_defeats_rock` (tests snail defeats any type)
- [x] Write test: `test_player_cannot_attack_snail`
- [x] Write test: `test_snail_crontask_scheduling`
- [x] Write test: `test_snail_movement_close_range`
- [x] Write test: `test_snail_movement_long_range`

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

**Next Action**: 
- Fix `test_energy_pickup_collection` if needed (simplify movement logic)
- Begin Phase 3: Whaleswap Integration (energy token setup, market creation)
- OR continue Phase 2 polish: Add more edge case tests, optimize energy placement

**Last Updated**: 2025-01-XX

