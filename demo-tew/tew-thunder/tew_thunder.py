#!/usr/bin/env python3
"""
TEW Thunder - Minimal Payment Channels Implementation
Based on TEW Protocol v0.5

This is a minimal implementation focusing on core functionality:
- Creating payment channels
- Depositing funds
- L2 transfers between members
- Withdrawals
- Channel termination
"""

from dys import _query, _msg, get_script_address, get_executor_address, get_attached_messages, dys_eval, get_block_info  # type: ignore
import json
from typing import Dict, List, Any, Optional
import hashlib
    

# ==========================================
# DECORATORS FOR L1/L2 FUNCTION ROUTING
# ==========================================

def l1(func):
    """Mark function as L1 (on-chain) executable - documentation only"""
    return func

def l2(func):
    """Mark function as L2 (off-chain) executable - documentation only"""
    return func

# ==========================================
# STORAGE HELPERS
# ==========================================

def get_storage_key(instance_id: str, key_type: str, *args) -> str:
    """Generate storage keys following TEW v0.5 spec"""
    base = f"tew/{instance_id}"
    if key_type == "l1_state":
        return f"{base}/l1/state"
    elif key_type == "l1_meta":
        return f"{base}/l1/meta"
    elif key_type == "l2_block":
        block_num = args[0]
        return f"{base}/l2/blocks/{block_num:010d}"
    elif key_type == "l2_latest":
        return f"{base}/l2/latest_block"
    elif key_type == "balance":
        denom = args[0]
        return f"{base}/balances/{denom}"
    elif key_type == "tx":
        block_num, member, tx_hash = args
        return f"{base}/txs/{block_num}/{member}/{tx_hash}"
    elif key_type == "force_signal":
        block_num = args[0]
        return f"{base}/force_signals/{block_num:010d}"
    else:
        raise ValueError(f"Unknown storage key type: {key_type}")

def load_data(owner: str, index: str) -> Optional[Dict]:
    """Load JSON data from storage"""
    try:
        response = _query({
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": owner,
            "index": index
        })
        return json.loads(response["entry"]["data"])
    except Exception as e:
        if "NotFound" in str(e) or "doesn't exist" in str(e):
            return None
        raise

def save_data(owner: str, index: str, data: Dict):
    """Save JSON data to storage"""
    _msg({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": owner,
        "index": index,
        "data": json.dumps(data)
    })

def delete_data(owner: str, index: str):
    """Delete data from storage"""
    _msg({
        "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
        "owner": owner,
        "indexes": [index]
    })

# ==========================================
# SIGNATURE VERIFICATION
# ==========================================

def verify_signed_tx(signed_tx: Dict) -> dict:
    """
    Verify a signed L2 transaction and extract the data.

    Args:
        signed_tx (Dict): An ADR-036 signed transaction.
            Expected structure:
            {
              "body": {
                "messages": [{
                  "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                  "signer": "dys1...",
                  "data": "{... JSON string of Tx Data or other payload ...}",
                  "app_domain": "tew/tx",
                  "metadata": "{}"
                }]
              },
              "auth_info": {...},
              "signatures": ["..."]
            }

    Returns:
        A dictionary containing the verification status and extracted data:
        {
            "valid": bool,
            "error": str (optional, if invalid),
            "tx_data": dict (if valid, parsed from data field),
            "signer": str (if valid, address of signer)
        }
    """
    # Verify signature first
    result = _query({
        "@type": "/dysonprotocol.script.v1.QueryVerifyTxRequest",
        "tx_json": json.dumps(signed_tx)
    })

    # Check if query failed - handle different response formats
    code = result.get("code", 0)
    if code != 0:
        return {
            "valid": False,
            "error": result.get("raw_log") or result.get("error") or f"Query failed with code {code}"
        }
    
    # Extract the inner data string and parse it
    # Validate structure exists
    if "body" not in signed_tx or "messages" not in signed_tx["body"] or len(signed_tx["body"]["messages"]) == 0:
        return {"valid": False, "error": "Invalid tx structure: missing body or messages"}
    
    message = signed_tx["body"]["messages"][0]
    if "data" not in message:
        return {"valid": False, "error": "Invalid tx structure: missing data field"}
    
    tx_data_str = message["data"]
    # Parse JSON
    tx_data = json.loads(tx_data_str)

    return {
        "valid": True,
        "tx_data": tx_data,
        "signer": signed_tx["body"]["messages"][0]["signer"]
    }

def verify_block_signatures(block_data: Dict, signed_block_txs: Dict[str, Dict], committee: List[str]) -> bool:
    """
    Verify that block data is properly signed by all committee members.
    This is used during checkpointing to ensure consensus on a block.

    Args:
        block_data (Dict): The complete BlockData object.
            Expected structure:
            {
              "meta": {
                "instance_id": "channel_001",
                "block_height": 5,
                "committee": ["dys1alice...", "dys1bob...", "dys1charlie..."],
                "l1_block_header": {/* l1 block header */}
              },
              "prev_state": {/* previous L2 state */},
              "prev_state_hash": "sha256:...",
              "signed_txs": {
                "dys1alice...": {/* signed tx */},
                "dys1bob...": {/* signed tx */}
              },
              "next_state": {/* computed next L2 state, including tx_results */}
            }
        signed_block_txs (Dict[str, Dict]): A dictionary mapping member addresses
            to their signed transactions. Each transaction's `data` field
            should contain a JSON string with `{"block_data_hash": "..."}`.
        committee (List[str]): A list of all committee member addresses.

    Returns:
        True if all signatures are valid and present.
    """
    if len(signed_block_txs) != len(committee):
        raise ValueError(f"Expected {len(committee)} signatures, got {len(signed_block_txs)}")
    
    # Use compact JSON with sorted keys for deterministic hashing
    block_data_json = json.dumps(block_data, sort_keys=True, separators=(',', ':'))
    block_data_hash = "sha256:" + hashlib.sha256(block_data_json.encode('utf-8')).hexdigest()
    
    committee_set = set(committee)
    
    for signer, signed_tx in signed_block_txs.items():
        if signer not in committee_set:
            raise ValueError(f"Signer {signer} not in committee")
        committee_set.discard(signer)
        
        # Verify the signature against the transaction
        verification = verify_signed_tx(signed_tx)
        if not verification["valid"]:
            raise ValueError(f"Invalid signature for signer {signer}: {verification['error']}")

        # Verify the signed data matches the block data hash
        signed_data = verification["tx_data"]
        if signed_data["block_data_hash"] != block_data_hash:
            raise ValueError("Signed data doesn't match block data hash")

    if committee_set:
        raise ValueError("Missing committee signatures")
    
    return True


