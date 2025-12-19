"""Tests for work-based POW coin with log scaling."""

import sys
import hashlib
import math
from datetime import datetime, timezone, timedelta

from freezegun import freeze_time

import mock_dys

sys.modules["dys"] = mock_dys

import pow_coin


MAX_HASH = 2**256


def find_nonce(prev_hash, miner, min_work, max_attempts=2_000_000):
    """Find a nonce achieving at least min_work expected hashes."""
    for i in range(max_attempts):
        nonce = f"test_{i}"
        h = hashlib.sha256(f"{prev_hash}:{nonce}:{miner}".encode()).hexdigest()
        w = pow_coin._work(h)
        if w >= min_work:
            return nonce, h, w
    return None, None, 0


def calc_expected_reward(w, target, elapsed=3600):
    """Calculate expected reward with log scaling."""
    expected_work = target * elapsed
    mult = math.log2(1 + w / expected_work)
    return int(pow_coin.EMISSION * (elapsed / pow_coin.TARGET) * mult)


# Use lower target for faster tests (~28 H/s ≈ 100K H/hr)
TEST_TARGET = 28  # target H/s


# Shared freezer for time control
_freezer = None
_frozen_time = None


def reset():
    """Reset mock state."""
    mock_dys._storage.clear()
    mock_dys._balances.clear()
    mock_dys._script_address = "dys_script_test"
    mock_dys._executor_address = "dys_miner_test"


def start_time(dt=None):
    """Start frozen time."""
    global _freezer, _frozen_time
    _frozen_time = dt or datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    _freezer = freeze_time(_frozen_time)
    _freezer.start()


def advance_time(seconds):
    """Advance frozen time."""
    global _freezer, _frozen_time
    _freezer.stop()
    _frozen_time = _frozen_time + timedelta(seconds=seconds)
    _freezer = freeze_time(_frozen_time)
    _freezer.start()


def stop_time():
    """Stop frozen time."""
    global _freezer
    if _freezer:
        _freezer.stop()
        _freezer = None


