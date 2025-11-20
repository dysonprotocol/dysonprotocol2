"""
Whaleswap execution script - runs inside dyslang sandbox.

This script executes message sequences using MsgSudo and captures
comprehensive state before/after for invariant checking.

All setup (name registration, pool creation, etc.) happens here.

SEQUENTIAL EXECUTION WITH DYS_EVAL TEMPLATE SUBSTITUTION:

The execute_messages_sequentially() function allows you to chain messages
where results from one message can be used in subsequent messages.

Example:
    messages = [
        {"@type": "CreatePool", ...},  # Creates pool, returns pool_id
        {
            "@type": "MakeTrade",
            "pool_id": "{{ msg_0['pool_id'] }}",  # Uses pool_id from first message response
            # ... other fields
        }
    ]

The function:
1. Executes each message individually via MsgSudo
2. Stores complete response as msg_resp_{index} (JSON string)
3. Stores response dict as msg_{index} for template access
4. Uses dys_eval to evaluate {{ python_expression }} templates within dyslang runtime
5. Accumulates variables across all messages

Available template variables:
- msg_resp_0: Complete JSON response from first message
- msg_0: Response dict from first message (use msg_0['pool_id'])
- msg_1: Response dict from second message (use msg_1['offer_id'])
- etc.

dys_eval provides full Python expression evaluation within the dyslang sandbox.
"""

from dys import _msg, _query, get_executor_address, dys_eval
import json
import re


def query_balance(address, denom):
    """Query balance for an address and denom."""
    result = _query(
        {
            "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
            "address": address,
            "denom": denom,
        }
    )
    balance_obj = result.get("balance", {})
    return int(balance_obj.get("amount", "0"))


def set_zero_block_delays(authority):
    """
    Set block delays to 0 for fast testing in query exec.

    This allows positions to be opened and closed in the same transaction
    without waiting for blocks to advance. Essential for hypothesis testing.

    Args:
        authority: Gov module address

    Returns:
        MsgUpdateParams message dict
    """
    return {
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": authority,
        "params": {
            "pfand_per_offer": {"denom": "udys", "amount": "1"},
            "valuation_fee_pct": "0",
            "valuation_period": "3600s",
            "bid_timeout": "5s",
            "minimum_bid_percent_increase": "0",
            "max_note_length": 128,
            "block_delay_before_close": "0",
            "block_delay_before_liquidation": "0",
        },
    }


def dys_eval_template_substitution(json_str, template_vars):
    """
    Substitute {{ expression }} templates in JSON string using dys_eval.

    Args:
        json_str: JSON string containing {{ expression }} templates
        template_vars: Dictionary of variables available to expressions

    Returns:
        JSON string with templates substituted
    """
    # Log for debugging
    print(
        f"TEMPLATE_DEBUG: Starting substitution with template_vars keys: {list(template_vars.keys())}"
    )

    def replace_template(match):
        expression = match.group(1).strip()
        print(f"TEMPLATE_DEBUG: Evaluating expression: '{expression}'")
        print(f"TEMPLATE_DEBUG: Available vars: {template_vars}")

        try:
            result = dys_eval(expression, scope=template_vars)
            print(f"TEMPLATE_DEBUG: dys_eval result: {result}")
            if isinstance(result, list):
                final_result = result[-1]
                print(f"TEMPLATE_DEBUG: Using last element: {final_result}")
            else:
                final_result = result
            print(f"TEMPLATE_DEBUG: Final result: {final_result}")
            return str(final_result)
        except Exception as e:
            print(f"TEMPLATE_DEBUG: ERROR evaluating '{expression}': {e}")
            raise

    # Pattern to match {{ expression }} (non-greedy, allows nested braces)
    pattern = r"\{\{\s*(.*?)\s*\}\}"
    matches = re.findall(pattern, json_str)
    print(f"TEMPLATE_DEBUG: Found template matches: {matches}")

    result = re.sub(pattern, replace_template, json_str)
    print(f"TEMPLATE_DEBUG: Final substituted JSON: {result}")
    return result


def query_account_balance(address, denom):
    """Query account balance for a denom."""
    result = _query(
        {
            "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
            "address": address,
            "denom": denom,
        }
    )
    return int(result.get("balance", {}).get("amount", "0"))


def query_offer(offer_id):
    """Query single offer by ID."""
    result = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryOfferRequest",
            "offer_id": offer_id,
        }
    )
    return result.get("offer", {})


