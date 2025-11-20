"""
Metrics helper coverage for leverage suite.

Exercises pool/liquidity and offer lifecycle helper functions and
verifies AddressMetrics tallies update accordingly.
"""

import json


def _extract_event_attr(tx_result, event_type, key):
    events = [e for e in tx_result.get("events", []) if e.get("type") == event_type]
    assert events, f"{event_type} missing: {json.dumps(tx_result, indent=2)}"
    attrs = {a.get("key"): a.get("value") for a in events[0].get("attributes", [])}
    value = attrs.get(key)
    assert value, f"{key} missing in {event_type}: {json.dumps(events[0], indent=2)}"
    return value.strip('"')


def test_metrics_pool_and_liquidity_tracking(
    chainnet, leverage_accounts, leverage_names_and_coins
):
    """Pool creation plus add/remove liquidity should update metrics counters."""
    dysond = chainnet[0]
    alice = leverage_accounts["alice"]
    alice_name = alice["name"]
    alice_addr = alice["addr"]
    foo = leverage_names_and_coins["foo_name"]
    bar = leverage_names_and_coins["bar_name"]
    base, quote = sorted([foo, bar])

    pool_result = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        f"6000{foo}",
        "--coins",
        f"6000{bar}",
        "--fee-rate",
        f"0.003{base}",
        "--fee-rate",
        f"0.003{quote}",
        "--min-collateral-ratio",
        f"1.5{base}",
        "--min-collateral-ratio",
        f"1.5{quote}",
        "--liquidation-threshold",
        f"1.2{base}",
        "--liquidation-threshold",
        f"1.2{quote}",
        "--max-borrow-percent",
        f"0.8{base}",
        "--max-borrow-percent",
        f"0.8{quote}",
        "--from",
        alice_name,
    )
    assert (
        pool_result.get("code", 1) == 0
    ), f"create-pool failed: {json.dumps(pool_result, indent=2)}"
    pool_id = _extract_event_attr(
        pool_result, "dysonprotocol.whaleswap.v1.EventPoolCreated", "pool_id"
    )

    metrics_after_pool = dysond(
        "query", "whaleswap", "address-metrics", f"--address={alice_addr}"
    )
    pools_created = int(metrics_after_pool["metrics"].get("pools_created", 0))
    assert (
        pools_created >= 1
    ), f"pool counter not incremented: {json.dumps(metrics_after_pool, indent=2)}"

    add_result = dysond(
        "tx",
        "whaleswap",
        "add-liquidity",
        "--pool-id",
        pool_id,
        "--amounts",
        f"2000{foo}",
        "--amounts",
        f"2000{bar}",
        "--from",
        alice_name,
    )
    assert (
        add_result.get("code", 1) == 0
    ), f"add-liquidity failed: {json.dumps(add_result, indent=2)}"

    metrics_after_add = dysond(
        "query", "whaleswap", "address-metrics", f"--address={alice_addr}"
    )
    adds = int(metrics_after_add["metrics"].get("liquidity_adds", 0))
    assert (
        adds >= 1
    ), f"liquidity_adds should increment: {json.dumps(metrics_after_add, indent=2)}"

    remove_result = dysond(
        "tx",
        "whaleswap",
        "remove-liquidity",
        "--pool-id",
        pool_id,
        "--shares",
        "500",
        "--from",
        alice_name,
    )
    assert (
        remove_result.get("code", 1) == 0
    ), f"remove-liquidity failed: {json.dumps(remove_result, indent=2)}"

    metrics_after_remove = dysond(
        "query", "whaleswap", "address-metrics", f"--address={alice_addr}"
    )
    removes = int(metrics_after_remove["metrics"].get("liquidity_removes", 0))
    assert (
        removes >= 1
    ), f"liquidity_removes should increment: {json.dumps(metrics_after_remove, indent=2)}"


def test_metrics_offer_lifecycle(chainnet, leverage_accounts, leverage_names_and_coins):
    """Offer creation, take, and cancel should update metrics including maker volume."""
    dysond = chainnet[0]
    alice = leverage_accounts["alice"]
    bob = leverage_accounts["bob"]
    foo = leverage_names_and_coins["foo_name"]
    bar = leverage_names_and_coins["bar_name"]

    make_result = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"120{foo}",
        "--want",
        f"60{bar}",
        "--settlement-mode",
        "settlement-escrow",
        "--from",
        alice["name"],
    )
    assert (
        make_result.get("code", 1) == 0
    ), f"make-offer failed: {json.dumps(make_result, indent=2)}"
    offer_id = int(
        _extract_event_attr(
            make_result, "dysonprotocol.whaleswap.v1.EventOfferCreated", "offer_id"
        )
    )

    metrics_after_offer = dysond(
        "query", "whaleswap", "address-metrics", f"--address={alice['addr']}"
    )
    assert (
        int(metrics_after_offer["metrics"].get("offers_created", 0)) >= 1
    ), f"offer creation not recorded: {json.dumps(metrics_after_offer, indent=2)}"

    take_result = dysond(
        "tx",
        "whaleswap",
        "make-trade",
        "--max-input",
        f"60{bar}",
        "--op",
        json.dumps({"take": {"offer_id": int(offer_id), "take_units": ""}}),
        "--from",
        bob["name"],
    )
    assert (
        take_result.get("code", 1) == 0
    ), f"take-offer failed: {json.dumps(take_result, indent=2)}"

    metrics_after_close = dysond(
        "query", "whaleswap", "address-metrics", f"--address={alice['addr']}"
    )
    assert (
        int(metrics_after_close["metrics"].get("offers_closed", 0)) >= 1
    ), f"offer close not recorded: {json.dumps(metrics_after_close, indent=2)}"
    maker_volume = metrics_after_close["metrics"].get("maker_volume", [])
    assert (
        maker_volume
    ), f"maker_volume empty: {json.dumps(metrics_after_close, indent=2)}"

    make_result_two = dysond(
        "tx",
        "whaleswap",
        "make-offer",
        "--have",
        f"80{bar}",
        "--want",
        f"40{foo}",
        "--settlement-mode",
        "settlement-escrow",
        "--from",
        alice["name"],
    )
    assert (
        make_result_two.get("code", 1) == 0
    ), f"make-offer second failed: {json.dumps(make_result_two, indent=2)}"
    offer_id_two = _extract_event_attr(
        make_result_two, "dysonprotocol.whaleswap.v1.EventOfferCreated", "offer_id"
    )

    cancel_result = dysond(
        "tx",
        "whaleswap",
        "cancel-offer",
        "--offer-id",
        offer_id_two,
        "--from",
        alice["name"],
    )
    assert (
        cancel_result.get("code", 1) == 0
    ), f"cancel-offer failed: {json.dumps(cancel_result, indent=2)}"

    metrics_final = dysond(
        "query", "whaleswap", "address-metrics", f"--address={alice['addr']}"
    )
    assert (
        int(metrics_final["metrics"].get("offers_cancelled", 0)) >= 1
    ), f"offer cancel not recorded: {json.dumps(metrics_final, indent=2)}"
