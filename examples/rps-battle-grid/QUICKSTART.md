# RPS Grid Battle - Quick Start Guide

## For Players (When Live)

```bash
# 1. Get some energy tokens
dysond tx bank send <faucet> <your_address> 100rpsgrid.energy.dys --from your_key

# 2. Spawn a piece (requires 100 udys payment)
dysond tx script exec \
  --script-address <game_address> \
  --function-name spawn_piece \
  --args '["rock"]' \
  --attached-message '{"@type":"/cosmos.bank.v1beta1.MsgSend","from_address":"<your_address>","to_address":"<game_address>","amount":[{"denom":"udys","amount":"100"}]}' \
  --from your_key

# 3. Move your piece (move away from spawn!)
dysond tx script exec \
  --script-address <game_address> \
  --function-name move_piece \
  --args '[1, 1, 0]' \
  --from your_key
  # Args: [piece_id (int), target_x (int), target_y (int)]

# 4. View the grid
curl http://<game_address>.localhost:8000/
```

## For Developers

### Prerequisites
```bash
# Ensure you have Dyson Protocol node running
make install

# Start local testnet
dysond start

# Create test accounts
dysond keys add alice
dysond keys add bob
```

### Deploy Game Script

```bash
# Deploy the script
dysond tx script update \
  --code-path ./examples/rps-battle-grid/script.py \
  --from alice \
  --gas 2000000 \
  -y | dysond query wait-tx

# Initialize game config
dysond tx script exec \
  --script-address $(dysond keys show -a alice) \
  --function-name initialize_game \
  --from alice \
  --gas 500000 \
  -y | dysond query wait-tx

# Check game status
dysond query script run \
  --script-address $(dysond keys show -a alice) \
  --function-name get_game_status
```

### Run Tests

```bash
# Install test dependencies
pip install -r dev-requirements.txt

# Run all game tests
pytest tests/examples/rps/ -v

# Run specific test file (combat suite)
pytest tests/examples/rps/test_combat.py -v

# Run with coverage
pytest tests/examples/rps/ --cov=examples/rps-battle-grid
```

### Development Workflow

1. **Edit script.py** - Implement game logic
2. **Run tests** - Verify functionality
3. **Deploy to local node** - Test on chain
4. **Iterate** - Fix bugs, add features

### Useful Commands

```bash
# Query storage directly
dysond query storage get <script_address> --index "game/config"

# List all game pieces
dysond query storage list <script_address> --index-prefix "game/pieces/"

# Check piece info
dysond query script run \
  --script-address <script_address> \
  --function-name get_piece_info \
  --args '[123]'
  # Args: [piece_id (int)]

# View player stats
dysond query script run \
  --script-address <script_address> \
  --function-name get_player_stats \
  --args '["<player_address>"]'
```

## Project Structure

```
examples/rps-battle-grid/
├── README.md              # Project overview
├── spec.md                # Complete specification
├── ARCHITECTURE.md        # Technical architecture
├── GAME_MECHANICS.md      # Visual game mechanics guide
├── TODO.md                # Implementation checklist
├── QUICKSTART.md          # This file
├── script.py              # Main game script (dyslang)
└── tests/                 # Test suite
    ├── test_movement.py
    ├── test_combat.py
    └── test_economics.py
```

## Implementation Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ COMPLETE | Core grid & movement |
| Phase 2 | 🟡 IN PROGRESS | Combat & energy economics |
| Phase 3 | ⚪ PENDING | Whaleswap integration |
| Phase 4 | ⚪ PENDING | Optimization & features |

## Common Issues

### "Out of gas" error
**Solution**: Increase gas limit with `--gas 500000` or higher

### "Piece not found" error
**Solution**: Verify piece_id exists with `get_piece_info()`

### "Invalid move" error  
**Solution**: Check valid move type (king or queen only, not diagonal beyond adjacent)

### Storage not persisting
**Solution**: Ensure transaction succeeded with `dysond query wait-tx <txhash>`

## Key Files to Review

1. **spec.md** - Understanding game design and rules
2. **ARCHITECTURE.md** - System architecture and data flow
3. **script.py** - Implementation entry point
4. **TODO.md** - Current development status

## Contributing

When implementing new features:

1. Read the specification carefully
2. Update TODO.md to track progress  
3. Write tests first (TDD approach)
4. Implement feature in script.py
5. Test on local node
6. Update documentation
7. Submit PR

## Performance Tips

- Use `--gas auto` for complex operations
- Query grid state in regions, not entire grid
- Cache frequently accessed data
- Minimize storage writes
- Use prefix queries for efficient listing

## Security Reminders

- Always validate piece ownership
- Check energy balance before deductions
- Verify rate limits (1 action/block/piece)
- Validate coordinates in bounds
- Use Python's random module for randomness

## Debugging

```python
# Enable debug output in script
print(f"Debug: piece_id={piece_id}, target=({x},{y})")

# Check execution result
dysond query wait-tx <txhash> -o json | python scripts/parse_exec_script_tx.py

# View full storage state
dysond query storage list <script_address> --index-prefix "" | jq .
```

## Resources

- **Dyson Protocol Docs**: `/docs/`
- **Storage Guide**: `/docs/storage_guide.md`
- **Scripting Guide**: `/docs/scripting_guide.md`
- **Whaleswap Guide**: `/docs/whaleswap_guide.md`
- **Example Scripts**: `/examples/`

## Support

- Review documentation in `/docs/`
- Check examples in `/examples/`
- Review test patterns in `/tests/`

---

**Version**: 0.1  
**Last Updated**: 2025-11-11  
**Status**: Phase 2 combat iteration

**Next Steps**: Expand combat features and integrate energy economics (see TODO.md)

