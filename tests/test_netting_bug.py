#!/usr/bin/env python3
"""
Test to reproduce the netting bug where inputs=1, outputs=0.

This test creates a scenario where the netting logic results in unbalanced
inputs and outputs, causing the "inputs/outputs cannot be empty" error.
"""

import json
import subprocess
import sys
import time


def run_cmd(cmd, check=True):
    """Run a command and return the result."""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Command failed: {cmd}")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        sys.exit(1)
    return result


def setup_test_environment():
    """Set up the test environment with accounts and offers."""
    print("Setting up test environment...")

    # Create test accounts
    run_cmd("dysond keys add test_trader --keyring-backend test")
    run_cmd("dysond keys add test_maker1 --keyring-backend test")
    run_cmd("dysond keys add test_maker2 --keyring-backend test")

    # Get addresses
    trader_addr = run_cmd(
        "dysond keys show test_trader -a --keyring-backend test"
    ).stdout.strip()
    maker1_addr = run_cmd(
        "dysond keys show test_maker1 -a --keyring-backend test"
    ).stdout.strip()
    maker2_addr = run_cmd(
        "dysond keys show test_maker2 -a --keyring-backend test"
    ).stdout.strip()

    print(f"Trader: {trader_addr}")
    print(f"Maker1: {maker1_addr}")
    print(f"Maker2: {maker2_addr}")

    # Fund accounts
    run_cmd(f"dysond tx bank send alice {trader_addr} 1000000udys --from alice -y")
    run_cmd(f"dysond tx bank send alice {maker1_addr} 1000000udys --from alice -y")
    run_cmd(f"dysond tx bank send alice {maker2_addr} 1000000udys --from alice -y")

    # Create custom denoms
    run_cmd(f"dysond tx nameservice mint-denom trader.dys --from {trader_addr} -y")
    run_cmd(f"dysond tx nameservice mint-denom maker1.dys --from {maker1_addr} -y")
    run_cmd(f"dysond tx nameservice mint-denom maker2.dys --from {maker2_addr} -y")

    # Distribute some custom tokens
    run_cmd(
        f"dysond tx bank send {trader_addr} {maker1_addr} 100000trader.dys --from {trader_addr} -y"
    )
    run_cmd(
        f"dysond tx bank send {trader_addr} {maker2_addr} 100000trader.dys --from {trader_addr} -y"
    )

    return trader_addr, maker1_addr, maker2_addr


def create_offers(trader_addr, maker1_addr, maker2_addr):
    """Create offers that will trigger the netting bug."""
    print("Creating offers...")

    # Create offers where the trader can net their outputs against makers' wants
    # This should create a scenario where netting results in inputs=1, outputs=0

    # Offer 1: Maker1 wants trader.dys, has maker1.dys
    run_cmd(
        f"dysond tx whaleswap make-offer "
        f"--want 1000trader.dys "
        f"--have 2000maker1.dys "
        f"--from {maker1_addr} -y"
    )

    # Offer 2: Maker2 wants trader.dys, has maker2.dys
    run_cmd(
        f"dysond tx whaleswap make-offer "
        f"--want 1000trader.dys "
        f"--have 2000maker2.dys "
        f"--from {maker2_addr} -y"
    )

    # Give the trader some of the makers' tokens so they can net
    run_cmd(
        f"dysond tx bank send {maker1_addr} {trader_addr} 1000maker1.dys --from {maker1_addr} -y"
    )
    run_cmd(
        f"dysond tx bank send {maker2_addr} {trader_addr} 1000maker2.dys --from {maker2_addr} -y"
    )


def test_netting_bug(trader_addr):
    """Test the netting bug by attempting a trade that should fail."""
    print("Testing netting bug...")

    # Get the offer IDs
    offers_result = run_cmd("dysond query whaleswap offers --output json")
    offers = json.loads(offers_result.stdout)

    if len(offers) < 2:
        print("Not enough offers created")
        return False

    offer1_id = offers[0]["offer_id"]
    offer2_id = offers[1]["offer_id"]

    print(f"Using offers {offer1_id} and {offer2_id}")

    # Attempt a trade that should trigger the netting bug
    # The trader will take both offers, but the netting should result in unbalanced inputs/outputs
    result = run_cmd(
        f"dysond tx whaleswap make-trade "
        f"--from {trader_addr} "
        f"--max-input 2000trader.dys "
        f'--op \'{{"take": {{"offer_id": "{offer1_id}", "take_units": "1"}}}}\' '
        f'--op \'{{"take": {{"offer_id": "{offer2_id}", "take_units": "1"}}}}\' '
        f"--note 'Test netting bug' -y",
        check=False,
    )

    print(f"Trade result: {result.returncode}")
    print(f"STDOUT: {result.stdout}")
    print(f"STDERR: {result.stderr}")

    # Check if we got the expected error
    if (
        "inputs/outputs cannot be empty" in result.stderr
        or "invalid netting result" in result.stderr
    ):
        print("✓ Bug reproduced: Got expected netting error")
        return True
    elif result.returncode == 0:
        print("✗ Bug not reproduced: Trade succeeded unexpectedly")
        return False
    else:
        print(f"✗ Unexpected error: {result.stderr}")
        return False


def main():
    """Main test function."""
    print("=== Netting Bug Reproduction Test ===")

    try:
        # Setup
        trader_addr, maker1_addr, maker2_addr = setup_test_environment()

        # Create offers
        create_offers(trader_addr, maker1_addr, maker2_addr)

        # Test the bug
        bug_reproduced = test_netting_bug(trader_addr)

        if bug_reproduced:
            print("\n✓ Test PASSED: Bug successfully reproduced")
            print(
                "The netting logic has a bug that results in unbalanced inputs/outputs"
            )
        else:
            print("\n✗ Test FAILED: Bug not reproduced")
            print("Either the bug is fixed or the test scenario doesn't trigger it")

    except Exception as e:
        print(f"Test failed with exception: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
