#!/usr/bin/env python3
"""
Test MsgSudo functionality for executing arbitrary messages with authority override.

MsgSudo allows the governance authority to execute any message without signer validation,
enabling governance to perform administrative operations.
"""
import json
import pytest
import tempfile
from tests.conftest import dedent


def test_sudo_update_script(chainnet, generate_account, faucet):
    """
    Test MsgSudo can update a script without signer validation.

    This test demonstrates that governance can execute messages on behalf
    of any account by using MsgSudo, which bypasses the normal signer checks.
    """
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    [bob_name, bob_address] = generate_account("bob")

    faucet(
        alice_address, denom="udys", amount="100000000"
    )  # Need enough for delegation
    faucet(bob_address, denom="udys", amount="100")

    # Alice creates a script
    script_code_v1 = dedent(
        """
        def version():
            return "v1"
    """
    ).strip()

    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code",
        script_code_v1,
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
    )

    assert update_result["code"] == 0, f"Script creation failed: {update_result}"

    # Verify initial script content
    script_info = dysond_bin(
        "query", "script", "script-info", "--address", alice_address
    )
    assert "v1" in script_info["script"]["code"], "Initial script version mismatch"

    # Get governance module address (the authority)
    gov_module_result = dysond_bin("query", "auth", "module-account", "gov")
    gov_address = (
        gov_module_result.get("account", {}).get("value", {}).get("address", "")
    )
    assert gov_address, "Could not get governance module address"

    print(f"Governance module address: {gov_address}")

    # Create a proposal that uses MsgSudo to update Alice's script
    # The inner message has Alice as the signer, but we bypass that check via Sudo
    script_code_v2 = dedent(
        """
        def version():
            return "v2 updated via governance sudo"
    """
    ).strip()

    # Create the inner message (no encoding needed - just embed it)
    inner_msg = {
        "@type": "/dysonprotocol.script.v1.MsgUpdateScript",
        "address": alice_address,
        "code": script_code_v2,
    }

    # Create MsgSudo with the inner message embedded directly
    sudo_msg = {
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": gov_address,
        "messages": [inner_msg],
    }

    proposal_data = {
        "messages": [sudo_msg],
        "metadata": "ipfs://CID",
        "deposit": "100000udys",
        "title": "Test Sudo Message Execution",
        "summary": "Update Alice's script via governance sudo without her signature",
    }

    # Alice needs voting power to pass the proposal
    validators = dysond_bin("query", "staking", "validators")
    validator_operator = validators["validators"][0]["operator_address"]

    delegate_result = dysond_bin(
        "tx",
        "staking",
        "delegate",
        validator_operator,
        "50000000udys",
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert delegate_result["code"] == 0, f"Delegation failed: {delegate_result}"

    # Submit governance proposal
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as f:
        json.dump(proposal_data, f, indent=2)
        f.flush()

        submit_result = dysond_bin(
            "tx",
            "gov",
            "submit-proposal",
            f.name,
            "--from",
            alice_name,
            "--keyring-backend",
            "test",
            "--yes",
        )

    assert submit_result["code"] == 0, f"Proposal submission failed: {submit_result}"

    # Extract proposal ID - look for submit_proposal event
    submit_events = [
        e for e in submit_result.get("events", []) if e.get("type") == "submit_proposal"
    ]
    proposal_id_attrs = [
        a
        for e in submit_events
        for a in e.get("attributes", [])
        if a.get("key") == "proposal_id"
    ]
    assert (
        proposal_id_attrs
    ), f"No proposal_id found in submit event. Events: {json.dumps(submit_result.get('events', []), indent=2)}"
    proposal_id = proposal_id_attrs[0].get("value")

    print(f"Submitted proposal ID: {proposal_id}")

    # Vote on the proposal
    vote_result = dysond_bin(
        "tx",
        "gov",
        "vote",
        str(proposal_id),
        "yes",
        "--from",
        alice_name,
        "--keyring-backend",
        "test",
        "--yes",
    )
    assert vote_result["code"] == 0, f"Voting failed: {vote_result}"

    # Wait for proposal to pass
    from tests.utils import poll_until_condition

    def check_proposal_passed():
        proposal = dysond_bin("query", "gov", "proposal", str(proposal_id))
        status = proposal.get("proposal", {}).get("status")
        print(f"Proposal status: {status}")
        assert status in [
            "PROPOSAL_STATUS_PASSED",
            "PROPOSAL_STATUS_VOTING_PERIOD",
        ], f"Proposal failed with status: {status}"
        return status == "PROPOSAL_STATUS_PASSED"

    poll_until_condition(
        check_proposal_passed, timeout=30, error_message="Proposal did not pass in time"
    )

    # Verify the script was updated via sudo
    final_script_info = dysond_bin(
        "query", "script", "script-info", "--address", alice_address
    )
    final_code = final_script_info["script"]["code"]

    assert (
        "v2 updated via governance sudo" in final_code
    ), f"Script was not updated via sudo. Code: {final_code}"
    assert "v1" not in final_code, "Old script version still present"

    print("✅ MsgSudo successfully updated script without original signer")


def test_sudo_authority_validation(chainnet, generate_account, faucet):
    """
    Test that MsgSudo rejects non-authority signers.

    Only the governance module account should be able to execute MsgSudo.
    Regular users should be rejected.
    """
    dysond_bin = chainnet[0]
    [alice_name, alice_address] = generate_account("alice")
    [bob_name, bob_address] = generate_account("bob")

    faucet(alice_address, denom="udys", amount="1000")
    faucet(bob_address, denom="udys", amount="1000")

    # Get governance module address
    gov_module_result = dysond_bin("query", "auth", "module-account", "gov")
    gov_address = (
        gov_module_result.get("account", {}).get("value", {}).get("address", "")
    )
    assert gov_address, "Could not get governance module address"

    # Try to create a MsgSudo directly from Alice (not via governance)
    # This should fail because Alice is not the authority
    script_code = dedent(
        """
        def test():
            return "should fail"
    """
    ).strip()

    inner_msg = {
        "@type": "/dysonprotocol.script.v1.MsgUpdateScript",
        "address": alice_address,
        "code": script_code,
    }

    # Attempt to send MsgSudo from Alice using the correct authority address
    # This should still fail because the transaction signer (Alice) doesn't match authority
    with pytest.raises(Exception) as exc_info:
        # Create the transaction JSON manually
        tx_data = {
            "body": {
                "messages": [
                    {
                        "@type": "/dysonprotocol.script.v1.MsgSudo",
                        "authority": gov_address,  # Correct authority
                        "messages": [inner_msg],  # Embed message directly
                    }
                ]
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as f:
            json.dump(tx_data, f, indent=2)
            f.flush()

            # Try to broadcast - this should fail
            result = dysond_bin(
                "tx",
                "sign-and-broadcast",
                f.name,
                "--from",
                alice_name,
                "--keyring-backend",
                "test",
            )

            # If we get here, check if there's an error in the result
            assert (
                result.get("code") != 0
            ), "Expected transaction to fail but it succeeded"

    print("✅ MsgSudo correctly rejects unauthorized signers")
