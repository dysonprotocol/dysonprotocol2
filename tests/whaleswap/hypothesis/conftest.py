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
