# Coverage API Handoff Document

This document explains how to run coverage tests using the Dyson Protocol script query API and aggregate the results.

## Overview

Coverage functions (`coverage_*`) in Dyson scripts return AST node execution data that can be used to visualize which parts of your code were executed and how much gas each node consumed.

## Running Coverage via Query API

### Basic Query

Use `dysond query script run` to execute a coverage function:

```bash
dysond query script run <script_address> <function_name> --kwargs '{}' --extra-code ''
```

### With Extra Code

The `--extra-code` flag allows you to inject additional Python code that runs before the function call. This is useful for setting up test fixtures or mocking:

```bash
dysond query script run dys1abc123... coverage_main \
  --kwargs '{"test_input": 42}' \
  --extra-code 'MOCK_DATA = {"key": "value"}'
```

### REST API Equivalent

```
GET /dysonprotocol/script/v1/run/{address}/{function_name}?kwargs={}&extra_code={}
```

## Coverage Data Format

Coverage functions return an array of tuples with this structure:

```
[[meta], [stats]]
```

Where:
- `meta` = `[lineno, col_offset, end_lineno, end_col_offset, node_type, snippet]`
- `stats` = `[call_count, gas]`

### Example Response

```json
{
  "result": [
    [[1, 0, 4, 38, "FunctionDef", "def fib(n):..."], [5, 1200]],
    [[2, 4, 2, 15, "If", "if n <= 1:"], [5, 800]],
    [[3, 8, 3, 16, "Return", "return n"], [3, 400]],
    [[4, 4, 4, 38, "Return", "return fib(n-1)..."], [0, 0]]
  ]
}
```

### Field Descriptions

| Field | Description |
|-------|-------------|
| `lineno` | Starting line number (1-based) |
| `col_offset` | Starting column offset (0-based) |
| `end_lineno` | Ending line number |
| `end_col_offset` | Ending column offset |
| `node_type` | Python AST node type (FunctionDef, If, Return, Call, etc.) |
| `snippet` | Source code snippet for this node |
| `call_count` | Number of times this node was executed (0 = uncovered) |
| `gas` | Gas consumed by this node |

## Aggregating Multiple Coverage Results

When running multiple coverage functions, aggregate results by taking the **maximum call count** and **sum of gas** for each unique AST node.

### Aggregation Algorithm

```python
def aggregate_coverage(results: list[list]) -> list:
    """
    Aggregate coverage from multiple coverage function results.

    Args:
        results: List of coverage results from multiple functions

    Returns:
        Aggregated coverage data
    """
    coverage_map = {}

    for coverage_data in results:
        for entry in coverage_data:
            meta, stats = entry
            lineno, col_offset, end_lineno, end_col_offset, node_type, snippet = meta
            calls, gas = stats

            # Create unique key for this AST node
            key = f"{lineno}:{col_offset}:{end_lineno}:{end_col_offset}"

            if key in coverage_map:
                # Aggregate: max calls, sum gas
                existing = coverage_map[key]
                existing['calls'] = max(existing['calls'], calls or 0)
                existing['gas'] = existing['gas'] + (gas or 0)
            else:
                coverage_map[key] = {
                    'calls': calls or 0,
                    'gas': gas or 0,
                    'meta': meta
                }

    # Convert back to coverage format
    return [
        [entry['meta'], [entry['calls'], entry['gas']]]
        for entry in coverage_map.values()
    ]
```

### JavaScript/TypeScript Implementation

```typescript
interface CoverageEntry {
  meta: [number, number, number, number, string, string];
  stats: [number, number];
}

function aggregateCoverage(results: CoverageEntry[][]): CoverageEntry[] {
  const coverageMap = new Map<string, { calls: number; gas: number; meta: any }>();

  for (const coverageData of results) {
    for (const [meta, [calls, gas]] of coverageData) {
      const [lineno, colOffset, endLineno, endColOffset] = meta;
      const key = `${lineno}:${colOffset}:${endLineno}:${endColOffset}`;

      const existing = coverageMap.get(key);
      if (existing) {
        existing.calls = Math.max(existing.calls, calls || 0);
        existing.gas = existing.gas + (gas || 0);
      } else {
        coverageMap.set(key, {
          calls: calls || 0,
          gas: gas || 0,
          meta,
        });
      }
    }
  }

  return Array.from(coverageMap.values()).map(({ meta, calls, gas }) => [
    meta,
    [calls, gas],
  ]);
}
```

## Calculating Coverage Statistics

```typescript
function calculateStats(coverage: CoverageEntry[]) {
  const totalNodes = coverage.length;
  const coveredNodes = coverage.filter(([, [calls]]) => calls > 0).length;
  const coveragePercent = totalNodes > 0
    ? Math.round((coveredNodes / totalNodes) * 100)
    : 0;
  const maxCalls = Math.max(...coverage.map(([, [calls]]) => calls), 1);
  const maxGas = Math.max(...coverage.map(([, [, gas]]) => gas), 1);

  return {
    totalNodes,
    coveredNodes,
    coveragePercent,
    maxCalls,
    maxGas,
  };
}
```

