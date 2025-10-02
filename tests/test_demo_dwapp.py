#!/usr/bin/env python3
"""
Frontend UI Tests for DysonProtocol Demo DApp
Integration with existing test infrastructure
"""

import pytest
import json
import os
import requests
from pathlib import Path
from playwright.sync_api import Page
from tests.utils import poll_until_condition


@pytest.fixture(scope="session")
def deployed_demo_script(chainnet, api_address):
    """Deploy demo script and return deployment info."""
    import random
    import string

    dysond = chainnet[0]

    # Get the actual chain-id from the node
    status_result = dysond("status")
    chain_id = status_result["node_info"]["network"]
    print(f"Using chain-id: {chain_id}")

    # Get the correct API port for this test node
    api_port = api_address["port"]
    print(f"Using API port: {api_port}")

    # Generate unique account name directly
    random_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    account_name = f"demo_test_{random_suffix}"

    # Create account directly
    account_result = dysond("keys", "add", account_name, "--keyring-backend", "test")

    # Get account address
    account_info = dysond("keys", "show", account_name, "--keyring-backend", "test")
    address = account_info["address"]
    print(f"Created account: {account_name} -> {address}")

    # Fund account directly (faucet logic)
    fund_result = dysond(
        "tx",
        "bank",
        "send",
        "alice",
        address,
        "10000udys",
        "--from",
        "alice",
        "--chain-id",
        chain_id,
    )
    assert fund_result["code"] == 0, f"Funding failed: {fund_result}"

    # Deploy script using update command (without --script-address, defaults to sender address)
    script_path = Path(__file__).parent.parent / "demo-dwapp/script.py"

    deploy_result = dysond(
        "tx",
        "script",
        "update",
        "--code-path",
        str(script_path),
        "--from",
        account_name,
        "--chain-id",
        chain_id,
        "--gas",
        "auto",
        "--gas-adjustment",
        "1.3",
    )

    print(f"Deploy result: {deploy_result}")
    assert deploy_result["code"] == 0, f"Script deployment failed: {deploy_result}"
    # Upload storage files
    base_path = Path(__file__).parent.parent / "demo-dwapp/storage"
    storage_files = []

    # Recursively find all files in the storage directory
    for root, dirs, files in os.walk(base_path):
        for file in files:
            local_path = Path(root) / file
            # Calculate relative path from base_path for storage key
            storage_key = str(local_path.relative_to(base_path))
            storage_files.append((local_path, storage_key))

    for local_path, storage_key in storage_files:
        # Calculate gas limit based on file size
        file_size = local_path.stat().st_size
        gas_limit = max(300000, min(1000000, file_size * 100 + 200000))

        upload_result = dysond(
            "tx",
            "storage",
            "set",
            "--index",
            storage_key,
            "--data-path",
            str(local_path),
            "--gas",
            "auto",
            "--gas-prices",
            "0udys",
            "--from",
            account_name,
            "--chain-id",
            chain_id,
        )
        assert (
            upload_result["code"] == 0
        ), f"File upload failed for {storage_key}: {upload_result}"
        print(f"Uploaded: {storage_key}")

    print(f"Demo deployed successfully at: http://{address}.localhost:{api_port}")

    # Poll until the script is accessible via HTTP
    def check_script_accessible():
        response = requests.get(
            f"http://localhost:{api_port}",
            timeout=5,
            headers={"Host": f"{address}.localhost"},
        )
        print(
            f"Poll response: status={response.status_code}, content_preview={response.text[:200]}"
        )
        return (
            response.status_code == 200
            and "DysonProtocol WalletStore Demo" in response.text
        )

    poll_until_condition(
        check_script_accessible,
        timeout=30,
        poll_interval=0.5,
        error_message=f"Script not accessible at http://{address}.localhost:{api_port}",
    )
    print(f"Script confirmed accessible at http://{address}.localhost:{api_port}")

    return {
        "account_name": account_name,
        "address": address,
        "script_url": f"http://{address}.localhost:{api_port}",
    }


@pytest.fixture(scope="function")
def demo_url(deployed_demo_script):
    """Return the demo URL."""
    return deployed_demo_script["script_url"]


# TODO use local node_modules for this, don't make a request to cdns
@pytest.mark.skip(reason="Sometimes the js is not loaded fast enough")
@pytest.mark.frontend
def test_homepage_loads(page: Page, demo_url):
    """Test that the homepage loads successfully."""
    # Reduce element operation timeout but allow ample time for the first
    # navigation to complete because the local dev node may take a moment to
    # serve the demo after deployment.
    page.set_default_timeout(10000)  # 5 s element operations
    page.set_default_navigation_timeout(10000)  # 10 s navigation

    page.goto(demo_url)

    # Wait for the page to fully load
    page.wait_for_load_state("networkidle", timeout=5_000)

    # Debug: check what's actually on the page
    print(f"Page URL: {page.url}")
    print(f"Page title: '{page.title()}'")
    print(f"Page content preview: {page.content()[:500]}")

    # Check basic navigation structure exists (not necessarily visible due to Alpine.js logic)
    assert page.locator('a[href="/"]').count() > 0, "Home link not found"
    # The wallet link might be hidden when no wallet is connected, so just check it exists
    assert page.locator('a[href="/wallet"]').count() > 0, "Wallet link not found"
