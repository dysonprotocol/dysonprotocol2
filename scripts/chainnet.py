#!/usr/bin/env python3
"""
Unified CLI for Cosmos SDK chains and IBC with Hermes.

Commands:
  - generate: write network config JSON (and optional Hermes TOML)
  - setup: init nodes, add accounts, configure peers, gentx, collect-gentxs, distribute genesis
  - start: launch dysond nodes and Hermes relayer
  - ibc: create IBC connections between chains

Examples:
  # Generate network config with 2 chains, 1 node each, and Hermes TOML
  ./scripts/chainnet.py generate --chains 2 --nodes 1 --hermes-config

  # Generate with custom base config overrides
  ./scripts/chainnet.py generate --chains 2 --base-config custom-config.json

  # Setup the network (init, gentx, genesis) from default config
  ./scripts/chainnet.py setup --config-file /tmp/dysonchains/chains.json --force

  # Start nodes with extra flags (e.g., pruning, timeout)
  ./scripts/chainnet.py start --config-file /tmp/dysonchains/chains.json -- --pruning everything

  # Create IBC channels between chains
  ./scripts/chainnet.py ibc --config-file /tmp/dysonchains/chains.json

Base Config Format (custom-config.json):
  cat > custom-config.json <<EOF
{
  "global_genesis_overrides": {
    "governance_params": {
      "max_deposit_period": "172800s",
      "voting_period": "604800s",
      "quorum": "0.334000000000000000",
      "threshold": "0.500000000000000000",
      "expedited_voting_period": "86400s",
      "expedited_threshold": "0.667000000000000000"
    },
    "distribution_params": {
      "community_tax": "0.500000000000000000"
    },
    "mint_params": {
      "inflation": "0.010000000000000000",
      "inflation_max": "0.100000000000000000",
      "inflation_min": "0.010000000000000000",
      "blocks_per_year": "10512000"
    },
    "nameservice_params": {
      "bid_timeout": "2592000s"
    },
    "slashing_params": {
      "downtime_jail_duration": "600s"
    },
    "staking_params": {
      "unbonding_time": "2592000s"
    },
    "storage_params": {
      "storage_stake_multiple": "100"
    }
  },
  "accounts": [
    {
      "name": "alice",
      "address": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
      "mnemonic": "public feature teach face federal matrix throw legend bridge brass diary beach typical doll evoke weapon among crane regret trust enact swarm brother outside",
      "initial_balance": "5000000000000udys"
    },
    {
      "name": "custom-user",
      "address": "dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el",
      "mnemonic": "aerobic creek copper rice disagree become brass elegant century elegant apology position infant saddle metal brain gain loud alpha add boy balance truth cherry",
      "initial_balance": "10000000000000udys"
    }
  ]
}
EOF
"""
import json
import os
import signal
import shutil
import subprocess
import sys
import atexit
from pathlib import Path
import time
from typing import cast, Optional
from textwrap import dedent
import click
import requests
import tomlkit
from datetime import datetime, timezone
import tempfile


# --- Defaults & Constants ---
DEFAULT_DENOM = "udys"
DEFAULT_GENTX_AMOUNT = f"1000000{DEFAULT_DENOM}"
DEFAULT_INITIAL_BALANCE = f"10000000000{DEFAULT_DENOM}"
USER_KEYS = {
    "alice": {
        "address": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
        "mnemonic": "public feature teach face federal matrix throw legend bridge brass diary beach typical doll evoke weapon among crane regret trust enact swarm brother outside",
    },
    "bob": {
        "address": "dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el",
        "mnemonic": "aerobic creek copper rice disagree become brass elegant century elegant apology position infant saddle metal brain gain loud alpha add boy balance truth cherry",
    },
    "charlie": {
        "address": "dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e",
        "mnemonic": "blind people aim sheriff awkward once wish above agree journey unknown uncover swap damage bamboo volume clay error weekend fiber acquire diamond vintage lake",
    },
}
MAX_CHAINNET_OFFSET = 10
MAX_NODES_PER_CHAIN = 10


# --- Helpers for generation ---
def _resolve_base_dir(base_dir_option: Optional[str]) -> Path:
    """Resolve the effective base directory.

    Precedence:
    1) Explicit --base-dir option
    2) DYSON_BASE_DIR environment variable
    3) A newly created random temporary directory
    """
    if base_dir_option:
        return Path(base_dir_option)
    env_base = os.getenv("DYSON_BASE_DIR")
    if env_base:
        return Path(env_base)
    return Path(tempfile.mkdtemp(prefix="dyson-chainnet."))


def _resolve_config_path(config_file_option: Optional[str]) -> Path:
    """Resolve the config file path from option or DYSON_BASE_DIR.

    Requires either --config-file or DYSON_BASE_DIR to be set.
    """
    if config_file_option:
        return Path(config_file_option)
    env_base = os.getenv("DYSON_BASE_DIR")
    if env_base:
        return Path(env_base) / "chains.json"
    raise click.ClickException(
        "Missing config file. Provide --config-file or set DYSON_BASE_DIR environment variable"
    )


def deep_merge_config(base: dict, override: dict) -> dict:
    """Deep merge override config into base config.

    Special handling for 'chains' array: merge by chain_id.
    Special handling for 'accounts' array: completely replace base accounts.

    Args:
        base: Base configuration dictionary
        override: Override configuration dictionary

    Returns:
        Merged configuration dictionary
    """
    result = base.copy()

    for key, value in override.items():
        if (
            key == "chains"
            and isinstance(value, list)
            and key in result
            and isinstance(result[key], list)
        ):
            # Merge chains by chain_id
            result[key] = merge_chains_array(result[key], value)
        elif key == "accounts" and isinstance(value, list):
            # Replace accounts entirely if provided in override
            result[key] = value
        elif (
            key in result and isinstance(result[key], dict) and isinstance(value, dict)
        ):
            result[key] = deep_merge_config(result[key], value)
        else:
            result[key] = value

    return result


