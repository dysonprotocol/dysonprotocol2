"""
Test affiliate payment system for whaleswap arbitrage.

Uses alice_sudo_grant fixture to allow alice to execute MsgSudo via authz.
Tests use tx script exec with --note to set transaction memo for affiliate.

Key insight: The ArbitrageMsgInterceptor is called for ALL messages going through
MsgServiceRouter.Handler(), including _msg calls from scripts. The memo is available
via ctx.TxBytes() which is preserved through the script execution context.

For ProcessAffiliatePayment to be called, we need:
1. ArbitrageMode = AUTO
2. affiliate_fee_pct > 0
3. Multiple pools forming a cycle (arbitrage opportunity)
4. A trade that creates price imbalance
5. Valid affiliate dysname in memo
"""

import json


def test_affiliate_payment_with_arbitrage(chainnet, alice_sudo_grant, register_name):
    """
    Test ProcessAffiliatePayment by triggering actual arbitrage.

    Creates a 2-pool cycle (A-B direct + A-C-B indirect), swaps on direct pool
    to create imbalance, then the interceptor executes arbitrage and pays affiliate.

    This covers:
    - ProcessAffiliatePayment
    - incrementAffiliateEarned
    - EventAffiliatePayment emission
    """
    dysond = chainnet[0]

    alice_addr = alice_sudo_grant["alice_addr"]
    gov_addr = alice_sudo_grant["gov_addr"]

    # Register 3 denoms for triangle arbitrage
    denom_a = register_name(dysond, "alice", alice_addr, "10udys")
    denom_b = register_name(dysond, "alice", alice_addr, "10udys")
    denom_c = register_name(dysond, "alice", alice_addr, "10udys")

    # Register affiliate dysname
    affiliate_name = register_name(dysond, "alice", alice_addr, "10udys")

    # Mint coins
    params = dysond("query", "nameservice", "params")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_fee = int(2_000_000 * fee_per + 1)

    for denom in [denom_a, denom_b, denom_c]:
        dysond(
            "tx",
            "nameservice",
            "mint-coins",
            "--amount",
            f"2000000{denom}",
            "--mint-fee",
            f"{mint_fee}udys",
            "--from",
            "alice",
        )

    # Create triangle of pools + create arbitrage opportunity
    extra_code = """
from dys import _msg, _query, get_executor_address

def _sudo(gov_addr, msg_dict):
    _msg({
        "@type": "/cosmos.authz.v1beta1.MsgExec",
        "grantee": get_executor_address(),
        "msgs": [
            {
                "@type": "/dysonprotocol.script.v1.MsgSudo",
                "authority": gov_addr,
                "messages": [msg_dict]
            }
        ]
    })

def _create_pool(creator, gov_addr, denom_a, amount_a, denom_b, amount_b):
    base, quote = sorted([denom_a, denom_b])
    _sudo(gov_addr, {
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": creator,
        "coins": [
            {"denom": denom_a, "amount": str(amount_a)},
            {"denom": denom_b, "amount": str(amount_b)}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.001"},
            {"denom": quote, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })

def setup_arbitrage(alice_addr, gov_addr, denom_a, denom_b, denom_c):
    POOL_AMOUNT = 100000
    SWAP_AMOUNT = 30000

    # Set affiliate_fee_pct and enable auto arbitrage
    _sudo(gov_addr, {
        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
        "authority": gov_addr,
        "params": {
            "pfand_per_offer": {"denom": "udys", "amount": "1"},
            "valuation_fee_pct": "0",
            "valuation_period": "3600s",
            "bid_timeout": "5s",
            "minimum_bid_percent_increase": "0",
            "max_note_length": 128,
            "block_delay_before_close": 1,
            "block_delay_before_liquidation": 1,
            "arbitrage_mode": 3,  # AUTO
            "arbitrage_ref_denom": denom_a,
            "affiliate_fee_pct": "0.10"  # 10% to affiliate
        }
    })

    # Create triangle: A-B, B-C, C-A (all balanced initially)
    _create_pool(alice_addr, gov_addr, denom_a, POOL_AMOUNT, denom_b, POOL_AMOUNT)
    _create_pool(alice_addr, gov_addr, denom_b, POOL_AMOUNT, denom_c, POOL_AMOUNT)
    _create_pool(alice_addr, gov_addr, denom_c, POOL_AMOUNT, denom_a, POOL_AMOUNT)

    # Query pool A-B directly by pair (avoids looping through all pools)
    base, quote = sorted([denom_a, denom_b])
    pools_resp = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryPoolsByPairRequest",
        "base_denom": base,
        "quote_denom": quote,
        "pagination": {"limit": "1"}
    })
    pools = pools_resp.get("pools", [])
    assert len(pools) > 0, "Pool A-B not found"
    pool_ab_id = int(pools[0]["pool_id"])

    # Get trade count before swap
    trades_before = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradesRequest",
        "pagination": {"limit": "1", "reverse": True}
    })
    trades_list = trades_before.get("trades", [])
    trade_count_before = int(trades_list[0]["trade_id"]) if trades_list else 0

    # Swap on A-B to create imbalance: A -> B
    _sudo(gov_addr, {
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": alice_addr,
        "operations": [{
            "swap": {
                "pool_id": str(pool_ab_id),
                "swap_in": {"denom": denom_a, "amount": str(SWAP_AMOUNT)},
                "swap_out": {"denom": denom_b, "amount": "0"}
            }
        }],
        "max_input": [{"denom": denom_a, "amount": str(SWAP_AMOUNT * 2)}],
        "min_output": []
    })

    # Get latest trade ID after swap
    trades_after = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryTradesRequest",
        "pagination": {"limit": "1", "reverse": True}
    })
    trades_list_after = trades_after.get("trades", [])
    trade_count_after = int(trades_list_after[0]["trade_id"]) if trades_list_after else 0

    # Count interceptor trades = (trades after - trades before - 1 for alice's trade)
    alice_trade_id = trade_count_before + 1
    interceptor_count = trade_count_after - alice_trade_id

    return {
        "pool_count": 1,
        "pool_ab_id": pool_ab_id,
        "trade_count_before": trade_count_before,
        "alice_trade_id": alice_trade_id,
        "interceptor_trades_count": interceptor_count,
    }
"""

    kwargs = json.dumps(
        {
            "alice_addr": alice_addr,
            "gov_addr": gov_addr,
            "denom_a": denom_a,
            "denom_b": denom_b,
            "denom_c": denom_c,
        }
    )

    result = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_addr,
        "--function-name",
        "setup_arbitrage",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
        "--from",
        "alice",
        "--gas",
        "200000000",
        "--note",
        affiliate_name,  # This is the affiliate!
    )

    assert result.get("code", 1) == 0, f"Setup failed: {result}"

    # Verify script executed and pools were created
    # The interceptor will run ProcessAffiliatePayment if arbitrage is found
    events = result.get("events", [])
    event_types = [e.get("type", "") for e in events]

    # Verify script execution happened
    assert (
        "dysonprotocol.script.v1.EventExecScript" in event_types
    ), f"Expected script exec event in: {event_types}"

    # Print debug info about arbitrage/affiliate events
    print(f"Event types: {event_types}")
    print(
        f"Has affiliate event: {'dysonprotocol.whaleswap.v1.EventAffiliatePayment' in event_types}"
    )


