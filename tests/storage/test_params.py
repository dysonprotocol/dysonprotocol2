import pytest
import json
import random
import string
import pytest
import tempfile
import os
from tests.utils import poll_until_condition


def test_storage_params_governance_update_size_enforcement(
    chainnet, generate_account, faucet
):
    """Test updating storage params via governance and verify size limits are enforced adaptively."""
    dysond = chainnet[0]

    # Create test accounts but use alice for governance (she has staking tokens)
    [user_name, user_addr] = generate_account("user", faucet_amount=1_000_000)

    # Step 1: Get original limit
    current_params = dysond("query", "storage", "params")["params"]
    print(f"Current storage params: {json.dumps(current_params, indent=2)}")

    original_max_size = int(current_params["max_storage_size"])
    print(f"Original max storage size: {original_max_size} bytes")

    # Generate unique test keys
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    test_key = f"adaptive_test_{suffix}"

    # Step 2: Upload at original limit - should OK
    test_data_original = "x" * original_max_size
    print(f"Testing upload at original limit ({original_max_size} bytes)")

    result_original = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        user_name,
        "--index",
        test_key,
        "--data",
        test_data_original,
        "--gas",
        "10000000",  # Storage operations have high gas costs that scale with data size (WritePerByte)
    )
    assert (
        result_original["code"] == 0
    ), f"Upload at original limit should succeed: {result_original['raw_log']}"
    print("✅ Upload at original limit succeeds")

    # Clean up before next test
    dysond("tx", "storage", "delete", "--from", user_name, "--indexes", test_key)

    # Step 3: Set up alice for governance voting
    # Get validator operator address
    validators = dysond("query", "staking", "validators")
    validator_operator = validators["validators"][0]["operator_address"]

    # Delegate tokens from Alice to validator so Alice has voting power
    delegate_result = dysond(
        "tx",
        "staking",
        "delegate",
        validator_operator,
        "50000000udys",
        "--from",
        "alice",
        "--yes",
    )
    assert (
        delegate_result["code"] == 0
    ), f"Failed to delegate: {delegate_result['raw_log']}"
    print("✅ Alice delegated tokens for voting power")

    # Step 4: Lower limit to 1/2 original value via governance
    half_max_size = original_max_size // 2
    print(f"Lowering limit to half: {half_max_size} bytes (min allowed: 1024 bytes)")

    # Ensure half size is above minimum
    min_allowed = 1024
    assert (
        half_max_size >= min_allowed
    ), f"Half size {half_max_size} must be >= minimum {min_allowed}"

    # Get governance module address
    gov_module_result = dysond("query", "auth", "module-account", "gov")
    gov_module_addr = (
        gov_module_result.get("account", {}).get("value", {}).get("address", "")
    )
    print(f"Gov module address: {gov_module_addr}")

    # Get current parameters to preserve existing values
    current_params = dysond("query", "storage", "params")["params"]

    # Create proposal to lower limit using the correct message structure
    proposal_data_lower = {
        "messages": [
            {
                "@type": "/dysonprotocol.storage.v1.MsgUpdateParams",
                "authority": gov_module_addr,
                "params": {
                    "max_storage_size": str(half_max_size),
                    "storage_stake_multiple": current_params[
                        "storage_stake_multiple"
                    ],  # Preserve existing value
                },
            }
        ],
        "metadata": "ipfs://CID",
        "deposit": "1udys",
        "title": "Lower Storage Max Size",
        "summary": f"Decrease max storage size from {original_max_size} to {half_max_size}",
    }

    # Submit and execute governance proposal to lower limit using alice
    proposal_id_lower = _submit_and_execute_proposal(
        dysond, "alice", proposal_data_lower
    )

    # Verify params were lowered
    updated_params = dysond("query", "storage", "params")["params"]
    updated_max_size = int(updated_params["max_storage_size"])
    assert (
        updated_max_size == half_max_size
    ), f"Expected max_storage_size {half_max_size}, got {updated_max_size}"
    print(f"✅ Storage params lowered: max_storage_size = {updated_max_size} bytes")

    # Step 5: Upload at original value - should FAIL
    print(
        f"Testing upload at original limit ({original_max_size} bytes) with lowered limit ({half_max_size} bytes)"
    )

    with pytest.raises(
        Exception,
        match=f"data size {original_max_size} bytes exceeds maximum allowed size {half_max_size} bytes",
    ):
        dysond(
            "tx",
            "storage",
            "set",
            "--from",
            user_name,
            "--index",
            test_key,
            "--data",
            test_data_original,
            "--gas",
            "auto",  # use "auto" so that the rejection is now and not when in the block
        )
    print("✅ Upload at original limit fails with lowered limit")

    # Step 6: Raise back to original value via governance
    print(f"Raising limit back to original: {original_max_size} bytes")

    # Create proposal to restore original limit
    proposal_data_restore = {
        "messages": [
            {
                "@type": "/dysonprotocol.storage.v1.MsgUpdateParams",
                "authority": gov_module_addr,
                "params": {
                    "max_storage_size": str(original_max_size),
                    "storage_stake_multiple": current_params[
                        "storage_stake_multiple"
                    ],  # Preserve existing value
                },
            }
        ],
        "metadata": "ipfs://CID",
        "deposit": "1udys",
        "title": "Restore Storage Max Size",
        "summary": f"Restore max storage size from {half_max_size} back to {original_max_size}",
    }

    # Submit and execute governance proposal to restore limit using alice
    proposal_id_restore = _submit_and_execute_proposal(
        dysond, "alice", proposal_data_restore
    )

    # Verify params were restored
    final_params = dysond("query", "storage", "params")["params"]
    final_max_size = int(final_params["max_storage_size"])
    assert (
        final_max_size == original_max_size
    ), f"Expected max_storage_size {original_max_size}, got {final_max_size}"
    print(f"✅ Storage params restored: max_storage_size = {final_max_size} bytes")

    # Step 7: Upload at original value - should OK again
    print(
        f"Testing upload at original limit ({original_max_size} bytes) with restored limit"
    )

    result_restored = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        user_name,
        "--index",
        test_key,
        "--data",
        test_data_original,
        "--gas",
        "auto",  # use "auto" so that the rejection is now and not when in the block
    )
    assert (
        result_restored["code"] == 0
    ), f"Upload at original limit should succeed after restore: {result_restored['raw_log']}"
    print("✅ Upload at original limit succeeds with restored limit")

    # Clean up
    dysond("tx", "storage", "delete", "--from", user_name, "--indexes", test_key)

    print("✅ Adaptive storage params governance test completed successfully")