def merge_chains_array(base_chains: list, override_chains: list) -> list:
    """Merge chains arrays by chain_id."""
    result = base_chains.copy()

    for override_chain in override_chains:
        override_id = override_chain.get("chain_id")
        if not override_id:
            # No chain_id, just append
            result.append(override_chain)
            continue

        # Find matching base chain
        found = False
        for i, base_chain in enumerate(result):
            if base_chain.get("chain_id") == override_id:
                # Merge this chain
                result[i] = deep_merge_config(base_chain, override_chain)
                found = True
                break

        if not found:
            # New chain, append it
            result.append(override_chain)

    return result


def check_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is available for binding."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def get_genesis_defaults():
    """Get default genesis parameters."""
    return {
        "governance_params": {
            "voting_period": "10s",
            "expedited_voting_period": "5s",
            "expedited_threshold": "0.0001",
            "expedited_min_deposit": [{"denom": "udys", "amount": "2"}],
            "min_deposit": [{"denom": "udys", "amount": "1"}],
            "quorum": "0.00001",
            "threshold": "0.00001",
        },
        "nameservice_params": {
            "min_valuation_period": "1s",
            "max_valuation_period": "24h",
            "min_valuation_fee_pct": "0.0",
            "max_valuation_fee_pct": "1.0",
            "min_minimum_bid_percent_increase": "0.0",
            "max_minimum_bid_percent_increase": "1.0",
            "min_reject_bid_valuation_fee_percent": "0.0",
            "max_reject_bid_valuation_fee_percent": "1.0",
        },
    }


def apply_genesis_overrides(
    genesis_data: dict, app_state: dict, global_overrides: dict, denom: str
):
    """Apply global genesis parameter overrides to genesis data."""
    defaults = get_genesis_defaults()

    # Merge defaults with overrides
    merged_genesis = deep_merge_config(defaults, global_overrides)

    # Gov params
    if "governance_params" in merged_genesis:
        gov_params = merged_genesis["governance_params"]
        app_state_gov = app_state.setdefault("gov", {})
        app_state_gov_params = app_state_gov.setdefault("params", {})
        for key, value in gov_params.items():
            app_state_gov_params[key] = value

    # Distribution params
    if "distribution_params" in merged_genesis:
        dist_params = merged_genesis["distribution_params"]
        app_state_dist = app_state.setdefault("distribution", {})
        app_state_dist_params = app_state_dist.setdefault("params", {})
        for key, value in dist_params.items():
            app_state_dist_params[key] = str(value)

    # Mint params
    if "mint_params" in merged_genesis:
        mint_params = merged_genesis["mint_params"]
        # Minter section
        if "inflation" in mint_params:
            app_state_mint = app_state.setdefault("mint", {})
            minter = app_state_mint.setdefault("minter", {})
            minter["inflation"] = str(mint_params["inflation"])
        # Params section
        app_state_mint = app_state.setdefault("mint", {})
        app_state_mint_params = app_state_mint.setdefault("params", {})
        for key, value in mint_params.items():
            if key != "inflation":  # Skip inflation as it goes in minter
                app_state_mint_params[key] = str(value)

    # Nameservice params (only allow new fields; old global bidding params removed)
    if "nameservice_params" in merged_genesis:
        ns_params = merged_genesis["nameservice_params"]
        app_state_ns = app_state.setdefault("nameservice", {})
        app_state_ns_params = app_state_ns.setdefault("params", {})
        allowed_ns_keys = {
            "mint_fee_per_coin",
            "min_bid_timeout_class",
            "max_bid_timeout_class",
            "min_reject_bid_valuation_fee_percent",
            "max_reject_bid_valuation_fee_percent",
            "min_minimum_bid_percent_increase",
            "max_minimum_bid_percent_increase",
            "min_valuation_fee_pct",
            "max_valuation_fee_pct",
            "min_valuation_period",
            "max_valuation_period",
        }
        for key, value in ns_params.items():
            if key in allowed_ns_keys:
                app_state_ns_params[key] = str(value)

    # Slashing params
    if "slashing_params" in merged_genesis:
        slash_params = merged_genesis["slashing_params"]
        app_state_slash = app_state.setdefault("slashing", {})
        app_state_slash_params = app_state_slash.setdefault("params", {})
        for key, value in slash_params.items():
            app_state_slash_params[key] = str(value)

    # Staking params
    if "staking_params" in merged_genesis:
        stake_params = merged_genesis["staking_params"]
        app_state_stake = app_state.setdefault("staking", {})
        app_state_stake_params = app_state_stake.setdefault("params", {})
        for key, value in stake_params.items():
            app_state_stake_params[key] = str(value)

    # Storage params
    if "storage_params" in merged_genesis:
        storage_params = merged_genesis["storage_params"]
        app_state_storage = app_state.setdefault("storage", {})
        app_state_storage_params = app_state_storage.setdefault("params", {})
        for key, value in storage_params.items():
            app_state_storage_params[key] = str(value)

    # script params
    if "script_params" in merged_genesis:
        script_params = merged_genesis["script_params"]
        app_state_script = app_state.setdefault("script", {})
        app_state_script_params = app_state_script.setdefault("params", {})
        for key, value in script_params.items():
            app_state_script_params[key] = str(value)

    # Ensure IBC transfer module has its required params
    app_state_transfer = app_state.setdefault("transfer", {})
    if "params" not in app_state_transfer:
        app_state_transfer["params"] = {
            "send_enabled": True,
            "receive_enabled": True,
        }

    # Set bank denom metadata for dys/udys with 6 exponent
    app_state_bank = app_state.setdefault("bank", {})
    app_state_bank["denom_metadata"] = [
        {
            "description": "The native staking and governance token of the Dyson Protocol",
            "denom_units": [
                {"denom": "udys", "exponent": 0, "aliases": []},
                {"denom": "dys2", "exponent": 6, "aliases": []},
            ],
            "base": "udys",
            "display": "dys2",
            "name": "Dys2",
            "symbol": "DYS2",
        }
    ]

    # Set consensus params for evidence and block size limits
    consensus_params = genesis_data.setdefault("consensus_params", {})
    evidence_params = consensus_params.setdefault("evidence", {})
    evidence_params["max_bytes"] = "204800"  # 200KB
    block_params = consensus_params.setdefault("block", {})
    block_params["max_bytes"] = "3145728"  # 3MB
    block_params["max_gas"] = "6000000"  # 10T gas


