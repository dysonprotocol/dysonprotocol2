"""
TEWL: Tool for External World Lookups

A commit-reveal consensus protocol for non-deterministic external data.
Providers bond funds, fulfill requests, and earn fees for correct answers.
"""

import json
import hashlib

from datetime import datetime, timezone, timedelta
from dys import (
    _msg,
    _query,
    dys_eval,
    get_attached_messages,
    get_executor_address,
    get_script_address,
    get_block_info,
    get_gas_consumed,
    get_gas_limit,
    emit_event,
    DysQueryException,
)


# =============================================================================
# Constants
# =============================================================================

SCRIPT_NAME = "tewl.dys"

# Storage index prefixes
PREFIX_PROVIDER = "p/"
PREFIX_REQUEST = "request/"   # request/{id}/state
PREFIX_RESPONSE = "response/" # response/{id}/provider/{addr}
PREFIX_STATE = "s/"

# Provider statuses
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"  # bond below minimum
STATUS_JAILED = "jailed"

# Request statuses
REQ_PENDING = "pending"
REQ_ACTIVE = "active"
REQ_REVEALING = "revealing"
REQ_RESOLVED = "resolved"
REQ_FAILED = "failed"


# =============================================================================
# Coin Helpers
# =============================================================================


def _get_attached_coins_to_script():
    """Get coins sent to this script via attached messages."""
    coins = []
    script_addr = get_script_address()
    for msg in get_attached_messages() or []:
        if (
            isinstance(msg, dict)
            and msg.get("@type") == "/cosmos.bank.v1beta1.MsgSend"
            and msg.get("to_address") == script_addr
        ):
            for c in msg.get("amount", []) or []:
                coins.append({"denom": c["denom"], "amount": c["amount"]})
    return coins


def _get_attached_udys():
    """Get total udys sent to this script via attached messages."""
    total = 0
    for coin in _get_attached_coins_to_script():
        if coin["denom"] == "udys":
            total += int(coin["amount"])
    return total


# =============================================================================
# Storage Helpers
# =============================================================================


def _storage_get(index):
    """Get value for index (JSON-decoded). Returns None if not found."""
    try:
        res = _query(
            {
                "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
                "owner": get_script_address(),
                "index": index,
            }
        )
        return json.loads(res["entry"]["data"])
    except DysQueryException as e:
        if "doesn't exist" in str(e) or "doesn\\'t exist" in str(e):
            return None
        raise


def _storage_set(index, data):
    """Set data at index; JSON-encoded."""
    return _msg(
        {
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": get_script_address(),
            "index": index,
            "data": json.dumps(data, default=str),
        }
    )


def _storage_delete(indexes):
    """Delete storage entries by indexes."""
    return _msg(
        {
            "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
            "owner": get_script_address(),
            "indexes": indexes,
        }
    )


def _storage_list(prefix):
    """List storage entries by prefix."""
    res = _query(
        {
            "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
            "owner": get_script_address(),
            "index_prefix": prefix,
        }
    )
    entries = res.get("entries", [])
    return [{"index": e["index"], "data": json.loads(e["data"])} for e in entries]


# =============================================================================
# State Management
# =============================================================================


def _get_state():
    """Get global state or initialize defaults."""
    state = _storage_get(PREFIX_STATE + "global")
    if state is None:
        state = {
            "next_request_id": 1,
            "min_bond": "100",  # 100 udys
            "active_request_id": None,  # currently active request
            "commit_timeout_seconds": 30,
            "reveal_timeout_seconds": 30,
        }
    return state


def _set_state(state):
    """Save global state."""
    return _storage_set(PREFIX_STATE + "global", state)


# =============================================================================
# Participation Helpers (for early phase transitions)
# =============================================================================


def _all_active_providers_committed(request_id):
    """Check if all active providers have committed."""
    active = get_active_providers()
    if not active:
        return False
    active_addrs = {p["address"] for p in active}
    providers = _get_response_providers(request_id)
    committed = {addr for addr, data in providers.items() if "commit_hash" in data}
    return active_addrs == committed


def _all_committed_providers_revealed(request_id):
    """Check if all committed providers have revealed."""
    providers = _get_response_providers(request_id)
    committed = {addr for addr, data in providers.items() if "commit_hash" in data}
    if not committed:
        return False
    revealed = {addr for addr, data in providers.items() if "response" in data}
    return committed == revealed


