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
# Coming soon - implementation pending
# See spec.md for detailed design
```

## Game Rules

### Spawning
- Pay 100 energy tokens to spawn a piece
- Choose Rock, Paper, or Scissors type
- All pieces spawn at origin (0, 0) - move away immediately!

### Movement
- **King Move** (adjacent squares): FREE
- **Queen Move** (straight lines): Costs distance² energy

### Combat
- Attack by moving onto vulnerable enemy type
- Rock > Scissors > Paper > Rock
- Winner gains 50 energy
- Loser's energy is distributed: market sale, random drops, and burn
- **Beware the Snail**: Invulnerable NPC that hunts oldest players

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
- [Tests](./tests/) - Coming soon
- [Scripts](./script.py) - Coming soon

## Development Status

**Current Phase**: Planning & Specification

- [x] Specification complete
- [ ] Core grid & movement (Phase 1)
- [ ] Combat & energy mechanics (Phase 2)  
- [ ] Whaleswap integration (Phase 3)
- [ ] Optimization & UI (Phase 4)

## Contributing

This game is part of the Dyson Protocol examples. Contributions welcome after initial implementation.

## License

See repository root for license information.

