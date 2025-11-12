import json

from tests.examples.rps.utils import deploy_script, exec_initialize_game


def test_initialize_game_sets_expected_storage(chainnet, generate_account):
    dysond_bin = chainnet[0]
    account_name, account_address = generate_account("rps_init", faucet_amount=1)

    deploy_script(dysond_bin, account_name)
    script_output = exec_initialize_game(dysond_bin, account_name, account_address)

    expected_config = {
        "join_cost": 100,
        "attack_reward": 50,
    }
    expected_state = {
        "total_pieces": 0,
        "total_energy_circulation": 0,
        "pending_market_energy": 0,
        "pending_grid_energy": 0,
        "last_updated_block": 0,
        "next_piece_id": 1,
    }

    assert (
        script_output["status"] == "initialized"
    ), f"Unexpected status. Script output: {json.dumps(script_output, indent=2)}"
    assert (
        script_output["config"] == expected_config
    ), f"Config mismatch. Expected: {json.dumps(expected_config, indent=2)}. Output: {json.dumps(script_output['config'], indent=2)}"
    assert (
        script_output["state"] == expected_state
    ), f"State mismatch. Expected: {json.dumps(expected_state, indent=2)}. Output: {json.dumps(script_output['state'], indent=2)}"

    config_query = dysond_bin(
        "query",
        "storage",
        "get",
        account_address,
        "--index",
        "game/config",
    )
    state_query = dysond_bin(
        "query",
        "storage",
        "get",
        account_address,
        "--index",
        "game/state",
    )

    config_value = json.loads(config_query["entry"]["data"])
    state_value = json.loads(state_query["entry"]["data"])

    assert (
        config_value == expected_config
    ), f"Stored config mismatch. Expected: {json.dumps(expected_config, indent=2)}. Stored: {json.dumps(config_value, indent=2)}"
    assert (
        state_value == expected_state
    ), f"Stored state mismatch. Expected: {json.dumps(expected_state, indent=2)}. Stored: {json.dumps(state_value, indent=2)}"

    second_exec = dysond_bin(
        "tx",
        "script",
        "exec",
        "--script-address",
        account_address,
        "--function-name",
        "initialize_game",
        "--args",
        "[]",
        "--from",
        account_name,
        "--gas",
        "2000000",
    )
    assert (
        second_exec["code"] != 0
    ), f"Second initialization should fail. Full result: {json.dumps(second_exec, indent=2)}"
    assert (
        "game already initialized" in second_exec["raw_log"].lower()
    ), f"Expected error message missing. Raw log: {second_exec['raw_log']}"