# =============================================================================
# Provider Management (Task 37-1)
# =============================================================================


def _provider_index(address):
    return PREFIX_PROVIDER + address


def get_provider(address):
    """Get provider by address. Returns None if not registered."""
    return _storage_get(_provider_index(address))


def deposit_bond():
    """
    Deposit bond as a provider. Creates provider if not exists.

    Caller must attach MsgSend with udys to script address.

    Returns:
        Provider record
    """
    caller = get_executor_address()
    state = _get_state()
    min_bond = int(state["min_bond"])

    # Get deposit from attached messages
    deposit_amount = _get_attached_udys()
    if deposit_amount <= 0:
        raise ValueError("attach MsgSend with udys to deposit")

    # Get or create provider
    provider = get_provider(caller)
    if provider is None:
        provider = {
            "address": caller,
            "bond": "0",
            "reputation": {"total": 0, "correct": 0, "slashed": 0},
            "status": STATUS_INACTIVE,
            "registered_at": get_block_info()["height"],
        }

    # Update bond
    new_bond = int(provider["bond"]) + deposit_amount
    provider["bond"] = str(new_bond)

    # Update status based on bond level
    if new_bond >= min_bond and provider["status"] == STATUS_INACTIVE:
        provider["status"] = STATUS_ACTIVE

    _storage_set(_provider_index(caller), provider)
    emit_event("provider_deposit", f"{caller}:{deposit_amount}")

    return provider


def withdraw_bond(amount):
    """
    Withdraw bond. Active providers can withdraw down to min_bond.
    Inactive providers can withdraw all.

    Args:
        amount: Amount to withdraw (e.g., "1000000udys")

    Returns:
        Withdrawal details
    """
    caller = get_executor_address()
    provider = get_provider(caller)

    if provider is None:
        raise ValueError(f"not registered: {caller}")

    if provider["status"] == STATUS_JAILED:
        raise ValueError("cannot withdraw while jailed")

    # Parse amount
    if not amount.endswith("udys"):
        raise ValueError("amount must be in udys")
    withdraw_amount = int(amount[:-4])

    current_bond = int(provider["bond"])
    if withdraw_amount > current_bond:
        raise ValueError(f"withdraw {withdraw_amount} exceeds bond {current_bond}")

    state = _get_state()
    min_bond = int(state["min_bond"])
    new_bond = current_bond - withdraw_amount

    # Active providers must keep min_bond
    if provider["status"] == STATUS_ACTIVE and new_bond < min_bond:
        raise ValueError(f"active provider must keep minimum bond {min_bond}")

    # Transfer back to provider
    _msg(
        {
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": get_script_address(),
            "to_address": caller,
            "amount": [{"denom": "udys", "amount": str(withdraw_amount)}],
        }
    )

    # Update or delete provider
    if new_bond == 0:
        _storage_delete([_provider_index(caller)])
        emit_event("provider_withdrawn", caller)
        return {"address": caller, "withdrawn": str(withdraw_amount), "remaining": "0"}

    provider["bond"] = str(new_bond)

    # Update status if bond falls below minimum
    if new_bond < min_bond and provider["status"] == STATUS_ACTIVE:
        provider["status"] = STATUS_INACTIVE

    _storage_set(_provider_index(caller), provider)
    emit_event("provider_withdraw", f"{caller}:{withdraw_amount}")

    return {
        "address": caller,
        "withdrawn": str(withdraw_amount),
        "remaining": str(new_bond),
    }


def list_providers():
    """List all registered providers."""
    entries = _storage_list(PREFIX_PROVIDER)
    return [e["data"] for e in entries]


def get_active_providers():
    """List providers with active status."""
    providers = list_providers()
    return [p for p in providers if p["status"] == STATUS_ACTIVE]


# =============================================================================
# Request Management (Task 37-2)
# =============================================================================


def _request_state_index(request_id):
    """Index for request state: request/{id}/state"""
    return f"{PREFIX_REQUEST}{request_id:06d}/state"


def _response_provider_index(request_id, provider):
    """Index for provider commit/reveal: response/{id}/provider/{addr}"""
    return f"{PREFIX_RESPONSE}{request_id:06d}/provider/{provider}"


def _response_provider_prefix(request_id):
    """Prefix for listing all providers of a request."""
    return f"{PREFIX_RESPONSE}{request_id:06d}/provider/"


