# 6-3 MoveNft tests (success + failure paths)

# (register_name fixture provided via conftest)


def _nft_owner(dysond_bin, class_id: str, nft_id: str) -> str:
    return dysond_bin("query", "nft", "owner", class_id, nft_id).get("owner", "")


# ----------------------------- TESTS -----------------------------------


def test_move_nft_success(chainnet, generate_account, faucet, register_name):
    dysond_bin = chainnet[0]

    # accounts
    destination_name, destination_addr = generate_account("nft_destination")
    recipient_name, recipient_addr = generate_account("nft_recipient")
    faucet(destination_addr, denom="udys", amount="25000")

    # register name & derive NFT class ID
    class_id = register_name(dysond_bin, destination_name, destination_addr)

    # save nft class
    save_resp = dysond_bin(
        "tx",
        "nameservice",
        "save-class",
        "--class-id",
        class_id,
        "--from",
        destination_name,
    )
    assert save_resp["code"] == 0, save_resp.get("raw_log")

    # verify EventClassSaved emitted
    event_types = [ev.get("type", "") for ev in save_resp.get("events", [])]
    print(f"Emitted event types: {event_types}")
    assert isinstance(
        event_types, list
    ), f"Expected list of event types, got {type(event_types)}"
    assert len(event_types) >= 1, f"Expected at least one event, got: {event_types}"
    expected_event = "dysonprotocol.nameservice.v1.EventClassSaved"
    assert (
        expected_event in event_types
    ), f"Expected '{expected_event}' not found in: {event_types}"

    # mint nft
    nft_id = "nft1"
    mint_resp = dysond_bin(
        "tx",
        "nameservice",
        "mint-nft",
        "--class-id",
        class_id,
        "--nft-id",
        nft_id,
        "--uri",
        "https://example.com/n1",
        "--from",
        destination_name,
    )
    assert mint_resp["code"] == 0, mint_resp.get("raw_log")

    # ensure ownership
    assert _nft_owner(dysond_bin, class_id, nft_id) == destination_addr

    # move nft
    tx_resp = dysond_bin(
        "tx",
        "nameservice",
        "move-nft",
        "--class-id",
        class_id,
        "--nft-id",
        nft_id,
        "--to-address",
        recipient_addr,
        "--from",
        destination_name,
    )
    assert tx_resp["code"] == 0, tx_resp.get("raw_log")

    # verify new owner
    assert _nft_owner(dysond_bin, class_id, nft_id) == recipient_addr


def test_move_nft_non_destination_fails(
    chainnet, generate_account, faucet, register_name
):
    dysond_bin = chainnet[0]

    destination_name, destination_addr = generate_account("nft_destination")
    attacker_name, attacker_addr = generate_account("nft_attacker")
    faucet(destination_addr, denom="udys", amount="25000")
    faucet(attacker_addr, denom="udys", amount="1000")

    class_id = register_name(dysond_bin, destination_name, destination_addr)

    save_resp = dysond_bin(
        "tx",
        "nameservice",
        "save-class",
        "--class-id",
        class_id,
        "--from",
        destination_name,
    )
    assert save_resp["code"] == 0, save_resp.get("raw_log")

    nft_id = "nft1"
    mint_resp = dysond_bin(
        "tx",
        "nameservice",
        "mint-nft",
        "--class-id",
        class_id,
        "--nft-id",
        nft_id,
        "--from",
        destination_name,
    )
    assert mint_resp["code"] == 0, mint_resp.get("raw_log")

    # attacker attempts move
    tx_resp = dysond_bin(
        "tx",
        "nameservice",
        "move-nft",
        "--class-id",
        class_id,
        "--nft-id",
        nft_id,
        "--to-address",
        attacker_addr,
        "--from",
        attacker_name,
    )
    assert tx_resp["code"] != 0, "non-destination signer should not be able to move NFT"


def test_move_nft_module_account_fails(
    chainnet, generate_account, faucet, register_name
):
    dysond_bin = chainnet[0]

    destination_name, destination_addr = generate_account("nft_destination")
    faucet(destination_addr, denom="udys", amount="25000")

    # module account destination
    module_info = dysond_bin("query", "auth", "module-account", "distribution")
    module_addr = module_info["account"]["value"]["address"]

    class_id = register_name(dysond_bin, destination_name, destination_addr)
    save_resp = dysond_bin(
        "tx",
        "nameservice",
        "save-class",
        "--class-id",
        class_id,
        "--from",
        destination_name,
    )
    assert save_resp["code"] == 0, save_resp.get("raw_log")

    nft_id = "nft1"
    mint_resp = dysond_bin(
        "tx",
        "nameservice",
        "mint-nft",
        "--class-id",
        class_id,
        "--nft-id",
        nft_id,
        "--from",
        destination_name,
    )
    assert mint_resp["code"] == 0, mint_resp.get("raw_log")

    # attempt move to module account
    tx_resp = dysond_bin(
        "tx",
        "nameservice",
        "move-nft",
        "--class-id",
        class_id,
        "--nft-id",
        nft_id,
        "--to-address",
        module_addr,
        "--from",
        destination_name,
    )
    assert tx_resp["code"] != 0, "move to module account should fail"
