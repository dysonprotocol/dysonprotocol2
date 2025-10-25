#!/usr/bin/env python3

"""
Integration tests for nameservice reverse mapping functionality.
Tests the QueryNamesByDestination query and reverse mapping updates.
"""

import pytest
import os
from tests.utils import poll_until_condition


def test_reverse_mapping_creation_on_name_registration(
    chainnet, generate_account, faucet, register_name
):
    """Test that reverse mappings are created when names are registered with destinations."""

    dysond_bin = chainnet[0]

    # Generate test account
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10000000")

    # Register a name (this will create initial destination mapping to alice_address)
    name = register_name(dysond_bin, alice_name, alice_address)

    # Step 2: Query names by destination to verify reverse mapping was created during registration
    query_result = dysond_bin(
        "query",
        "nameservice",
        "query-names-by-destination",
        "--destination",
        alice_address,
    )

    assert "names" in query_result, f"Missing 'names' field in response: {query_result}"
    assert (
        name in query_result["names"]
    ), f"Name {name} not found in reverse mapping for {alice_address}. Response: {query_result}"


def test_reverse_mapping_update_on_destination_change(
    chainnet, generate_account, faucet, register_name
):
    """Test that reverse mappings are updated when destination changes."""

    dysond_bin = chainnet[0]

    # Generate test accounts
    [alice_name, alice_address] = generate_account("alice")
    [bob_name, bob_address] = generate_account("bob")
    faucet(alice_address, denom="udys", amount="10000000")

    # Register a name (initially points to alice_address)
    name = register_name(dysond_bin, alice_name, alice_address)

    # Change destination to bob's address
    set_dest_result = dysond_bin(
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name,
        "--destination",
        bob_address,
        "--from",
        alice_name,
        "--yes",
    )

    assert (
        set_dest_result.get("code", 1) == 0
    ), f"Set destination failed: {set_dest_result}"

    # Verify old destination no longer has the name
    old_query = dysond_bin(
        "query",
        "nameservice",
        "query-names-by-destination",
        "--destination",
        alice_address,
    )

    # Should be empty or not contain the name
    names_in_old = old_query.get("names", [])
    assert (
        name not in names_in_old
    ), f"Name {name} still mapped to old destination {alice_address}. Response: {old_query}"

    # Verify new destination has the name
    new_query = dysond_bin(
        "query",
        "nameservice",
        "query-names-by-destination",
        "--destination",
        bob_address,
    )

    assert (
        "names" in new_query
    ), f"Missing 'names' field in new destination response: {new_query}"
    assert (
        name in new_query["names"]
    ), f"Name {name} not found in new destination mapping. Response: {new_query}"


def test_query_pagination(chainnet, generate_account, faucet, register_name):
    """Test that the query supports pagination properly."""

    dysond_bin = chainnet[0]

    # Generate test account
    [alice_name, alice_address] = generate_account("alice")
    faucet(
        alice_address, denom="udys", amount="50000000"
    )  # More funds for multiple registrations

    # Register multiple names (all will initially point to alice_address)
    names = []
    for i in range(5):
        name = register_name(dysond_bin, alice_name, alice_address)
        names.append(name)

    # Query with pagination limit
    paginated_query = dysond_bin(
        "query",
        "nameservice",
        "query-names-by-destination",
        "--destination",
        alice_address,
        "--page-limit",
        "3",
    )

    assert (
        "names" in paginated_query
    ), f"Missing 'names' field in paginated response: {paginated_query}"
    assert (
        "pagination" in paginated_query
    ), f"Missing 'pagination' field in paginated response: {paginated_query}"

    # Should return at most 3 names
    returned_names = paginated_query["names"]
    assert (
        len(returned_names) <= 3
    ), f"Expected at most 3 names, got {len(returned_names)}: {returned_names}"

    # Check that all returned names are in our expected set
    for returned_name in returned_names:
        assert (
            returned_name in names
        ), f"Unexpected name {returned_name} returned. Expected one of: {names}"