def _get_response_providers(request_id):
    """Get all provider entries for a request as {address: data} dict."""
    prefix = _response_provider_prefix(request_id)
    entries = _storage_list(prefix)
    result = {}
    for e in entries:
        # Extract provider address from index (after last /)
        addr = e["index"].rsplit("/", 1)[-1]
        result[addr] = e["data"]
    return result


def get_request(request_id):
    """Get request by ID with commits/reveals reconstructed. Returns None if not found."""
    state = _storage_get(_request_state_index(request_id))
    if state is None:
        return None
    # Reconstruct commits and reveals from provider entries
    providers = _get_response_providers(request_id)
    commits = {}
    reveals = {}
    for addr, data in providers.items():
        if "commit_hash" in data:
            commits[addr] = {"hash": data["commit_hash"], "timestamp": data["commit_ts"]}
        if "response" in data:
            reveals[addr] = {"response": data["response"], "timestamp": data["reveal_ts"]}
    state["commits"] = commits
    state["reveals"] = reveals
    return state


def get_request_state(request_id):
    """Get raw request state without reconstructing commits/reveals."""
    return _storage_get(_request_state_index(request_id))


def list_requests(status=None):
    """List all requests, optionally filtered by status."""
    # List all state entries (they end with /state)
    entries = _storage_list(PREFIX_REQUEST)
    # Filter to only state entries
    state_entries = [e for e in entries if e["index"].endswith("/state")]
    requests = []
    for e in state_entries:
        req = e["data"]
        # For listing, we include empty commits/reveals (full reconstruction is expensive)
        req["commits"] = {}
        req["reveals"] = {}
        if status is None or req["status"] == status:
            requests.append(req)
    return requests


def _validate_scorer(scorer_code):
    """Validate scorer code defines a scorer(reveal, state) function."""
    if not isinstance(scorer_code, str) or not scorer_code.strip():
        raise ValueError("scorer must be non-empty string")

    # Check it defines scorer function (actual syntax check at execution time)
    if "def scorer(" not in scorer_code:
        raise ValueError("scorer must define 'def scorer(reveal, state)'")


def _validate_response_schema(schema):
    """Validate response_schema is a valid JSON Schema dict."""
    if not isinstance(schema, dict):
        raise ValueError("response_schema must be dict")

    # Basic JSON Schema structure check
    if "type" not in schema and "$ref" not in schema and "oneOf" not in schema:
        raise ValueError("response_schema must have 'type', '$ref', or 'oneOf'")


def create_request(
    prompt,
    response_schema,
    scorer,
    callback_script=None,
    callback_fn=None,
):
    """
    Create a new external data request.

    Caller must attach MsgSend with udys fee to script address.
    Timeouts are global (commit_timeout_blocks, reveal_timeout_blocks in state).
    Phases transition early if 100% of providers participate.

    Args:
        prompt: Human-readable query string
        response_schema: JSON Schema dict for validating provider responses
        scorer: Dyslang code defining scorer(reveals) -> {result, scores}
        callback_script: Optional script address to call with result
        callback_fn: Optional function name on callback_script

    Returns:
        Created request record
    """
    caller = get_executor_address()
    state = _get_state()

    # Get fee from attached messages
    fee = _get_attached_udys()
    if fee <= 0:
        raise ValueError("attach MsgSend with udys as fee")

    # Validate inputs
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be non-empty string")

    _validate_response_schema(response_schema)
    _validate_scorer(scorer)

    # Validate callback (both or neither)
    if (callback_script is None) != (callback_fn is None):
        raise ValueError(
            "callback_script and callback_fn must both be set or both None"
        )

    # Allocate request ID
    request_id = state["next_request_id"]
    state["next_request_id"] = request_id + 1
    _set_state(state)

    # Create request state (commits/reveals stored separately per provider)
    block_info = get_block_info()
    request_state = {
        "request_id": request_id,
        "requester": caller,
        "prompt": prompt,
        "response_schema": response_schema,
        "scorer": scorer,
        "fee": str(fee),
        "callback_script": callback_script,
        "callback_fn": callback_fn,
        "created_at": block_info["height"],
        "status": REQ_PENDING,
        "result": None,
        "scores": {},
    }

    _storage_set(_request_state_index(request_id), request_state)
    emit_event("request_created", f"{request_id}:{caller}:{fee}")

    # Try to activate if no active request
    _try_activate_next()

    # Return fresh copy (may have been activated)
    return get_request(request_id)


