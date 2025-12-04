#!/usr/bin/env python3
"""
Pool Stress Test Script

High-level DSL for creating pool scenarios and testing arbitrage detection.

Usage:
    python scripts/pool_stress_test.py --from alice circle --pools 20 --amount 1000
    python scripts/pool_stress_test.py --from alice gradient --pools 20 --start 10 --end 200
    python scripts/pool_stress_test.py --from alice grid --size 3 --amount 1000
    python scripts/pool_stress_test.py --from alice triangle --skew 100
    python scripts/pool_stress_test.py --from alice hub-spoke --spokes 6 --amount 1000
    python scripts/pool_stress_test.py --from alice complete --denoms 3 --pools-per-pair 2

Scenarios:
    circle   - N pools in a circular chain (A→B→C→...→A)
    gradient - N pools of 2 denoms with ratios from start:start to end:end
    grid     - NxN 2D square grid (N² denoms, 2*N*(N-1)+1 pools between adjacent cells + diagonal)
    triangle - 3 pools forming a triangle with optional price skew
    hub-spoke - Hub denom connected to N spoke denoms
    complete - Complete graph: pools between ALL denom pairs (+ optional udys)
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def run_json(command: str) -> dict:
    """Run a shell command and parse JSON output."""
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(f"Command failed: {command}\n{result.stderr}\n")
        raise RuntimeError(f"command exited {result.returncode}")
    return json.loads(result.stdout)


def get_account_address(account: str) -> str:
    """Get bech32 address from key name."""
    result = subprocess.run(
        f"dysond keys show -a {account}",
        shell=True,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to get address for {account}")
    return result.stdout.strip()


def get_gov_address() -> str:
    """Get the governance module address."""
    result = run_json("dysond query auth module-account gov -o json")
    return result["account"]["value"]["address"]


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario DSL
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class PoolSpec:
    """Specification for a single pool."""

    denom0: str
    denom1: str
    amount0: int
    amount1: int
    fee_rate: str = "0.001"

    def to_create_msg(self, creator: str) -> dict:
        """Convert to MsgCreatePool format."""
        base, quote = sorted([self.denom0, self.denom1])
        return {
            "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
            "creator": creator,
            "coins": [
                {"denom": self.denom0, "amount": str(self.amount0)},
                {"denom": self.denom1, "amount": str(self.amount1)},
            ],
            "min_initial_collateral_ratio": [
                {"denom": base, "amount": "1.5"},
                {"denom": quote, "amount": "1.5"},
            ],
            "max_borrow_percent": [
                {"denom": base, "amount": "0.5"},
                {"denom": quote, "amount": "0.5"},
            ],
            "liquidation_threshold": [
                {"denom": base, "amount": "1.2"},
                {"denom": quote, "amount": "1.2"},
            ],
            "fee_rate": [
                {"denom": base, "amount": self.fee_rate},
                {"denom": quote, "amount": self.fee_rate},
            ],
        }


@dataclass
class Scenario:
    """A pool scenario with denoms and pool specifications."""

    name: str
    description: str
    base_denom: str
    subdenoms: list[str] = field(default_factory=list)
    pools: list[PoolSpec] = field(default_factory=list)

    def denoms_to_mint(self) -> dict[str, int]:
        """Calculate how much of each subdenom to mint."""
        needs = {}
        for pool in self.pools:
            for denom, amount in [
                (pool.denom0, pool.amount0),
                (pool.denom1, pool.amount1),
            ]:
                if denom.startswith(self.base_denom + "/"):
                    needs[denom] = needs.get(denom, 0) + amount
        return needs


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario Builders
# ═══════════════════════════════════════════════════════════════════════════════


def build_circle_scenario(base_denom: str, num_pools: int, amount: int) -> Scenario:
    """
    Build a circular chain of pools: A→B→C→...→A

    Each pool has equal amounts (amount:amount).
    Creates num_pools pools and num_pools denoms.
    """
    scenario = Scenario(
        name=f"circle-{num_pools}",
        description=f"{num_pools} pools in circular chain at {amount}:{amount}",
        base_denom=base_denom,
    )

    # Generate subdenom names
    chars = [chr(ord("A") + i) for i in range(num_pools)]
    scenario.subdenoms = [f"{base_denom}/{c}" for c in chars]

    # Create pools connecting adjacent denoms in a circle
    for i in range(num_pools):
        denom0 = scenario.subdenoms[i]
        denom1 = scenario.subdenoms[(i + 1) % num_pools]
        scenario.pools.append(PoolSpec(denom0, denom1, amount, amount))

    return scenario


def build_gradient_scenario(
    base_denom: str, num_pools: int, start: int, end: int
) -> Scenario:
    """
    Build pools of 2 denoms with ratios from start:start to end:end.

    Creates num_pools pools between denom A and denom B with linearly
    increasing amounts.
    """
    scenario = Scenario(
        name=f"gradient-{num_pools}",
        description=f"{num_pools} pools from {start}:{start} to {end}:{end}",
        base_denom=base_denom,
    )

    denom_a = f"{base_denom}/GradA"
    denom_b = f"{base_denom}/GradB"
    scenario.subdenoms = [denom_a, denom_b]

    # Create pools with linearly interpolated amounts
    for i in range(num_pools):
        t = i / max(1, num_pools - 1)  # 0.0 to 1.0
        amount = int(start + t * (end - start))
        scenario.pools.append(PoolSpec(denom_a, denom_b, amount, amount))

    return scenario


def build_grid_scenario(base_denom: str, size: int, amount: int) -> Scenario:
    """
    Build a 2D square grid of denoms with pools connecting adjacent cells.

    For size=3, creates a 3x3 grid:
        1-1  1-2  1-3
        2-1  2-2  2-3
        3-1  3-2  3-3

    Pools connect horizontally and vertically adjacent cells:
        - Horizontal: (1-1↔1-2), (1-2↔1-3), (2-1↔2-2), etc.
        - Vertical: (1-1↔2-1), (2-1↔3-1), (1-2↔2-2), etc.
        - Diagonal shortcut: (1-1↔N-N)

    For NxN grid:
        - Denoms: N²
        - Pools: 2 * N * (N-1) + 1  (horizontal + vertical + diagonal)
    """
    num_denoms = size * size
    num_pools = 2 * size * (size - 1) + 1  # +1 for diagonal shortcut

    scenario = Scenario(
        name=f"grid-{size}x{size}",
        description=f"{size}x{size} grid: {num_denoms} denoms, {num_pools} pools",
        base_denom=base_denom,
    )

    # Generate subdenom names as row-col (1-indexed for readability)
    def denom_name(row: int, col: int) -> str:
        return f"{base_denom}/G{row+1}_{col+1}"

    # Create all denoms
    scenario.subdenoms = [denom_name(r, c) for r in range(size) for c in range(size)]

    # Create horizontal pools (row, col) ↔ (row, col+1)
    for r in range(size):
        for c in range(size - 1):
            scenario.pools.append(
                PoolSpec(denom_name(r, c), denom_name(r, c + 1), amount, amount)
            )

    # Create vertical pools (row, col) ↔ (row+1, col)
    for r in range(size - 1):
        for c in range(size):
            scenario.pools.append(
                PoolSpec(denom_name(r, c), denom_name(r + 1, c), amount, amount)
            )

    # Create diagonal shortcut: (0,0) ↔ (N-1, N-1)
    if size > 1:
        scenario.pools.append(
            PoolSpec(denom_name(0, 0), denom_name(size - 1, size - 1), amount, amount)
        )

    return scenario


def build_triangle_scenario(base_denom: str, skew: int = 1) -> Scenario:
    """
    Build a 3-pool triangle with optional price skew.

    skew=1: All pools 1:1 (balanced, no arbitrage)
    skew=100: Extreme skew creating arbitrage opportunity
              A-B: 100:10000 (A expensive)
              B-C: 100:10000 (B expensive)
              C-A: 100:11000 (C cheap vs A, completing profitable cycle)
    """
    scenario = Scenario(
        name=f"triangle-skew{skew}",
        description=f"3-pool triangle with skew factor {skew}",
        base_denom=base_denom,
    )

    denom_a = f"{base_denom}/TriA"
    denom_b = f"{base_denom}/TriB"
    denom_c = f"{base_denom}/TriC"
    scenario.subdenoms = [denom_a, denom_b, denom_c]

    base_amt = 100
    skewed_amt = base_amt * skew

    # A-B: skewed (A is expensive)
    scenario.pools.append(PoolSpec(denom_a, denom_b, base_amt, skewed_amt))
    # B-C: skewed (B is expensive)
    scenario.pools.append(PoolSpec(denom_b, denom_c, base_amt, skewed_amt))
    # C-A: slightly more skewed to create profit
    scenario.pools.append(PoolSpec(denom_c, denom_a, base_amt, int(skewed_amt * 1.1)))

    return scenario


def build_hub_spoke_scenario(base_denom: str, num_spokes: int, amount: int) -> Scenario:
    """
    Build a hub-and-spoke topology.

    One central HUB denom connected to N spoke denoms (S0, S1, ..., SN-1).
    Creates num_spokes pools (HUB-S0, HUB-S1, ..., HUB-SN-1).

    Optional shortcuts between adjacent spokes can create triangular arbitrage.
    """
    scenario = Scenario(
        name=f"hub-spoke-{num_spokes}",
        description=f"Hub with {num_spokes} spokes at {amount}",
        base_denom=base_denom,
    )

    hub = f"{base_denom}/HUB"
    spokes = [f"{base_denom}/S{i}" for i in range(num_spokes)]
    scenario.subdenoms = [hub] + spokes

    # Create hub-to-spoke pools with varying ratios for arbitrage
    for i, spoke in enumerate(spokes):
        # Alternate between different ratios to create opportunities
        if i % 2 == 0:
            scenario.pools.append(PoolSpec(hub, spoke, amount, amount * 10))
        else:
            scenario.pools.append(PoolSpec(hub, spoke, amount * 10, amount))

    # Add shortcuts between adjacent spokes
    for i in range(0, num_spokes - 1, 2):
        if i + 1 < num_spokes:
            scenario.pools.append(PoolSpec(spokes[i], spokes[i + 1], amount, amount))

    return scenario


def build_complete_graph_scenario(
    base_denom: str,
    num_denoms: int = 3,
    base_amount: int = 1000,
    pools_per_pair: int = 2,
    include_udys: bool = True,
) -> Scenario:
    """
    Build a complete graph of pools between N denoms.

    For N denoms, creates pools between ALL pairs (complete graph).
    With pools_per_pair=2, each pair gets 2 pools with different ratios.

    Args:
        base_denom: Parent denom for subdenoms
        num_denoms: Number of custom denoms to create (e.g., 3 = A, B, C)
        base_amount: Base liquidity amount (scaled for each pool)
        pools_per_pair: Number of pools per denom pair
        include_udys: If True, also create pools connecting to udys

    For num_denoms=3, pools_per_pair=2, include_udys=True:
        - 3 pairs among A,B,C: 3 * 2 = 6 pools
        - 3 pairs to udys: 3 * 1 = 3 pools
        - Total: 9 pools (matching production scenario)
    """
    # Generate denom names
    chars = [chr(ord("A") + i) for i in range(num_denoms)]
    denoms = [f"{base_denom}/{c}" for c in chars]

    # Calculate total pools for naming
    num_pairs = num_denoms * (num_denoms - 1) // 2
    total_pools = num_pairs * pools_per_pair
    if include_udys:
        total_pools += num_denoms

    scenario = Scenario(
        name=f"complete-{num_denoms}x{pools_per_pair}",
        description=f"Complete graph: {num_denoms} denoms, {pools_per_pair} pools/pair, {total_pools} total pools",
        base_denom=base_denom,
        subdenoms=denoms,
    )

    # Create pools between all pairs of custom denoms
    for i in range(num_denoms):
        for j in range(i + 1, num_denoms):
            denom_a = denoms[i]
            denom_b = denoms[j]

            for p in range(pools_per_pair):
                # Vary the ratio and fee for each pool in the pair
                # First pool: balanced, second pool: skewed
                if p == 0:
                    amt_a = base_amount * (i + 1)
                    amt_b = base_amount * (j + 1)
                    fee = "0.001"
                else:
                    # Skew ratio for arbitrage opportunities
                    amt_a = base_amount * (i + 1) * (p + 1)
                    amt_b = base_amount * (j + 1) * (p + 2)
                    fee = f"0.00{p + 2}"  # 0.002, 0.003, ...

                scenario.pools.append(PoolSpec(denom_a, denom_b, amt_a, amt_b, fee))

    # Create pools connecting each denom to udys
    if include_udys:
        for i, denom in enumerate(denoms):
            # Vary ratio based on position (creates price discrepancies)
            amt_denom = base_amount * (i + 1)
            amt_udys = base_amount * 10 * (num_denoms - i)  # Inverse scaling
            scenario.pools.append(PoolSpec(denom, "udys", amt_denom, amt_udys, "0.003"))

    return scenario


# ═══════════════════════════════════════════════════════════════════════════════
# Script Generation
# ═══════════════════════════════════════════════════════════════════════════════


def generate_script_code(
    scenario: Scenario, creator_addr: str, swap_spec: dict | None = None
) -> str:
    """Generate the Python code to run via query script run."""

    # Build mint coins list (add swap amount if needed)
    mint_needs = scenario.denoms_to_mint()

    # Add extra coins for swap if specified
    if swap_spec:
        in_denom = swap_spec["in_denom"]
        # If denom is a suffix, prepend base_denom/
        if "/" not in in_denom:
            in_denom = f"{scenario.base_denom}/{in_denom}"
        mint_needs[in_denom] = mint_needs.get(in_denom, 0) + swap_spec["amount"]

    mint_coins = [{"denom": d, "amount": str(a)} for d, a in mint_needs.items()]

    # Build pool creation calls
    pool_msgs = [pool.to_create_msg(creator_addr) for pool in scenario.pools]

    # Swap spec as JSON for embedding
    swap_spec_json = json.dumps(swap_spec) if swap_spec else "None"

    code = f'''
from dys import _msg, _query, get_executor_address
import json

def _sudo(msg_dict):
    return _msg({{
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": get_executor_address(),
        "messages": [msg_dict]
    }})

def run_scenario(creator_addr, base_denom, arb_params):
    """
    Scenario: {scenario.name}
    {scenario.description}
    """
    swap_spec = {swap_spec_json}
    
    results = {{
        "scenario": "{scenario.name}",
        "pools_created": 0,
        "mint_result": None,
        "pool_results": [],
        "swap_result": None,
        "arbitrage_results": [],
    }}
    
    # Step 0: Set arbitrage mode to MANUAL to prevent auto-arbitrage during pool creation
    ws_params = _query({{"@type": "/dysonprotocol.whaleswap.v1.QueryParamsRequest"}})
    params = ws_params["params"]
    params["arbitrage_mode"] = 2  # ARBITRAGE_MODE_MANUAL
    _sudo({{
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": get_executor_address(),
        "params": params,
    }})
    
    # Step 1: Mint required subdenoms
    mint_coins = {json.dumps(mint_coins, indent=4)}
    
    if mint_coins:
        # Get mint fee
        params = _query({{"@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"}})
        mint_fee_per = float(params["params"]["mint_fee_per_coin"])
        total_units = sum([int(c["amount"]) for c in mint_coins])
        required_fee = int(total_units * mint_fee_per + 0.99999)
        
        # Sort coins by denom
        sorted_coins = sorted(mint_coins, key=lambda c: c["denom"])
        
        mint_result = _sudo({{
            "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
            "name_destination": creator_addr,
            "amount": sorted_coins,
            "mint_fee": {{"denom": "udys", "amount": str(required_fee)}},
        }})
        results["mint_result"] = "success"
    
    # Step 2: Create pools
    pool_msgs = {json.dumps(pool_msgs, indent=4)}
    pool_ids = []
    
    for i, msg in enumerate(pool_msgs):
        pool_result = _sudo(msg)
        pool_id = pool_result.get("results", [{{}}])[0].get("pool_id")
        pool_ids.append(pool_id)
        results["pool_results"].append({{
            "pool_id": pool_id,
            "initial_coins": msg["coins"],
        }})
        results["pools_created"] += 1
    
    # Step 3: Execute swap if specified (POOL_INDEX:AMOUNT:IN_DENOM:OUT_DENOM)
    if swap_spec:
        pool_idx = swap_spec["pool_index"]
        if pool_idx < len(pool_ids):
            target_pool_id = pool_ids[pool_idx]
            in_denom = swap_spec["in_denom"]
            out_denom = swap_spec["out_denom"]
            amount = str(swap_spec["amount"])
            
            # If denom is a suffix, prepend base_denom/
            if "/" not in in_denom:
                in_denom = base_denom + "/" + in_denom
            if "/" not in out_denom:
                out_denom = base_denom + "/" + out_denom
            
            trade_result = _sudo({{
                "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
                "trader": creator_addr,
                "max_input": [{{"denom": in_denom, "amount": amount}}],
                "operations": [{{
                    "swap": {{
                        "pool_id": str(target_pool_id),
                        "swap_in": {{"denom": in_denom, "amount": amount}},
                        "swap_out": {{"denom": out_denom, "amount": "0"}},
                    }}
                }}],
                "min_output": [],
            }})
            results["swap_result"] = {{
                "pool_id": target_pool_id,
                "input": {{"denom": in_denom, "amount": amount}},
                "output_denom": out_denom,
                "outputs": trade_result.get("results", [{{}}])[0].get("trader_outputs", []),
            }}
    
    # Step 4: Query post-trade pool states
    results["post_trade_pools"] = []
    for pool_id in pool_ids:
        pool_resp = _query({{
            "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
            "pool_id": str(pool_id),
        }})
        pool = pool_resp.get("pool", {{}})
        results["post_trade_pools"].append({{
            "pool_id": pool_id,
            "coins": pool.get("coins", []),
            "fee_rate": pool.get("fee_rate", []),
        }})
    
    # Step 5: Run SimulateArbitrage with various parameters
    affected_denoms = list(set(
        [p["coins"][0]["denom"] for p in pool_msgs] +
        [p["coins"][1]["denom"] for p in pool_msgs]
    ))
    
    for arb_param in arb_params:
        req = {{
            "@type": "/dysonprotocol.whaleswap.v1.QuerySimulateArbitrageRequest",
            "trader": creator_addr,
            "affected_denoms": affected_denoms[:5],
            "ref_denom": arb_param.get("ref_denom", "udys"),
            "max_fraction": arb_param.get("max_fraction", "0.1"),
            "max_depth": arb_param.get("max_depth", 2),
        }}
        if arb_param.get("max_splits"):
            req["max_splits"] = arb_param["max_splits"]
        
        arb_result = _query(req)
        results["arbitrage_results"].append({{
            "params": arb_param,
            "found": arb_result.get("found", False),
            "pool_count": arb_result.get("pool_count", 0),
            "profit": arb_result.get("profit", "0"),
            "denoms": arb_result.get("denoms", []),
            "trader_inputs": arb_result.get("trader_inputs", []),
            "trader_outputs": arb_result.get("trader_outputs", []),
            "swap_amounts": arb_result.get("swap_amounts", []),
            "pool_ids": arb_result.get("pool_ids", []),
        }})
    
    return results
'''
    return code


# ═══════════════════════════════════════════════════════════════════════════════
# Execution
# ═══════════════════════════════════════════════════════════════════════════════


def execute_scenario(
    account: str,
    scenario: Scenario,
    arb_params: list[dict],
    swap_spec: dict | None = None,
) -> dict:
    """Execute a scenario via query script run."""

    creator_addr = get_account_address(account)
    gov_addr = get_gov_address()

    print(f"\n{'='*60}")
    print(f"Scenario: {scenario.name}")
    print(f"Description: {scenario.description}")
    print(f"Pools: {len(scenario.pools)}")
    print(f"Subdenoms: {scenario.subdenoms}")
    if swap_spec:
        print(
            f"Swap: pool[{swap_spec['pool_index']+1}] {swap_spec['amount']} {swap_spec['in_denom']} → {swap_spec['out_denom']}"
        )
    print(f"{'='*60}\n")

    # Generate script code
    code = generate_script_code(scenario, creator_addr, swap_spec)

    # Build kwargs
    kwargs = json.dumps(
        {
            "creator_addr": creator_addr,
            "base_denom": scenario.base_denom,
            "arb_params": arb_params,
        }
    )

    # Execute via query script run
    cmd = [
        "dysond",
        "query",
        "script",
        "run",
        "--script-address",
        gov_addr,
        "--executor-address",
        gov_addr,
        "--function-name",
        "run_scenario",
        "--kwargs",
        kwargs,
        "--extra-code",
        code,
        "-o",
        "json",
    ]

    print("Executing scenario...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return {"error": result.stderr}

    try:
        output = json.loads(result.stdout)
        if output.get("exception"):
            print(f"Script exception: {output['exception']}")
            return {"error": output["exception"]}

        # Parse nested result - handle both dict and string formats
        result_data = output.get("result", {})
        if isinstance(result_data, str):
            result_data = json.loads(result_data)

        inner = result_data.get("result", {})
        if isinstance(inner, str):
            inner = json.loads(inner)

        return inner
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        print(f"stdout: {result.stdout[:500]}")
        return {"error": str(e)}


def get_or_create_name(account: str) -> str:
    """Get existing name for account, or return a name to create in simulation."""
    address = get_account_address(account)

    # Check if account already has a name
    try:
        result = run_json(
            f'dysond query nft nfts nameservice.dys --owner "{address}" -o json'
        )
        nfts = result.get("nfts", [])
        if nfts:
            name = nfts[0].get("id")
            print(f"Account {account} already owns name: {name}")
            return name
    except:
        pass

    # Return name to create in simulation
    name = f"{account}.dys"
    print(f"Will create name {name} in simulation")
    return name


def print_results(results: dict) -> None:
    """Pretty print scenario results."""
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    if "error" in results:
        print(f"ERROR: {results['error']}")
        return

    print(f"Scenario: {results.get('scenario', 'unknown')}")
    print(f"Pools created: {results.get('pools_created', 0)}")

    if results.get("mint_result"):
        print(f"Mint: {results['mint_result']}")

    print("\nPools Created:")
    for i, pool in enumerate(results.get("pool_results", [])):
        coins = pool.get("initial_coins", pool.get("coins", []))
        coin_str = " + ".join(f"{c['amount']}{c['denom']}" for c in coins)
        print(f"  [{i+1}] Pool {pool.get('pool_id')}: {coin_str}")

    if results.get("swap_result"):
        swap = results["swap_result"]
        outputs = swap.get("outputs", [])
        out_str = (
            ", ".join(f"{c['amount']}{c['denom']}" for c in outputs)
            if outputs
            else "none"
        )
        print(f"\nSwap Executed:")
        print(
            f"  Pool {swap.get('pool_id')}: {swap.get('input', {}).get('amount')}{swap.get('input', {}).get('denom')} → {out_str}"
        )

    if results.get("post_trade_pools"):
        print("\nPost Trade States:")
        for i, pool in enumerate(results.get("post_trade_pools", [])):
            coins = pool.get("coins", [])
            coin_str = " + ".join(f"{c['amount']}{c['denom']}" for c in coins)
            print(f"  [{i+1}] Pool {pool.get('pool_id')}: {coin_str}")

    print("\nArbitrage Results:")
    for i, arb in enumerate(results.get("arbitrage_results", [])):
        params = arb.get("params", {})
        print(
            f"  [{i+1}] max_depth={params.get('max_depth')}, max_splits={params.get('max_splits')}, ref_denom={params.get('ref_denom')}"
        )
        print(
            f"      Found: {arb.get('found')}, Pools: {arb.get('pool_count')}, Profit: {arb.get('profit')}"
        )

        # Show trader inputs/outputs if found
        inputs = arb.get("trader_inputs", [])
        outputs = arb.get("trader_outputs", [])
        if inputs or outputs:
            in_str = (
                ", ".join(f"{c['amount']}{c['denom']}" for c in inputs)
                if inputs
                else "none"
            )
            out_str = (
                ", ".join(f"{c['amount']}{c['denom']}" for c in outputs)
                if outputs
                else "none"
            )
            print(f"      Inputs: {in_str}")
            print(f"      Outputs: {out_str}")

        # Show pool operations (only non-zero swaps)
        pool_ids = arb.get("pool_ids", [])
        swap_amounts = arb.get("swap_amounts", [])

        # Build pool_id -> coins lookup from post_trade_pools
        pool_coins = {}
        for fp in results.get("post_trade_pools", []):
            pid = fp.get("pool_id")
            coins = fp.get("coins", [])
            if pid and len(coins) >= 2:
                # Shorten denom names for display
                d0 = coins[0].get("denom", "?").split("/")[-1]
                d1 = coins[1].get("denom", "?").split("/")[-1]
                pool_coins[pid] = (d0, d1)

        if pool_ids and swap_amounts:
            # Filter to non-zero swaps
            active_ops = [
                (pid, int(amt) if isinstance(amt, str) else amt)
                for pid, amt in zip(pool_ids, swap_amounts)
                if (int(amt) if isinstance(amt, str) else amt) != 0
            ]

            if active_ops:
                print(f"      Active swaps ({len(active_ops)}/{len(pool_ids)} pools):")
                for pid, amt in active_ops:
                    denoms_str = ""
                    if pid in pool_coins:
                        d0, d1 = pool_coins[pid]
                        if amt > 0:
                            denoms_str = f" ({d0}→{d1})"
                        else:
                            denoms_str = f" ({d1}→{d0})"
                    print(f"        Pool {pid}: {abs(amt)}{denoms_str}")
            else:
                print(f"      Active swaps: none (0/{len(pool_ids)} pools)")

        # Show denoms summary
        denoms = arb.get("denoms", [])
        if denoms:
            short_denoms = [d.split("/")[-1] for d in denoms]
            print(f"      Graph: {len(denoms)} denoms, {len(pool_ids)} pools")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="Pool stress test with various scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--from", dest="account", required=True, help="Account key name"
    )

    subparsers = parser.add_subparsers(dest="scenario", required=True)

    # Circle scenario
    circle_parser = subparsers.add_parser("circle", help="Circular chain of pools")
    circle_parser.add_argument("--pools", type=int, default=20, help="Number of pools")
    circle_parser.add_argument(
        "--amount", type=int, default=1000, help="Amount per pool"
    )

    # Gradient scenario
    gradient_parser = subparsers.add_parser("gradient", help="Gradient of pool ratios")
    gradient_parser.add_argument(
        "--pools", type=int, default=20, help="Number of pools"
    )
    gradient_parser.add_argument(
        "--start", type=int, default=10, help="Starting amount"
    )
    gradient_parser.add_argument("--end", type=int, default=200, help="Ending amount")

    # Grid scenario (2D square)
    grid_parser = subparsers.add_parser("grid", help="2D square grid of pools")
    grid_parser.add_argument("--size", type=int, default=3, help="Grid size (NxN)")
    grid_parser.add_argument("--amount", type=int, default=1000, help="Amount per pool")

    # Triangle scenario
    triangle_parser = subparsers.add_parser("triangle", help="3-pool triangle")
    triangle_parser.add_argument(
        "--skew", type=int, default=100, help="Price skew factor"
    )

    # Hub-spoke scenario
    hub_parser = subparsers.add_parser("hub-spoke", help="Hub and spoke topology")
    hub_parser.add_argument("--spokes", type=int, default=6, help="Number of spokes")
    hub_parser.add_argument("--amount", type=int, default=1000, help="Amount per pool")

    # Complete graph scenario
    complete_parser = subparsers.add_parser(
        "complete", help="Complete graph of pools between N denoms"
    )
    complete_parser.add_argument(
        "--denoms", type=int, default=3, help="Number of denoms (default: 3)"
    )
    complete_parser.add_argument(
        "--amount", type=int, default=1000, help="Base liquidity amount"
    )
    complete_parser.add_argument(
        "--pools-per-pair",
        type=int,
        default=2,
        help="Pools per denom pair (default: 2)",
    )
    complete_parser.add_argument(
        "--no-udys", action="store_true", help="Don't include udys connections"
    )

    # Common arbitrage test parameters
    parser.add_argument(
        "--max-depth-range",
        type=str,
        default="1,2,4,6",
        help="Comma-separated max_depth values to test (default: 1,2,4,6)",
    )
    parser.add_argument(
        "--ref-denom",
        type=str,
        default="udys",
        help="Reference denom for arbitrage (default: udys)",
    )
    parser.add_argument(
        "--max-splits", type=int, default=None, help="Override max_splits"
    )
    parser.add_argument(
        "--swap",
        type=str,
        default=None,
        help="Execute swap: POOL_INDEX:AMOUNT:IN_DENOM:OUT_DENOM (e.g., 1:500:G1_1:G1_2)",
    )

    args = parser.parse_args()

    # Get or create name
    base_denom = get_or_create_name(args.account)

    # Build scenario
    if args.scenario == "circle":
        scenario = build_circle_scenario(base_denom, args.pools, args.amount)
    elif args.scenario == "gradient":
        scenario = build_gradient_scenario(base_denom, args.pools, args.start, args.end)
    elif args.scenario == "grid":
        scenario = build_grid_scenario(base_denom, args.size, args.amount)
    elif args.scenario == "triangle":
        scenario = build_triangle_scenario(base_denom, args.skew)
    elif args.scenario == "hub-spoke":
        scenario = build_hub_spoke_scenario(base_denom, args.spokes, args.amount)
    elif args.scenario == "complete":
        scenario = build_complete_graph_scenario(
            base_denom,
            num_denoms=args.denoms,
            base_amount=args.amount,
            pools_per_pair=args.pools_per_pair,
            include_udys=not args.no_udys,
        )
    else:
        print(f"Unknown scenario: {args.scenario}")
        sys.exit(1)

    # Build arbitrage test parameters from --max-depth-range and --ref-denom
    depth_values = [int(d.strip()) for d in args.max_depth_range.split(",")]
    arb_params = []
    for depth in depth_values:
        param = {"max_depth": depth, "ref_denom": args.ref_denom}
        if args.max_splits is not None:
            param["max_splits"] = args.max_splits
        arb_params.append(param)

    # Parse swap argument: POOL_INDEX:AMOUNT:IN_DENOM:OUT_DENOM
    swap_spec = None
    if args.swap:
        parts = args.swap.split(":")
        if len(parts) != 4:
            print("Error: --swap format is POOL_INDEX:AMOUNT:IN_DENOM:OUT_DENOM")
            print("  e.g., --swap 1:500:G1_1:G1_2")
            sys.exit(1)
        swap_spec = {
            "pool_index": int(parts[0]) - 1,  # Convert to 0-indexed
            "amount": int(parts[1]),
            "in_denom": parts[2],
            "out_denom": parts[3],
        }

    # Execute
    results = execute_scenario(args.account, scenario, arb_params, swap_spec)
    print_results(results)


if __name__ == "__main__":
    main()
