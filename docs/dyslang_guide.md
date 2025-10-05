# Dyson Protocol Language Module Guide

This notebook provides a comprehensive guide to the Dyson Protocol Language Module (dyslang), which offers a secure and sandboxed Python execution environment on the blockchain. Through practical examples, we'll explore how to interact with the blockchain state, manage gas consumption, and leverage the powerful features of the `dys` module to build robust decentralized applications.

## Introduction to dyslang

The dyslang module serves as the backbone for on-chain Python execution in the Dyson Protocol. It provides a set of functions that enable scripts to:

- **Query Chain State**: Access account balances, contract data, and module parameters
- **Execute Transactions**: Send tokens, create contracts, and interact with other modules
- **Manage Resources**: Monitor gas consumption and execution limits
- **Access Context**: Retrieve information about the current script, executor, and block
- **Emit Events**: Produce blockchain events that can be indexed and monitored
- **Evaluate Code**: Execute dynamic Python code within a controlled environment

Let's dive into these features with practical examples.

## Setting Up

Before we start, let's set up our environment by defining our test accounts:


```python
# Get addresses of our test accounts
[ALICE_ADDRESS] = ! dysond keys show -a alice
[BOB_ADDRESS] = ! dysond keys show -a bob

print(f"Using alice address: {ALICE_ADDRESS}")
print(f"Using bob address: {BOB_ADDRESS}")
```

    Using alice address: dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej
    Using bob address: dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el


## Chain Interaction

The dyslang module provides two primary functions for interacting with the blockchain: `_query` and `_msg`.

- `_query`: Used to query the blockchain state (read-only operations)
- `_msg`: Used to submit transactions that modify the blockchain state

Let's explore these functions with practical examples.

### Querying Account Balances

One common operation is to query an account's balance. Let's create a script that queries the balance of an account:


```python
import json
import tempfile
import os

# Create a script that queries the account balance
query_script = '''
from dys import _query, get_script_address
import json

def query_balance():
    # Query the script's own balance
    script_address = get_script_address()
    response = _query({
        "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
        "address": script_address,
        "denom": "udys"
    })
    return response
'''

# Write the script to a temporary file and ensure it is deleted after use
with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=True) as f:
    f.write(query_script)
    f.flush()
    # Execute the script using dysond query script run
    out = ! dysond query script run --script-address {ALICE_ADDRESS} --executor-address {ALICE_ADDRESS} --function-name query_balance --extra-code-path {f.name} -o json
out = '\n'.join(out)
print(out)
result = json.loads(out)
json_result = json.loads(result['result'])['result']

assert 'balance' in json_result, "Balance not found in the result"
print(json.dumps(json_result['balance'], indent=2))
```

    {"result":"{\"cumsize\":6570,\"exception\":null,\"gas_limit\":18446744073709551615,\"nodes_called\":23,\"result\":{\"@type\":\"/cosmos.bank.v1beta1.QueryBalanceResponse\",\"balance\":{\"amount\":\"10000000000\",\"denom\":\"udys\"}},\"script_gas_consumed\":1013352,\"stdout\":\"\"}","attached_message_results":[]}
    {
      "amount": "10000000000",
      "denom": "udys"
    }


### Querying Multiple Account Balances

Let's create a more advanced script that queries the balances of multiple accounts:


```python
# Create a script that queries multiple account balances
import tempfile
import json

query_multi_script = f'''
from dys import _query
import json

def query_multiple_balances():
    # Define the addresses to query
    alice_address = "{ALICE_ADDRESS}"
    bob_address = "{BOB_ADDRESS}"
    
    # Query Alice's balance
    alice_balance = _query({{
        "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
        "address": alice_address,
        "denom": "udys"
    }})
    
    # Query Bob's balance
    bob_balance = _query({{
        "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
        "address": bob_address,
        "denom": "udys"
    }})
    
    # Return both balances
    return {{
        "alice_balance": alice_balance,
        "bob_balance": bob_balance
    }}
'''

# Write the script to a temporary file and ensure it is deleted after use
with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=True) as f:
    f.write(query_multi_script)
    f.flush()
    path = f.name
    # Execute the script using dysond query script exec
    out = ! dysond query script run --script-address {ALICE_ADDRESS} --executor-address {ALICE_ADDRESS} --function-name query_multiple_balances --extra-code-path {path} -o json
out = '\n'.join(out)
print(out)
result = json.loads(out)
json_result = json.loads(result['result'])['result']
assert 'alice_balance' in json_result, "Alice's balance not found in the result"
assert 'bob_balance' in json_result, "Bob's balance not found in the result"
print(json.dumps(json_result, indent=2))
```

    {"result":"{\"cumsize\":15368,\"exception\":null,\"gas_limit\":18446744073709551615,\"nodes_called\":39,\"result\":{\"alice_balance\":{\"@type\":\"/cosmos.bank.v1beta1.QueryBalanceResponse\",\"balance\":{\"amount\":\"10000000000\",\"denom\":\"udys\"}},\"bob_balance\":{\"@type\":\"/cosmos.bank.v1beta1.QueryBalanceResponse\",\"balance\":{\"amount\":\"10000000000\",\"denom\":\"udys\"}}},\"script_gas_consumed\":1023261,\"stdout\":\"\"}","attached_message_results":[]}
    {
      "alice_balance": {
        "@type": "/cosmos.bank.v1beta1.QueryBalanceResponse",
        "balance": {
          "amount": "10000000000",
          "denom": "udys"
        }
      },
      "bob_balance": {
        "@type": "/cosmos.bank.v1beta1.QueryBalanceResponse",
        "balance": {
          "amount": "10000000000",
          "denom": "udys"
        }
      }
    }


## Gas Management

In blockchain environments, computational resources are metered using a concept called "gas". The dyslang module provides several functions to help you monitor and manage gas consumption in your scripts.

### Monitoring Gas Consumption

Let's create a script that measures the gas consumed by various operations:


```python
# Create a script to benchmark gas consumption
gas_benchmark_script = '''
from dys import _query, get_gas_consumed, get_script_address, get_gas_limit
import json

def benchmark_gas(iterations=5):
    # Start tracking gas
    initial_gas = get_gas_consumed()
    
    # Perform a query that consumes gas
    script_address = get_script_address()
    balance_response = _query({
        "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
        "address": script_address,
        "denom": "udys"
    })
    
    # Check gas after query
    after_query_gas = get_gas_consumed()
    
    # Run some iterations to measure their gas cost
    for i in range(iterations):
        print(f"Iteration {i+1} of {iterations}")
    
    # Check final gas consumption
    final_gas = get_gas_consumed()
    
    # Calculate gas used by different operations
    query_gas = after_query_gas - initial_gas
    iterations_gas = final_gas - after_query_gas
    
    return {
        "initial_gas": initial_gas,
        "after_query_gas": after_query_gas,
        "final_gas": final_gas,
        "query_gas": query_gas,
        "iterations_gas": iterations_gas,
        "per_iteration": iterations_gas / iterations
    }
'''

# Save and execute the script
with open('/tmp/gas_benchmark.py', 'w') as f:
    f.write(gas_benchmark_script)

out = ! dysond query script run --script-address {ALICE_ADDRESS} --executor-address {ALICE_ADDRESS} --function-name benchmark_gas --extra-code-path /tmp/gas_benchmark.py -o json
out = '\n'.join(out)
print(out)
result = json.loads(out)

# Extract and display the gas measurements
gas_metrics = json.loads(result['result'])['result']
assert 'initial_gas' in gas_metrics, "Initial gas not found in the result: " + str(gas_metrics)
print(f"Gas report for benchmark operations:")
print(f"- Initial gas consumed: {gas_metrics['initial_gas']}")
print(f"- Gas after query: {gas_metrics['after_query_gas']}")
print(f"- Gas after iterations: {gas_metrics['final_gas']}")
print(f"- Total gas for query: {gas_metrics['query_gas']}")
print(f"- Total gas for iterations: {gas_metrics['iterations_gas']}")
print(f"- Average gas per iteration: {gas_metrics['per_iteration']}")
```

    {"result":"{\"cumsize\":75443,\"exception\":null,\"gas_limit\":18446744073709551615,\"nodes_called\":133,\"result\":{\"after_query_gas\":1017185,\"final_gas\":1061678,\"initial_gas\":1008377,\"iterations_gas\":44493,\"per_iteration\":8898.6,\"query_gas\":8808},\"script_gas_consumed\":1082225,\"stdout\":\"Iteration 1 of 5\\nIteration 2 of 5\\nIteration 3 of 5\\nIteration 4 of 5\\nIteration 5 of 5\\n\"}","attached_message_results":[]}
    Gas report for benchmark operations:
    - Initial gas consumed: 1008377
    - Gas after query: 1017185
    - Gas after iterations: 1061678
    - Total gas for query: 8808
    - Total gas for iterations: 44493
    - Average gas per iteration: 8898.6


### Gas Limits

Each execution has a gas limit to prevent infinite loops or excessive computation. Let's check the gas limit for our execution:


```python
# Create a script to check the gas limit
gas_limit_script = '''
from dys import get_gas_limit

def check_limit():
    # Check the gas limit for the current execution
    limit = get_gas_limit()
    return {"gas_limit": limit}
'''

# Save and execute the script
with open('/tmp/gas_limit.py', 'w') as f:
    f.write(gas_limit_script)

out = ! dysond query script run --script-address {ALICE_ADDRESS} --executor-address {ALICE_ADDRESS} --function-name check_limit --extra-code-path /tmp/gas_limit.py -o json
out = '\n'.join(out)
result = json.loads(out)

# Extract and display the gas limit 
gas_limit = json.loads(result['result'])['result']['gas_limit']
print(f"Gas limit for this execution: {gas_limit}")
```

    Gas limit for this execution: 18446744073709551615


### Node Execution Tracking

The dyslang module tracks the execution of Python AST nodes. This is useful for understanding the computational complexity of your scripts:


```python
# Create a script to measure node execution
node_count_script = '''
from dys import _query, get_nodes_called, get_script_address
import json

def count_nodes():
    """
    Demonstrate node counting by performing operations of varying complexity
    """
    # Simple operations
    a = 1 + 2
    
    # More complex operation that will use more nodes
    script_address = get_script_address()
    _query({
        "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
        "address": script_address,
        "denom": "udys"
    })
    
    # Complex calculation with loop
    result = 0
    for i in range(10):
        result += i * 2
    
    # Get the count of AST nodes evaluated
    nodes_called = get_nodes_called()
    
    return {
        "nodes_called": nodes_called,
        "calculation_result": result
    }
'''

# Save and execute the script
with open('/tmp/node_count.py', 'w') as f:
    f.write(node_count_script)

out = ! dysond query script run --script-address {ALICE_ADDRESS} --executor-address {ALICE_ADDRESS} --function-name count_nodes --extra-code-path /tmp/node_count.py -o json
out = '\n'.join(out)
result = json.loads(out)


# Extract and display the node metrics
node_metrics = json.loads(result['result'])['result']
assert 'nodes_called' in node_metrics, "Nodes called not found in the result: " + str(node_metrics)

print(f"Node execution metrics:")
print(f"- Nodes called: {node_metrics['nodes_called']}")
print(f"- Calculation result: {node_metrics['calculation_result']}")
```

    Node execution metrics:
    - Nodes called: 106
    - Calculation result: 90


### Memory Usage Tracking

The dyslang module also tracks memory usage through the `get_cumulative_size()` function:


```python
# Create a script to check memory usage
memory_script = '''
from dys import get_cumulative_size

def check_memory():
    # Check the cumulative memory size used
    size = get_cumulative_size()
    return {"memory_used": size}
'''

# Save and execute the script
with open('/tmp/memory_check.py', 'w') as f:
    f.write(memory_script)

out = ! dysond query script run --script-address {ALICE_ADDRESS} --executor-address {ALICE_ADDRESS} --function-name check_memory --extra-code-path /tmp/memory_check.py -o json
out = '\n'.join(out)
result = json.loads(out)

# Extract and display the memory usage
memory_used = json.loads(result['result'])['result']
assert 'memory_used' in memory_used, "Memory used not found in the result: " + str(memory_used)
print(f"Memory usage: {memory_used['memory_used']} bytes")
```

    Memory usage: 463 bytes


## Context Information

The dyslang module provides several functions to access contextual information about the current execution environment, including the script's address, the executor's address, and block information.

### Script and Executor Addresses

Let's create a script that retrieves information about the script's own address and the address of the account executing the script:


```python
# Create a script to get address information
address_script = '''
from dys import get_executor_address, get_script_address

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
        "is_self_call": is_self_call
    }
'''

# Save and execute the script
with open('/tmp/address_info.py', 'w') as f:
    f.write(address_script)

# Execute with Bob calling Alice's script
out = ! dysond query script run --script-address {ALICE_ADDRESS} --executor-address {ALICE_ADDRESS} --function-name who_called_me --extra-code-path /tmp/address_info.py -o json
out = '\n'.join(out)
print(out)
result = json.loads(out)


# Extract and display the address information
address_info = json.loads(result['result'])['result']
assert 'script_address' in address_info, "Script address not found in the result: " + str(address_info)
assert 'caller_address' in address_info, "Caller address not found in the result: " + str(address_info)
assert 'is_self_call' in address_info, "Is self call not found in the result: " + str(address_info)
print(f"Script Address: {address_info['script_address']}")
print(f"Executor Address: {address_info['caller_address']}")
print(f"Self-execution: {address_info['is_self_call']}")
```

    {"result":"{\"cumsize\":8798,\"exception\":null,\"gas_limit\":18446744073709551615,\"nodes_called\":27,\"result\":{\"caller_address\":\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\",\"is_self_call\":true,\"script_address\":\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"},\"script_gas_consumed\":1014469,\"stdout\":\"\"}","attached_message_results":[]}
    Script Address: dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej
    Executor Address: dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej
    Self-execution: True


