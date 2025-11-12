# RPS Grid Battle

A fully on-chain multiplayer Rock-Paper-Scissors battle game built on Dyson Protocol.

## Overview

RPS Grid Battle is a blockchain game where players spawn pieces (Rock, Paper, or Scissors) on a shared grid and battle for energy tokens. The game combines classic RPS mechanics with spatial strategy and an integrated token economy powered by Whaleswap.

## Key Features

- **Unlimited Multiplayer**: Join anytime, battle anyone on the grid
- **Energy Economy**: Entry costs, movement costs, combat rewards all use tradeable energy tokens
- **Market Integration**: Energy prices fluctuate on Whaleswap, creating strategic timing decisions
- **Turn-Based**: One action per piece per block ensures fair, deterministic gameplay
- **Spatial Strategy**: Choose between cheap local movement or expensive long-range teleportation
- **PvE Threat**: Autonomous Snail NPCs hunt the oldest player, adding survival pressure

## Quick Start

```bash
# 1. Deploy the script (see Quick Start for full command)
# 2. Initialize with `initialize_game()`
# 3. Spawn a piece: `spawn_piece("rock")`
# 4. Move: `move_piece(1, 0, 1)`  # piece_id=1, target_x=0, target_y=1
# 5. Engage combat: move onto a vulnerable enemy
```

## Game Rules

### Spawning
- Pay 100 udys (Phase 2) / 100 energy tokens (Phase 3) to spawn a piece
- Must attach `MsgSend` payment message to `spawn_piece()` transaction
- Choose Rock, Paper, or Scissors type
- Pieces spawn at random empty locations on the board

### Movement
- **King Move** (adjacent squares): FREE
- **Queen Move** (straight lines): Costs distance² energy
- **Board Boundaries**: Dynamic grid that expands with number of pieces
  - Formula: `min = -1 * (10 + num_pieces)`, `max = 10 + num_pieces`
  - Starts at -10 to 10, grows by ±1 per piece spawned
  - Players restricted to boundaries; Snail NPC not restricted

### Combat
- Attack by moving onto vulnerable enemy type
- Rock > Scissors > Paper > Rock
- Winner gains 50 energy
- Loser's energy is distributed: market sale, energy drops (in rectangle from origin to combat), and burn
- **Beware the Snail**: Invulnerable NPC that hunts oldest players (not restricted by board boundaries)

### Energy Market
- All energy is tradeable on Whaleswap
- Movement costs feed liquidity pool
- Combat generates market pressure
- Time your moves with price fluctuations

## Architecture

Built with Dyson Protocol modules:
- **Storage**: Grid state, piece data, energy pickups
- **Script**: Game logic in dyslang (sandboxed Python)
- **Whaleswap**: Energy token market and liquidity
- **Bank**: Token transfers for payments and rewards

## Documentation

- [Specification](./spec.md) - Complete game design and implementation plan
- [Tests](../tests/examples/rps/) - CLI integration tests for spawning, movement, and combat
- [Scripts](./script.py) - Dyslang implementation

## Development Status

**Current Phase**: Phase 2 – Combat Iteration

- [x] Specification complete
- [x] Core grid & movement (Phase 1)
- [ ] Combat & energy mechanics (Phase 2)  
- [ ] Whaleswap integration (Phase 3)
- [ ] Optimization & UI (Phase 4)

## Contributing

This game is part of the Dyson Protocol examples. Contributions welcome after initial implementation.

## License

See repository root for license information.

