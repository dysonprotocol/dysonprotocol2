import json
import random
import string


def _rand_suffix(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def test_storage_get_by_name_success(chainnet, generate_account, faucet, register_name):
    dysond = chainnet[0]

    # Create owner account and fund
    owner_name, owner_addr = generate_account(
        "owner_name_query", faucet_amount=1_000_000
    )
    faucet(owner_addr)

    # Register a nameservice name and point it to the owner's address
    ns_name = register_name(dysond, owner_name, owner_addr)
    set_dest = dysond(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        ns_name,
        "--destination",
        owner_addr,
        "--from",
        owner_name,
    )
    assert (
        isinstance(set_dest, dict) and set_dest.get("code") == 0
    ), f"set-destination failed: {set_dest}"

    # Write a storage entry under the owner's address
    key = f"ns_storage_key_{_rand_suffix()}"
    value = "hello-ns"
    tx = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        owner_name,
        "--index",
        key,
        "--data",
        value,
    )
    assert tx.get("code") == 0, f"storage set failed: {tx}"

    # Query by address (control)
    by_addr = dysond("query", "storage", "get", owner_addr, "--index", key)
    assert by_addr["entry"]["data"] == value
    assert by_addr["entry"]["owner"] == owner_addr
    assert by_addr["entry"]["index"] == key

    # Query by nameservice name – should resolve to same entry
    by_name = dysond("query", "storage", "get", ns_name, "--index", key)
    assert by_name["entry"]["data"] == value
    assert by_name["entry"]["owner"] == owner_addr  # resolved owner returned
    assert by_name["entry"]["index"] == key


def test_storage_get_by_name_errors(chainnet):
    dysond = chainnet[0]

    # Query using a nonexistent name should produce a helpful error
    bogus_name = f"nonexistent-{_rand_suffix()}.dys"
    res = dysond("query", "storage", "get", bogus_name, "--index", "nope")

    # Print actual error for precise assertion update
    print(f"Actual error: {res}")

    # Stepwise assertions: type, shape, equality
    assert isinstance(
        res, str
    ), f"Expected error string for nonexistent name, got: {type(res)}"

    # Accept either layer by matching the exact inner error substring
    expected = "name not found: " + bogus_name
    assert expected in res, f"Expected '{expected}' not found in: {res}"