### Block Information

Let's retrieve information about the current block:


```python
# Create a script to get block information
block_info_script = '''
from dys import get_block_info

def show_block_info():
    """Get basic block information"""
    block = get_block_info()
    return {
        "height": block.get("height"),
        "chain_id": block.get("chain_id"),
        "time": block.get("time")
    }
'''

# Save and execute the script
with open('/tmp/block_info.py', 'w') as f:
    f.write(block_info_script)

out = ! dysond query script run --script-address {ALICE_ADDRESS} --executor-address {ALICE_ADDRESS} --function-name show_block_info --extra-code-path /tmp/block_info.py -o json
out = '\n'.join(out)
result = json.loads(out)

# Extract and display the block information
block_info = json.loads(result['result'])['result']
assert 'height' in block_info and block_info['height'] is not None, "Height not found in the result: " + str(block_info)
assert 'chain_id' in block_info and block_info['chain_id'] is not None, "Chain ID not found in the result: " + str(block_info)
assert 'time' in block_info and block_info['time'] is not None, "Time not found in the result: " + str(block_info)
print(f"Block Information:")
print(f"- Height: {block_info['height']}")
print(f"- Chain ID: {block_info['chain_id']}")
print(f"- Time: {block_info['time']}")
```

    Block Information:
    - Height: 9
    - Chain ID: chain-a
    - Time: 2025-10-05T14:03:58.810332Z


## Transaction Data

The dyslang module allows scripts to access information about attached messages in transactions. This is particularly useful for scripts that need to process multiple operations in a single transaction.

### Attached Messages

Let's create a script that checks for attached messages:


```python
# Create a script to check for attached messages
import shlex
import json

msg1 = shlex.quote(json.dumps({
        "@type":"/cosmos.bank.v1beta1.MsgSend",
        "from_address": ALICE_ADDRESS,
        "to_address": BOB_ADDRESS,
        "amount":[{"denom":"udys","amount":"12"}]
    }))


msg2 = shlex.quote(json.dumps({
    "@type":"/cosmos.bank.v1beta1.MsgSend",
    "from_address": ALICE_ADDRESS   ,
    "to_address": BOB_ADDRESS,
    "amount":[{"denom":"udys","amount":"34"}]
}))

attached_msgs_script = '''
from dys import get_attached_messages, get_attached_msg_results

def check_messages():
    # Access attached messages
    attached_messages = get_attached_messages()
    attached_msg_results = get_attached_msg_results()
    return {"attached_messages": attached_messages, "attached_msg_results": attached_msg_results}
'''

# Save and execute the script
with open('/tmp/attached_msgs.py', 'w') as f:
    f.write(attached_msgs_script)

out = ! dysond query script run --script-address {ALICE_ADDRESS} --executor-address {ALICE_ADDRESS} --function-name check_messages --extra-code-path /tmp/attached_msgs.py -o json --attached-message {msg1} --attached-message {msg2} 

out = '\n'.join(out)
print(out)
result = json.loads(out)


# Extract and display the attached messages

results = json.loads(result['result'])['result']
print(results)
assert 'attached_messages' in results, "Attached messages not found in the result: " + str(results)
assert 'attached_msg_results' in results, "Attached msg results not found in the result: " + str(results)
for m, r in zip(results['attached_messages'], results['attached_msg_results']):
    print(f"Message: {m}")
    print(f"Result: {r}")
```

    {"result":"{\"cumsize\":12601,\"exception\":null,\"gas_limit\":18446744073709551615,\"nodes_called\":18,\"result\":{\"attached_messages\":[{\"@type\":\"/cosmos.bank.v1beta1.MsgSend\",\"amount\":[{\"amount\":\"12\",\"denom\":\"udys\"}],\"from_address\":\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\",\"to_address\":\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\"},{\"@type\":\"/cosmos.bank.v1beta1.MsgSend\",\"amount\":[{\"amount\":\"34\",\"denom\":\"udys\"}],\"from_address\":\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\",\"to_address\":\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\"}],\"attached_msg_results\":[{\"@type\":\"/cosmos.bank.v1beta1.MsgSendResponse\"},{\"@type\":\"/cosmos.bank.v1beta1.MsgSendResponse\"}]},\"script_gas_consumed\":1054963,\"stdout\":\"\"}","attached_message_results":[{"@type":"/cosmos.bank.v1beta1.MsgSendResponse"},{"@type":"/cosmos.bank.v1beta1.MsgSendResponse"}]}
    {'attached_messages': [{'@type': '/cosmos.bank.v1beta1.MsgSend', 'amount': [{'amount': '12', 'denom': 'udys'}], 'from_address': 'dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej', 'to_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el'}, {'@type': '/cosmos.bank.v1beta1.MsgSend', 'amount': [{'amount': '34', 'denom': 'udys'}], 'from_address': 'dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej', 'to_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el'}], 'attached_msg_results': [{'@type': '/cosmos.bank.v1beta1.MsgSendResponse'}, {'@type': '/cosmos.bank.v1beta1.MsgSendResponse'}]}
    Message: {'@type': '/cosmos.bank.v1beta1.MsgSend', 'amount': [{'amount': '12', 'denom': 'udys'}], 'from_address': 'dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej', 'to_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el'}
    Result: {'@type': '/cosmos.bank.v1beta1.MsgSendResponse'}
    Message: {'@type': '/cosmos.bank.v1beta1.MsgSend', 'amount': [{'amount': '34', 'denom': 'udys'}], 'from_address': 'dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej', 'to_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el'}
    Result: {'@type': '/cosmos.bank.v1beta1.MsgSendResponse'}


## Events and Evaluation

The dyslang module provides functions to emit blockchain events and evaluate dynamic code at runtime.

### Emitting Events

Let's create a script that emits a custom event to the blockchain:


```python
# Create a script to emit an event
emit_event_script = '''
from dys import emit_event

def emit_test_event():
    # Emit a custom event, none is a success or an exception is raised
    emit_event("payment_processed", "success")
    emit_event("foo", '123123')
    return {"event_emitted": True}
'''

# Save and execute the script
with open('/tmp/emit_event.py', 'w') as f:
    f.write(emit_event_script)


out = ! dysond tx script exec --script-address {ALICE_ADDRESS} --from {ALICE_ADDRESS} --function-name emit_test_event --extra-code-path /tmp/emit_event.py -y --gas "10000000" | dysond q wait-tx -o json
out = '\n'.join(out)
try:
    result = json.loads(out)
except json.JSONDecodeError:
    print("Error decoding JSON:", out)
    raise
# Quering script run does not emit events
print(json.dumps(result, indent=2))
# make the events more readable
events = {}
for e in result['events']:
    event_type = e['type']
    events.setdefault(event_type, {})
    for a in e['attributes']:
        events[event_type][a['key']] = a['value']
            
print(json.dumps(events, indent=2))
assert events['dysonprotocol.script.v1.EventScriptEvent']['key'] == '"foo"', "Event foo not found in the result: " + str(events)
assert events['dysonprotocol.script.v1.EventScriptEvent']['value'] == '"123123"', "Event value not found in the result: " + str(events)
```

    {
      "height": "12",
      "txhash": "07CA48632DAFD22BD80387C8E3236CF6ECFBD02CBC76D254FC95988B4D1FEDFB",
      "codespace": "",
      "code": 0,
      "data": "12C2010A282F6479736F6E70726F746F636F6C2E7363726970742E76312E4D736745786563526573706F6E73651295010A92017B2263756D73697A65223A323431362C22657863657074696F6E223A6E756C6C2C226761735F6C696D6974223A31303030303030302C226E6F6465735F63616C6C6564223A31372C22726573756C74223A7B226576656E745F656D6974746564223A747275657D2C227363726970745F6761735F636F6E73756D6564223A313035323332332C227374646F7574223A22227D",
      "raw_log": "",
      "logs": [],
      "info": "",
      "gas_wanted": "10000000",
      "gas_used": "1052323",
      "tx": null,
      "timestamp": "",
      "events": [
        {
          "type": "tx",
          "attributes": [
            {
              "key": "acc_seq",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/0",
              "index": true
            }
          ]
        },
        {
          "type": "tx",
          "attributes": [
            {
              "key": "signature",
              "value": "yxrrjbGGLzn09Jqc6e9SLE+Jy1g6wVhIezi8RjWOp2ESxV+75TvJFP/FuqK5L5RO56wvTn6y7bM5dGapJA/ocg==",
              "index": true
            }
          ]
        },
        {
          "type": "message",
          "attributes": [
            {
              "key": "action",
              "value": "/dysonprotocol.script.v1.MsgExec",
              "index": true
            },
            {
              "key": "sender",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
              "index": true
            },
            {
              "key": "module",
              "value": "script",
              "index": true
            },
            {
              "key": "msg_index",
              "value": "0",
              "index": true
            }
          ]
        },
        {
          "type": "dysonprotocol.script.v1.EventScriptEvent",
          "attributes": [
            {
              "key": "address",
              "value": "\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"",
              "index": true
            },
            {
              "key": "key",
              "value": "\"payment_processed\"",
              "index": true
            },
            {
              "key": "value",
              "value": "\"success\"",
              "index": true
            },
            {
              "key": "msg_index",
              "value": "0",
              "index": true
            }
          ]
        },
        {
          "type": "dysonprotocol.script.v1.EventScriptEvent",
          "attributes": [
            {
              "key": "address",
              "value": "\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"",
              "index": true
            },
            {
              "key": "key",
              "value": "\"foo\"",
              "index": true
            },
            {
              "key": "value",
              "value": "\"123123\"",
              "index": true
            },
            {
              "key": "msg_index",
              "value": "0",
              "index": true
            }
          ]
        },
        {
          "type": "dysonprotocol.script.v1.EventExecScript",
          "attributes": [
            {
              "key": "executor_address",
              "value": "\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"",
              "index": true
            },
            {
              "key": "function_name",
              "value": "\"emit_test_event\"",
              "index": true
            },
            {
              "key": "request",
              "value": "{\"executor_address\":\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\",\"script_address\":\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\",\"script_name\":\"\",\"extra_code\":\"\\nfrom dys import emit_event\\n\\ndef emit_test_event():\\n    # Emit a custom event, none is a success or an exception is raised\\n    emit_event(\\\"payment_processed\\\", \\\"success\\\")\\n    emit_event(\\\"foo\\\", '123123')\\n    return {\\\"event_emitted\\\": True}\\n\",\"function_name\":\"emit_test_event\",\"args\":\"\",\"kwargs\":\"\",\"attached_messages\":[]}",
              "index": true
            },
            {
              "key": "response",
              "value": "{\"result\":\"{\\\"cumsize\\\":2416,\\\"exception\\\":null,\\\"gas_limit\\\":10000000,\\\"nodes_called\\\":17,\\\"result\\\":{\\\"event_emitted\\\":true},\\\"script_gas_consumed\\\":1052323,\\\"stdout\\\":\\\"\\\"}\",\"attached_message_results\":[]}",
              "index": true
            },
            {
              "key": "script_address",
              "value": "\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"",
              "index": true
            },
            {
              "key": "script_name",
              "value": "\"\"",
              "index": true
            },
            {
              "key": "msg_index",
              "value": "0",
              "index": true
            }
          ]
        }
      ]
    }
    {
      "tx": {
        "acc_seq": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/0",
        "signature": "yxrrjbGGLzn09Jqc6e9SLE+Jy1g6wVhIezi8RjWOp2ESxV+75TvJFP/FuqK5L5RO56wvTn6y7bM5dGapJA/ocg=="
      },
      "message": {
        "action": "/dysonprotocol.script.v1.MsgExec",
        "sender": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
        "module": "script",
        "msg_index": "0"
      },
      "dysonprotocol.script.v1.EventScriptEvent": {
        "address": "\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"",
        "key": "\"foo\"",
        "value": "\"123123\"",
        "msg_index": "0"
      },
      "dysonprotocol.script.v1.EventExecScript": {
        "executor_address": "\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"",
        "function_name": "\"emit_test_event\"",
        "request": "{\"executor_address\":\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\",\"script_address\":\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\",\"script_name\":\"\",\"extra_code\":\"\\nfrom dys import emit_event\\n\\ndef emit_test_event():\\n    # Emit a custom event, none is a success or an exception is raised\\n    emit_event(\\\"payment_processed\\\", \\\"success\\\")\\n    emit_event(\\\"foo\\\", '123123')\\n    return {\\\"event_emitted\\\": True}\\n\",\"function_name\":\"emit_test_event\",\"args\":\"\",\"kwargs\":\"\",\"attached_messages\":[]}",
        "response": "{\"result\":\"{\\\"cumsize\\\":2416,\\\"exception\\\":null,\\\"gas_limit\\\":10000000,\\\"nodes_called\\\":17,\\\"result\\\":{\\\"event_emitted\\\":true},\\\"script_gas_consumed\\\":1052323,\\\"stdout\\\":\\\"\\\"}\",\"attached_message_results\":[]}",
        "script_address": "\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"",
        "script_name": "\"\"",
        "msg_index": "0"
      }
    }


