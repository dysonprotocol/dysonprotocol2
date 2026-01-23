#!/usr/bin/env python3
"""
Tests for script.ValidateGenesis via dysond validate-genesis.
"""

import json
import shutil
import tempfile
from pathlib import Path


def _get_node_home(test_config_path):
    cfg = json.loads(Path(test_config_path).read_text())
    chains = cfg.get("chains", [])
    assert isinstance(chains, list), f"chains should be list: {json.dumps(cfg, indent=2)}"
    assert len(chains) > 0, f"chains empty: {json.dumps(cfg, indent=2)}"
    nodes = chains[0].get("nodes", [])
    assert isinstance(nodes, list), f"nodes should be list: {json.dumps(chains[0], indent=2)}"
    assert len(nodes) > 0, f"nodes empty: {json.dumps(chains[0], indent=2)}"
    home = nodes[0].get("home")
    assert isinstance(home, str), f"home should be string: {json.dumps(nodes[0], indent=2)}"
    assert home, f"home empty: {json.dumps(nodes[0], indent=2)}"
    return Path(home)


def _write_genesis(temp_home, script_state):
    genesis_path = Path(temp_home) / "config" / "genesis.json"
    genesis = json.loads(genesis_path.read_text())
    assert "app_state" in genesis, f"app_state missing: {json.dumps(genesis, indent=2)}"
    app_state = genesis["app_state"]
    assert isinstance(app_state, dict), f"app_state should be dict: {json.dumps(genesis, indent=2)}"
    app_state["script"] = script_state
    genesis_path.write_text(json.dumps(genesis))
    return genesis_path


def _make_temp_home(node_home):
    temp_dir = Path(tempfile.mkdtemp())
    temp_home = temp_dir / "home"
    shutil.copytree(node_home, temp_home)
    return temp_home


def test_validate_genesis_rejects_nil_script_entry(chainnet, test_config_path):
    dysond = chainnet[0]
    node_home = _get_node_home(test_config_path)
    temp_home = _make_temp_home(node_home)
    _write_genesis(temp_home, {"scripts": [None]})
    result = dysond("genesis", "validate", "--home", str(temp_home))
    assert "nil script entry" in str(result), f"Unexpected result: {result}"


def test_validate_genesis_rejects_empty_script_address(chainnet, test_config_path):
    dysond = chainnet[0]
    node_home = _get_node_home(test_config_path)
    temp_home = _make_temp_home(node_home)
    _write_genesis(temp_home, {"scripts": [{"address": ""}]})
    result = dysond("genesis", "validate", "--home", str(temp_home))
    assert "script address cannot be empty" in str(result), f"Unexpected result: {result}"


def test_validate_genesis_rejects_invalid_script_address(chainnet, test_config_path):
    dysond = chainnet[0]
    node_home = _get_node_home(test_config_path)
    temp_home = _make_temp_home(node_home)
    _write_genesis(temp_home, {"scripts": [{"address": "not-an-address"}]})
    result = dysond("genesis", "validate", "--home", str(temp_home))
    assert "invalid script address" in str(result), f"Unexpected result: {result}"


def test_validate_genesis_rejects_duplicate_script_address(chainnet, test_config_path):
    dysond = chainnet[0]
    node_home = _get_node_home(test_config_path)
    temp_home = _make_temp_home(node_home)
    alice_info = dysond("keys", "show", "alice")
    alice_addr = alice_info.get("address")
    assert isinstance(alice_addr, str), f"alice address invalid: {json.dumps(alice_info, indent=2)}"
    _write_genesis(
        temp_home,
        {"scripts": [{"address": alice_addr}, {"address": alice_addr}]},
    )
    result = dysond("genesis", "validate", "--home", str(temp_home))
    assert "duplicate script address" in str(result), f"Unexpected result: {result}"