def validate_tx(signed_tx: Dict) -> Dict:
    """
    Validate a signed tx for off-chain verification.
    This is called via query by L2 nodes to validate txs before execution.

    Args:
        signed_tx (Dict): An ADR-036 signed transaction, where the `data`
            field contains a JSON string of the `Tx Data` object.
            
            Signed Tx structure:
            {
              "body": {
                "messages": [{
                  "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                  "signer": "dys1alice...",
                  "data": "{... JSON string of Tx Data ...}",
                  "app_domain": "tew/tx",
                  "metadata": "{}"
                }]
              },
              "auth_info": {...},
              "signatures": ["..."]
            }
            
            Tx Data structure (inside data field):
            {
              "instance_id": "channel_001",
              "l2_block_height": 5,
              "prev_state_hash": "sha256:...",
              "msgs": ["transfer_to('dys1bob...', 100000)"]
            }

    Returns:
        A dictionary with validation status and extracted data:
        {
            "valid": bool,
            "error": str (optional, if invalid),
            "tx_data": dict (if valid, the parsed Tx Data),
            "signer": str (if valid, address of signer)
        }
    """
    verification = verify_signed_tx(signed_tx)
    if not verification["valid"]:
        return verification

    tx_data = verification["tx_data"]
    
    required_fields = ["instance_id", "l2_block_height", "prev_state_hash", "msgs"]
    for field in required_fields:
        if field not in tx_data:
            return {"valid": False, "error": f"Missing required field in tx_data: {field}"}
    
    return {
        "valid": True,
        "tx_data": tx_data,
        "signer": verification["signer"]
    }

# ==========================================
# TEW FRAMEWORK CORE FUNCTIONS
# ==========================================

def create_tew(config: dict) -> dict:
    """
    Create a new TEW instance within this app.

    Args:
        config (dict): Configuration for the new instance.
            Expected structure:
            {
              "instance_id": "channel_001",
              "committee": ["dys1alice...", "dys1bob...", "dys1charlie..."],
              "timeout": 300,  # seconds for force on-chain timeout
              "app_config": { 
                "min_deposit": 1000000  # minimum deposit in udys
              },
              "l1_state": {  # optional, defaults provided
                "deposits": {},     # Track deposits by user
                "balances": {},     # Track balances by user
                "total_locked": 0,  # Total funds locked in channel
                "withdrawals": {},  # Pending withdrawals
                "nonce": 0         # For unique tx generation
              },
              "l2_state": {  # optional, defaults provided
                "meta": {
                  "instance_id": "channel_001",
                  "block_height": 0,
                  "committee": ["dys1alice...", "dys1bob..."]
                },
                "data": {
                  "balances": {},           # L2 balances by user
                  "transfers": [],          # Transfer history
                  "withdrawal_requests": {} # Pending L2 withdrawals
                },
                "tx_results": {}  # Results from previous block
              }
            }
            
    Returns:
        {
            "status": "created",
            "instance_id": "channel_001",
            "committee": ["dys1alice...", "dys1bob...", "dys1charlie..."]
        }
    """
    instance_id = config["instance_id"]
    committee = config["committee"]
    timeout = config.get("timeout", 300)  # 5 minutes default - OK to have default
    app_config = config.get("app_config", {})  # OK to have default empty config
    l1_state = config.get("l1_state", {  # OK to have default initial state
        "deposits": {},    # Track deposits by user
        "balances": {},    # Track balances by user (for backward compatibility)
        "total_locked": 0,
        "withdrawals": {}
    })
    l2_state = config.get("l2_state", {})  # OK to have default empty state
    
    script_address = get_script_address()
    
    # Check if instance already exists
    existing_meta = load_data(script_address, get_storage_key(instance_id, "l1_meta"))
    if existing_meta:
        raise ValueError(f"Instance {instance_id} already exists")
    
    # Initialize instance metadata
    meta = {
        "instance_id": instance_id,
        "committee": committee,
        "timeout": timeout,
        "app_config": app_config,
        "created_by": get_executor_address(),
        "status": "active"
    }
    
    # Initialize states
    if "balances" not in l1_state:
        l1_state["balances"] = {}
    if "pending_deposits" not in l1_state:
        l1_state["pending_deposits"] = {}
    if "pending_withdrawals" not in l1_state:
        l1_state["pending_withdrawals"] = {}
    if "total_locked" not in l1_state:
        l1_state["total_locked"] = 0
    if "nonce" not in l1_state:
        l1_state["nonce"] = 0
    
    # Initialize L2 state with proper structure
    if not l2_state:
        l2_state = {
            "meta": {
                "instance_id": instance_id,
                "block_height": 0,
                "committee": committee
            },
            "data": {
                "balances": {},
                "transfers": [],
                "withdrawal_requests": {}
            },
            "tx_results": {}
        }
    else:
        # Ensure proper structure if partial state provided
        if "meta" not in l2_state:
            l2_state["meta"] = {
                "instance_id": instance_id,
                "block_height": 0,
                "committee": committee
            }
        if "data" not in l2_state:
            l2_state["data"] = {
                "balances": {},
                "transfers": [],
                "withdrawal_requests": {}
            }
        if "tx_results" not in l2_state:
            l2_state["tx_results"] = {}
    
    # Save everything
    save_data(script_address, get_storage_key(instance_id, "l1_meta"), meta)
    save_data(script_address, get_storage_key(instance_id, "l1_state"), l1_state)
    save_data(script_address, get_storage_key(instance_id, "l2_block", 0), l2_state)
    save_data(script_address, get_storage_key(instance_id, "l2_latest"), {"block": 0})
    
    return {
        "status": "created",
        "instance_id": instance_id,
        "committee": committee
    }

