from dys import (
    _query,
    get_gas_consumed,
    get_gas_limit,
    get_nodes_called,
    get_cumulative_size,
    get_script_address,
    get_executor_address,
    get_block_info,
    get_attached_messages,
    get_attached_msg_results,
    emit_event,
    dys_eval,
)
import json


def show_block_info():
    """Get basic block information"""
    block = get_block_info()
    return {
        "height": block.get("Height"),
        "chain_id": block.get("ChainID"),
        "time": block.get("Time"),
    }


def query_balance():
    """Query the script's own balance at current height"""
    script_address = get_script_address()
    current_balance = _query(
        {
            "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
            "address": script_address,
            "denom": "udys",
        },
    )
    current_height = get_block_info().get("Height")
    return {"current_balance": current_balance, "current_height": current_height}


def check_gas():
    """Check gas consumption information"""
    # Perform a query that consumes gas
    script_address = get_script_address()
    _chain(
        "Query",
        json_query=json.dumps(
            {
                "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
                "address": script_address,
                "denom": "udys",
            }
        ),
    )

    # Check how much gas was used and the limit
    current_gas = get_gas_consumed()
    max_gas = get_gas_limit()

    return {
        "gas_consumed": current_gas,
        "gas_limit": max_gas,
        "percentage_used": f"{(current_gas / max_gas) * 100:.2f}%",
    }


def check_limit():
    """Check the gas limit for the current execution"""
    limit = get_gas_limit()
    return {"gas_limit": limit}


def count_nodes():
    """Demonstrate node counting by performing operations of varying complexity"""
    # Simple operations
    a = 1 + 2

    # More complex operation that will use more nodes
    script_address = get_script_address()
    _query(
        {
            "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
            "address": script_address,
            "denom": "udys",
        }
    )

    # Complex calculation with loop
    result = 0
    for i in range(10):
        result += i * 2

    # Get the count of AST nodes evaluated
    nodes_called = get_nodes_called()

    return {"nodes_called": nodes_called, "calculation_result": result}


def check_memory():
    """Check the cumulative memory size used"""
    size = get_cumulative_size()
    return {"memory_used": size}


def get_my_address():
    """Get current script address"""
    my_address = get_script_address()
    return {"script_address": my_address}


def who_called_me():
    """Returns information about who executed this script"""
    # Get the script's own address
    script_address = get_script_address()

    # Get the address of who called this script
    caller_address = get_executor_address()

    # Check if the script was called by its owner
    is_self_call = script_address == caller_address

    return {
        "script_address": script_address,
        "caller_address": caller_address,
        "is_self_call": is_self_call,
    }


def check_messages():
    """Access attached messages"""
    messages = get_attached_messages()
    return {"attached_messages": messages}


def check_msg_results():
    """Access results of attached messages"""
    results = get_attached_msg_results()
    return {"message_results": results}


def emit_test_event():
    """Emit a custom event"""
    result = emit_event("payment_processed", "success")
    return {"event_emitted": True, "event_result": result}


def demonstrate_dys_eval():
    """Demonstrate different ways to use dys_eval"""
    results = {}

    # Simple arithmetic
    results["arithmetic"] = dys_eval("2 + 3 * 4")

    # String operations
    results["string_ops"] = dys_eval("'hello ' + 'world'.upper()")

    # Using variables from current scope
    x = 10
    y = 5
    local_scope = {"x": x, "y": y}
    results["with_variables"] = dys_eval("x * y", scope=local_scope)

    # Multiple statements
    results["multi_statement"] = dys_eval(
        """
a = 5
b = 7
result = a * b
result + 3
"""
    )

    return results


def a_or_b(a, b):
    """Example function for coverage testing"""
    if a:
        return "a"
    if b:
        return "b"
    return None


def test_a_or_b():
    """Test function with coverage enabled"""
    a_or_b(1, 0)
    a_or_b(1, 1)


def wsgi(environ, start_response):
    """Simple WSGI handler that shows available functions"""
    start_response("200 OK", [("Content-Type", "text/html")])

    html = """
    <html>
    <head><title>Dyslang Example Script</title></head>
    <body>
        <h1>Dyslang Example Functions</h1>
        <ul>
    """

    for name in globals():
        if name.startswith("_") or name == "wsgi":
            continue
        if callable(globals()[name]):
            html += f"<li><strong>{name}</strong>: {globals()[name].__doc__ or 'No documentation'}</li>\n"

    html += """
        </ul>
    </body>
    </html>
    """

    return [html.encode("utf-8")]