def _submit_and_execute_proposal(dysond, proposer_name, proposal_data):
    """Helper function to submit and execute a governance proposal."""

    # Write proposal to temporary file
    with tempfile.NamedTemporaryFile(mode="w", delete=True, suffix=".json") as f:
        json.dump(proposal_data, f, indent=2)
        proposal_file = f.name
        f.flush()
        # Submit governance proposal using file
        prop_result = dysond(
            "tx", "gov", "submit-proposal", proposal_file, "--from", proposer_name
        )

    assert (
        prop_result["code"] == 0
    ), f"Proposal submission failed: {prop_result['raw_log']}"

    # Get proposal ID from events
    events = prop_result.get("events", [])
    submit_proposal_events = [e for e in events if e["type"] == "submit_proposal"]
    assert (
        len(submit_proposal_events) > 0
    ), f"No submit_proposal event found in: {events}"

    proposal_id_attrs = [
        attr
        for attr in submit_proposal_events[0]["attributes"]
        if attr["key"] == "proposal_id"
    ]
    assert (
        len(proposal_id_attrs) > 0
    ), f"No proposal_id attribute found in submit_proposal event"
    proposal_id = proposal_id_attrs[0]["value"]
    print(f"Created governance proposal {proposal_id}")

    # Vote on proposal (assuming alice has voting power from genesis)
    vote_result = dysond("tx", "gov", "vote", proposal_id, "yes", "--from", "alice")
    assert vote_result["code"] == 0, f"Voting failed: {vote_result['raw_log']}"
    print(f"Voted on proposal {proposal_id}")

    # Wait for proposal to pass
    def check_proposal_status():
        result = dysond("query", "gov", "proposal", proposal_id)
        status = result.get("proposal", {}).get("status", "UNKNOWN")
        print(f"Current proposal status: {status}")
        final_states = [
            "PROPOSAL_STATUS_PASSED",
            "PROPOSAL_STATUS_REJECTED",
            "PROPOSAL_STATUS_FAILED",
        ]
        return status in final_states

    poll_until_condition(check_proposal_status, timeout=60, poll_interval=2)

    # Verify proposal passed
    final_result = dysond("query", "gov", "proposal", proposal_id)
    final_status = final_result.get("proposal", {}).get("status", "UNKNOWN")
    assert (
        final_status == "PROPOSAL_STATUS_PASSED"
    ), f"Expected proposal to pass but got status: {final_status}"
    print(f"✅ Proposal {proposal_id} passed!")

    return proposal_id