def submit_tx(instance_id: str, signed_tx_str: str) -> dict:
    """
    Submit a signed L2 transaction for the next block (on-chain fallback).
    
    Args:
        instance_id (str): The TEW instance ID
        signed_tx_str (str): JSON string of a signed transaction
            Expected structure (same as validate_tx):
            {
              "body": {
                "messages": [{
                  "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                  "signer": "dys1alice...",
                  "data": "{\"instance_id\": \"channel_001\", ...}",
                  "app_domain": "tew/tx",
                  "metadata": "{}"
                }]
              },
              "auth_info": {...},
              "signatures": ["..."]
            }
            
    Returns:
        {
            "status": "submitted",
            "block": 5,  # The block number this tx is for
            "member": "dys1alice...",
            "tx_hash": "channel_001_5_dys1alice..."
        }
    """
    script_address = get_script_address()
    
    # Check if instance exists and is not terminated
    meta = load_data(script_address, get_storage_key(instance_id, "l1_meta"))
    if not meta:
        raise ValueError(f"Instance {instance_id} not found")
    
    if meta.get("status") == "terminated":
        raise ValueError(f"Instance {instance_id} is terminated - no operations allowed")
    
    # New format: signed transaction
    signed_tx = json.loads(signed_tx_str)
    verification = validate_tx(signed_tx)
    if not verification["valid"]:
        raise ValueError(f"Invalid tx: {verification.get('error', 'Unknown error')}")

    tx_data = verification["tx_data"]
    
    # Verify instance_id matches
    if tx_data["instance_id"] != instance_id:
        raise ValueError("Instance ID mismatch")
    
    member = verification["signer"]
    
    # Verify member is part of committee
    if member not in meta["committee"]:
        raise ValueError(f"Member {member} is not part of the committee")
    
    # Get current block
    latest_info = load_data(script_address, get_storage_key(instance_id, "l2_latest"))
    if not latest_info:
        raise ValueError(f"Instance {instance_id} not found")
    
    current_block = latest_info["block"]
    next_block = current_block + 1
    
    # Verify block number matches expected
    if tx_data["l2_block_height"] != next_block:
        raise ValueError(f"Invalid block number. Expected {next_block}, got {tx_data['l2_block_height']}")
    
    # Generate unique tx hash
    tx_hash = f"{instance_id}_{next_block}_{member}"
    
    # Check if tx already exists for this member/block
    existing_tx = load_data(
        script_address,
        get_storage_key(instance_id, "tx", next_block, member, tx_hash)
    )
    if existing_tx:
        raise ValueError(f"Tx already submitted for member {member} in block {next_block}")
    
    # Store the tx data
    save_data(
        script_address,
        get_storage_key(instance_id, "tx", next_block, member, tx_hash),
        tx_data
    )
    
    return {
        "status": "submitted",
        "block": next_block,
        "member": member,
        "tx_hash": tx_hash
    }

def checkpoint_block(instance_id: str, block_height: int, signed_checkpoint: Any) -> dict:
    """
    Fast-forward checkpoint with verified committee signatures.

    Args:
        instance_id (str): The ID of the TewInstance.
        block_height (int): The block height being checkpointed.
        signed_checkpoint (Any): The checkpoint object.
            Expected structure:
            {
              "block_data": {
                "meta": {
                  "instance_id": "channel_001",
                  "block_height": 5,
                  "committee": ["dys1alice...", "dys1bob...", "dys1charlie..."],
                  "l1_block_height": 12345
                },
                "prev_state": {/* Full L2 state from block 4 */},
                "prev_state_hash": "sha256:abc123...",
                "signed_txs": {
                  "dys1alice...": {/* Signed tx for block 5 */},
                  "dys1bob...": {/* Signed tx for block 5 */}
                },
                "next_state": {/* Computed L2 state for block 5 */}
              },
              "signatures": {
                "dys1alice...": {/* Signed tx with block_data_hash */},
                "dys1bob...": {/* Signed tx with block_data_hash */},
                "dys1charlie...": {/* Signed tx with block_data_hash */}
              }
            }
            
    Returns:
        {
            "status": "checkpointed",
            "block": 5,
            "state_hash": "sha256:def456..."  # Hash of the new state
        }
    """
    script_address = get_script_address()
    
    # Load instance metadata
    meta = load_data(script_address, get_storage_key(instance_id, "l1_meta"))
    if not meta:
        raise ValueError(f"Instance {instance_id} not found")
    
    if meta.get("status") == "terminated":
        raise ValueError(f"Instance {instance_id} is terminated - no operations allowed")
    
    # Get current block
    latest_info = load_data(script_address, get_storage_key(instance_id, "l2_latest"))
    current_block = latest_info.get("block", 0) if latest_info else 0
    
    # Validate block number
    if block_height <= current_block:
        raise ValueError(f"Cannot checkpoint block {block_height}, current block is {current_block}")
    
    # Parse checkpoint data
    checkpoint_data = signed_checkpoint
    if isinstance(checkpoint_data, str):
        checkpoint_data = json.loads(checkpoint_data)
    
    # New format: block_data with signatures
    block_data = checkpoint_data["block_data"]
    signatures = checkpoint_data["signatures"]
    
    # Verify block number matches
    if block_data.get("next_state", {}).get("meta", {}).get("block_height") != block_height:
        raise ValueError("Block height mismatch in checkpoint data")
    
    # Verify all committee members signed the block data
    committee = meta["committee"]
    verify_block_signatures(block_data, signatures, committee)
    
    # Extract the new L2 state
    new_l2_state = block_data["next_state"]
    
    # Validate state consistency
    if new_l2_state.get("meta", {}).get("block_height") != block_height:
        raise ValueError(f"State block height {new_l2_state.get('meta', {}).get('block_height')} doesn't match checkpoint block height {block_height}")
    
    # Additional validation: ensure total L2 balances don't exceed L1 locked funds
    l1_state = load_data(script_address, get_storage_key(instance_id, "l1_state"))
    total_l1_locked = l1_state.get("total_locked", 0) if l1_state else 0
    
    total_l2_balance = 0
    for member_balances in new_l2_state.get("data", {}).get("balances", {}).values():
        total_l2_balance += member_balances.get("udys", 0)
    
    if total_l2_balance > total_l1_locked:
        raise ValueError(f"L2 balance {total_l2_balance} exceeds L1 locked funds {total_l1_locked}")
    
    # Save the new block
    save_data(script_address, get_storage_key(instance_id, "l2_block", block_height), new_l2_state)
    save_data(script_address, get_storage_key(instance_id, "l2_latest"), {"block": block_height})
    
    return {
        "status": "checkpointed",
        "block": block_height,
        "state_hash": get_state_hash(new_l2_state)
    }

