# Hypothesis-Based Whaleswap Testing

Property-based testing for whaleswap using Hypothesis to discover edge cases and invariant violations.

## Architecture

All operations execute in a **single `dysond query script exec`** call for:
- **Speed**: No waiting for blocks
- **Determinism**: Same inputs → same outputs
- **Atomicity**: All messages succeed or all fail together

### Flow

```
Hypothesis → Message Sequence → dysond query script exec → Invariant Check
               ↓                          ↓                        ↓
        [Setup + Test Ops]       MsgSudo wrapper            Balance/Pool/Offer
```

### Key Files

- `whaleswap_executor.py`: Dyslang script that executes messages with MsgSudo
- `test_whaleswap_hypothesis.py`: Hypothesis property tests
- `conftest.py`: Fixtures (only creates accounts, everything else happens in query exec)

## Running Tests

### Basic Sanity Tests

```bash
# Run sanity tests to verify infrastructure works
pytest tests/whaleswap/hypothesis/test_whaleswap_hypothesis.py::test_executor_script_basic -v
pytest tests/whaleswap/hypothesis/test_whaleswap_hypothesis.py::test_name_registration_in_script -v
pytest tests/whaleswap/hypothesis/test_whaleswap_hypothesis.py::test_pool_creation_in_script -v
```

### Hypothesis Tests

```bash
# Run hypothesis tests (default: 10-50 examples each)
pytest tests/whaleswap/hypothesis/ -v

# Run with more examples (bug hunting mode)
pytest tests/whaleswap/hypothesis/ -v --hypothesis-seed=12345

# Run specific test with verbose hypothesis output
pytest tests/whaleswap/hypothesis/test_whaleswap_hypothesis.py::test_make_trade_mixed_operations -v --hypothesis-verbosity=verbose
```

### Extended Campaign

```bash
# Run 1000+ examples per test (overnight run)
pytest tests/whaleswap/hypothesis/ -v --maxfail=1
```

## Test Coverage

### AMM & Orderbook Tests

1. **test_make_trade_multiple_swaps_same_pool**: Multiple swaps on same pool in one MakeTrade
   - Targets bug from deleted `test_cli_make_trade_reused_pool_two_legs.py`
   - 1-3 swaps, random amounts 10-500

2. **test_make_trade_multiple_takes_same_offer**: Multiple takes on same offer in one MakeTrade
   - Targets offer accounting bugs
   - 1-3 takes, 1-5 units each

3. **test_make_trade_mixed_operations**: Mix of swaps and takes in one MakeTrade
   - **Highest risk scenario** for accounting bugs
   - 0-2 swaps + 0-2 takes (at least 1 operation)

### Leveraged Positions Tests

4. **test_leverage_sanity_open_close_basic**: Sanity test with known-good params
   - Validates infrastructure before hypothesis tests
   - Fixed parameters: 100k pool, 3k collateral, 1k borrow

5. **test_open_close_position_random_amounts**: Full position lifecycle with random amounts
   - Pool reserves: 50k-500k
   - Collateral: 2k-50k, Borrow: 500-20k
   - Validates open → close with profit/loss accounting

6. **test_partial_close_position_random_fractions**: Partial closes with random fractions
   - Close fractions: 10%-90%
   - Tests partial → full close sequence
   - Validates remaining position health

7. **test_multiple_positions_same_pool**: Multiple positions on same pool
   - 2-4 positions with independent tracking
   - Validates borrow cap enforcement
   - Tests closing one position doesn't affect others

8. **test_position_edge_cases**: Boundary conditions
   - min_collateral: CR exactly at minimum (1.5x)
   - max_borrow: At pool's max_borrow_percent limit
   - tiny_amounts: Minimum viable position sizes

9. **test_pool_creation_random_params**: Pool parameter fuzzing
   - Fee rates: 0.1%-10%
   - Interest rates: 0%-30%
   - Min CR: 1.1x-5.0x
   - Validates wide parameter ranges

### Invariants Checked

