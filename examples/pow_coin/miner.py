#!/usr/bin/env python3
"""
POW COIN MINER

Usage: python miner.py <script_addr> <account>

Finds nonces that produce low SHA-256 hashes, then submits to claim reward.

Reward = EMISSION × work / (target_hashrate × TARGET)
where work = 2²⁵⁶ / hash_value
"""
import hashlib
import json
import random
import string
import subprocess
import sys
import time

# Must match pow_coin.py
EMISSION = 1_000_000  # 1 POW per period (in micro-units)
TARGET = 3600  # period = 1 hour
MAX_HASH = 2**256


def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()


def nonce(n=12):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def work(hash_hex):
    """Expected hashes to find a hash this small: 2²⁵⁶ / hash."""
    h = int(hash_hex, 16)
    if h == 0:
        return MAX_HASH
    return MAX_HASH // h


def get_state(script):
    """Read contract state from on-chain storage."""
    r = subprocess.run(
        [
            "dysond",
            "query",
            "storage",
            "get",
            script,
            "--index",
            "s",
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        # No state yet — return defaults
        return "0" * 64, 0, 278  # BASE_TARGET
    data = json.loads(r.stdout)
    state = json.loads(data["entry"]["data"])
    prev = state[0]
    last_time = state[1]
    target = state[2] if len(state) > 2 else 278
    return prev, last_time, target


def estimate_reward(w, target):
    """Estimate reward (micro-units) for given work at current target hashrate."""
    expected_work = target * TARGET
    return int(EMISSION * w / expected_work)


def main():
    if len(sys.argv) < 3:
        print("Usage: python miner.py <script_address> <account>")
        sys.exit(1)

    script, account = sys.argv[1], sys.argv[2]

    miner = subprocess.run(
        ["dysond", "keys", "show", "-a", account], capture_output=True, text=True
    ).stdout.strip()

    prev, last_time, target = get_state(script)
    now = int(time.time())
    elapsed = max(1, now - last_time) if last_time else TARGET
    expected_work = int(target * TARGET)

    print(f"Target hashrate: {target:.1f} H/s")
    print(f"Expected work per period: {expected_work:,}")
    print(f"Elapsed since last claim: {elapsed}s")
    print(f"Prev: {prev[:16]}...")
    print()

    best_nonce, best_hash, best_work = None, None, 0
    start, attempts = time.time(), 0

    print("Mining...")

    while True:
        n = nonce()
        h = sha256(f"{prev}:{n}:{miner}")
        w = work(h)
        attempts += 1

        if w > best_work:
            best_nonce, best_hash, best_work = n, h, w
            reward = estimate_reward(w, target)
            print(
                f"  New best: work={w:,} → ~{reward} micro-POW"
                f" ({reward / EMISSION:.4f} POW)"
            )

            if reward >= 1:
                print(
                    f"\nVALID PROOF in {attempts:,} attempts"
                    f" ({time.time() - start:.1f}s)"
                )
                print(f"Nonce: {best_nonce}")
                print(f"Hash:  {best_hash}")
                print(f"Work:  {best_work:,}")
                print(f"Est reward: {reward} micro-POW ({reward / EMISSION:.4f} POW)")
                print(
                    f"\nSubmit:\n"
                    f"dysond tx script exec --script-address {script} "
                    f'--function-name mine --args \'["{best_nonce}"]\' '
                    f"--from {account} --gas 3000000 -y"
                )
                break

        if attempts % 100000 == 0:
            rate = attempts / (time.time() - start)
            print(f"  {attempts:,}... ({rate:.0f} H/s, best_work={best_work:,})")


if __name__ == "__main__":
    main()