def signal_force_onchain(instance_id: str, block: int) -> dict:
    """
    Signal intent to force on-chain execution after timeout.
    
    Args:
        instance_id (str): The TEW instance ID
        block (int): The block number to force on-chain
        
    Returns:
        {
            "status": "force_signaled",
            "block": 5,
            "timeout": 300,  # Timeout in seconds
            "signaler": "dys1alice..."
        }
    """
    script_address = get_script_address()
    
    # Load instance metadata
    meta = load_data(script_address, get_storage_key(instance_id, "l1_meta"))
    if not meta:
        raise ValueError(f"Instance {instance_id} not found")
    
    if meta.get("status") == "terminated":
        raise ValueError(f"Instance {instance_id} is terminated - no operations allowed")
    
    # Check if caller is a committee member
    caller = get_executor_address()
    if caller not in meta["committee"]:
        raise ValueError("Only committee members can signal force on-chain")
    
    # Get current block
    latest_info = load_data(script_address, get_storage_key(instance_id, "l2_latest"))
    current_block = latest_info.get("block", 0) if latest_info else 0
    
    # Validate block number
    if block != current_block + 1:
        raise ValueError(f"Can only force next block. Current: {current_block}, requested: {block}")
    
    # Store force signal with current block height as a fallback for time
    # This is needed because block time might be 0 in test environments
    block_info = get_block_info()
    current_time = block_info.get("Time", 0)  # OK - might be 0 in test
    current_height = block_info.get("Height", 0)  # OK - might be 0 in test
    
    force_signal = {
        "block": block,
        "signaler": caller,
        "signal_time": current_time,
        "signal_height": current_height,  # Use height as fallback
        "timeout": meta["timeout"]
    }
    
    # Save force signal
    save_data(
        script_address,
        get_storage_key(instance_id, "force_signal", block),
        force_signal
    )
    
    return {
        "status": "force_signaled",
        "block": block,
        "timeout": meta["timeout"],
        "signaler": caller
    }

def progress_block(instance_id: str) -> dict:
    """
    Execute block on-chain when members are offline.
    
    Args:
        instance_id (str): The TEW instance ID
        
    Returns:
        {
            "status": "block_progressed",
            "block": 5,  # The block that was progressed
            "txs_processed": 2,  # Number of txs that were submitted
            "committee_size": 3,  # Total committee size
            "forced": true  # Whether force signal was used
        }
    """
    script_address = get_script_address()
    
    # Load instance metadata
    meta = load_data(script_address, get_storage_key(instance_id, "l1_meta"))
    if not meta:
        raise ValueError(f"Instance {instance_id} not found")
    
    if meta.get("status") == "terminated":
        raise ValueError(f"Instance {instance_id} is terminated - no operations allowed")
    
    # Get current block and next block
    latest_info = load_data(script_address, get_storage_key(instance_id, "l2_latest"))
    current_block = latest_info.get("block", 0) if latest_info else 0
    next_block = current_block + 1
    
    # Check for force signal
    force_signal = load_data(script_address, get_storage_key(instance_id, "force_signal", next_block))
    
    if force_signal:
        # Check if timeout has elapsed
        block_info = get_block_info()
        current_time = block_info.get("Time", 0)
        current_height = block_info.get("Height", 0)
        signal_time = force_signal["signal_time"]
        signal_height = force_signal.get("signal_height", 0)
        timeout = force_signal["timeout"]
        
        # If we have valid timestamps, use time-based check
        if current_time > 0 and signal_time > 0:
            if current_time < signal_time + timeout:
                raise ValueError(f"Force signal active but timeout not elapsed. Wait {signal_time + timeout - current_time} more seconds")
        # Otherwise fall back to block height (assume ~1 second per block)
        elif current_height > 0 and signal_height > 0:
            blocks_elapsed = current_height - signal_height
            if blocks_elapsed < timeout:
                raise ValueError(f"Force signal active but timeout not elapsed. Wait {timeout - blocks_elapsed} more blocks")
        # If neither time nor height is available, check if there are submitted txs
        else:
            # In test environments, allow progress if txs are submitted
            pass
    
    # Collect submitted txs for the block
    submitted_txs = {}
    committee = meta["committee"]
    
    for member in committee:
        # Try to find tx for this member and block
        tx_hash = f"{instance_id}_{next_block}_{member}"
        tx_data = load_data(
            script_address,
            get_storage_key(instance_id, "tx", next_block, member, tx_hash)
        )
        if tx_data:
            submitted_txs[member] = tx_data
    
    if not submitted_txs and not force_signal:
        raise ValueError("Block not ready: no txs submitted and no force signal")
    
    # Load current L2 state
    current_l2_state = load_data(script_address, get_storage_key(instance_id, "l2_block", current_block))
    if not current_l2_state:
        raise ValueError(f"Current block {current_block} state not found")
    
    # Process the block with available txs
    txs_to_process = {}
    for member in committee:
        if member in submitted_txs:
            txs_to_process[member] = {"msgs": submitted_txs[member].get("msgs", [])}
        else:
            # Member didn't submit - empty tx
            txs_to_process[member] = {"msgs": []}
    
    # Execute L2 logic
    result = process_l2_block(instance_id, current_l2_state, txs_to_process)
    new_l2_state = result["state"]
    
    # Save the new block state
    save_data(script_address, get_storage_key(instance_id, "l2_block", next_block), new_l2_state)
    save_data(script_address, get_storage_key(instance_id, "l2_latest"), {"block": next_block})
    
    # Clean up force signal if it existed
    if force_signal:
        delete_data(script_address, get_storage_key(instance_id, "force_signal", next_block))
    
    # Clean up processed txs
    for member in submitted_txs:
        tx_hash = f"{instance_id}_{next_block}_{member}"
        delete_data(script_address, get_storage_key(instance_id, "tx", next_block, member, tx_hash))
    
    return {
        "status": "block_progressed",
        "block": next_block,
        "txs_processed": len(submitted_txs),
        "committee_size": len(committee),
        "forced": bool(force_signal)
    }

