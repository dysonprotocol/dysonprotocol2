"""TewProtocol - Fast Ephemeral L2s with L1/L2 Queue Communication on DysonProtocol.

This module combines TewQueue (L1/L2 message passing) and TewChain (blockchain processing)
into a unified system for building ephemeral L2 solutions on DysonProtocol.

This is a proof-of-concept implementation and is not production-ready.
"""

# ======================== IMPORTS ========================
# Dyson runtime imports
from dys import (  # type: ignore
    _query,
    _msg,
    get_script_address,
    get_executor_address,
    dys_eval,
)

# Standard library imports
import json
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional, TypedDict, Union

# Constants
GENESIS_AUTH = get_script_address()


# ======================== TEWQUEUE DATACLASSES ========================


class Message(TypedDict):
    msg_id: str
    message_data: Any


class Response(TypedDict):
    msg_id: str
    response_data: Any


@dataclass
class Queueable:
    """Base class for L1 and L2 with common queue functionality"""

    queue_metadata: Dict[str, Any] = field(default_factory=dict)
    outgoing_queue: Dict[str, Message] = field(default_factory=dict)
    response_queue: Dict[str, Response] = field(default_factory=dict)

    def get_next_message_id(self):
        next_id = self.queue_metadata.get("next_message_id", 0)
        self.queue_metadata["next_message_id"] = next_id + 1
        return str(next_id)

    def send_message(self, msg: str):
        """sends a message to the other side"""
        # message can be any basic data type
        message_id = self.get_next_message_id()
        self.outgoing_queue[message_id] = {
            "msg_id": message_id,
            "message_data": msg,
        }
        return message_id

    def on_message(self, message: Message):
        """receive a message, now respond to it - to be overridden by subclasses"""
        raise NotImplementedError("Subclasses must implement on_message")

    def on_response(self, response):
        """handle response - to be overridden by subclasses"""
        raise NotImplementedError("Subclasses must implement on_response")

    def process_incoming_message(self, message: Message):
        print(f"DEBUG: process_incoming_message called with: {message}")
        result = self.on_message(message)
        print(f"DEBUG: on_message returned: {result}")
        self.response_queue[str(message["msg_id"])] = {
            "msg_id": message["msg_id"],
            "response_data": result,
        }
        print(f"DEBUG: Response queue after adding: {self.response_queue}")

    def process_response(self, response: Response):
        self.on_response(response)
        # Don't delete response here - it will be deleted by the cleanup logic
        # when the corresponding message is no longer in the sender's outgoing queue

    def process_snapshot_queue(self, other_snapshot):
        """Process messages from the other side's snapshot"""
        # height must be greater than the last height but not necessarily the subsequent height

        other_height = other_snapshot.queue_metadata.get("last_height", 0)

        # Process all messages from the other snapshot
        for msg_id, msg in sorted(other_snapshot.outgoing_queue.items()):
            self.process_incoming_message(msg)
        for msg_id, response in sorted(other_snapshot.response_queue.items()):
            self.process_response(response)

        self.queue_metadata["last_height"] = other_height

    # ==========================================
    # STORAGE METHODS - to be overridden by subclasses
    # ==========================================

    def _get_storage_key(self, instance_id: str = "default") -> str:
        """Generate storage key - to be overridden by subclasses"""
        raise NotImplementedError("Subclasses must implement _get_storage_key")

    def _load_data(self, instance_id: str = "default") -> Optional[Dict]:
        """Load JSON data from storage"""
        storage_key = self._get_storage_key(instance_id)
        response = _query(
            {
                "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
                "owner": get_script_address(),
                "index": storage_key,
            },
        )

        # Handle both success and error response structures
        return (
            json.loads(response["entry"]["data"])
            if "entry" in response and "data" in response["entry"]
            else None
        )

    def _save_data(self, data: Dict, instance_id: str = "default"):
        """Save JSON data to storage"""
        storage_key = self._get_storage_key(instance_id)
        _msg(
            {
                "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
                "owner": get_script_address(),
                "index": storage_key,
                "data": json.dumps(data, default=str),
            }
        )


@dataclass
class L1(Queueable):
    """L1 queue implementation - runs on DysonProtocol main chain

    L1 handles:
    - Sending messages to L2
    - Processing responses from L2
    - Storing state in DysonProtocol storage
    """

    # Store responses from L2 for verification
    stored_responses: Dict[str, str] = field(default_factory=dict)

    def say_hi(self, sender: str, greeting: str):
        """Example L1-initiated message to L2"""
        return self.send_message(f"{sender} says hi: {greeting}")

    def on_message(self, message: Message):
        """Process messages from L2"""
        # Check if this is a structured message with a type
        msg_data = message["message_data"]
        if isinstance(msg_data, dict) and "type" in msg_data:
            msg_type = msg_data["type"]

            # Handle query_dyson requests
            if msg_type == "query_dyson":
                query_params = msg_data.get("params", {})
                try:
                    # Execute the Dyson query
                    result = _query(query_params)
                    return {"type": "query_response", "result": result, "error": None}
                except Exception as e:
                    return {"type": "query_response", "result": None, "error": str(e)}

            # Handle other message types here in the future

        # Default acknowledgment for simple messages
        return f'L1 received from L2: {message["message_data"]}'

    def on_response(self, response: Response):
        """Handle L2's responses to L1 messages

        This is where L1 stores the response from L2.
        """
        print(
            f"L1: Received response for message {response['msg_id']}: {response['response_data']}"
        )
        # Store the response
        self.stored_responses[response["msg_id"]] = response["response_data"]

    def on_l2_block(self, l2_block_data: Dict) -> bool:
        """Process a submitted L2 block

        Note: Queue messages are processed like TCP (ordered, acknowledged).
        We only process messages in sequence by message ID, not by block height.

        For example, if L2 sends message 0 in block 3 and message 1 in block 20,
        we process them in that order regardless of the gap in block heights.

        Future implementations might support UDP-like semantics (unordered).

        Returns:
            True if any messages were processed, False otherwise
        """
        l2_state = l2_block_data["post_state"].get("l2_queue_state", {})
        if not l2_state:
            return False

        # Check if this block contains the next message(s) we need
        l2_outgoing = l2_state.get("outgoing_queue", {})
        messages_processed = False

        # Process messages in sequence starting from next_l2_message_id
        next_l2_msg_id = self.queue_metadata.get("next_l2_message_id", 0)
        while str(next_l2_msg_id) in l2_outgoing:
            msg_data = l2_outgoing[str(next_l2_msg_id)]
            message: Message = {
                "msg_id": msg_data["msg_id"],
                "message_data": msg_data["message_data"],
            }

            # Process this message
            self.process_incoming_message(message)
            self.queue_metadata["next_l2_message_id"] = next_l2_msg_id + 1
            next_l2_msg_id = self.queue_metadata["next_l2_message_id"]
            messages_processed = True

        # Also check for responses to our messages
        l2_responses = l2_state.get("response_queue", {})
        for msg_id_str, resp_data in l2_responses.items():
            # Only process responses for messages we haven't acknowledged yet
            if msg_id_str in self.outgoing_queue:
                response: Response = {
                    "msg_id": resp_data["msg_id"],
                    "response_data": resp_data["response_data"],
                }
                self.process_response(response)
                # Remove the original message since we got a response
                del self.outgoing_queue[msg_id_str]
                messages_processed = True

        return messages_processed

    def _get_storage_key(self, instance_id: str = "default") -> str:
        """Generate storage key for L1 state in DysonProtocol storage"""
        return f"tew/{instance_id}/l1"


