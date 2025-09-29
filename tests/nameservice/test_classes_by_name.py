import pytest


def test_query_classes_by_name_single(
    chainnet, generate_account, faucet, register_name
):
    dysond_bin = chainnet[0]

    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10000000")

    root = register_name(dysond_bin, alice_name, alice_address)

    # Save a class under the root
    resp = dysond_bin(
        "tx",
        "nameservice",
        "save-class",
        "--class-id",
        root,
        "--name",
        "Main",
        "--symbol",
        "MAIN",
        "--description",
        "Main collection",
        "--uri",
        "https://example.com",
        "--from",
        alice_name,
    )
    assert resp["code"] == 0, resp.get("raw_log", "")

    out = dysond_bin("query", "nameservice", "nftclasses-by-name", "--name", root)
    assert "class_ids" in out
    assert root in out["class_ids"], out


def test_query_classes_by_name_multiple(
    chainnet, generate_account, faucet, register_name
):
    dysond_bin = chainnet[0]

    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10000000")

    root = register_name(dysond_bin, alice_name, alice_address)

    sub1 = f"{root}/a"
    sub2 = f"{root}/b"

    for cid in [root, sub1, sub2]:
        resp = dysond_bin(
            "tx",
            "nameservice",
            "save-class",
            "--class-id",
            cid,
            "--name",
            "C",
            "--symbol",
            "C",
            "--description",
            "C",
            "--uri",
            "https://example.com",
            "--from",
            alice_name,
        )
        assert resp["code"] == 0, resp.get("raw_log", "")

    out = dysond_bin("query", "nameservice", "nftclasses-by-name", "--name", root)
    assert set([root, sub1, sub2]).issubset(set(out.get("class_ids", []))), out


def test_query_classes_by_name_with_prefix(
    chainnet, generate_account, faucet, register_name
):
    dysond_bin = chainnet[0]

    [alice_name, alice_address] = generate_account("alice")
    faucet(alice_address, denom="udys", amount="10000000")

    root = register_name(dysond_bin, alice_name, alice_address)

    paths = [
        f"{root}",
        f"{root}/a",
        f"{root}/aaa",
        f"{root}/foo",
        f"{root}/foo/bar1",
        f"{root}/foo/bar2",
    ]

    for cid in paths:
        resp = dysond_bin(
            "tx",
            "nameservice",
            "save-class",
            "--class-id",
            cid,
            "--name",
            "C",
            "--symbol",
            "C",
            "--description",
            "C",
            "--uri",
            "https://example.com",
            "--from",
            alice_name,
        )
        assert resp["code"] == 0, resp.get("raw_log", "")

    out_all = dysond_bin("query", "nameservice", "nftclasses-by-name", "--name", root)
    assert set(paths).issubset(set(out_all.get("class_ids", []))), out_all

    out_pref = dysond_bin(
        "query",
        "nameservice",
        "nftclasses-by-name",
        "--name",
        root,
        "--subclass-prefix",
        "/foo",
    )
    expect = {f"{root}/foo", f"{root}/foo/bar1", f"{root}/foo/bar2"}
    assert expect.issubset(set(out_pref.get("class_ids", []))), out_pref


def test_query_classes_by_name_not_found(chainnet):
    dysond_bin = chainnet[0]
    out = dysond_bin(
        "query", "nameservice", "nftclasses-by-name", "--name", "doesnotexist.dys"
    )
    print(f"Query response for missing name: {out}")
    # Stepwise: type, then precise substring
    assert isinstance(out, str), f"Expected error string, got: {type(out)}"
    expected = "root name NFT not found"
    assert expected in out, f"{expected} not in: {out}"
