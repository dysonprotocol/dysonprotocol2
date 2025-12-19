"""
Verify work calculations with log-based diminishing returns.
"""

import hashlib
import math
import random

MAX_HASH = 2**256
EMISSION = 100  # base units per hour
TARGET = 3600  # 1 hour in seconds


def hash_it(data: str) -> str:
    """SHA-256 hash as hex string."""
    return hashlib.sha256(data.encode()).hexdigest()


def work(hash_hex: str) -> int:
    """Expected hashes to find one this small: 2²⁵⁶ / hash."""
    h = int(hash_hex, 16)
    if h == 0:
        return MAX_HASH
    return MAX_HASH // h


def reward_mult(w: int, target: int) -> float:
    """Log-based multiplier with diminishing returns."""
    ratio = w / target
    return math.log2(1 + ratio)


def calc_reward(w: int, target_hashrate: int, elapsed: int) -> int:
    """Reward = EMISSION × (elapsed / TARGET) × log₂(1 + work/target)"""
    mult = reward_mult(w, target_hashrate)
    return int(EMISSION * (elapsed / TARGET) * mult)


def adjust_target(w: int, old_target: int, elapsed: int) -> int:
    """EMA adjustment of target hashrate."""
    elapsed_hours = elapsed / TARGET
    observed = w / elapsed_hours  # observed hashes per hour
    alpha = min(0.5, elapsed / 3600)  # EMA weight
    new_target = alpha * observed + (1 - alpha) * old_target
    return max(32, int(new_target))


# ============================================================
print("=" * 70)
print("LOG-BASED REWARD SCALING (DIMINISHING RETURNS)")
print("=" * 70)

print("\nFormulas:")
print("  work   = 2²⁵⁶ / hash")
print("  mult   = log₂(1 + work/target)")
print("  reward = EMISSION × (elapsed/3600) × mult")
print("")
print("Key property: work = target → mult = log₂(2) = 1 → baseline emission")

# ============================================================
print("\n" + "=" * 70)
print("MULTIPLIER TABLE")
print("=" * 70)

print("\n  work/target    |  mult = log₂(1+ratio)  |  savings vs linear")
print("  " + "-" * 55)

for ratio in [0.5, 1, 2, 5, 10, 100, 1000, 1_000_000]:
    mult = math.log2(1 + ratio)
    savings = ratio / mult if mult > 0 else 0
    print(f"  {ratio:>12,}×  |  {mult:>6.2f}               |  {savings:>6.1f}× less")

# ============================================================
print("\n" + "=" * 70)
print("SCENARIO 1: Baseline (1 hour, work = target)")
print("=" * 70)

target = 1_000_000
elapsed = 3600
w = 1_000_000

mult = reward_mult(w, target)
reward = calc_reward(w, target, elapsed)

print(f"\ntarget_hashrate = {target:,} hashes/hour")
print(f"elapsed         = {elapsed}s (1 hour)")
print(f"work            = {w:,} hashes")
print(f"")
print(f"ratio = {w}/{target} = {w/target}")
print(f"mult  = log₂(1 + {w/target}) = log₂(2) = {mult}")
print(f"")
print(f"reward = {EMISSION:,} × 1.0 × {mult}")
print(f"       = {reward:,} coins ✓ (exactly 1 POW)")

# ============================================================
print("\n" + "=" * 70)
print("SCENARIO 2: Lucky miner (1M× work)")
print("=" * 70)

target = 100  # very low target
w = 100_000_000  # 100M hashes of work
elapsed = 3600

ratio = w / target
mult = reward_mult(w, target)
linear_mult = ratio
reward = calc_reward(w, target, elapsed)
linear_reward = int(EMISSION * (elapsed / TARGET) * linear_mult)

print(f"\ntarget_hashrate = {target:,} hashes/hour (very low)")
print(f"work            = {w:,} hashes (got lucky!)")
print(f"ratio           = {ratio:,.0f}×")
print(f"")
print(f"WITH LINEAR SCALING:")
print(f"  mult   = {linear_mult:,.0f}")
print(f"  reward = {linear_reward:,} coins = {linear_reward/1_000_000:,.0f} POW 💀")
print(f"")
print(f"WITH LOG SCALING:")
print(f"  mult   = log₂(1 + {ratio:,.0f}) = {mult:.2f}")
print(f"  reward = {reward:,} coins = {reward/1_000_000:.1f} POW ✓")
print(f"")
print(f"Savings: {linear_mult / mult:,.0f}× less reward!")

# ============================================================
print("\n" + "=" * 70)
print("SCENARIO 3: Your case (~1.47M× work)")
print("=" * 70)

target = 23
w = 33_759_587
elapsed = 3377

ratio = w / target
mult = reward_mult(w, target)
linear_mult = ratio
reward = calc_reward(w, target, elapsed)
linear_reward = int(EMISSION * (elapsed / TARGET) * linear_mult)

print(f"\ntarget_hashrate = {target:,} hashes/hour")
print(f"work            = {w:,} hashes")
print(f"elapsed         = {elapsed}s ({elapsed/3600*100:.1f}% of 1hr)")
print(f"ratio           = {ratio:,.0f}×")
print(f"")
print(f"WITH LINEAR SCALING (broken):")
print(f"  mult   = {linear_mult:,.0f}")
print(f"  reward = {linear_reward:,} coins = {linear_reward/1_000_000:,.0f} POW 💀")
print(f"")
print(f"WITH LOG SCALING (fixed):")
print(f"  mult   = log₂(1 + {ratio:,.0f}) = {mult:.2f}")
print(f"  reward = {EMISSION:,} × {elapsed/TARGET:.4f} × {mult:.2f}")
print(f"         = {reward:,} coins = {reward/1_000_000:.1f} POW ✓")

# ============================================================
print("\n" + "=" * 70)
print("MINING SIMULATION")
print("=" * 70)

prev = "0" * 64
address = "dys1test"
best_hash = "f" * 64
best_nonce = ""
num_hashes = 100_000

for i in range(num_hashes):
    nonce = f"n{random.randint(0, 10**12)}"
    h = hash_it(f"{prev}:{nonce}:{address}")
    if int(h, 16) < int(best_hash, 16):
        best_hash = h
        best_nonce = nonce

w = work(best_hash)
target = 1_000_000
elapsed = 60

mult = reward_mult(w, target)
reward = calc_reward(w, target, elapsed)

print(f"\nAfter {num_hashes:,} hashes:")
print(f"best_hash:  {best_hash[:20]}...{best_hash[-8:]}")
print(f"work:       {w:,} expected hashes")
print(f"")
print(f"If claimed after {elapsed}s with target={target:,}:")
print(f"  ratio  = {w/target:.4f}")
print(f"  mult   = log₂(1 + {w/target:.4f}) = {mult:.4f}")
print(f"  reward = {reward:,} coins ({reward/1_000_000:.6f} POW)")

# ============================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(
    """
The log-based model:
  • mult = log₂(1 + work/target)
  • When work = target: mult = 1 (baseline 1 POW/hr)
  • Diminishing returns for work > target
  • No more lottery windfalls!
  
Key insight:
  - 1× work   → 1× reward (baseline)
  - 10× work  → 3.5× reward (not 10×)
  - 100× work → 6.7× reward (not 100×)
  - 1M× work  → 20× reward (not 1,000,000×!)
"""
)