### Dynamic Code Evaluation

The `dys_eval` function allows you to evaluate Python code dynamically at runtime. This is a powerful feature that enables creating flexible and adaptable scripts:


```python
# Create a script for dynamic code evaluation
dys_eval_script = '''
from dys import dys_eval

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
    local_scope = {'x': x, 'y': y}
    results["with_variables"] = dys_eval("x * y", scope=local_scope)
    
    # Multiple statements
    results["multi_statement"] = dys_eval("""
a = 5
b = 7
result = a * b
result + 3
""")
    
    return results
'''

# Save and execute the script
with open('/tmp/dys_eval.py', 'w') as f:
    f.write(dys_eval_script)

out = ! dysond q script run --script-address {ALICE_ADDRESS} --executor-address {ALICE_ADDRESS} --function-name demonstrate_dys_eval --extra-code-path /tmp/dys_eval.py -o json
out = '\n'.join(out)
json_out = json.loads(out)
print(json.dumps(json_out, indent=2))
# Extract and display the evaluation results
eval_results = json.loads(json_out['result'])['result']
print(f"Dynamic evaluation results:")
print(f"- Arithmetic: {eval_results['arithmetic']}")
print(f"- String operations: {eval_results['string_ops']}")
print(f"- With variables: {eval_results['with_variables']}")
print(f"- Multi-statement: {eval_results['multi_statement']}")
```

    {
      "result": "{\"cumsize\":12729,\"exception\":null,\"gas_limit\":18446744073709551615,\"nodes_called\":84,\"result\":{\"arithmetic\":14,\"multi_statement\":38,\"string_ops\":\"hello WORLD\",\"with_variables\":50},\"script_gas_consumed\":1014997,\"stdout\":\"\"}",
      "attached_message_results": []
    }
    Dynamic evaluation results:
    - Arithmetic: 14
    - String operations: hello WORLD
    - With variables: 50
    - Multi-statement: 38


## Testing and Coverage

The dyslang module includes built-in tools for testing and code coverage analysis. By prefixing function names with `test_`, you can enable coverage mode, which provides detailed information about which parts of your code are being executed.

### Code Coverage Analysis

Let's create a script with a test function to demonstrate code coverage analysis:


```python
# Get Charlie's address
[CHARLIE_ADDRESS] = ! dysond keys show -a charlie

# Create a script with test coverage
coverage_script = '''
def a_or_b(a, b):
    if a:
        return a
    if b:
        return b
    return None

def test_a_or_b():
    # Test with different inputs
    a_or_b(1, 0)  # Should return a
    a_or_b(1, 1)  # Should still return a (first condition)
    # Note: We're not testing the b condition or the fallback
'''

# Save and execute the script
with open('/tmp/coverage_test.py', 'w') as f:
    f.write(coverage_script)

out = ! dysond q script run --script-address {CHARLIE_ADDRESS} --executor-address {CHARLIE_ADDRESS} --function-name test_a_or_b --extra-code-path /tmp/coverage_test.py -o json
out = '\n'.join(out)
json_out = json.loads(out)
print(json.loads(json_out['result']))
# Extract and interpret the coverage data
coverage_data = json.loads(json_out['result'])['result']

```

    {'cumsize': 2794, 'exception': None, 'gas_limit': 18446744073709551615, 'nodes_called': 23, 'result': [[[3, 0, 8, 15, 'FunctionDef', ''], [1, 68]], [[3, 11, 3, 12, 'arg', ''], [2, 96]], [[3, 14, 3, 15, 'arg', ''], [2, 96]], [[4, 4, 5, 16, 'If', ''], [2, 288]], [[4, 7, 4, 8, 'Name', ''], [2, 288]], [[5, 8, 5, 16, 'Return', ''], [2, 288]], [[5, 15, 5, 16, 'Name', ''], [2, 288]], [[6, 4, 7, 16, 'If', ''], [0, 0]], [[6, 7, 6, 8, 'Name', ''], [0, 0]], [[7, 8, 7, 16, 'Return', ''], [0, 0]], [[7, 15, 7, 16, 'Name', ''], [0, 0]], [[8, 4, 8, 15, 'Return', ''], [0, 0]], [[8, 11, 8, 15, 'Constant', ''], [0, 0]], [[10, 0, 13, 16, 'FunctionDef', ''], [1, 117]], [[12, 4, 12, 16, 'Expr', ''], [1, 128]], [[12, 4, 12, 16, 'Call', ''], [1, 128]], [[12, 4, 12, 10, 'Name', ''], [1, 154]], [[12, 11, 12, 12, 'Constant', ''], [1, 128]], [[12, 14, 12, 15, 'Constant', ''], [1, 128]], [[13, 4, 13, 16, 'Expr', ''], [1, 128]], [[13, 4, 13, 16, 'Call', ''], [1, 128]], [[13, 4, 13, 10, 'Name', ''], [1, 154]], [[13, 11, 13, 12, 'Constant', ''], [1, 128]], [[13, 14, 13, 15, 'Constant', ''], [1, 128]]], 'script_gas_consumed': 1008465, 'stdout': ''}



```python
# Display a simplified analysis of the coverage data
print("Coverage Analysis Results:")
for item in coverage_data:
    node_info = item[0]
    count, memory_usage = item[1]
    line = node_info[0]
    node_type = node_info[4]
    
    # Simplify the coverage output for key lines
    if node_type == "FunctionDef" and line == 3:
        print(f"- FunctionDef (a_or_b): executed {count} time{'s' if count != 1 else ''} and used {memory_usage} bytes of memory")
    elif node_type == "If" and line == 4:
        print(f"- If (line {line}): {f'executed {count} times' if count > 0 else 'never executed'} and used {memory_usage} bytes of memory")
    elif node_type == "If" and line == 6:
        print(f"- If (line {line}): {f'executed {count} times' if count > 0 else 'never executed'} and used {memory_usage} bytes of memory")
    elif node_type == "Return" and line == 5:
        print(f"- Return (line {line}): {f'executed {count} times' if count > 0 else 'never executed'} and used {memory_usage} bytes of memory")
    elif node_type == "Return" and line == 7:
        print(f"- Return (line {line}): {f'executed {count} times' if count > 0 else 'never executed'} and used {memory_usage} bytes of memory")
    elif node_type == "Return" and line == 8:
        print(f"- Return (fallback): {f'executed {count} times' if count > 0 else 'never executed'} and used {memory_usage} bytes of memory")
assert len(coverage_data) > 0, "Coverage data should be greater than 0"
```

    Coverage Analysis Results:
    - FunctionDef (a_or_b): executed 1 time and used 68 bytes of memory
    - If (line 4): executed 2 times and used 288 bytes of memory
    - Return (line 5): executed 2 times and used 288 bytes of memory
    - If (line 6): never executed and used 0 bytes of memory
    - Return (line 7): never executed and used 0 bytes of memory
    - Return (fallback): never executed and used 0 bytes of memory


From the coverage analysis, we can see that:

1. The `a_or_b` function was defined (executed once)
2. The first `if` condition (line 4) was evaluated twice and passed both times
3. The first `return` statement (line 5) was executed twice
4. The second `if` condition (line 6) was never evaluated because the first condition always passed
5. The second `return` statement (line 7) was never executed
6. The fallback `return None` (line 8) was never executed

This coverage analysis helps us identify test gaps in our code. In this case, we need to add tests for when the first condition fails to ensure we're testing all code paths.

# Available Modules and Functions

These are the available modules and functions that can be used in dyslang scripts.


<div><h3>Available Modules</h3><h4>ast</h4><ul><li><code>ClassDef</code>: ClassDef(identifier name, expr* bases, keyword* keywords, stmt* body, expr* decorator_list, type_param* type_params)</li><li><code>FunctionDef</code>: FunctionDef(identifier name, arguments args, stmt* body, expr* decorator_list, expr? returns, string? type_comment, type_param* type_params)</li><li><code>NodeTransformer</code>: A :class:`NodeVisitor` subclass that walks the abstract syntax tree and
allows modification of nodes.

The `NodeTransformer` will walk the AST and use the return value of the
visitor methods to replace or remove the old node.  If the return value of
the visitor method is ``None``, the node will be removed from its location,
otherwise it is replaced with the return value.  The return value may be the
original node in which case no replacement takes place.

Here is an example transformer that rewrites all occurrences of name lookups
(``foo``) to ``data['foo']``::

   class RewriteName(NodeTransformer):

       def visit_Name(self, node):
           return Subscript(
               value=Name(id='data', ctx=Load()),
               slice=Constant(value=node.id),
               ctx=node.ctx
           )

Keep in mind that if the node you're operating on has child nodes you must
either transform the child nodes yourself or call the :meth:`generic_visit`
method for the node first.

For nodes that were part of a collection of statements (that applies to all
statement nodes), the visitor may also return a list of nodes rather than
just a single node.

Usually you use the transformer like this::

   node = YourTransformer().visit(node)</li><li><code>NodeVisitor</code>: A node visitor base class that walks the abstract syntax tree and calls a
visitor function for every node found.  This function may return a value
which is forwarded by the `visit` method.

This class is meant to be subclassed, with the subclass adding visitor
methods.

Per default the visitor functions for the nodes are ``'visit_'`` +
class name of the node.  So a `TryFinally` node visit function would
be `visit_TryFinally`.  This behavior can be changed by overriding
the `visit` method.  If no visitor function exists for a node
(return value `None`) the `generic_visit` visitor is used instead.

Don't use the `NodeVisitor` if you want to apply changes to nodes during
traversing.  For this a special visitor exists (`NodeTransformer`) that
allows modifications.</li><li><code>dump</code>: Return a formatted dump of the tree in node.  This is mainly useful for
debugging purposes.  If annotate_fields is true (by default),
the returned string will show the names and the values for fields.
If annotate_fields is false, the result string will be more compact by
omitting unambiguous field names.  Attributes such as line
numbers and column offsets are not dumped by default.  If this is wanted,
include_attributes can be set to true.  If indent is a non-negative
integer or string, then the tree will be pretty-printed with that indent
level. None (the default) selects the single line representation.</li><li><code>fix_missing_locations</code>: When you compile a node tree with compile(), the compiler expects lineno and
col_offset attributes for every node that supports them.  This is rather
tedious to fill in for generated nodes, so this helper adds these attributes
recursively where not already set, by setting them to the values of the
parent node.  It works recursively starting at *node*.</li><li><code>get_docstring</code>: Return the docstring for the given node or None if no docstring can
be found.  If the node provided does not have docstrings a TypeError
will be raised.

If *clean* is `True`, all tabs are expanded to spaces and any whitespace
that can be uniformly removed from the second line onwards is removed.</li><li><code>get_source_segment</code>: Get source code segment of the *source* that generated *node*.

    If some location information (`lineno`, `end_lineno`, `col_offset`,
    or `end_col_offset`) is missing, return None.

    If *padded* is `True`, the first line of a multi-line statement will
    be padded with spaces to match its original position.</li><li><code>literal_eval</code>: Evaluate an expression node or a string containing only a Python
expression.  The string or node provided may only consist of the following
Python literal structures: strings, bytes, numbers, tuples, lists, dicts,
sets, booleans, and None.

