"""
State Channels Test Fixtures - PBI-40

Shared fixtures for state channel tests.
"""

from pathlib import Path

import pytest


# Path to the state channel script
SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "examples" / "state_channels" / "script.py"
)


@pytest.fixture(scope="session")
def sc_script(chainnet, generate_account):
    """
    Deploy the state channel script and create test participants once per session.

    Returns dict with:
        - script_address: Address where script is deployed
        - dysond: The dysond command runner
        - participants: List of (name, addr) tuples for 4 test participants
    """
    dysond = chainnet[0]

    status_result = dysond("status")
    chain_id = status_result["node_info"]["network"]

    # Deploy using alice's address
    alice_info = dysond("keys", "show", "alice")
    script_address = alice_info["address"]

    # Deploy the script
    tx_result = dysond(
        "tx",
        "script",
        "update",
        "--from",
        "alice",
        "--code-path",
        str(SCRIPT_PATH),
        "--chain-id",
        chain_id,
        "--gas",
        "5000000",
    )
    assert (
        tx_result.get("code", 1) == 0
    ), f"State channel script deployment failed: {tx_result}"

    # Create 4 test participants once per session
    participants = []
    for i in range(4):
        name, addr = generate_account(f"sc_p{i+1}", faucet_amount=1000)
        participants.append((name, addr))

    return {
        "script_address": script_address,
        "dysond": dysond,
        "participants": participants,
    }


@pytest.fixture(scope="session")
def sc_participants(sc_script):
    """Get the 4 test participants created in sc_script fixture."""
    return sc_script["participants"]
