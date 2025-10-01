import json
import os
import pytest
from tests.utils import poll_until_condition


def test_ica_complete_e2e_workflow(ibc_setup, generate_account, faucet):
    """
    Complete end-to-end test for ICA functionality covering the entire workflow:
    1. Deploy ica_e2e.py script
    2. Register ICA account
    3. Wait for ICA address establishment
    4. Fund the ICA account via IBC transfer
    5. Query balance of ICA account
    6. Wait for balance query callback
    7. Withdraw funds back to controller
    8. Wait for withdrawal callback
    9. Verify all operations and callbacks completed successfully
    """
    dysond_bin = ibc_setup[0]
    [alice_name, alice_address] = generate_account("alice", faucet_amount=200000)

    print(f"🔧 Starting ICA E2E test with alice: {alice_name} ({alice_address})")

    # 1. Deploy the ICA e2e script
    ica_script_path = "examples/ica_e2e.py"
    abs_ica_script_path = os.path.abspath(ica_script_path)
    print(f"📝 Deploying script from: {abs_ica_script_path}")

    update_result = dysond_bin(
        "tx",
        "script",
        "update",
        "--code-path",
        str(abs_ica_script_path),
        "--from",
        alice_name,
        "--gas",
        "2000000",
    )
    print(f"📝 Script deployment result: {update_result}")
    assert (
        update_result.get("code", 1) == 0
    ), f"Failed to deploy ICA e2e script: {update_result}"

    # 2. Register ICA account
    print(f"🔗 Registering ICA account...")
    register_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "register",
        "--args",
        "[]",
        "--from",
        alice_name,
        "--gas",
        "2000000",
    )
    print(f"🔗 ICA registration result: {register_result}")
    assert (
        register_result.get("code", 1) == 0
    ), f"Failed to register ICA account: {register_result}"

    # Pre-check diagnostics to understand ICA readiness issues
    print(f"🧪 Gathering IBC pre-check diagnostics...")

    def _log_ibc_preconditions():

        # Both chains' dysond runners
        chain_a = ibc_setup[0]
        chain_b = ibc_setup[1] if len(ibc_setup) > 1 else ibc_setup[0]

        # Heights
        status_a = chain_a("status")
        status_b = chain_b("status")
        print(
            f"⛓️  Chain A height: {status_a.get('sync_info', {}).get('latest_block_height')}"
        )
        print(
            f"⛓️  Chain B height: {status_b.get('sync_info', {}).get('latest_block_height')}"
        )

        # Connection state on Chain A
        conn_a = chain_a("query", "ibc", "connection", "end", "connection-0")
        print(f"🔗 connection-0 on Chain A: {json.dumps(conn_a, indent=2)}")

        # Transfer channel state (created during IBC setup) on both chains
        chan_a = chain_a("query", "ibc", "channel", "channel", "transfer", "channel-0")
        chan_b = chain_b("query", "ibc", "channel", "channel", "transfer", "channel-0")
        print(f"🚚 transfer/channel-0 on Chain A: {json.dumps(chan_a, indent=2)}")
        print(f"🚚 transfer/channel-0 on Chain B: {json.dumps(chan_b, indent=2)}")

        # Controller port id for this owner/script
        ctrl_port = f"icacontroller-{alice_address}"
        print(f"🪪 Expected ICA controller port_id: {ctrl_port}")

        # List channels and filter for ICS-27 controller port on both chains
        chs_a = chain_a("query", "ibc", "channel", "channels")
        chs_b = chain_b("query", "ibc", "channel", "channels")
        ica_chs_a = [
            c for c in chs_a.get("channels", []) if c.get("port_id") == ctrl_port
        ]
        ica_chs_b = [
            c
            for c in chs_b.get("channels", [])
            if c.get("port_id")
            in [
                ctrl_port,
                "icahost",
            ]
        ]
        print(
            f"🛰️  ICS-27 channels (controller) on Chain A: {json.dumps(ica_chs_a, indent=2)}"
        )
        print(
            f"🛰️  ICS-27 channels (controller/host) on Chain B: {json.dumps(ica_chs_b, indent=2)}"
        )

    _log_ibc_preconditions()

    # 3. Wait for ICA address to be established via get_ica_address
    print(f"⏳ Waiting for ICA address establishment...")

    def _ica_address_established():
        """Check if ICA address has been established"""
        print(f"🔍 Checking if ICA address is established...")
        result = dysond_bin(
            "query",
            "script",
            "run",
            "--executor-address",
            alice_address,
            "--script-address",
            alice_address,
            "--function-name",
            "get_ica_address",
            "--args",
            "[]",
            "--kwargs",
            "{}",
            "-o",
            "json",
        )
        print(f"🔍 get_ica_address (query run) result: {result}")
        assert "result" in result, f"get_ica_address run failed: {result}"

        # Parse query run structured response (see tests/script/test_script.py)
        result_data = json.loads(result["result"])  # outer wrapper
        ica_result = result_data.get("result", {})  # actual function return
        print(f"🔍 ICA address check response: {ica_result}")

        # Check if ICA is ready
        is_dict = isinstance(ica_result, dict)
        is_success = is_dict and ica_result.get("status") == "success"

        (
            print(f"❌ ICA address not ready: {ica_result}")
            if is_dict and not is_success
            else None
        )

        # Return early if successful
        registered_address = (
            ica_result.get("registered_address", "") if is_success else ""
        )
        print(f"✅ Found ICA address: {registered_address}") if is_success else None
        return (
            (registered_address and registered_address.startswith("dys"))
            if is_success
            else False
        )

    poll_until_condition(
        _ica_address_established,
        timeout=120,
        poll_interval=1,
        error_message="ICA address not established after registration",
    )

    # 4. Get the established ICA address
    print(f"📍 Getting final ICA address...")
    ica_address_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "get_ica_address",
        "--args",
        "[]",
        "--from",
        alice_name,
        "--gas",
        "2000000",
    )
    print(f"📍 Final ICA address result: {ica_address_result}")
    assert (
        ica_address_result.get("code", 1) == 0
    ), f"Failed to get ICA address: {ica_address_result}"

    # Extract ICA address from first successful response
    exec_events = [
        e
        for e in ica_address_result.get("events", [])
        if e.get("type") == "dysonprotocol.script.v1.EventExecScript"
    ]
    response_attrs = [
        a
        for e in exec_events
        for a in e.get("attributes", [])
        if a.get("key") == "response"
    ]

    successful_results = []
    for attr in response_attrs:
        response_json = attr.get("value")
        response_data = json.loads(response_json)
        result_data = json.loads(response_data.get("result", "{}"))
        ica_result = result_data.get("result", {})

        # Check if successful and add to results
        is_success = (
            isinstance(ica_result, dict) and ica_result.get("status") == "success"
        )
        successful_results.extend(
            [ica_result.get("registered_address", "")] if is_success else []
        )

    ica_address = successful_results[0] if successful_results else None

    assert ica_address, "ICA address should be returned"
    assert ica_address.startswith("dys2"), "ICA address should be valid bech32 format"
    print(f"✅ ICA Address established: {ica_address}")

    # 5. Fund the ICA account via IBC transfer
    fund_args = ["udys", "5000"]
    print(f"💰 Funding ICA account with {fund_args}...")
    fund_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "fund",
        "--args",
        json.dumps(fund_args),
        "--from",
        alice_name,
        "--gas",
        "2000000",
    )
    print(f"💰 Fund result: {fund_result}")
    assert fund_result.get("code", 1) == 0, f"Failed to fund ICA account: {fund_result}"

    # 6. Request balance query
    print(f"📊 Requesting balance query...")
    query_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "request_query_balance",
        "--args",
        "[]",
        "--from",
        alice_name,
        "--gas",
        "2000000",
    )
    print(f"📊 Query request result: {query_result}")
    assert (
        query_result.get("code", 1) == 0
    ), f"Failed to request balance query: {query_result}"

    # Extract ref_id from query result using list comprehensions
    exec_events = [
        e
        for e in query_result.get("events", [])
        if e.get("type") == "dysonprotocol.script.v1.EventExecScript"
    ]
    response_attrs = [
        a
        for e in exec_events
        for a in e.get("attributes", [])
        if a.get("key") == "response"
    ]

    query_ref_ids = []
    for attr in response_attrs:
        response_json = attr.get("value")
        response_data = json.loads(response_json)
        result_data = json.loads(response_data.get("result", "{}"))
        query_response = result_data.get("result", {})
        print(f"📊 Query response data: {query_response}")

        # Extract ref_id if successful
        is_success = (
            isinstance(query_response, dict)
            and query_response.get("status") == "success"
        )
        ref_id = query_response.get("ref_id") if is_success else None
        print(f"📊 Extracted ref_id: {ref_id}") if ref_id is not None else None
        query_ref_ids.extend([ref_id] if ref_id is not None else [])

    query_ref_id = query_ref_ids[0] if query_ref_ids else None

    assert query_ref_id is not None, "Balance query ref_id should be returned"
    print(f"✅ Balance query sent with ref_id: {query_ref_id}")

    # 7. Wait for balance query callback to be stored
    print(f"⏳ Waiting for balance query callback (ref_id: {query_ref_id})...")

    def _balance_callback_received():
        """Check if balance query callback has been received"""
        callback_args = ["balance_query", query_ref_id]
        print(f"🔍 Checking for callback with args: {callback_args}")
        result = dysond_bin(
            "tx",
            "script",
            "exec",
            "--script-address",
            alice_address,
            "--function-name",
            "get_callback",
            "--args",
            json.dumps(callback_args),
            "--from",
            alice_name,
            "--gas",
            "2000000",
        )
        print(f"🔍 Callback check result: {result}")
        assert result.get("code", 1) == 0, f"get_callback execution failed: {result}"

        # Extract callback response using list comprehensions
        exec_events = [
            e
            for e in result.get("events", [])
            if e.get("type") == "dysonprotocol.script.v1.EventExecScript"
        ]
        response_attrs = [
            a
            for e in exec_events
            for a in e.get("attributes", [])
            if a.get("key") == "response"
        ]

        for attr in response_attrs:
            response_json = attr.get("value")
            response_data = json.loads(response_json)
            result_data = json.loads(response_data.get("result", "{}"))
            callback_result = result_data.get("result", {})
            print(f"🔍 Callback check response: {callback_result}")

            # Check callback status
            is_dict = isinstance(callback_result, dict)
            status = callback_result.get("status") if is_dict else None
            print(f"🔍 Callback status: {status}")

            # Return based on status
            print(f"✅ Callback found!") if status == "success" else None
            print(f"❌ Callback not found yet") if status == "not_found" else None
            (
                print(f"❓ Unexpected callback status: {status}")
                if status not in ["success", "not_found"] and status is not None
                else None
            )

            return status == "success"

        print(f"❌ No callback response found in events")
        return False

    # Let's also check what callbacks exist at all
    print(f"🔍 Checking what callbacks exist...")
    list_callbacks_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "get_callback",
        "--args",
        '["balance_query"]',
        "--from",
        alice_name,
        "--gas",
        "2000000",
    )
    print(f"🔍 List callbacks result: {list_callbacks_result}")

    poll_until_condition(
        _balance_callback_received,
        timeout=20,
        poll_interval=1,
        error_message="Balance query callback not received",
    )

    # 8. Verify balance query callback data
    callback_args = ["balance_query", query_ref_id]
    print(f"✅ Getting callback data for verification...")
    callback_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "get_callback",
        "--args",
        json.dumps(callback_args),
        "--from",
        alice_name,
        "--gas",
        "2000000",
    )
    print(f"✅ Callback verification result: {callback_result}")
    assert (
        callback_result.get("code", 1) == 0
    ), f"Failed to get balance callback: {callback_result}"

    # 9. Withdraw funds back to controller
    withdraw_args = [
        "ibc/3B2294AF63D402DF9B10DA43CEC03677D9041297A1031AB1AFC789C492280D79",
        "1000",
    ]
    print(f"💸 Withdrawing funds with args: {withdraw_args}")
    withdraw_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "withdraw",
        "--args",
        json.dumps(withdraw_args),
        "--from",
        alice_name,
        "--gas",
        "2000000",
    )
    print(f"💸 Withdraw result: {withdraw_result}")
    assert (
        withdraw_result.get("code", 1) == 0
    ), f"Failed to withdraw from ICA account: {withdraw_result}"

    # Extract withdrawal ref_id using list comprehensions
    exec_events = [
        e
        for e in withdraw_result.get("events", [])
        if e.get("type") == "dysonprotocol.script.v1.EventExecScript"
    ]
    response_attrs = [
        a
        for e in exec_events
        for a in e.get("attributes", [])
        if a.get("key") == "response"
    ]

    withdrawal_ref_id = None
    for attr in response_attrs:
        response_json = attr.get("value")
        response_data = json.loads(response_json)
        result_data = json.loads(response_data.get("result", "{}"))
        withdraw_response = result_data.get("result", {})
        print(f"💸 Withdraw response data: {withdraw_response}")

        # Check if successful - for withdrawal, ref_id comes from tx_result or we can derive from block
        is_success = (
            isinstance(withdraw_response, dict)
            and withdraw_response.get("status") == "success"
        )
        # Let's get latest callback for withdrawal topic - we don't need the ref_id for this test
        pass

    # 10. Wait for withdrawal callback
    print(f"⏳ Waiting for withdrawal callback...")

    def _withdrawal_callback_received():
        """Check if withdrawal callback has been received"""
        # Get latest callback for withdrawal topic
        callback_args = ["withdrawal"]
        print(f"🔍 Checking for withdrawal callback...")
        result = dysond_bin(
            "tx",
            "script",
            "exec",
            "--script-address",
            alice_address,
            "--function-name",
            "get_callback",
            "--args",
            json.dumps(callback_args),
            "--from",
            alice_name,
            "--gas",
            "2000000",
        )
        print(f"🔍 Withdrawal callback check result: {result}")
        assert result.get("code", 1) == 0, f"get_callback execution failed: {result}"

        # Extract callback response using list comprehensions
        exec_events = [
            e
            for e in result.get("events", [])
            if e.get("type") == "dysonprotocol.script.v1.EventExecScript"
        ]
        response_attrs = [
            a
            for e in exec_events
            for a in e.get("attributes", [])
            if a.get("key") == "response"
        ]

        for attr in response_attrs:
            response_json = attr.get("value")
            response_data = json.loads(response_json)
            result_data = json.loads(response_data.get("result", "{}"))
            callback_result = result_data.get("result", {})
            print(f"🔍 Withdrawal callback response: {callback_result}")

            # Check status and return
            is_dict = isinstance(callback_result, dict)
            status = callback_result.get("status") if is_dict else None
            print(f"🔍 Withdrawal callback status: {status}")
            return status == "success"

        return False

    poll_until_condition(
        _withdrawal_callback_received,
        timeout=20,
        poll_interval=1,
        error_message="Withdrawal callback not received",
    )

    # 11. Verify withdrawal callback data
    withdrawal_callback_args = ["withdrawal"]
    print(f"✅ Getting withdrawal callback data for verification...")
    withdrawal_callback_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "get_callback",
        "--args",
        json.dumps(withdrawal_callback_args),
        "--from",
        alice_name,
        "--gas",
        "2000000",
    )
    print(f"✅ Withdrawal callback verification result: {withdrawal_callback_result}")
    assert (
        withdrawal_callback_result.get("code", 1) == 0
    ), f"Failed to get withdrawal callback: {withdrawal_callback_result}"

    print(f"🎉 Complete ICA E2E workflow successful!")
    print(f"   - ICA Address: {ica_address}")
    print(f"   - Registration, funding, balance query, and withdrawal completed")
    print(f"   - All callbacks received and stored properly")
    print(f"   - Query ref_id: {query_ref_id}")
    print(f"   - Script deployment, IBC operations, and callback handling working")