def query_offers_by_owner(owner, status=""):
    """Query offers by owner and optional status."""
    result = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByOwnerRequest",
            "owner": owner,
            "status": status,
        }
    )
    return result.get("offers", [])


def query_offers_by_denom(denom, role=""):
    """Query offers mentioning denom on have or want side."""
    result = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByDenomRequest",
            "denom": denom,
            "role": role,
        }
    )
    return result.get("offers", [])


def create_and_query_offers(
    messages, owner, status, have_denom, role, denoms, accounts, authority
):
    """
    Create offers via MsgSudo and then query OffersByOwner and OffersByDenom
    within the same script run to avoid cross-call persistence boundaries.

    Returns dict with keys: success, message_count, owner_offers, denom_offers
    """
    sudo_msg = {
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": authority,
        "messages": messages,
    }
    sudo_result = _msg(sudo_msg)
    ok = bool(sudo_result and sudo_result.get("results"))

    owner_res = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByOwnerRequest",
            "owner": owner,
            "status": status,
        }
    )
    denom_res = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryOffersByDenomRequest",
            "denom": have_denom,
            "role": role,
        }
    )
    return {
        "success": ok,
        "message_count": len(messages),
        "owner_offers": owner_res.get("offers", []),
        "denom_offers": denom_res.get("offers", []),
    }


def query_pool(pool_id):
    """Query single pool by ID."""
    result = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
            "pool_id": pool_id,
        }
    )
    return result.get("pool", {})


def query_pools_by_pair(base_denom, quote_denom):
    """Query pools for a denom pair."""
    result = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairRequest",
            "base_denom": base_denom,
            "quote_denom": quote_denom,
        }
    )
    return result.get("pools", [])


def query_pools_by_denom(denom):
    """Query pools containing a specific denom."""
    result = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByDenomRequest",
            "denom": denom,
        }
    )
    return result.get("pools", [])


def query_trade(trade_id):
    """Query single trade by ID."""
    result = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryTradeRequest",
            "trade_id": trade_id,
        }
    )
    return result.get("trade", {})


def query_trades_by_taker(taker):
    """Query trades by taker address."""
    result = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryTradesByTakerRequest",
            "taker": taker,
        }
    )
    return result.get("trades", [])


def query_trades_by_pool(pool_id):
    """Query trades for a pool."""
    result = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryTradesByPoolRequest",
            "pool_id": pool_id,
        }
    )
    return result.get("trades", [])


def create_and_query_trades(
    messages, taker, base_denom, quote_denom, denoms, accounts, authority
):
    """
    Execute trade-related messages (e.g., create pool, make trade) sequentially (handles
    templates like {{ msg_0['pool_id'] }}), then query TradesByTaker and TradesByPool
    within the same script run.

    Returns dict with keys: success, message_count, taker_trades, pool_trades
    """
    # Execute messages with template substitution support
    seq_res = execute_messages_sequentially(messages, denoms, accounts, authority)
    ok = bool(seq_res and seq_res.get("msg_results"))

    # Prefer pool_id from template_vars (MsgCreatePool response)
    pool_id = None
    tv = seq_res.get("template_vars", {}) if seq_res else {}
    if isinstance(tv, dict) and "msg_0" in tv and isinstance(tv["msg_0"], dict):
        pool_id = tv["msg_0"].get("pool_id")

    # Fallback: query by pair if pool_id not available
    if pool_id is None:
        pair_res = _query(
            {
                "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairRequest",
                "base_denom": base_denom,
                "quote_denom": quote_denom,
            }
        )
        pools = pair_res.get("pools", [])
        if isinstance(pools, list) and len(pools) > 0:
            pool_id = pools[0].get("pool_id")

    # Queries within same run
    taker_res = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryTradesByTakerRequest",
            "taker": taker,
        }
    )
    taker_trades = taker_res.get("trades", [])

    pool_trades = []
    if pool_id is not None:
        pool_res = _query(
            {
                "@type": "/dysonprotocol.whaleswap.v1.QueryTradesByPoolRequest",
                "pool_id": pool_id,
            }
        )
        pool_trades = pool_res.get("trades", [])

    return {
        "success": ok,
        "message_count": len(messages),
        "taker_trades": taker_trades,
        "pool_trades": pool_trades,
    }