@dataclass
class L2(Queueable):
    """L2 queue implementation - runs as TEW ephemeral chain

    L2 handles:
    - Processing messages from L1
    - Computing responses based on message content
    - Maintaining state in memory (during tests)
    """

    # L2-specific state
    current_height: int = 0
    processed_messages: Dict[str, str] = field(default_factory=dict)

    def say_hola(self, sender: str, greeting: str):
        """Example L2-initiated message to L1"""
        return self.send_message(f"{sender} says hola: {greeting}")

    def on_message(self, message: Message):
        """Process messages from L1

        This is the key function that processes L1 messages and returns
        a response that L1 will receive in its on_response callback.
        """
        print(f"DEBUG L2.on_message: Received message: {message}")
        # Store that we processed this message
        self.processed_messages[message["msg_id"]] = message["message_data"]

        # Generate a response based on the message
        if (
            isinstance(message["message_data"], str)
            and "says hi:" in message["message_data"]
        ):
            print("DEBUG L2.on_message: Message contains 'says hi:', parsing...")
            # Extract the greeting
            parts = message["message_data"].split("says hi:", 1)
            if len(parts) == 2:
                sender_part = parts[0].strip()
                greeting = parts[1].strip()
                # Return a computed response
                response = (
                    f"L2 computed response: Hello {sender_part}, you said '{greeting}'"
                )
                print(f"DEBUG L2.on_message: Generated response: {response}")
                return response

        # Default response
        default_response = f'L2 processed: {message["message_data"]}'
        print(f"DEBUG L2.on_message: Using default response: {default_response}")
        return default_response

    def on_response(self, response: Response):
        """Handle L1's responses to L2 messages"""
        print(
            f"L2: Received response for message {response['msg_id']}: {response['response_data']}"
        )

    # ========================================
    # TEW CHAIN CALLBACKS - Core L2 Logic
    # ========================================

    def on_begin_block(self, block):
        """Called at the beginning of each TEW block"""
        # Height increment and queue processing are handled by the wrapper
        pass

    def on_tx(self, msg):
        """Process a user transaction on L2

        Note: The actual transaction processing is now handled by on_tx_wrapper
        which provides the proper eval scope with access to queue functions.
        This method is kept for compatibility but the wrapper does the real work.
        """
        # Transaction processing is handled by the wrapper
        pass

    def on_end_block(self):
        """Called at the end of each TEW block"""
        pass

    def on_queue_message(self, message):
        """Called when processing a queue message during begin_block"""
        # Logging is handled by the wrapper function
        # This method is here for future extensibility
        pass

    def on_queue_response(self, response):
        """Called when processing a queue response during begin_block"""
        # Logging is handled by the wrapper function
        # This method is here for future extensibility
        pass

    def _get_storage_key(self, instance_id: str = "default") -> str:
        """Generate storage key for L2 state (stored in TEW block state)"""
        return f"tew/{instance_id}/l2"


# ======================== TEWCHAIN TYPEDDICTS ========================


class TewTxResult(TypedDict):
    """The result of a transaction in the Tew chain."""

    signer: str
    sequence: int
    # 0-based index of the tx in the chain
    total_tx_count: int
    block_height: int
    result: Any
    error: Any
    stdout: str


class TewTxMsgData(TypedDict):
    """The data field of a Tew transaction body."""

    chain_id: str
    sequence: int
    data: str  # python code to for the tew_eval function


class TewTxMsg(TypedDict):
    """The body of a Tew transaction."""

    signer: str
    data: (
        TewTxMsgData | str
    )  # data is either a JSON string of TewTxMsgData, or the deserialized TewTxMsgData object
    app_domain: str  # "tew/tx"


class SignedTewTx(TypedDict):
    """A signed Tew transaction."""

    body: dict[str, Any]  # Contains messages, memo, etc.
    auth_info: dict[str, Any]
    signatures: list[str]


class Account(TypedDict):
    """A user account in the Tew chain."""

    address: str
    account_number: int
    sequence: int


class StateDict(TypedDict, total=False):
    """The state of the Tew chain."""

    # account_number -> account state sorted by account_number, allows for removal of accounts
    accounts_by_number: dict[str, Account]
    # address -> account_number
    account_numbers_by_address: dict[str, int]
    # next account number to assign
    next_account_number: int
    # Queue state fields - these contain the full L1/L2 instance state
    l1_queue_state: Optional[Dict[str, Any]]
    l2_queue_state: Optional[Dict[str, Any]]
    captured_stdout: str
    # Extra state here


class Metadata(TypedDict):
    """The metadata of a Tew block."""

    chain_id: str
    height: int
    time: str
    # current_authority == previous_block.metadata.next_authority by construction.
    # address that actually signed *this* block
    current_authority: str
    # address expected to sign the *next* block
    next_authority: str
    # number of txs processed in the chain since the chain started
    total_tx_count: int


class TewBlockBodyData(TypedDict):
    """The data of a Tew block body."""

    prev_signed_tew_block_hash: str
    metadata: Metadata
    pre_state: StateDict
    signed_txs: list[SignedTewTx]
    tx_results: list[TewTxResult]
    post_state: StateDict


class TewBlockBody(TypedDict):
    """The body of a Tew block."""

    signer: str
    # data is either a JSON string of TewBlockBodyData, or the deserialized TewBlockBodyData object
    data: TewBlockBodyData | str
    app_domain: str  # "tew/block"


class SignedTewBlock(TypedDict):
    """A signed Tew block."""

    body: dict[str, Any]  # Contains messages, memo, etc.
    auth_info: dict[str, Any]
    signatures: list[str]


# ======================== FACTORY FUNCTIONS ========================


def create_l1_from_snapshot(snapshot: Optional[Dict] = None):
    """Create an L1 instance from a snapshot or fresh - dyslang compatible"""
    if snapshot is None:
        # Create fresh L1 instance
        return L1(
            queue_metadata={"next_message_id": 0, "next_l2_message_id": 0},
            outgoing_queue={},
            response_queue={},
            stored_responses={},
        )

    # Recreate from snapshot with proper types
    queue_metadata = snapshot.get("queue_metadata", {"next_message_id": 0})
    stored_responses = snapshot.get("stored_responses", {})
    # Handle migration from old format where next_l2_message_id was a separate field
    if "next_l2_message_id" not in queue_metadata and "next_l2_message_id" in snapshot:
        queue_metadata["next_l2_message_id"] = snapshot["next_l2_message_id"]
    elif "next_l2_message_id" not in queue_metadata:
        queue_metadata["next_l2_message_id"] = 0

    # Reconstruct outgoing_queue with Message objects
    outgoing_queue = {}
    for msg_id, msg_data in snapshot.get("outgoing_queue", {}).items():
        if isinstance(msg_data, dict) and "msg_id" in msg_data:
            # Handle both old and new field names for compatibility
            message_content = msg_data.get("message_data", msg_data.get("msg"))
            outgoing_queue[msg_id] = {
                "msg_id": msg_data["msg_id"],
                "message_data": message_content,
            }

    # Reconstruct response_queue with Response objects
    response_queue = {}
    for resp_id, resp_data in snapshot.get("response_queue", {}).items():
        if isinstance(resp_data, dict) and "msg_id" in resp_data:
            # Handle both old and new field names for compatibility
            response_content = resp_data.get("response_data", resp_data.get("response"))
            response_queue[resp_id] = {
                "msg_id": resp_data["msg_id"],
                "response_data": response_content,
            }

    return L1(
        queue_metadata=queue_metadata,
        outgoing_queue=outgoing_queue,
        response_queue=response_queue,
        stored_responses=stored_responses,
    )


