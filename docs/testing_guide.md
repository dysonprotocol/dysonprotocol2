# Dyson Protocol Testing Guide

This guide documents the optimal test structure, patterns, and utilities for testing the Dyson Protocol codebase, with a focus on achieving high Go code coverage through Python integration tests.

## Table of Contents

1. [Testing Philosophy](#testing-philosophy)
2. [Test Structure Overview](#test-structure-overview)
3. [Key Testing Patterns](#key-testing-patterns)
4. [Test Utilities and Fixtures](#test-utilities-and-fixtures)
5. [Single-Block vs Multi-Block Testing](#single-block-vs-multi-block-testing)
6. [Assertion Best Practices](#assertion-best-practices)
7. [Common Pitfalls and Solutions](#common-pitfalls-and-solutions)
8. [Coverage Analysis](#coverage-analysis)

---

## Testing Philosophy

> ⚠️ **CRITICAL RULE #1: NEVER HARDCODE IDs**
> 
> The most common and dangerous mistake in testing is hardcoding IDs (position IDs, pool IDs, auction IDs, etc.). 
> **ALWAYS** create entities within your test and capture their IDs from the response. Tests must be completely 
> self-contained and work on any chain state. See [Pitfall 1: Hardcoding IDs](#pitfall-1-hardcoding-ids) for 
> detailed examples.

### Core Principles

1. **No Assumptions About Chain State**: Tests must be self-contained and create all necessary state within the test itself. Never hardcode IDs or assume pre-existing entities.

2. **Exact Assertions Only**: Use `==` and `is` for comparisons. Avoid `<`, `>`, `in` operators. Tests must break if anything changes - this is a new project, so we prioritize correctness over backwards compatibility.

3. **Type, Shape, Then Values**: Always validate in this order:
   - Type (e.g., `isinstance(result, dict)`)
   - Shape (e.g., `"key" in result`)
   - Specific values (e.g., `result["key"] == expected_value`)

4. **Comprehensive Error Context**: Every assertion should include full diagnostic information in the failure message using f-strings with `json.dumps(data, indent=2)`.

5. **No Conditional Logic**: Avoid `if/else` and `try/except` in tests. These create false positives/negatives. Let errors bubble up naturally.

---

## Test Structure Overview

### Directory Layout

```
tests/
├── conftest.py                    # Global fixtures and utilities
├── utils.py                       # Helper functions (poll_until_condition, etc.)
├── deep_parse.py                  # JSON parsing utility
└── whaleswap/
    └── leverage/
        ├── conftest.py            # Module-specific fixtures
        ├── test_msg_open_position.py
        ├── test_msg_close_position.py
        ├── test_msg_cover_position.py
        └── test_query_position.py
```

### Test File Structure

```python
"""
Module docstring explaining what is being tested.

Include any important context about the functionality,
edge cases, or special considerations.
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


def test_specific_functionality(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test docstring describing the specific scenario."""
    # 1. Setup: Extract fixtures
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    
    # 2. Get gov address for sudo operations
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]
    
    # 3. Define script code (for single-block tests)
    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def test_function(param1, param2):
    # Create necessary state
    result = _sudo({
        "@type": "/some.module.MsgSomething",
        "field": param1
    })
    
    # Query state
    query_result = _query({
        "@type": "/some.module.QuerySomething",
        "id": result["id"]
    })
    
    return {
        "result": result,
        "query": query_result
    }
"""
    
    # 4. Execute script
    kwargs = json.dumps({"param1": alice_addr, "param2": foo_name})
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "test_function",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    
    # 5. Parse and validate response structure
    result = deep_parse(query_result)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    assert result is not None, f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"
    
    # 6. Extract nested result
    demo_result = result["result"]["result"]
    
    # 7. Check for exceptions
    assert query_result.get("exception") is None, f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"
    
    # 8. Validate returned structure
    assert demo_result.get("result") is not None, f"Script should return result. Result: {json.dumps(demo_result, indent=2)}"
    
    # 9. Type assertions
    assert isinstance(demo_result["result"], dict), f"Result should be dict, got {type(demo_result['result'])}"
    
    # 10. Shape assertions
    assert "field1" in demo_result["result"], f"Result missing 'field1' key. Keys: {list(demo_result['result'].keys())}"
    
    # 11. Value assertions
    assert demo_result["result"]["field1"] == expected_value, f"Field1 mismatch: expected {expected_value}, got {demo_result['result']['field1']}"
```

---

## Key Testing Patterns

### Pattern 1: Single-Block State Setup and Query

**Use Case**: Testing queries or read-only operations where state can be created and queried in a single block.

**Advantages**:
- Fast execution (no block waiting)
- Atomic operations (all-or-nothing)
- Simpler to reason about
- Better for coverage of query paths

**Example**:

```python
def test_query_position_basic(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test basic Position query functionality."""
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_position_query(alice_addr, foo_name, bar_name):
    # Create pool
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        # ... other pool config
    })
    
    pool_id = sudo_pool_result["results"][0]["pool_id"]
    
    # Create position
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })
    
    # Query the position (positions start at 1)
    position_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": 1
    })
    
    return {
        "pool_id": pool_id,
        "position_id": 1,
        "position_query": position_query
    }
"""
    
    kwargs = json.dumps({"alice_addr": alice_addr, "foo_name": foo_name, "bar_name": bar_name})
    query_result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "demo_position_query",
        "--kwargs", kwargs,
        "--extra-code", extra_code,
    )
    
    # Parse and validate...
```

**Key Points**:
- Use `dysond query script run` (not `dysond tx script exec`)
- State created via `_sudo` is visible within the same query
- State is NOT persisted to the blockchain
- Perfect for testing query endpoints

### Pattern 2: Multi-Block State Persistence

**Use Case**: Testing scenarios that require state to persist across multiple blocks or transactions.

**Advantages**:
- Tests real transaction flow
- Validates state persistence
- Can test time-dependent logic
- Tests cross-block invariants

**Example**:

```python
def test_multi_block_scenario(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test scenario requiring multiple blocks."""
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    denom1 = leverage_names_and_coins["foo_name"]
    denom2 = leverage_names_and_coins["bar_name"]
    
    # Block 1: Create pool
    # Note: CLI commands may require specific ordering of denoms
    # Check the CLI implementation for requirements
    tx1 = dysond(
        "tx", "whaleswap", "create-pool",
        "--coins", f"1000{denom1},1000{denom2}",
        "--from", alice_name,
    )
    assert tx1.get("code", 1) == 0, f"Transaction failed: {tx1}"
    pool_id = extract_pool_id_from_events(tx1)
    
    # Block 2: Open position
    tx2 = dysond(
        "tx", "whaleswap", "open-position",
        "--pool-id", str(pool_id),
        "--collateral", f"750{denom1}",
        "--borrow", f"500{denom2}",
        "--from", alice_name,
    )
    assert tx2.get("code", 1) == 0, f"Transaction failed: {tx2}"
    
    # Query persisted state
    position = dysond("query", "whaleswap", "position", "1")
    assert position["position"]["position_id"] == "1"
```

**Key Points**:
- Use `dysond tx ...` for state-modifying operations
- Each `tx` command creates a new block
- Use `assert tx.get("code", 1) == 0` to verify success
- Query state between transactions to validate persistence

### Pattern 3: Lexicographic Denom Ordering

**Critical Pattern**: Cosmos SDK canonicalizes coin arrays lexicographically by denom. Never rely on array indices for semantic meaning.

⚠️ **IMPORTANT**: The terms "base" and "quote" are purely user-implied semantics for readability in test code. The blockchain does NOT use or recognize these concepts. All pool configuration parameters (fee_rate, min_collateral_ratio, etc.) are keyed by the actual denom string, not by any base/quote designation. The lexicographic sorting is ONLY to ensure consistent ordering when constructing configuration arrays.

```python
def test_with_denoms(chainnet, leverage_accounts, leverage_names_and_coins):
    """Always sort denoms explicitly and key by denom string."""
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    
    # CORRECT: Sort denoms for consistent array ordering
    # Note: "base" and "quote" are just variable names for readability
    # The chain only cares about the actual denom strings
    base, quote = sorted([foo_name, bar_name])
    
    pool_config = {
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        # Each config parameter is keyed by the ACTUAL denom string
        # NOT by any semantic "base" or "quote" concept
        "fee_rate": [
            {"denom": base, "amount": "0.003"},    # base is just the first denom alphabetically
            {"denom": quote, "amount": "0.003"}    # quote is just the second denom alphabetically
        ]
    }
    
    # CORRECT: Map by denom, not index
    pool_coins = pool_query["pool"]["coins"]
    denom_to_amount = {c["denom"]: int(c["amount"]) for c in pool_coins}
    
    # WRONG: Never do this
    # coin0_amount = pool_coins[0]["amount"]  # DON'T ASSUME INDEX MEANING
    # base_amount = pool_coins[0]["amount"]   # DON'T ASSUME "BASE" IS FIRST
```

---

## Test Utilities and Fixtures

### Core Fixtures (from `tests/conftest.py`)

#### `chainnet`

Provides access to running blockchain nodes.

```python
def test_something(chainnet):
    dysond = chainnet[0]  # First node
    result = dysond("query", "bank", "balances", address)
```

#### `generate_account`

Creates new test accounts with optional funding.

```python
def test_with_accounts(chainnet, generate_account, faucet):
    # Create account with 5M udys
    alice_name, alice_addr = generate_account("alice", faucet_amount=5_000_000)
    
    # Create account with mnemonic
    bob_name, bob_addr, mnemonic = generate_account(
        "bob", 
        faucet_amount=1_000_000,
        return_mnemonic=True
    )
```

**Parameters**:
- `name_prefix`: Base name for the account (random suffix added)
- `faucet_amount`: Amount of udys to fund (default: 1)
- `dysond_bin`: Specific node to use (default: chainnet[0])
- `return_mnemonic`: Return mnemonic phrase (default: False)

**Returns**: `[name, address]` or `[name, address, mnemonic]`

#### `register_name`

Registers a name via commit-reveal in a single transaction.

```python
def test_with_names(chainnet, generate_account, register_name):
    dysond = chainnet[0]
    owner_name, owner_addr = generate_account("owner", faucet_amount=1_000_000)
    
    # Register name with 10udys valuation
    name = register_name(dysond, owner_name, owner_addr, valuation="10udys")
    
    # name is now a string like "abcdef.dys"
```

**Parameters**:
- `dysond_bin`: Node to use
- `owner_keychain_name`: Keychain name of owner
- `owner_addr`: Address of owner
- `valuation`: Initial valuation (default: "10udys")

**Returns**: Registered name string (e.g., "random.dys")

#### `faucet`

Funds an address with udys.

```python
def test_with_funding(chainnet, faucet):
    faucet(some_address, amount=5_000_000)
```

### Module-Specific Fixtures (from `tests/whaleswap/leverage/conftest.py`)

⚠️ **CRITICAL: Session-Scoped Fixtures for Performance**

Module-specific fixtures should be **session-scoped** whenever possible to dramatically reduce test setup time. Session-scoped fixtures run once for the entire test session and are reused across all tests.

**Why This Matters**:
- Name registration requires 3 transactions: commit, reveal, set destination (~3 seconds)
- Coin minting requires name registration + mint transaction (~1 second)
- Session-scoped fixtures can reduce test suite runtime by **50-80%**

**Implementation**: See `tests/whaleswap/leverage/conftest.py` for the complete pattern.

#### `leverage_accounts`

Session-scoped fixture providing 3 pre-funded accounts.

```python
def test_leverage(chainnet, leverage_accounts):
    alice = leverage_accounts["alice"]
    alice_name = alice["name"]
    alice_addr = alice["addr"]
    
    bob = leverage_accounts["bob"]
    charlie = leverage_accounts["charlie"]
```

**Provides**:
- `alice`, `bob`, `charlie` each with:
  - `name`: Keychain name
  - `addr`: Address
  - Initial balance: 5,000,000 udys

**Implementation**: See lines 5-20 in `tests/whaleswap/leverage/conftest.py`

#### `leverage_names_and_coins`

Session-scoped fixture providing 2 registered names with minted coins.

```python
def test_with_coins(chainnet, leverage_names_and_coins):
    foo_name = leverage_names_and_coins["foo_name"]  # e.g., "abcdef.dys"
    bar_name = leverage_names_and_coins["bar_name"]  # e.g., "ghijkl.dys"
    alice_addr = leverage_names_and_coins["alice_addr"]
```

**Provides**:
- `foo_name`: First registered name (1M coins minted)
- `bar_name`: Second registered name (1M coins minted)
- `alice_addr`: Owner address
- Distribution:
  - Alice: 400K of each
  - Bob: 300K of each
  - Charlie: 300K of each

**Implementation**: See lines 23-97 in `tests/whaleswap/leverage/conftest.py`

**Key Pattern Details**:
1. Depends on `register_name` fixture for efficient name registration
2. Calculates mint fees dynamically from chain params
3. Uses multi-coin bank sends for efficient distribution
4. Returns dictionary with descriptive keys for easy access

### Creating Your Own Module-Specific Fixtures

When creating fixtures for a new module, follow this pattern:

**File**: `tests/yourmodule/conftest.py`

```python
import json
import pytest


@pytest.fixture(scope="session")
def yourmodule_accounts(chainnet, generate_account, faucet):
    """
    Create test accounts for yourmodule testing.
    Session-scoped for reuse across all tests.
    """
    dysond = chainnet[0]
    alice = generate_account("yourmodule_alice", faucet_amount=5_000_000)
    bob = generate_account("yourmodule_bob", faucet_amount=5_000_000)
    
    return {
        "alice": {"name": alice[0], "addr": alice[1]},
        "bob": {"name": bob[0], "addr": bob[1]},
    }


@pytest.fixture(scope="session")
def yourmodule_denoms(
    chainnet, generate_account, faucet, register_name, yourmodule_accounts
):
    """
    Register names and mint coins for yourmodule testing.
    Session-scoped for performance.
    """
    dysond = chainnet[0]
    alice_name = yourmodule_accounts["alice"]["name"]
    alice_addr = yourmodule_accounts["alice"]["addr"]
    
    # Register names using the register_name fixture
    denom_a = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    denom_b = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    
    # Calculate mint fees dynamically from chain params
    params = dysond("query", "nameservice", "params")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_amount = 1_000_000
    mint_fee = int(mint_amount * fee_per + 0.99999)  # ceiling
    
    # Mint coins
    for denom in [denom_a, denom_b]:
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"{mint_amount}{denom}",
            "--mint-fee",
            f"{mint_fee}udys",
            "--from",
            alice_name,
        )
    
    # Distribute to bob (multi-coin send is efficient)
    dysond(
        "tx",
        "bank",
        "send",
        alice_addr,
        yourmodule_accounts["bob"]["addr"],
        f"300000{denom_a},300000{denom_b}",
        "--from",
        alice_name,
    )
    
    return {
        "denom_a": denom_a,
        "denom_b": denom_b,
        "alice_addr": alice_addr,
    }
```

**Key Patterns**:
- Use descriptive prefixes (`yourmodule_`) to avoid fixture name collisions
- Always use `scope="session"` for expensive setup (names, coins, accounts)
- Depend on global fixtures from `tests/conftest.py` (see lines 452-549, 959-1043)
- Use `register_name` fixture instead of manual commit-reveal-set_destination
- Calculate mint fees dynamically from chain params (see line 41-43 in example)
- Use multi-coin bank sends for efficient distribution
- Return dictionaries with clear, descriptive keys
- Document scope and purpose in docstrings

**Reference Implementations**:
- **Leverage module**: `tests/whaleswap/leverage/conftest.py` (lines 5-97)
- **Whaleswap setup**: `tests/conftest.py` lines 1245-1380 (`ws_setup_env` fixture)
- **Name registration**: `tests/conftest.py` lines 959-1043 (`register_name` fixture)
- **Account generation**: `tests/conftest.py` lines 452-497 (`generate_account` fixture)

### Utility Functions

#### `deep_parse`

Recursively parses JSON strings in nested structures.

```python
from deep_parse import deep_parse

query_result = dysond("query", "script", "run", ...)
result = deep_parse(query_result)

# Handles cases where result["result"] is a JSON string
# and automatically parses it to a dict
```

**Why It's Needed**: `dysond query script run` returns nested JSON strings that need recursive parsing to access the actual data.

**Implementation**: See `deep_parse.py` in project root (lines 1-27)

#### `poll_until_condition` (from `tests/utils.py`)

Polls a condition until it's true or timeout.

```python
from utils import poll_until_condition

def check_balance():
    bal = dysond("query", "bank", "balances", addr)
    return int(bal["balances"][0]["amount"]) > 1000

poll_until_condition(check_balance, timeout=10, interval=0.5)
```

**Note**: Prefer `dysond query wait-tx` for transaction confirmation over polling.

**Implementation**: See `tests/utils.py`

---

## Single-Block vs Multi-Block Testing

### When to Use Single-Block (`dysond query script run`)

✅ **Use for**:
- Query endpoint testing
- Read-only operations
- Fast iteration during development
- Testing complex state setup without persistence
- Coverage of query handler code paths

❌ **Don't use for**:
- Testing transaction flows
- Time-dependent logic (block height, timestamps)
- Cross-block invariants
- State persistence validation

### When to Use Multi-Block (`dysond tx ...`)

✅ **Use for**:
- Transaction message testing
- State persistence validation
- Time-dependent scenarios
- Cross-block invariants
- Integration testing
- End-to-end user flows

❌ **Don't use for**:
- Simple query testing (slower)
- Rapid iteration (blocks take time)

### Hybrid Approach

Many tests benefit from combining both:

```python
def test_hybrid_approach(chainnet, leverage_accounts):
    """Use tx for state setup, query script for validation."""
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    
    # Use tx to persist state
    tx = dysond("tx", "whaleswap", "create-pool", ..., "--from", alice_name)
    assert tx.get("code", 1) == 0
    pool_id = extract_pool_id(tx)
    
    # Use query script to validate complex state
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"]["address"]
    
    extra_code = """
from dys import _query

def validate_pool(pool_id):
    pool = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
        "pool_id": pool_id
    })
    
    # Complex validation logic here
    return {"pool": pool, "validation": "passed"}
"""
    
    result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "validate_pool",
        "--kwargs", json.dumps({"pool_id": pool_id}),
        "--extra-code", extra_code,
    )
```

---

## Assertion Best Practices

### 1. Always Validate Type First

```python
# CORRECT
assert isinstance(result, dict), f"Expected dict, got {type(result)}: {result}"
assert isinstance(amount, str), f"Amount should be string, got {type(amount)}"

# WRONG
assert result["amount"] == "100"  # Fails with unclear error if result is not dict
```

### 2. Check Shape Before Values

```python
# CORRECT
assert "position" in query_response, f"Missing 'position' key. Keys: {list(query_response.keys())}"
assert "borrowed" in query_response, f"Missing 'borrowed' key. Keys: {list(query_response.keys())}"
borrowed = query_response["borrowed"]
assert borrowed["denom"] == expected_denom

# WRONG
borrowed = query_response["borrowed"]  # KeyError if 'borrowed' missing
```

### 3. Use Exact Comparisons

```python
# CORRECT
assert position_id == 1, f"Position ID should be 1, got {position_id}"
assert denom == foo_name, f"Denom should be {foo_name}, got {denom}"
assert can_close is False, f"Can close should be False, got {can_close}"

# WRONG
assert position_id > 0  # Too permissive
assert denom in [foo_name, bar_name]  # Doesn't test which one
assert not can_close  # Unclear what False means
```

### 4. Provide Comprehensive Error Messages

```python
# CORRECT
assert result.get("code", 1) == 0, f"Transaction failed. Code: {result.get('code')}, Raw log: {result.get('raw_log')}, Full result: {json.dumps(result, indent=2)}"

# WRONG
assert result["code"] == 0  # No context on failure
```

### 5. Handle Type Variations

```python
# Cosmos SDK sometimes returns uint64 as string in JSON
assert isinstance(blocks_until_closeable, (int, str)), f"Should be int or str, got {type(blocks_until_closeable)}"

# When comparing, convert appropriately
assert int(position["position_id"]) == expected_id, f"Position ID mismatch"
```

### 6. Test Cosmos SDK Types

```python
# cosmos.Dec fields are strings
assert isinstance(collateral_ratio, str), f"Collateral ratio should be string (cosmos.Dec)"

# Coin structures
assert isinstance(borrowed, dict), f"Borrowed should be dict (cosmos.Coin)"
assert "denom" in borrowed, f"Borrowed missing 'denom'"
assert "amount" in borrowed, f"Borrowed missing 'amount'"
assert borrowed["denom"] == expected_denom
assert borrowed["amount"] == expected_amount
```

---

## Common Pitfalls and Solutions

### Pitfall 1: Hardcoding IDs

⚠️ **CRITICAL**: This is the most common and dangerous pitfall. Never hardcode any IDs in tests.

**Why This Matters**:
- Tests may run on chains with existing state
- Sequences may start at different values
- Tests must be completely self-contained
- Hardcoded IDs cause flaky, environment-dependent tests

**Common ID Types to NEVER Hardcode**:
- Position IDs (leverage positions)
- Pool IDs
- Auction IDs
- Offer IDs
- NFT token IDs
- Storage entry IDs
- Any auto-incrementing sequence

❌ **Wrong**:
```python
# NEVER do this - assumes position 1 exists and is yours
position_query = _query({
    "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
    "position_id": 1  # ❌ Hardcoded ID!
})

# NEVER do this - assumes pool 1 exists
tx = dysond("tx", "whaleswap", "open-position",
    "--pool-id", "1",  # ❌ Hardcoded ID!
    "--from", alice_name)
```

✅ **Correct**:
```python
# ALWAYS create the entity and capture its ID
position_result = _sudo({
    "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
    "trader": alice_addr,
    "pool_id": pool_id,  # ✅ Using previously captured pool_id
    "collateral": {"denom": bar_name, "amount": "750"},
    "borrow": {"denom": foo_name, "amount": "500"}
})

# Extract the ID from the response
position_id = position_result["results"][0]["position_id"]

# Use the captured ID
position_query = _query({
    "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
    "position_id": int(position_id)  # ✅ Using captured ID
})
```

**For Multi-Block Tests**:
```python
# Create pool and extract ID from events
tx = dysond("tx", "whaleswap", "create-pool", ..., "--from", alice_name)
assert tx.get("code", 1) == 0, f"Pool creation failed: {tx}"

# Extract pool_id from events
pool_id = None
for event in tx.get("events", []):
    if event.get("type") == "dysonprotocol.whaleswap.v1.EventPoolCreated":
        for attr in event.get("attributes", []):
            if attr.get("key") == "pool_id":
                pool_id = int(attr.get("value"))
                break

assert pool_id is not None, f"Failed to extract pool_id from events: {json.dumps(tx, indent=2)}"

# Now use the captured pool_id
tx2 = dysond("tx", "whaleswap", "open-position",
    "--pool-id", str(pool_id),  # ✅ Using captured ID
    "--from", alice_name)
```

### Pitfall 2: Assuming Array Order or Semantic Meaning

❌ **Wrong**:
```python
coin0 = pool["coins"][0]  # Assumes semantic meaning
coin1 = pool["coins"][1]
base_coin = pool["coins"][0]  # Assumes "base" has meaning to the chain
quote_coin = pool["coins"][1]  # The chain doesn't know about "base" or "quote"
```

✅ **Correct**:
```python
# Map by actual denom string - the ONLY thing the chain understands
denom_to_coin = {c["denom"]: c for c in pool["coins"]}
foo_coin = denom_to_coin[foo_name]
bar_coin = denom_to_coin[bar_name]

# If you need sorted order for configuration arrays:
sorted_denoms = sorted([foo_name, bar_name])
# But remember: sorted_denoms[0] is just "alphabetically first"
# NOT "base" or any other semantic concept
```

### Pitfall 3: Using Conditional Logic

❌ **Wrong**:
```python
try:
    result = dysond("query", "whaleswap", "position", "1")
    assert result["position"]["position_id"] == "1"
except Exception:
    pass  # Test passes even if query fails
```

✅ **Correct**:
```python
result = dysond("query", "whaleswap", "position", "1")
assert isinstance(result, dict), f"Expected dict, got {type(result)}"
assert "position" in result, f"Missing 'position' key"
assert result["position"]["position_id"] == "1"
```

### Pitfall 4: Insufficient Error Context

❌ **Wrong**:
```python
assert result["code"] == 0
```

✅ **Correct**:
```python
assert result.get("code", 1) == 0, f"Transaction failed. Code: {result.get('code')}, Raw log: {result.get('raw_log')}, Full result: {json.dumps(result, indent=2)}"
```

### Pitfall 5: Not Handling JSON Nesting

❌ **Wrong**:
```python
query_result = dysond("query", "script", "run", ...)
demo_result = query_result["result"]  # May be a JSON string
```

✅ **Correct**:
```python
from deep_parse import deep_parse

query_result = dysond("query", "script", "run", ...)
result = deep_parse(query_result)
demo_result = result["result"]["result"]
```

### Pitfall 6: Ignoring Sequence Counters

❌ **Wrong**:
```python
# Assuming position IDs start at 0
position_id = 0
```

✅ **Correct**:
```python
# Check the actual implementation or capture from response
# In Dyson, sequences start at 1
position_id = 1  # With comment explaining why
```

---

## Coverage Analysis

### Running Tests with Coverage

```bash
make test COVERAGE_PACKAGES="dysonprotocol.com/x/whaleswap/keeper" PYTEST_ARGS="tests/whaleswap/leverage/ -x --ff --showlocals"
```

**Flags**:
- `COVERAGE_PACKAGES`: Go packages to measure
- `-x`: Stop on first failure
- `--ff`: Run failed tests first
- `--showlocals`: Show local variables on failure

### Reading Coverage Reports

Coverage reports are generated in `coverage/x/whaleswap/keeper/`:

```
coverage/x/whaleswap/keeper/
├── query_leverage_health.go.txt
├── msg_open_position.go.txt
├── msg_close_position.go.txt
└── ...
```

**Example Coverage Report**:
```
File: dysonprotocol.com/x/whaleswap/keeper/query_leverage_health.go
Source: x/whaleswap/keeper/query_leverage_health.go

   1    14: func (k Keeper) Position(ctx context.Context, req *whaleswapv1.QueryPositionRequest) (*whaleswapv1.QueryPositionResponse, error) {
   0    15:     if req == nil {
   0    16:         return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "request cannot be nil")
   0    17:     }
   1    18:     if req.PositionId == 0 {
   1    19:         return nil, cosmossdkerrors.Wrap(sdkerrors.ErrInvalidRequest, "position_id required")
   1    20:     }
   1    21:     pos, err := k.LeveragePositions.Get(ctx, req.PositionId)
   ...

Coverage: 66.7% (12/18 statements)
```

**Coverage Line Format**:
- First number: Execution count (0 = not covered, >0 = covered)
- Second number: Line number in source file
- Code: The actual source code

### Improving Coverage

**Strategy**:
1. Identify uncovered lines in coverage reports
2. Determine what conditions trigger those paths
3. Write tests that exercise those paths
4. Verify coverage improved

**Example**: To cover error paths:
```python
def test_position_query_invalid_id(chainnet):
    """Test Position query with invalid ID."""
    dysond = chainnet[0]
    gov_addr = dysond("query", "auth", "module-account", "gov")["account"]["value"]["address"]
    
    extra_code = """
from dys import _query

def test_invalid_id():
    # This should trigger the position_id == 0 check
    try:
        result = _query({
            "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
            "position_id": 0
        })
        return {"error": "Should have failed"}
    except Exception as e:
        return {"error": str(e), "expected": True}
"""
    
    result = dysond(
        "query", "script", "run",
        "--script-address", gov_addr,
        "--executor-address", gov_addr,
        "--function-name", "test_invalid_id",
        "--extra-code", extra_code,
    )
    
    parsed = deep_parse(result)
    # Validate error was caught
    assert parsed["result"]["result"]["expected"] is True
```

---

## Example: Complete Test

Here's a complete example incorporating all best practices:

```python
"""
Test Position query for leverage positions.

Tests the QueryPosition endpoint which retrieves a single position by ID
with health status, collateral ratio, and liquidation information.
"""

import json
import pytest
from pathlib import Path
from deep_parse import deep_parse


def test_query_position_basic(chainnet, leverage_accounts, leverage_names_and_coins):
    """Test basic Position query functionality with comprehensive validation."""
    # 1. Setup: Extract fixtures
    dysond = chainnet[0]
    alice_addr = leverage_accounts["alice"]["addr"]
    foo_name = leverage_names_and_coins["foo_name"]
    bar_name = leverage_names_and_coins["bar_name"]
    
    # 2. Get gov address for sudo operations
    gov_result = dysond("query", "auth", "module-account", "gov")
    gov_addr = gov_result["account"]["value"]["address"]

    # 3. Define script code
    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(msg_dict):
    return _msg({
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    })

def demo_position_query(alice_addr, foo_name, bar_name):
    # Create pool with sorted denoms for config
    # Note: "base" and "quote" are just variable names for convenience
    # The blockchain only cares about the actual denom strings
    base, quote = sorted([foo_name, bar_name])
    sudo_pool_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": alice_addr,
        "coins": [
            {"denom": foo_name, "amount": "10000"},
            {"denom": bar_name, "amount": "10000"}
        ],
        # All config parameters are keyed by actual denom string
        "fee_rate": [
            {"denom": base, "amount": "0.003"},    # base = alphabetically first denom
            {"denom": quote, "amount": "0.003"}    # quote = alphabetically second denom
        ],
        "min_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "max_leverage_ratio": [
            {"denom": base, "amount": "20.0"},
            {"denom": quote, "amount": "20.0"}
        ],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })

    pool_result = sudo_pool_result["results"][0]
    pool_id = pool_result["pool_id"]

    # Create position
    sudo_position_result = _sudo({
        "@type": "/dysonprotocol.whaleswap.v1.MsgOpenPosition",
        "trader": alice_addr,
        "pool_id": pool_id,
        "collateral": {"denom": bar_name, "amount": "750"},
        "borrow": {"denom": foo_name, "amount": "500"}
    })

    position_result = sudo_position_result["results"][0]
    position_id = 1  # Positions start at 1

    # Query the position
    position_query = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
        "position_id": position_id
    })

    return {
        "pool_id": pool_id,
        "position_id": position_id,
        "position_query": position_query
    }
"""
    
    # 4. Execute script
    kwargs = json.dumps(
        {"alice_addr": alice_addr, "foo_name": foo_name, "bar_name": bar_name}
    )
    query_result = dysond(
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "demo_position_query",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
    )
    
    # 5. Parse response with deep_parse
    result = deep_parse(query_result)
    
    # 6. Validate response structure (Type)
    assert isinstance(result, dict), f"deep_parse should return dict. Got: {type(result)}; full={json.dumps(query_result, indent=2)}"
    
    # 7. Validate response structure (Shape)
    assert result is not None, f"deep_parse returned None. Full query_result: {json.dumps(query_result, indent=2)}"
    assert "result" in result, f"result missing 'result' key. Keys: {list(result.keys())}"
    
    # 8. Extract nested result
    demo_result = result["result"]["result"]
    
    # 9. Check for exceptions
    assert query_result.get("exception") is None, f"Script execution failed with exception: {json.dumps(query_result.get('exception'), indent=2)}"
    
    # 10. Validate script returned expected structure
    assert demo_result.get("pool_id") is not None, f"Script should return pool_id. Result: {json.dumps(demo_result, indent=2)}"
    assert demo_result.get("position_id") is not None, f"Script should return position_id. Result: {json.dumps(demo_result, indent=2)}"
    assert demo_result.get("position_query") is not None, f"Script should return position_query. Result: {json.dumps(demo_result, indent=2)}"
    
    # 11. Extract the position query response
    position_query = demo_result["position_query"]
    
    # 12. Verify the query response structure (Type + Shape)
    assert isinstance(position_query, dict), f"Position query should return dict, got {type(position_query)}"
    assert "position" in position_query, f"Position query missing 'position' key. Keys: {list(position_query.keys())}"
    assert "health_status" in position_query, f"Position query missing 'health_status' key. Keys: {list(position_query.keys())}"
    assert "current_collateral_ratio" in position_query, f"Position query missing 'current_collateral_ratio' key. Keys: {list(position_query.keys())}"
    assert "liquidation_threshold" in position_query, f"Position query missing 'liquidation_threshold' key. Keys: {list(position_query.keys())}"
    assert "borrowed" in position_query, f"Position query missing 'borrowed' key. Keys: {list(position_query.keys())}"
    
    # 13. Verify position details (Type + Values)
    position = position_query["position"]
    assert isinstance(position, dict), f"Position should be dict, got {type(position)}"
    assert int(position["position_id"]) == demo_result["position_id"], f"Position ID mismatch: expected {demo_result['position_id']}, got {position['position_id']}"
    assert position["pool_id"] == demo_result["pool_id"], f"Pool ID mismatch: expected {demo_result['pool_id']}, got {position['pool_id']}"
    assert position["user"] == alice_addr, f"User address mismatch: expected {alice_addr}, got {position['user']}"
    
    # 14. Verify collateral (Type + Shape + Values)
    assert "collateral" in position, f"Position missing 'collateral' key. Keys: {list(position.keys())}"
    collateral = position["collateral"]
    assert collateral["denom"] == bar_name, f"Collateral denom mismatch: expected {bar_name}, got {collateral['denom']}"
    assert collateral["amount"] == "750", f"Collateral amount mismatch: expected '750', got {collateral['amount']}"
    
    # 15. Verify borrowed amount (Type + Shape + Values)
    borrowed = position_query["borrowed"]
    assert borrowed["denom"] == foo_name, f"Borrowed denom mismatch: expected {foo_name}, got {borrowed['denom']}"
    assert borrowed["amount"] == "500", f"Borrowed amount mismatch: expected '500', got {borrowed['amount']}"
    
    # 16. Verify health status (Type)
    health_status = position_query["health_status"]
    assert isinstance(health_status, str), f"Health status should be string, got {type(health_status)}"
    
    # 17. Verify numeric fields are strings (cosmos.Dec format)
    assert isinstance(position_query["current_collateral_ratio"], str), f"Current collateral ratio should be string, got {type(position_query['current_collateral_ratio'])}"
    assert isinstance(position_query["liquidation_threshold"], str), f"Liquidation threshold should be string, got {type(position_query['liquidation_threshold'])}"
    
    # 18. Verify boolean fields
    assert isinstance(position_query["can_close_by_owner"], bool), f"Can close by owner should be bool, got {type(position_query['can_close_by_owner'])}"
    assert isinstance(position_query["can_initialize_liquidation"], bool), f"Can initialize liquidation should be bool, got {type(position_query['can_initialize_liquidation'])}"
```

---

## Summary Checklist

When writing tests, ensure:

- [ ] Test is self-contained (no assumptions about chain state)
- [ ] Uses appropriate fixtures (`chainnet`, `leverage_accounts`, etc.)
- [ ] Chooses correct testing approach (single-block vs multi-block)
- [ ] Validates Type → Shape → Values in that order
- [ ] Uses exact assertions (`==`, `is`) not comparisons (`<`, `>`, `in`)
- [ ] Provides comprehensive error messages with full context
- [ ] Handles lexicographic denom ordering correctly
- [ ] Uses `deep_parse` for nested JSON responses
- [ ] Avoids conditional logic (`if/else`, `try/except`)
- [ ] Captures and uses dynamic IDs (never hardcodes)
- [ ] Documents any assumptions or special considerations
- [ ] Verifies coverage improvement after implementation

---

## Additional Resources

- **Dyslang Guide**: `docs/dyslang_guide.md` - Python scripting in Dyson
- **Scripting Guide**: `docs/scripting_guide.md` - Script execution patterns
- **Storage Guide**: `docs/storage_guide.md` - On-chain storage patterns
- **Nameservice Guide**: `docs/nameservice_guide.md` - Name registration and management
- **Whaleswap Guide**: `docs/whaleswap_guide.md` - Trading and leverage functionality
- **Fix Tests Rule**: `.cursorrules` - Automated test quality rules

---

*This guide is a living document. Update it as new patterns emerge and best practices evolve.*