def query_trades_by_offer(offer_id):
    """Query trades for an offer."""
    result = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryTradesByOfferRequest",
            "offer_id": offer_id,
        }
    )
    return result.get("trades", [])


def query_auction(auction_id):
    """Query single auction by ID."""
    result = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryAuctionRequest",
            "auction_id": auction_id,
        }
    )
    return result.get("auction", {})


def query_auctions_by_seller(seller):
    """Query auctions by seller address."""
    result = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryAuctionsBySellerRequest",
            "seller": seller,
        }
    )
    return result.get("auctions", [])


def query_position(position_id):
    """Query single position by ID."""
    result = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryPositionRequest",
            "position_id": position_id,
        }
    )
    return result.get("position", {})


def query_positions_by_user(user):
    """Query positions by user address."""
    result = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryPositionsByUserRequest",
            "user": user,
        }
    )
    return result.get("positions", [])


def query_positions_by_pool(pool_id):
    """Query positions for a pool."""
    result = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryPositionsByPoolRequest",
            "pool_id": pool_id,
        }
    )
    return result.get("positions", [])


def capture_balances(denoms, accounts):
    """Capture account balances."""
    account_balances = {}
    for account in accounts:
        account_balances[account] = {}
        for denom in denoms:
            account_balances[account][denom] = query_account_balance(account, denom)
    return account_balances


def execute_messages_with_sudo(messages, denoms, accounts, authority):
    """
    Execute a sequence of messages using MsgSudo.

    Args:
        messages: List of message dicts (includes setup + test operations)
        denoms: List of denoms to track
        accounts: List of account addresses to track
        authority: Authority address (gov module address)

    Returns:
        {
            "success": bool,
            "pre_balances": {...},
            "post_balances": {...},
            "message_count": int
        }
    """
    # Capture pre-state
    pre_balances = capture_balances(denoms, accounts)

    # Execute all messages in a single MsgSudo for atomicity
    sudo_msg = {
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": authority,
        "messages": messages,
    }

    result = _msg(sudo_msg)

    # Capture post-state
    post_balances = capture_balances(denoms, accounts)

    return {
        "success": True,
        "pre_balances": pre_balances,
        "post_balances": post_balances,
        "message_count": len(messages),
        "sudo_result": result,
    }


def execute_messages_with_conditional_close(messages, denoms, accounts, authority):
    """
    Execute messages sequentially with special handling for position lifecycle testing.
    The last message (final close) is only executed if the position is still active after the partial close.
    """
    # Execute messages up to the partial close (all but the last message)
    partial_result = execute_messages_sequentially(
        messages[:-1], denoms, accounts, authority
    )

    # Extract position_id from template_vars
    position_id = None
    template_vars = partial_result.get("template_vars", {})
    for key, value in template_vars.items():
        if isinstance(value, dict) and "position_id" in value:
            position_id = value["position_id"]
            break

    # Query position status
    position_active = False
    if position_id:
        position_query = query_position(position_id)
        status = position_query.get("status", "")
        position_active = status == "POSITION_STATUS_OPEN"

    # If position is still active, execute the final close
    if position_active:
        final_message = messages[-1]
        # Apply template substitution to final message
        if template_vars:
            final_json = json.dumps(final_message)
            final_json = dys_eval_template_substitution(final_json, template_vars)
            final_message = json.loads(final_json)

        # Execute final close
        final_sudo_result = execute_messages_with_sudo(
            [final_message], denoms, accounts, authority
        )

        # Merge results
        partial_result["msg_results"].append(final_sudo_result["sudo_result"])
        partial_result["message_count"] += 1

        # Re-query final state
        pool_id = None
        for key, value in template_vars.items():
            if isinstance(value, dict) and "pool_id" in value:
                pool_id = value["pool_id"]
                break

        if pool_id:
            final_queries = query_final_state(pool_id, position_id, accounts[0], denoms)
            partial_result["queries"] = final_queries

    return partial_result