def generate_ports(port_offset: int, chainnet_offset: int) -> dict:
    """Generate port mappings for a node with given offsets.

    Args:
        port_offset: Offset for this node within its chain (0-based)
        chainnet_offset: Offset for this chainnet instance (0-based)

    Returns:
        Dict mapping service names to port numbers
    """

    assert (
        port_offset < MAX_NODES_PER_CHAIN
    ), f"port_offset must be less than {MAX_NODES_PER_CHAIN}, do you really need more than {MAX_NODES_PER_CHAIN} nodes per chain?"
    assert (
        chainnet_offset < MAX_CHAINNET_OFFSET
    ), f"chainnet_offset must be less than {MAX_CHAINNET_OFFSET}, do you really need more than {MAX_CHAINNET_OFFSET} chains?"

    base_ports = {
        "p2p": 26656,
        "rpc": 26657,
        "abci": 26658,
        "grpc": 9090,
        "api": 1317,
        "libp2p": 9095,
    }

    return {
        service: base + (port_offset * 100) + (chainnet_offset * 1000)
        for service, base in base_ports.items()
    }


def generate_chain_structure(
    chainnet_offset: int,
    idx: int,
    num_chains: int,
    nodes_per_chain: int,
    base_dir: Path,
) -> dict:
    chain_id = f"chain-{chr(ord('a')+idx)}"
    nodes = []
    for j in range(nodes_per_chain):
        nid = idx * nodes_per_chain + j + 1
        moniker = f"node-{nid}"
        home = base_dir / f"{chain_id}-{moniker}"
        ports = generate_ports(port_offset=nid - 1, chainnet_offset=chainnet_offset)
        nodes.append(
            {
                "moniker": moniker,
                "home": str(home),
                "ports": ports,
                "validator": {
                    "gentx_amount": DEFAULT_GENTX_AMOUNT,
                    "initial_balance": DEFAULT_INITIAL_BALANCE,
                },
            }
        )

    # Add other nodes information to each node
    for i, node in enumerate(nodes):
        node["other_nodes"] = [
            {
                "moniker": other_node["moniker"],
                "home": other_node["home"],
                "ports": other_node["ports"],
            }
            for j, other_node in enumerate(nodes)
            if i != j  # Exclude self
        ]

    return {"chain_id": chain_id, "nodes": nodes}


def generate_accounts() -> list:
    return [
        {
            "name": n,
            "address": d["address"],
            "mnemonic": d["mnemonic"],
            "initial_balance": DEFAULT_INITIAL_BALANCE,
        }
        for n, d in USER_KEYS.items()
    ]


def generate_hermes_config(
    chains: list, base_dir: Path, denom: str, key_name: str = "charlie"
) -> str:
    """Generate a full Hermes relayer TOML config with chain entries as [[chains]] array of tables."""
    return f"""
[global]
log_level = 'info'

[mode]

[mode.clients]
enabled = true
refresh = true
misbehaviour = false

[mode.connections]
enabled = true

[mode.channels]
enabled = true

[mode.packets]
enabled = true
clear_interval = 1
clear_on_start = true
tx_confirmation = true

[telemetry]
enabled = false
host = '127.0.0.1'
port = 3001

{"".join(f'''
[[chains]]
id = "{chain["chain_id"]}"
type = "CosmosSdk"
rpc_addr = "http://localhost:{chain["nodes"][0]["ports"]["rpc"]}"
grpc_addr = "http://localhost:{chain["nodes"][0]["ports"]["grpc"]}"
event_source = {{ mode = "pull", interval = '100ms' }}
rpc_timeout = "15s"
trusted_node = true
account_prefix = "dys2"
key_name = "{key_name}"
store_prefix = "ibc"
gas_price = {{ price = 0.000, denom = "{denom}" }}
gas_multiplier = 2
default_gas = 1000000
max_gas = 10000000
max_msg_num = 30
max_tx_size = 2097152
clock_drift = "10s"
max_block_time = "1000ms"
trusting_period = "14days"
trust_threshold = {{ numerator = "2", denominator = "3" }}

[chains.packet_filter]
policy = "allow"
list = [
  ["*", "*"],
]
''' for chain in chains)}

"""


# --- CLI ---
@click.group()
def chainnet():
    """Manage chain generation, setup, start, and IBC."""
    pass