def create_l2_from_snapshot(snapshot: Optional[Dict] = None):
    """Create L2 instance from snapshot data (dyslang compatible)"""

    # Reconstruct the data structures from snapshot
    if snapshot:
        queue_metadata = snapshot.get("queue_metadata", {})

        # Reconstruct message objects from snapshot (preserve original string keys)
        outgoing_queue = {}
        outgoing_data = snapshot.get("outgoing_queue", {})
        for k, v in outgoing_data.items():
            # Handle both old and new field names for compatibility
            message_content = v.get("message_data", v.get("msg"))
            outgoing_queue[k] = {
                "msg_id": v["msg_id"],
                "message_data": message_content,
            }

        response_queue = {}
        response_data = snapshot.get("response_queue", {})
        for k, v in response_data.items():
            # Handle both old and new field names for compatibility
            response_content = v.get("response_data", v.get("response"))
            response_queue[k] = {
                "msg_id": v["msg_id"],
                "response_data": response_content,
            }
    else:
        # Empty defaults
        queue_metadata = {}
        outgoing_queue = {}
        response_queue = {}

    # Reconstruct L2-specific fields if available
    current_height = 0
    processed_messages = {}
    if snapshot:
        current_height = snapshot.get("current_height", 0)

    # Create instance with reconstructed data
    l2 = L2(
        queue_metadata=queue_metadata,
        outgoing_queue=outgoing_queue,
        response_queue=response_queue,
        current_height=current_height,
        processed_messages=processed_messages,
    )

    return l2


# ======================== TEWPROTOCOL FUNCTIONS ========================
#
# Architecture Overview:
#
# L1 Core Logic (DysonProtocol main chain):
# - Functions decorated with @l1_function run as DysonProtocol scripts
# - Handle deposits, withdrawals, and L2 snapshot validation
# - State stored in DysonProtocol storage
# - Examples: initialize_l1, say_hi, submit_l2_block
#
# L2 Core Logic (TEW ephemeral chain):
# - Chain logic methods are defined directly in the L2 class
# - Methods: on_begin_block, on_tx, on_end_block, on_queue_message, on_queue_response
# - Called through wrapper functions in build_next_block that provide access to chain utilities
# - State stored in TEW block state (in post_state["l2_queue_state"])
# - Example methods: L2.on_message (processes L1 messages), L2.say_hola
#
# The separation allows L1 to remain authoritative while L2 processes at high speed


def l1_function(func):
    """Decorator for L1 functions that run on DysonProtocol main chain

    These functions have access to DysonProtocol features:
    - _query, _msg for storage operations
    - get_executor_address for caller identification
    - get_attached_messages for processing deposits
    """
    # Authentication is done by the Dysprotocol chain, so we don't need to do anything here
    return func


def l2_function(func):
    """Decorator for L2 functions that process TEW transactions

    These functions run within the TEW chain context and process
    signed transactions from L2 users.

    Note: With the new architecture where L2 logic is in the L2 class,
    this decorator is less commonly used.
    """

    def process_tx(tew_tx: SignedTewTx):
        # TODO: verify the signature
        # TODO: patch the storage loaders
        L2_TX["body"] = tew_tx["body"]
        L2_TX["auth_info"] = tew_tx["auth_info"]
        L2_TX["signatures"] = tew_tx["signatures"]
        ret = func(**json.loads(tew_tx["body"]["messages"][0]["data"]))
        return ret

    return process_tx


# ==========================================
# L1 CORE LOGIC - Functions that run on DysonProtocol
# ==========================================
#
# These functions define the L1 behavior and can be called via:
# dysond tx script exec --function-name <function_name>


@l1_function
def initialize_l1(instance_id: str = "default"):
    """Initialize L1 state in storage.

    This must be called before any other L1 functions that expect state to exist.
    """
    storage_key = f"tew/{instance_id}/l1"

    # Check if L1 state already exists
    # Note: In dyslang we can't catch specific exceptions, and the query will throw if storage doesn't exist
    # So we first check if the storage exists by querying for it in a way that won't throw

    # Create new L1 instance
    l1 = create_l1_from_snapshot()

    # Save initial state (this will overwrite if it already exists)
    _msg(
        {
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": get_script_address(),
            "index": storage_key,
            "data": json.dumps(asdict(l1)),
        }
    )

    return {
        "status": "initialized",
        "message": f"L1 state initialized at {storage_key}",
        "initial_state": asdict(l1),
    }


@l1_function
def initialize_l2_genesis(
    instance_id: str = "default", chain_id: str = "", authority: str = ""
):
    """Initialize L2 genesis block after L1 has been initialized.

    This creates the initial L2 genesis block that references the existing L1 state.
    L1 MUST be initialized before calling this function.

    Args:
        instance_id: The instance identifier for this L1/L2 pair
        chain_id: The chain ID for the L2 instance (defaults to "tew-{instance_id}")
        authority: The initial authority address (defaults to script address)

    Returns:
        Success message with genesis block details

    Raises:
        Exception: If L1 has not been initialized
    """
    # Check that L1 exists
    storage_key = f"tew/{instance_id}/l1"
    response = _query(
        {
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": get_script_address(),
            "index": storage_key,
        }
    )

    if "entry" not in response or "data" not in response["entry"]:
        raise Exception(
            f"L1 must be initialized before L2. Run initialize_l1('{instance_id}') first."
        )

    # Load L1 state
    l1_data = json.loads(response["entry"]["data"])

    # Use default chain_id if not provided
    if not chain_id:
        chain_id = f"tew-{instance_id}"

    # Use script address as default authority
    if not authority:
        authority = get_script_address()

    # Create L2 genesis state
    l2 = create_l2_from_snapshot(None)

    # Create genesis block data
    genesis_block_data = {
        "prev_signed_tew_block_hash": "genesis",
        "metadata": {
            "chain_id": chain_id,
            "height": 0,
            "time": "2024-01-01T00:00:00Z",  # Genesis time
            "current_authority": authority,
            "next_authority": authority,
            "total_tx_count": 0,
            "instance_id": instance_id,
        },
        "pre_state": {
            "accounts_by_number": {
                "0": {"address": authority, "account_number": 0, "sequence": 0}
            },
            "account_numbers_by_address": {authority: 0},
            "next_account_number": 1,
            "l1_queue_state": l1_data,  # Reference to L1 state
            "l2_queue_state": asdict(l2),
        },
        "signed_txs": [],
        "tx_results": [],
        "post_state": {
            "accounts_by_number": {
                "0": {"address": authority, "account_number": 0, "sequence": 0}
            },
            "account_numbers_by_address": {authority: 0},
            "next_account_number": 1,
            "l1_queue_state": l1_data,  # Reference to L1 state
            "l2_queue_state": asdict(l2),
        },
    }

    # Store genesis block reference in L2 storage
    l2_genesis_key = f"tew/{instance_id}/l2_genesis"
    _msg(
        {
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": get_script_address(),
            "index": l2_genesis_key,
            "data": json.dumps(genesis_block_data),
        }
    )

    return {
        "status": "initialized",
        "message": f"L2 genesis initialized for instance {instance_id}",
        "chain_id": chain_id,
        "authority": authority,
        "genesis_height": 0,
    }


@l1_function
def say_hi(greeting: str, instance_id: str = "default"):
    """Send a greeting to L2 and store the response

    This demonstrates the complete flow:
    1. L1 sends message to L2
    2. L2 processes and returns response
    3. L1 stores the response
    """
    sender = get_executor_address()

    # Load L1 state from storage
    storage_key = f"tew/{instance_id}/l1"
    response = _query(
        {
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": get_script_address(),
            "index": storage_key,
        }
    )

    # Check if storage exists
    if "entry" not in response or "data" not in response["entry"]:
        raise Exception(
            f"L1 state not found at storage key {storage_key}. Initialize L1 first."
        )

    # Parse the stored data
    l1_snapshot = json.loads(response["entry"]["data"])
    l1 = create_l1_from_snapshot(l1_snapshot)

    # Send message to L2
    msg_id = l1.say_hi(sender, greeting)

    # Save updated state (with the new message in outgoing queue)
    _msg(
        {
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": get_script_address(),
            "index": storage_key,
            "data": json.dumps(asdict(l1)),
        }
    )

    return {
        "status": "message_sent",
        "sender": sender,
        "greeting": greeting,
        "message_id": msg_id,
    }


