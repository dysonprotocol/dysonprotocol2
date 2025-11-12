# Documentation Status - Piece ID Refactoring

## Documentation Files

1. **spec.md** - Complete game specification
2. **ARCHITECTURE.md** - Technical architecture and system design
3. **SNAIL_NPC.md** - Snail NPC system documentation
4. **TODO.md** - Implementation checklist
5. **README.md** - Project overview
6. **QUICKSTART.md** - Quick start guide for players and developers
7. **GAME_MECHANICS.md** - Visual game mechanics guide
8. **INDEX_COMPARISON.md** - Comparison of index formatting patterns

## Update Status

### ✅ Fully Updated

1. **spec.md**
   - ✅ Storage schema updated (`piece_id: int`, `game/pieces/{piece_id:010d}`)
   - ✅ Function signatures updated (`piece_id: int`)
   - ✅ Implementation Notes section added
   - ✅ SNAIL_ID references updated (0 instead of "snail")

2. **ARCHITECTURE.md**
   - ✅ Storage schema diagram updated
   - ✅ Helper function signatures updated
   - ✅ System overview note added
   - ✅ Storage access patterns updated

3. **SNAIL_NPC.md**
   - ✅ SNAIL_ID references updated (0 instead of "snail")
   - ✅ Piece ID references updated

4. **INDEX_COMPARISON.md**
   - ⚠️ Needs update (see below)

### ⚠️ Partially Updated / Needs Review

5. **TODO.md**
   - ✅ Most piece_id references updated
   - ⚠️ Still has some generic `{piece_id}` references (acceptable, but could be more specific)

6. **QUICKSTART.md**
   - ⚠️ Line 20: `move_piece("<piece_id>", 1, 0)` - Should show integer example
   - ⚠️ Line 102: `--args '["piece_123"]'` - Should show integer example

7. **README.md**
   - ⚠️ Line 24: `move_piece("<piece_id>", 0, 1)` - Should show integer example
   - ✅ No other piece_id references found

8. **GAME_MECHANICS.md**
   - ✅ No piece_id references found (pure mechanics, no implementation details)

### ❌ Needs Update

9. **INDEX_COMPARISON.md**
   - ❌ Line 11: Still shows old format `{type}_{block_height:010d}_{next_piece_id:010d}`
   - ❌ Line 14: Storage path shows `game/pieces/{piece_id}` (should be `{piece_id:010d}`)
   - ❌ Should reflect that piece_id is now plain integer, not composite string

## Required Updates

### INDEX_COMPARISON.md
```diff
- **Piece IDs**: `{type}_{block_height:010d}_{next_piece_id:010d}`
- **Format**: Zero-padded to 10 digits for both block_height and next_piece_id
- **Example**: `rock_0000000100_0000000005`
- **Storage Path**: `game/pieces/{piece_id}`
+ **Piece IDs**: Plain integer counter (`next_piece_id`)
+ **Format**: Zero-padded to 10 digits in storage index only
+ **Example**: `1`, `2`, `5` (stored as `0000000001`, `0000000002`, `0000000005`)
+ **Storage Path**: `game/pieces/{piece_id:010d}`
+ **Special ID**: `0` reserved for SNAIL_ID
```

### QUICKSTART.md
```diff
- --args '["<piece_id>", 1, 0]'
+ --args '[1, 1, 0]'  # piece_id=1, target_x=1, target_y=0

- --args '["piece_123"]'
+ --args '[123]'  # piece_id=123
```

### README.md
```diff
- move_piece("<piece_id>", 0, 1)
+ move_piece(1, 0, 1)  # piece_id=1, target_x=0, target_y=1
```

## Summary

**Total Files**: 8 documentation files
- **Fully Updated**: 3 files (spec.md, ARCHITECTURE.md, SNAIL_NPC.md)
- **Partially Updated**: 2 files (TODO.md, QUICKSTART.md, README.md)
- **Needs Update**: 1 file (INDEX_COMPARISON.md)
- **No Updates Needed**: 1 file (GAME_MECHANICS.md)

**Priority Updates**:
1. **INDEX_COMPARISON.md** - Critical: Contains incorrect format information
2. **QUICKSTART.md** - Important: Developer examples should show correct format
3. **README.md** - Minor: Quick example should be accurate