@chainnet.command()
@click.option(
    "--base-dir", default=None, type=click.Path(), help="Base directory for chain data"
)
@click.option("--chains", "num_chains", default=2, type=int, show_default=True)
@click.option("--chainnet-offset", default=0, type=int, show_default=True)
@click.option("--nodes", "nodes_per_chain", default=1, type=int, show_default=True)
@click.option("--denom", default=DEFAULT_DENOM, show_default=True)
@click.option("--dysond-bin", default="dysond")
@click.option("--hermes-config", is_flag=True)
@click.option(
    "--base-config",
    type=click.Path(exists=True),
    help="Base config JSON file to use as template/override defaults",
)
@click.option("--output", type=click.Path(), help="JSON output path")
def generate(
    base_dir,
    num_chains,
    chainnet_offset,
    nodes_per_chain,
    denom,
    dysond_bin,
    hermes_config,
    base_config,
    output,
):
    """Generate and persist network config JSON (and optional Hermes TOML)."""
    base = _resolve_base_dir(base_dir)
    base.mkdir(parents=True, exist_ok=True)

    # Load base config if provided
    if base_config:
        base_cfg = json.loads(Path(base_config).read_text())
        click.echo(f"Loaded base config from {base_config}")
    else:
        base_cfg = {}

    # Generate default configuration
    default_cfg = {
        "dysond_bin": dysond_bin,
        "default_denom": denom,
        "base_dir": str(base),
        "chains": [],
        "accounts": generate_accounts(),
    }
    for i in range(num_chains):
        default_cfg["chains"].append(
            generate_chain_structure(
                chainnet_offset=chainnet_offset,
                idx=i,
                num_chains=num_chains,
                nodes_per_chain=nodes_per_chain,
                base_dir=base,
            )
        )

    # Merge base config with defaults (base config takes precedence)
    cfg = deep_merge_config(default_cfg, base_cfg)
    path = Path(output) if output else (base / "chains.json")
    path.write_text(json.dumps(cfg, indent=2))
    # print contents of path
    click.echo(f"Wrote config JSON to {path}")
    if hermes_config:
        hermes_dir = base / "hermes"
        hermes_dir.mkdir(exist_ok=True)
        toml = generate_hermes_config(cfg["chains"], base, denom)
        (hermes_dir / "config.toml").write_text(toml)
        click.echo(f"Wrote Hermes TOML to {str(hermes_dir / 'config.toml')}")


