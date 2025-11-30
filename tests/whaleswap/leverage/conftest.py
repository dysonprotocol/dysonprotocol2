import json
import pytest


@pytest.fixture(scope="session")
def leverage_accounts(chainnet, generate_account, faucet):
    """
    Create 3 test accounts with sufficient balance for leverage testing.
    Session-scoped for reuse across all leverage tests.
    """
    dysond = chainnet[0]
    alice = generate_account("leverage_alice", faucet_amount=5_000_000)
    bob = generate_account("leverage_bob", faucet_amount=5_000_000)
    charlie = generate_account("leverage_charlie", faucet_amount=5_000_000)

    return {
        "alice": {"name": alice[0], "addr": alice[1]},
        "bob": {"name": bob[0], "addr": bob[1]},
        "charlie": {"name": charlie[0], "addr": charlie[1]},
    }


@pytest.fixture(scope="session")
def leverage_names_and_coins(
    chainnet, generate_account, faucet, register_name, leverage_accounts
):
    """
    Register 3 names and mint 1,000,000 coins of each.
    Names are reusable across all leverage tests.
    Session-scoped for performance.
    """
    dysond = chainnet[0]
    alice_name = leverage_accounts["alice"]["name"]
    alice_addr = leverage_accounts["alice"]["addr"]

    # Register 3 names
    foo_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    bar_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")
    qux_name = register_name(dysond, alice_name, alice_addr, valuation="10udys")

    # Get mint fee from params
    params = dysond("query", "nameservice", "params")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_fee = int(1_000_000 * fee_per + 0.99999)  # ceiling

    # Mint 1M of each name
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

    dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"1000000{qux_name}",
        "--mint-fee",
        f"{mint_fee}udys",
        "--from",
        alice_name,
    )

    # Distribute coins to bob and charlie (300K each denom)
    dysond(
        "tx",
        "bank",
        "send",
        alice_addr,
        leverage_accounts["bob"]["addr"],
        f"300000{foo_name},300000{bar_name},300000{qux_name}",
        "--from",
        alice_name,
    )

    dysond(
        "tx",
        "bank",
        "send",
        alice_addr,
        leverage_accounts["charlie"]["addr"],
        f"300000{foo_name},300000{bar_name},300000{qux_name}",
        "--from",
        alice_name,
    )

    return {
        "foo_name": foo_name,
        "bar_name": bar_name,
        "qux_name": qux_name,
        "alice_addr": alice_addr,
    }