# =============================================================================
# Priority Queue (Task 37-3)
# =============================================================================


def get_pending_requests():
    """
    Get pending requests sorted by priority (fee DESC, created_at ASC).

    Returns:
        List of pending requests in priority order
    """
    requests = list_requests(REQ_PENDING)
    # Sort by fee descending, then created_at ascending
    requests.sort(key=lambda r: (-int(r["fee"]), r["created_at"]))
    return requests


def get_active_request():
    """
    Get the currently active request.

    Returns:
        Active request or None
    """
    state = _get_state()
    if state["active_request_id"] is None:
        return None
    return get_request(state["active_request_id"])


def _try_activate_next():
    """
    Activate the next pending request if no active request exists.

    Returns:
        Activated request or None
    """
    state = _get_state()

    # Already have active request
    if state["active_request_id"] is not None:
        return None

    # Get top pending request
    pending = get_pending_requests()
    if not pending:
        return None

    # Activate the top request (list_requests returns partial data, get fresh state)
    request_id = pending[0]["request_id"]
    request_state = get_request_state(request_id)
    now = datetime.now(timezone.utc)

    # Use global timeouts from state (in seconds)
    commit_timeout = state.get("commit_timeout_seconds", 30)
    reveal_timeout = state.get("reveal_timeout_seconds", 30)

    request_state["status"] = REQ_ACTIVE
    request_state["commit_deadline"] = (now + timedelta(seconds=commit_timeout)).isoformat()
    request_state["reveal_deadline"] = (
        now + timedelta(seconds=commit_timeout + reveal_timeout)
    ).isoformat()

    _storage_set(_request_state_index(request_id), request_state)

    # Update state
    state["active_request_id"] = request_id
    _set_state(state)

    emit_event("request_activated", str(request_id))
    return get_request(request_id)


def _deactivate_request(request_id, new_status):
    """
    Deactivate a request and try to activate the next one.

    Args:
        request_id: ID of request to deactivate
        new_status: New status (REQ_RESOLVED or REQ_FAILED)
    """
    state = _get_state()

    # Only deactivate if it's the active request
    if state["active_request_id"] != request_id:
        raise ValueError(f"request {request_id} is not active")

    # Update request status
    request_state = get_request_state(request_id)
    request_state["status"] = new_status
    _storage_set(_request_state_index(request_id), request_state)

    # Clear active request
    state["active_request_id"] = None
    _set_state(state)

    emit_event("request_deactivated", f"{request_id}:{new_status}")

    # Try to activate next
    _try_activate_next()


# =============================================================================
# Commit Phase (Task 37-4)
# =============================================================================


def commit(request_id, commit_hash):
    """
    Submit a commitment for the active request.

    Provider commits hash(json.dumps({request_id, response, salt, provider}))
    before revealing the actual response.

    Args:
        request_id: ID of the request to commit to
        commit_hash: Hash of the response (provider computes offline)

    Returns:
        Updated request record
    """
    caller = get_executor_address()
    now = datetime.now(timezone.utc)

    # Validate provider
    provider = get_provider(caller)
    if provider is None:
        raise ValueError(f"provider not registered: {caller}")
    if provider["status"] != STATUS_ACTIVE:
        raise ValueError(f"provider not active: {provider['status']}")

    # Validate request (read state only, not full request)
    request_state = get_request_state(request_id)
    if request_state is None:
        raise ValueError(f"request not found: {request_id}")
    if request_state["status"] != REQ_ACTIVE:
        raise ValueError(f"request not active: {request_state['status']}")

    # Check deadline
    commit_deadline = datetime.fromisoformat(
        request_state.get("commit_deadline", "2000-01-01T00:00:00+00:00")
    )
    if now >= commit_deadline:
        raise ValueError(
            f"commit deadline passed: {now.isoformat()} >= {commit_deadline.isoformat()}"
        )

    # Check not already committed (read provider entry)
    provider_entry = _storage_get(_response_provider_index(request_id, caller))
    if provider_entry is not None and "commit_hash" in provider_entry:
        raise ValueError(f"already committed: {caller}")

    # Validate commit_hash
    if not isinstance(commit_hash, str) or len(commit_hash) < 32:
        raise ValueError("commit_hash must be at least 32 chars")

    # Store commitment in provider entry
    _storage_set(
        _response_provider_index(request_id, caller),
        {"commit_hash": commit_hash, "commit_ts": now.isoformat()},
    )

    emit_event("commit", f"{request_id}:{caller}")

    # Check for early transition (100% participation)
    _transition_to_revealing(request_id, request_state)

    return get_request(request_id)