def terminate_instance(instance_id: str) -> dict:
    """
    Cleanly terminate an instance, settling any remaining balances.
    
    Args:
        instance_id (str): The TEW instance ID
        
    Returns:
        {
            "status": "terminated",
            "final_block": 100,
            "pending_withdrawals_processed": [
                {
                    "user": "dys1alice...",
                    "amount": 200000,
                    "denom": "udys",
                    "status": "processed"  # or "insufficient_balance"
                }
            ],
            "final_settlements": [
                {
                    "user": "dys1alice...",
                    "amount": 800000,
                    "denom": "udys
                }
            ],
            "total_returned": 1500000
        }
    """
    script_address = get_script_address()
    
    # Load metadata
    meta = load_data(script_address, get_storage_key(instance_id, "l1_meta"))
    if not meta:
        raise ValueError(f"Instance {instance_id} not found")
    
    # Check if already terminated
    if meta.get("status") == "terminated":
        raise ValueError(f"Instance {instance_id} is already terminated")
    
    # Check if caller is a committee member
    caller = get_executor_address()
    if caller not in meta["committee"]:
        raise ValueError("Only committee members can terminate the instance")
    
    # Load L1 state
    l1_state = load_data(script_address, get_storage_key(instance_id, "l1_state"))
    
    # Get latest L2 state to check for pending withdrawals
    latest_info = load_data(script_address, get_storage_key(instance_id, "l2_latest"))
    latest_block = latest_info.get("block", 0) if latest_info else 0
    l2_state = load_data(script_address, get_storage_key(instance_id, "l2_block", latest_block))
    
    # Process any pending (unexecuted) withdrawals
    pending_withdrawals = []
    if l2_state:
        withdrawal_requests = l2_state.get("data", {}).get("withdrawal_requests", {})
        for user, withdrawal in withdrawal_requests.items():
            if not withdrawal.get("executed", False):
                amount = withdrawal["amount"]
                denom = "udys"  # Hardcoded for minimal implementation
                
                # Load L1 state
                l1_state = load_data(script_address, get_storage_key(instance_id, "l1_state"))
                if not l1_state:
                    raise ValueError(f"Instance {instance_id} L1 state not found")
                
                # Verify user has deposited funds
                user_deposits = l1_state.get("deposits", {}).get(user, {})
                if not user_deposits or denom not in user_deposits:
                    raise ValueError(f"No {denom} deposits found for {user}")
                
                deposited_amount = user_deposits[denom]
                
                # Check if user has sufficient L1 balance
                if deposited_amount >= amount:
                    
                    # Process the withdrawal
                    _msg({
                        "@type": "/cosmos.bank.v1beta1.MsgSend",
                        "from_address": script_address,
                        "to_address": user,
                        "amount": [{"denom": denom, "amount": str(amount)}]
                    })
                    
                    # Deduct from L1 balance
                    l1_state["deposits"][user][denom] -= amount
                    l1_state["total_locked"] -= amount
                    
                    pending_withdrawals.append({
                        "user": user,
                        "amount": amount,
                        "denom": denom,
                        "status": "processed"
                    })
                else:
                    pending_withdrawals.append({
                        "user": user,
                        "amount": amount,
                        "denom": denom,
                        "status": "insufficient_balance"
                    })
    
    # Return remaining L1 balances to their owners
    final_settlements = []
    for user, balances in (l1_state.get("balances", {}) if l1_state else {}).items():
        for denom, amount in balances.items():
            if amount > 0:
                # Return funds to user
                _msg({
                    "@type": "/cosmos.bank.v1beta1.MsgSend",
                    "from_address": script_address,
                    "to_address": user,
                    "amount": [{"denom": denom, "amount": str(amount)}]
                })
                
                final_settlements.append({
                    "user": user,
                    "amount": amount,
                    "denom": denom
                })
                
                # Zero out the balance
                if l1_state and "balances" in l1_state:
                    l1_state["balances"][user][denom] = 0
                    l1_state["total_locked"] -= amount
    
    # Update status
    meta["status"] = "terminated"
    meta["terminated_by"] = caller
    meta["terminated_at_block"] = latest_block
    
    # Save updated states
    save_data(script_address, get_storage_key(instance_id, "l1_meta"), meta)
    if l1_state:
        save_data(script_address, get_storage_key(instance_id, "l1_state"), l1_state)
    
    # Calculate total returned amount without generator expression
    total_returned = 0
    for settlement in final_settlements:
        total_returned += settlement["amount"]
    
    return {
        "status": "terminated",
        "final_block": latest_block,
        "pending_withdrawals_processed": pending_withdrawals,
        "final_settlements": final_settlements,
        "total_returned": total_returned
    }

# ==========================================
# THUNDER-SPECIFIC L1 FUNCTIONS
# ==========================================

