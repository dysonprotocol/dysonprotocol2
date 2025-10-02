from dys import (
    _msg,
    _query,
    get_script_address,
    emit_event,
    get_block_info,
)
import json
import base64


def encode_json(json_data):
    """Helper function to encode JSON data"""
    return _query(
        {
            "@type": "/dysonprotocol.script.v1.QueryEncodeJsonRequest",
            "json": json.dumps(json_data),
        }
    )


def decode_bytes(type_url, encoded_bytes):
    """Helper function to decode bytes"""
    return _query(
        {
            "@type": "/dysonprotocol.script.v1.QueryDecodeBytesRequest",
            "type_url": type_url,
            "bytes": encoded_bytes,
        }
    )


def register(
    connection_id="connection-0", host_connection_id=None, encoding="proto3json"
):
    """
    Register a new Interchain Account on the host chain.
    
    Equivalent to:
    dysond tx interchain-accounts controller register connection-0 \
      --version '{"version":"ics27-1","controller_connection_id":"connection-0",...}'
    
    Args:
        connection_id: The IBC connection ID to use for the controller side
        host_connection_id: The connection ID on the host side (defaults to same as connection_id)
        encoding: The encoding format to use ("proto3json" or "protobuf")
        
    Returns:
        Dictionary with registration result (address will be available after IBC handshake)
    """
    if host_connection_id is None:
        # Try to derive host_connection_id from counterparty of the controller connection.
        # If the query type is unavailable in this runtime, default to controller's connection_id.
        derived_host_cid = None
        try:
            conn = _query(
                {
                    "@type": "/ibc.core.connection.v1.QueryConnectionRequest",
                    "connection_id": connection_id,
                }
            )
            derived_host_cid = (
                conn.get("connection", {}).get("counterparty", {}).get("connection_id")
            )
        except Exception as e:
            print(
                f"Connection query unsupported or failed, defaulting host_connection_id={connection_id}: {str(e)}"
            )
        host_connection_id = derived_host_cid or connection_id

    # Construct the version JSON as required by ICA specification
    # ICA channels must be ORDERED
    version_data = {
        "version": "ics27-1",
        "controller_connection_id": connection_id,
        "host_connection_id": host_connection_id,
        "address": "",  # Will be assigned by the host chain
        "encoding": encoding,
        "tx_type": "sdk_multi_msg",
    }

    print(
        f"Starting ICA registration for connection {connection_id}, owner: {get_script_address()}"
    )

    try:
        # Send the ICA registration message with proper ordering
        tx_result = _msg(
            {
                "@type": "/ibc.applications.interchain_accounts.controller.v1.MsgRegisterInterchainAccount",
                "owner": get_script_address(),
                "connection_id": connection_id,
                "version": json.dumps(version_data),
                "ordering": "ORDER_ORDERED",  # Explicitly specify ORDERED channel
            }
        )

        print("ICA registration initiated successfully")
        emit_event("ica_registration_sent", connection_id)

        return {
            "status": "success",
            "message": "ICA registration initiated - address will be available after IBC handshake completion",
            "connection_id": connection_id,
            "tx_result": tx_result,
        }

    except Exception as e:
        print(f"ICA registration failed: {str(e)}")

        return {"status": "error", "connection_id": connection_id, "message": str(e)}


def fund(
    denom,
    amount,
    src_port="transfer",
    src_channel="channel-0",
    connection_id="connection-0",
):
    """
    Send IBC coins from this chain controller to the registered address on the host chain.

    Equivalent to:
    dysond tx ibc-transfer transfer [src-port] [src-channel] [receiver] [coin]

    Args:
        denom: The denomination of the coin to send
        amount: The amount to send
        src_port: Source port (default: "transfer")
        src_channel: Source channel (default: "channel-0")
        connection_id: Connection ID to get the registered ICA address

    Returns:
        Dictionary with transfer result
    """
    try:
        # Get the registered ICA address
        ica_info = _query(
            {
                "@type": "/ibc.applications.interchain_accounts.controller.v1.QueryInterchainAccountRequest",
                "owner": get_script_address(),
                "connection_id": connection_id,
            }
        )

        receiver_address = ica_info["address"]

        print(f"Starting IBC transfer: {amount} {denom} to {receiver_address}")

        # Send IBC transfer
        tx_result = _msg(
            {
                "@type": "/ibc.applications.transfer.v1.MsgTransfer",
                "source_port": src_port,
                "source_channel": src_channel,
                "token": {"denom": denom, "amount": str(amount)},
                "sender": get_script_address(),
                "receiver": receiver_address,
                "timeout_height": {"revision_number": "0", "revision_height": "0"},
                "timeout_timestamp": "9999999999999999999",  # Far future timestamp
                "memo": "",
            }
        )

        print(f"IBC transfer successful to {receiver_address}")
        emit_event("ica_funded", f"{amount} {denom}")

        return {
            "status": "success",
            "receiver": receiver_address,
            "denom": denom,
            "amount": amount,
            "tx_result": tx_result,
        }

    except Exception as e:
        print(f"IBC transfer failed: {str(e)}")

        return {"status": "error", "message": str(e)}