# =============================================================================
# Reveal Phase (Task 37-5)
# =============================================================================


def _compute_commit_hash(request_id, response, salt, provider):
    """Compute the expected commit hash for verification."""
    data = json.dumps(
        {
            "request_id": request_id,
            "response": response,
            "salt": salt,
            "provider": provider,
        },
        sort_keys=True,
    )
    return hashlib.sha256(data.encode()).hexdigest()


def _validate_against_schema(response, schema):
    """
    Simple JSON Schema validation.

    Returns True if valid, False otherwise.
    Note: This is a basic implementation; full JSON Schema is complex.
    """
    if not isinstance(schema, dict):
        return False

    schema_type = schema.get("type")

    # Handle type validation
    if schema_type == "object":
        if not isinstance(response, dict):
            return False
        # Check required properties
        required = schema.get("required", [])
        for prop in required:
            if prop not in response:
                return False
        # Check property types if defined
        properties = schema.get("properties", {})
        for prop, prop_schema in properties.items():
            if prop in response:
                if not _validate_against_schema(response[prop], prop_schema):
                    return False
        return True

    elif schema_type == "array":
        if not isinstance(response, list):
            return False
        items_schema = schema.get("items")
        if items_schema:
            for item in response:
                if not _validate_against_schema(item, items_schema):
                    return False
        return True

    elif schema_type == "string":
        return isinstance(response, str)

    elif schema_type == "number":
        return isinstance(response, (int, float)) and not isinstance(response, bool)

    elif schema_type == "integer":
        return isinstance(response, int) and not isinstance(response, bool)

    elif schema_type == "boolean":
        return isinstance(response, bool)

    elif schema_type == "null":
        return response is None

    # If no type specified but has oneOf/anyOf, assume valid for now
    if "oneOf" in schema or "anyOf" in schema or "$ref" in schema:
        return True

    # Unknown or missing type - be permissive
    return True


def _transition_to_revealing(request_id, request_state):
    """
    Transition request from active to revealing.
    Triggers when: commit_deadline passed OR 100% active providers committed.
    Sets reveal_deadline to 30s from transition time.

    Returns updated request_state.
    """
    now = datetime.now(timezone.utc)

    if request_state["status"] == REQ_ACTIVE:
        commit_deadline = datetime.fromisoformat(
            request_state.get("commit_deadline", "2000-01-01T00:00:00+00:00")
        )
        deadline_passed = now >= commit_deadline
        all_committed = _all_active_providers_committed(request_id)

        if deadline_passed or all_committed:
            request_state["status"] = REQ_REVEALING
            # Set reveal deadline to 30s from now (not from activation)
            state = _get_state()
            reveal_timeout = state.get("reveal_timeout_seconds", 30)
            request_state["reveal_deadline"] = (
                now + timedelta(seconds=reveal_timeout)
            ).isoformat()
            _storage_set(_request_state_index(request_id), request_state)
            reason = "full_participation" if all_committed else "timeout"
            emit_event("request_revealing", f"{request_id}:{reason}")

    return request_state


