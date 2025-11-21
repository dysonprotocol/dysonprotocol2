"""
UpdateParams message handler coverage tests.

Tests the UpdateParams message handler which updates module parameters via governance.
Covers authority validation, parameter validation, and state updates.
"""

import json
import pytest
import tempfile
from tests.utils import poll_until_condition


def test_update_params_success(chainnet, generate_account, faucet):
    """Test UpdateParams succeeds with valid authority and parameters."""
    dysond = chainnet[0]
    [proposer_name, proposer_addr] = generate_account("update_params", faucet_amount=50_000_000)
    faucet(proposer_addr)

    # Get governance module address
    gov_module_result = dysond("query", "auth", "module-account", "gov")
    gov_module_addr = gov_module_result.get("account", {}).get("value", {}).get("address", "")

    # Get current params
    current_params = dysond("query", "storage", "params")["params"]
    original_max_size = int(current_params["max_storage_size"])

    # Ensure proposer has voting power
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
    assert delegate_result.get("code", 0) == 0, f"Delegation failed: {json.dumps(delegate_result, indent=2)}"

    # Create proposal to update params
    new_max_size = original_max_size + 1000
    proposal_data = {
        "messages": [
            {
                "@type": "/dysonprotocol.storage.v1.MsgUpdateParams",
                "authority": gov_module_addr,
                "params": {
                    "max_storage_size": str(new_max_size),
                    "storage_stake_multiple": current_params["storage_stake_multiple"],
                },
            }
        ],
        "metadata": "ipfs://CID",
        "deposit": "1udys",
        "title": "Update Storage Params",
        "summary": f"Update max_storage_size from {original_max_size} to {new_max_size}",
    }

    # Submit and execute proposal
    proposal_id = _submit_and_execute_proposal(dysond, proposer_name, proposal_data)

    # Verify params were updated
    updated_params = dysond("query", "storage", "params")["params"]
    updated_max_size = int(updated_params["max_storage_size"])
    assert updated_max_size == new_max_size, f"Expected max_storage_size {new_max_size}, got {updated_max_size}"


def test_update_params_invalid_authority(chainnet, generate_account, faucet):
    """Test UpdateParams fails with invalid authority."""
    dysond = chainnet[0]
    [proposer_name, proposer_addr] = generate_account("update_params_auth", faucet_amount=50_000_000)
    faucet(proposer_addr)

    # Get current params
    current_params = dysond("query", "storage", "params")["params"]
    gov_module_result = dysond("query", "auth", "module-account", "gov")
    gov_module_addr = gov_module_result.get("account", {}).get("value", {}).get("address", "")

    # Create proposal with wrong authority (use proposer address instead of gov module)
    proposal_data = {
        "messages": [
            {
                "@type": "/dysonprotocol.storage.v1.MsgUpdateParams",
                "authority": proposer_addr,  # Wrong authority
                "params": {
                    "max_storage_size": str(int(current_params["max_storage_size"]) + 1000),
                    "storage_stake_multiple": current_params["storage_stake_multiple"],
                },
            }
        ],
        "metadata": "ipfs://CID",
        "deposit": "1udys",
        "title": "Invalid Authority Update",
        "summary": "Try to update params with wrong authority",
    }

    # Submit proposal
    with tempfile.NamedTemporaryFile(mode="w", delete=True, suffix=".json") as f:
        json.dump(proposal_data, f, indent=2)
        proposal_file = f.name
        f.flush()
        prop_result = dysond("tx", "gov", "submit-proposal", proposal_file, "--from", proposer_name)

    assert prop_result.get("code", 0) == 0, f"Proposal submission should succeed: {json.dumps(prop_result, indent=2)}"

    # Get proposal ID
    events = prop_result.get("events", [])
    submit_proposal_events = [e for e in events if e.get("type") == "submit_proposal"]
    assert len(submit_proposal_events) > 0, f"No submit_proposal event found"
    proposal_id_attrs = [attr for attr in submit_proposal_events[0].get("attributes", []) if attr.get("key") == "proposal_id"]
    assert len(proposal_id_attrs) > 0, f"No proposal_id attribute found"
    proposal_id = proposal_id_attrs[0].get("value")

    # Vote on proposal
    vote_result = dysond("tx", "gov", "vote", proposal_id, "yes", "--from", proposer_name)
    assert vote_result.get("code", 0) == 0, f"Voting should succeed: {json.dumps(vote_result, indent=2)}"

    # Wait for proposal to execute
    def check_proposal_status():
        result = dysond("query", "gov", "proposal", proposal_id)
        status = result.get("proposal", {}).get("status", "UNKNOWN")
        final_states = ["PROPOSAL_STATUS_PASSED", "PROPOSAL_STATUS_REJECTED", "PROPOSAL_STATUS_FAILED"]
        return status in final_states

    poll_until_condition(check_proposal_status, timeout=60, poll_interval=2)

    # Verify proposal failed (due to invalid authority)
    final_result = dysond("query", "gov", "proposal", proposal_id)
    final_status = final_result.get("proposal", {}).get("status", "UNKNOWN")
    # Proposal may pass but execution should fail, or proposal may be rejected
    assert final_status in ["PROPOSAL_STATUS_REJECTED", "PROPOSAL_STATUS_FAILED"], f"Proposal should fail due to invalid authority, got status: {final_status}"