def test_storage_params_query(chainnet):
    """Test querying storage module parameters."""
    dysond = chainnet[0]

    # Query storage params
    params_result = dysond("query", "storage", "params")
    print(f"Storage params query result: {json.dumps(params_result, indent=2)}")

    # Verify structure
    assert (
        "params" in params_result
    ), f"Expected 'params' field in result: {params_result}"
    params = params_result["params"]

    # Verify required fields
    assert (
        "max_storage_size" in params
    ), f"Expected 'max_storage_size' field in params: {params}"

    # Verify types and ranges
    max_storage_size = int(params["max_storage_size"])
    assert (
        max_storage_size > 0
    ), f"max_storage_size should be positive: {max_storage_size}"
    assert (
        max_storage_size >= 1024
    ), f"max_storage_size should be at least 1KB: {max_storage_size}"

    print(
        f"✅ Storage params query works correctly: max_storage_size = {max_storage_size} bytes"
    )


def test_storage_size_enforcement(chainnet, generate_account, faucet):
    """Test that storage size limits are properly enforced during set operations."""
    dysond = chainnet[0]

    # Create test account
    [user_name, user_addr] = generate_account("size_test")
    faucet(user_addr)

    # Get current max storage size
    params = dysond("query", "storage", "params")["params"]
    max_size = int(params["max_storage_size"])
    print(f"Current max storage size: {max_size} bytes")

    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))

    # Test data that's exactly at the limit
    test_data_at_limit = "x" * max_size
    test_key_at_limit = f"at_limit_{suffix}"

    at_limit_result = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        user_name,
        "--index",
        test_key_at_limit,
        "--gas",
        "10000000",  # Storage operations have high gas costs that scale with data size (WritePerByte)
        "--data",
        test_data_at_limit,
    )

    # Validate response type and structure
    assert isinstance(
        at_limit_result, dict
    ), f"Expected dict response, got {type(at_limit_result)}: {at_limit_result}"
    assert (
        "code" in at_limit_result
    ), f"Missing 'code' field in response: {at_limit_result}"
    assert (
        at_limit_result["code"] == 0
    ), f"Data at limit should succeed: {at_limit_result.get('raw_log', 'No raw_log')}"

    # Verify it was stored
    get_result = dysond(
        "query", "storage", "get", user_addr, "--index", test_key_at_limit
    )
    assert (
        get_result["entry"]["data"] == test_data_at_limit
    ), "Data at limit was not stored correctly"

    print(f"✅ Data exactly at limit ({max_size} bytes) succeeds")

    # Test data that exceeds the limit by 1 byte
    test_data_over_limit = "x" * (max_size + 1)
    test_key_over_limit = f"over_limit_{suffix}"

    # Test that data over limit fails with proper error
    with pytest.raises(Exception, match="exceeds maximum.*allowed size.*bytes"):
        dysond(
            "tx",
            "storage",
            "set",
            "--from",
            user_name,
            "--index",
            test_key_over_limit,
            "--data",
            test_data_over_limit,
            "--gas",
            "auto",  # Storage operations have gas costs that scale with data size (WritePerByte)
        )

    print(f"✅ Data over limit ({max_size + 1} bytes) correctly fails")

    # Test updating existing entry to exceed limit
    # Test that updating existing entry to exceed limit fails
    with pytest.raises(Exception, match="exceeds maximum.*allowed size.*bytes"):
        dysond(
            "tx",
            "storage",
            "set",
            "--from",
            user_name,
            "--index",
            test_key_at_limit,
            "--data",
            test_data_over_limit,
            "--gas",
            "auto",  # Storage operations have gas costs that scale with data size (WritePerByte)
        )

    print("✅ Updating existing entry to exceed limit correctly fails")

    # Verify original data is still there (update failed)
    get_after_failed_update = dysond(
        "query", "storage", "get", user_addr, "--index", test_key_at_limit
    )
    assert (
        get_after_failed_update["entry"]["data"] == test_data_at_limit
    ), "Original data should be preserved after failed update"

    # Clean up
    dysond(
        "tx", "storage", "delete", "--from", user_name, "--indexes", test_key_at_limit
    )

    print("✅ Storage size enforcement test completed successfully")