def reveal(request_id, response, salt):
    """
    Reveal a previously committed response.

    Args:
        request_id: ID of the request
        response: The actual response data (must match commit hash)
        salt: Random salt used in commit hash

    Returns:
        Updated request record
    """
    caller = get_executor_address()
    now = datetime.now(timezone.utc)

    # Get and validate request state
    request_state = get_request_state(request_id)
    if request_state is None:
        raise ValueError(f"request not found: {request_id}")

    # Transition to revealing if needed
    request_state = _transition_to_revealing(request_id, request_state)

    # Validate request status
    if request_state["status"] not in (REQ_ACTIVE, REQ_REVEALING):
        raise ValueError(f"request not in reveal phase: {request_state['status']}")

    # Check we're past commit deadline OR status is already REVEALING (early transition)
    commit_deadline = datetime.fromisoformat(
        request_state.get("commit_deadline", "2000-01-01T00:00:00+00:00")
    )
    if now < commit_deadline and request_state["status"] != REQ_REVEALING:
        raise ValueError(
            f"commit phase not ended: {now.isoformat()} < {commit_deadline.isoformat()}"
        )

    # Check we're before reveal deadline
    reveal_deadline = datetime.fromisoformat(
        request_state.get("reveal_deadline", "2000-01-01T00:00:00+00:00")
    )
    if now >= reveal_deadline:
        raise ValueError(
            f"reveal deadline passed: {now.isoformat()} >= {reveal_deadline.isoformat()}"
        )

    # Get provider entry (contains commit)
    provider_entry = _storage_get(_response_provider_index(request_id, caller))
    if provider_entry is None or "commit_hash" not in provider_entry:
        raise ValueError(f"no commit found for: {caller}")

    # Verify provider hasn't already revealed
    if "response" in provider_entry:
        raise ValueError(f"already revealed: {caller}")

    # Verify commit hash
    expected_hash = _compute_commit_hash(request_id, response, salt, caller)
    actual_hash = provider_entry["commit_hash"]
    if expected_hash != actual_hash:
        raise ValueError(
            f"hash mismatch: expected {expected_hash[:16]}..., got {actual_hash[:16]}..."
        )

    # Validate response against schema - reject invalid responses
    if not _validate_against_schema(response, request_state["response_schema"]):
        raise ValueError("response does not match schema")

    # Update provider entry with reveal
    provider_entry["response"] = response
    provider_entry["reveal_ts"] = now.isoformat()
    _storage_set(_response_provider_index(request_id, caller), provider_entry)

    emit_event("reveal", f"{request_id}:{caller}")
    return get_request(request_id)


# =============================================================================
# Finalize & Consensus (Task 37-6)
# =============================================================================

# Finalize phases
PHASE_SCORING = "scoring"
PHASE_SETTLING = "settling"
PHASE_COMPLETE = "complete"


def _run_scorer_step(scorer_code, reveal, state):
    """
    Run one step of the scorer in a sandboxed environment.

    Args:
        scorer_code: Dyslang code defining scorer(reveal, state) function
        reveal: Single {provider, response} dict
        state: Previous state or None if first

    Returns:
        New state dict, or raises on error
    """
    eval_code = scorer_code + "\n\nscorer_result = scorer(reveal_input, state_input)"

    scope = {"reveal_input": reveal, "state_input": state}
    module_dict = {"json": {"loads": json.loads, "dumps": json.dumps}}

    try:
        dys_eval(eval_code, scope=scope, module_dict=module_dict)
        return scope.get("scorer_result")
    except Exception as e:
        raise ValueError(f"scorer execution failed: {e}")


def _gas_budget_ok():
    """Check if we have at least 50% gas remaining."""
    consumed = get_gas_consumed()
    limit = get_gas_limit()
    return consumed < (limit * 0.5)


def _distribute_fees(request, scores):
    """
    Distribute fees to providers based on scores.

    Args:
        request: The request record
        scores: Dict of {provider: score}

    Returns:
        Dict of {provider: amount_received}
    """
    total_fee = int(request["fee"])
    script_addr = get_script_address()

    # Calculate total positive score
    total_score = sum(s for s in scores.values() if s > 0)
    if total_score <= 0:
        return {}

    distributions = {}
    for provider, score in scores.items():
        if score > 0:
            amount = int(total_fee * score / total_score)
            if amount > 0:
                # Send fee to provider
                _msg(
                    {
                        "@type": "/cosmos.bank.v1beta1.MsgSend",
                        "from_address": script_addr,
                        "to_address": provider,
                        "amount": [{"denom": "udys", "amount": str(amount)}],
                    }
                )
                distributions[provider] = amount

    return distributions


def _slash_provider(provider_addr, amount):
    """
    Slash a provider's bond.

    Args:
        provider_addr: Provider address to slash
        amount: Amount to slash in udys
    """
    provider = get_provider(provider_addr)
    if provider is None:
        return

    current_bond = int(provider["bond"])
    slash_amount = min(amount, current_bond)

    if slash_amount > 0:
        provider["bond"] = str(current_bond - slash_amount)
        provider["reputation"]["slashed"] += 1

        # Jail if bond falls below minimum
        state = _get_state()
        min_bond = int(state["min_bond"])
        if int(provider["bond"]) < min_bond:
            provider["status"] = STATUS_JAILED

        _storage_set(_provider_index(provider_addr), provider)
        emit_event("provider_slashed", f"{provider_addr}:{slash_amount}")