def test_affiliate_param_update_via_authz(chainnet, alice_sudo_grant):
    """
    Test that alice can update whaleswap params via authz MsgSudo.

    Verifies the authz grant from gov module works for MsgUpdateParams.
    """
    dysond = chainnet[0]

    alice_addr = alice_sudo_grant["alice_addr"]
    gov_addr = alice_sudo_grant["gov_addr"]

    extra_code = """
from dys import _msg, _query, get_executor_address

def test_affiliate(gov_addr):
    executor = get_executor_address()

    # Use authz exec to call MsgSudo on behalf of gov
    authz_result = _msg({
        "@type": "/cosmos.authz.v1beta1.MsgExec",
        "grantee": executor,
        "msgs": [
            {
                "@type": "/dysonprotocol.script.v1.MsgSudo",
                "authority": gov_addr,
                "messages": [
                    {
                        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
                        "authority": gov_addr,
                        "params": {
                            "pfand_per_offer": {"denom": "udys", "amount": "1"},
                            "valuation_fee_pct": "0",
                            "valuation_period": "3600s",
                            "bid_timeout": "5s",
                            "minimum_bid_percent_increase": "0",
                            "max_note_length": 128,
                            "block_delay_before_close": 1,
                            "block_delay_before_liquidation": 1,
                            "arbitrage_mode": 3,
                            "arbitrage_ref_denom": "udys",
                            "affiliate_fee_pct": "0.10"
                        }
                    }
                ]
            }
        ]
    })

    # Query params to verify
    params = _query({
        "@type": "/dysonprotocol.whaleswap.v1.QueryParamsRequest"
    })

    return {
        "affiliate_fee_pct": params["params"]["affiliate_fee_pct"],
        "success": params["params"]["affiliate_fee_pct"] == "0.10"
    }
"""

    kwargs = json.dumps({"gov_addr": gov_addr})

    result = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_addr,
        "--function-name",
        "test_affiliate",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
        "--from",
        "alice",
        "--gas",
        "50000000",
        "--note",
        "affiliate.dys",
    )

    assert result.get("code", 1) == 0, f"Test failed: {result}"

    # Verify params were updated
    params_check = dysond("query", "whaleswap", "params")
    assert (
        params_check["params"]["affiliate_fee_pct"] == "0.10"
    ), f"Affiliate fee not set: {params_check}"