def request_query_balance(connection_id="connection-0"):
    """
    Query balance of the registered ICA address on the host chain.

    Sends a MsgSendTx + MsgModuleQuerySafe + cosmos.bank.v1beta1.Query/AllBalances

    Args:
        connection_id: The IBC connection ID to use

    Returns:
        Dictionary with ref_id and query result
    """
    try:
        # Get the registered ICA address
        ica_info = _query(
            {
                "@type": "/ibc.applications.interchain_accounts.controller.v1.QueryInterchainAccountRequest",
                "owner": get_script_address(),
                "connection_id": connection_id,
            }
        )

        target_address = ica_info["address"]

        print(f"Starting balance query for {target_address}")

        # Construct the request to query all balances
        balance_query_encoded = encode_json(
            {
                "@type": "/cosmos.bank.v1beta1.QueryAllBalancesRequest",
                "address": target_address,
            }
        )

        # Construct the ModuleQuerySafe message
        module_query_safe = {
            "@type": "/ibc.applications.interchain_accounts.host.v1.MsgModuleQuerySafe",
            "signer": target_address,
            "requests": [
                {
                    "path": "/cosmos.bank.v1beta1.Query/AllBalances",
                    "data": balance_query_encoded["bytes"],
                }
            ],
        }

        # Get block info for ref_id tracking
        block_info = get_block_info()
        ref_id = f"balance_query_{block_info['height']}"

        # Send the ICA transaction with callback
        tx_result = _msg(
            {
                "@type": "/ibc.applications.interchain_accounts.controller.v1.MsgSendTx",
                "owner": get_script_address(),
                "connection_id": connection_id,
                "packet_data": {
                    "type": "TYPE_EXECUTE_TX",
                    "data": base64.b64encode(
                        json.dumps({"messages": [module_query_safe]}).encode()
                    ).decode(),
                    "memo": json.dumps(
                        {
                            "src_callback": {
                                "address": get_script_address(),
                                "function_name": "ibc_callback",
                                "kwargs": {
                                    "topic": "balance_query",
                                    "ref_id": ref_id,
                                    "target_address": target_address,
                                },
                                "args": [],
                            }
                        }
                    ),
                },
                "relative_timeout": 10000000000,  # 10 seconds in nanoseconds
            }
        )

        print(f"Balance query sent for {target_address}, ref_id: {ref_id}")
        emit_event("balance_query_requested", ref_id)

        return {
            "status": "success",
            "ref_id": ref_id,
            "target_address": target_address,
            "tx_result": tx_result,
        }

    except Exception as e:
        print(f"Balance query failed: {str(e)}")

        return {"status": "error", "message": str(e)}


def ibc_callback(topic, ref_id, *args, **kwargs):
    """
    Generic IBC callback function for handling all ICA operation responses.

    Stores all the data under the corresponding topic and ref_id.
    Index format: f"query_callback/{topic}/{ref_id}"

    Args:
        topic: The topic/category of the IBC operation (e.g., "balance_query", "withdrawal")
        *args: Arguments passed from the callback
        **kwargs: Keyword arguments response data
    """
    try:
        print(
            f"IBC callback received for topic: {topic}, args: {args}, kwargs: {kwargs}"
        )

        target_address = kwargs.get("target_address", "unknown")

        # Store the callback data with topic-based indexing
        storage_index = f"query_callback/{topic}/{ref_id}"

        storage_data = {
            "topic": topic,
            "ref_id": ref_id,
            "target_address": target_address,
            "timestamp": get_block_info()["time"],
            "height": get_block_info()["height"],
            "args": args,
            "kwargs": kwargs,
        }

        _msg(
            {
                "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
                "owner": get_script_address(),
                "index": storage_index,
                "data": json.dumps(storage_data),
            }
        )

        print(f"IBC callback stored at {storage_index} for topic: {topic}")
        emit_event("ibc_callback_completed", f"{topic}:{ref_id}")

        return {
            "status": "success",
            "topic": topic,
            "ref_id": ref_id,
            "storage_index": storage_index,
        }

    except Exception as e:
        print(f"IBC callback failed for topic {topic}: {str(e)}")

        return {"status": "error", "topic": topic, "message": str(e)}