@l1_function
def get_stored_responses(instance_id: str = "default"):
    """Get all responses that L1 has stored from L2

    This allows us to verify that L1 received and stored L2's responses.
    """
    # Load L1 state from storage
    storage_key = f"tew/{instance_id}/l1"
    response = _query(
        {
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": get_script_address(),
            "index": storage_key,
        }
    )

    # Check if storage exists
    if "entry" not in response or "data" not in response["entry"]:
        raise Exception(
            f"L1 state not found at storage key {storage_key}. Initialize L1 first."
        )

    # Parse the stored data
    l1_snapshot = json.loads(response["entry"]["data"])
    l1 = create_l1_from_snapshot(l1_snapshot)

    return {
        "stored_responses": l1.stored_responses,
        "total_responses": len(l1.stored_responses),
    }


@l1_function
def process_l2_responses(l2_state_json: str, instance_id: str = "default"):
    """Process L2 responses by reading L2 state and updating L1

    This is called after L2 blocks are processed to read the responses
    and update L1 state accordingly. This function respects storage isolation -
    L2 cannot write to L1 storage, so L1 must explicitly read L2 state.
    """
    # Parse the L2 state
    l2_state = json.loads(l2_state_json)

    # Load L1 state from storage
    storage_key = f"tew/{instance_id}/l1"
    response = _query(
        {
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": get_script_address(),
            "index": storage_key,
        }
    )

    # Check if storage exists
    if "entry" not in response or "data" not in response["entry"]:
        raise Exception(
            f"L1 state not found at storage key {storage_key}. Initialize L1 first."
        )

    # Parse the stored data
    l1_snapshot = json.loads(response["entry"]["data"])
    # Recreate L1 with loaded state
    l1 = create_l1_from_snapshot(l1_snapshot)

    # Process responses from L2
    l2_responses = l2_state.get("response_queue", {})
    processed_count = 0

    for msg_id_str, resp_data in l2_responses.items():
        # Only process responses for messages that L1 sent and hasn't acknowledged
        if msg_id_str in l1.outgoing_queue:
            # Handle both old and new field names for compatibility
            response_content = resp_data.get("response_data", resp_data.get("response"))
            response: Response = {
                "msg_id": resp_data["msg_id"],
                "response_data": response_content,
            }
            l1.process_response(response)
            # Remove the original message since we got a response
            del l1.outgoing_queue[msg_id_str]
            processed_count += 1

    # Also process any new messages from L2
    l2_messages = l2_state.get("outgoing_queue", {})
    for msg_id_str, msg_data in l2_messages.items():
        # L1 should only process messages it hasn't seen yet
        # This is handled by on_l2_block method
        pass

    # Save updated L1 state
    l1_state_dict = asdict(l1)

    # Save to storage
    def save_l1_data(data):
        storage_key = f"tew/{instance_id}/l1"
        _msg(
            {
                "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
                "owner": get_script_address(),
                "index": storage_key,
                "data": json.dumps(data, default=str),
            }
        )

    save_l1_data(l1_state_dict)

    return {"processed_responses": processed_count, "l1_state": l1_state_dict}


@l1_function
def submit_l2_block(signed_l2_block_json: str, instance_id: str = "default"):
    """Public function that anyone can call to submit an L2 block to L1

    The submitter pays gas. Typically the L2 authority will submit, but anyone can.
    """
    # Parse the signed block
    signed_l2_block = json.loads(signed_l2_block_json)

    # Verify signature and basic validation
    try:
        signer, raw_msg = verify_signed_data(signed_l2_block)
    except Exception as e:
        raise Exception(f"Invalid L2 block signature: {e}")

    # Debug logging to understand structure
    print(f"DEBUG submit_l2_block: raw_msg keys = {list(raw_msg.keys())}")
    print(f"DEBUG submit_l2_block: raw_msg = {json.dumps(raw_msg, indent=2)}")

    # Parse the raw message to get block data
    data_field = raw_msg["data"]
    if isinstance(data_field, str):
        l2_block_data = json.loads(data_field)
    else:
        l2_block_data = data_field

    # Get app_domain from raw message (it's at the message level)
    app_domain = raw_msg.get("app_domain", "")

    # Check if this is wrapped in a TewBlockBody structure
    if (
        isinstance(l2_block_data, dict)
        and "signer" in l2_block_data
        and "data" in l2_block_data
    ):
        # This is a TewBlockBody wrapper, extract the actual block data
        inner_data = l2_block_data["data"]
        if isinstance(inner_data, str):
            l2_block_data = json.loads(inner_data)
        else:
            l2_block_data = inner_data

    # Debug logging to understand the structure
    print(f"DEBUG submit_l2_block: raw_msg app_domain = {raw_msg.get('app_domain')}")
    print(f"DEBUG submit_l2_block: extracted app_domain = {app_domain}")

    # Validate chain ID and app domain
    if l2_block_data["metadata"]["chain_id"] != f"tew-{instance_id}":
        raise Exception(f"Invalid chain_id for instance {instance_id}")
    if app_domain != "tew/block":
        raise Exception(f"Invalid app_domain '{app_domain}', expected 'tew/block'")

    # Load existing L1 state from storage
    storage_key = f"tew/{instance_id}/l1"
    response = _query(
        {
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": get_script_address(),
            "index": storage_key,
        }
    )

    # Check if storage exists
    if "entry" not in response or "data" not in response["entry"]:
        raise Exception(
            f"L1 state not found at storage key {storage_key}. Initialize L1 first."
        )

    # Parse the stored data
    l1_snapshot = json.loads(response["entry"]["data"])
    # Recreate L1 with loaded state
    l1 = create_l1_from_snapshot(l1_snapshot)

    # Process the L2 block
    accepted = l1.on_l2_block(l2_block_data)

    # Save L1 state if block was processed
    if accepted:
        l1_state_dict = asdict(l1)
        _msg(
            {
                "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
                "owner": get_script_address(),
                "index": storage_key,
                "data": json.dumps(l1_state_dict),
            }
        )
        return f"L2 block processed successfully, height: {l2_block_data['metadata']['height']}"
    else:
        return "L2 block valid but not processed (no new messages in sequence)"


# ==========================================
# L2 HELPER FUNCTIONS
# ==========================================
#
# Since the main L2 logic is now encapsulated in the L2 class,
# these functions are primarily for special operations that
# need to run outside the normal block processing flow.

# The L2_TX global is used by @l2_function decorator
L2_TX: SignedTewTx = {
    "body": {
        "messages": [
            {
                "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                "signer": "dys1..",
                "data": "{}",
                "app_domain": "tew/tx",
            }
        ],
        "memo": "",
        "timeout_height": "0",
        "extension_options": [],
        "non_critical_extension_options": [],
    },
    "auth_info": {
        "signer_infos": [],
        "fee": {"amount": [], "gas_limit": "200000", "payer": "", "granter": ""},
    },
    "signatures": [],
}


# ======================== TEW BLOCK BUILDING ========================