def _update_reputation(provider_addr, correct):
    """
    Update provider reputation.

    Args:
        provider_addr: Provider address
        correct: True if provider was correct
    """
    provider = get_provider(provider_addr)
    if provider is None:
        return

    provider["reputation"]["total"] += 1
    if correct:
        provider["reputation"]["correct"] += 1

    _storage_set(_provider_index(provider_addr), provider)


def _refund_escrow(request):
    """Refund the escrow fee to the requester."""
    fee = int(request["fee"])
    if fee > 0:
        _msg(
            {
                "@type": "/cosmos.bank.v1beta1.MsgSend",
                "from_address": get_script_address(),
                "to_address": request["requester"],
                "amount": [{"denom": "udys", "amount": str(fee)}],
            }
        )


def _invoke_callback(request, result):
    """
    Invoke the callback script with the result.

    Args:
        request: The request record
        result: The consensus result
    """
    if request["callback_script"] is None:
        return

    # Call the callback function on the callback script
    _msg(
        {
            "@type": "/dysonprotocol.script.v1.MsgExecScript",
            "script_address": request["callback_script"],
            "executor_address": get_script_address(),
            "function_name": request["callback_fn"],
            "args": json.dumps([request["request_id"], result]),
            "kwargs": "{}",
            "attached_messages": [],
        }
    )


def finalize(request_id):
    """
    Incrementally finalize a request.

    Triggers when: reveal_deadline passed OR 100% committed providers revealed.
    Gas-aware: processes reveals until 50% gas is consumed, then saves state.
    Can be called multiple times by anyone to continue processing.

    Scorer format: scorer(reveal, state) -> new_state
    - reveal = {"provider": str, "response": any}
    - state = previous state or None if first call
    - Returns new state dict; final state must have "result" and "scores" keys

    Args:
        request_id: ID of the request to finalize

    Returns:
        dict with "complete": bool and "request": request record
    """
    now = datetime.now(timezone.utc)

    # Get request state
    request_state = get_request_state(request_id)
    if request_state is None:
        raise ValueError(f"request not found: {request_id}")

    # Initialize finalize tracking fields if needed
    if "finalize_phase" not in request_state:
        request_state["finalize_phase"] = PHASE_SCORING
        request_state["scorer_state"] = None
        request_state["processed_providers"] = []

    # Check status
    if request_state["status"] not in (REQ_ACTIVE, REQ_REVEALING):
        if request_state["status"] in (REQ_RESOLVED, REQ_FAILED):
            return {"complete": True, "request": get_request(request_id)}
        raise ValueError(f"request not in reveal phase: {request_state['status']}")

    # Must be past reveal deadline OR all committed providers have revealed
    reveal_deadline = datetime.fromisoformat(
        request_state.get("reveal_deadline", "2000-01-01T00:00:00+00:00")
    )
    all_revealed = _all_committed_providers_revealed(request_id)
    if now < reveal_deadline and not all_revealed:
        raise ValueError(
            f"reveal deadline not reached: {now.isoformat()} < {reveal_deadline.isoformat()}"
        )

    # Get provider entries for commits/reveals
    providers = _get_response_providers(request_id)
    committed_providers = {addr for addr, data in providers.items() if "commit_hash" in data}
    revealed_providers = {addr for addr, data in providers.items() if "response" in data}

    # Get providers to process
    processed = set(request_state["processed_providers"])

    # Collect reveals not yet processed
    pending_reveals = []
    for addr, data in providers.items():
        if "response" in data and addr not in processed:
            pending_reveals.append({"provider": addr, "response": data["response"]})

    # Phase 1: Scoring - process reveals incrementally
    if request_state["finalize_phase"] == PHASE_SCORING:
        # No valid reveals at all
        if not pending_reveals and not processed:
            request_state["status"] = REQ_FAILED
            request_state["result"] = None
            request_state["finalize_phase"] = PHASE_SETTLING
            _storage_set(_request_state_index(request_id), request_state)
            emit_event("finalize_progress", f"{request_id}:no_valid_reveals")
            # Fall through to settling phase

        # Process reveals while gas budget ok
        scorer_error = None
        while pending_reveals and _gas_budget_ok():
            reveal_data = pending_reveals.pop(0)
            try:
                request_state["scorer_state"] = _run_scorer_step(
                    request_state["scorer"], reveal_data, request_state["scorer_state"]
                )
                request_state["processed_providers"].append(reveal_data["provider"])
            except Exception as e:
                scorer_error = str(e)
                break

        # Save progress
        _storage_set(_request_state_index(request_id), request_state)

        # Handle scorer error
        if scorer_error:
            request_state["status"] = REQ_FAILED
            request_state["result"] = None
            _refund_escrow(request_state)
            request_state["finalize_phase"] = PHASE_COMPLETE
            _storage_set(_request_state_index(request_id), request_state)
            _deactivate_request(request_id, REQ_FAILED)
            emit_event("request_failed", f"{request_id}:scorer_error")
            return {"complete": True, "request": get_request(request_id)}

        # Still have pending reveals - need more calls
        if pending_reveals:
            emit_event("finalize_progress", f"{request_id}:scoring")
            return {"complete": False, "request": get_request(request_id)}

        # Scoring complete - transition to settling
        request_state["finalize_phase"] = PHASE_SETTLING
        _storage_set(_request_state_index(request_id), request_state)

    # Phase 2: Settling - distribute fees, slash, callback
    if request_state["finalize_phase"] == PHASE_SETTLING:
        state = _get_state()
        slash_amount = int(int(state["min_bond"]) * 0.1)

        # Extract result and scores from scorer state
        scorer_state = request_state.get("scorer_state") or {}
        result = scorer_state.get("result")
        scores = scorer_state.get("scores", {})
        request_state["scores"] = scores

        # No consensus
        if result is None:
            request_state["status"] = REQ_FAILED
            request_state["result"] = None
            _refund_escrow(request_state)
            request_state["finalize_phase"] = PHASE_COMPLETE
            _storage_set(_request_state_index(request_id), request_state)
            _deactivate_request(request_id, REQ_FAILED)
            emit_event("request_failed", f"{request_id}:no_consensus")
            return {"complete": True, "request": get_request(request_id)}

        # Consensus reached
        request_state["status"] = REQ_RESOLVED
        request_state["result"] = result

        # Distribute fees
        _distribute_fees(request_state, scores)

        # Update reputations and slash
        for provider, score in scores.items():
            if score <= 0:
                _slash_provider(provider, slash_amount)
                _update_reputation(provider, False)
            else:
                _update_reputation(provider, True)

        # Slash non-revealers
        for provider in committed_providers - revealed_providers:
            _slash_provider(provider, slash_amount)

        # Invoke callback
        try:
            _invoke_callback(request_state, result)
        except Exception:
            emit_event("callback_failed", str(request_id))

        request_state["finalize_phase"] = PHASE_COMPLETE
        _storage_set(_request_state_index(request_id), request_state)
        _deactivate_request(request_id, REQ_RESOLVED)
        emit_event("request_resolved", f"{request_id}:{json.dumps(result)}")

    return {"complete": True, "request": get_request(request_id)}