## Example: Running All Coverage Functions

```python
import requests

def get_script_functions(script_address: str, node_url: str = "http://localhost:1317") -> list[str]:
    """Get list of function names from a script."""
    resp = requests.get(f"{node_url}/dysonprotocol/script/v1/script_info/{script_address}")
    resp.raise_for_status()
    functions = resp.json().get("script", {}).get("functions", [])
    return [f["function_name"] for f in functions if f.get("function_name")]


def run_all_coverage_functions(script_address: str, node_url: str = "http://localhost:1317") -> list:
    """Run all coverage_* functions and return aggregated results."""
    functions = get_script_functions(script_address, node_url)
    coverage_functions = [f for f in functions if f.startswith("coverage_")]

    all_results = []
    for func_name in coverage_functions:
        print(f"Running {func_name}...")
        resp = requests.get(
            f"{node_url}/dysonprotocol/script/v1/run/{script_address}/{func_name}",
            params={"kwargs": "{}"}
        )
        if resp.ok:
            result = resp.json().get("result", [])
            if isinstance(result, dict) and "result" in result:
                result = result["result"]
            all_results.append(result)
            print(f"  Got {len(result)} nodes")
        else:
            print(f"  Failed: {resp.text}")

    return all_results


# Usage
script_address = "dys1abc123..."
results = run_all_coverage_functions(script_address)
```

## Dashboard Integration

The dashboard's `CoveragePanel.vue` component automates this process:

1. Detects `coverage_*` functions in the script
2. Runs all coverage functions
3. Aggregates results using the algorithm above
4. Dispatches `dyson:script-coverage` event with aggregated data
5. `ScriptEditor.vue` receives the event and highlights uncovered code

### Events

| Event | Payload | Description |
|-------|---------|-------------|
| `dyson:script-coverage` | `{ address, functionName, coverageData }` | New coverage data available |
| `dyson:coverage-mode` | `{ mode: 'coverage' \| 'performance' }` | Change visualization mode |
| `dyson:coverage-clear` | `{ address }` | Clear coverage visualization |

## Visualization Modes

### Coverage Mode
- Highlights **uncovered** nodes (call_count = 0) in red
- Covered nodes are not highlighted (to avoid overlap issues with nested AST nodes)

### Performance (Gas) Mode
- Highlights nodes based on gas consumption
- Yellow for low gas usage, red for high gas usage
- Useful for identifying expensive code paths

## Writing Coverage Functions

Coverage functions should exercise specific code paths and return the coverage data from the dyslang runtime:

```python
def coverage_happy_path():
    """Test the main success path."""
    result = my_function(valid_input=True)
    return __coverage__  # Returns coverage data

def coverage_error_handling():
    """Test error handling paths."""
    try:
        my_function(valid_input=False)
    except:
        pass
    return __coverage__

def coverage_edge_cases():
    """Test boundary conditions."""
    my_function(value=0)
    my_function(value=-1)
    my_function(value=MAX_VALUE)
    return __coverage__
```

## Runtime Coverage Tests with Extra Code

You can define coverage tests at runtime using `--extra-code` without storing them in the script. This is useful for:
- Running ad-hoc coverage tests during development
- Testing scripts you don't own
- CI/CD pipelines that inject test code

### Basic Pattern

Define a `coverage_*` function in `extra_code` and call it:

```python
import requests

script_address = "dys1abc123..."
extra_code = """
def coverage_runtime():
    # Exercise code paths
    my_function(1)
    my_function(2)
    other_function("test")
    return __coverage__
"""

response = requests.get(
    f"http://localhost:1317/dysonprotocol/script/v1/run/{script_address}/coverage_runtime",
    params={"extra_code": extra_code}
)
coverage_data = response.json()["result"]
```

### Testing Specific Functions

```python
# Test a fibonacci function with various inputs
extra_code = """
def coverage_fib():
    fib(0)
    fib(1)
    fib(5)
    fib(10)
    return __coverage__
"""

response = requests.get(
    f"http://localhost:1317/dysonprotocol/script/v1/run/{script_address}/coverage_fib",
    params={"extra_code": extra_code}
)
```

### Testing Error Paths

```python
# Test exception handling
extra_code = """
def coverage_errors():
    # Test valid inputs
    transfer(sender="dys1...", amount=100)

    # Test error paths
    try:
        transfer(sender="invalid", amount=-1)
    except:
        pass

    try:
        transfer(sender="dys1...", amount=0)
    except:
        pass

    return __coverage__
"""

response = requests.get(
    f"http://localhost:1317/dysonprotocol/script/v1/run/{script_address}/coverage_errors",
    params={"extra_code": extra_code}
)
```