def test_update_params_invalid_max_size(chainnet, generate_account, faucet):
    """Test UpdateParams fails with invalid MaxStorageSize value."""
    dysond = chainnet[0]
    [proposer_name, proposer_addr] = generate_account("update_params_invalid", faucet_amount=50_000_000)
    faucet(proposer_addr)

    # Get current params
    current_params = dysond("query", "storage", "params")["params"]
    gov_module_result = dysond("query", "auth", "module-account", "gov")
    gov_module_addr = gov_module_result.get("account", {}).get("value", {}).get("address", "")

    # Ensure proposer has voting power
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
    assert delegate_result.get("code", 0) == 0, f"Delegation failed: {json.dumps(delegate_result, indent=2)}"

    # Create proposal with invalid max_storage_size (below minimum 1024)
    proposal_data = {
        "messages": [
            {
                "@type": "/dysonprotocol.storage.v1.MsgUpdateParams",
                "authority": gov_module_addr,
                "params": {
                    "max_storage_size": "512",  # Below 1KB minimum
                    "storage_stake_multiple": current_params["storage_stake_multiple"],
                },
            }
        ],
        "metadata": "ipfs://CID",
        "deposit": "1udys",
        "title": "Invalid Max Size",
        "summary": "Try to set max_storage_size below minimum",
    }

    # Submit proposal
    with tempfile.NamedTemporaryFile(mode="w", delete=True, suffix=".json") as f:
        json.dump(proposal_data, f, indent=2)
        proposal_file = f.name
        f.flush()
        prop_result = dysond("tx", "gov", "submit-proposal", proposal_file, "--from", proposer_name)

    assert prop_result.get("code", 0) == 0, f"Proposal submission should succeed: {json.dumps(prop_result, indent=2)}"

    # Get proposal ID and vote
    events = prop_result.get("events", [])
    submit_proposal_events = [e for e in events if e.get("type") == "submit_proposal"]
    assert len(submit_proposal_events) > 0, f"No submit_proposal event found"
    proposal_id_attrs = [attr for attr in submit_proposal_events[0].get("attributes", []) if attr.get("key") == "proposal_id"]
    assert len(proposal_id_attrs) > 0, f"No proposal_id attribute found"
    proposal_id = proposal_id_attrs[0].get("value")

    vote_result = dysond("tx", "gov", "vote", proposal_id, "yes", "--from", proposer_name)
    assert vote_result.get("code", 0) == 0, f"Voting should succeed: {json.dumps(vote_result, indent=2)}"

    # Wait for proposal to execute
    def check_proposal_status():
        result = dysond("query", "gov", "proposal", proposal_id)
        status = result.get("proposal", {}).get("status", "UNKNOWN")
        final_states = ["PROPOSAL_STATUS_PASSED", "PROPOSAL_STATUS_REJECTED", "PROPOSAL_STATUS_FAILED"]
        return status in final_states

    poll_until_condition(check_proposal_status, timeout=60, poll_interval=2)

    # Verify proposal failed (due to invalid parameter)
    final_result = dysond("query", "gov", "proposal", proposal_id)
    final_status = final_result.get("proposal", {}).get("status", "UNKNOWN")
    # Proposal execution should fail due to parameter validation
    assert final_status in ["PROPOSAL_STATUS_REJECTED", "PROPOSAL_STATUS_FAILED"], f"Proposal should fail due to invalid parameter, got status: {final_status}"


def _submit_and_execute_proposal(dysond, proposer_name, proposal_data):
    """Helper function to submit and execute a governance proposal."""
    # Write proposal to temporary file
    with tempfile.NamedTemporaryFile(mode="w", delete=True, suffix=".json") as f:
        json.dump(proposal_data, f, indent=2)
        proposal_file = f.name
        f.flush()
        prop_result = dysond("tx", "gov", "submit-proposal", proposal_file, "--from", proposer_name)

    assert prop_result.get("code", 0) == 0, f"Proposal submission failed: {json.dumps(prop_result, indent=2)}"

    # Get proposal ID from events
    events = prop_result.get("events", [])
    submit_proposal_events = [e for e in events if e.get("type") == "submit_proposal"]
    assert len(submit_proposal_events) > 0, f"No submit_proposal event found in: {events}"

    proposal_id_attrs = [attr for attr in submit_proposal_events[0].get("attributes", []) if attr.get("key") == "proposal_id"]
    assert len(proposal_id_attrs) > 0, f"No proposal_id attribute found"
    proposal_id = proposal_id_attrs[0].get("value")

    # Vote on proposal
    vote_result = dysond("tx", "gov", "vote", proposal_id, "yes", "--from", proposer_name)
    assert vote_result.get("code", 0) == 0, f"Voting failed: {json.dumps(vote_result, indent=2)}"

    # Wait for proposal to pass
    def check_proposal_status():
        result = dysond("query", "gov", "proposal", proposal_id)
        status = result.get("proposal", {}).get("status", "UNKNOWN")
        final_states = ["PROPOSAL_STATUS_PASSED", "PROPOSAL_STATUS_REJECTED", "PROPOSAL_STATUS_FAILED"]
        return status in final_states

    poll_until_condition(check_proposal_status, timeout=60, poll_interval=2)

    # Verify proposal passed
    final_result = dysond("query", "gov", "proposal", proposal_id)
    final_status = final_result.get("proposal", {}).get("status", "UNKNOWN")
    assert final_status == "PROPOSAL_STATUS_PASSED", f"Expected proposal to pass but got status: {final_status}"

    return proposal_id

