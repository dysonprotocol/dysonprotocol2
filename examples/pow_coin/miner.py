#!/usr/bin/env python3
"""
POW COIN MINER - Difficulty-adjusted emission

Usage: python miner.py <script_addr> <account>

Reward = EMISSION × (elapsed/TARGET) × (work / difficulty)
"""
import hashlib
import json
import math
import random
import string
import subprocess
import sys
import time


def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()


def nonce(n=12):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def work(hash_hex):
    """Work as continuous bits: 256 - log2(hash)."""
    h = int(hash_hex, 16)
    if h == 0:
        return 256.0
    return 256.0 - math.log2(h)


def get_info(script, miner):
    r = subprocess.run(
        [
            "dysond",
            "query",
            "script",
            "run",
            "--script-address",
            script,
            "--executor-address",
            miner,
            "--function-name",
            "info",
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
    )
    return json.loads(json.loads(r.stdout)["result"])["result"]


def main():
    if len(sys.argv) < 3:
        print("Usage: python miner.py <script_address> <account>")
        sys.exit(1)

    script, account = sys.argv[1], sys.argv[2]

    miner = subprocess.run(
        ["dysond", "keys", "show", "-a", account], capture_output=True, text=True
    ).stdout.strip()

    info = get_info(script, miner)
    prev = info["prev_hash"]
    diff = info["difficulty"]
    elapsed = info["elapsed"]
    base_reward = info["base_reward"]

    EMISSION = info["emission_per_period"]
    TARGET = info["period"]

    print(f"Difficulty: {diff} bits")
    print(f"Elapsed: {elapsed}s, Base reward (if work=diff): {base_reward}")
    print(f"Prev: {prev[:16]}...")
    print()

    # Mine for best proof
    best_nonce, best_hash, best_work = None, None, 0
    start, attempts = time.time(), 0

    print(f"Mining (target difficulty={diff} bits)...")

    while True:
        n = nonce()
        h = sha256(f"{prev}:{n}:{miner}")
        w = work(h)
        attempts += 1

        if w > best_work:
            best_nonce, best_hash, best_work = n, h, w
            # Reward = EMISSION × (elapsed/TARGET) × (work/diff)
            reward = int(EMISSION * (elapsed / TARGET) * (w / diff))
            print(f"  New best: {w:.1f} bits (diff={diff}) → ~{reward} reward")

            if reward >= 1:
                print(
                    f"\nVALID PROOF in {attempts} attempts ({time.time()-start:.1f}s)"
                )
                print(f"Nonce: {best_nonce}")
                print(f"Hash:  {best_hash}")
                print(f"Work:  {best_work:.1f} bits (diff={diff})")
                print(f"Est reward: {reward}")
                print(
                    f"\nSubmit:\ndysond tx script exec --script-address {script} "
                    f"--function-name mine --args '[\"{best_nonce}\"]' "
                    f"--from {account} --gas 3000000 -y"
                )
                break

        if attempts % 100000 == 0:
            rate = attempts / (time.time() - start)
            print(f"  {attempts:,}... ({rate:.0f} H/s, best={best_work:.1f})")


if __name__ == "__main__":
    main()