### Complete Python Example

```python
import requests
from typing import Any

def run_coverage(
    script_address: str,
    test_name: str,
    test_body: str,
    node_url: str = "http://localhost:1317"
) -> list:
    """
    Run a coverage test with runtime-defined function.

    Args:
        script_address: The script address to test
        test_name: Name for the coverage function (will be prefixed with coverage_)
        test_body: Python code to execute (indented automatically)
        node_url: Dyson node REST API URL

    Returns:
        Coverage data array
    """
    # Build the coverage function
    indented_body = "\n".join(f"    {line}" for line in test_body.strip().split("\n"))
    extra_code = f"""
def coverage_{test_name}():
{indented_body}
    return __coverage__
"""

    response = requests.get(
        f"{node_url}/dysonprotocol/script/v1/run/{script_address}/coverage_{test_name}",
        params={"extra_code": extra_code}
    )
    response.raise_for_status()

    result = response.json().get("result", [])
    # Handle nested result object
    if isinstance(result, dict) and "result" in result:
        result = result["result"]

    return result


def aggregate_coverage(results: list[list]) -> list:
    """
    Aggregate coverage from multiple test runs.

    Args:
        results: List of coverage results from multiple functions

    Returns:
        Aggregated coverage data
    """
    coverage_map = {}

    for coverage_data in results:
        if not coverage_data:
            continue
        for entry in coverage_data:
            meta, stats = entry
            lineno, col_offset, end_lineno, end_col_offset, node_type, snippet = meta
            calls, gas = stats

            key = f"{lineno}:{col_offset}:{end_lineno}:{end_col_offset}"

            if key in coverage_map:
                existing = coverage_map[key]
                existing["calls"] = max(existing["calls"], calls or 0)
                existing["gas"] = existing["gas"] + (gas or 0)
            else:
                coverage_map[key] = {
                    "calls": calls or 0,
                    "gas": gas or 0,
                    "meta": meta
                }

    return [
        [entry["meta"], [entry["calls"], entry["gas"]]]
        for entry in coverage_map.values()
    ]


def calculate_stats(coverage: list) -> dict:
    """Calculate coverage statistics."""
    total_nodes = len(coverage)
    covered_nodes = sum(1 for _, (calls, _) in coverage if calls > 0)
    coverage_percent = round((covered_nodes / total_nodes) * 100) if total_nodes > 0 else 0

    return {
        "total_nodes": total_nodes,
        "covered_nodes": covered_nodes,
        "coverage_percent": coverage_percent,
    }


# Example usage
if __name__ == "__main__":
    script_address = "dys1abc123..."

    # Define test cases
    tests = [
        ("happy_path", """
            create_order(price=100, quantity=10)
            execute_order(order_id=1)
        """),
        ("edge_cases", """
            create_order(price=0, quantity=0)
            create_order(price=-1, quantity=1)
        """),
        ("error_handling", """
            try:
                create_order(price="invalid", quantity="bad")
            except:
                pass
            try:
                execute_order(order_id=999999)
            except:
                pass
        """),
    ]

    # Run all tests and collect results
    results = []
    for test_name, test_body in tests:
        print(f"Running coverage_{test_name}...")
        try:
            coverage = run_coverage(script_address, test_name, test_body)
            results.append(coverage)
            print(f"  Got {len(coverage)} nodes")
        except Exception as e:
            print(f"  Failed: {e}")

    # Aggregate results
    aggregated = aggregate_coverage(results)
    stats = calculate_stats(aggregated)

    print(f"\nCoverage Report:")
    print(f"  {stats['coverage_percent']}% covered")
    print(f"  {stats['covered_nodes']}/{stats['total_nodes']} nodes")
```

### CLI Usage

The CLI is also available with `--extra-code`:

```bash
dysond query script run <address> coverage_test --extra-code 'def coverage_test():
    my_function(42)
    return __coverage__'
```

### Advantages of Runtime Coverage Tests

1. **No script modification required** - Test any script without deploying changes
2. **Flexible test scenarios** - Define tests based on current needs
3. **CI/CD friendly** - Inject tests from your repository
4. **Isolation** - Each test runs independently
5. **Version control** - Keep tests in your repo, not on-chain

## Troubleshooting

### Coverage data is empty
- Ensure the function returns `__coverage__`
- Check that the function actually executes code paths

### All nodes show as covered
- The coverage function might be calling a parent function that covers all child nodes
- Write more targeted coverage functions for specific branches

### Visualization not appearing
- Check browser console for errors
- Verify the script address matches between CoveragePanel and ScriptEditor
- Ensure coverage data format is valid (array of `[[meta], [stats]]` tuples)
