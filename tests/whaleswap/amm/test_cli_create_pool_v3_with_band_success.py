import json


def test_create_pool_v3_with_band_success(
    chainnet, generate_account, faucet, register_name
):
    dysond = chainnet[0]
    [creator_name, creator_addr] = generate_account("amm_creator")
    faucet(creator_addr, amount=2_000_000)

    name = register_name(dysond, creator_name, creator_addr, "1000udys")
    params = dysond("query", "nameservice", "params")
    fee_per_unit = float(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
    units = 1000
    required_fee = int(units * fee_per_unit)
    mint = dysond(
        "tx",
        "nameservice",
        "mint-coins",
        "--amount",
        f"{units}{name}",
        "--mint-fee",
        f"{required_fee}udys",
        "--from",
        creator_name,
    )
    assert mint.get("code", 1) == 0, f"mint-coins failed: {json.dumps(mint, indent=2)}"

    sorted_denoms = sorted(["udys", name])
    bound_values = [
        "0.400000000000000000",
        "0.750000000000000000",
    ]
    tx = dysond(
        "tx",
        "whaleswap",
        "create-pool",
        "--coins",
        "500udys",
        "--coins",
        f"500{name}",
        "--bound-percent",
        f"{bound_values[0]}{sorted_denoms[0]}",
        "--bound-percent",
        f"{bound_values[1]}{sorted_denoms[1]}",
        "--min-collateral-ratio",
        "1.5",
        "--max-borrow-percent",
        "0.8",
        "--from",
        creator_name,
    )
    assert tx.get("code", 1) == 0, f"create-pool v3 failed: {json.dumps(tx, indent=2)}"

    pool_id = int(tx["events"][-2]["attributes"][0]["value"].strip('"'))
    pool_query = dysond(
        "query",
        "whaleswap",
        "pool",
        "--pool-id",
        str(pool_id),
    )
    pool_data = pool_query["pool"]
    assert (
        int(pool_data["pool_id"]) == pool_id
    ), f"Pool ID mismatch: {json.dumps(pool_query, indent=2)}"

    bound_percent = pool_data.get("bound_percent", [])
    expected_bounds = [
        f"{bound_values[0]}{sorted_denoms[0]}",
        f"{bound_values[1]}{sorted_denoms[1]}",
    ]
    assert sorted(bound_percent) == sorted(
        expected_bounds
    ), f"bound_percent mismatch. Expected {expected_bounds}, got {bound_percent}. Full pool: {json.dumps(pool_data, indent=2)}"