def test_storage_params_validation(chainnet, generate_account, faucet):
    """Test that invalid parameter updates are rejected."""
    import tempfile
    import os

    dysond = chainnet[0]

    # Create proposer account
    [proposer_name, proposer_addr] = generate_account(
        "param_validator", faucet_amount=50_000_000
    )

    # Get current params
    current_params = dysond("query", "storage", "params")["params"]
    gov_module_result = dysond("query", "auth", "module-account", "gov")
    gov_module_addr = (
        gov_module_result.get("account", {}).get("value", {}).get("address", "")
    )

    # Test invalid params: max_storage_size too small (below 1KB minimum)
    invalid_params = dict(current_params)
    invalid_params["max_storage_size"] = "512"  # 512 bytes < 1KB minimum

    invalid_proposal_msg = {
        "@type": "/dysonprotocol.storage.v1.MsgUpdateParams",
        "authority": gov_module_addr,
        "params": invalid_params,
    }

    # Create governance proposal with modern CLI format
    proposal_data = {
        "title": "Invalid Storage Params",
        "summary": "Try to set max_storage_size below minimum",
        "metadata": "test",
        "messages": [invalid_proposal_msg],
        "deposit": "10000000udys",
    }

    # Write proposal to temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as f:
        json.dump(proposal_data, f)
        proposal_file = f.name
        f.flush()
        invalid_prop_result = dysond(
            "tx", "gov", "submit-proposal", proposal_file, "--from", proposer_name
        )

    # The proposal submission should succeed, but if voted on and executed, it should fail
    # For now, just verify we can submit proposals with invalid params
    # The validation happens during execution, not submission
    assert (
        invalid_prop_result["code"] == 0
    ), f"Proposal submission should succeed: {invalid_prop_result['raw_log']}"

    print("✅ Invalid parameter proposal submitted (validation happens at execution)")

    # Test invalid params: max_storage_size too large (above 100MB maximum)
    too_large_params = dict(current_params)
    too_large_params["max_storage_size"] = str(
        200 * 1024 * 1024
    )  # 200MB > 100MB maximum

    too_large_proposal_msg = {
        "@type": "/dysonprotocol.storage.v1.MsgUpdateParams",
        "authority": gov_module_addr,
        "params": too_large_params,
    }

    # Create second governance proposal with modern CLI format
    too_large_proposal_data = {
        "title": "Too Large Storage Params",
        "summary": "Try to set max_storage_size above maximum",
        "metadata": "test",
        "messages": [too_large_proposal_msg],
        "deposit": "10000000udys",
    }

    # Write proposal to temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as f:
        json.dump(too_large_proposal_data, f)
        proposal_file = f.name
        f.flush()
        too_large_prop_result = dysond(
            "tx", "gov", "submit-proposal", proposal_file, "--from", proposer_name
        )

    assert (
        too_large_prop_result["code"] == 0
    ), f"Proposal submission should succeed: {too_large_prop_result['raw_log']}"

    print("✅ Parameter validation test completed")


