#!/usr/bin/env python3

import pytest
import json
import tempfile
import os

# Floating-point benchmark script code
FP_BENCHMARK_SCRIPT = '''
import math
import hashlib

def to_bytes(n, length=1, byteorder='big', signed=False):
    if byteorder == 'little':
        order = range(length)
    elif byteorder == 'big':
        order = reversed(range(length))
    else:
        raise ValueError("byteorder must be either 'little' or 'big'")

    return bytes([(n >> i*8) & 0xff for i in order])

def float_to_ieee_int(f):
    if math.isnan(f):
        sign = 1 if math.copysign(1.0, f) < 0 else 0
        return (sign << 63) | 0x7ff8000000000000
    if math.isinf(f):
        sign = 1 if f < 0 else 0
        return (sign << 63) | 0x7ff0000000000000
    if f == 0.0:
        sign = 1 if math.copysign(1.0, f) < 0 else 0
        return sign << 63
    sign = 1 if f < 0 else 0
    f = abs(f)
    mant, exp = math.frexp(f)
    fraction = 2 * mant - 1
    mant_bits = int(fraction * (1 << 52))
    biased_exp = exp + 1022
    if biased_exp > 0:
        if biased_exp >= 2047:
            return (sign << 63) | 0x7ff0000000000000
        bits = (sign << 63) | (biased_exp << 52) | mant_bits
    else:
        mant_bits_full = (1 << 52) | mant_bits
        shift = 1 - biased_exp
        if shift > 53:
            bits = 0
        else:
            mant_bits_denorm = mant_bits_full >> shift
            bits = (sign << 63) | mant_bits_denorm
    return bits

def detect_fp_differences_detailed(iterations=100):
    """
    This function performs various floating-point operations and math functions
    that may exhibit differences across platforms due to underlying C library
    implementations or floating-point behavior. It packs the results into bytes using
    big-endian order for consistency, computes a SHA-256 hash of the concatenated data,
    and returns a dictionary with the total hash, intermediate values as hex strings
    of their packed bytes, and lossy repr strings of the float values to allow isolating
    differences more easily.

    Args:
        iterations (int): Number of iterations for transcendental function tests (default: 100)

    For transcendental functions, the lists in 'values' and 'repr_values' correspond to
    i=1 to iterations, where x = i * math.pi / iterations. If hashes differ between systems, compare
    the repr_values lists element-wise to see which specific step (index +1) shows a
    numerical difference, and check hex values for bit-level differences.

    Run this on different systems, compare the total_hash; if different, compare sub-hashes,
    values, and repr_values to pinpoint differences.
    """

    def float_to_big_endian_bytes(x):
        bits = float_to_ieee_int(x)
        return to_bytes(bits, length=8, byteorder='big')

    def pack_hex(x):
        return float_to_big_endian_bytes(x).hex()

    sections = {}
    all_bytes = b""

    # Signed zero section
    signed_bytes = b""
    copysign_val = math.copysign(1.0, -0.0)
    signed_bytes += float_to_big_endian_bytes(copysign_val)
    neg_zero_val = -0.0
    signed_bytes += float_to_big_endian_bytes(neg_zero_val)
    pos_zero_val = 0.0
    signed_bytes += float_to_big_endian_bytes(pos_zero_val)
    signed_hash = hashlib.sha256(signed_bytes).hexdigest()
    signed_values = [
        pack_hex(copysign_val),
        pack_hex(neg_zero_val),
        pack_hex(pos_zero_val),
    ]
    signed_repr_values = [str(copysign_val), str(neg_zero_val), str(pos_zero_val)]
    sections["signed_zero"] = {
        "hash": signed_hash,
        "values": signed_values,
        "repr_values": signed_repr_values,
    }
    all_bytes += signed_bytes

    # Loop summation section
    a = 0.0
    for i in range(1, iterations * 100 + 1):
        a += 1.0 / i**2
    loop_sum_bytes = b""
    loop_sum_bytes += float_to_big_endian_bytes(a)
    loop_sum_hash = hashlib.sha256(loop_sum_bytes).hexdigest()
    sections["loop_sum"] = {
        "hash": loop_sum_hash,
        "values": [pack_hex(a)],
        "repr_values": [str(a)],
    }
    all_bytes += loop_sum_bytes

    # math.fsum section
    nums = [1.0 / i**2 for i in range(1, iterations * 100 + 1)]
    fsum_result = math.fsum(nums)
    fsum_bytes = b""
    fsum_bytes += float_to_big_endian_bytes(fsum_result)
    fsum_hash = hashlib.sha256(fsum_bytes).hexdigest()
    sections["fsum"] = {
        "hash": fsum_hash,
        "values": [pack_hex(fsum_result)],
        "repr_values": [str(fsum_result)],
    }
    all_bytes += fsum_bytes

    # Transcendental functions sections
    trans = {}

    # Sin
    sin_bytes = b""
    sin_values = []
    sin_repr_values = []
    for i in range(1, iterations + 1):
        x = i * math.pi / iterations
        val = math.sin(x)
        sin_bytes += float_to_big_endian_bytes(val)
        sin_values.append(pack_hex(val))
        sin_repr_values.append(str(val))
    sin_hash = hashlib.sha256(sin_bytes).hexdigest()
    trans["sin"] = {
        "hash": sin_hash,
        "values": sin_values,
        "repr_values": sin_repr_values,
    }
    all_bytes += sin_bytes

    # Cos
    cos_bytes = b""
    cos_values = []
    cos_repr_values = []
    for i in range(1, iterations + 1):
        x = i * math.pi / iterations
        val = math.cos(x)
        cos_bytes += float_to_big_endian_bytes(val)
        cos_values.append(pack_hex(val))
        cos_repr_values.append(str(val))
    cos_hash = hashlib.sha256(cos_bytes).hexdigest()
    trans["cos"] = {
        "hash": cos_hash,
        "values": cos_values,
        "repr_values": cos_repr_values,
    }
    all_bytes += cos_bytes

    # Tan
    tan_bytes = b""
    tan_values = []
    tan_repr_values = []
    for i in range(1, iterations + 1):
        x = i * math.pi / iterations
        cos_x = math.cos(x)
        val = math.tan(x) if cos_x != 0 else 0.0
        tan_bytes += float_to_big_endian_bytes(val)
        tan_values.append(pack_hex(val))
        tan_repr_values.append(str(val))
    tan_hash = hashlib.sha256(tan_bytes).hexdigest()
    trans["tan"] = {
        "hash": tan_hash,
        "values": tan_values,
        "repr_values": tan_repr_values,
    }
    all_bytes += tan_bytes

    # Exp
    exp_bytes = b""
    exp_values = []
    exp_repr_values = []
    for i in range(1, iterations + 1):
        x = i * math.pi / iterations
        val = math.exp(x)
        exp_bytes += float_to_big_endian_bytes(val)
        exp_values.append(pack_hex(val))
        exp_repr_values.append(str(val))
    exp_hash = hashlib.sha256(exp_bytes).hexdigest()
    trans["exp"] = {
        "hash": exp_hash,
        "values": exp_values,
        "repr_values": exp_repr_values,
    }
    all_bytes += exp_bytes

    # Log
    log_bytes = b""
    log_values = []
    log_repr_values = []
    for i in range(1, iterations + 1):
        x = i * math.pi / iterations
        val = math.log(1 + x)
        log_bytes += float_to_big_endian_bytes(val)
        log_values.append(pack_hex(val))
        log_repr_values.append(str(val))
    log_hash = hashlib.sha256(log_bytes).hexdigest()
    trans["log"] = {
        "hash": log_hash,
        "values": log_values,
        "repr_values": log_repr_values,
    }
    all_bytes += log_bytes

    # Fmod
    fmod_bytes = b""
    fmod_values = []
    fmod_repr_values = []
    for i in range(1, iterations + 1):
        x = i * math.pi / iterations
        val = math.fmod(x, math.pi / 4)
        fmod_bytes += float_to_big_endian_bytes(val)
        fmod_values.append(pack_hex(val))
        fmod_repr_values.append(str(val))
    fmod_hash = hashlib.sha256(fmod_bytes).hexdigest()
    trans["fmod"] = {
        "hash": fmod_hash,
        "values": fmod_values,
        "repr_values": fmod_repr_values,
    }
    all_bytes += fmod_bytes

    sections["transcendental"] = trans

    # Total hash
    total_hash = hashlib.sha256(all_bytes).hexdigest()
    sections["total_hash"] = total_hash

    return sections

def detect_fp_differences_summary(iterations=100):
    """
    Return only the total hash for faster execution when details aren't needed.
    """
    detailed_result = detect_fp_differences_detailed(iterations)
    return {"total_hash": detailed_result["total_hash"]}

def simple_fp_test(iterations=5):
    """Simple floating-point test for gas efficiency"""
    import math
    import hashlib
    
    # Simple floating-point operations
    result = 0.0
    for i in range(1, iterations + 1):
        result += math.sin(i * math.pi / iterations)
        result += math.cos(i * math.pi / iterations)
    
    # Hash just the final result
    result_str = str(result)
    total_hash = hashlib.sha256(result_str.encode()).hexdigest()
    
    return {
        "total_hash": total_hash,
        "result": result,
        "iterations": iterations
    }


'''