Caution: A complex expression can overflow the C stack and cause a crash.</li><li><code>parse</code>: Parse the source into an AST node.
Equivalent to compile(source, filename, mode, PyCF_ONLY_AST).
Pass type_comments=True to get back type comments where the syntax allows.</li><li><code>unparse</code>: </li><li><code>walk</code>: Recursively yield all descendant nodes in the tree starting at *node*
(including *node* itself), in no specified order.  This is useful if you
only want to modify nodes in place and don't care about the context.</li></ul><h4>base64</h4><ul><li><code>b64decode</code>: Decode the Base64 encoded bytes-like object or ASCII string s.

    Optional altchars must be a bytes-like object or ASCII string of length 2
    which specifies the alternative alphabet used instead of the '+' and '/'
    characters.

    The result is returned as a bytes object.  A binascii.Error is raised if
    s is incorrectly padded.

    If validate is False (the default), characters that are neither in the
    normal base-64 alphabet nor the alternative alphabet are discarded prior
    to the padding check.  If validate is True, these non-alphabet characters
    in the input result in a binascii.Error.
    For more information about the strict base64 check, see:

    https://docs.python.org/3.11/library/binascii.html#binascii.a2b_base64</li><li><code>b64encode</code>: Encode the bytes-like object s using Base64 and return a bytes object.

    Optional altchars should be a byte string of length 2 which specifies an
    alternative alphabet for the '+' and '/' characters.  This allows an
    application to e.g. generate url or filesystem safe Base64 strings.</li><li><code>decodebytes</code>: Decode a bytestring of base-64 data into a bytes object.</li><li><code>encodebytes</code>: Encode a bytestring into a bytes object containing multiple lines
    of base-64 data.</li><li><code>urlsafe_b64decode</code>: Decode bytes using the URL- and filesystem-safe Base64 alphabet.

    Argument s is a bytes-like object or ASCII string to decode.  The result
    is returned as a bytes object.  A binascii.Error is raised if the input
    is incorrectly padded.  Characters that are not in the URL-safe base-64
    alphabet, and are not a plus '+' or slash '/', are discarded prior to the
    padding check.

    The alphabet uses '-' instead of '+' and '_' instead of '/'.</li><li><code>urlsafe_b64encode</code>: Encode bytes using the URL- and filesystem-safe Base64 alphabet.

    Argument s is a bytes-like object to encode.  The result is returned as a
    bytes object.  The alphabet uses '-' instead of '+' and '_' instead of
    '/'.</li></ul><h4>bencoder</h4><ul><li><code>decode</code>: Decodes *bdata* back to a Python object.

    Parameters
    ----------
    bdata : ``bytes`` | ``str``
        The B‑encoded payload.
    strict_bytes : bool, default ``False``
        * ``False`` (default) – try UTF‑8 decode; if it succeeds return ``str``.
        * ``True``  – **always** return raw ``bytes`` even if the payload is
          valid UTF‑8. This lets callers disambiguate the type when needed.</li><li><code>encode</code>: B‑encodes *obj*.

    Supported types: ``None``, ``bool``, ``int``, ``float``, ``bytes``,
    ``bytearray``, ``str``, ``list``, ``tuple``, ``set``, ``frozenset``, ``dict``.

    For ``dict`` keys only ``bytes`` or ``str`` are allowed; ``str`` keys are
    UTF‑8 encoded automatically. Keys are sorted lexicographically (byte order)
    to guarantee deterministic output.</li></ul><h4>dataclasses</h4><ul><li><code>asdict</code>: Return the fields of a dataclass instance as a new dictionary mapping
    field names to field values.

    Example usage::

      @dataclass
      class C:
          x: int
          y: int

      c = C(1, 2)
      assert asdict(c) == {'x': 1, 'y': 2}

    If given, 'dict_factory' will be used instead of built-in dict.
    The function applies recursively to field values that are
    dataclass instances. This will also look into built-in containers:
    tuples, lists, and dicts. Other objects are copied with 'copy.deepcopy()'.</li><li><code>astuple</code>: Return the fields of a dataclass instance as a new tuple of field values.

    Example usage::

      @dataclass
      class C:
          x: int
          y: int

      c = C(1, 2)
      assert astuple(c) == (1, 2)

    If given, 'tuple_factory' will be used instead of built-in tuple.
    The function applies recursively to field values that are
    dataclass instances. This will also look into built-in containers:
    tuples, lists, and dicts. Other objects are copied with 'copy.deepcopy()'.</li><li><code>dataclass</code>: Add dunder methods based on the fields defined in the class.

    Examines PEP 526 __annotations__ to determine fields.

    If init is true, an __init__() method is added to the class. If repr
    is true, a __repr__() method is added. If order is true, rich
    comparison dunder methods are added. If unsafe_hash is true, a
    __hash__() method is added. If frozen is true, fields may not be
    assigned to after instance creation. If match_args is true, the
    __match_args__ tuple is added. If kw_only is true, then by default
    all fields are keyword-only. If slots is true, a new class with a
    __slots__ attribute is returned.</li><li><code>field</code>: Return an object to identify dataclass fields.

    default is the default value of the field.  default_factory is a
    0-argument function called to initialize a field's value.  If init
    is true, the field will be a parameter to the class's __init__()
    function.  If repr is true, the field will be included in the
    object's repr().  If hash is true, the field will be included in the
    object's hash().  If compare is true, the field will be used in
    comparison functions.  metadata, if specified, must be a mapping
    which is stored but not otherwise examined by dataclass.  If kw_only
    is true, the field will become a keyword-only parameter to
    __init__().

    It is an error to specify both default and default_factory.</li></ul><h4>datetime</h4><ul><li><code>UTC</code>: Fixed offset from UTC implementation of tzinfo.</li><li><code>date</code>: date(year, month, day) --&gt; date object</li><li><code>datetime</code>: datetime(year, month, day[, hour[, minute[, second[, microsecond[,tzinfo]]]]])

The year, month and day arguments are required. tzinfo may be None, or an
instance of a tzinfo subclass. The remaining arguments may be ints.</li><li><code>time</code>: time([hour[, minute[, second[, microsecond[, tzinfo]]]]]) --&gt; a time object

All arguments are optional. tzinfo may be None, or an instance of
a tzinfo subclass. The remaining arguments may be ints.</li><li><code>timedelta</code>: Difference between two datetime values.

timedelta(days=0, seconds=0, microseconds=0, milliseconds=0, minutes=0, hours=0, weeks=0)

All arguments are optional and default to 0.
Arguments may be integers or floats, and may be positive or negative.</li><li><code>timezone</code>: Fixed offset from UTC implementation of tzinfo.</li><li><code>tzinfo</code>: Abstract base class for time zone info objects.</li></ul><h4>decimal</h4><ul><li><code>Decimal</code>: Construct a new Decimal object. 'value' can be an integer, string, tuple,
or another Decimal object. If no value is given, return Decimal('0'). The
context does not affect the conversion and is only passed to determine if
the InvalidOperation trap is active.</li><li><code>ROUND_05UP</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li><li><code>ROUND_CEILING</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li><li><code>ROUND_DOWN</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li><li><code>ROUND_FLOOR</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li><li><code>ROUND_HALF_DOWN</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li><li><code>ROUND_HALF_EVEN</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li><li><code>ROUND_HALF_UP</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li><li><code>ROUND_UP</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li></ul><h4>dys</h4><ul><li><code>DysMsgException</code>: Used for dysvm _msg exceptions.</li><li><code>DysQueryException</code>: Used for dysvm _query exceptions.</li><li><code>_chain</code>: DEPRECATED: Use _msg() and _query() functions instead.

:raises DeprecationError: Always raises this error to encourage migration to _msg and _query</li><li><code>_msg</code>: Wrapper function for _chain("Msg") that JSON encodes the params argument.

:param params: A dictionary of parameters to be JSON encoded and passed to _chain
:returns: The response from the chain</li><li><code>_query</code>: Wrapper function for _chain("Query") that JSON encodes the params argument.

:param params: A dictionary of parameters to be JSON encoded and passed to _chain
:returns: The response from the chain</li><li><code>dys_eval</code>: Evaluate a string of Dsyon Protocol code.

:param code: the code to evaluate
:param scope: the scope to evaluate the code in
:param track_func: a function to call after each node is evaluated use to track gas or scope size
:param module_dict: a dictionary of modules to make available for import in the sandbox.
                    Keys are module names, values are dicts of attributes.
                    Example: {"json": {"loads": json.loads}, "foo": {"bar": my_custom_func}}

:returns: the result of the evaluation</li><li><code>emit_event</code>: Emits an event to the blockchain.

:param key: the key of the event (string)
:param value: the value of the event (string)

:returns: the response from the chain</li><li><code>get_attached_messages</code>: Returns the nfts sent to this function.</li><li><code>get_attached_msg_results</code>: Returns the results of the attached messages.</li><li><code>get_block_info</code>: Returns a dictionary containing the following block header information:
- Height (int): The height of the block
- Hash (bytes): The hash of the block header
- Time (string): The time of the block in ISO format
- AppHash (bytes): AppHash used in the current block header
- ChainID (string): The chain ID of the block</li><li><code>get_cumulative_size</code>: The cumulative size of memory used for each node called in this query or script</li><li><code>get_executor_address</code>: Returns the address of the caller of this script.</li><li><code>get_gas_consumed</code>: The total amount of gas consumed so far.</li><li><code>get_gas_limit</code>: The maximum amount of gas that can be used in this query or transaction</li><li><code>get_nodes_called</code>: The number of Python AST nodes evaluated in this query or transaction</li><li><code>get_script_address</code>: Returns the address of this current script.</li><li><code>get_script_code</code>: Returns the source code of this current script.</li><li><code>get_script_name</code>: Returns the script name used in the execution message, if provided.
Returns empty string if not provided.</li><li><code>get_script_version</code>: Returns the version of this current script.</li><li><code>list_functions</code>: Returns a copy of the set of whitelisted functions available in the Dyson Protocol environment.</li><li><code>list_modules</code>: Returns a dictionary of available modules and their functions in the Dyson Protocol environment.
The returned dictionary has module names as keys and lists of available functions as values.</li></ul><h4>enum</h4><ul><li><code>Enum</code>: Create a collection of name/value pairs.

Example enumeration:

&gt;&gt;&gt; class Color(Enum):
...     RED = 1
...     BLUE = 2
...     GREEN = 3

Access them by:

- attribute access:

  &gt;&gt;&gt; Color.RED
  &lt;Color.RED: 1&gt;

- value lookup:

  &gt;&gt;&gt; Color(1)
  &lt;Color.RED: 1&gt;

- name lookup:

  &gt;&gt;&gt; Color['RED']
  &lt;Color.RED: 1&gt;

Enumerations can be iterated over, and know how many members they have:

&gt;&gt;&gt; len(Color)
3

&gt;&gt;&gt; list(Color)
[&lt;Color.RED: 1&gt;, &lt;Color.BLUE: 2&gt;, &lt;Color.GREEN: 3&gt;]

Methods can be added to enumerations, and members can have their own
attributes -- see the documentation for details.</li><li><code>EnumType</code>: Metaclass for Enum</li><li><code>IntEnum</code>: Enum where members are also (and must be) ints</li><li><code>StrEnum</code>: Enum where members are also (and must be) strings</li></ul><h4>function_schema</h4><ul><li><code>Doc</code>: Define the documentation of a type annotation using ``Annotated``, to be
         used in class attributes, function and method parameters, return values,
         and variables.

        The value should be a positional-only string literal to allow static tools
        like editors and documentation generators to use it.

        This complements docstrings.

        The string value passed is available in the attribute ``documentation``.

        Example::

            &gt;&gt;&gt; from typing_extensions import Annotated, Doc
            &gt;&gt;&gt; def hi(to: Annotated[str, Doc("Who to say hi to")]) -&gt; None: ...</li><li><code>get_function_schema</code>: Returns a JSON schema for the given function.

You can annotate your function parameters with the special Annotated type.
Then get the schema for the function without writing the schema by hand.

Especially useful for OpenAI API function-call.