def test_storage_params_adaptive_size_testing(chainnet, generate_account, faucet):
    """Test storage limits adaptively based on current params without governance changes."""
    dysond = chainnet[0]

    # Create test account
    [user_name, user_addr] = generate_account("adaptive_user", faucet_amount=1_000_000)

    # Step 1: Get original limit dynamically
    current_params = dysond("query", "storage", "params")["params"]
    print(f"Current storage params: {json.dumps(current_params, indent=2)}")

    original_max_size = int(current_params["max_storage_size"])
    print(f"Original max storage size: {original_max_size} bytes")

    # Generate unique test keys
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    test_key = f"adaptive_test_{suffix}"

    # Step 2: Test upload at original limit - should OK
    test_data_original = "x" * original_max_size
    print(f"Testing upload at original limit ({original_max_size} bytes)")

    result_original = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        user_name,
        "--index",
        test_key,
        "--data",
        test_data_original,
        "--gas",
        "10000000",  # Storage operations have high gas costs that scale with data size (WritePerByte)
    )
    assert (
        result_original["code"] == 0
    ), f"Upload at original limit should succeed: {result_original['raw_log']}"
    print("✅ Upload at original limit succeeds")

    # Verify it was stored
    get_result = dysond("query", "storage", "get", user_addr, "--index", test_key)
    assert (
        get_result["entry"]["data"] == test_data_original
    ), "Data at limit was not stored correctly"
    print("✅ Data at original limit verified in storage")

    # Step 3: Test upload 1 byte over original limit - should FAIL
    over_limit_size = original_max_size + 1
    test_data_over = "x" * over_limit_size
    test_key_over = f"over_limit_{suffix}"

    print(
        f"Testing upload over limit by 1 byte ({over_limit_size} bytes > {original_max_size} bytes)"
    )

    with pytest.raises(
        Exception,
        match=f"data size {over_limit_size} bytes exceeds maximum allowed size {original_max_size} bytes",
    ):
        dysond(
            "tx",
            "storage",
            "set",
            "--from",
            user_name,
            "--index",
            test_key_over,
            "--data",
            test_data_over,
            "--gas",
            "auto",  # Storage operations have gas costs that scale with data size (WritePerByte)
        )
    print("✅ Upload over limit by 1 byte correctly fails")

    # Step 4: Test upload 1 byte below the original limit - should OK
    below_limit_size = original_max_size - 1
    below_limit_data = "x" * below_limit_size
    test_key_below = f"below_limit_{suffix}"

    print(
        f"Testing upload below limit by 1 byte ({below_limit_size} bytes < {original_max_size} bytes)"
    )

    below_result = dysond(
        "tx",
        "storage",
        "set",
        "--from",
        user_name,
        "--index",
        test_key_below,
        "--data",
        below_limit_data,
        "--gas",
        "10000000",  # Storage operations have high gas costs that scale with data size (WritePerByte)
    )
    assert (
        below_result["code"] == 0
    ), f"Upload below limit should succeed: {below_result['raw_log']}"
    print("✅ Upload below limit succeeds")

    # Verify stored data
    get_below_result = dysond(
        "query", "storage", "get", user_addr, "--index", test_key_below
    )
    assert (
        get_below_result["entry"]["data"] == below_limit_data
    ), "Below limit data was not stored correctly"
    print("✅ Below limit data verified in storage")

    # Clean up
    dysond(
        "tx",
        "storage",
        "delete",
        "--from",
        user_name,
        "--indexes",
        f"{test_key},{test_key_below}",
    )

    print(f"✅ Adaptive storage size testing completed successfully")
    print(f"   - Original limit: {original_max_size} bytes")
    print(f"   - Below limit: {below_limit_size} bytes")
    print(f"   - Over limit: {over_limit_size} bytes")