def build_next_block(
    block: SignedTewBlock,
    prev_block_meta: Metadata,
    block_hash: str,
) -> TewBlockBodyData:
    print("DEBUG: build_next_block starting")

    # Verify the block and get the decoded body
    print("DEBUG: About to verify_signed_block")
    signer_addr, block_body = verify_signed_block(block, prev_block_meta)
    print("DEBUG: verify_signed_block completed")
    print(f"DEBUG: signer_addr: {signer_addr}")
    # Check if block_body is what we expect
    if not isinstance(block_body, dict):
        print(f"ERROR: block_body is not a dict! It's: {block_body}")
    elif "data" not in block_body:
        print(f"ERROR: block_body has no 'data' key! Keys: {list(block_body.keys())}")
    else:
        print("DEBUG: block_body structure looks correct")
        print(
            f"DEBUG: block_body['data'] type is dict? {isinstance(block_body['data'], dict)}"
        )
        if isinstance(block_body["data"], dict):
            print(f"DEBUG: block_body['data'] keys: {list(block_body['data'].keys())}")
        else:
            print(
                f"DEBUG: block_body['data'] is not a dict, it's: {block_body['data']}"
            )

    # Initialize pending state from the pre_state in the block
    # Debug: Check the block_body structure
    print("DEBUG: About to initialize pending_state")

    # Extract the block data - it might be a string that needs parsing
    block_data = block_body["data"]
    if isinstance(block_data, str):
        print("DEBUG: block_data is a string, parsing JSON")
        block_data = json.loads(block_data)

    pre_state = block_data["pre_state"]
    print("DEBUG: pre_state loaded")
    pending_state = json.loads(  # deep.copy is not supported in dysvm
        json.dumps(pre_state, separators=(",", ":"), sort_keys=True, default=str),
    )
    print("DEBUG: pending_state initialized")
    pending_metadata = json.loads(  # deep.copy is not supported in dysvm
        json.dumps(
            block_data["metadata"],
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ),
    )

    def _set_next_authority(addr: str):
        """Propose the validator expected to sign the *next* block.

        This mutates the pending *metadata* (header), not the application
        state, because `next_authority` is a consensus-level field.
        """
        if not isinstance(addr, str) or len(addr) == 0:
            raise ValueError("empty authority address")
        if addr not in pending_state["account_numbers_by_address"]:
            raise ValueError(f"unknown validator address: {addr}")
        pending_metadata["next_authority"] = addr

    def _create_account(addr: str):
        """Create a new account if it doesn't already exist.

        Returns the assigned `account_number`.
        """
        # Fast path: already present
        acct_num = pending_state["account_numbers_by_address"].get(addr)
        if acct_num is not None:
            return acct_num

        # Allocate new account_number
        acct_num = pending_state["next_account_number"]
        pending_state["next_account_number"] = acct_num + 1

        # Insert bidirectional mappings
        pending_state["account_numbers_by_address"][addr] = acct_num
        pending_state["accounts_by_number"][str(acct_num)] = {
            "address": addr,
            "account_number": acct_num,
            "sequence": 0,
        }

        return acct_num

    def _print(*args, end="\n"):
        """Print to the captured stdout."""
        print(f"DEBUG: _print called with: arga={args} end={end}")
        # Convert args to strings using list comprehension (available in dyslang)
        str_args = [str(arg) for arg in args]
        chain_scope["captured_stdout"] += " ".join(str_args) + end

    def _get_msg():
        """Get the message of the current transaction being processed."""
        return chain_scope["tx"]["body"]["messages"][0]["data"]

    def _get_signer():
        """Get the signer of the current transaction being processed."""
        return chain_scope["tx"]["body"]["messages"][0]["signer"]

    def _get_current_authority():
        """Get the current authority address."""
        return pending_metadata["current_authority"]

    # Extract instance_id from metadata or use default
    instance_id = pending_metadata.get("instance_id", "default")

    # Load L1 queue state from DysonProtocol storage
    # Use helper function to avoid underscore method access
    def load_l1_data():
        storage_key = f"tew/{instance_id}/l1"
        try:
            response = _query(
                {
                    "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
                    "owner": get_script_address(),
                    "index": storage_key,
                }
            )

            # Check if storage exists
            if "entry" not in response or "data" not in response["entry"]:
                # Storage doesn't exist yet, return None (legitimate for genesis/first block)
                print(f"L1 storage response missing entry/data for {storage_key}")
                return None

            # Parse and return the stored data
            data = json.loads(response["entry"]["data"])
            print(f"L1 data loaded from storage: {list(data.keys())}")
            return data
        except Exception as e:
            # Handle the specific case where storage doesn't exist
            error_msg = str(e)
            if "NotFound" in error_msg and "doesn't exist" in error_msg:
                print(f"L1 storage not found at {storage_key} (expected for genesis)")
                return None
            # Re-raise any other exceptions
            raise

    l1_snapshot = load_l1_data()

    # L1 must exist for L2 to operate
    if l1_snapshot is None:
        raise ValueError(
            f"L1 state not found at tew/{instance_id}/l1. L1 must be initialized before L2 can build blocks."
        )

    l1 = create_l1_from_snapshot(l1_snapshot)
    print(
        f"L1 state loaded from storage, next_l2_message_id: {l1.queue_metadata.get('next_l2_message_id', 0)}"
    )

    # Load L2 queue state from block state
    l2_snapshot = pending_state.get("l2_queue_state")
    l2 = create_l2_from_snapshot(l2_snapshot)

    # ========================================
    # INTERNAL BLOCK BUILDING CONTEXT
    # ========================================
    # chain_scope is the internal context for block building (NOT for transaction execution).
    # It contains:
    # - References to L1/L2 instances and internal utility functions
    # - Captured stdout for debugging block processing
    # - Chain callbacks (wrapper functions that process blocks)
    #
    # Transaction execution happens in a separate sandboxed environment created by on_tx_wrapper
    chain_scope = {
        "block_body": block_body,
        "chain_callbacks": {},
        "dys_eval": dys_eval,  # Used for sandboxed tx evaluation
        "tx": None,  # Current transaction being processed
        "captured_stdout": "",
        "print": _print,
        "get_current_authority": _get_current_authority,
        "l1": l1,
        "l2": l2,
        "instance_id": instance_id,
    }

    def _get_l1():
        """Get the L1 queue instance."""
        return chain_scope["l1"]

    def _get_l2():
        """Get the L2 queue instance."""
        return chain_scope["l2"]

    def _process_queue_messages():
        """Process queue messages between L1 and L2.

        This happens at the start of on_begin_block before any transactions.
        Errors are logged but don't fail the block.
        """
        # Count messages before processing
        l1 = chain_scope["l1"]
        l2 = chain_scope["l2"]
        l1_outgoing_count = len(l1.outgoing_queue)
        l2_outgoing_count = len(l2.outgoing_queue)

        # L1 processes L2's messages
        try:
            if l2_outgoing_count > 0:
                # Process each message individually to invoke callbacks
                for msg_id, msg in sorted(l2.outgoing_queue.items()):
                    try:
                        # Invoke L2's on_queue_message through wrapper
                        chain_scope["chain_callbacks"]["on_queue_message"](msg)
                        # Process the message
                        l1.process_incoming_message(msg)
                    except Exception as e:
                        chain_scope["print"]("Error processing L2 message: " + str(e))

                # Don't clear messages yet - they'll be cleared when responses are seen
                chain_scope["print"](
                    "L1 processed " + str(l2_outgoing_count) + " messages from L2"
                )
        except Exception as e:
            # Log error but don't fail block
            chain_scope["print"]("Error in L1 processing L2 messages: " + str(e))

        # L1 processes L2's responses
        try:
            if len(l2.response_queue) > 0:
                # Process each response individually to invoke callbacks
                processed_responses = []
                for resp_id, resp in sorted(l2.response_queue.items()):
                    try:
                        # Invoke L2's on_queue_response through wrapper
                        chain_scope["chain_callbacks"]["on_queue_response"](resp)
                        # Process the response
                        l1.process_response(resp)
                        processed_responses.append(resp_id)
                    except Exception as e:
                        chain_scope["print"](
                            f"Error processing L2 response {resp_id}: {e}"
                        )

                # Only delete responses whose messages are no longer in L1's outgoing queue
                # (meaning L1 has seen and removed them)
                for resp_id in processed_responses:
                    if resp_id not in l1.outgoing_queue:
                        del l2.response_queue[resp_id]

                chain_scope["print"](
                    f"L1 processed {len(processed_responses)} responses from L2"
                )
        except Exception as e:
            # Log error but don't fail block
            chain_scope["print"](f"Error in L1 processing L2 responses: {e}")

        # L2 processes L1's messages
        try:
            if l1_outgoing_count > 0:
                # Process each message individually to invoke callbacks
                for msg_id, msg in sorted(l1.outgoing_queue.items()):
                    try:
                        # Invoke L2's on_queue_message through wrapper
                        chain_scope["chain_callbacks"]["on_queue_message"](msg)
                        # Process the message
                        l2.process_incoming_message(msg)
                    except Exception as e:
                        chain_scope["print"](
                            f"Error processing L1 message {msg_id}: {e}"
                        )

                # Don't clear messages yet - they'll be cleared when responses are seen
                chain_scope["print"](
                    f"L2 processed {l1_outgoing_count} messages from L1"
                )
        except Exception as e:
            # Log error but don't fail block
            chain_scope["print"](f"Error in L2 processing L1 messages: {e}")

        # L2 processes L1's responses
        try:
            if len(l1.response_queue) > 0:
                # Process each response individually to invoke callbacks
                processed_responses = []
                for resp_id, resp in sorted(l1.response_queue.items()):
                    try:
                        # Invoke L2's on_queue_response through wrapper
                        chain_scope["chain_callbacks"]["on_queue_response"](resp)
                        # Process the response
                        l2.process_response(resp)
                        processed_responses.append(resp_id)
                    except Exception as e:
                        chain_scope["print"](
                            f"Error processing L1 response {resp_id}: {e}"
                        )

                # Only delete responses whose messages are no longer in L2's outgoing queue
                # (meaning L2 has seen and removed them)
                for resp_id in processed_responses:
                    if resp_id not in l2.outgoing_queue:
                        del l1.response_queue[resp_id]

                chain_scope["print"](
                    f"L2 processed {len(processed_responses)} responses from L1"
                )
        except Exception as e:
            # Log error but don't fail block
            chain_scope["print"](f"Error in L2 processing L1 responses: {e}")

        # Clean up acknowledged messages
        # L1: Remove messages that have responses in L2's response queue
        l1_messages_to_remove = []
        for msg_id in l1.outgoing_queue:
            if msg_id in l2.response_queue:
                l1_messages_to_remove.append(msg_id)
        for msg_id in l1_messages_to_remove:
            del l1.outgoing_queue[msg_id]
            chain_scope["print"](f"L1 removed acknowledged message {msg_id}")

    def _send_l1_message(message_data):
        """Core L1 message sending with validation"""
        if not isinstance(message_data, dict):
            raise ValueError("Message data must be a dictionary")
        if len(json.dumps(message_data)) > 1000:  # Size limit
            raise ValueError("Message too large (max 1000 bytes)")

        # Get L1 queue from chain scope
        l1 = chain_scope.get("l1")
        if l1:
            return l1.send_message(message_data)
        raise ValueError("L1 queue not available")

    def _send_l2_message(message_data):
        """Core L2 message sending with validation"""
        if not isinstance(message_data, dict):
            raise ValueError("Message data must be a dictionary")
        if len(json.dumps(message_data)) > 1000:  # Size limit
            raise ValueError("Message too large (max 1000 bytes)")

        # Get L2 queue from chain scope
        l2 = chain_scope.get("l2")
        if l2:
            return l2.send_message(message_data)
        raise ValueError("L2 queue not available")

    # Note: tew_module is no longer needed since we don't have chain_logic
    # The internal functions are used directly by the wrapper functions

    # ========================================
    # USE L2 INSTANCE CALLBACKS WITH WRAPPERS
    # ========================================
    #
    # The L2 class contains the core chain logic methods (on_begin_block, on_tx, etc.)
    # However, these methods need access to block processing utilities like _print,
    # _process_queue_messages, etc. Since dyslang forbids setting attributes on instances
    # after creation, we use wrapper functions that:
    # 1. Have access to chain_scope and its utilities
    # 2. Call the corresponding L2 methods
    # 3. Add logging and debugging functionality

    # Create wrapper functions for L2 callbacks that have access to chain_scope
    def on_begin_block_wrapper(block):
        """Wrapper for L2.on_begin_block that provides access to chain utilities"""
        # Height is tracked in pending_metadata, not on L2 instance
        # Process queue messages automatically
        _process_queue_messages()

    def on_tx_wrapper(msg):
        """Wrapper for L2.on_tx that provides a sandboxed execution environment"""
        # Extract the transaction data
        tx_data = msg["data"].get("data", "")
        if not tx_data.strip():
            return None

        # Create a transaction-specific stdout collector
        tx_stdout = []

        def tx_print(*args, **kwargs):
            """Print function that collects output for this transaction only"""
            # Convert args to strings without generator expression
            str_args = []
            for arg in args:
                str_args.append(str(arg))
            output = " ".join(str_args)
            tx_stdout.append(output)

        # Create safe wrapper functions for L1/L2 access
        def safe_send_l1_message(text):
            """Safe wrapper for sending L1 messages from transactions

            Accepts only strings under 20 characters and automatically sets the sender.
            """
            if not isinstance(text, str):
                raise ValueError("Message must be a string")
            if len(text) >= 20:
                raise ValueError("Message too long (max 19 characters)")
            # Automatically create message dict with sender
            message_dict = {"sender": msg["signer"], "text": text}
            return _send_l1_message(message_dict)

        def safe_send_l2_message(text):
            """Safe wrapper for sending L2 messages from transactions

            Accepts only strings under 20 characters and automatically sets the sender.
            """
            if not isinstance(text, str):
                raise ValueError("Message must be a string")
            if len(text) >= 20:
                raise ValueError("Message too long (max 19 characters)")
            # Automatically create message dict with sender
            message_dict = {"sender": msg["signer"], "text": text}
            return _send_l2_message(message_dict)

        def safe_query_dyson(query_params):
            """Safe wrapper for querying Dyson storage from L2 transactions

            Sends a query request to L1 which executes dys._query() and returns the result.

            Args:
                query_params: Dict containing the query parameters, typically with @type field

            Returns:
                The message ID of the query request. The response will be available
                after L1 processes the message.

            Example:
                # Query storage
                msg_id = query_dyson({
                    "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
                    "owner": "dys1...",
                    "index": "my_key"
                })
            """
            if not isinstance(query_params, dict):
                raise ValueError("Query params must be a dict")

            # Create structured message for L1 to process
            query_message = {
                "type": "query_dyson",
                "params": query_params,
                "sender": msg["signer"],
            }
            return _send_l2_message(query_message)

        # Create minimal sandboxed eval scope for transaction
        tx_eval_scope = {
            "print": tx_print,
            "signer": msg["signer"],
            "send_l1_message": safe_send_l1_message,
            "send_l2_message": safe_send_l2_message,
            "query_dyson": safe_query_dyson,
        }

        # Evaluate the transaction code in sandboxed environment
        try:
            result = dys_eval(tx_data, scope=tx_eval_scope)
            # Append transaction stdout to the result
            if tx_stdout:
                chain_scope["captured_stdout"] += "\n".join(tx_stdout) + "\n"
            return result
        except Exception as e:
            # Still capture stdout even on error
            if tx_stdout:
                chain_scope["captured_stdout"] += "\n".join(tx_stdout) + "\n"
            raise Exception(f"Transaction execution failed: {e}")

    def on_end_block_wrapper():
        """Wrapper for L2.on_end_block"""
        l2.on_end_block()

    def on_queue_message_wrapper(message):
        """Wrapper for L2.on_queue_message with access to print"""
        # Debug what we're actually receiving
        _print("DEBUG: message=", message)
        _print("DEBUG: message is dict?", isinstance(message, dict))
        _print("DEBUG: message is str?", isinstance(message, str))
        # Add logging - safer approach for dyslang
        if isinstance(message, dict):
            msg_id = message.get("msg_id", "?")
            msg_text = message.get("message_data", "?")
        else:
            msg_id = "?"
            msg_text = str(message)
        _print("Processing queue message " + str(msg_id) + ": " + str(msg_text))
        # Call the original method
        l2.on_queue_message(message)

    def on_queue_response_wrapper(response):
        """Wrapper for L2.on_queue_response with access to print"""
        # Debug what we're actually receiving
        _print("DEBUG: response=", response)
        _print("DEBUG: response is dict?", isinstance(response, dict))
        _print("DEBUG: response is str?", isinstance(response, str))
        # Add logging - safer approach for dyslang
        if isinstance(response, dict):
            resp_id = response.get("msg_id", "?")
            resp_text = response.get("response_data", "?")
        else:
            resp_id = "?"
            resp_text = str(response)
        _print("Processing queue response " + str(resp_id) + ": " + str(resp_text))
        # Call the original method
        l2.on_queue_response(response)

    # Set up the callbacks using wrapper functions
    chain_scope["chain_callbacks"] = {
        "on_begin_block": on_begin_block_wrapper,
        "on_tx": on_tx_wrapper,
        "on_end_block": on_end_block_wrapper,
        "on_queue_message": on_queue_message_wrapper,
        "on_queue_response": on_queue_response_wrapper,
    }

    # Begin block processing
    _print("About to call on_begin_block")
    try:
        chain_scope["chain_callbacks"]["on_begin_block"](block_body)
        _print("on_begin_block completed successfully")
    except Exception as e:
        _print(f"Error in on_begin_block: {e}")
        print(f"Error in on_begin_block: {e}")
        raise

    # tx_results will be added to pending_state
    tx_results = []
    # verify all transactions, then execute them
    signed_txs = block_data["signed_txs"]
    _print(f"Number of transactions to process: {len(signed_txs)}")

    # Only process if there are transactions
    if len(signed_txs) > 0:
        _print(f"Processing {len(signed_txs)} transactions")
        for tx in signed_txs:
            tx_result = dict(
                signer=tx["body"]["messages"][0]["signer"],
                sequence=0,
                total_tx_count=0,
                block_height=0,
                result=None,
                error=None,
                stdout="",  # Initialize stdout field
            )
            try:
                # verify the transaction against current state & header
                tx_signer, tew_tx_msg = validate_tx(tx, block_data)

                chain_scope["tx"] = tx

                # The message is already decoded by validate_tx
                # tew_tx_msg has fields: signer, app_domain, data
                # The actual transaction data is in tew_tx_msg["data"]
                msg = tew_tx_msg

                # increment the global tx index
                pending_metadata["total_tx_count"] += 1

                # look up the signer's account_number and bump its sequence in state
                # Note: tx_signer was already verified by validate_tx
                acct_num = pending_state["account_numbers_by_address"].get(tx_signer)
                if acct_num is None:
                    raise ValueError(f"unknown account address: {tx_signer}")

                account = pending_state["accounts_by_number"][str(acct_num)]
                account["sequence"] += 1  # increment stored sequence

                # Call on_tx with the print function available
                result = chain_scope["chain_callbacks"]["on_tx"](msg)
                tx_result["result"] = result
                tx_result["stdout"] = chain_scope["captured_stdout"]
                tx_results.append(tx_result)
            except Exception as e:
                tx_result["error"] = str(e)
                tx_result["stdout"] = chain_scope["captured_stdout"]
                tx_results.append(tx_result)
    else:
        _print("No transactions to process")

    # End block processing
    chain_scope["chain_callbacks"]["on_end_block"]()

    # Refresh header fields for the *next* block expected by followers.
    if prev_block_meta is None:
        # Genesis case
        pending_metadata.update(
            {
                "height": 1,
                "current_authority": GENESIS_AUTH,
                "time": datetime.now(),
            },
        )
    else:
        # Normal case
        pending_metadata.update(
            {
                "height": prev_block_meta["height"] + 1,
                "current_authority": prev_block_meta["next_authority"],
                "time": datetime.now(),
            },
        )

    # If the L2 logic did not set `next_authority`, carry current forward.
    pending_metadata.setdefault("next_authority", pending_metadata["current_authority"])

    # Save updated queue states
    # L1 queue state persists to DysonProtocol storage (for real blocks)
    # AND in block state (for testing with query script run)
    l1_state_dict = asdict(chain_scope["l1"])

    # Always save L1 state in pending_state for testing
    pending_state["l1_queue_state"] = l1_state_dict

    # L2 queue state persists in block state
    # Include the current height from metadata in the L2 state
    l2_state_dict = asdict(chain_scope["l2"])
    l2_state_dict["current_height"] = pending_metadata["height"]
    pending_state["l2_queue_state"] = l2_state_dict
    pending_state["captured_stdout"] = chain_scope["captured_stdout"]

    return {
        "prev_signed_tew_block_hash": block_hash,
        "metadata": pending_metadata,
        "pre_state": pending_state,
        "signed_txs": block_data["signed_txs"],
        "tx_results": tx_results,
        "post_state": pending_state,
    }