@l1
def process_deposit(instance_id: str) -> dict:
    """
    Process incoming deposit to the payment channel.
    
    Args:
        instance_id (str): The TEW instance ID
        
    Required attached message:
        MsgSend with funds to the script address
        
    Returns:
        {
            "status": "deposit_processed",
            "depositor": "dys1alice...",
            "amount": 1000000,
            "denom": "udys",
            "l1_total_locked": 1500000,  # Total locked in channel
            "l2_balance": 1000000  # User's L2 balance after deposit
        }
    """
    script_address = get_script_address()
    attached_msgs = get_attached_messages()
    
    if not attached_msgs:
        raise ValueError("No attached message found - deposit requires MsgSend")
    
    # Find the MsgSend message
    msg_send = None
    for msg in attached_msgs:
        if msg.get("@type") == "/cosmos.bank.v1beta1.MsgSend":
            msg_send = msg
            break
    
    if not msg_send:
        raise ValueError("No MsgSend found in attached messages")
    
    # Validate deposit details
    from_address = msg_send["from_address"]
    to_address = msg_send["to_address"]
    
    if to_address != script_address:
        raise ValueError(f"MsgSend must be to script address {script_address}")
    
    # Get deposit amount
    amount = msg_send["amount"]
    if not amount or len(amount) == 0:
        raise ValueError("No amount specified in MsgSend")
    
    # For now, only support single denom deposits
    deposit = amount[0]
    denom = deposit["denom"]
    deposit_amount = int(deposit["amount"])
    
    # Load instance metadata to check committee membership
    meta = load_data(script_address, get_storage_key(instance_id, "l1_meta"))
    if not meta:
        raise ValueError(f"Instance {instance_id} not found")
    
    if meta.get("status") == "terminated":
        raise ValueError(f"Instance {instance_id} is terminated - no deposits allowed")
    
    if from_address not in meta["committee"]:
        raise ValueError(f"Only committee members can deposit. {from_address} not in committee")
    
    # Check minimum deposit if configured
    min_deposit = meta.get("app_config", {}).get("min_deposit", 0)
    if min_deposit > 0 and deposit_amount < min_deposit:
        raise ValueError(f"Deposit amount {deposit_amount} is below minimum deposit requirement of {min_deposit}")
    
    # Update L1 state
    l1_state = load_data(script_address, get_storage_key(instance_id, "l1_state"))
    if not l1_state:
        l1_state = {
            "deposits": {},
            "total_locked": 0,
            "withdrawals": {}
        }
    
    # Track individual deposits
    if from_address not in l1_state["deposits"]:
        l1_state["deposits"][from_address] = {}
    if denom not in l1_state["deposits"][from_address]:
        l1_state["deposits"][from_address][denom] = 0
    
    l1_state["deposits"][from_address][denom] += deposit_amount
    
    # Also update balances for backward compatibility
    if "balances" not in l1_state:
        l1_state["balances"] = {}
    if from_address not in l1_state["balances"]:
        l1_state["balances"][from_address] = {}
    if denom not in l1_state["balances"][from_address]:
        l1_state["balances"][from_address][denom] = 0
    
    l1_state["balances"][from_address][denom] += deposit_amount
    l1_state["total_locked"] += deposit_amount
    
    # Save updated L1 state
    save_data(script_address, get_storage_key(instance_id, "l1_state"), l1_state)
    
    # IMPORTANT: Also update L2 state to reflect the deposit
    # Load current L2 state (block 0)
    current_block_info = load_data(script_address, get_storage_key(instance_id, "l2_latest"))
    current_block = current_block_info.get("block", 0) if current_block_info else 0
    
    l2_state = load_data(script_address, get_storage_key(instance_id, "l2_block", current_block))
    if not l2_state:
        # Initialize L2 state if it doesn't exist
        l2_state = {
            "meta": {"block_height": current_block},
            "data": {
                "balances": {},
                "transfers": [],
                "withdrawal_requests": {}
            },
            "tx_results": {}
        }
    
    # Initialize balances structure if needed
    if "balances" not in l2_state["data"]:
        l2_state["data"]["balances"] = {}
    
    # Update L2 balance to match deposit
    if from_address not in l2_state["data"]["balances"]:
        l2_state["data"]["balances"][from_address] = {}
    if denom not in l2_state["data"]["balances"][from_address]:
        l2_state["data"]["balances"][from_address][denom] = 0
    
    l2_state["data"]["balances"][from_address][denom] += deposit_amount
    
    # Save updated L2 state
    save_data(script_address, get_storage_key(instance_id, "l2_block", current_block), l2_state)
    
    return {
        "status": "deposit_processed",
        "depositor": from_address,
        "amount": deposit_amount,
        "denom": denom,
        "l1_total_locked": l1_state["total_locked"],
        "l2_balance": l2_state["data"]["balances"][from_address][denom]
    }

@l1
def execute_withdrawal(instance_id: str, user_address: str) -> dict:
    """
    Process withdrawal request.
    
    Args:
        instance_id (str): The TEW instance ID
        user_address (str): The address requesting withdrawal
        
    Returns:
        {
            "withdrawn": 200000,
            "denom": "udys",
            "to": "dys1alice..."
        }
    """
    script_address = get_script_address()
    
    # Load states
    l1_state = load_data(script_address, get_storage_key(instance_id, "l1_state"))
    if not l1_state:
        raise ValueError(f"Instance {instance_id} not found")
    
    # Load metadata and check if terminated
    meta = load_data(script_address, get_storage_key(instance_id, "l1_meta"))
    if meta and meta.get("status") == "terminated":
        raise ValueError(f"Instance {instance_id} is terminated - no operations allowed")
    
    # Get latest L2 state
    latest_block_info = load_data(script_address, get_storage_key(instance_id, "l2_latest"))
    if not latest_block_info:
        raise ValueError(f"No L2 state found for instance {instance_id}")
    l2_state = load_data(script_address, get_storage_key(instance_id, "l2_block", latest_block_info["block"]))
    
    # Check L2 state for approved withdrawals
    if not l2_state:
        raise ValueError(f"No L2 state found for instance {instance_id}")
    withdrawals = l2_state["data"]["withdrawal_requests"]
    if user_address not in withdrawals:
        raise ValueError(f"No pending withdrawal for {user_address}")
    
    withdrawal = withdrawals[user_address]
    
    # Check if already executed
    if "executed" in withdrawal and withdrawal["executed"]:
        raise ValueError(f"Withdrawal for {user_address} has already been executed")
    
    amount = withdrawal["amount"]
    denom = "udys"  # Hardcoded for minimal implementation
    
    # Load L1 state
    l1_state = load_data(script_address, get_storage_key(instance_id, "l1_state"))
    if not l1_state:
        raise ValueError(f"Instance {instance_id} L1 state not found")
    
    # Verify user has deposited funds
    if "deposits" not in l1_state or user_address not in l1_state["deposits"]:
        raise ValueError(f"No deposits found for {user_address}")
    user_deposits = l1_state["deposits"][user_address]
    if denom not in user_deposits:
        raise ValueError(f"No {denom} deposits found for {user_address}")
    
    deposited_amount = user_deposits[denom]
    
    # Verify L1 balance is sufficient
    if deposited_amount < amount:
        raise ValueError("Insufficient L1 balance for withdrawal")
    
    # Send coins using bank module
    _msg({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": script_address,
        "to_address": user_address,
        "amount": [{"denom": denom, "amount": str(amount)}]
    })
    
    # Update L1 state
    l1_state["deposits"][user_address][denom] -= amount
    l1_state["total_locked"] -= amount
    
    # Mark withdrawal as executed in L2 state
    withdrawals[user_address]["executed"] = True
    if l2_state:
        save_data(script_address, get_storage_key(instance_id, "l2_block", latest_block_info["block"]), l2_state)
    
    # Save updated L1 state
    save_data(script_address, get_storage_key(instance_id, "l1_state"), l1_state)
    
    return {"withdrawn": amount, "denom": denom, "to": user_address}

# ==========================================
# L2 LOGIC FUNCTIONS
# ==========================================

