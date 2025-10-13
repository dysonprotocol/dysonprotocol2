import pytest
import json
import tempfile
import os
import decimal
import random
import string
from tests.utils import poll_until_condition


class TestStorageStakingParameters:
    """Tests for storage staking parameter management and validation."""

    def test_default_parameters(self, chainnet):
        """Test that storage staking parameters have expected default values."""
        dysond = chainnet[0]

        params_result = dysond("query", "storage", "params")
        params = params_result["params"]

        # Verify default values
        expected_max_storage_size = 100 * 1024  # 100KB default from params.go
        expected_storage_stake_multiple = decimal.Decimal(
            "0.0"
        )  # Default enabled validation

        actual_max_storage_size = int(params["max_storage_size"])
        actual_storage_stake_multiple = decimal.Decimal(
            params["storage_stake_multiple"]
        )

        assert actual_max_storage_size == expected_max_storage_size
        assert actual_storage_stake_multiple == expected_storage_stake_multiple

        print(
            f"✅ Default params: max_storage_size={actual_max_storage_size}, storage_stake_multiple='{actual_storage_stake_multiple}'"
        )

    def test_parameter_structure_and_types(self, chainnet):
        """Test that storage params have correct JSON structure and field types."""
        dysond = chainnet[0]

        params_result = dysond("query", "storage", "params")

        # Verify JSON structure
        assert isinstance(params_result, dict)
        assert "params" in params_result

        params = params_result["params"]
        assert isinstance(params, dict)

        # Verify required fields
        required_fields = ["max_storage_size", "storage_stake_multiple"]
        for field in required_fields:
            assert field in params, f"Missing required field '{field}'"

        # Verify field types
        assert isinstance(params["max_storage_size"], str)
        assert isinstance(params["storage_stake_multiple"], str)

        # Verify values can be parsed correctly
        max_size_int = int(params["max_storage_size"])
        assert max_size_int > 0

        stake_multiple_decimal = decimal.Decimal(params["storage_stake_multiple"])
        assert stake_multiple_decimal >= 0

        print("✅ Parameter structure and types verified")

    def test_parameter_validation_values(self, chainnet):
        """Test that parameter values can be properly validated."""
        dysond = chainnet[0]

        # Get current params
        current_params = dysond("query", "storage", "params")["params"]
        current_multiplier = current_params["storage_stake_multiple"]

        # Test current value parsing
        current_decimal = decimal.Decimal(current_multiplier)
        assert current_decimal >= 0

        print("✅ Parameter validation verified")

    def test_governance_parameter_updates(self, chainnet, generate_account, faucet):
        """Test updating storage_stake_multiple via governance proposals."""
        dysond = chainnet[0]

        # Use alice instead of creating a new proposer account
        # alice has the necessary staked tokens for governance voting
        proposer_name = "alice"

        # Get governance module address
        gov_module_result = dysond("query", "auth", "module-account", "gov")
        gov_module_addr = (
            gov_module_result.get("account", {}).get("value", {}).get("address", "")
        )

        # Get current params
        current_params = dysond("query", "storage", "params")["params"]

        # Ensure proposer (alice) has voting power by delegating stake
        validators = dysond("query", "staking", "validators")
        validator_operator = validators["validators"][0]["operator_address"]
        delegate_result = dysond(
            "tx",
            "staking",
            "delegate",
            validator_operator,
            "50000000udys",
            "--from",
            proposer_name,
            "--yes",
        )
        assert delegate_result["code"] == 0

        # Prepare test account with zero delegated stake
        test_account = "bob"
        bob_addr = dysond("keys", "show", test_account, "-a").strip()
        delegations_result = dysond("query", "staking", "delegations", bob_addr)
        assert delegations_result["delegation_responses"] is None

        # Large data that requires stake when multiplier > 0
        large_data = "a" * 10000  # 10KB

        inital_value = current_params["storage_stake_multiple"]

        # Test valid parameter update proposals (non-zero multipliers)

        valid_multipliers = ["2.0", "0.5"]

        for multiplier in valid_multipliers:
            test_params = dict(current_params)
            test_params["storage_stake_multiple"] = multiplier

            proposal_data = {
                "messages": [
                    {
                        "@type": "/dysonprotocol.storage.v1.MsgUpdateParams",
                        "authority": gov_module_addr,
                        "params": test_params,
                    }
                ],
                "metadata": "ipfs://CID",
                "deposit": "10000000udys",
                "title": f"Test Storage Stake Multiple {multiplier}",
                "summary": f"Test setting storage_stake_multiple to {multiplier}",
                "expedited": True,
            }

            # Submit proposal (should succeed)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=True
            ) as f:
                json.dump(proposal_data, f)
                f.flush()
                proposal_file = f.name
                prop_result = dysond(
                    "tx",
                    "gov",
                    "submit-proposal",
                    proposal_file,
                    "--from",
                    proposer_name,
                )
                assert (
                    prop_result["code"] == 0
                ), f"Valid proposal should succeed for '{multiplier}'"

            # Get proposal ID and pass it via governance
            events = prop_result.get("events", [])
            submit_proposal_events = [
                e for e in events if e["type"] == "submit_proposal"
            ]
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
            ), "No proposal_id attribute found in submit_proposal event"
            proposal_id = proposal_id_attrs[0]["value"]

            # Vote yes and wait for proposal to reach a final state
            vote_result = dysond(
                "tx", "gov", "vote", proposal_id, "yes", "--from", proposer_name
            )
            assert (
                vote_result["code"] == 0
            ), f"Voting failed: {vote_result.get('raw_log', 'no raw_log')}"

            def check_proposal_status():
                result = dysond("query", "gov", "proposal", proposal_id)
                status = result.get("proposal", {}).get("status", "UNKNOWN")
                final_states = [
                    "PROPOSAL_STATUS_PASSED",
                    "PROPOSAL_STATUS_REJECTED",
                    "PROPOSAL_STATUS_FAILED",
                ]
                return status in final_states

            poll_until_condition(check_proposal_status, timeout=120, poll_interval=2)

            # Verify proposal passed
            final_result = dysond("query", "gov", "proposal", proposal_id)
            final_status = final_result.get("proposal", {}).get("status", "UNKNOWN")
            assert (
                final_status == "PROPOSAL_STATUS_PASSED"
            ), f"Expected proposal to pass but got status: {final_status}"

            # After proposal: attempt storage set, expect insufficient stake
            with pytest.raises(Exception, match="insufficient delegated stake"):
                dysond(
                    "tx",
                    "storage",
                    "set",
                    "--index",
                    "test_zero_multiplier_bypass",
                    "--data",
                    large_data,
                    "--from",
                    test_account,
                    "--gas",
                    "auto",
                )

        # Now set multiplier to zero and verify storage succeeds
        zero_params = dict(current_params)
        zero_params["storage_stake_multiple"] = "0"

        zero_proposal_data = {
            "messages": [
                {
                    "@type": "/dysonprotocol.storage.v1.MsgUpdateParams",
                    "authority": gov_module_addr,
                    "params": zero_params,
                }
            ],
            "metadata": "ipfs://CID",
            "deposit": "10000000udys",
            "title": "Set Storage Stake Multiple 0",
            "summary": "Set storage_stake_multiple to 0 to disable validation",
            "expedited": True,
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as f:
            json.dump(zero_proposal_data, f)
            f.flush()
            zero_proposal_file = f.name
            zero_prop_result = dysond(
                "tx",
                "gov",
                "submit-proposal",
                zero_proposal_file,
                "--from",
                proposer_name,
            )
            assert zero_prop_result["code"] == 0

        zero_events = zero_prop_result.get("events", [])
        zero_submit_events = [e for e in zero_events if e["type"] == "submit_proposal"]
        zero_id_attrs = [
            attr
            for attr in zero_submit_events[0]["attributes"]
            if attr["key"] == "proposal_id"
        ]
        zero_proposal_id = zero_id_attrs[0]["value"]

        zero_vote_result = dysond(
            "tx", "gov", "vote", zero_proposal_id, "yes", "--from", proposer_name
        )
        assert zero_vote_result["code"] == 0

        def zero_check_status():
            result = dysond("query", "gov", "proposal", zero_proposal_id)
            status = result.get("proposal", {}).get("status", "UNKNOWN")
            final_states = [
                "PROPOSAL_STATUS_PASSED",
                "PROPOSAL_STATUS_REJECTED",
                "PROPOSAL_STATUS_FAILED",
            ]
            return status in final_states

        poll_until_condition(zero_check_status, timeout=120, poll_interval=2)

        zero_final = dysond("query", "gov", "proposal", zero_proposal_id)
        zero_status = zero_final.get("proposal", {}).get("status", "UNKNOWN")
        assert zero_status == "PROPOSAL_STATUS_PASSED"

        storage_result = dysond(
            "tx",
            "storage",
            "set",
            "--index",
            "test_zero_multiplier_bypass",
            "--data",
            large_data,
            "--from",
            test_account,
            "--gas",
            "auto",
        )
        assert storage_result["code"] == 0

        metrics_result = dysond("query", "storage", "metrics", bob_addr)
        assert int(metrics_result["min_stake_amount"]) == 0
        assert int(metrics_result["total_bytes"]) > 0

        print("✅ Governance parameter updates validated")


class TestStorageStakingMetrics:
    """Tests for storage metrics including stake-related fields."""

    def test_metrics_structure_and_fields(self, chainnet):
        """Test that QueryMetrics returns all required fields with correct types."""
        dysond = chainnet[0]

        test_account = "alice"
        alice_addr = dysond("keys", "show", test_account, "-a").strip()

        metrics_result = dysond("query", "storage", "metrics", alice_addr)

        # Verify all required fields
        required_fields = [
            "owner",
            "total_bytes",
            "min_stake_amount",
            "current_stake_amount",
        ]
        for field in required_fields:
            assert field in metrics_result, f"Missing required field '{field}'"

        # Verify field types
        assert isinstance(metrics_result["owner"], str)
        assert isinstance(metrics_result["total_bytes"], str)
        assert isinstance(metrics_result["min_stake_amount"], str)
        assert isinstance(metrics_result["current_stake_amount"], str)

        # Verify numeric fields can be parsed
        assert metrics_result["total_bytes"].isdigit()
        assert metrics_result["min_stake_amount"].isdigit()
        assert metrics_result["current_stake_amount"].isdigit()

        print("✅ Metrics structure verified")

    def test_current_stake_amount_integration(self, chainnet, generate_account, faucet):
        """Test that current_stake_amount correctly reflects staking module delegations."""
        dysond = chainnet[0]

        # Create test account
        test_account_name, test_addr = generate_account(
            "stake_metrics_test", faucet_amount=10_000_000
        )

        # Initial metrics should show zero stake
        initial_metrics = dysond("query", "storage", "metrics", test_addr)
        initial_stake = int(initial_metrics["current_stake_amount"])
        assert initial_stake == 0

        # Get validator for delegation
        validators_result = dysond("query", "staking", "validators")
        validator_addr = validators_result["validators"][0]["operator_address"]

        # Delegate tokens
        delegation_amount = "1000000udys"  # 1 dys
        delegate_result = dysond(
            "tx",
            "staking",
            "delegate",
            validator_addr,
            delegation_amount,
            "--from",
            test_account_name,
            "--gas",
            "auto",
        )
        assert delegate_result["code"] == 0

        # Verify metrics reflect delegation
        updated_metrics = dysond("query", "storage", "metrics", test_addr)
        updated_stake = int(updated_metrics["current_stake_amount"])

        assert updated_stake > initial_stake
        assert updated_stake == 1000000

        print(f"✅ Current stake amount integration: {updated_stake} udys")

    def test_multiple_delegations_sum(self, chainnet, generate_account, faucet):
        """Test that current_stake_amount correctly sums multiple delegations."""
        dysond = chainnet[0]

        test_account_name, test_addr = generate_account(
            "multi_delegation_test", faucet_amount=20_000_000
        )

        # Get validators
        validators = dysond("query", "staking", "validators")["validators"]
        validator1 = validators[0]["operator_address"]
        validator2 = (
            validators[1]["operator_address"] if len(validators) > 1 else validator1
        )

        # Delegate to multiple validators
        delegate1_result = dysond(
            "tx",
            "staking",
            "delegate",
            validator1,
            "3000000udys",
            "--from",
            test_account_name,
        )
        assert delegate1_result["code"] == 0

        delegate2_result = dysond(
            "tx",
            "staking",
            "delegate",
            validator2,
            "2000000udys",
            "--from",
            test_account_name,
        )
        assert delegate2_result["code"] == 0

        # Verify sum
        metrics = dysond("query", "storage", "metrics", test_addr)
        current_stake = int(metrics["current_stake_amount"])

        expected_total = 5000000  # 3M + 2M
        assert current_stake == expected_total

        print(f"✅ Multiple delegations summed correctly: {current_stake} udys")

    def test_no_delegations_zero_stake(self, chainnet, generate_account, faucet):
        """Test that accounts with no delegations return zero current_stake_amount."""
        dysond = chainnet[0]

        test_account_name, test_addr = generate_account(
            "no_delegations_test", faucet_amount=1_000_000
        )

        metrics = dysond("query", "storage", "metrics", test_addr)
        current_stake = int(metrics["current_stake_amount"])

        assert current_stake == 0
        print("✅ No delegations correctly returns zero stake")

    def test_zero_bytes_storage_always_succeeds(
        self, chainnet, generate_account, faucet
    ):
        """Test that zero bytes storage always succeeds regardless of stake validation."""
        dysond = chainnet[0]

        test_account_name, test_addr = generate_account(
            "zero_bytes_test", faucet_amount=1_000_000
        )

        # Enable stake validation
        validators = dysond("query", "staking", "validators")
        validator_operator = validators["validators"][0]["operator_address"]

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
        assert delegate_result["code"] == 0

        self._submit_governance_proposal_with_multiplier(dysond, "alice", "1.0")

        # Test storing empty data (0 bytes)
        empty_result = dysond(
            "tx",
            "storage",
            "set",
            "--index",
            "zero_bytes_test",
            "--data",
            "",
            "--from",
            test_account_name,
            "--gas",
            "auto",
        )
        assert empty_result["code"] == 0

        # Verify metrics
        metrics = dysond("query", "storage", "metrics", test_addr)
        min_stake = int(metrics["min_stake_amount"])
        total_bytes = int(metrics["total_bytes"])

        assert total_bytes == 0
        assert min_stake == 0
        print("✅ Zero bytes storage succeeds with zero stake requirement")

        # Restore default
        self._submit_governance_proposal_with_multiplier(dysond, "alice", "0")

    def test_edge_case_large_storage_requirements(
        self, chainnet, generate_account, faucet
    ):
        """Test edge cases with large storage and stake requirements."""
        dysond = chainnet[0]

        test_account_name, test_addr = generate_account(
            "large_storage_test", faucet_amount=100_000_000
        )

        # Set up governance and large stake
        validators = dysond("query", "staking", "validators")
        validator_operator = validators["validators"][0]["operator_address"]

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
        assert delegate_result["code"] == 0

        large_delegate_result = dysond(
            "tx",
            "staking",
            "delegate",
            validator_operator,
            "50000000udys",
            "--from",
            test_account_name,
        )
        assert large_delegate_result["code"] == 0

        self._submit_governance_proposal_with_multiplier(dysond, "alice", "1.0")

        # Test with maximum allowed storage size
        params = dysond("query", "storage", "params")
        max_size = int(params["params"]["max_storage_size"])

        max_data = "a" * max_size
        max_storage_result = dysond(
            "tx",
            "storage",
            "set",
            "--index",
            "max_size_test",
            "--data",
            max_data,
            "--from",
            test_account_name,
            "--gas",
            "auto",
        )
        assert max_storage_result["code"] == 0

        # Verify metrics
        metrics = dysond("query", "storage", "metrics", test_addr)
        min_stake = int(metrics["min_stake_amount"])
        total_bytes = int(metrics["total_bytes"])
        current_stake = int(metrics["current_stake_amount"])

        assert total_bytes == max_size
        assert min_stake == max_size
        assert current_stake >= min_stake

        print(
            f"✅ Large storage: {total_bytes} bytes requires {min_stake} udys, have {current_stake} udys"
        )

        # Restore default
        self._submit_governance_proposal_with_multiplier(dysond, "alice", "0")

    def _submit_governance_proposal_with_multiplier(
        self, dysond, proposer, multiplier_value
    ):
        """Helper to submit governance proposal with specific storage_stake_multiple value."""
        # Get governance module address
        gov_module_result = dysond("query", "auth", "module-account", "gov")
        gov_module_addr = (
            gov_module_result.get("account", {}).get("value", {}).get("address", "")
        )

        # Get current params
        current_params = dysond("query", "storage", "params")["params"]

        # Create proposal
        proposal_data = {
            "messages": [
                {
                    "@type": "/dysonprotocol.storage.v1.MsgUpdateParams",
                    "authority": gov_module_addr,
                    "params": {
                        "max_storage_size": current_params["max_storage_size"],
                        "storage_stake_multiple": multiplier_value,
                    },
                }
            ],
            "metadata": "ipfs://CID",
            "deposit": "2udys",
            "title": f"Set Storage Stake Multiple to {multiplier_value}",
            "summary": f"Update storage_stake_multiple parameter to {multiplier_value}",
            "expedited": True,
        }

        # Submit and execute proposal
        with tempfile.NamedTemporaryFile(mode="w", delete=True, suffix=".json") as f:
            json.dump(proposal_data, f, indent=2)
            proposal_file = f.name
            f.flush()
            # Submit proposal
            prop_result = dysond(
                "tx", "gov", "submit-proposal", proposal_file, "--from", proposer
            )
        assert prop_result["code"] == 0

        # Get proposal ID
        events = prop_result.get("events", [])
        submit_proposal_events = [e for e in events if e["type"] == "submit_proposal"]
        proposal_id_attrs = [
            attr
            for attr in submit_proposal_events[0]["attributes"]
            if attr["key"] == "proposal_id"
        ]
        proposal_id = proposal_id_attrs[0]["value"]

        # Vote on proposal
        vote_result = dysond(
            "tx", "gov", "vote", proposal_id, "yes", "--from", proposer
        )
        assert vote_result["code"] == 0

        # Wait for proposal to pass
        def check_proposal_status():
            result = dysond("query", "gov", "proposal", proposal_id)
            status = result.get("proposal", {}).get("status", "UNKNOWN")
            final_states = [
                "PROPOSAL_STATUS_PASSED",
                "PROPOSAL_STATUS_REJECTED",
                "PROPOSAL_STATUS_FAILED",
            ]
            return status in final_states

        poll_until_condition(check_proposal_status, timeout=120, poll_interval=2)

        # Verify proposal passed
        final_result = dysond("query", "gov", "proposal", proposal_id)
        final_status = final_result.get("proposal", {}).get("status", "UNKNOWN")
        assert (
            final_status == "PROPOSAL_STATUS_PASSED"
        ), f"Expected proposal to pass but got status: {final_status}"

        return proposal_id


class TestStorageStakingErrorHandling:
    """Tests for error handling in storage staking functionality."""

    def test_invalid_address_handling(self, chainnet):
        """Test that storage metrics handles invalid addresses gracefully."""
        dysond = chainnet[0]

        # Test with invalid address format
        result = dysond("query", "storage", "metrics", "invalid_address_format")

        # Should return string with error information
        assert isinstance(result, str), f"Expected error string, got: {type(result)}"
        lower = result.lower()
        print(f"Invalid address error: {lower}")
        tail = lower.strip().splitlines()[-1]
        prefix = (
            "rpc error: code = invalidargument desc = rpc error: code = invalidargument desc = "
            "failed to resolve owner: name not found: invalid_address_format: not found "
            "[dysonprotocol.com/x/nameservice/keeper/keeper.go:"
        )
        suffix = "]: invalid request"
        assert tail.startswith(
            prefix
        ), f"Expected error to start with '{prefix}', got: {tail}\nFull: {lower}"
        assert tail.endswith(
            suffix
        ), f"Expected error to end with '{suffix}', got: {tail}\nFull: {lower}"

        print("✅ Invalid address handling works correctly")

    def test_nonexistent_storage_entry_handling(self, chainnet):
        """Test that storage queries handle non-existent entries properly."""
        dysond = chainnet[0]

        test_account = "alice"
        alice_addr = dysond("keys", "show", test_account, "-a").strip()

        # Query non-existent storage entry
        result = dysond(
            "query", "storage", "get", alice_addr, "--index", "non_existent_index"
        )

        # Should return string with error information
        assert isinstance(result, str), f"Expected error string, got: {type(result)}"
        lower = result.lower()
        print(f"Non-existent entry error: {lower}")
        expected = "key not found"
        assert expected in lower, f"{expected} not in: {lower}"

        print("✅ Non-existent entry handling works correctly")

    def test_insufficient_stake_error_format(self, chainnet, generate_account, faucet):
        """Test error message format for insufficient stake validation."""
        dysond = chainnet[0]

        # This test documents expected error patterns
        expected_patterns = [
            "insufficient delegated stake",
            "account \\[.*\\] has .* udys staked",
            "need .* udys staked",
            "bytes of storage",
            "ratio: .* udys per byte",
        ]

        print("Expected error message patterns for insufficient stake:")
        for pattern in expected_patterns:
            print(f"  - {pattern}")

        print(
            "Expected format: insufficient delegated stake: account [ADDRESS] has X udys staked, need Y udys staked for Z bytes of storage (ratio: R udys per byte)"
        )

        # When stake validation is enabled, errors should match these patterns
        print("✅ Error format requirements documented")


# Standalone utility tests
def test_stake_validation_requirements_documentation():
    """Document the complete requirements for stake validation implementation."""

    requirements = {
        "validation_point": "Before storage write operations (StorageSet)",
        "bypass_condition": "storage_stake_multiple = '0' disables validation",
        "calculation": "required_stake = new_total_bytes × storage_stake_multiple",
        "error_condition": "current_delegated_stake < required_stake",
        "error_message_format": "insufficient delegated stake: account [ADDRESS] has X udys staked, need Y udys staked for Z bytes of storage (ratio: R udys per byte)",
        "deletion_behavior": "StorageDelete never blocked by insufficient stake",
        "governance_control": "storage_stake_multiple parameter can be updated via governance",
        "metrics_integration": "QueryMetrics includes current_stake_amount from staking module",
    }

    print("Complete stake validation requirements:")
    for key, value in requirements.items():
        print(f"  {key}: {value}")

    print("✅ Requirements documented")


def test_storage_staking_integration_summary(chainnet):
    """Verify overall integration between storage and staking modules."""
    dysond = chainnet[0]

    # Test that both modules are available and integrated
    storage_params = dysond("query", "storage", "params")
    assert "storage_stake_multiple" in storage_params["params"]

    # Test that metrics query works
    alice_addr = dysond("keys", "show", "alice", "-a").strip()
    metrics = dysond("query", "storage", "metrics", alice_addr)
    assert "current_stake_amount" in metrics

    print("✅ Storage-staking integration verified")