# ======================== HELPER FUNCTIONS ========================


def verify_signed_block(
    block: SignedTewBlock,
    prev_meta: Metadata | None,
) -> tuple[str, TewBlockBody]:
    """1. Extract metadata from the canonical, un-mutated block body.
    2. Determine who *should* have signed this height.
    3. Ask Dyson to verify the signature bytes.
    4. Enforce header invariants (height, chain-id, authority rollover).
    5. Return the signer address and decoded block body.
    Raises ValueError on any mismatch.
    """
    # --- 1. verify signature and get raw message --------------------------
    signer_addr, raw_msg = verify_signed_data(block)  # already raises on bad sig

    # --- 2. parse TewBlockBody from raw message --------------------------
    # Create block_body structure
    block_body = {
        "signer": raw_msg["signer"],
        "app_domain": raw_msg.get("app_domain", ""),
        "data": None,  # Will be populated below
    }

    # Parse the data field which should be a JSON string
    data_field = raw_msg["data"]
    if isinstance(data_field, str):
        msg_body_data = json.loads(data_field)
    else:
        msg_body_data = data_field

    # Check what kind of data we have
    if isinstance(msg_body_data, dict):
        # Check if this is already TewBlockBodyData (has metadata field)
        if "metadata" in msg_body_data and "pre_state" in msg_body_data:
            # This is already TewBlockBodyData
            block_body["data"] = msg_body_data
        # Check if msg_body_data has the structure of a TewBlockBody (with signer, data, app_domain)
        elif "signer" in msg_body_data and "data" in msg_body_data:
            # This is a full TewBlockBody, extract its data field
            block_data = msg_body_data["data"]
            # The data field might be a JSON string that needs to be decoded
            if isinstance(block_data, str):
                block_body["data"] = json.loads(block_data)
            else:
                block_body["data"] = block_data
            # Also preserve the app_domain if present
            if "app_domain" in msg_body_data:
                block_body["app_domain"] = msg_body_data["app_domain"]
        else:
            # Unknown structure, assume it's TewBlockBodyData
            block_body["data"] = msg_body_data
    else:
        # Not a dict, not a valid structure
        raise ValueError(
            f"Expected msg_body_data to be dict after parsing, got: {msg_body_data}"
        )

    # Debug logging - let's see what block_body["data"] actually is
    print(f"DEBUG: block_body['data'] = {block_body['data']}")
    print(f"DEBUG: block_body['data'] is dict? {isinstance(block_body['data'], dict)}")

    # Ensure block_body["data"] is a dict at this point
    if not isinstance(block_body["data"], dict):
        raise ValueError(
            f"block_body['data'] must be a dict at this point, got: {block_body['data']}"
        )

    # Try accessing metadata in a safer way
    try:
        # Extract metadata from the decoded block body
        if "metadata" not in block_body["data"]:
            raise ValueError(
                f"block_body['data'] missing 'metadata' field. block_body['data'] = {block_body['data']}"
            )

        meta: Metadata = block_body["data"]["metadata"]
    except Exception as e:
        # Debug what went wrong
        raise ValueError(
            f"Failed to extract metadata. block_body['data'] = {block_body['data']}, error: {e}"
        )

    # --- 3. who *should* sign this block? -----------------------------------
    if prev_meta is None:  # genesis case
        expected_authority = GENESIS_AUTH
        if meta["height"] != 0:
            raise ValueError("genesis block must have height 0")
    else:
        # height & chain-id must advance deterministically
        if meta["height"] != prev_meta["height"] + 1:
            raise ValueError("non-monotonic height")
        if meta["chain_id"] != prev_meta["chain_id"]:
            raise ValueError("chain-id changed unexpectedly")

        expected_authority = prev_meta["next_authority"]

    # --- 4. verify signer matches expected authority ------------------------
    if signer_addr != expected_authority:
        raise ValueError(
            f"block signed by {signer_addr}, expected {expected_authority}",
        )

    # --- 5. header consistency checks ---------------------------------------
    if meta["current_authority"] != expected_authority:
        raise ValueError("metadata.current_authority mismatch")

    # sanity-check next_authority field (cannot be empty / null)
    if not meta.get("next_authority"):
        raise ValueError("metadata.next_authority must be non-empty")

    # --- 6. done — caller can now trust `meta` ------------------------------
    # Ensure block_body conforms to TewBlockBody structure
    if not isinstance(block_body["data"], dict):
        raise ValueError(
            f"block_body['data'] must be a dict, got: {block_body['data']}"
        )

    # Validate required fields for TewBlockBodyData
    required_fields = [
        "metadata",
        "pre_state",
        "signed_txs",
        "tx_results",
        "post_state",
        "prev_signed_tew_block_hash",
    ]
    missing_fields = []
    for field_name in required_fields:
        if field_name not in block_body["data"]:
            missing_fields.append(field_name)

    if missing_fields:
        raise ValueError(
            f"Missing required fields in block data: {missing_fields}. block_body['data'] = {block_body['data']}"
        )

    # Type cast to satisfy pyright - we've validated the structure
    tew_block_body: TewBlockBody = block_body  # type: ignore[assignment]
    return signer_addr, tew_block_body