def get_callback(topic, ref_id=None):
    """
    Get callback results for a specific topic and ref_id.

    Args:
        topic: The topic/category of the IBC operation (e.g., "balance_query", "withdrawal")
        seq: Specific ref_id number to retrieve, or None for the latest

    Returns:
        Dictionary with the callback result data
    """
    try:
        if ref_id is not None:
            # Get specific ref_id
            storage_index = f"query_callback/{topic}/{ref_id}"
            print(f"Querying specific callback: {storage_index}")

            storage_result = _query(
                {
                    "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
                    "owner": get_script_address(),
                    "index": storage_index,
                }
            )

            if not storage_result.get("entry"):
                return {
                    "status": "not_found",
                    "message": f"No callback found for topic {topic}, ref_id {ref_id}",
                }

            callback_data = json.loads(storage_result["entry"]["data"])
            print(f"Retrieved specific callback: {storage_index}")

            return {"status": "success", "index": storage_index, "data": callback_data}
        else:
            # Get latest for this topic
            print(f"Querying latest callback for topic: {topic}")

            storage_result = _query(
                {
                    "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
                    "owner": get_script_address(),
                    "index_prefix": f"query_callback/{topic}/",
                    "pagination": {"limit": 1, "reverse": True},
                }
            )

            if not storage_result.get("entries") or len(storage_result["entries"]) == 0:
                return {
                    "status": "not_found",
                    "message": f"No callbacks found for topic {topic}",
                }

            latest_entry = storage_result["entries"][0]
            latest_data = json.loads(latest_entry["data"])

            print(
                f"Retrieved latest callback for topic {topic}: {latest_entry['index']}"
            )

            return {
                "status": "success",
                "index": latest_entry["index"],
                "data": latest_data,
            }

    except Exception as e:
        print(f"Failed to get callback for topic '{topic}': {str(e)}")

        return {"status": "error", "topic": topic, "ref_id": ref_id, "message": str(e)}


def withdraw(
    denom,
    amount,
    dest_port="transfer",
    dest_channel="channel-0",
    connection_id="connection-0",
):
    """
    Withdraw coins from the host account back to the controller account.

    Sends MsgSendTx + MsgTransfer to transfer coins from host account to controller account.

    Args:
        denom: The denomination of the coin to withdraw
        amount: The amount to withdraw
        dest_port: Destination port (default: "transfer")
        dest_channel: Destination channel (default: "channel-0")
        connection_id: Connection ID to get the registered ICA address

    Returns:
        Dictionary with withdrawal result
    """
    try:
        # Get the registered ICA address (sender on host chain)
        ica_info = _query(
            {
                "@type": "/ibc.applications.interchain_accounts.controller.v1.QueryInterchainAccountRequest",
                "owner": get_script_address(),
                "connection_id": connection_id,
            }
        )

        sender_address = ica_info["address"]  # ICA address on host chain
        receiver_address = get_script_address()  # Controller address on this chain

        print(
            f"Starting withdrawal: {amount} {denom} from {sender_address} to {receiver_address}"
        )

        # Construct IBC transfer message to send from host chain back to controller
        ibc_transfer_msg = {
            "@type": "/ibc.applications.transfer.v1.MsgTransfer",
            "source_port": dest_port,
            "source_channel": dest_channel,
            "token": {"denom": denom, "amount": str(amount)},
            "sender": sender_address,
            "receiver": receiver_address,
            "timeout_height": {"revision_number": "0", "revision_height": "0"},
            "timeout_timestamp": "9999999999999999999",  # Far future timestamp
            "memo": "",
        }

        ref_id = f"withdrawal_{get_block_info()['height']}"

        # Send the ICA transaction
        tx_result = _msg(
            {
                "@type": "/ibc.applications.interchain_accounts.controller.v1.MsgSendTx",
                "owner": get_script_address(),
                "connection_id": connection_id,
                "packet_data": {
                    "type": "TYPE_EXECUTE_TX",
                    "data": base64.b64encode(
                        json.dumps({"messages": [ibc_transfer_msg]}).encode()
                    ).decode(),
                    "memo": json.dumps(
                        {
                            "src_callback": {
                                "address": get_script_address(),
                                "function_name": "ibc_callback",
                                "kwargs": {
                                    "topic": "withdrawal",
                                    "ref_id": ref_id,
                                    "sender": sender_address,
                                    "receiver": receiver_address,
                                    "denom": denom,
                                    "amount": amount,
                                },
                                "args": [],
                            }
                        }
                    ),
                },
                "relative_timeout": 10000000000,  # 10 seconds in nanoseconds
            }
        )

        print(f"Withdrawal successful: {amount} {denom}")
        emit_event("ica_withdrawn", f"{amount} {denom}")

        return {
            "status": "success",
            "sender": sender_address,
            "receiver": receiver_address,
            "denom": denom,
            "amount": amount,
            "tx_result": tx_result,
            "ref_id": ref_id,
        }

    except Exception as e:
        print(f"Withdrawal failed: {str(e)}")

        return {"status": "error", "message": str(e)}


def get_ica_address(connection_id="connection-0"):
    """
    Query the registered ICA address for the given connection.

    Use this function after ICA registration to check if the IBC handshake has completed
    and the address is available.

    Args:
        connection_id: The IBC connection ID to query

    Returns:
        Dictionary with the ICA address if found, or error status
    """
    try:
        print(f"Querying ICA address for connection {connection_id}")

        # Query the registered ICA address
        ica_info = _query(
            {
                "@type": "/ibc.applications.interchain_accounts.controller.v1.QueryInterchainAccountRequest",
                "owner": get_script_address(),
                "connection_id": connection_id,
            }
        )

        registered_address = ica_info["address"]
        print(f"Found ICA address: {registered_address}")
        emit_event("ica_address_found", registered_address)

        return {
            "status": "success",
            "registered_address": registered_address,
            "connection_id": connection_id,
        }

    except Exception as e:
        print(f"ICA address not found: {str(e)}")

        return {
            "status": "not_found",
            "connection_id": connection_id,
            "message": str(e),
        }
