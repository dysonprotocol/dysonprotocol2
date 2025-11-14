#!/usr/bin/env python3

import argparse
import json
import re
import shlex
import subprocess
import sys
import requests


def run_json(command: str) -> dict:
    """Run a shell command expected to produce JSON on stdout and parse it."""
    completed = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        sys.stderr.write(f"Command failed: {command}\n{completed.stderr}\n")
        raise RuntimeError(f"command exited {completed.returncode}")
    return json.loads(completed.stdout)


def run_tx_and_wait(tx_command: str) -> dict:
    """Run a tx command and wait for it."""
    print(f"Running tx command: {tx_command}")
    tx_proc = subprocess.run(
        tx_command,
        shell=True,
        capture_output=True,
        text=True,
    )
    if tx_proc.returncode != 0:
        error_msg = f"tx exited {tx_proc.returncode}"
        if tx_proc.stderr:
            error_msg += f": {tx_proc.stderr.strip()}"
        sys.stderr.write(f"Tx failed\n")
        if tx_proc.stderr:
            sys.stderr.write(f"{tx_proc.stderr}\n")
        raise RuntimeError(error_msg)

    try:
        tx_json = json.loads(tx_proc.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(f"Tx stdout not JSON: {tx_proc.stdout}\n")
        raise
    if int(tx_json.get("code", 0)) != 0:
        raw_log = tx_json.get("raw_log", "")
        sys.stderr.write(f"Tx rejected: {raw_log}\n")
        raise RuntimeError("tx rejected")

    wait_proc = subprocess.run(
        "dysond query wait-tx -o json",
        shell=True,
        input=tx_proc.stdout,
        capture_output=True,
        text=True,
    )
    if wait_proc.returncode != 0:
        error_msg = f"wait-tx exited {wait_proc.returncode}"
        if wait_proc.stderr:
            error_msg += f": {wait_proc.stderr.strip()}"
        sys.stderr.write(f"Wait-tx failed\n")
        if wait_proc.stderr:
            sys.stderr.write(f"{wait_proc.stderr}\n")
        raise RuntimeError(error_msg)

    # print all events
    result = json.loads(wait_proc.stdout)
    events = result.get("events", [])
    for event in events:
        print(f"Event: {json.dumps(flatten_event(event), indent=2)}")
    return result


def flatten_event(event: dict) -> dict:
    """Convert event from attributes array format to flat dict."""
    flat = {"type": event.get("type")}
    for attr in event.get("attributes", []):
        key = attr.get("key")
        value = attr.get("value")
        # Parse value: try int, fall back to keeping as-is
        try:
            flat[key] = int(value)
        except (ValueError, TypeError):
            flat[key] = value
    return flat


def get_offers_for_pair(base_denom: str, quote_denom: str) -> list[dict]:
    """Get all offers mentioning either denom."""
    offers = []
    for denom in [base_denom, quote_denom]:
        data = run_json(
            f'dysond query whaleswap offers-by-denom --denom "{denom}" -o json'
        )
        offers.extend(data.get("offers", []))
    # Deduplicate by offer_id
    seen = set()
    unique_offers = []
    for offer in offers:
        oid = offer.get("offer_id")
        if oid not in seen:
            seen.add(oid)
            unique_offers.append(offer)
    return unique_offers


def get_pools_for_pair(base_denom: str, quote_denom: str) -> list[dict]:
    """Get all pools for the pair."""
    data = run_json(
        f'dysond query whaleswap pools-by-pair --base-denom "{base_denom}" --quote-denom "{quote_denom}" -o json'
    )
    return data.get("pools", [])


def get_account_balances(account: str) -> list[dict]:
    """Get all balances for an account."""
    data = run_json(f'dysond query bank balances "{account}" -o json')
    return data.get("balances", [])


def get_account_address(account: str) -> str:
    """Get bech32 address from key name."""
    result = subprocess.run(
        f"dysond keys show -a {account}",
        shell=True,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to get address for {account}")
    return result.stdout.strip()


def get_owned_names(account: str) -> list[str]:
    """Get all names (NFTs in nameservice.dys class) owned by account."""
    address = get_account_address(account)
    data = run_json(
        f'dysond query nft nfts nameservice.dys --owner "{address}" -o json'
    )
    nfts = data.get("nfts", [])
    return [nft.get("id") for nft in nfts if nft.get("id")]


def mint_coins_for_names(account: str, amount_per_name: int) -> None:
    """Mint coins for all names owned by account."""
    names = get_owned_names(account)
    if not names:
        print(f"No names owned by {account}")
        return

    params = run_json("dysond query nameservice params -o json")
    fee_per = float(params["params"].get("mint_fee_per_coin", "0"))
    mint_fee = int(amount_per_name * fee_per + 0.99999)  # ceiling

    for name in names:
        print(f"Minting {amount_per_name}{name} with fee {mint_fee}udys")
        try:
            run_tx_and_wait(
                f'dysond tx nameservice mint-coins --amount "{amount_per_name}{name}" --mint-fee "{mint_fee}udys" --from {account} -y -o json'
            )
            print(f"  Minted {amount_per_name}{name}")
        except RuntimeError as e:
            print(f"  Failed to mint {name}: {e}")


def count_pools_for_pair(denom1: str, denom2: str) -> int:
    """Count pools for a denom pair."""
    data = run_json(
        f'dysond query whaleswap pools-by-pair --base-denom "{denom1}" --quote-denom "{denom2}" -o json'
    )
    return len(data.get("pools", []))


def count_offers_for_pair(denom1: str, denom2: str) -> int:
    """Count open offers for a denom pair (both directions)."""
    data = run_json(
        f'dysond query whaleswap offers --have-denom "{denom1}" --want-denom "{denom2}" -o json'
    )
    offers1 = [o for o in data.get("offers", []) if o.get("status") == "open"]

    data = run_json(
        f'dysond query whaleswap offers --have-denom "{denom2}" --want-denom "{denom1}" -o json'
    )
    offers2 = [o for o in data.get("offers", []) if o.get("status") == "open"]

    return len(offers1) + len(offers2)


def count_auctions_for_pair(sell_denom: str, bid_denom: str) -> int:
    """Count auctions for a sell/bid denom pair (both directions)."""
    data = run_json(
        f'dysond query whaleswap auctions --sell-denom "{sell_denom}" --bid-denom "{bid_denom}" -o json'
    )
    auctions1 = data.get("auctions", [])

    data = run_json(
        f'dysond query whaleswap auctions --sell-denom "{bid_denom}" --bid-denom "{sell_denom}" -o json'
    )
    auctions2 = data.get("auctions", [])

    return len(auctions1) + len(auctions2)


def create_pool(
    account: str, denom1: str, amount1: int, denom2: str, amount2: int
) -> None:
    """Create a pool with specified reserves."""
    print(f"Creating pool: {amount1}{denom1} + {amount2}{denom2}")
    run_tx_and_wait(
        f'dysond tx whaleswap create-pool --coins "{amount1}{denom1}" --coins "{amount2}{denom2}" --from {account} -y -o json --gas auto'
    )


def create_offer(
    account: str, have_denom: str, have_amount: int, want_denom: str, want_amount: int
) -> None:
    """Create an orderbook offer."""
    print(
        f"Creating offer: have {have_amount}{have_denom}, want {want_amount}{want_denom}"
    )
    run_tx_and_wait(
        f'dysond tx whaleswap make-offer --have "{have_amount}{have_denom}" --want "{want_amount}{want_denom}" --from {account} -y -o json --gas auto'
    )


def create_auction(
    account: str, sell_denom: str, sell_amount: int, bid_denom: str
) -> None:
    """Create an auction."""
    print(f"Creating auction: sell {sell_amount}{sell_denom}, bid_denom={bid_denom}")
    run_tx_and_wait(
        f'dysond tx whaleswap open-auction --sell "{sell_amount}{sell_denom}" --bid-denom "{bid_denom}" --from {account} -y -o json --gas auto'
    )


def setup_markets(account: str) -> None:
    """Create pools, offers, and auctions for all denom pairs in account balance."""
    import random

    balances = get_account_balances(account)

    # Filter out whaleswap.dys/* system denoms (pool shares, liquid denoms, pfand)

    denoms = [
        b["denom"]
        for b in balances
        if int(b.get("amount", "0")) > 0 and not b["denom"].startswith("whaleswap.dys/")
    ]
    print(
        f"Found {len(denoms)} tradeable denoms (excluding whaleswap.dys/* system denoms)"
    )

    # Generate all pairs
    pairs = []
    for i, d1 in enumerate(denoms):
        for d2 in denoms[i + 1 :]:
            pairs.append((d1, d2))

    print(f"Processing {len(pairs)} denom pairs")

    for denom1, denom2 in pairs:
        print(f"\n--- Pair: {denom1} / {denom2} ---")

        bal1 = int([b for b in balances if b["denom"] == denom1][0]["amount"])
        bal2 = int([b for b in balances if b["denom"] == denom2][0]["amount"])

        # Pools: if <10, make one with 10% of balance
        num_pools = count_pools_for_pair(denom1, denom2)
        print(f"Pools: {num_pools}")
        if num_pools < 10:
            amount1 = max(100, bal1 // 10)
            amount2 = max(100, bal2 // 10)
            fee = f"0.{random.randint(10, 50):03d}"  # 0.010 to 0.050
            try:
                create_pool(account, denom1, amount1, denom2, amount2, fee)
            except RuntimeError as e:
                print(f"  Pool creation failed: {e}")

        # Offers: if <20, make 2 offers (one each direction)
        num_offers = count_offers_for_pair(denom1, denom2)
        print(f"Offers: {num_offers}")
        if num_offers < 20:
            # Offer 1: have denom1, want denom2
            have1 = max(10, bal1 // 100)
            want1 = max(10, int(have1 * random.uniform(0.8, 1.2)))
            try:
                create_offer(account, denom1, have1, denom2, want1)
            except RuntimeError as e:
                print(f"  Offer 1 failed: {e}")

            # Offer 2: have denom2, want denom1
            have2 = max(10, bal2 // 100)
            want2 = max(10, int(have2 * random.uniform(0.8, 1.2)))
            try:
                create_offer(account, denom2, have2, denom1, want2)
            except RuntimeError as e:
                print(f"  Offer 2 failed: {e}")

        # Auctions: if <20, make 2 auctions (one each direction)
        num_auctions = count_auctions_for_pair(denom1, denom2)
        print(f"Auctions: {num_auctions}")
        if num_auctions < 20:
            # Auction 1: sell denom1, bid in denom2
            sell1 = max(10, bal1 // 100)
            try:
                create_auction(account, denom1, sell1, denom2)
            except RuntimeError as e:
                print(f"  Auction 1 failed: {e}")

            # Auction 2: sell denom2, bid in denom1
            sell2 = max(10, bal2 // 100)
            try:
                create_auction(account, denom2, sell2, denom1)
            except RuntimeError as e:
                print(f"  Auction 2 failed: {e}")


def get_pool_details(pool_id: str) -> dict | None:
    """Get detailed information for a specific pool."""
    try:
        pool_data = run_json(f"dysond query whaleswap pool {pool_id} -o json")
        return pool_data.get("pool")
    except:
        return None


def is_pool_balanced(pool: dict, input_denom: str) -> bool:
    """Check if a pool has reasonable balance for trading."""
    coins = pool.get("coins", [])
    if len(coins) != 2:
        return False

    # Find input and output coins
    input_coin = None
    output_coin = None
    for coin in coins:
        if coin.get("denom") == input_denom:
            input_coin = coin
        else:
            output_coin = coin

    if not input_coin or not output_coin:
        return False

    # Skip pools with whaleswap.dys/* system denoms
    if output_coin.get("denom", "").startswith("whaleswap.dys/"):
        return False

    input_amount = int(input_coin.get("amount", "0"))
    output_amount = int(output_coin.get("amount", "0"))

    # Skip pools with zero amounts
    if input_amount == 0 or output_amount == 0:
        return False

    # Check balance ratio - skip if ratio is too extreme (>10:1 or <1:10)
    ratio = max(input_amount, output_amount) / min(input_amount, output_amount)
    if ratio > 10:
        return False

    # Skip pools with very small reserves (<1000 total tokens)
    total_reserves = input_amount + output_amount
    if total_reserves < 1000:
        return False

    return True


def get_all_trades_for_denom(denom: str) -> list[dict]:
    """Find all pools and offers involving a specific denom."""
    trades = []

    # Get offers for this denom
    offers_data = run_json(
        f'dysond query whaleswap offers-by-denom --denom "{denom}" -o json'
    )
    offers = offers_data.get("offers", [])

    # Get all pools that contain this denom
    pools_data = run_json("dysond query whaleswap pools -o json")
    all_pools = pools_data.get("pools", [])
    candidate_pools = [
        pool
        for pool in all_pools
        if any(coin.get("denom") == denom for coin in pool.get("coins", []))
    ]

    # Filter pools to only include balanced ones
    pools = []
    for pool in candidate_pools:
        pool_id = pool.get("pool_id")
        if pool_id and is_pool_balanced(pool, denom):
            pools.append(pool)

    # Convert to trade opportunities
    for offer in offers:
        if offer.get("status") == "open":
            trades.append({"type": "offer", "data": offer})

    for pool in pools:
        trades.append({"type": "pool", "data": pool})

    return trades


def find_best_buy_price(base_denom: str, quote_denom: str) -> dict | None:
    """Find best price to buy base using quote (lowest quote/base ratio)."""
    pools = get_pools_for_pair(base_denom, quote_denom)
    offers = get_offers_for_pair(base_denom, quote_denom)

    best_price = float("inf")
    best_deal = None

    # Check pools: price = quote/base
    for pool in pools:
        coins = pool.get("coins", [])
        if len(coins) != 2:
            continue
        c0, c1 = coins[0], coins[1]
        if c0["denom"] == base_denom and c1["denom"] == quote_denom:
            amt_base = int(c0["amount"])
            amt_quote = int(c1["amount"])
            if amt_base > 0:
                price = amt_quote / amt_base
                if price < best_price:
                    best_price = price
                    best_deal = {"type": "pool", "data": pool, "price": price}
        elif c0["denom"] == quote_denom and c1["denom"] == base_denom:
            amt_quote = int(c0["amount"])
            amt_base = int(c1["amount"])
            if amt_quote > 0:
                price = amt_base / amt_quote
                if price < best_price:
                    best_price = price
                    best_deal = {"type": "pool", "data": pool, "price": price}

    # Check offers: makers selling base for quote
    for offer in offers:
        if offer.get("status") != "open":
            continue
        have = offer.get("initial_have", {})
        want = offer.get("initial_want", {})
        if have.get("denom") == base_denom and want.get("denom") == quote_denom:
            amt_base = int(have.get("amount", "0"))
            amt_quote = int(want.get("amount", "0"))
            if amt_base > 0:
                price = amt_quote / amt_base
                if price < best_price:
                    best_price = price
                    best_deal = {"type": "offer", "data": offer, "price": price}

    return best_deal


def find_best_sell_price(base_denom: str, quote_denom: str) -> dict | None:
    """Find best price to sell base for quote (highest quote/base ratio)."""
    pools = get_pools_for_pair(base_denom, quote_denom)
    offers = get_offers_for_pair(base_denom, quote_denom)

    best_price = 0
    best_deal = None

    # Check pools: price = quote/base
    for pool in pools:
        coins = pool.get("coins", [])
        if len(coins) != 2:
            continue
        c0, c1 = coins[0], coins[1]
        if c0["denom"] == base_denom and c1["denom"] == quote_denom:
            amt_base = int(c0["amount"])
            amt_quote = int(c1["amount"])
            if amt_base > 0:
                price = amt_quote / amt_base
                if price > best_price:
                    best_price = price
                    best_deal = {"type": "pool", "data": pool, "price": price}
        elif c0["denom"] == quote_denom and c1["denom"] == base_denom:
            amt_quote = int(c0["amount"])
            amt_base = int(c1["amount"])
            if amt_quote > 0:
                price = amt_base / amt_quote
                if price > best_price:
                    best_price = price
                    best_deal = {"type": "pool", "data": pool, "price": price}

    # Check offers: makers buying base with quote
    for offer in offers:
        if offer.get("status") != "open":
            continue
        have = offer.get("initial_have", {})
        want = offer.get("initial_want", {})
        if have.get("denom") == quote_denom and want.get("denom") == base_denom:
            amt_quote = int(have.get("amount", "0"))
            amt_base = int(want.get("amount", "0"))
            if amt_quote > 0:
                price = amt_base / amt_quote
                if price > best_price:
                    best_price = price
                    best_deal = {"type": "offer", "data": offer, "price": price}

    return best_deal


def collect_trade_operations(
    trades: list[dict], input_denom: str, amount: int, debug: bool = True
) -> tuple[list[dict], list[str]]:
    """Collect trade operations and determine output denoms.

    Consolidates operations by pool_id/offer_id since each can only be referenced once per trade.
    """
    pool_operations = {}  # pool_id -> (operation, output_denom)
    offer_operations = {}  # offer_id -> (operation, output_denom)
    output_denoms = []

    for trade in trades:
        output_denom = None

        if trade["type"] == "pool":
            pool = trade["data"]
            pool_id = pool["pool_id"]

            # Skip if we already have an operation for this pool
            if pool_id in pool_operations:
                continue

            coins = pool.get("coins", [])
            if len(coins) == 2:
                # Find input and output coins
                input_coin = None
                output_coin = None
                for coin in coins:
                    if coin.get("denom") == input_denom:
                        input_coin = coin
                    else:
                        output_coin = coin
                        output_denom = coin.get("denom")

                # Skip pools with whaleswap.dys/* system denoms
                if output_denom and output_denom.startswith("whaleswap.dys/"):
                    if debug:
                        print(
                            f"  Skipping pool {pool_id}: output denom is whaleswap.dys/* system denom"
                        )
                    continue

                if input_coin is None or output_coin is None:
                    if debug:
                        print(
                            f"  Skipping pool {pool_id}: coins={[c.get('denom') for c in coins]}, input_denom={input_denom}, matched={input_coin is not None}"
                        )
                    continue

                # For swap_in, we specify the exact input amount we want to provide
                op = {
                    "swap": {
                        "pool_id": pool_id,
                        "swap_in": {"denom": input_denom, "amount": str(amount)},
                    }
                }
                pool_operations[pool_id] = (op, output_denom)
                if output_denom not in output_denoms:
                    output_denoms.append(output_denom)

        elif trade["type"] == "offer":
            offer = trade["data"]
            offer_id = offer["offer_id"]

            # Skip if already used or not open
            if offer_id in offer_operations:
                if debug:
                    print(f"  Skipping offer {offer_id}: already in use")
                continue
            if offer.get("status") != "open":
                if debug:
                    print(f"  Skipping offer {offer_id}: status={offer.get('status')}")
                continue

            # Check if this offer accepts our input_denom (we pay want, receive have)
            want_denom = offer.get("initial_want", {}).get("denom")
            have_denom = offer.get("initial_have", {}).get("denom")

            # Skip offers with whaleswap.dys/* system denoms
            if (want_denom and want_denom.startswith("whaleswap.dys/")) or (
                have_denom and have_denom.startswith("whaleswap.dys/")
            ):

                print(f"  Skipping offer {offer_id}: contains whaleswap.dys/* denom")
                continue

            if want_denom == input_denom:
                # We can take this offer by providing want_denom
                output_denom = have_denom

                # Calculate units we can take with our amount
                unit_want = int(offer.get("unit_want_int", "1"))
                remaining_units = int(offer.get("remaining_units", "0"))

                if unit_want == 0 or remaining_units == 0:
                    if debug:
                        print(
                            f"  Skipping offer {offer_id}: unit_want={unit_want}, remaining_units={remaining_units}"
                        )
                    continue

                # Take as many units as our amount allows
                units_to_take = min(amount // unit_want, remaining_units)

                if units_to_take == 0:
                    if debug:
                        print(
                            f"  Skipping offer {offer_id}: units_to_take=0 (amount={amount}, unit_want={unit_want})"
                        )
                    continue

                op = {"take": {"offer_id": offer_id, "take_units": str(units_to_take)}}
                offer_operations[offer_id] = (op, output_denom)
                if output_denom not in output_denoms:
                    output_denoms.append(output_denom)
            else:
                if debug:
                    print(
                        f"  Skipping offer {offer_id}: want={want_denom}, have={have_denom}, input={input_denom}"
                    )

    # Extract operations in a consistent order
    operations = [op for op, _ in pool_operations.values()] + [
        op for op, _ in offer_operations.values()
    ]

    if debug:
        print(
            f"  Total operations after dedup: {len(pool_operations)} pools, {len(offer_operations)} offers"
        )

    return operations, output_denoms


def execute_batch_trades(
    from_acct: str,
    operations: list[dict],
    max_inputs: list[str],
    min_outputs: list[str],
    gas_flags: str = "",
) -> dict:
    """Execute multiple trade operations in a single transaction."""
    # Build command with multiple --op, --max-input, and --min-output flags
    cmd_parts = ["dysond tx whaleswap make-trade", f"--from {shlex.quote(from_acct)}"]

    # Add max-input flags
    for max_input in max_inputs:
        cmd_parts.append(f'--max-input "{max_input}"')

    # Add operation flags
    for op in operations:
        op_q = shlex.quote(json.dumps(op))
        cmd_parts.append(f"--op {op_q}")

    # Add min-output flags
    for min_output in min_outputs:
        cmd_parts.append(f'--min-output "{min_output}"')

    # add note flag
    # request https://jaspervdj.be/lorem-markdownum/markdown.txt?num-blocks=1
    note = requests.get(
        "https://jaspervdj.be/lorem-markdownum/markdown.txt?num-blocks=1"
    ).text[:100]
    cmd_parts.append(f"--note {shlex.quote(note)}")

    # Add other flags
    cmd_parts.extend([gas_flags, "-y -o json --gas auto"])

    cmd = " ".join(cmd_parts)
    print(f"Executing batch transaction with {len(operations)} operations...")
    tx = run_tx_and_wait(cmd)

    return tx


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Whaleswap market operations and stress testing"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Mint command
    mint_parser = subparsers.add_parser(
        "mint", help="Mint coins for all names owned by account"
    )
    mint_parser.add_argument("--from", dest="from_acct", required=True, help="key name")
    mint_parser.add_argument(
        "--amount", type=int, default=1000000, help="Amount to mint per name"
    )

    # Setup markets command
    setup_parser = subparsers.add_parser(
        "setup", help="Create pools, offers, and auctions for all denom pairs"
    )
    setup_parser.add_argument(
        "--from", dest="from_acct", required=True, help="key name"
    )

    # Stress test command
    stress_parser = subparsers.add_parser(
        "stress", help="Stress test make-trade with multiple small trades"
    )
    stress_parser.add_argument(
        "--from", dest="from_acct", required=True, help="key name"
    )
    stress_parser.add_argument("--gas-flags", default="", help="Optional gas flags")

    args = parser.parse_args()

    if args.command == "mint":
        mint_coins_for_names(args.from_acct, args.amount)
        return

    if args.command == "setup":
        setup_markets(args.from_acct)
        return

    # Stress test command
    print(f"Account: {args.from_acct}")

    # Get account balances, filter out whaleswap.dys/* system denoms

    all_balances = get_account_balances(args.from_acct)
    balances = [b for b in all_balances if not b["denom"].startswith("whaleswap.dys/")]
    print(
        f"Found {len(balances)} tradeable denoms (excluding whaleswap.dys/* system denoms)"
    )

    # Collect all operations across all denoms with global pool/offer deduplication
    all_operations = []
    all_output_denoms = set()
    input_denom_limits = {}  # Track how much of each input denom we're using
    used_pool_ids = set()  # Global pool tracking across all denoms
    used_offer_ids = set()  # Global offer tracking across all denoms

    # For each denom with positive balance, find trade opportunities
    for balance in balances:
        denom = balance.get("denom")
        available_amount = int(balance.get("amount", "0"))

        if available_amount <= 0:
            continue

        print(f"\nProcessing denom: {denom} (balance: {available_amount})")

        # Find all trade opportunities for this denom
        trades = get_all_trades_for_denom(denom)
        pool_count = sum(1 for t in trades if t["type"] == "pool")
        offer_count = sum(1 for t in trades if t["type"] == "offer")
        print(
            f"Found {len(trades)} trade opportunities ({pool_count} pools, {offer_count} offers)"
        )

        # Use moderate amount that can satisfy typical offer unit sizes
        trade_amount = min(10000, available_amount // 10)
        if trade_amount < 100:
            trade_amount = max(1, available_amount)  # Use what's available, minimum 1
        print(f"Using trade amount: {trade_amount}")

        # Collect operations for this denom (already deduplicated by pool_id/offer_id)
        operations, output_denoms = collect_trade_operations(
            trades, denom, trade_amount, debug=True
        )

        # Filter out pools/offers we've already used globally
        new_operations = []
        for op in operations:
            if "swap" in op:
                pool_id = op["swap"]["pool_id"]
                if pool_id not in used_pool_ids:
                    new_operations.append(op)
                    used_pool_ids.add(pool_id)
            elif "take" in op:
                offer_id = op["take"]["offer_id"]
                if offer_id not in used_offer_ids:
                    new_operations.append(op)
                    used_offer_ids.add(offer_id)

        print(f"Collected {len(new_operations)} unique operations (after global dedup)")

        # Add operations if we have enough balance
        total_needed = len(new_operations) * trade_amount
        if available_amount >= total_needed and len(new_operations) > 0:
            all_operations.extend(new_operations)
            all_output_denoms.update(output_denoms)
            input_denom_limits[denom] = total_needed

    if not all_operations:
        print("No valid trade operations found. Exiting.")
        return

    # Build max_inputs list: small limits for inputs since we're using small test amounts
    max_inputs = [f"{amount}{denom}" for denom, amount in input_denom_limits.items()]

    # Build min_outputs: don't enforce minimums since we're testing functionality
    # The AMM will determine actual outputs, we just want operations to work
    min_outputs = []

    print(f"\nTotal operations to execute: {len(all_operations)}")
    print(f"Input denoms: {list(input_denom_limits.keys())}")
    print(f"Output denoms: {sorted(all_output_denoms)}")

    # Execute all operations in a single batch transaction
    try:
        tx = execute_batch_trades(
            args.from_acct, all_operations, max_inputs, min_outputs, args.gas_flags
        )

        # Count successful trades
        trade_count = 0
        for e in tx.get("events", []):
            if e.get("type", "").startswith("dysonprotocol"):
                flat_e = flatten_event(e)
                print(f"Event: {flat_e}")
                if "trade_id" in flat_e:
                    trade_count += 1

        print(f"Batch transaction completed with {trade_count} trades executed")

    except Exception as e:
        error_msg = str(e)
        print(f"Error: {error_msg}")


if __name__ == "__main__":
    main()
