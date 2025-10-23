"""
Fixtures for hypothesis-based whaleswap testing.
"""

import pytest
from pathlib import Path


@pytest.fixture(scope="session")
def executor_script_path():
    """Path to the whaleswap executor script."""
    return Path(__file__).parent / "whaleswap_executor.py"


@pytest.fixture(scope="session")
def hypo_accounts(generate_account, faucet):
    """
    Generate test accounts with balances for all operations.

    This is the ONLY fixture that does blockchain setup.
    Everything else happens in the query exec.

    Session-scoped for performance since accounts are reusable.
    """
    # Generate accounts with balances for all operations
    [alice_name, alice_addr] = generate_account("alice_hypo", faucet_amount=1_000_000)
    [bob_name, bob_addr] = generate_account("bob_hypo", faucet_amount=1_000_000)
    [charlie_name, charlie_addr] = generate_account(
        "charlie_hypo", faucet_amount=1_000_000
    )

    return {
        "alice_addr": alice_addr,
        "alice_name": alice_name,
        "bob_addr": bob_addr,
        "bob_name": bob_name,
        "charlie_addr": charlie_addr,
        "charlie_name": charlie_name,
        "accounts": [alice_addr, bob_addr, charlie_addr],
    }


@pytest.fixture(scope="session")
def gov_addr(chainnet):
    """Return the governance module address by querying the auth module."""
    dysond = chainnet[0]

    result = dysond("query", "auth", "module-account", "gov", "-o", "json")

    return result["account"]["value"]["address"]


@pytest.fixture(scope="session")
def registered_names(chainnet, hypo_accounts, register_name):
    """
    Session-scoped fixture that registers names and mints coins once per session.

    Returns dict with foo_name and bar_name that tests can reuse.
    """
    dysond = chainnet[0]
    alice_addr = hypo_accounts["alice_addr"]
    alice_name = hypo_accounts["alice_name"]

    # Register foo.dys
    foo_name = register_name(dysond, alice_name, alice_addr)

    # Register bar.dys
    bar_name = register_name(dysond, alice_name, alice_addr)

    # Mint coins for both names (alice gets 1M of each)
    params = dysond("query", "nameservice", "params")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_fee = int(1_000_000 * fee_per + 0.99999)  # ceiling

    # Mint foo.dys coins
    dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"1000000{foo_name}",
        "--mint-fee",
        f"{mint_fee}udys",
        "--from",
        alice_name,
    )

    # Mint bar.dys coins
    dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"1000000{bar_name}",
        "--mint-fee",
        f"{mint_fee}udys",
        "--from",
        alice_name,
    )

    return {
        "foo_name": foo_name,
        "bar_name": bar_name,
    }