def validate_tx(tx: SignedTewTx, block_data: TewBlockBodyData) -> tuple[str, TewTxMsg]:
    """Verify a signed TewTx using DysonProtocol's verify_data endpoint.
    Verify the account sequence is correct

    Returns:
        tuple[str, TewTxMsg]: (signer address, decoded TewTxMsg with TewTxMsgData)
    """
    # --- 1. verify signature and get raw message --------------------------
    signer, raw_msg = verify_signed_data(tx)  # already raises on bad sig

    # --- 2. parse TewTxMsg from raw message --------------------------
    # Debug logging
    print(f"DEBUG validate_tx: raw_msg keys = {list(raw_msg.keys())}")
    print(
        f"DEBUG validate_tx: raw_msg['data'] is str = {isinstance(raw_msg['data'], str)}"
    )

    # Create tx_msg structure
    tx_msg = {
        "signer": raw_msg["signer"],
        "app_domain": raw_msg.get("app_domain", ""),
        "data": None,  # Will be populated below
    }

    # Parse the data field which should be a JSON string or dict
    data_field = raw_msg["data"]
    if isinstance(data_field, str):
        # First parse gets us the tx_body_msg structure
        tx_body_msg = json.loads(data_field)
        print(f"DEBUG validate_tx: After first parse, tx_body_msg = {tx_body_msg}")

        # Check if this is a wrapped structure with signer and data
        if (
            isinstance(tx_body_msg, dict)
            and "signer" in tx_body_msg
            and "data" in tx_body_msg
        ):
            # This is the tx_body_msg wrapper, extract the actual TewTxMsgData
            tx_msg_data = tx_body_msg["data"]
            print(
                f"DEBUG validate_tx: Extracted tx_msg_data from wrapper = {tx_msg_data}"
            )
        else:
            # No wrapper, assume it's directly TewTxMsgData
            tx_msg_data = tx_body_msg
    else:
        tx_msg_data = data_field

    # This should be TewTxMsgData containing chain_id and sequence
    if not (
        isinstance(tx_msg_data, dict)
        and "chain_id" in tx_msg_data
        and "sequence" in tx_msg_data
    ):
        print(f"DEBUG validate_tx: tx_msg_data = {tx_msg_data}")
        print(
            f"DEBUG validate_tx: tx_msg_data is dict = {isinstance(tx_msg_data, dict)}"
        )
        raise ValueError("Invalid TewTxMsgData: missing chain_id or sequence")

    tx_msg["data"] = tx_msg_data

    # Extract the TewTxMsgData
    tx_body_data = tx_msg_data
    tx_sequence = tx_body_data["sequence"]
    tx_chain_id = tx_body_data["chain_id"]

    # chain-id must match the current block
    if tx_chain_id != block_data["metadata"]["chain_id"]:
        raise ValueError(
            f"tx chain_id {tx_chain_id} mismatches block {block_data['metadata']['chain_id']}",
        )

    state = block_data["pre_state"]

    # locate the on-chain account via the address → account_number index
    acct_num = state.get("account_numbers_by_address", {}).get(signer)
    if acct_num is None:
        raise ValueError(f"unknown account address: {signer}")

    account = state.get("accounts_by_number", {}).get(str(acct_num))
    if account is None:
        raise ValueError(f"account_number {acct_num} missing in state")

    account_sequence = account.get("sequence", 0)

    if tx_sequence != account_sequence:
        raise ValueError(
            f"tx sequence {tx_sequence} does not match account sequence {account_sequence}",
        )

    # Validate tx_msg conforms to TewTxMsg structure
    if not tx_msg.get("signer"):
        raise ValueError(f"tx_msg missing signer. Got: {tx_msg}")
    if "data" not in tx_msg or tx_msg["data"] is None:
        raise ValueError(f"tx_msg missing data. Got: {tx_msg}")
    if not isinstance(tx_msg["data"], dict):
        raise ValueError(f"tx_msg['data'] must be a dict, got: {tx_msg['data']}")

    # Validate TewTxMsgData fields
    if (
        "chain_id" not in tx_msg["data"]
        or "sequence" not in tx_msg["data"]
        or "data" not in tx_msg["data"]
    ):
        raise ValueError(
            f"tx_msg['data'] missing required fields (chain_id, sequence, data). Got: {tx_msg['data']}"
        )

    # Type cast to satisfy pyright - we've validated the structure
    tew_tx_msg: TewTxMsg = tx_msg  # type: ignore[assignment]
    return signer, tew_tx_msg


