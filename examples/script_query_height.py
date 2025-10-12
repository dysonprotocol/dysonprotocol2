def store_block_height():
    """Store current block height in storage at index 'test_history'"""
    import json
    from dys import get_block_info, get_script_address, _msg

    block_info = get_block_info()
    current_height = block_info["height"]
    data = {"block_height": current_height}

    # Store data using storage module
    result = _msg(
        {
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": get_script_address(),
            "index": "test_history",
            "data": json.dumps(data),
        }
    )

    return f"Stored block height {current_height}"


def query_heights(indices):
    """Query storage data for given indices (current state only)"""
    import json
    from dys import get_script_address, _query

    results = []
    for idx in indices:
        try:
            # Query storage at specific height
            result = _query(
                {
                    "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
                    "owner": get_script_address(),
                    "index": idx,
                },
            )

            results.append(result)
        except Exception as e:
            results.append({"error": str(e)})

    return results