def execute_messages_sequentially(messages, denoms, accounts, authority):
    """
    Execute messages sequentially, using results from previous messages to substitute
    variables in subsequent messages via string templates.

    Args:
        messages: List of message dicts with potential template variables like $pool_id.
                 Messages can include an optional "_extract_vars" field specifying
                 which fields from the response should be extracted as template variables.
        denoms: List of denoms to track
        accounts: List of account addresses to track
        authority: Authority address (gov module address)

    Returns:
        {
            "success": bool,
            "pre_balances": {...},
            "post_balances": {...},
            "message_count": int,
            "message_results": [...],
            "template_vars": {...}
        }
    """
    # Capture pre-state
    pre_balances = capture_balances(denoms, accounts)

    message_results = []
    template_vars = {}
    all_messages_succeeded = True

    for i, msg_template in enumerate(messages):
        print(
            f"SEQUENTIAL_DEBUG: Processing message {i}, template_vars keys: {list(template_vars.keys())}"
        )

        # Convert message to JSON string for template substitution
        msg_json = json.dumps(msg_template)
        print(f"SEQUENTIAL_DEBUG: Original message JSON: {msg_json}")

        # Apply dys_eval template substitution with accumulated variables
        if template_vars:
            msg_json = dys_eval_template_substitution(msg_json, template_vars)
        else:
            print("SEQUENTIAL_DEBUG: No template_vars available, skipping substitution")

        # Parse back to dict
        msg_dict = json.loads(msg_json)
        print(f"SEQUENTIAL_DEBUG: Final message dict: {msg_dict}")

        # Execute single message with MsgSudo
        sudo_msg = {
            "@type": "/dysonprotocol.script.v1.MsgSudo",
            "authority": authority,
            "messages": [msg_dict],
        }

        result = _msg(sudo_msg)

        # Store result for return
        message_results.append(result)

        # Check if this message succeeded
        message_succeeded = bool(result and "results" in result and result["results"])

        if message_succeeded:
            msg_result = result["results"][0]
            print(f"SEQUENTIAL_DEBUG: Message {i} result: {msg_result}")

            # Store complete response as JSON string
            template_vars[f"msg_resp_{i}"] = json.dumps(msg_result)

            # Store response as simple dict for template access
            template_vars[f"msg_{i}"] = msg_result

            print(
                f"SEQUENTIAL_DEBUG: Stored template_vars for msg_{i}: {template_vars[f'msg_{i}']}"
            )
        else:
            print(f"SEQUENTIAL_DEBUG: Message {i} failed - no results in response")
            all_messages_succeeded = False

    # Capture post-state
    post_balances = capture_balances(denoms, accounts)

    # Query final state for invariant checking
    queries = {}

    # Extract pool_id and position_id from template_vars
    pool_id = None
    position_id = None

    for key, value in template_vars.items():
        if isinstance(value, dict):
            if "pool_id" in value:
                pool_id = value["pool_id"]
            if "position_id" in value:
                position_id = value["position_id"]

    # Query pool if we have pool_id
    if pool_id:
        pool_query = _query(
            {
                "@type": "/dysonprotocol.whaleswap.v1.QueryPoolRequest",
                "pool_id": str(pool_id),
            }
        )
        queries["pool"] = pool_query.get("pool", {})

        # Query positions by pool
        positions_query = _query(
            {
                "@type": "/dysonprotocol.whaleswap.v1.QueryPositionsByPoolRequest",
                "pool_id": str(pool_id),
                "pagination": {"limit": "100"},
            }
        )
        queries["positions_by_pool"] = positions_query.get("positions", [])

    # Query module address dynamically using auth module
    module_addr_result = _query(
        {
            "@type": "/cosmos.auth.v1beta1.QueryModuleAccountByNameRequest",
            "name": "whaleswap",
        }
    )
    module_addr = (
        module_addr_result.get("account", {}).get("base_account", {}).get("address", "")
    )

    # Query balances for accounts and module
    if len(accounts) > 0:
        alice_addr = accounts[0]
        queries["alice_balance_base"] = query_balance(alice_addr, denoms[0])
        queries["alice_balance_quote"] = query_balance(alice_addr, denoms[1])

    # Query module balances
    if module_addr:
        queries["module_balance_base"] = query_balance(module_addr, denoms[0])
        queries["module_balance_quote"] = query_balance(module_addr, denoms[1])
    else:
        # Fallback to zero if module address not found
        queries["module_balance_base"] = 0
        queries["module_balance_quote"] = 0

    return {
        "success": all_messages_succeeded,
        "pre_balances": pre_balances,
        "post_balances": post_balances,
        "message_count": len(messages),
        "msg_results": message_results,
        "template_vars": template_vars,
        "queries": queries,
    }