def verify_signed_data(
    data: Union[SignedTewBlock, SignedTewTx, dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    """Verify a signed message using DysonProtocol's verify_tx endpoint.

    Only verifies the signature and returns the raw message data.
    Does not parse or interpret the message contents.

    Args:
        data: A signed message dict with body, auth_info, and signatures

    Returns:
        tuple[str, dict[str, Any]]: (signer address, raw message from body.messages[0])

    Raises:
        Exception: If the signature verification fails
    """
    # Type validation - ensure we have required fields
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict, got: {data}")

    missing_fields = []
    for field_name in ["body", "auth_info", "signatures"]:
        if field_name not in data:
            missing_fields.append(field_name)

    if missing_fields:
        raise ValueError(f"Missing required fields: {missing_fields}. Data: {data}")
    try:
        # Verify the signature
        resp = _query(
            {
                "@type": "/dysonprotocol.script.v1.QueryVerifyTxRequest",
                "tx_json": json.dumps(data, separators=(",", ":")),
            },
        )
        signer = resp["signer"]

        # Return the raw message
        msg = data["body"]["messages"][0]
        return signer, msg
    except Exception as e:
        raise Exception(f"Failed to verify signed data: {e}")


# ======================== SIMPLE TEST FUNCTIONS ========================


def queue_demo():
    """Demo the queue functionality without storage - dyslang compatible"""
    # Create a new L1 instance using the factory function
    l1 = create_l1_from_snapshot()

    # Test sending a message
    sender = "test_user"
    greeting = "Hello from queue test!"
    message_id = l1.say_hi(sender, greeting)

    # Return the message ID and the content of the queue using asdict
    return {"message_id": message_id, "l1_state": asdict(l1)}