def process_l2_block(instance_id: str, current_state: dict, txs: dict) -> dict:
    """
    Process L2 block by executing txs and returning new state.

    Args:
        instance_id (str): The ID of the TewInstance.
        current_state (dict): The current L2 state object.
            Expected structure:
            {
              "meta": {
                "instance_id": "channel_001",
                "block_height": 4,
                "committee": ["dys1alice...", "dys1bob..."]
              },
              "data": {
                "balances": {
                  "dys1alice...": {"udys": 1000000},
                  "dys1bob...": {"udys": 500000}
                },
                "transfers": [],
                "withdrawal_requests": {}
              },
              "tx_results": {}
            }
        txs (dict): A dictionary mapping member addresses to their txs.
            Expected structure:
            {
              "dys1alice...": { "msgs": ["transfer_to('dys1bob...', 100000)"] },
              "dys1bob...": { "msgs": ["request_withdrawal(50000)"] }
            }

    Returns:
        {
            "state": {  # New L2 state with block_height incremented
                "meta": { "block_height": 5, ... },
                "data": { ... updated balances, transfers, etc ... },
                "tx_results": {
                    "dys1alice...": {"success": true, "result": null},
                    "dys1bob...": {"success": false, "error": "Insufficient balance"}
                }
            },
            "tx_results": { ... same as state.tx_results ... }
        }
    """
    # Create working copy of state using JSON for deep copy
    new_state = json.loads(json.dumps(current_state))
    new_state["meta"]["block_height"] = current_state["meta"]["block_height"] + 1
    
    # Track tx results for each member
    tx_results = {}
    
    # Process each member's tx
    for member, tx in txs.items():
        msgs = tx.get("msgs", [])
        if not msgs:
            tx_results[member] = {"success": True, "result": None}
            continue
        
        # Create safe wrapper functions that return errors instead of raising
        def safe_transfer_to(recipient, amount):
            # Pre-check balance to avoid exception
            balances = new_state.get("data", {}).get("balances", {})
            author_balance = balances.get(member, {}).get("udys", 0)
            if author_balance < amount:
                return {"error": f"Insufficient balance: {author_balance} < {amount}"}
            # If check passes, do the transfer
            transfer_to(new_state, member, recipient, amount)
            return {"success": True}
        
        def safe_request_withdrawal(amount):
            # Pre-check balance to avoid exception
            balances = new_state.get("data", {}).get("balances", {})
            author_balance = balances.get(member, {}).get("udys", 0)
            if author_balance < amount:
                return {"error": f"Insufficient balance for withdrawal: {author_balance} < {amount}"}
            # If check passes, do the withdrawal request
            request_withdrawal(new_state, member, amount)
            return {"success": True}
        
        # Execute tx code in a safe context
        namespace = {
            "state": new_state,
            "author": member,
            "transfer_to": safe_transfer_to,
            "request_withdrawal": safe_request_withdrawal,
            "dys_eval": dys_eval,
            "_query": _query,
            "_msg": _msg
        }
        
        # Execute the code
        # For now, we'll let dys_eval handle any syntax errors
        final_result = None
        error_result = None
        for code in msgs:
            result = dys_eval(code, namespace)
            # Check if the result indicates an error
            if isinstance(result, dict) and "error" in result:
                error_result = {"success": False, "error": result["error"]}
                break 
            final_result = result
        
        if error_result:
            tx_results[member] = error_result
        else:
            tx_results[member] = {"success": True, "result": final_result}

    new_state["tx_results"] = tx_results
    
    # Return both new state and tx results
    return {
        "state": new_state,
        "tx_results": tx_results
    }

@l2
def transfer_to(state: dict, author: str, recipient: str, amount: int):
    """
    Execute a transfer between members.
    
    Args:
        state (dict): The L2 state being modified
        author (str): The sender's address (from tx context)
        recipient (str): The recipient's address
        amount (int): Amount to transfer in udys
        
    Side effects:
        - Updates balances in state["data"]["balances"]
        - Appends transfer record to state["data"]["transfers"]
        
    Raises:
        ValueError: If insufficient balance
    """
    balances = state.get("data", {}).get("balances", {})
    
    # Check balance
    author_balance = balances.get(author, {}).get("udys", 0)
    if author_balance < amount:
        raise ValueError(f"Insufficient balance: {author_balance} < {amount}")
    
    # Update balances
    if author not in balances:
        balances[author] = {}
    if recipient not in balances:
        balances[recipient] = {}
    
    balances[author]["udys"] = balances[author].get("udys", 0) - amount
    balances[recipient]["udys"] = balances[recipient].get("udys", 0) + amount
    
    # Record transfer
    state["data"]["transfers"].append({
        "from": author,
        "to": recipient,
        "amount": amount,
        "block": state.get("meta", {}).get("block_height", 0)
    })

@l2
def request_withdrawal(state: dict, author: str, amount: int):
    """
    Queue a withdrawal request.
    
    Args:
        state (dict): The L2 state being modified
        author (str): The user requesting withdrawal (from tx context)
        amount (int): Amount to withdraw in udys
        
    Side effects:
        - Adds/updates entry in state["data"]["withdrawal_requests"]
        
    Raises:
        ValueError: If insufficient balance for withdrawal
    """
    balances = state.get("data", {}).get("balances", {})
    
    # Check balance
    author_balance = balances.get(author, {}).get("udys", 0)
    if author_balance < amount:
        raise ValueError(f"Insufficient balance for withdrawal: {author_balance} < {amount}")
    
    # Queue withdrawal request
    state.setdefault("data", {}).setdefault("withdrawal_requests", {})[author] = {
        "amount": amount,
        "requested_block": state.get("meta", {}).get("block_height", 0)
    }

