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
    )
    print(f"📝 Script deployment result: {update_result}")
    assert (
        update_result.get("code", 1) == 0
    ), f"Failed to deploy ICA e2e script: {update_result}"

    # Discover transfer channel pair and derive controller/host connection IDs
    chain_a = ibc_setup[0]
    chain_b = ibc_setup[1] if len(ibc_setup) > 1 else ibc_setup[0]
    chs_a = chain_a("query", "ibc", "channel", "channels")
    chs_b = chain_b("query", "ibc", "channel", "channels")
    a_open = [
        c
        for c in chs_a.get("channels", [])
        if c.get("port_id") == "transfer" and c.get("state") == "STATE_OPEN"
    ]
    assert (
        len(a_open) > 0
    ), f"No OPEN transfer channel on Chain A. Full: {json.dumps(chs_a, indent=2)}"
    transfer_chan_id_a = a_open[0].get("channel_id")
    b_matches = [
        c
        for c in chs_b.get("channels", [])
        if c.get("port_id") == "transfer"
        and c.get("state") == "STATE_OPEN"
        and c.get("counterparty", {}).get("channel_id") == transfer_chan_id_a
    ]
    assert (
        len(b_matches) > 0
    ), f"No OPEN transfer counterparty for {transfer_chan_id_a} on Chain B. Full: {json.dumps(chs_b, indent=2)}"
    transfer_chan_id_b = b_matches[0].get("channel_id")
    end_a = chain_a("query", "ibc", "channel", "end", "transfer", transfer_chan_id_a)
    end_b = chain_b("query", "ibc", "channel", "end", "transfer", transfer_chan_id_b)
    assert end_a.get(
        "channel"
    ), f"Missing channel end for A transfer/{transfer_chan_id_a}: {json.dumps(end_a, indent=2)}"
    assert end_b.get(
        "channel"
    ), f"Missing channel end for B transfer/{transfer_chan_id_b}: {json.dumps(end_b, indent=2)}"
    controller_connection_id = end_a["channel"].get("connection_hops", [None])[0]
    host_connection_id = end_b["channel"].get("connection_hops", [None])[0]
    assert (
        controller_connection_id
    ), f"No connection hop on A channel {transfer_chan_id_a}: {json.dumps(end_a, indent=2)}"
    assert (
        host_connection_id
    ), f"No connection hop on B channel {transfer_chan_id_b}: {json.dumps(end_b, indent=2)}"
    print(
        f"🔗 Derived: transfer A={transfer_chan_id_a} B={transfer_chan_id_b}; connections controller={controller_connection_id} host={host_connection_id}"
    )

    # 2. Register ICA account using derived connection IDs
    print(
        f"🔗 Registering ICA account (controller={controller_connection_id}, host={host_connection_id})..."
    )
    register_args = [controller_connection_id, host_connection_id, "proto3json"]
    register_result = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "register",
        "--args",
        json.dumps(register_args),
        "--from",
        alice_name,
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
        chan_a = chain_a("query", "ibc", "channel", "end", "transfer", "channel-0")
        chan_b = chain_b("query", "ibc", "channel", "end", "transfer", "channel-0")
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

    # Remove hardcoded pre-asserts; rely on dynamic discovery and polls below

    # Poll: ICS-27 controller and host channels are OPEN on both chains
    def _ics27_channels_open():
        ctrl_port = f"icacontroller-{alice_address}"
        chain_a = ibc_setup[0]
        chain_b = ibc_setup[1] if len(ibc_setup) > 1 else ibc_setup[0]

        chs_a = chain_a("query", "ibc", "channel", "channels")
        chs_b = chain_b("query", "ibc", "channel", "channels")

        ica_ctrl = [
            c for c in chs_a.get("channels", []) if c.get("port_id") == ctrl_port
        ]
        ica_host = [
            c for c in chs_b.get("channels", []) if c.get("port_id") == "icahost"
        ]

        a_open = any([c.get("state") == "STATE_OPEN" for c in ica_ctrl])
        b_open = any([c.get("state") == "STATE_OPEN" for c in ica_host])

        print(f"🛰️  ICS-27 controller open on A: {a_open}; host open on B: {b_open}")
        return a_open and b_open

    poll_until_condition(
        _ics27_channels_open,
        timeout=10,
        poll_interval=1,
        error_message="ICS-27 channels not open on both chains",
    )

    # Resolve transfer channel IDs dynamically (do not assume channel-0)
    def _resolve_transfer_channels():
        chain_a = ibc_setup[0]
        chain_b = ibc_setup[1] if len(ibc_setup) > 1 else ibc_setup[0]

        chs_a = chain_a("query", "ibc", "channel", "channels")
        chs_b = chain_b("query", "ibc", "channel", "channels")

        a_open = [
            c
            for c in chs_a.get("channels", [])
            if c.get("port_id") == "transfer" and c.get("state") == "STATE_OPEN"
        ]
        assert (
            len(a_open) > 0
        ), f"No OPEN transfer channel found on Chain A. Full: {json.dumps(chs_a, indent=2)}"

        # Pick the first open channel on A, find its mapped partner on B via counterparty.channel_id
        a_chan_id = a_open[0].get("channel_id")
        b_matches = [
            c
            for c in chs_b.get("channels", [])
            if c.get("port_id") == "transfer"
            and c.get("state") == "STATE_OPEN"
            and c.get("counterparty", {}).get("channel_id") == a_chan_id
        ]
        assert (
            len(b_matches) > 0
        ), f"No OPEN transfer counterparty for {a_chan_id} on Chain B. Full: {json.dumps(chs_b, indent=2)}"

        b_chan_id = b_matches[0].get("channel_id")
        print(
            f"🚚 Resolved transfer channel pair: A transfer/{a_chan_id} <-> B transfer/{b_chan_id}"
        )
        return a_chan_id, b_chan_id

    transfer_chan_id_a, transfer_chan_id_b = _resolve_transfer_channels()

    # Poll: transfer channel is OPEN on both chains using resolved IDs
    def _transfer_channel_open():
        chain_a = ibc_setup[0]
        chain_b = ibc_setup[1] if len(ibc_setup) > 1 else ibc_setup[0]

        end_a = chain_a(
            "query", "ibc", "channel", "end", "transfer", transfer_chan_id_a
        )
        end_b = chain_b(
            "query", "ibc", "channel", "end", "transfer", transfer_chan_id_b
        )

        a_open = end_a.get("channel", {}).get("state") == "STATE_OPEN"
        b_open = end_b.get("channel", {}).get("state") == "STATE_OPEN"

        print(
            f"🚚 transfer/{transfer_chan_id_a} open on A: {a_open}; transfer/{transfer_chan_id_b} on B: {b_open}"
        )
        return a_open and b_open

    poll_until_condition(
        _transfer_channel_open,
        timeout=10,
        poll_interval=1,
        error_message="transfer channel not open on both chains",
    )

    # Resolve ICS-27 controller/host channel IDs to use in later diagnostics
    def _resolve_ics27_channels():
        ctrl_port = f"icacontroller-{alice_address}"
        chain_a = ibc_setup[0]
        chain_b = ibc_setup[1] if len(ibc_setup) > 1 else ibc_setup[0]

        chs_a = chain_a("query", "ibc", "channel", "channels")
        chs_b = chain_b("query", "ibc", "channel", "channels")

        ica_ctrl_list = [
            c for c in chs_a.get("channels", []) if c.get("port_id") == ctrl_port
        ]
        assert (
            len(ica_ctrl_list) > 0
        ), f"No ICS-27 controller channel found on Chain A for port {ctrl_port}. Full A channels: {json.dumps(chs_a, indent=2)}"

        ctrl_chan_id = ica_ctrl_list[0].get("channel_id")

        ica_host_list = [
            c
            for c in chs_b.get("channels", [])
            if c.get("port_id") == "icahost"
            and c.get("counterparty", {}).get("port_id") == ctrl_port
        ]
        assert (
            len(ica_host_list) > 0
        ), f"No ICS-27 host channel found on Chain B for counterparty port {ctrl_port}. Full B channels: {json.dumps(chs_b, indent=2)}"

        host_chan_id = ica_host_list[0].get("channel_id")

        print(
            f"🛰️  Resolved ICS-27 channels -> controller: {ctrl_port}/{ctrl_chan_id}, host: icahost/{host_chan_id}"
        )
        return ctrl_port, ctrl_chan_id, host_chan_id

    ctrl_port, ctrl_chan_id, host_chan_id = _resolve_ics27_channels()

    # Snapshot helper to print IBC progress for ICS-27 on both chains
    def _ibc_progress_snapshot(label):
        chain_a = ibc_setup[0]
        chain_b = ibc_setup[1] if len(ibc_setup) > 1 else ibc_setup[0]

        print(f"\n===== IBC Progress Snapshot: {label} =====")
        end_a = chain_a("query", "ibc", "channel", "end", ctrl_port, ctrl_chan_id)
        end_b = chain_b("query", "ibc", "channel", "end", "icahost", host_chan_id)
        print(f"A end {ctrl_port}/{ctrl_chan_id}: {json.dumps(end_a, indent=2)}")
        print(f"B end icahost/{host_chan_id}: {json.dumps(end_b, indent=2)}")

        try_next = chain_a(
            "query", "ibc", "channel", "next-sequence-send", ctrl_port, ctrl_chan_id
        )
        print(
            f"A next-sequence-send {ctrl_port}/{ctrl_chan_id}: {json.dumps(try_next, indent=2)}"
        )

        try_commit = chain_a(
            "query",
            "ibc",
            "channel",
            "packet-commitments",
            ctrl_port,
            ctrl_chan_id,
        )
        seqs = [int(c.get("sequence", 0)) for c in try_commit.get("commitments", [])]
        print(
            f"A packet-commitments {ctrl_port}/{ctrl_chan_id}: sequences={seqs} full={json.dumps(try_commit, indent=2)}"
        )
        print("===== End Snapshot =====\n")

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
            json.dumps([controller_connection_id]),
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
        timeout=10,
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
        json.dumps([controller_connection_id]),
        "--from",
        alice_name,
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
    fund_args = [
        "udys",
        "5000",
        "transfer",
        transfer_chan_id_a,
        controller_connection_id,
    ]
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
        json.dumps([controller_connection_id]),
        "--from",
        alice_name,
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
            "query",
            "script",
            "run",
            "--executor-address",
            alice_address,
            "--script-address",
            alice_address,
            "--function-name",
            "get_callback",
            "--args",
            json.dumps(callback_args),
            "--kwargs",
            "{}",
            "-o",
            "json",
        )
        print(f"🔍 Callback (query run) result: {result}")
        assert "result" in result, f"get_callback run failed: {result}"

        # Parse query run structured response
        result_data = json.loads(result["result"])  # outer wrapper
        callback_result = result_data.get("result", {})  # actual function return
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
    )
    print(f"🔍 List callbacks result: {list_callbacks_result}")

    poll_until_condition(
        _balance_callback_received,
        timeout=10,
        poll_interval=1,
        error_message="Balance query callback not received",
    )

    # 8. Verify balance query callback data
    callback_args = ["balance_query", query_ref_id]
    print(f"✅ Getting callback data for verification...")
    callback_result = dysond_bin(
        "query",
        "script",
        "run",
        "--executor-address",
        alice_address,
        "--script-address",
        alice_address,
        "--function-name",
        "get_callback",
        "--args",
        json.dumps(callback_args),
        "--kwargs",
        "{}",
        "-o",
        "json",
    )
    print(f"✅ Callback verification (query run) result: {callback_result}")
    assert "result" in callback_result, f"get_callback run failed: {callback_result}"

    # Parse and verify
    result_data = json.loads(callback_result["result"])  # outer wrapper
    verify_callback = result_data.get("result", {})  # actual function return
    assert (
        isinstance(verify_callback, dict) and verify_callback.get("status") == "success"
    ), f"Expected success status. Full context: {json.dumps(verify_callback, indent=2)}"

    # 9. Wait for host (chain B) voucher to arrive and derive its denom dynamically
    print(f"⏳ Waiting for host voucher on Chain B...")
    host_voucher = {"denom": None}

    def _host_voucher_funded():
        balances = chain_b("query", "bank", "balances", ica_address)
        bals = balances.get("balances", [])
        ibc_bals = [
            b
            for b in bals
            if isinstance(b, dict) and str(b.get("denom", "")).startswith("ibc/")
        ]
        eligible = [
            b.get("denom") for b in ibc_bals if int(str(b.get("amount", "0"))) >= 5000
        ]
        host_voucher["denom"] = (
            eligible[0] if len(eligible) > 0 else host_voucher["denom"]
        )
        print(
            f"🔎 Host voucher candidates: {ibc_bals}; selected={host_voucher['denom']}"
        )
        return len(eligible) > 0

    poll_until_condition(
        _host_voucher_funded,
        timeout=10,
        poll_interval=1,
        error_message="Host voucher not found on Chain B",
    )

    voucher_denom_b = host_voucher["denom"]
    print(f"✅ Host voucher ready: {voucher_denom_b}")

    # Withdraw funds back to controller using discovered voucher denom
    withdraw_args = [
        voucher_denom_b,
        "1000",
        "transfer",
        transfer_chan_id_b,
        controller_connection_id,
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
    )
    print(f"💸 Withdraw result: {withdraw_result}")
    assert (
        withdraw_result.get("code", 1) == 0
    ), f"Failed to withdraw from ICA account: {withdraw_result}"

    # Immediate post-withdraw diagnostic snapshot to capture sequences/commitments
    _ibc_progress_snapshot("post-withdraw-tx")

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

        # Extract ref_id when successful
        is_success = (
            isinstance(withdraw_response, dict)
            and withdraw_response.get("status") == "success"
        )
        withdrawal_ref_id = (
            withdraw_response.get("ref_id") if is_success else withdrawal_ref_id
        )

    assert (
        withdrawal_ref_id is not None
    ), f"Withdrawal ref_id should be returned. Full withdraw result: {json.dumps(withdraw_result, indent=2)}"

    # 10. Wait for withdrawal callback
    print(f"⏳ Waiting for withdrawal callback...")

    def _withdrawal_callback_received():
        """Check if withdrawal callback has been received"""
        # Get specific callback for withdrawal topic via query run (read-only)
        callback_args = ["withdrawal", withdrawal_ref_id]
        print(f"🔍 Checking for withdrawal callback via query run...")
        result = dysond_bin(
            "query",
            "script",
            "run",
            "--executor-address",
            alice_address,
            "--script-address",
            alice_address,
            "--function-name",
            "get_callback",
            "--args",
            json.dumps(callback_args),
            "--kwargs",
            "{}",
            "-o",
            "json",
        )
        print(f"🔍 Withdrawal callback (query run) result: {result}")
        assert "result" in result, f"get_callback run failed: {result}"

        # Parse query run structured response
        result_data = json.loads(result["result"])  # outer wrapper
        callback_result = result_data.get("result", {})  # actual function return
        print(f"🔍 Withdrawal callback response: {callback_result}")

        # Check status and return
        is_dict = isinstance(callback_result, dict)
        status = callback_result.get("status") if is_dict else None
        print(f"🔍 Withdrawal callback status: {status}")
        # Ongoing snapshot to observe IBC progress while polling
        _ibc_progress_snapshot("poll-withdraw-callback")
        return status == "success"

    # Poll: withdrawal packet has been acknowledged (sequence 2 leaves packet commitments)
    def _withdrawal_packet_acknowledged():
        """Check if withdrawal packet (sequence 2) has been acknowledged by host"""
        try_commit = chain_a(
            "query", "ibc", "channel", "packet-commitments", ctrl_port, ctrl_chan_id
        )
        seqs = [int(c.get("sequence", 0)) for c in try_commit.get("commitments", [])]
        print(f"🛰️  Pending sequences on {ctrl_port}/{ctrl_chan_id}: {seqs}")
        is_acked = 2 not in seqs
        (
            print(f"✅ Withdrawal packet acknowledged")
            if is_acked
            else print(f"⏳ Withdrawal packet still pending (seq 2 in {seqs})")
        )
        return is_acked

    print(f"⏳ Waiting for withdrawal packet to be acknowledged...")
    poll_until_condition(
        _withdrawal_packet_acknowledged,
        timeout=30,
        poll_interval=1,
        error_message="Withdrawal packet not acknowledged by host",
    )

    poll_until_condition(
        _withdrawal_callback_received,
        timeout=10,
        poll_interval=1,
        error_message="Withdrawal callback not received",
    )

    # 11. Verify withdrawal callback data
    withdrawal_callback_args = ["withdrawal", withdrawal_ref_id]
    print(f"✅ Getting withdrawal callback data for verification...")
    withdrawal_callback_result = dysond_bin(
        "query",
        "script",
        "run",
        "--executor-address",
        alice_address,
        "--script-address",
        alice_address,
        "--function-name",
        "get_callback",
        "--args",
        json.dumps(withdrawal_callback_args),
        "--kwargs",
        "{}",
        "-o",
        "json",
    )
    print(
        f"✅ Withdrawal callback verification (query run) result: {withdrawal_callback_result}"
    )
    assert (
        "result" in withdrawal_callback_result
    ), f"get_callback run failed: {withdrawal_callback_result}"

    # Parse and verify
    _w_result_data = json.loads(withdrawal_callback_result["result"])  # outer wrapper
    _w_verify_callback = _w_result_data.get("result", {})  # actual function return
    assert (
        isinstance(_w_verify_callback, dict)
        and _w_verify_callback.get("status") == "success"
    ), f"Expected success status. Full context: {json.dumps(_w_verify_callback, indent=2)}"

    print(f"🎉 Complete ICA E2E workflow successful!")
    print(f"   - ICA Address: {ica_address}")
    print(f"   - Registration, funding, balance query, and withdrawal completed")
    print(f"   - All callbacks received and stored properly")
    print(f"   - Query ref_id: {query_ref_id}")
    print(f"   - Script deployment, IBC operations, and callback handling working")
