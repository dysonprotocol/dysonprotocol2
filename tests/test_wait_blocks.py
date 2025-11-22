"""
Test demonstrating how to wait for a specific number of blocks to be produced.
"""
import pytest
import time
from tests import utils


def test_wait_for_blocks(chainnet):
    """Demonstrate waiting for blocks to be produced."""
    dysond = chainnet[0]
    
    # Get current height
    status_data = dysond("status")
    current_height = int(status_data.get("sync_info", {}).get("latest_block_height", 0))
    
    # Get initial block data
    initial_block_data = dysond("query", "block", "--type=height", str(current_height))
    initial_height = int(initial_block_data.get("header", {}).get("height", 0))
    
    # Wait for blocks to be produced by polling
    blocks_to_wait = 2
    target_height = initial_height + blocks_to_wait
    
    def check_height_reached():
        status_data = dysond("status")
        current_height = int(status_data.get("sync_info", {}).get("latest_block_height", 0))
        return current_height >= target_height
    
    utils.poll_until_condition(
        check_height_reached,
        timeout=5, # Do not change this!!!!
        poll_interval=0.1, # Do not change this!!!!
        error_message=f"Timeout waiting for blocks. Target: {target_height}"
    )
    
    # Get final block data - need to get current height again after waiting
    final_status_data = dysond("status")
    final_height = int(final_status_data.get("sync_info", {}).get("latest_block_height", 0))
    
    # Verify the height increased by at least the number of blocks we waited for
    assert final_height >= initial_height + blocks_to_wait, \
        f"Block height didn't increase as expected. Initial: {initial_height}, Final: {final_height}"
    
    print(f"Successfully waited for {blocks_to_wait} blocks to be produced.")
    print(f"Initial height: {initial_height}, Final height: {final_height}") 