def setup_hermes_keys(
    cfg: dict, force: bool = False, ibc_account: Optional[dict] = None
):
    """Setup Hermes keys for all chains in the configuration.

    Args:
        cfg: The configuration dictionary containing chain information
        force: If True, delete existing keys before adding new ones
        ibc_account: Optional custom IBC account dictionary with 'name', 'address', and 'mnemonic' keys.
                     If not provided, defaults to using charlie account.
    """
    hermes_config_path = Path(cfg["base_dir"]) / "hermes" / "config.toml"

    # Check if Hermes is available and config exists
    if not shutil.which("hermes"):
        click.echo(
            "Warning: Hermes binary not found in PATH, skipping Hermes key setup."
        )
        return

    if not hermes_config_path.exists():
        click.echo("Warning: Hermes config not found, skipping Hermes key setup.")
        return

    # Use provided IBC account or default to charlie
    if ibc_account:
        hermes_key_name = ibc_account["name"]
        hermes_mnemonic = ibc_account["mnemonic"]
        expected_address = ibc_account["address"]
        click.echo(f"Using custom IBC account: {hermes_key_name} ({expected_address})")
    else:
        # Use charlie account for Hermes operations
        hermes_key_name = "charlie"
        hermes_mnemonic = USER_KEYS[hermes_key_name]["mnemonic"]
        expected_address = USER_KEYS[hermes_key_name]["address"]

    # Create temporary mnemonic file
    mnemonic_file = Path(cfg["base_dir"]) / "hermes" / f"{hermes_key_name}_mnemonic.txt"
    mnemonic_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Write mnemonic to temporary file
        mnemonic_file.write_text(hermes_mnemonic)

        for chain in cfg["chains"]:
            chain_id = chain["chain_id"]

            if force:
                # Delete all existing keys for this chain
                click.echo(f"Removing all Hermes keys for chain {chain_id}...")
                try:
                    subprocess.run(
                        [
                            "hermes",
                            "--config",
                            str(hermes_config_path),
                            "keys",
                            "delete",
                            "--chain",
                            chain_id,
                            "--all",
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    click.echo(f"Successfully removed all keys for chain {chain_id}")
                except subprocess.CalledProcessError as e:
                    # It's okay if this fails (e.g., no keys exist)
                    pass

            # Add the key
            click.echo(
                f"Adding {hermes_key_name} key to Hermes for chain {chain_id}..."
            )
            try:
                subprocess.run(
                    [
                        "hermes",
                        "--config",
                        str(hermes_config_path),
                        "keys",
                        "add",
                        "--chain",
                        chain_id,
                        "--mnemonic-file",
                        str(mnemonic_file),
                        "--key-name",
                        hermes_key_name,
                        "--overwrite",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                click.echo(
                    f"Successfully added {hermes_key_name} key for chain {chain_id}"
                )

                # Verify the key was imported with the correct prefix
                try:
                    list_result = subprocess.run(
                        [
                            "hermes",
                            "--config",
                            str(hermes_config_path),
                            "keys",
                            "list",
                            "--chain",
                            chain_id,
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )

                    # Check if the output contains the expected address with correct prefix
                    if expected_address in list_result.stdout:
                        click.echo(
                            f"✓ Verified: {hermes_key_name} key has correct address {expected_address}"
                        )
                    elif "dys1" in list_result.stdout:
                        click.echo(
                            f"⚠️  WARNING: Found old 'dys1' prefix in Hermes keys for chain {chain_id}!",
                            err=True,
                        )
                        click.echo(f"  Expected: {expected_address}", err=True)
                        click.echo(f"  Output: {list_result.stdout.strip()}", err=True)
                    else:
                        click.echo(
                            f"⚠️  WARNING: Could not verify key address for chain {chain_id}",
                            err=True,
                        )
                        click.echo(f"  Output: {list_result.stdout.strip()}", err=True)

                except subprocess.CalledProcessError as e:
                    click.echo(
                        f"Warning: Could not verify key for chain {chain_id}: {e.stderr}",
                        err=True,
                    )

            except subprocess.CalledProcessError as e:
                click.echo(
                    f"Error adding {hermes_key_name} key for chain {chain_id}: {e.stderr}",
                    err=True,
                )

    finally:
        # Clean up mnemonic file
        if mnemonic_file.exists():
            mnemonic_file.unlink()


@chainnet.command()
@click.option(
    "--config-file", default=None, type=click.Path(), help="Path to chains.json"
)
@click.option("--force", is_flag=True)
def setup(config_file, force):
    """Initialize nodes, keys, genesis, gentx, collect-gentxs, and distribute genesis.json"""
    cfg_path = _resolve_config_path(config_file)
    cfg = json.loads(cfg_path.read_text())
    bin_path = cfg["dysond_bin"]
    denom = cfg.get("default_denom", DEFAULT_DENOM)

    for chain_idx, chain in enumerate(cfg["chains"]):
        cid = chain["chain_id"]
        click.echo(f"Setting up {cid}")
        peer_map = {}

        # Step 1: Initialize nodes, configure ports/peers, add keys, get validator addresses,
        # and prepare individual genesis files with initial balances and params.
        for node_idx, node_config_data in enumerate(chain["nodes"]):
            home = Path(node_config_data["home"])
            moniker = node_config_data["moniker"]
            node_ports = node_config_data["ports"]

            if home.exists():
                if force:
                    shutil.rmtree(home)
                else:
                    raise RuntimeError(f"{home} exists; use --force")
            home.mkdir(parents=True)

            # Init node
            subprocess.run(
                [
                    bin_path,
                    "init",
                    moniker,
                    "--chain-id",
                    cid,
                    "--default-denom",
                    denom,
                    "-o",
                    "--home",
                    str(home),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            # Get node ID using comet show-node-id
            node_id_proc = subprocess.run(
                [bin_path, "comet", "show-node-id", "--home", str(home)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            node_id = node_id_proc.stdout.strip()
            ext_host = node_config_data.get("external_host", "127.0.0.1")
            peer_map[moniker] = f"{node_id}@{ext_host}:{node_ports['p2p']}"
            node_config_data["node_id"] = (
                node_id  # Store node_id for later use if needed
            )

            # Configure config.toml for this node
            cfg_dir = home / "config"
            toml_conf_path = cfg_dir / "config.toml"
            toml_conf = tomlkit.parse(toml_conf_path.read_text())
            toml_conf["proxy_app"] = f"tcp://127.0.0.1:{node_ports['abci']}"
            toml_conf["pprof_laddr"] = ""
            cast(dict, toml_conf.setdefault("rpc", tomlkit.table()))[
                "laddr"
            ] = f"tcp://127.0.0.1:{node_ports['rpc']}"
            p2p_table = cast(dict, toml_conf.setdefault("p2p", tomlkit.table()))
            # Persistent peers will be set later after all nodes in this chain are processed
            p2p_table["laddr"] = f"tcp://0.0.0.0:{node_ports['p2p']}"
            p2p_table["allow_duplicate_ip"] = True
            p2p_table["external_address"] = f"tcp://{ext_host}:{node_ports['p2p']}"
            inst_table = cast(
                dict, toml_conf.setdefault("instrumentation", tomlkit.table())
            )
            inst_table["prometheus"] = False
            toml_conf_path.write_text(tomlkit.dumps(toml_conf))

            # Configure client.toml for this node
            client_toml_path = cfg_dir / "client.toml"
            client_toml_obj = tomlkit.parse(client_toml_path.read_text())
            client_toml_obj["chain-id"] = cid
            client_toml_obj["keyring-backend"] = "test"
            # Force IPv4 to avoid ::1 resolution issues on localhost
            client_toml_obj["node"] = f"tcp://127.0.0.1:{node_ports['rpc']}"
            client_toml_path.write_text(tomlkit.dumps(client_toml_obj))

            # Configure app.toml for this node
            app_toml_path = cfg_dir / "app.toml"
            if app_toml_path.exists():
                app_toml = tomlkit.parse(app_toml_path.read_text())
                cast(dict, app_toml.setdefault("api", tomlkit.table()))[
                    "address"
                ] = f"tcp://localhost:{node_ports['api']}"
                cast(dict, app_toml.setdefault("api", tomlkit.table()))["enable"] = True
                cast(dict, app_toml.setdefault("api", tomlkit.table()))[
                    "enabled-unsafe-cors"
                ] = True
                cast(dict, app_toml.setdefault("grpc", tomlkit.table()))[
                    "address"
                ] = f"localhost:{node_ports['grpc']}"
                cast(dict, app_toml.setdefault("grpc", tomlkit.table()))[
                    "enable"
                ] = True
                cast(dict, app_toml.setdefault("grpc-web", tomlkit.table()))[
                    "enable"
                ] = True
                # Configure dwapp libp2p port
                cast(dict, app_toml.setdefault("dwapp", tomlkit.table()))[
                    "libp2p-port"
                ] = node_ports["libp2p"]
                # Configure state-sync snapshots
                cast(dict, app_toml.setdefault("state-sync", tomlkit.table()))[
                    "snapshot-interval"
                ] = 100
                cast(dict, app_toml.setdefault("state-sync", tomlkit.table()))[
                    "snapshot-keep-recent"
                ] = 5
                app_toml_path.write_text(tomlkit.dumps(app_toml))
            else:
                click.echo(
                    f"Warning: app.toml not found at {app_toml_path}, skipping its port configuration."
                )

            # Add user keys to this node's keyring
            for acc in cfg["accounts"]:
                subprocess.run(
                    [
                        bin_path,
                        "keys",
                        "add",
                        acc["name"],
                        "--recover",
                        "--home",
                        str(home),
                    ],
                    input=acc["mnemonic"] + "\n",
                    text=True,
                    check=True,
                    capture_output=True,
                )

            # Add validator key for this node to its own keyring and get address
            subprocess.run(
                [bin_path, "keys", "add", "validator", "--home", str(home)],
                check=True,
                capture_output=True,
                text=True,
            )
            show_addr_proc = subprocess.run(
                [bin_path, "keys", "show", "validator", "-a", "--home", str(home)],
                capture_output=True,
                text=True,
                check=True,
            )
            validator_address = show_addr_proc.stdout.strip()
            node_config_data["validator_address"] = validator_address

            # Modify this node's genesis.json
            current_genesis_path = cfg_dir / "genesis.json"
            gdata = json.loads(current_genesis_path.read_text())
            app_state = gdata.setdefault("app_state", {})

            # Apply global genesis overrides
            global_overrides = cfg.get("global_genesis_overrides", {})
            apply_genesis_overrides(gdata, app_state, global_overrides, denom)

            current_genesis_path.write_text(json.dumps(gdata, indent=2))

            # Add user accounts to this node's genesis
            for acc in cfg["accounts"]:
                subprocess.run(
                    [
                        bin_path,
                        "genesis",
                        "add-genesis-account",
                        acc["address"],
                        acc["initial_balance"],
                        "--home",
                        str(home),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            # Add this validator's initial_balance to its own genesis
            subprocess.run(
                [
                    bin_path,
                    "genesis",
                    "add-genesis-account",
                    validator_address,
                    node_config_data["validator"]["initial_balance"],
                    "--home",
                    str(home),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        # NOTE: Will set persistent_peers AFTER collect-gentxs to avoid being overwritten

        # Step 2: Generate Gentx for each node using its own prepared genesis
        for node_config_data in chain["nodes"]:
            subprocess.run(
                [
                    bin_path,
                    "genesis",
                    "gentx",
                    "validator",
                    node_config_data["validator"]["gentx_amount"],
                    "--chain-id",
                    cid,
                    "--home",
                    str(node_config_data["home"]),
                ],
                check=True,
            )

        # Step 3: Add all validator accounts to primary node's genesis, copy gentx files, and collect gentxs

        primary_node_home = Path(chain["nodes"][0]["home"])
        primary_node_home_str = str(primary_node_home)
        primary_gentx_dir = primary_node_home / "config" / "gentx"

        # Add all other validator accounts to the primary node's genesis
        for i in range(1, len(chain["nodes"])):
            other_validator_address = chain["nodes"][i]["validator_address"]
            other_initial_balance = chain["nodes"][i]["validator"]["initial_balance"]
            subprocess.run(
                [
                    bin_path,
                    "genesis",
                    "add-genesis-account",
                    other_validator_address,
                    other_initial_balance,
                    "--home",
                    primary_node_home_str,
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        # Copy gentx files from all other nodes to the primary node's gentx directory
        for i in range(1, len(chain["nodes"])):
            other_node_home = Path(chain["nodes"][i]["home"])
            other_gentx_dir = other_node_home / "config" / "gentx"

            if other_gentx_dir.exists():
                for gentx_file in other_gentx_dir.glob("*.json"):
                    shutil.copy2(gentx_file, primary_gentx_dir)

        subprocess.run(
            [bin_path, "genesis", "collect-gentxs", "--home", primary_node_home_str],
            check=True,
            capture_output=True,
            text=True,
        )

        final_genesis_content = (
            Path(primary_node_home_str) / "config" / "genesis.json"
        ).read_text()
        for i in range(1, len(chain["nodes"])):  # Distribute to other nodes
            other_node_home = Path(chain["nodes"][i]["home"])
            (other_node_home / "config" / "genesis.json").write_text(
                final_genesis_content
            )

        # NOW set persistent_peers for each node (after collect-gentxs which may overwrite config)
        for node_config_data_for_peers in chain["nodes"]:
            home = Path(node_config_data_for_peers["home"])
            moniker = node_config_data_for_peers["moniker"]
            peers_for_this_node = [
                p_str for m, p_str in peer_map.items() if m != moniker
            ]

            toml_conf_path = home / "config" / "config.toml"
            toml_conf = tomlkit.parse(toml_conf_path.read_text())
            cast(dict, toml_conf.setdefault("p2p", tomlkit.table()))[
                "persistent_peers"
            ] = ",".join(peers_for_this_node)
            toml_conf_path.write_text(tomlkit.dumps(toml_conf))

    # Setup Hermes keys after all chains are initialized
    click.echo("\nSetting up Hermes keys...")
    setup_hermes_keys(cfg, force=force)

    click.echo("Setup complete")


@chainnet.command()
@click.option(
    "--config-file", default=None, type=click.Path(), help="Path to chains.json"
)
@click.option(
    "--block-speed",
    default=None,
    help='Override block production speed (timeout_commit) for all nodes, e.g. "500ms" or "1s".',
)
@click.option(
    "--no-blocks-timeout",
    default=None,
    type=float,
    help="Timeout in seconds to stop if no new blocks are produced by any node.",
)
@click.option(
    "--logs",
    is_flag=True,
    help="Output all node and hermes logs to stdout instead of log files",
)
@click.option(
    "--log-module",
    default=None,
    help='Filter logs to only show a specific module (e.g. "whaleswap" or "script"). Sets that module to debug level and others to error.',
)
@click.argument("extra_args", nargs=-1)
def start(config_file, block_speed, extra_args, no_blocks_timeout, logs, log_module):
    """Start all dysond nodes and Hermes relayer."""
    import threading, time, requests

    cfg_path = _resolve_config_path(config_file)
    cfg = json.loads(cfg_path.read_text())
    bin_path = cfg["dysond_bin"]
    procs = []
    node_procs = []  # track per-node proc/cmd/home
    log_files = []  # Track log files for cleanup
    hermes_started = False
    stop_event = threading.Event()

    # Check all ports are available before starting any nodes
    # Services that bind to all interfaces (0.0.0.0) vs localhost (127.0.0.1)
    all_interfaces_services = {"p2p", "libp2p"}

    occupied_ports = []
    for chain in cfg["chains"]:
        for node in chain["nodes"]:
            for service, port in node["ports"].items():
                # Check on the same interface the service will actually bind to
                host = "0.0.0.0" if service in all_interfaces_services else "127.0.0.1"
                if not check_port_available(port, host):
                    occupied_ports.append(
                        {
                            "chain": chain["chain_id"],
                            "node": node["moniker"],
                            "service": service,
                            "port": port,
                            "host": host,
                        }
                    )

    if occupied_ports:
        error_lines = [
            "\nThe following ports are already in use and cannot be bound:\n"
        ]
        for info in occupied_ports:
            error_lines.append(
                f"  • {info['host']}:{info['port']} ({info['service']}) needed by {info['chain']}/{info['node']}"
            )
        error_lines.append(
            f"\nTo fix this:\n"
            f"  1. Stop processes using these ports (e.g., 'lsof -ti:{occupied_ports[0]['port']} | xargs kill')\n"
            f"  2. Or regenerate network config with different --chainnet-offset to use different port ranges\n"
        )
        raise click.ClickException("".join(error_lines))

    def cleanup_processes():
        """Simple cleanup function."""
        for p in procs:
            if p.poll() is None:
                try:
                    os.killpg(os.getpgid(p.pid), signal.SIGTERM)
                    p.wait(timeout=3)
                except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                    except (ProcessLookupError, OSError):
                        pass
        # Close log files if we opened any
        for log_file in log_files:
            try:
                log_file.close()
            except:
                pass

    atexit.register(cleanup_processes)

    # If block_speed is provided, patch all config.toml files (let errors bubble up)
    if block_speed:
        for chain in cfg["chains"]:
            for node in chain["nodes"]:
                config_toml_path = Path(node["home"]) / "config" / "config.toml"
                doc = tomlkit.parse(config_toml_path.read_text())
                consensus = doc.setdefault("consensus", tomlkit.table())
                consensus["timeout_commit"] = str(block_speed)
                config_toml_path.write_text(tomlkit.dumps(doc))

    # Build log level flag if log_module is specified
    log_level_args = []
    if log_module:
        # Set the specified module to debug and everything else to error
        log_level_args = ["--log_level", f"{log_module}:debug,*:error"]
        click.echo(f"Filtering logs to module: {log_module}")

    for chain in cfg["chains"]:
        for node in chain["nodes"]:
            if logs:
                # Output logs to stdout/stderr
                click.echo(
                    f"Starting {chain['chain_id']}/{node['moniker']} (logs will appear below)"
                )
                cmd = [
                    bin_path,
                    "start",
                    "--home",
                    node["home"],
                    *log_level_args,
                    *extra_args,
                ]
                p = subprocess.Popen(cmd, preexec_fn=os.setsid)
                click.echo(
                    f"[chainnet] started node {chain['chain_id']}/{node['moniker']} pid={p.pid} home={node['home']}"
                )
            else:
                # Output logs to files (current behavior)
                log_path = os.path.join(node["home"], "node.log")
                log_file = open(log_path, "w")
                log_files.append(log_file)
                cmd = [
                    bin_path,
                    "start",
                    "--home",
                    node["home"],
                    *log_level_args,
                    *extra_args,
                ]
                p = subprocess.Popen(
                    cmd,
                    preexec_fn=os.setsid,
                    stdout=log_file,
                    stderr=log_file,
                )
                click.echo(
                    f"[chainnet] started node {chain['chain_id']}/{node['moniker']} pid={p.pid} home={node['home']} (logs at {log_path})"
                )
            procs.append(p)
            node_procs.append(
                {
                    "proc": p,
                    "cmd": cmd,
                    "home": node["home"],
                    "moniker": node["moniker"],
                    "chain_id": chain["chain_id"],
                    "restart_count": 0,
                }
            )

    hcfg = Path(cfg["base_dir"]) / "hermes" / "config.toml"
    if hcfg.exists() and shutil.which("hermes"):
        time.sleep(1)
        click.echo(f"Starting Hermes relayer with config: {hcfg}")
        if logs:
            # Output logs to stdout/stderr
            click.echo("Hermes logs will appear below")
            hermes_proc = subprocess.Popen(
                ["hermes", "--config", str(hcfg), "start"], preexec_fn=os.setsid
            )
        else:
            # Output logs to files (current behavior)
            hermes_log_path = Path(cfg["base_dir"]) / "hermes" / "hermes.log"
            hermes_log_file = open(hermes_log_path, "w")
            log_files.append(hermes_log_file)
            hermes_proc = subprocess.Popen(
                ["hermes", "--config", str(hcfg), "start"],
                preexec_fn=os.setsid,
                stdout=hermes_log_file,
                stderr=hermes_log_file,
            )
        procs.append(hermes_proc)
        hermes_started = True
    elif hcfg.exists():
        click.echo("Warning: Hermes binary not found in PATH, skipping Hermes start.")

    if logs:
        click.echo(
            f"Nodes {'and Hermes ' if hermes_started else ''}started with logs output to terminal. Ctrl+C to stop."
        )
    else:
        click.echo(
            f"Nodes {'and Hermes ' if hermes_started else ''}started. Ctrl+C to stop."
        )

    def get_rpc_url(node):
        config_path = Path(node["home"]) / "config" / "config.toml"
        doc = tomlkit.parse(config_path.read_text())
        rpc_addr = str(doc.get("rpc", {}).get("laddr"))
        if rpc_addr.startswith("tcp://"):
            rpc_addr = "http://" + rpc_addr[6:]
        return rpc_addr

    def get_block_info(rpc_url):
        """Get latest block height and timestamp from RPC endpoint"""
        for i in range(3):
            try:
                resp = requests.get(f"{rpc_url}/status", timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    sync_info = data["result"]["sync_info"]
                    height = int(sync_info["latest_block_height"])
                    # Parse the timestamp (format: "2025-01-20T15:17:07.770381Z")
                    block_time_str = sync_info["latest_block_time"]
                    block_time = datetime.fromisoformat(
                        block_time_str.replace("Z", "+00:00")
                    )
                    return height, block_time
            except Exception as e:
                click.echo(
                    f"Error getting block info for {rpc_url} (attempt {i+1} of 3): {e}",
                    err=True,
                )
                time.sleep(1)
        return None, None

    def monitor_blocks(timeout):
        node_infos = []
        for chain in cfg["chains"]:
            for node in chain["nodes"]:
                node_infos.append(
                    {
                        "moniker": node["moniker"],
                        "chain_id": chain["chain_id"],
                        "rpc": get_rpc_url(node),
                    }
                )

        # Give nodes time to start up and begin producing blocks
        startup_grace_period = max(10, timeout)
        click.echo(
            f"Giving nodes {startup_grace_period}s to start up before monitoring..."
        )
        time.sleep(startup_grace_period)

        try:
            while not stop_event.is_set():
                time.sleep(timeout / 2)
                current_time = datetime.now(timezone.utc)
                stale_nodes = []

                for info in node_infos:
                    height, block_time = get_block_info(info["rpc"])
                    key = f"{info['chain_id']}-{info['moniker']}"

                    if height is not None and block_time is not None:
                        # Check if the latest block is older than our timeout
                        time_since_block = (current_time - block_time).total_seconds()
                        if time_since_block > timeout:
                            stale_nodes.append(
                                f"Node: {key} Height: {height} Block Age: {time_since_block:.1f}s"
                            )
                    else:
                        # Node is unreachable
                        stale_nodes.append(
                            f"Node: {key} Height: unreachable Block Age: N/A"
                        )

                if stale_nodes:
                    stale_nodes_str = "\n".join(stale_nodes)
                    click.echo(
                        f"""
------------------------------------------------------------------------------------------------
Not all nodes produced new blocks in the last {timeout} seconds. 
{stale_nodes_str}

Stopping all nodes!
------------------------------------------------------------------------------------------------"""
                    )
                    stop_event.set()
                    return
        except Exception as e:
            click.echo(f"Exception in block monitor: {e}")
            stop_event.set()
            return

    if no_blocks_timeout:
        t = threading.Thread(
            target=monitor_blocks, args=(no_blocks_timeout,), daemon=True
        )
        t.start()

    def handle_signal(sig, frame):
        cleanup_processes()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        while True:
            if stop_event.is_set():
                cleanup_processes()
                sys.exit(1)
            # stay alive while at least one node process is running
            any_running = False
            for entry in node_procs:
                if entry["proc"].poll() is None:
                    any_running = True
                    break
            if not any_running:
                break
            time.sleep(0.5)
    except Exception:
        cleanup_processes()
        raise


@chainnet.command()
@click.option(
    "--config-file", default=None, type=click.Path(), help="Path to chains.json"
)
@click.option("--ibc-account-name", default=None, help="Name of the IBC account to use")
@click.option(
    "--ibc-account-address", default=None, help="Address of the IBC account to use"
)
@click.option(
    "--ibc-account-mnemonic", default=None, help="Mnemonic of the IBC account to use"
)
def ibc(config_file, ibc_account_name, ibc_account_address, ibc_account_mnemonic):
    """Create IBC channels between consecutive chains."""
    cfg_path = _resolve_config_path(config_file)
    cfg = json.loads(cfg_path.read_text())
    if not cfg["chains"] or len(cfg["chains"]) < 2:
        click.echo("IBC setup requires at least two chains. Skipping.")
        return

    chains_ids = [c["chain_id"] for c in cfg["chains"]]
    hcfg = Path(cfg["base_dir"]) / "hermes" / "config.toml"

    if not shutil.which("hermes"):
        click.echo("Hermes binary not found in PATH, skipping IBC setup.")
        return

    # Prepare custom IBC account if provided
    ibc_account = None
    key_name = "charlie"  # default key name
    if ibc_account_name and ibc_account_address and ibc_account_mnemonic:
        ibc_account = {
            "name": ibc_account_name,
            "address": ibc_account_address,
            "mnemonic": ibc_account_mnemonic,
        }
        key_name = ibc_account_name

        # Regenerate Hermes config with the custom key name
        click.echo(f"Regenerating Hermes config with custom key name: {key_name}")
        hermes_toml = generate_hermes_config(
            cfg["chains"], Path(cfg["base_dir"]), DEFAULT_DENOM, key_name
        )
        hcfg.write_text(hermes_toml)
        click.echo(f"Updated Hermes config at {hcfg}")

    # Ensure Hermes keys are set up before attempting to create channels
    click.echo("Ensuring Hermes keys are properly configured...")
    setup_hermes_keys(cfg, force=False, ibc_account=ibc_account)

    # verify both chains are making blocks within the timeout
    some_node_not_ready = True
    while some_node_not_ready:
        some_node_not_ready = False
        for chain in cfg["chains"]:
            for node in chain["nodes"]:
                rpc_url = f"http://localhost:{node['ports']['rpc']}"
                resp = requests.get(f"{rpc_url}/status")
                if resp.status_code != 200:
                    click.echo(f"Chain {chain['chain_id']} is not running. waiting...")
                    time.sleep(1)
                    some_node_not_ready = True

    for i in range(len(chains_ids) - 1):
        chain_a_id = chains_ids[i]
        chain_b_id = chains_ids[i + 1]
        click.echo(f"Creating IBC channel between {chain_a_id} and {chain_b_id}")
        try:
            command = [
                "hermes",
                "--config",
                str(hcfg),
                "create",
                "channel",
                "--a-chain",
                chain_a_id,
                "--b-chain",
                chain_b_id,
                "--a-port",
                "transfer",
                "--b-port",
                "transfer",
                "--new-client-connection",
                "--yes",
            ]
            print("Running command: " + " ".join(command))
            subprocess.run(command, check=True, capture_output=True, text=True)
            click.echo(
                f"Successfully created channel between {chain_a_id} and {chain_b_id}"
            )
        except subprocess.CalledProcessError as e:
            click.echo(
                f"Error creating IBC channel between {chain_a_id} and {chain_b_id}:"
            )
            click.echo(f"Stdout: {e.stdout}")
            click.echo(f"Stderr: {e.stderr}")
            raise e
    click.echo("IBC connection attempts complete.")


if __name__ == "__main__":
    chainnet()
