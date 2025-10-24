import pytest
from utils import poll_until_condition
from pathlib import Path


def test_chainnet_bank_send(chainnet, generate_account, faucet):
    """Test bank send on chainnet network using generated account and faucet."""
    dysond_bin = chainnet[0]

    # Create a new account and fund it
    [alice_name, alice_addr] = generate_account("alice")
    faucet(alice_addr, denom="udys", amount="11")

    [bob_name, bob_addr] = generate_account("bob")
    faucet(bob_addr, denom="udys", amount="5")

    def get_balance(addr):
        print(f"Getting balance for {addr}")
        out = dysond_bin("query", "bank", "balances", addr)
        balances = out["balances"]
        print(f"Balances: {balances}")
        return (
            {b["denom"]: int(b["amount"]) for b in balances}["udys"] if balances else 0
        )

    expected_bob_bal = get_balance(bob_addr)
    expected_alice_bal = get_balance(alice_addr)
    for i in range(10):
        print(f"Iteration {i}")
        send_amt = 1
        tx_out = dysond_bin(
            "tx",
            "bank",
            "send",
            alice_addr,
            bob_addr,
            str(send_amt) + "udys",
            "--from",
            alice_name,
        )
        assert tx_out["code"] == 0, f"Transaction failed: {tx_out.get('raw_log', '')}"

        expected_bob_bal += send_amt
        expected_alice_bal -= send_amt
        assert get_balance(bob_addr) == expected_bob_bal
        assert get_balance(alice_addr) == expected_alice_bal


def test_chainnet_with_ibc_setup(ibc_setup, generate_account, faucet):
    """Test that demonstrates using the ibc_setup fixture for IBC functionality."""
    dysond_bin = ibc_setup[0]

    # Create an account and fund it
    [alice_name, alice_addr] = generate_account("alice")
    faucet(alice_addr, denom="udys", amount="100")

    # Test basic functionality - IBC setup should be running in background
    balance_out = dysond_bin("query", "bank", "balances", alice_addr)
    balances = balance_out["balances"]
    assert len(balances) > 0
    assert balances[0]["denom"] == "udys"
    assert int(balances[0]["amount"]) >= 100

    # Query IBC channels (they may not be ready yet since IBC setup runs in background)
    channels = dysond_bin("query", "ibc", "channel", "channels")
    assert "channels" in channels
    # Just verify the query works, channels may still be setting up


def test_fixtures_independent(test_base_dir, test_config_path):
    """Test that the base fixtures work independently of chainnet."""
    # Test that base directory exists and is a Path object
    assert isinstance(test_base_dir, Path)
    print(f"Test base directory: {test_base_dir}")

    # Test that config path is properly constructed
    assert isinstance(test_config_path, Path)
    assert test_config_path.name == "chains.json"
    assert test_config_path.parent == test_base_dir
    print(f"Test config path: {test_config_path}")

    # These fixtures can be used without starting the full chainnet
    # This is useful for setup/teardown or configuration testing