def create_and_query_pools(
    messages, base_denom, quote_denom, denoms, accounts, authority
):
    """
    Create pools via _msg (MsgSudo) and immediately query PoolsByPair and PoolsByDenom
    within the same script run to avoid persistence boundaries between calls.

    Returns:
        {
            "success": bool,
            "message_count": int,
            "pair": [...],   # pools for (base, quote)
            "denom": [...],  # pools containing base_denom
        }
    """
    sudo_msg = {
        "@type": "/dysonprotocol.script.v1.MsgSudo",
        "authority": authority,
        "messages": messages,
    }
    sudo_result = _msg(sudo_msg)
    ok = bool(sudo_result and sudo_result.get("results"))

    pair_res = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairRequest",
            "base_denom": base_denom,
            "quote_denom": quote_denom,
        }
    )
    denom_res = _query(
        {
            "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByDenomRequest",
            "denom": base_denom,
        }
    )

    return {
        "success": ok,
        "message_count": len(messages),
        "pair": pair_res.get("pools", []),
        "denom": denom_res.get("pools", []),
    }


def query_final_state(pool_id, position_id, alice_addr, denoms):
    """
    Query final state for test verification.
    """
    base_denom, quote_denom = denoms[0], denoms[1]

    # Query pool
    pool = query_pool(pool_id)

    # Query positions by pool
    positions_by_pool = query_positions_by_pool(pool_id)

    # Query balances
    alice_balance_base = query_balance(alice_addr, base_denom)
    alice_balance_quote = query_balance(alice_addr, quote_denom)

    # Query module balances
    module_addr_result = _query(
        {
            "@type": "/cosmos.auth.v1beta1.QueryModuleAccountByNameRequest",
            "name": "whaleswap",
        }
    )
    module_addr = (
        module_addr_result.get("account", {}).get("base_account", {}).get("address", "")
    )

    module_balance_base = 0
    module_balance_quote = 0
    if module_addr:
        module_balance_base = query_balance(module_addr, base_denom)
        module_balance_quote = query_balance(module_addr, quote_denom)

    return {
        "pool": pool,
        "positions_by_pool": positions_by_pool,
        "alice_balance_base": alice_balance_base,
        "alice_balance_quote": alice_balance_quote,
        "module_balance_base": module_balance_base,
        "module_balance_quote": module_balance_quote,
    }


def check_position_invariants(pool_id, user_addr):
    """
    Check position-specific invariants after operations.

    Invariants:
    1. Pool total_borrowed == sum of all open position borrowed amounts
    2. All open positions have CR >= min_collateral_ratio
    3. All open positions have positive held and borrowed amounts
    4. Closed positions have zero borrowed and held

    Args:
        pool_id: Pool ID to check
        user_addr: User address to check positions for

    Returns:
        List of error strings (empty if all invariants pass)
    """
    errors = []

    # Query pool state
    pool = query_pool(pool_id)
    if not pool:
        errors.append(f"Pool {pool_id} not found")
        return errors

    # Query all positions for this pool
    positions = query_positions_by_pool(pool_id)

    # Calculate total borrowed from open positions
    total_borrowed_from_positions = {}
    for pos in positions:
        if pos.get("status") == "POSITION_STATUS_OPEN":
            borrowed = pos.get("borrowed", {})
            denom = borrowed.get("denom", "")
            amount = int(borrowed.get("amount", "0"))

            if denom:
                total_borrowed_from_positions[denom] = (
                    total_borrowed_from_positions.get(denom, 0) + amount
                )

            # Check position has positive amounts
            held = pos.get("held", {})
            held_amt = int(held.get("amount", "0"))
            if held_amt <= 0:
                errors.append(
                    f"Position {pos.get('position_id')} has non-positive held: {held_amt}"
                )

            if amount <= 0:
                errors.append(
                    f"Position {pos.get('position_id')} has non-positive borrowed: {amount}"
                )

    # Check pool total_borrowed matches sum of positions
    pool_total_borrowed = pool.get("total_borrowed", [])
    for coin in pool_total_borrowed:
        denom = coin.get("denom", "")
        pool_amt = int(coin.get("amount", "0"))
        pos_amt = total_borrowed_from_positions.get(denom, 0)

        if pool_amt != pos_amt:
            errors.append(
                f"Pool total_borrowed mismatch for {denom}: "
                f"pool={pool_amt}, positions={pos_amt}"
            )

    return errors