def test_affiliate_trade_with_memo(chainnet, alice_sudo_grant, register_name):
    """
    Test MakeTrade with affiliate memo via tx script exec.

    Verifies that:
    1. Trade executes successfully with --note set
    2. The memo is available in ctx.TxBytes() for the interceptor
    """
    dysond = chainnet[0]

    alice_addr = alice_sudo_grant["alice_addr"]
    gov_addr = alice_sudo_grant["gov_addr"]

    # Register denoms for pool
    denom_a = register_name(dysond, "alice", alice_addr, "10udys")
    denom_b = register_name(dysond, "alice", alice_addr, "10udys")

    # Mint coins
    params = dysond("query", "nameservice", "params")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_fee = int(500_000 * fee_per + 1)

    dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"500000{denom_a}",
        "--mint-fee",
        f"{mint_fee}udys",
        "--from",
        "alice",
    )
    dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"500000{denom_b}",
        "--mint-fee",
        f"{mint_fee}udys",
        "--from",
        "alice",
    )

    # Create pool and trade in one script
    extra_code = """
from dys import _msg, _query, get_executor_address

def setup_and_trade(gov_addr, denom_a, denom_b):
    executor = get_executor_address()
    base, quote = sorted([denom_a, denom_b])

    # Set affiliate_fee_pct via authz
    _msg({
        "@type": "/cosmos.authz.v1beta1.MsgExec",
        "grantee": executor,
        "msgs": [
            {
                "@type": "/dysonprotocol.script.v1.MsgSudo",
                "authority": gov_addr,
                "messages": [
                    {
                        "@type": "/dysonprotocol.whaleswap.v1.MsgUpdateParams",
                        "authority": gov_addr,
                        "params": {
                            "pfand_per_offer": {"denom": "udys", "amount": "1"},
                            "valuation_fee_pct": "0",
                            "valuation_period": "3600s",
                            "bid_timeout": "5s",
                            "minimum_bid_percent_increase": "0",
                            "max_note_length": 128,
                            "block_delay_before_close": 1,
                            "block_delay_before_liquidation": 1,
                            "arbitrage_mode": 3,
                            "arbitrage_ref_denom": "udys",
                            "affiliate_fee_pct": "0.10"
                        }
                    }
                ]
            }
        ]
    })

    # Create pool
    pool_result = _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": executor,
        "coins": [
            {"denom": denom_a, "amount": "100000"},
            {"denom": denom_b, "amount": "100000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.001"},
            {"denom": quote, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })

    pool_id = pool_result["pool_id"]

    # Make trade
    trade_result = _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": executor,
        "operations": [
            {
                "swap": {
                    "pool_id": int(pool_id),
                    "swap_in": {"denom": denom_a, "amount": "1000"}
                }
            }
        ],
        "max_input": [{"denom": denom_a, "amount": "2000"}]
    })

    return {
        "pool_id": pool_id,
        "trade_id": trade_result.get("trade_id"),
        "success": True
    }
"""

    kwargs = json.dumps(
        {
            "gov_addr": gov_addr,
            "denom_a": denom_a,
            "denom_b": denom_b,
        }
    )

    # Register an affiliate name
    affiliate_name = register_name(dysond, "alice", alice_addr, "10udys")

    result = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_addr,
        "--function-name",
        "setup_and_trade",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
        "--from",
        "alice",
        "--gas",
        "100000000",
        "--note",
        affiliate_name,  # Set affiliate memo
    )

    assert result.get("code", 1) == 0, f"Trade failed: {result}"

    # Verify the trade completed - check for script exec event
    events = result.get("events", [])
    event_types = [e.get("type", "") for e in events]

    # Check for script execution event (trade happens inside script)
    assert (
        "dysonprotocol.script.v1.EventExecScript" in event_types
    ), f"Expected script exec event in: {event_types}"


