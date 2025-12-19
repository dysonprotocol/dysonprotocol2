"""Real-time POW simulation with actual hashing."""

import hashlib
import math
import time
import random
import string

# Config for fast simulation
TARGET = 1  # 1 second per POW
WINDOW = 10  # 10 second EMA window
EMISSION = 1_000_000
MIN_DIFF = 5


def work(hash_hex):
    """Work as continuous bits: 256 - log2(hash)."""
    h = int(hash_hex, 16)
    return 256.0 - math.log2(h) if h else 256.0


def adjust(w, diff, elapsed):
    """Adjust based on observed hashrate: ideal = work - log2(elapsed/TARGET)."""
    ideal = w - math.log2(elapsed / TARGET)
    a = min(0.5, elapsed / WINDOW)
    return max(MIN_DIFF, round(a * ideal + (1 - a) * diff, 1))


def estimate_hashrate():
    """Measure local hashrate."""
    start = time.time()
    count = 0
    while time.time() - start < 0.5:
        for _ in range(1000):
            hashlib.sha256(b"test").hexdigest()
            count += 1
    return count / (time.time() - start)


def mine_until(prev_hash, miner, min_work):
    """Mine until we find hash with work >= min_work."""
    attempts = 0
    while True:
        attempts += 1
        nonce = "".join(random.choices(string.ascii_letters + string.digits, k=12))
        h = hashlib.sha256(f"{prev_hash}:{nonce}:{miner}".encode()).hexdigest()
        w = work(h)
        if w >= min_work:
            return nonce, h, w, attempts


def run_simulation(duration=20):
    """Run simulation targeting ~1 claim per second."""

    # Measure hashrate to set appropriate difficulty
    hashrate = estimate_hashrate()
    # For 1 claim/sec, need 2^diff = hashrate
    target_diff = math.log2(hashrate * TARGET)
    diff = round(target_diff, 1)

    print(f"=== POW Simulation: TARGET={TARGET}s, WINDOW={WINDOW}s ===")
    print(f"Local hashrate: {hashrate:,.0f} H/s")
    print(f"Starting difficulty: {diff} (~{2**diff:,.0f} hashes/claim)")
    print(f"Goal: ~{duration} POW in {duration}s\n")

    # State
    prev_hash = "0" * 64
    last_time = time.time()
    miner = "miner1"

    total_pow = 0
    claim_count = 0
    start = time.time()

    print(
        f"{'Time':>6} {'Elapsed':>7} {'Work':>6} {'Diff':>6} {'α':>6} {'Reward':>12} {'Total POW':>12}"
    )
    print("-" * 75)

    while time.time() - start < duration:
        # Mine at current difficulty
        nonce, h, w, attempts = mine_until(prev_hash, miner, diff)
        now = time.time()
        elapsed = max(0.001, now - last_time)

        # Calculate reward (linear with work ratio)
        reward = int(EMISSION * (elapsed / TARGET) * (w / diff))
        reward = max(1, reward)

        total_pow += reward
        claim_count += 1

        # Calculate α for display
        alpha = min(0.5, elapsed / WINDOW)

        # Adjust difficulty
        new_diff = adjust(w, diff, elapsed)

        print(
            f"{now - start:6.1f}s {elapsed:6.2f}s {w:6.1f} {diff:6.1f} {alpha:6.3f} {reward:12,} {total_pow:12,}"
        )

        # Update state
        prev_hash = h
        last_time = now
        diff = new_diff

    elapsed_total = time.time() - start
    print("-" * 75)
    print(f"\nSummary:")
    print(f"  Duration: {elapsed_total:.1f}s")
    print(f"  Claims: {claim_count}")
    print(f"  Total POW: {total_pow:,} ({total_pow/1_000_000:.2f} POW)")
    print(f"  Expected: {elapsed_total * EMISSION:,.0f} ({elapsed_total:.2f} POW)")
    print(f"  Ratio: {total_pow / (elapsed_total * EMISSION):.1%}")
    print(f"  Final difficulty: {diff}")


if __name__ == "__main__":
    run_simulation(duration=20)