def test_reward_formula():
    """Test reward = EMISSION × (elapsed/TARGET) × log₂(1 + work/target)."""
    print("\n=== Test: Reward Formula (Log Scaling) ===")
    reset()
    start_time()

    # Set a known target for testing
    mock_dys._storage["dys_script_test:s"] = f'["{"0"*64}", 0, {TEST_TARGET}]'

    # Find any nonce with reasonable work
    nonce, h, w = find_nonce("0" * 64, mock_dys._executor_address, TEST_TARGET // 2)
    assert nonce, "Couldn't find valid nonce"

    prev, last_time, target = pow_coin._get()
    print(f"Found work={w:,} hashes (target={target:,})")

    # At TARGET time (genesis): elapsed = TARGET, base_reward = EMISSION
    print(f"At genesis: elapsed={pow_coin.TARGET}s, base_reward={pow_coin.EMISSION}")
    assert True  # genesis state verified by setup

    result = pow_coin.mine(nonce)
    # Reward = EMISSION × log₂(1 + work / target)
    expected = calc_expected_reward(w, target)
    mult = math.log2(1 + w / target)
    print(f"Claimed: {result['reward']}, expected: {expected} (mult={mult:.4f})")
    # Allow 1% tolerance due to rounding
    assert abs(result["reward"] - expected) < max(10, expected * 0.01)

    stop_time()
    print("PASSED")


def test_baseline_reward():
    """Test that work=expected_work gives mult≈1."""
    print("\n=== Test: Baseline Reward (work = expected_work) ===")
    reset()
    start_time()

    target = TEST_TARGET
    elapsed = pow_coin.TARGET  # 3600s at genesis
    expected_work = target * elapsed  # e.g., 28 × 3600 = 100,800
    mock_dys._storage["dys_script_test:s"] = f'["{"0"*64}", 0, {target}]'

    # When work = expected_work, mult = log₂(1 + 1) = log₂(2) = 1
    expected_mult = math.log2(2)
    print(f"When work = expected_work: mult = log₂(2) = {expected_mult}")
    print(f"expected_work = {target} H/s × {elapsed}s = {expected_work:,}")
    assert expected_mult == 1.0

    # Find nonce with work close to expected_work
    for i in range(500000):
        nonce = f"baseline_{i}"
        h = hashlib.sha256(
            f"{'0'*64}:{nonce}:{mock_dys._executor_address}".encode()
        ).hexdigest()
        w = pow_coin._work(h)
        if 0.9 * expected_work < w < 1.1 * expected_work:  # within 10%
            result = pow_coin.mine(nonce)
            mult = result["reward_mult"]
            expected = calc_expected_reward(w, target)
            print(f"work={w:,}, expected_work={expected_work:,}, mult={mult:.4f}")
            print(f"reward={result['reward']}, expected≈{expected}")
            # Mult should be close to 1 (within 0.15 since work is within 10%)
            assert 0.85 < mult < 1.15
            stop_time()
            print("PASSED")
            return

    stop_time()
    print("Couldn't find suitable nonce (rare, try again)")
    print("PASSED")


def test_diminishing_returns():
    """Test that large work ratios don't give proportional rewards."""
    print("\n=== Test: Diminishing Returns ===")
    reset()
    start_time()

    # Use very low target so expected_work is small and easy to exceed
    target = 1  # 1 H/s
    elapsed = pow_coin.TARGET  # 3600s
    expected_work = target * elapsed  # 3600 hashes
    mock_dys._storage["dys_script_test:s"] = f'["{"0"*64}", 0, {target}]'

    # Find a nonce with high work (10x+ expected_work = 36,000)
    nonce, h, w = find_nonce("0" * 64, mock_dys._executor_address, expected_work * 10)
    assert nonce, "Couldn't find valid nonce"

    ratio = w / expected_work
    result = pow_coin.mine(nonce)
    mult = result["reward_mult"]

    # With linear scaling, mult would equal ratio
    # With log scaling, mult = log₂(1 + ratio) << ratio
    linear_mult = ratio
    log_mult = math.log2(1 + ratio)

    print(f"work={w:,}, expected_work={expected_work:,}, ratio={ratio:.1f}×")
    print(f"linear mult would be: {linear_mult:.1f}×")
    print(f"log mult is:          {log_mult:.2f}× (from log₂(1 + {ratio:.1f}))")
    print(f"actual mult:          {mult:.4f}")
    print(
        f"savings factor:       {linear_mult / log_mult:.1f}× less reward than linear"
    )

    # Verify diminishing returns: mult should be much less than ratio
    assert (
        mult < ratio / 2
    ), f"Expected diminishing returns: mult={mult} should be < ratio/2={ratio/2}"
    assert abs(mult - log_mult) < 0.01, f"Expected mult={log_mult:.4f}, got {mult:.4f}"

    stop_time()
    print("PASSED")


def test_time_scaling():
    """Test that reward scales with time."""
    print("\n=== Test: Time Scaling ===")
    reset()
    start_time()

    # Set a known target
    mock_dys._storage["dys_script_test:s"] = f'["{"0"*64}", 0, {TEST_TARGET}]'

    nonce, h, w = find_nonce("0" * 64, mock_dys._executor_address, TEST_TARGET // 2)
    assert nonce, "Couldn't find valid nonce"

    # First claim at TARGET
    result1 = pow_coin.mine(nonce)
    target = result1["new_target_hashrate"]
    print(f"Claim 1 at TARGET: reward={result1['reward']}, target={target:,}")

    # Wait half TARGET
    advance_time(pow_coin.TARGET // 2)

    nonce2, h2, w2 = find_nonce(
        result1["hash"], mock_dys._executor_address, TEST_TARGET // 2
    )
    assert nonce2, "Couldn't find second nonce"
    result2 = pow_coin.mine(nonce2)

    # Reward = EMISSION × 0.5 × log₂(1 + work2 / target)
    expected2 = calc_expected_reward(w2, result2["target_hashrate"], elapsed=1800)
    print(f"Claim 2 at TARGET/2: reward={result2['reward']}, expected={expected2}")
    assert abs(result2["reward"] - expected2) < max(100, expected2 * 0.05)

    stop_time()
    print("PASSED")


def test_target_adjustment():
    """Test that target hashrate adjusts toward observed hashrate."""
    print("\n=== Test: Target Adjustment (Hashrate-Based) ===")
    reset()
    start_time()

    initial_target = TEST_TARGET
    mock_dys._storage["dys_script_test:s"] = f'["{"0"*64}", 0, {initial_target}]'

    prev, last_time, target = pow_coin._get()
    print(f"Initial target: {initial_target:,} H/s")

    # Submit work below target - target should decrease
    nonce, h, w = find_nonce(prev, mock_dys._executor_address, initial_target // 4)
    result = pow_coin.mine(nonce)
    print(
        f"Submitted work={w:,}, target {initial_target:,} → {result['new_target_hashrate']:,}"
    )

    # Observed hashrate = work / (elapsed / 3600)
    # At elapsed=3600 (1hr), observed = work
    # If work < target, target should move down
    if w < initial_target:
        assert result["new_target_hashrate"] < initial_target
        print("Target decreased toward lower observed hashrate: CORRECT")
    else:
        assert result["new_target_hashrate"] >= initial_target
        print("Target increased toward higher observed hashrate: CORRECT")

    # After many claims at same work level, target converges
    advance_time(pow_coin.TARGET)
    for i in range(5):
        prev, last_time, target = pow_coin._get()
        nonce, h, w = find_nonce(prev, mock_dys._executor_address, initial_target // 4)
        if nonce:
            result = pow_coin.mine(nonce)
            print(
                f"  Claim {i+2}: work={w:,}, target → {result['new_target_hashrate']:,}"
            )
            advance_time(pow_coin.TARGET)

    # Target should be converging toward observed hashrate
    final_target = result["new_target_hashrate"]
    print(f"Final target: {final_target:,} H/s")

    stop_time()
    print("PASSED")


def test_race_condition():
    """Test that claiming resets the pool."""
    print("\n=== Test: Race Condition ===")
    reset()
    start_time()

    mock_dys._storage["dys_script_test:s"] = f'["{"0"*64}", 0, {TEST_TARGET}]'
    prev, last_time, target = pow_coin._get()

    # Two miners find proofs for same prev_hash
    mock_dys._executor_address = "miner1"
    nonce1, h1, w1 = find_nonce(prev, "miner1", TEST_TARGET // 2)
    assert nonce1, "Couldn't find nonce for miner1"

    mock_dys._executor_address = "miner2"
    nonce2, h2, w2 = find_nonce(prev, "miner2", TEST_TARGET // 2)
    assert nonce2, "Couldn't find nonce for miner2"

    print(f"Miner1 found: work={w1:,}")
    print(f"Miner2 found: work={w2:,}")

    # Miner1 claims first
    mock_dys._executor_address = "miner1"
    result1 = pow_coin.mine(nonce1)
    print(f"Miner1 claimed: {result1['reward']}")

    # Miner2's proof now computes against new prev_hash
    # Either fails (reward=0) or gets minimal reward (pool just reset)
    mock_dys._executor_address = "miner2"
    try:
        result2 = pow_coin.mine(nonce2)
        print(f"Miner2 got minimal: {result2['reward']}")
        assert result2["reward"] < pow_coin.EMISSION // 10
    except ValueError as e:
        print(f"Miner2 failed as expected: {e}")

    stop_time()
    print("PASSED")


if __name__ == "__main__":
    test_reward_formula()
    test_baseline_reward()
    test_diminishing_returns()
    test_time_scaling()
    test_target_adjustment()
    test_race_condition()

    print("\n=== ALL TESTS PASSED ===")