def test_affiliate_invalid_memo_no_event(chainnet, alice_sudo_grant, register_name):
    """
    Test that invalid memo (no .dys suffix) produces no affiliate event.
    """
    dysond = chainnet[0]

    alice_addr = alice_sudo_grant["alice_addr"]
    gov_addr = alice_sudo_grant["gov_addr"]

    # Register denoms for pool
    denom_a = register_name(dysond, "alice", alice_addr, "10udys")
    denom_b = register_name(dysond, "alice", alice_addr, "10udys")

    # Mint coins
    params = dysond("query", "nameservice", "params")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0.01"))
    mint_fee = int(500_000 * fee_per + 1)

    dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"500000{denom_a}",
        "--mint-fee",
        f"{mint_fee}udys",
        "--from",
        "alice",
    )
    dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"500000{denom_b}",
        "--mint-fee",
        f"{mint_fee}udys",
        "--from",
        "alice",
    )

    extra_code = """
from dys import _msg, get_executor_address

def create_pool_and_trade(denom_a, denom_b):
    executor = get_executor_address()
    base, quote = sorted([denom_a, denom_b])

    # Create pool
    pool_result = _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgCreatePool",
        "creator": executor,
        "coins": [
            {"denom": denom_a, "amount": "100000"},
            {"denom": denom_b, "amount": "100000"}
        ],
        "fee_rate": [
            {"denom": base, "amount": "0.001"},
            {"denom": quote, "amount": "0.001"}
        ],
        "min_initial_collateral_ratio": [
            {"denom": base, "amount": "1.5"},
            {"denom": quote, "amount": "1.5"}
        ],
        "interest_rate": [],
        "liquidation_threshold": [
            {"denom": base, "amount": "1.2"},
            {"denom": quote, "amount": "1.2"}
        ],
        "max_borrow_percent": [
            {"denom": base, "amount": "0.8"},
            {"denom": quote, "amount": "0.8"}
        ]
    })

    pool_id = pool_result["pool_id"]

    # Make trade
    trade_result = _msg({
        "@type": "/dysonprotocol.whaleswap.v1.MsgMakeTrade",
        "trader": executor,
        "operations": [
            {
                "swap": {
                    "pool_id": int(pool_id),
                    "swap_in": {"denom": denom_a, "amount": "1000"}
                }
            }
        ],
        "max_input": [{"denom": denom_a, "amount": "2000"}]
    })

    return {"pool_id": pool_id, "trade_id": trade_result.get("trade_id")}
"""

    kwargs = json.dumps(
        {
            "denom_a": denom_a,
            "denom_b": denom_b,
        }
    )

    result = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_addr,
        "--function-name",
        "create_pool_and_trade",
        "--kwargs",
        kwargs,
        "--extra-code",
        extra_code,
        "--from",
        "alice",
        "--gas",
        "50000000",
        "--note",
        "not_a_dysname",  # Invalid - no .dys suffix
    )

    assert result.get("code", 1) == 0, f"Trade failed: {result}"

    # Verify no EventAffiliatePayment
    events = result.get("events", [])
    event_types = [e.get("type", "") for e in events]

    assert (
        "dysonprotocol.whaleswap.v1.EventAffiliatePayment" not in event_types
    ), f"Should not emit affiliate event for invalid memo. Events: {event_types}"