# =============================================================================
# Admin Functions
# =============================================================================


def set_min_bond(amount):
    """
    Set minimum bond requirement (governance).

    Args:
        amount: Minimum bond in udys (e.g., "1000000")
    """
    caller = get_executor_address()
    script = get_script_address()

    # Only script owner can update
    if caller != script:
        raise ValueError("unauthorized")

    state = _get_state()
    state["min_bond"] = amount
    _set_state(state)

    emit_event("min_bond_updated", amount)
    return {"min_bond": amount}


def reset_all():
    """
    Delete all protocol data (providers, requests, state).
    Admin only. Use with caution - this is irreversible.

    Returns:
        Dict with counts of deleted entries
    """
    caller = get_executor_address()
    script = get_script_address()

    if caller != script:
        raise ValueError("unauthorized")

    # Collect all indexes to delete
    indexes = []

    # Delete all providers
    for entry in _storage_list(PREFIX_PROVIDER):
        indexes.append(entry["index"])

    # Delete all requests
    for entry in _storage_list(PREFIX_REQUEST):
        indexes.append(entry["index"])

    # Delete all responses (commit/reveal data)
    for entry in _storage_list(PREFIX_RESPONSE):
        indexes.append(entry["index"])

    # Delete state
    indexes.append(PREFIX_STATE + "global")

    # Delete in batches (storage delete has limits)
    deleted = 0
    while indexes:
        batch = indexes[:50]
        indexes = indexes[50:]
        _storage_delete(batch)
        deleted += len(batch)

    emit_event("reset_all", str(deleted))
    return {"deleted": deleted}


# =============================================================================
# Query Functions
# =============================================================================


def get_state():
    """Get current protocol state."""
    return _get_state()