Example:
&gt;&gt;&gt; from typing import Annotated, Optional
&gt;&gt;&gt; import enum
&gt;&gt;&gt; def get_weather(
...     city: Annotated[str, Doc("The city to get the weather for")],
...     unit: Annotated[
...         Optional[str],
...         Doc("The unit to return the temperature in"),
...         enum.Enum("Unit", "celcius fahrenheit")
...     ] = "celcius",
... ) -&gt; str:
...     """Returns the weather for the given city."""
...     return f"Hello {name}, you are {age} years old."
&gt;&gt;&gt; get_function_schema(get_weather) # doctest: +SKIP
{
    'name': 'get_weather',
    'description': 'Returns the weather for the given city.',
    'parameters': {
        'type': 'object',
        'properties': {
            'city': {
                'type': 'string',
                'description': 'The city to get the weather for'
            },
            'unit': {
                'type': 'string',
                'description': 'The unit to return the temperature in',
                'enum': ['celcius', 'fahrenheit'],
                'default': 'celcius'
            }
        },
        'required': ['city']
    }
}</li></ul><h4>hashlib</h4><ul><li><code>md5</code>: Returns a md5 hash object; optionally initialized with a string</li><li><code>sha1</code>: Returns a sha1 hash object; optionally initialized with a string</li><li><code>sha256</code>: Returns a sha256 hash object; optionally initialized with a string</li><li><code>sha512</code>: Returns a sha512 hash object; optionally initialized with a string</li></ul><h4>html</h4><ul><li><code>escape</code>: Replace special characters "&amp;", "&lt;" and "&gt;" to HTML-safe sequences.
If the optional flag quote is true (the default), the quotation mark
characters, both double quote (") and single quote (') characters are also
translated.</li><li><code>unescape</code>: Convert all named and numeric character references (e.g. &amp;gt;, &amp;#62;,
&amp;x3e;) in the string s to the corresponding unicode characters.
This function uses the rules defined by the HTML 5 standard
for both valid and invalid character references, and the list of
HTML 5 named character references defined in html.entities.html5.</li></ul><h4>io</h4><ul><li><code>BytesIO</code>: Buffered I/O implementation using an in-memory bytes buffer.</li><li><code>StringIO</code>: Text I/O implementation using an in-memory buffer.

The initial_value argument sets the value of object.  The newline
argument is like the one of TextIOWrapper's constructor.</li></ul><h4>json</h4><ul><li><code>JSONDecodeError</code>: Subclass of ValueError with the following additional properties:

    msg: The unformatted error message
    doc: The JSON document being parsed
    pos: The start index of doc where parsing failed
    lineno: The line corresponding to pos
    colno: The column corresponding to pos</li><li><code>dumps</code>: Serialize ``obj`` to a JSON formatted ``str``.

    If ``skipkeys`` is true then ``dict`` keys that are not basic types
    (``str``, ``int``, ``float``, ``bool``, ``None``) will be skipped
    instead of raising a ``TypeError``.

    If ``ensure_ascii`` is false, then the return value can contain non-ASCII
    characters if they appear in strings contained in ``obj``. Otherwise, all
    such characters are escaped in JSON strings.

    If ``check_circular`` is false, then the circular reference check
    for container types will be skipped and a circular reference will
    result in an ``RecursionError`` (or worse).

    If ``allow_nan`` is false, then it will be a ``ValueError`` to
    serialize out of range ``float`` values (``nan``, ``inf``, ``-inf``) in
    strict compliance of the JSON specification, instead of using the
    JavaScript equivalents (``NaN``, ``Infinity``, ``-Infinity``).

    If ``indent`` is a non-negative integer, then JSON array elements and
    object members will be pretty-printed with that indent level. An indent
    level of 0 will only insert newlines. ``None`` is the most compact
    representation.

    If specified, ``separators`` should be an ``(item_separator, key_separator)``
    tuple.  The default is ``(', ', ': ')`` if *indent* is ``None`` and
    ``(',', ': ')`` otherwise.  To get the most compact JSON representation,
    you should specify ``(',', ':')`` to eliminate whitespace.

    ``default(obj)`` is a function that should return a serializable version
    of obj or raise TypeError. The default simply raises TypeError.

    If *sort_keys* is true (default: ``False``), then the output of
    dictionaries will be sorted by key.

    To use a custom ``JSONEncoder`` subclass (e.g. one that overrides the
    ``.default()`` method to serialize additional types), specify it with
    the ``cls`` kwarg; otherwise ``JSONEncoder`` is used.</li><li><code>loads</code>: Deserialize ``s`` (a ``str``, ``bytes`` or ``bytearray`` instance
    containing a JSON document) to a Python object.

    ``object_hook`` is an optional function that will be called with the
    result of any object literal decode (a ``dict``). The return value of
    ``object_hook`` will be used instead of the ``dict``. This feature
    can be used to implement custom decoders (e.g. JSON-RPC class hinting).

    ``object_pairs_hook`` is an optional function that will be called with the
    result of any object literal decoded with an ordered list of pairs.  The
    return value of ``object_pairs_hook`` will be used instead of the ``dict``.
    This feature can be used to implement custom decoders.  If ``object_hook``
    is also defined, the ``object_pairs_hook`` takes priority.

    ``parse_float``, if specified, will be called with the string
    of every JSON float to be decoded. By default this is equivalent to
    float(num_str). This can be used to use another datatype or parser
    for JSON floats (e.g. decimal.Decimal).

    ``parse_int``, if specified, will be called with the string
    of every JSON int to be decoded. By default this is equivalent to
    int(num_str). This can be used to use another datatype or parser
    for JSON integers (e.g. float).

    ``parse_constant``, if specified, will be called with one of the
    following strings: -Infinity, Infinity, NaN.
    This can be used to raise an exception if invalid JSON numbers
    are encountered.

    To use a custom ``JSONDecoder`` subclass, specify it with the ``cls``
    kwarg; otherwise ``JSONDecoder`` is used.</li></ul><h4>math</h4><ul><li><code>acos</code>: Return the arc cosine (measured in radians) of x.

The result is between 0 and pi.</li><li><code>asin</code>: Return the arc sine (measured in radians) of x.

The result is between -pi/2 and pi/2.</li><li><code>atan</code>: Return the arc tangent (measured in radians) of x.

The result is between -pi/2 and pi/2.</li><li><code>atan2</code>: Return the arc tangent (measured in radians) of y/x.

Unlike atan(y/x), the signs of both x and y are considered.</li><li><code>ceil</code>: Return the ceiling of x as an Integral.

This is the smallest integer &gt;= x.</li><li><code>copysign</code>: Return a float with the magnitude (absolute value) of x but the sign of y.

On platforms that support signed zeros, copysign(1.0, -0.0)
returns -1.0.</li><li><code>cos</code>: Return the cosine of x (measured in radians).</li><li><code>degrees</code>: Convert angle x from radians to degrees.</li><li><code>dist</code>: Return the Euclidean distance between two points p and q.

The points should be specified as sequences (or iterables) of
coordinates.  Both inputs must have the same dimension.

Roughly equivalent to:
    sqrt(sum((px - qx) ** 2.0 for px, qx in zip(p, q)))</li><li><code>e</code>: Convert a string or number to a floating-point number, if possible.</li><li><code>fabs</code>: Return the absolute value of the float x.</li><li><code>factorial</code>: Find n!.

Raise a ValueError if x is negative or non-integral.</li><li><code>floor</code>: Return the floor of x as an Integral.

This is the largest integer &lt;= x.</li><li><code>fmod</code>: Return fmod(x, y), according to platform C.

x % y may differ.</li><li><code>frexp</code>: Return the mantissa and exponent of x, as pair (m, e).

m is a float and e is an int, such that x = m * 2.**e.
If x is 0, m and e are both 0.  Else 0.5 &lt;= abs(m) &lt; 1.0.</li><li><code>fsum</code>: Return an accurate floating-point sum of values in the iterable seq.

Assumes IEEE-754 floating-point arithmetic.</li><li><code>gamma</code>: Gamma function at x.</li><li><code>gcd</code>: Greatest Common Divisor.</li><li><code>hypot</code>: hypot(*coordinates) -&gt; value

Multidimensional Euclidean distance from the origin to a point.

Roughly equivalent to:
    sqrt(sum(x**2 for x in coordinates))

For a two dimensional point (x, y), gives the hypotenuse
using the Pythagorean theorem:  sqrt(x*x + y*y).

For example, the hypotenuse of a 3/4/5 right triangle is:

    &gt;&gt;&gt; hypot(3.0, 4.0)
    5.0</li><li><code>inf</code>: Convert a string or number to a floating-point number, if possible.</li><li><code>isclose</code>: Determine whether two floating-point numbers are close in value.

  rel_tol
    maximum difference for being considered "close", relative to the
    magnitude of the input values
  abs_tol
    maximum difference for being considered "close", regardless of the
    magnitude of the input values

Return True if a is close in value to b, and False otherwise.

For the values to be considered close, the difference between them
must be smaller than at least one of the tolerances.

-inf, inf and NaN behave similarly to the IEEE 754 Standard.  That
is, NaN is not close to anything, even itself.  inf and -inf are
only close to themselves.</li><li><code>isfinite</code>: Return True if x is neither an infinity nor a NaN, and False otherwise.</li><li><code>isinf</code>: Return True if x is a positive or negative infinity, and False otherwise.</li><li><code>isnan</code>: Return True if x is a NaN (not a number), and False otherwise.</li><li><code>isqrt</code>: Return the integer part of the square root of the input.</li><li><code>lcm</code>: Least Common Multiple.</li><li><code>lgamma</code>: Natural logarithm of absolute value of Gamma function at x.</li><li><code>log</code>: log(x, [base=math.e])
Return the logarithm of x to the given base.

If the base is not specified, returns the natural logarithm (base e) of x.</li><li><code>log10</code>: Return the base 10 logarithm of x.</li><li><code>log1p</code>: Return the natural logarithm of 1+x (base e).

The result is computed in a way which is accurate for x near zero.</li><li><code>log2</code>: Return the base 2 logarithm of x.</li><li><code>modf</code>: Return the fractional and integer parts of x.

Both results carry the sign of x and are floats.</li><li><code>nan</code>: Convert a string or number to a floating-point number, if possible.</li><li><code>pi</code>: Convert a string or number to a floating-point number, if possible.</li><li><code>radians</code>: Convert angle x from degrees to radians.</li><li><code>remainder</code>: Difference between x and the closest integer multiple of y.

Return x - n*y where n*y is the closest integer multiple of y.
In the case where x is exactly halfway between two multiples of
y, the nearest even value of n is used. The result is always exact.</li><li><code>sin</code>: Return the sine of x (measured in radians).</li><li><code>sqrt</code>: Return the square root of x.</li><li><code>tan</code>: Return the tangent of x (measured in radians).</li><li><code>tau</code>: Convert a string or number to a floating-point number, if possible.</li><li><code>trunc</code>: Truncates the Real x to the nearest Integral toward 0.

Uses the __trunc__ magic method.</li><li><code>ulp</code>: Return the value of the least significant bit of the float x.</li></ul><h4>mimetypes</h4><ul><li><code>guess_type</code>: Guess the type of a file based on its URL.

    Return value is a tuple (type, encoding) where type is None if the
    type can't be guessed (no or unknown suffix) or a string of the
    form type/subtype, usable for a MIME Content-type header; and
    encoding is None for no encoding or the name of the program used
    to encode (e.g. compress or gzip).  The mappings are table
    driven.  Encoding suffixes are case sensitive; type suffixes are
    first tried case sensitive, then case insensitive.

    The suffixes .tgz, .taz and .tz (case sensitive!) are all mapped
    to ".tar.gz".  (This is table-driven too, using the dictionary
    suffix_map).

    Optional `strict' argument when false adds a bunch of commonly found, but
    non-standard types.</li></ul><h4>pathlib</h4><ul><li><code>PurePath</code>: Base class for manipulating paths without I/O.

    PurePath represents a filesystem path and offers operations which
    don't imply any actual filesystem I/O.  Depending on your system,
    instantiating a PurePath will return either a PurePosixPath or a
    PureWindowsPath object.  You can also instantiate either of these classes
    directly, regardless of your system.</li></ul><h4>random</h4><ul><li><code>betavariate</code>: Beta distribution.

        Conditions on the parameters are alpha &gt; 0 and beta &gt; 0.
        Returned values range between 0 and 1.

        The mean (expected value) and variance of the random variable are:

            E[X] = alpha / (alpha + beta)
            Var[X] = alpha * beta / ((alpha + beta)**2 * (alpha + beta + 1))</li><li><code>choice</code>: Choose a random element from a non-empty sequence.</li><li><code>expovariate</code>: Exponential distribution.

        lambd is 1.0 divided by the desired mean.  It should be
        nonzero.  (The parameter would be called "lambda", but that is
        a reserved word in Python.)  Returned values range from 0 to
        positive infinity if lambd is positive, and from negative
        infinity to 0 if lambd is negative.

        The mean (expected value) and variance of the random variable are:

            E[X] = 1 / lambd
            Var[X] = 1 / lambd ** 2</li><li><code>gauss</code>: Gaussian distribution.

        mu is the mean, and sigma is the standard deviation.  This is
        slightly faster than the normalvariate() function.

        Not thread-safe without a lock around calls.</li><li><code>paretovariate</code>: Pareto distribution.  alpha is the shape parameter.</li><li><code>randint</code>: Return random integer in range [a, b], including both end points.</li><li><code>random</code>: random() -&gt; x in the interval [0, 1).</li><li><code>seed</code>: Initialize internal state from a seed.

        The only supported seed types are None, int, float,
        str, bytes, and bytearray.

        None or no argument seeds from current time or from an operating
        system specific randomness source if available.

        If *a* is an int, all bits are used.

        For version 2 (the default), all of the bits are used if *a* is a str,
        bytes, or bytearray.  For version 1 (provided for reproducing random
        sequences from older versions of Python), the algorithm for str and
        bytes generates a narrower range of seeds.</li><li><code>shuffle</code>: Shuffle list x in place, and return None.</li><li><code>triangular</code>: Triangular distribution.

        Continuous distribution bounded by given lower and upper limits,
        and having a given mode value in-between.

        http://en.wikipedia.org/wiki/Triangular_distribution

        The mean (expected value) and variance of the random variable are:

            E[X] = (low + high + mode) / 3
            Var[X] = (low**2 + high**2 + mode**2 - low*high - low*mode - high*mode) / 18</li><li><code>uniform</code>: Get a random number in the range [a, b) or [a, b] depending on rounding.

        The mean (expected value) and variance of the random variable are:

            E[X] = (a + b) / 2
            Var[X] = (b - a) ** 2 / 12</li></ul><h4>re</h4><ul><li><code>ASCII</code>: An enumeration.</li><li><code>DOTALL</code>: An enumeration.</li><li><code>IGNORECASE</code>: An enumeration.</li><li><code>LOCALE</code>: An enumeration.</li><li><code>MULTILINE</code>: An enumeration.</li><li><code>UNICODE</code>: An enumeration.</li><li><code>VERBOSE</code>: An enumeration.</li><li><code>compile</code>: Compile a regular expression pattern, returning a Pattern object.</li><li><code>escape</code>: Escape special characters in a string.</li><li><code>findall</code>: Return a list of all non-overlapping matches in the string.

    If one or more capturing groups are present in the pattern, return
    a list of groups; this will be a list of tuples if the pattern
    has more than one group.

    Empty matches are included in the result.</li><li><code>finditer</code>: Return an iterator over all non-overlapping matches in the
    string.  For each match, the iterator returns a Match object.

    Empty matches are included in the result.</li><li><code>fullmatch</code>: Try to apply the pattern to all of the string, returning
    a Match object, or None if no match was found.</li><li><code>match</code>: Try to apply the pattern at the start of the string, returning
    a Match object, or None if no match was found.</li><li><code>search</code>: Scan through string looking for a match to the pattern, returning
    a Match object, or None if no match was found.</li><li><code>split</code>: Split the source string by the occurrences of the pattern,
    returning a list containing the resulting substrings.  If
    capturing parentheses are used in pattern, then the text of all
    groups in the pattern are also returned as part of the resulting
    list.  If maxsplit is nonzero, at most maxsplit splits occur,
    and the remainder of the string is returned as the final element
    of the list.</li><li><code>sub</code>: Return the string obtained by replacing the leftmost
    non-overlapping occurrences of the pattern in string by the
    replacement repl.  repl can be either a string or a callable;
    if a string, backslash escapes in it are processed.  If it is
    a callable, it's passed the Match object and must return
    a replacement string to be used.</li><li><code>subn</code>: Return a 2-tuple containing (new_string, number).
    new_string is the string obtained by replacing the leftmost
    non-overlapping occurrences of the pattern in the source
    string by the replacement repl.  number is the number of
    substitutions that were made. repl can be either a string or a
    callable; if a string, backslash escapes in it are processed.
    If it is a callable, it's passed the Match object and must
    return a replacement string to be used.</li></ul><h4>re2</h4><ul><li><code>ASCII</code>: An enumeration.</li><li><code>DOTALL</code>: An enumeration.</li><li><code>IGNORECASE</code>: An enumeration.</li><li><code>LOCALE</code>: An enumeration.</li><li><code>MULTILINE</code>: An enumeration.</li><li><code>UNICODE</code>: An enumeration.</li><li><code>VERBOSE</code>: An enumeration.</li><li><code>compile</code>: Compile a regular expression pattern, returning a Pattern object.</li><li><code>escape</code>: Escape special characters in a string.</li><li><code>findall</code>: Return a list of all non-overlapping matches in the string.

    If one or more capturing groups are present in the pattern, return
    a list of groups; this will be a list of tuples if the pattern
    has more than one group.

    Empty matches are included in the result.</li><li><code>finditer</code>: Return an iterator over all non-overlapping matches in the
    string.  For each match, the iterator returns a Match object.

    Empty matches are included in the result.</li><li><code>fullmatch</code>: Try to apply the pattern to all of the string, returning
    a Match object, or None if no match was found.</li><li><code>match</code>: Try to apply the pattern at the start of the string, returning
    a Match object, or None if no match was found.</li><li><code>search</code>: Scan through string looking for a match to the pattern, returning
    a Match object, or None if no match was found.</li><li><code>split</code>: Split the source string by the occurrences of the pattern,
    returning a list containing the resulting substrings.  If
    capturing parentheses are used in pattern, then the text of all
    groups in the pattern are also returned as part of the resulting
    list.  If maxsplit is nonzero, at most maxsplit splits occur,
    and the remainder of the string is returned as the final element
    of the list.</li><li><code>sub</code>: Return the string obtained by replacing the leftmost
    non-overlapping occurrences of the pattern in string by the
    replacement repl.  repl can be either a string or a callable;
    if a string, backslash escapes in it are processed.  If it is
    a callable, it's passed the Match object and must return
    a replacement string to be used.</li><li><code>subn</code>: Return a 2-tuple containing (new_string, number).
    new_string is the string obtained by replacing the leftmost
    non-overlapping occurrences of the pattern in the source
    string by the replacement repl.  number is the number of
    substitutions that were made. repl can be either a string or a
    callable; if a string, backslash escapes in it are processed.
    If it is a callable, it's passed the Match object and must
    return a replacement string to be used.</li></ul><h4>string</h4><ul><li><code>Template</code>: A string class for supporting $-substitutions.</li><li><code>ascii_letters</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li><li><code>ascii_lowercase</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li><li><code>ascii_uppercase</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li><li><code>capwords</code>: capwords(s [,sep]) -&gt; string

    Split the argument into words using split, capitalize each
    word using capitalize, and join the capitalized words using
    join.  If the optional second argument sep is absent or None,
    runs of whitespace characters are replaced by a single space
    and leading and trailing whitespace are removed, otherwise
    sep is used to split and join the words.</li><li><code>digits</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li><li><code>hexdigits</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li><li><code>octdigits</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li><li><code>printable</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li><li><code>punctuation</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li><li><code>whitespace</code>: str(object='') -&gt; str
str(bytes_or_buffer[, encoding[, errors]]) -&gt; str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to sys.getdefaultencoding().
errors defaults to 'strict'.</li></ul><h4>time</h4><ul><li><code>time</code>: </li></ul><h4>typing</h4><ul><li><code>Annotated</code>: Add context-specific metadata to a type.

    Example: Annotated[int, runtime_check.Unsigned] indicates to the
    hypothetical runtime_check module that this type is an unsigned int.
    Every other consumer of this type can ignore this metadata and treat
    this type as int.

    The first argument to Annotated must be a valid type.

    Details:

    - It's an error to call `Annotated` with less than two arguments.
    - Access the metadata via the ``__metadata__`` attribute::

        assert Annotated[int, '$'].__metadata__ == ('$',)

    - Nested Annotated types are flattened::

        assert Annotated[Annotated[T, Ann1, Ann2], Ann3] == Annotated[T, Ann1, Ann2, Ann3]

    - Instantiating an annotated type is equivalent to instantiating the
    underlying type::

        assert Annotated[C, Ann1](5) == C(5)

    - Annotated can be used as a generic type alias::

        type Optimized[T] = Annotated[T, runtime.Optimize()]
        # type checker will treat Optimized[int]
        # as equivalent to Annotated[int, runtime.Optimize()]

        type OptimizedList[T] = Annotated[list[T], runtime.Optimize()]
        # type checker will treat OptimizedList[int]
        # as equivalent to Annotated[list[int], runtime.Optimize()]

    - Annotated cannot be used with an unpacked TypeVarTuple::

        type Variadic[*Ts] = Annotated[*Ts, Ann1]  # NOT valid

      This would be equivalent to::

        Annotated[T1, T2, T3, ..., Ann1]

      where T1, T2 etc. are TypeVars, which would be invalid, because
      only one type should be passed to Annotated.</li><li><code>Any</code>: Special type indicating an unconstrained type.

    - Any is compatible with every type.
    - Any assumed to have all methods.
    - All values assumed to be instances of Any.

    Note that all the above statements are true from the point of view of
    static type checkers. At runtime, Any should not be used with instance
    checks.</li><li><code>Callable</code>: Deprecated alias to collections.abc.Callable.

    Callable[[int], str] signifies a function that takes a single
    parameter of type int and returns a str.

    The subscription syntax must always be used with exactly two
    values: the argument list and the return type.
    The argument list must be a list of types, a ParamSpec,
    Concatenate or ellipsis. The return type must be a single type.

    There is no syntax to indicate optional or keyword arguments;
    such function types are rarely used as callback types.</li><li><code>Dict</code>: A generic version of dict.</li><li><code>Iterable</code>: A generic version of collections.abc.Iterable.</li><li><code>List</code>: A generic version of list.</li><li><code>Literal</code>: Special typing form to define literal types (a.k.a. value types).

    This form can be used to indicate to type checkers that the corresponding
    variable or function parameter has a value equivalent to the provided
    literal (or one of several literals)::

        def validate_simple(data: Any) -&gt; Literal[True]:  # always returns True
            ...

        MODE = Literal['r', 'rb', 'w', 'wb']
        def open_helper(file: str, mode: MODE) -&gt; str:
            ...

        open_helper('/some/path', 'r')  # Passes type check
        open_helper('/other/path', 'typo')  # Error in type checker

    Literal[...] cannot be subclassed. At runtime, an arbitrary value
    is allowed as type argument to Literal[...], but type checkers may
    impose restrictions.</li><li><code>Optional</code>: Optional[X] is equivalent to Union[X, None].</li><li><code>Tuple</code>: Deprecated alias to builtins.tuple.

    Tuple[X, Y] is the cross-product type of X and Y.

    Example: Tuple[T1, T2] is a tuple of two elements corresponding
    to type variables T1 and T2.  Tuple[int, float, str] is a tuple
    of an int, a float and a string.

    To specify a variable-length tuple of homogeneous type, use Tuple[T, ...].</li><li><code>TypedDict</code>: A simple typed namespace. At runtime it is equivalent to a plain dict.

    TypedDict creates a dictionary type such that a type checker will expect all
    instances to have a certain set of keys, where each key is
    associated with a value of a consistent type. This expectation
    is not checked at runtime.

    Usage::

        &gt;&gt;&gt; class Point2D(TypedDict):
        ...     x: int
        ...     y: int
        ...     label: str
        ...
        &gt;&gt;&gt; a: Point2D = {'x': 1, 'y': 2, 'label': 'good'}  # OK
        &gt;&gt;&gt; b: Point2D = {'z': 3, 'label': 'bad'}           # Fails type check
        &gt;&gt;&gt; Point2D(x=1, y=2, label='first') == dict(x=1, y=2, label='first')
        True

    The type info can be accessed via the Point2D.__annotations__ dict, and
    the Point2D.__required_keys__ and Point2D.__optional_keys__ frozensets.
    TypedDict supports an additional equivalent form::

        Point2D = TypedDict('Point2D', {'x': int, 'y': int, 'label': str})

    By default, all keys must be present in a TypedDict. It is possible
    to override this by specifying totality::

        class Point2D(TypedDict, total=False):
            x: int
            y: int

    This means that a Point2D TypedDict can have any of the keys omitted. A type
    checker is only expected to support a literal False or True as the value of
    the total argument. True is the default, and makes all items defined in the
    class body be required.

    The Required and NotRequired special forms can also be used to mark
    individual keys as being required or not required::

        class Point2D(TypedDict):
            x: int               # the "x" key must always be present (Required is the default)
            y: NotRequired[int]  # the "y" key can be omitted

    See PEP 655 for more details on Required and NotRequired.</li><li><code>Union</code>: Union type; Union[X, Y] means either X or Y.

    On Python 3.10 and higher, the | operator
    can also be used to denote unions;
    X | Y means the same thing to the type checker as Union[X, Y].

    To define a union, use e.g. Union[int, str]. Details:
    - The arguments must be types and there must be at least one.
    - None as an argument is a special case and is replaced by
      type(None).
    - Unions of unions are flattened, e.g.::

        assert Union[Union[int, str], float] == Union[int, str, float]

    - Unions of a single argument vanish, e.g.::

        assert Union[int] == int  # The constructor actually returns int

    - Redundant arguments are skipped, e.g.::

        assert Union[int, str, int] == Union[int, str]

    - When comparing unions, the argument order is ignored, e.g.::

        assert Union[int, str] == Union[str, int]

    - You cannot subclass or instantiate a union.
    - You can use Optional[X] as a shorthand for Union[X, None].</li></ul><h4>urllib</h4><ul><li><code>parse</code>: dict() -&gt; new empty dictionary
dict(mapping) -&gt; new dictionary initialized from a mapping object's
    (key, value) pairs
dict(iterable) -&gt; new dictionary initialized as if via:
    d = {}
    for k, v in iterable:
        d[k] = v
dict(**kwargs) -&gt; new dictionary initialized with the name=value pairs
    in the keyword argument list.  For example:  dict(one=1, two=2)</li></ul><h3>Available Functions</h3><ul><li><code>BytesIO.read</code></li><li><code>Datetime.combine</code></li><li><code>Datetime.ctime</code></li><li><code>Datetime.date</code></li><li><code>Datetime.dst</code></li><li><code>Datetime.fromisoformat</code></li><li><code>Datetime.fromtimestamp</code></li><li><code>Datetime.isoformat</code></li><li><code>Datetime.now</code></li><li><code>Datetime.replace</code></li><li><code>Datetime.strptime</code></li><li><code>Datetime.time</code></li><li><code>Datetime.timestamp</code></li><li><code>Datetime.timetuple</code></li><li><code>Datetime.timetz</code></li><li><code>Datetime.tzname</code></li><li><code>Datetime.utcfromtimestamp</code></li><li><code>Datetime.utcnow</code></li><li><code>Datetime.utcoffset</code></li><li><code>Datetime.utctimetuple</code></li><li><code>Decimal.as_integer_ratio</code></li><li><code>Decimal.as_tuple</code></li><li><code>Decimal.exp</code></li><li><code>Decimal.quantize</code></li><li><code>Decimal.round</code></li><li><code>Decimal.sqrt</code></li><li><code>Decimal.to_integral</code></li><li><code>Decimal.to_integral_exact</code></li><li><code>Decimal.to_integral_value</code></li><li><code>HASH.digest</code></li><li><code>HASH.hexdigest</code></li><li><code>HASH.update</code></li><li><code>Match.end</code></li><li><code>Match.endpos</code></li><li><code>Match.group</code></li><li><code>Match.groupdict</code></li><li><code>Match.pos</code></li><li><code>Match.re</code></li><li><code>Match.span</code></li><li><code>Match.start</code></li><li><code>Random.random</code></li><li><code>_hashlib.openssl_md5</code></li><li><code>_hashlib.openssl_sha1</code></li><li><code>_hashlib.openssl_sha256</code></li><li><code>_hashlib.openssl_sha512</code></li><li><code>_io.BytesIO</code></li><li><code>_io.StringIO</code></li><li><code>ast.ClassDef</code></li><li><code>ast.FunctionDef</code></li><li><code>ast.NodeTransformer</code></li><li><code>ast.NodeVisitor</code></li><li><code>ast.dump</code></li><li><code>ast.fix_missing_locations</code></li><li><code>ast.get_docstring</code></li><li><code>ast.get_source_segment</code></li><li><code>ast.literal_eval</code></li><li><code>ast.parse</code></li><li><code>ast.unparse</code></li><li><code>ast.walk</code></li><li><code>base64.b64decode</code></li><li><code>base64.b64encode</code></li><li><code>base64.decodebytes</code></li><li><code>base64.encodebytes</code></li><li><code>base64.urlsafe_b64decode</code></li><li><code>base64.urlsafe_b64encode</code></li><li><code>bencoder.decode</code></li><li><code>bencoder.encode</code></li><li><code>builtins.ArithmeticError</code></li><li><code>builtins.AssertionError</code></li><li><code>builtins.AttributeError</code></li><li><code>builtins.Exception</code></li><li><code>builtins.False</code></li><li><code>builtins.FloatingPointError</code></li><li><code>builtins.ImportError</code></li><li><code>builtins.IndexError</code></li><li><code>builtins.KeyError</code></li><li><code>builtins.LookupError</code></li><li><code>builtins.MemoryError</code></li><li><code>builtins.ModuleNotFoundError</code></li><li><code>builtins.NameError</code></li><li><code>builtins.None</code></li><li><code>builtins.NotImplementedError</code></li><li><code>builtins.OverflowError</code></li><li><code>builtins.PermissionError</code></li><li><code>builtins.RecursionError</code></li><li><code>builtins.SyntaxError</code></li><li><code>builtins.True</code></li><li><code>builtins.TypeError</code></li><li><code>builtins.UnboundLocalError</code></li><li><code>builtins.UnicodeDecodeError</code></li><li><code>builtins.UnicodeEncodeError</code></li><li><code>builtins.UnicodeError</code></li><li><code>builtins.UnicodeTranslateError</code></li><li><code>builtins.ValueError</code></li><li><code>builtins.ZeroDivisionError</code></li><li><code>builtins.abs</code></li><li><code>builtins.all</code></li><li><code>builtins.any</code></li><li><code>builtins.bin</code></li><li><code>builtins.bool</code></li><li><code>builtins.bytearray</code></li><li><code>builtins.bytes</code></li><li><code>builtins.callable</code></li><li><code>builtins.chr</code></li><li><code>builtins.classmethod</code></li><li><code>builtins.complex</code></li><li><code>builtins.dict</code></li><li><code>builtins.divmod</code></li><li><code>builtins.enumerate</code></li><li><code>builtins.filter</code></li><li><code>builtins.float</code></li><li><code>builtins.frozenset</code></li><li><code>builtins.hex</code></li><li><code>builtins.int</code></li><li><code>builtins.isinstance</code></li><li><code>builtins.issubclass</code></li><li><code>builtins.iter</code></li><li><code>builtins.len</code></li><li><code>builtins.list</code></li><li><code>builtins.map</code></li><li><code>builtins.max</code></li><li><code>builtins.min</code></li><li><code>builtins.oct</code></li><li><code>builtins.ord</code></li><li><code>builtins.pow</code></li><li><code>builtins.print</code></li><li><code>builtins.range</code></li><li><code>builtins.reversed</code></li><li><code>builtins.round</code></li><li><code>builtins.set</code></li><li><code>builtins.slice</code></li><li><code>builtins.sorted</code></li><li><code>builtins.str</code></li><li><code>builtins.sum</code></li><li><code>builtins.tuple</code></li><li><code>builtins.zip</code></li><li><code>bytes.decode</code></li><li><code>bytes.hex</code></li><li><code>bytes.join</code></li><li><code>contains</code></li><li><code>count</code></li><li><code>dataclasses.asdict</code></li><li><code>dataclasses.astuple</code></li><li><code>dataclasses.dataclass</code></li><li><code>dataclasses.field</code></li><li><code>datetime.time</code></li><li><code>datetime.timedelta</code></li><li><code>datetime.timezone</code></li><li><code>datetime.tzinfo</code></li><li><code>decimal.Decimal</code></li><li><code>dict.clear</code></li><li><code>dict.copy</code></li><li><code>dict.fromkeys</code></li><li><code>dict.get</code></li><li><code>dict.items</code></li><li><code>dict.keys</code></li><li><code>dict.pop</code></li><li><code>dict.popitem</code></li><li><code>dict.setdefault</code></li><li><code>dict.update</code></li><li><code>dict.values</code></li><li><code>dys._chain</code></li><li><code>dys._msg</code></li><li><code>dys._query</code></li><li><code>dys.deprecated_chain</code></li><li><code>dys.dys_eval</code></li><li><code>dys.emit_event</code></li><li><code>dys.get_attached_messages</code></li><li><code>dys.get_attached_msg_results</code></li><li><code>dys.get_block_info</code></li><li><code>dys.get_cumulative_size</code></li><li><code>dys.get_executor_address</code></li><li><code>dys.get_gas_consumed</code></li><li><code>dys.get_gas_limit</code></li><li><code>dys.get_nodes_called</code></li><li><code>dys.get_script_address</code></li><li><code>dys.get_script_code</code></li><li><code>dys.get_script_name</code></li><li><code>dys.get_script_version</code></li><li><code>dys.list_functions</code></li><li><code>dys.list_modules</code></li><li><code>dys.safe_help</code></li><li><code>dyslang.dysvm_server.DysMsgException</code></li><li><code>dyslang.dysvm_server.DysQueryException</code></li><li><code>enum.Enum</code></li><li><code>enum.EnumType</code></li><li><code>enum.IntEnum</code></li><li><code>enum.StrEnum</code></li><li><code>findall</code></li><li><code>finditer</code></li><li><code>freezegun.api.Date</code></li><li><code>freezegun.api.Datetime</code></li><li><code>freezegun.api.FakeDatetime.astimezone</code></li><li><code>freezegun.api.FakeDatetime.combine</code></li><li><code>freezegun.api.FakeDatetime.ctime</code></li><li><code>freezegun.api.FakeDatetime.date</code></li><li><code>freezegun.api.FakeDatetime.dst</code></li><li><code>freezegun.api.FakeDatetime.fromisoformat</code></li><li><code>freezegun.api.FakeDatetime.fromtimestamp</code></li><li><code>freezegun.api.FakeDatetime.isoformat</code></li><li><code>freezegun.api.FakeDatetime.now</code></li><li><code>freezegun.api.FakeDatetime.replace</code></li><li><code>freezegun.api.FakeDatetime.strptime</code></li><li><code>freezegun.api.FakeDatetime.time</code></li><li><code>freezegun.api.FakeDatetime.timestamp</code></li><li><code>freezegun.api.FakeDatetime.timetuple</code></li><li><code>freezegun.api.FakeDatetime.timetz</code></li><li><code>freezegun.api.FakeDatetime.tzname</code></li><li><code>freezegun.api.FakeDatetime.utcfromtimestamp</code></li><li><code>freezegun.api.FakeDatetime.utcnow</code></li><li><code>freezegun.api.FakeDatetime.utcoffset</code></li><li><code>freezegun.api.FakeDatetime.utctimetupleDatetime.astimezone</code></li><li><code>freezegun.api.fake_time</code></li><li><code>fullmatch</code></li><li><code>function_schema.core.get_function_schema</code></li><li><code>html.escape</code></li><li><code>html.unescape</code></li><li><code>json.decoder.JSONDecodeError</code></li><li><code>json.dumps</code></li><li><code>json.loads</code></li><li><code>list.append</code></li><li><code>list.clear</code></li><li><code>list.copy</code></li><li><code>list.count</code></li><li><code>list.extend</code></li><li><code>list.index</code></li><li><code>list.insert</code></li><li><code>list.pop</code></li><li><code>list.remove</code></li><li><code>list.reverse</code></li><li><code>list.sort</code></li><li><code>match</code></li><li><code>math.acos</code></li><li><code>math.asin</code></li><li><code>math.atan</code></li><li><code>math.atan2</code></li><li><code>math.ceil</code></li><li><code>math.copysign</code></li><li><code>math.cos</code></li><li><code>math.degrees</code></li><li><code>math.dist</code></li><li><code>math.fabs</code></li><li><code>math.factorial</code></li><li><code>math.floor</code></li><li><code>math.fmod</code></li><li><code>math.frexp</code></li><li><code>math.fsum</code></li><li><code>math.gamma</code></li><li><code>math.gcd</code></li><li><code>math.hypot</code></li><li><code>math.isclose</code></li><li><code>math.isfinite</code></li><li><code>math.isinf</code></li><li><code>math.isnan</code></li><li><code>math.isqrt</code></li><li><code>math.lcm</code></li><li><code>math.lgamma</code></li><li><code>math.log</code></li><li><code>math.log10</code></li><li><code>math.log1p</code></li><li><code>math.log2</code></li><li><code>math.modf</code></li><li><code>math.radians</code></li><li><code>math.remainder</code></li><li><code>math.sin</code></li><li><code>math.sqrt</code></li><li><code>math.tan</code></li><li><code>math.trunc</code></li><li><code>math.ulp</code></li><li><code>mimetypes.guess_type</code></li><li><code>pathlib.PurePath</code></li><li><code>random.Random.betavariate</code></li><li><code>random.Random.choice</code></li><li><code>random.Random.expovariate</code></li><li><code>random.Random.gauss</code></li><li><code>random.Random.paretovariate</code></li><li><code>random.Random.randint</code></li><li><code>random.Random.sample</code></li><li><code>random.Random.seed</code></li><li><code>random.Random.shuffle</code></li><li><code>random.Random.triangular</code></li><li><code>random.Random.uniform</code></li><li><code>re.compile</code></li><li><code>re.escape</code></li><li><code>re.findall</code></li><li><code>re.finditer</code></li><li><code>re.fullmatch</code></li><li><code>re.match</code></li><li><code>re.search</code></li><li><code>re.split</code></li><li><code>re.sub</code></li><li><code>re.subn</code></li><li><code>re2._Match.groupdict</code></li><li><code>re2._Match.groups</code></li><li><code>re2._Regexp.match</code></li><li><code>scanner</code></li><li><code>script.list_api</code></li><li><code>search</code></li><li><code>set.add</code></li><li><code>set.clear</code></li><li><code>set.difference_update</code></li><li><code>set.discard</code></li><li><code>set.intersection_update</code></li><li><code>set.pop</code></li><li><code>set.remove</code></li><li><code>set.symmetric_difference_update</code></li><li><code>set.update</code></li><li><code>split</code></li><li><code>str.capitalize</code></li><li><code>str.casefold</code></li><li><code>str.count</code></li><li><code>str.encode</code></li><li><code>str.endswith</code></li><li><code>str.find</code></li><li><code>str.index</code></li><li><code>str.isalnum</code></li><li><code>str.isalpha</code></li><li><code>str.isascii</code></li><li><code>str.isdecimal</code></li><li><code>str.isdigit</code></li><li><code>str.isidentifier</code></li><li><code>str.islower</code></li><li><code>str.isnumeric</code></li><li><code>str.isprintable</code></li><li><code>str.isspace</code></li><li><code>str.istitle</code></li><li><code>str.isupper</code></li><li><code>str.join</code></li><li><code>str.lower</code></li><li><code>str.lstrip</code></li><li><code>str.partition</code></li><li><code>str.removeprefix</code></li><li><code>str.removesuffix</code></li><li><code>str.rfind</code></li><li><code>str.rindex</code></li><li><code>str.rpartition</code></li><li><code>str.rsplit</code></li><li><code>str.rstrip</code></li><li><code>str.split</code></li><li><code>str.splitlines</code></li><li><code>str.startswith</code></li><li><code>str.strip</code></li><li><code>str.swapcase</code></li><li><code>str.title</code></li><li><code>str.upper</code></li><li><code>string.Template</code></li><li><code>string.Template.safe_substitute</code></li><li><code>string.Template.substitute</code></li><li><code>string.capwords</code></li><li><code>typing.Annotated</code></li><li><code>typing.Any</code></li><li><code>typing.Callable</code></li><li><code>typing.Dict</code></li><li><code>typing.Iterable</code></li><li><code>typing.List</code></li><li><code>typing.Literal</code></li><li><code>typing.Optional</code></li><li><code>typing.Tuple</code></li><li><code>typing.TypedDict</code></li><li><code>typing.Union</code></li><li><code>typing_extensions.Doc</code></li><li><code>urllib.parse.parse_qs</code></li><li><code>urllib.parse.parse_qsl</code></li><li><code>urllib.parse.quote</code></li><li><code>urllib.parse.quote_from_bytes</code></li><li><code>urllib.parse.quote_plus</code></li><li><code>urllib.parse.unquote</code></li><li><code>urllib.parse.unquote_plus</code></li><li><code>urllib.parse.unquote_to_bytes</code></li><li><code>urllib.parse.urldefrag</code></li><li><code>urllib.parse.urljoin</code></li><li><code>urllib.parse.urlsplit</code></li><li><code>urllib.parse.urlunsplit</code></li><li><code>wsgiref.handlers.BaseHandler.start_response</code></li><li><code>wsgiref.handlers.BaseHandler.write</code></li></ul></div>


## Available Syntax

Here is a table of all the python syntax that is supported by Dyslang.


<table>
<thead><tr><th>AST Node</th><th>Demo</th><th>Result</th></tr></thead>
<tbody>
<tr><td colspan="3"><h3>Literals and Constants</h3></td></tr>
<tr><td>Constant</td><td><code>42</code></td><td>SUCCESS: 42</td></tr>
<tr><td>FormattedValue</td><td><code>f'The answer is {40 + 2}'</code></td><td>SUCCESS: The answer is 42</td></tr>
<tr><td>JoinedStr</td><td><code>f'Hello {"world"}'</code></td><td>SUCCESS: Hello world</td></tr>
<tr><td colspan="3"><h3>Collections</h3></td></tr>
<tr><td>List</td><td><code>[1, 2, 3]</code></td><td>SUCCESS: [1, 2, 3]</td></tr>
<tr><td>Tuple</td><td><code>(1, 2, 3)</code></td><td>SUCCESS: (1, 2, 3)</td></tr>
<tr><td>Set</td><td><code>{1, 2, 3}</code></td><td>SUCCESS: {1, 2, 3}</td></tr>
<tr><td>Dict</td><td><code>{'a': 1, 'b': 2}</code></td><td>SUCCESS: {'a': 1, 'b': 2}</td></tr>
<tr><td colspan="3"><h3>Variables</h3></td></tr>
<tr><td>Name_Load</td><td><code>x = 1; x</code></td><td>SUCCESS: 1</td></tr>
<tr><td>Name_Store</td><td><code>x = 42</code></td><td>SUCCESS: None</td></tr>
<tr><td>Name_Del</td><td><code>y = 10; del y</code></td><td>SUCCESS: None</td></tr>
<tr><td>Starred</td><td><code>a, *b = [1, 2, 3, 4]; b</code></td><td>SUCCESS: [2, 3, 4]</td></tr>
<tr><td colspan="3"><h3>Expressions</h3></td></tr>
<tr><td>UnaryOp_Not</td><td><code>not True</code></td><td>SUCCESS: False</td></tr>
<tr><td>UnaryOp_Invert</td><td><code>~42</code></td><td>SUCCESS: -43</td></tr>
<tr><td>UnaryOp_UAdd</td><td><code>+42</code></td><td>SUCCESS: 42</td></tr>
<tr><td>UnaryOp_USub</td><td><code>-42</code></td><td>SUCCESS: -42</td></tr>
<tr><td colspan="3"><h3>Binary Operations</h3></td></tr>
<tr><td>BinOp_Add</td><td><code>1 + 2</code></td><td>SUCCESS: 3</td></tr>
<tr><td>BinOp_Sub</td><td><code>1 - 2</code></td><td>SUCCESS: -1</td></tr>
<tr><td>BinOp_Mult</td><td><code>2 * 3</code></td><td>SUCCESS: 6</td></tr>
<tr><td>BinOp_Div</td><td><code>6 / 3</code></td><td>SUCCESS: 2.0</td></tr>
<tr><td>BinOp_FloorDiv</td><td><code>7 // 3</code></td><td>SUCCESS: 2</td></tr>
<tr><td>BinOp_Mod</td><td><code>7 % 3</code></td><td>SUCCESS: 1</td></tr>
<tr><td>BinOp_Pow</td><td><code>2 ** 3</code></td><td>SUCCESS: 8</td></tr>
<tr><td>BinOp_LShift</td><td><code>1 &lt;&lt; 2</code></td><td>SUCCESS: 4</td></tr>
<tr><td>BinOp_RShift</td><td><code>8 &gt;&gt; 2</code></td><td>SUCCESS: 2</td></tr>
<tr><td>BinOp_BitOr</td><td><code>1 | 2</code></td><td>SUCCESS: 3</td></tr>
<tr><td>BinOp_BitXor</td><td><code>5 ^ 3</code></td><td>SUCCESS: 6</td></tr>
<tr><td>BinOp_BitAnd</td><td><code>5 &amp; 3</code></td><td>SUCCESS: 1</td></tr>
<tr><td>BinOp_MatMult</td><td><code># Not in basic Python: a @ b</code></td><td>SKIPPED</td></tr>
<tr><td colspan="3"><h3>Boolean Operations</h3></td></tr>
<tr><td>BoolOp_And</td><td><code>True and False</code></td><td>SUCCESS: False</td></tr>
<tr><td>BoolOp_Or</td><td><code>True or False</code></td><td>SUCCESS: True</td></tr>
<tr><td colspan="3"><h3>Comparisons</h3></td></tr>
<tr><td>Compare_Eq</td><td><code>1 == 1</code></td><td>SUCCESS: True</td></tr>
<tr><td>Compare_NotEq</td><td><code>1 != 2</code></td><td>SUCCESS: True</td></tr>
<tr><td>Compare_Lt</td><td><code>1 &lt; 2</code></td><td>SUCCESS: True</td></tr>
<tr><td>Compare_LtE</td><td><code>1 &lt;= 2</code></td><td>SUCCESS: True</td></tr>
<tr><td>Compare_Gt</td><td><code>2 &gt; 1</code></td><td>SUCCESS: True</td></tr>
<tr><td>Compare_GtE</td><td><code>2 &gt;= 1</code></td><td>SUCCESS: True</td></tr>
<tr><td>Compare_Is</td><td><code>1 is 1</code></td><td>SUCCESS: True</td></tr>
<tr><td>Compare_IsNot</td><td><code>1 is not 2</code></td><td>SUCCESS: True</td></tr>
<tr><td>Compare_In</td><td><code>1 in [1, 2, 3]</code></td><td>SUCCESS: True</td></tr>
<tr><td>Compare_NotIn</td><td><code>0 not in [1, 2, 3]</code></td><td>SUCCESS: True</td></tr>
<tr><td colspan="3"><h3>Function and Method Calls</h3></td></tr>
<tr><td>Call</td><td><code>len([1, 2, 3])</code></td><td>SUCCESS: 3</td></tr>
<tr><td>Call_Kwargs</td><td><code>dict(a=1, b=2)</code></td><td>SUCCESS: {'a': 1, 'b': 2}</td></tr>
<tr><td>Call_Starred</td><td><code>sum([1, 2, 3])</code></td><td>SUCCESS: 6</td></tr>
<tr><td>Call_KwStarred</td><td><code>dict(**{'a': 1, 'b': 2})</code></td><td>SUCCESS: {'a': 1, 'b': 2}</td></tr>
<tr><td colspan="3"><h3>Conditional Expressions</h3></td></tr>
<tr><td>IfExp</td><td><code>1 if True else 2</code></td><td>SUCCESS: 1</td></tr>
<tr><td colspan="3"><h3>Attribute Access</h3></td></tr>
<tr><td>Attribute</td><td><code>'hello'.upper()</code></td><td>SUCCESS: HELLO</td></tr>
<tr><td colspan="3"><h3>Subscripting</h3></td></tr>
<tr><td>Subscript</td><td><code>[1, 2, 3][0]</code></td><td>SUCCESS: 1</td></tr>
<tr><td>Slice</td><td><code>[1, 2, 3, 4][1:3]</code></td><td>SUCCESS: [2, 3]</td></tr>
<tr><td colspan="3"><h3>Comprehensions</h3></td></tr>
<tr><td>ListComp</td><td><code>[x for x in range(5)]</code></td><td>SUCCESS: [0, 1, 2, 3, 4]</td></tr>
<tr><td>SetComp</td><td><code>{x for x in range(5)}</code></td><td>SUCCESS: {0, 1, 2, 3, 4}</td></tr>
<tr><td>DictComp</td><td><code>{x: x*x for x in range(5)}</code></td><td>SUCCESS: {0: 0, 1: 1, 2: 4, 3: 9, 4: 16}</td></tr>
<tr><td>GeneratorExp</td><td><code>(x for x in range(5))</code></td><td>SUCCESS: [0, 1, 2, 3, 4]</td></tr>
<tr><td colspan="3"><h3>Assignments</h3></td></tr>
<tr><td>Assign</td><td><code>x = 42</code></td><td>SUCCESS: None</td></tr>
<tr><td>AnnAssign</td><td><code>x: int = 42</code></td><td>SUCCESS: None</td></tr>
<tr><td>AugAssign</td><td><code>x = 1; x += 1</code></td><td>SUCCESS: None</td></tr>
<tr><td>NamedExpr</td><td><code>(x := 42)</code></td><td>SUCCESS: 42</td></tr>
<tr><td colspan="3"><h3>Control Flow</h3></td></tr>
<tr><td>If</td><td><code>if True: pass</code></td><td>SUCCESS: None</td></tr>
<tr><td>For</td><td><code>for i in range(5): pass</code></td><td>SUCCESS: None</td></tr>
<tr><td>While</td><td><code>while False: pass</code></td><td>SUCCESS: None</td></tr>
<tr><td>Break</td><td><code>for i in range(5):<br>    if i &gt; 2: break</code></td><td>SUCCESS: None</td></tr>
<tr><td>Continue</td><td><code>for i in range(5):<br>    if i &lt; 2: continue</code></td><td>SUCCESS: None</td></tr>
<tr><td colspan="3"><h3>Exception Handling</h3></td></tr>
<tr><td>Try</td><td><code>try:<br>    1/0<br>except ZeroDivisionError:<br>    pass</code></td><td>SUCCESS: None</td></tr>
<tr><td>Raise</td><td><code>try:<br>    raise ValueError('example error')<br>except ValueError:<br>    pass</code></td><td>SUCCESS: None</td></tr>
<tr><td>Assert</td><td><code>assert True, 'message'</code></td><td>SUCCESS: None</td></tr>
<tr><td colspan="3"><h3>Function and Class Definitions</h3></td></tr>
<tr><td>FunctionDef</td><td><code>def func(x): return x*2</code></td><td>SUCCESS: None</td></tr>
<tr><td>Lambda</td><td><code>lambda x: x*2</code></td><td>SUCCESS: &lt;function &lt;lambda&gt; at 0x1234&gt;</td></tr>
<tr><td>Return</td><td><code>def func(): return 42</code></td><td>SUCCESS: None</td></tr>
<tr><td>ClassDef</td><td><code>class MyClass:<br>    pass</code></td><td>SUCCESS: None</td></tr>
<tr><td colspan="3"><h3>Import Statements</h3></td></tr>
<tr><td>Import</td><td><code>try: import json<br>except ImportError: pass</code></td><td>SUCCESS: None</td></tr>
<tr><td>ImportFrom</td><td><code>try: from json import loads<br>except ImportError: pass</code></td><td>SUCCESS: None</td></tr>
<tr><td colspan="3"><h3>With Statements</h3></td></tr>
<tr><td>With</td><td><code>with open('file.txt', 'w') as f: pass</code></td><td>ERROR: Not Implemented</td></tr>
<tr><td colspan="3"><h3>Async/Await</h3></td></tr>
<tr><td>AsyncFunctionDef</td><td><code>async def func(): pass</code></td><td>ERROR: Not Implemented</td></tr>
<tr><td>Await</td><td><code>async def func():<br>    await other_func()</code></td><td>ERROR: Not Implemented</td></tr>
<tr><td>AsyncFor</td><td><code>async def func():<br>    async for i in aiter(): pass</code></td><td>ERROR: Not Implemented</td></tr>
<tr><td>AsyncWith</td><td><code>async def func():<br>    async with acontext() as a: pass</code></td><td>ERROR: Not Implemented</td></tr>
<tr><td colspan="3"><h3>Yield Expressions</h3></td></tr>
<tr><td>Yield</td><td><code>def gen(): yield 42</code></td><td>ERROR: Not Implemented</td></tr>
<tr><td>YieldFrom</td><td><code>def gen(): yield from [1, 2, 3]</code></td><td>ERROR: Not Implemented</td></tr>
<tr><td colspan="3"><h3>Others</h3></td></tr>
<tr><td>Delete</td><td><code>x = 1; del x</code></td><td>SUCCESS: None</td></tr>
<tr><td>Pass</td><td><code>pass</code></td><td>SUCCESS: None</td></tr>
<tr><td>Global</td><td><code>global x</code></td><td>ERROR: Not Implemented</td></tr>
<tr><td>Nonlocal</td><td><code>nonlocal x</code></td><td>ERROR: Not Implemented</td></tr>
</tbody></table>


## Security Constraints

The Dyson Protocol implements several security constraints to ensure safe and reliable execution of scripts:

### Gas Limits

All script executions are bound by gas limits to prevent infinite loops and excessive computation. As we saw earlier, you can query the gas limit for any execution using `get_gas_limit()`.

### Memory Restrictions

The dyslang module enforces limits on string lengths, stack depth, and scope sizes to prevent resource exhaustion. You can monitor memory usage with `get_cumulative_size()`.

### Sandboxed Environment

Scripts run in a carefully controlled environment where only whitelisted functions and modules are available. This prevents access to potentially dangerous system functions.

### Node Calls Tracking

As we've seen, the execution environment tracks AST node evaluations and terminates if limits are exceeded, preventing resource-exhaustion attacks.