- **Module Balance**: `module_balance == escrowed_pool + escrowed_liquid + fees`
- **Pool Reserves**: No negative amounts, exactly 2 coins per pool
- **Offer Consistency**: `remaining_units * unit_have == remaining_have`

## Adding New Tests

### 1. Add Message Generator

```python
@st.composite
def my_operation(draw, ...):
    """Generate operation messages."""
    # Use draw() to sample from strategies
    return {...}
```

### 2. Add Test Function

```python
@given(params=st.integers(min_value=1, max_value=10))
@settings(max_examples=20, deadline=None)
def test_my_scenario(chainnet, hypo_accounts, executor_script_path, params):
    # 1. Build setup messages
    # 2. Build test operation messages  
    # 3. Execute via script
    # 4. Check invariants
```

### 3. Add Invariant Check (if needed)

```python
# In whaleswap_executor.py
def check_my_invariant(result):
    """Check domain-specific invariant."""
    errors = []
    # ... validation logic ...
    return errors
```

## When Hypothesis Finds a Bug

Hypothesis will **automatically shrink** the failing example to minimal reproduction:

```bash
# Example output:
Falsifying example: test_make_trade_mixed_operations(
    num_swaps=1,
    num_takes=1,
    swap_amounts=[100],
    take_units=[1]
)
```

Then:
1. Copy the minimal example to a new regression test
2. Investigate the root cause
3. Fix the bug
4. Keep the regression test

## Tuning

### Hypothesis Settings

```python
@settings(
    max_examples=100,      # More examples = more coverage
    deadline=None,         # No timeout for slow blockchain ops
    derandomize=True,      # Reproducible runs
)
```

### Message Complexity

Adjust in strategy definitions:
- `min_size`/`max_size` for lists
- `min_value`/`max_value` for integers
- `min_val`/`max_val` for coin amounts

## Architecture Notes

### Why MsgSudo?

- **Bypasses signer validation**: Can execute messages on behalf of any account
- **Governance authority only**: Secure (only gov module can call it)
- **Perfect for testing**: Execute any message sequence atomically

### Why Query Exec?

- **No gas limits**: Query execution has unlimited gas
- **No blocks**: Instant execution, no waiting
- **Deterministic**: Same message sequence → same result
- **Fast**: Can run 1000s of examples quickly

### Limitations

- **No time progression**: Can't test time-dependent logic (auctions, valuations)
- **Single block**: Can't test multi-block scenarios
- **Setup overhead**: Each test regenerates names (but this is actually good for isolation)

## Leveraged Positions Testing

### Block Delay Workaround

**Problem**: By default, `block_delay_before_close` and `block_delay_before_liquidation` are set to `1`, requiring at least one block to pass before positions can be closed or liquidated. In query exec, blocks don't advance, making same-transaction testing impossible.

**Solution**: Use `MsgUpdateParams` via `MsgSudo` to set both delays to `0` at the start of each test.

```python
# First message in every leverage test
messages.append({
    "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
    "authority": gov_addr,
    "params": {
        # ... other params ...
        "block_delay_before_close": "0",
        "block_delay_before_liquidation": "0",
    },
})
```

**Why This Works**:
- Params validation was modified to allow `0` for testing
- Production deployments use governance to set `>= 1`
- Query exec can now open and close positions in same transaction

### Running Leverage Tests

```bash
# Run sanity test first
pytest tests/whaleswap/hypothesis/test_leverage_positions_hypothesis.py::test_leverage_sanity_open_close_basic -v

# Run all leverage tests
pytest tests/whaleswap/hypothesis/test_leverage_positions_hypothesis.py -v

# Run with more examples (bug hunting)
pytest tests/whaleswap/hypothesis/test_leverage_positions_hypothesis.py -v --hypothesis-seed=12345
```

### Leverage Test Invariants

- **Position Health**: CR >= min_collateral_ratio when open
- **Pool Accounting**: total_borrowed == sum(position.borrowed)
- **Collateral Return**: Correct profit/loss calculations
- **Module Balance**: Escrowed collateral + pool reserves balanced
- **Partial Close**: Remaining position stays healthy
- **Borrow Caps**: max_borrow_percent enforced across positions

