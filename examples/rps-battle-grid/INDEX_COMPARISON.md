# Index Formatting Comparison: RPS Battle Grid vs Other Scripts

## Summary

This document compares how the RPS Battle Grid script formats storage indexes compared to other scripts in the codebase, focusing on zero-padding patterns for chronological ordering.

## Index Formatting Patterns

### RPS Battle Grid (Current Implementation)

**Piece IDs**: Plain integer counter (`next_piece_id`)
- **Format**: Zero-padded to 10 digits in storage index only (`{piece_id:010d}`)
- **Example**: `1`, `2`, `5` (stored as `0000000001`, `0000000002`, `0000000005`)
- **Storage Path**: `game/pieces/{piece_id:010d}`
- **Special ID**: `0` reserved for SNAIL_ID (snail NPC)
- **Purpose**: Enable lexicographic index ordering to match chronological spawn order

**Benefits**:
- Clean separation: piece_id is plain integer, padding only in storage index
- Lexicographic ordering = chronological ordering
- Can query first piece by index (limit=1) instead of filtering/comparing
- Bounded queries (limit=1) instead of iterating through results
- Type safety: Integer IDs clearer than string IDs

### demo-dwapp/script.py

**Message IDs**: `f"{next_id:06d}"`
- **Format**: Zero-padded to 6 digits
- **Example**: `000001`, `000042`
- **Storage Path**: `ids/{key}` (counter stored separately)
- **Purpose**: Sequential message numbering with lexicographic ordering

**Key Differences**:
- Uses separate counter storage (`ids/{key}`)
- Only pads the counter, not block height
- Simpler structure (single counter vs composite key)

### demo-tew/tew-thunder/tew_thunder.py

**Block Numbers**: `{block_num:010d}`
- **Format**: Zero-padded to 10 digits
- **Example**: `0000000100`
- **Storage Path**: `tew/{instance_id}/l2/blocks/{block_num:010d}`
- **Purpose**: Chronological block ordering in L2 chain

**Key Differences**:
- Uses block number only (not composite with counter)
- Part of hierarchical path structure (`l2/blocks/`)
- Similar padding width (10 digits) to RPS

### examples/ica.py

**Greeting Index**: `greetings_v2/{height:010d}/{caller}`
- **Format**: Zero-padded block height (10 digits) + caller address
- **Example**: `greetings_v2/0000000100/dys1abc...`
- **Storage Path**: Direct index
- **Purpose**: Group greetings by block height, then by caller

**Key Differences**:
- Composite key with block height + identifier
- Block height padded, identifier (caller) not padded
- Hierarchical structure (`greetings_v2/{height}/{caller}`)

### nuance/script.py (from test examples)

**Hot Rating Index**: `rate/tags/{tag_name}/hot/{padded_score:012.05f}/{padded_id:015d}`
- **Format**: Score (12 digits, 5 decimals) + ID (15 digits)
- **Example**: `rate/tags/mytag/hot/000283.06579/000000000000004`
- **Storage Path**: Direct index
- **Purpose**: Sort by rating score, then by ID

**Key Differences**:
- Uses floating-point score as primary sort key
- Very wide padding (15 digits for ID)
- Two-level sorting (score first, then ID)

## Key Differences Summary

| Script | Index Format | Padding Width | Composite Keys | Ordering Strategy |
|--------|-------------|---------------|----------------|-------------------|
| **RPS Battle Grid** | `{id:010d}` (plain integer) | 10 digits | No (simple counter) | Lexicographic = chronological |
| **demo-dwapp** | `{id:06d}` | 6 digits | No (single counter) | Simple sequential |
| **demo-tew** | `{block:010d}` | 10 digits | No (block only) | Chronological blocks |
| **ica** | `{height:010d}/{caller}` | 10 digits (height) | Yes (height + caller) | Group by block, then caller |
| **nuance** | `{score:012.05f}/{id:015d}` | 12+5 (score), 15 (id) | Yes (score + id) | Sort by score, then ID |

## Implementation Details

### RPS Battle Grid Advantages

1. **Zero-padding enables index ordering**: With `{piece_id:010d}`, lexicographic ordering matches chronological spawn order
2. **Bounded queries**: Can use `limit=1` to get oldest piece directly
3. **No iteration needed**: First result is guaranteed oldest (by index order)
4. **Clean separation**: Piece ID is plain integer, padding only in storage index
5. **Simple structure**: Plain counter (no composite keys needed)

### Trade-offs

1. **Wider indexes**: 10-digit padding creates longer keys (~20 chars vs ~5 chars)
2. **No type prefix**: Piece type stored in data, not index (requires filter for type queries)
3. **Special ID**: ID `0` reserved for Snail NPC (not available for player pieces)

## Best Practices Observed

1. **Zero-padding for ordering**: All scripts that need chronological ordering use zero-padding
2. **Consistent width**: Choose padding width based on expected maximum value
3. **Composite keys**: Use when multiple dimensions needed (block + counter, score + id)
4. **Hierarchical paths**: Use `/` separators for logical grouping

## Recommendations

The RPS Battle Grid implementation follows best practices:
- ✅ Zero-padding enables lexicographic ordering
- ✅ Consistent padding width (10 digits)
- ✅ Simple counter structure (no composite keys)
- ✅ Clean separation of ID (integer) and index (padded string)
- ✅ Enables efficient bounded queries (limit=1)

The only consideration is whether 10 digits is sufficient:
- Piece ID counter: 10 digits = up to 9,999,999,999 pieces total (more than enough)
- Special ID `0` reserved for Snail NPC
- `next_piece_id` starts at 1 (0 is reserved)