def test_fp_benchmark_comprehensive(chainnet, generate_account, faucet):
    """Test floating-point benchmark with multiple iteration counts via tx script exec"""
    dysond = chainnet[0]

    # Generate account for testing
    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="100000000")  # 100 DYS

    # Write script to temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(FP_BENCHMARK_SCRIPT)
        script_path = f.name

    # Update script for alice
    update_result = dysond(
        "tx", "script", "update", "--code-path", script_path, "--from", alice_name, "-y"
    )
    assert (
        update_result.get("code", 1) == 0
    ), f"Failed to update script: {update_result}"

    # Test different iteration counts with detailed output
    test_cases = [
        {"function": "simple_fp_test", "iterations": 100, "name": "small"},
        {"function": "simple_fp_test", "iterations": 200, "name": "medium"},
        {"function": "simple_fp_test", "iterations": 300, "name": "large"},
    ]

    results = {}

    # Execute benchmark for each iteration count
    for case in test_cases:
        function_name = case["function"]
        iterations = case["iterations"]
        name = case["name"]

        # Execute the benchmark function
        exec_result = dysond(
            "tx",
            "script",
            "exec",
            "--script-address",
            alice_address,
            "--function-name",
            function_name,
            "--args",
            f"[{iterations}]",
            "--from",
            alice_name,
            "--gas",
            "6000000",
            "-y",
        )

        assert (
            exec_result.get("code", 1) == 0
        ), f"Failed to execute {name} benchmark: {exec_result.get('raw_log', 'No error log')}"

        # Extract response from events
        events_by_type = {
            event.get("type"): event for event in exec_result.get("events", [])
        }
        assert (
            "dysonprotocol.script.v1.EventExecScript" in events_by_type
        ), f"No EventExecScript found in {name} transaction events"

        exec_event = events_by_type["dysonprotocol.script.v1.EventExecScript"]
        attrs_by_key = {
            attr.get("key"): attr.get("value")
            for attr in exec_event.get("attributes", [])
        }
        assert (
            "response" in attrs_by_key
        ), f"No response attribute found in {name} EventExecScript"

        response_json = attrs_by_key["response"]
        response_data = json.loads(response_json)
        result_data = json.loads(response_data.get("result", "{}"))
        result = result_data.get("result")

        # Validate basic structure
        assert isinstance(
            result, dict
        ), f"Expected dict for {name} ({iterations} iterations) but got {type(result)}: {result}"
        assert (
            "total_hash" in result
        ), f"Missing 'total_hash' key in {name} result: {result}"
        assert "result" in result, f"Missing 'result' key in {name} result: {result}"
        assert (
            "iterations" in result
        ), f"Missing 'iterations' key in {name} result: {result}"

        # Verify iteration count matches expected
        actual_iterations = result["iterations"]
        assert (
            actual_iterations == iterations
        ), f"{name}: expected {iterations} iterations, got {actual_iterations}"

        # Store result for hash comparison
        results[name] = {
            "iterations": iterations,
            "hash": result["total_hash"],
            "result": result["result"],
        }

        print(
            f"✓ {name.capitalize()} benchmark ({iterations} iterations): {result['total_hash'][:16]}..."
        )

    # Verify different iteration counts produce different hashes
    small_hash = results["small"]["hash"]
    medium_hash = results["medium"]["hash"]
    large_hash = results["large"]["hash"]

    assert (
        small_hash != medium_hash
    ), f"Small (5) and medium (10) iterations should produce different hashes: {small_hash} vs {medium_hash}"
    assert (
        medium_hash != large_hash
    ), f"Medium (10) and large (50) iterations should produce different hashes: {medium_hash} vs {large_hash}"
    assert (
        small_hash != large_hash
    ), f"Small (5) and large (50) iterations should produce different hashes: {small_hash} vs {large_hash}"

    # Test hash consistency - same iteration count should produce same hash
    repeat_result = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        alice_address,
        "--function-name",
        "simple_fp_test",
        "--args",
        f"[{test_cases[0]['iterations']}]",
        "--from",
        alice_name,
        "--gas-adjustment",
        "1.5",
        "-y",
    )

    assert (
        repeat_result.get("code", 1) == 0
    ), f"Failed to execute repeat benchmark: {repeat_result.get('raw_log', 'No error log')}"

    # Extract response from repeat execution
    repeat_events_by_type = {
        event.get("type"): event for event in repeat_result.get("events", [])
    }
    repeat_exec_event = repeat_events_by_type["dysonprotocol.script.v1.EventExecScript"]
    repeat_attrs_by_key = {
        attr.get("key"): attr.get("value")
        for attr in repeat_exec_event.get("attributes", [])
    }
    repeat_response_json = repeat_attrs_by_key["response"]
    repeat_response_data = json.loads(repeat_response_json)
    repeat_result_data = json.loads(repeat_response_data.get("result", "{}"))
    repeat_hash = repeat_result_data.get("result")["total_hash"]

    assert (
        repeat_hash == small_hash
    ), f"Same iteration count should produce same hash: {small_hash} vs {repeat_hash}"

    print(f"✓ All benchmarks completed successfully")
    print(f"  - Small ({test_cases[0]['iterations']} iterations): {small_hash[:16]}...")
    print(
        f"  - Medium ({test_cases[1]['iterations']} iterations): {medium_hash[:16]}..."
    )
    print(f"  - Large ({test_cases[2]['iterations']} iterations): {large_hash[:16]}...")
    print(f"✓ Hash consistency verified")

    # Clean up temporary file
    os.unlink(script_path)