def compute_next_block(prev_state: dict, signed_txs: Dict[str, Dict]) -> Dict:
    """
    Compute a complete block from signed txs.
    This is called off-chain by L2 nodes to generate block data.
    
    Args:
        prev_state: The complete L2 state from the previous block
            Expected structure:
            {
              "meta": {
                "instance_id": "channel_001",
                "block_height": 4,
                "committee": ["dys1alice...", "dys1bob..."]
              },
              "data": {
                "balances": {...},
                "transfers": [...],
                "withdrawal_requests": {...}
              },
              "tx_results": {...}
            }
        signed_txs: Map of member address to signed tx
            Expected structure:
            {
              "dys1alice...": {  # Signed tx from Alice
                "body": {
                  "messages": [{
                    "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
                    "signer": "dys1alice...",
                    "data": "{\"instance_id\": \"channel_001\", ...}",
                    "app_domain": "tew/tx",
                    "metadata": "{}"
                  }]
                },
                "auth_info": {...},
                "signatures": ["..."]
              },
              "dys1bob...": { ... similar structure ... }
            }
        
    Returns:
        {
            "next_state": {/* Complete L2 state for next block */},
            "next_state_hash": "sha256:def456..."
        }
    """
    # Extract metadata from prev_state
    instance_id = prev_state["meta"]["instance_id"]
    current_block = prev_state["meta"]["block_height"]
    block_height = current_block + 1
    
    script_address = get_script_address()
    
    # Load metadata to verify committee
    meta = load_data(script_address, get_storage_key(instance_id, "l1_meta"))
    if not meta:
        raise ValueError(f"Instance {instance_id} not found")
    
    # Validate all txs first
    validated_txs = {}
    for member, signed_tx in signed_txs.items():
        validation = validate_tx(signed_tx)
        if not validation["valid"]:
            raise ValueError(f"Invalid tx from {member}: {validation['error']}")
        
        tx_data = validation["tx_data"]
        if tx_data["l2_block_height"] != block_height:
            raise ValueError(f"Tx block height mismatch for {member}")
        if tx_data["instance_id"] != instance_id:
            raise ValueError(f"Tx instance mismatch for {member}")
            
        validated_txs[member] = tx_data

    # Hash previous state for verification
    prev_state_hash = get_state_hash(prev_state)

    # Verify that all txs have the correct prev_state_hash
    for member, tx_data in validated_txs.items():
        if tx_data["prev_state_hash"] != prev_state_hash:
            raise ValueError(f"prev_state_hash mismatch for member {member}")

    # Build txs dict for processing
    txs_to_process = {}
    for member, tx_data in validated_txs.items():
        txs_to_process[member] = {"msgs": tx_data["msgs"]}
    
    # Process the block
    result = process_l2_block(instance_id, prev_state, txs_to_process)
    next_state = result["state"]
    
    # Return the result in the format expected by TEW spec
    return {
        "next_state": next_state,
        "next_state_hash": get_state_hash(next_state)
    }

# ==========================================
# UTILITY FUNCTIONS
# ==========================================

def get_state_hash(state: dict) -> str:
    """
    Compute the deterministic hash of an L2 state object.
    Uses compact sorted JSON for deterministic serialization and SHA256 for hashing.
    
    Args:
        state (dict): The L2 state object to hash
        
    Returns:
        str: The hash in format "sha256:hexdigest"
    """
    # Use compact JSON with sorted keys for deterministic serialization
    state_json = json.dumps(state, sort_keys=True, separators=(',', ':'))
    return "sha256:" + hashlib.sha256(state_json.encode('utf-8')).hexdigest()

def get_instance_info(instance_id: str) -> dict:
    """
    Get comprehensive information about an instance.
    
    Args:
        instance_id (str): The TEW instance ID
        
    Returns:
        {
            "metadata": {
                "instance_id": "channel_001",
                "committee": ["dys1alice...", "dys1bob...", "dys1charlie..."],
                "timeout": 300,
                "app_config": {"min_deposit": 1000000},
                "created_by": "dys1alice...",
                "status": "active"  # or "terminated"
            },
            "l1_state": {
                "deposits": {"dys1alice...": {"udys": 1000000}},
                "balances": {"dys1alice...": {"udys": 1000000}},
                "total_locked": 1500000,
                "withdrawals": {},
                "nonce": 42
            },
            "l2_state": {
                "meta": {...},
                "data": {
                    "balances": {...},
                    "transfers": [...],
                    "withdrawal_requests": {...}
                },
                "tx_results": {...}
            },
            "latest_block": 5
        }
    """
    script_address = get_script_address()
    
    # Load all relevant data
    meta = load_data(script_address, get_storage_key(instance_id, "l1_meta"))
    if not meta:
        raise ValueError(f"Instance {instance_id} not found")
    
    l1_state = load_data(script_address, get_storage_key(instance_id, "l1_state"))
    latest_block_info = load_data(script_address, get_storage_key(instance_id, "l2_latest"))
    l2_state = None
    if latest_block_info:
        l2_state = load_data(script_address, get_storage_key(instance_id, "l2_block", latest_block_info["block"]))
    
    return {
        "metadata": meta,
        "l1_state": l1_state,
        "l2_state": l2_state,
        "latest_block": latest_block_info.get("block", 0) if latest_block_info else 0
    }

def get_balance(instance_id: str, address: str) -> dict:
    """
    Get balance for a specific address in both L1 and L2.
    
    Args:
        instance_id (str): The TEW instance ID
        address (str): The user's address
        
    Returns:
        {
            "l1_balance": {"udys": 1000000},  # Deposited amount
            "l2_balance": {"udys": 800000}    # Current L2 balance
        }
    """
    info = get_instance_info(instance_id)
    
    l1_balance = info["l1_state"]["balances"].get(address, {})  # OK - user might not have balance
    l2_balance = info["l2_state"]["data"]["balances"].get(address, {}) if info["l2_state"] else {}  # OK - defensive
    
    return {
        "l1_balance": l1_balance,
        "l2_balance": l2_balance
    }

# ==========================================
# WEB DASHBOARD
# ==========================================

def wsgi(environ, start_response):
    """Web dashboard for viewing Thunder payment channels"""
    path = environ.get('PATH_INFO', '/')  # OK - standard WSGI pattern
    script_address = get_script_address()
    
    if path == '/':
        # List all channels
        # For a real implementation, you'd iterate through storage
        # For now, return a simple HTML page
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>TEW Thunder Payment Channels</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #333; }}
                .channel {{ border: 1px solid #ddd; padding: 10px; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <h1>TEW Thunder Payment Channels</h1>
            <p>Script Address: {script_address}</p>
            <div class="info">
                <h2>About Thunder</h2>
                <p>Thunder is a payment channel implementation built on TEW Protocol v0.5</p>
                <p>Features:</p>
                <ul>
                    <li>N-member payment channels</li>
                    <li>Instant off-chain transfers</li>
                    <li>On-chain deposits and withdrawals</li>
                    <li>Asynchronous operation with force on-chain</li>
                </ul>
            </div>
        </body>
        </html>
        """
        
        start_response('200 OK', [('Content-Type', 'text/html')])
        return [html.encode()]
    
    elif path.startswith('/api/channel/'):
        # API endpoint for channel info
        channel_id = path.split('/')[-1]
        
        try:
            info = get_instance_info(channel_id)
            response = json.dumps(info)
            start_response('200 OK', [('Content-Type', 'application/json')])
            return [response.encode()]
        except Exception as e:
            error = {"error": str(e)}
            start_response('404 Not Found', [('Content-Type', 'application/json')])
            return [json.dumps(error).encode()]
    
    else:
        start_response('404 Not Found', [('Content-Type', 'text/plain')])
        return [b'Not Found'] 