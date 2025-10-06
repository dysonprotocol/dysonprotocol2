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
    - Time: 2025-10-06T15:02:50.062658Z


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

## Available Modules and Functions

These are the available modules and functions that can be used in dyslang scripts.

    {
      "list_functions": [
        "BytesIO.read",
        "Datetime.combine",
        "Datetime.ctime",
        "Datetime.date",
        "Datetime.dst",
        "Datetime.fromisoformat",
        "Datetime.fromtimestamp",
        "Datetime.isoformat",
        "Datetime.now",
        "Datetime.replace",
        "Datetime.strptime",
        "Datetime.time",
        "Datetime.timestamp",
        "Datetime.timetuple",
        "Datetime.timetz",
        "Datetime.tzname",
        "Datetime.utcfromtimestamp",
        "Datetime.utcnow",
        "Datetime.utcoffset",
        "Datetime.utctimetuple",
        "Decimal.as_integer_ratio",
        "Decimal.as_tuple",
        "Decimal.exp",
        "Decimal.quantize",
        "Decimal.round",
        "Decimal.sqrt",
        "Decimal.to_integral",
        "Decimal.to_integral_exact",
        "Decimal.to_integral_value",
        "HASH.digest",
        "HASH.hexdigest",
        "HASH.update",
        "Match.end",
        "Match.endpos",
        "Match.group",
        "Match.groupdict",
        "Match.pos",
        "Match.re",
        "Match.span",
        "Match.start",
        "Random.random",
        "_hashlib.openssl_md5",
        "_hashlib.openssl_sha1",
        "_hashlib.openssl_sha256",
        "_hashlib.openssl_sha512",
        "_io.BytesIO",
        "_io.StringIO",
        "ast.ClassDef",
        "ast.FunctionDef",
        "ast.NodeTransformer",
        "ast.NodeVisitor",
        "ast.dump",
        "ast.fix_missing_locations",
        "ast.get_docstring",
        "ast.get_source_segment",
        "ast.literal_eval",
        "ast.parse",
        "ast.unparse",
        "ast.walk",
        "base64.b64decode",
        "base64.b64encode",
        "base64.decodebytes",
        "base64.encodebytes",
        "base64.urlsafe_b64decode",
        "base64.urlsafe_b64encode",
        "bencoder.decode",
        "bencoder.encode",
        "builtins.ArithmeticError",
        "builtins.AssertionError",
        "builtins.AttributeError",
        "builtins.Exception",
        "builtins.False",
        "builtins.FloatingPointError",
        "builtins.ImportError",
        "builtins.IndexError",
        "builtins.KeyError",
        "builtins.LookupError",
        "builtins.MemoryError",
        "builtins.ModuleNotFoundError",
        "builtins.NameError",
        "builtins.None",
        "builtins.NotImplementedError",
        "builtins.OverflowError",
        "builtins.PermissionError",
        "builtins.RecursionError",
        "builtins.SyntaxError",
        "builtins.True",
        "builtins.TypeError",
        "builtins.UnboundLocalError",
        "builtins.UnicodeDecodeError",
        "builtins.UnicodeEncodeError",
        "builtins.UnicodeError",
        "builtins.UnicodeTranslateError",
        "builtins.ValueError",
        "builtins.ZeroDivisionError",
        "builtins.abs",
        "builtins.all",
        "builtins.any",
        "builtins.bin",
        "builtins.bool",
        "builtins.bytearray",
        "builtins.bytes",
        "builtins.callable",
        "builtins.chr",
        "builtins.classmethod",
        "builtins.complex",
        "builtins.dict",
        "builtins.divmod",
        "builtins.enumerate",
        "builtins.filter",
        "builtins.float",
        "builtins.frozenset",
        "builtins.hex",
        "builtins.int",
        "builtins.isinstance",
        "builtins.issubclass",
        "builtins.iter",
        "builtins.len",
        "builtins.list",
        "builtins.map",
        "builtins.max",
        "builtins.min",
        "builtins.oct",
        "builtins.ord",
        "builtins.pow",
        "builtins.print",
        "builtins.range",
        "builtins.reversed",
        "builtins.round",
        "builtins.set",
        "builtins.slice",
        "builtins.sorted",
        "builtins.str",
        "builtins.sum",
        "builtins.tuple",
        "builtins.zip",
        "bytes.decode",
        "bytes.hex",
        "bytes.join",
        "contains",
        "count",
        "dataclasses.asdict",
        "dataclasses.astuple",
        "dataclasses.dataclass",
        "dataclasses.field",
        "datetime.time",
        "datetime.timedelta",
        "datetime.timezone",
        "datetime.tzinfo",
        "decimal.Decimal",
        "dict.clear",
        "dict.copy",
        "dict.fromkeys",
        "dict.get",
        "dict.items",
        "dict.keys",
        "dict.pop",
        "dict.popitem",
        "dict.setdefault",
        "dict.update",
        "dict.values",
        "dys._chain",
        "dys._msg",
        "dys._query",
        "dys.deprecated_chain",
        "dys.dys_eval",
        "dys.emit_event",
        "dys.get_attached_messages",
        "dys.get_attached_msg_results",
        "dys.get_block_info",
        "dys.get_cumulative_size",
        "dys.get_executor_address",
        "dys.get_gas_consumed",
        "dys.get_gas_limit",
        "dys.get_nodes_called",
        "dys.get_script_address",
        "dys.get_script_code",
        "dys.get_script_name",
        "dys.get_script_version",
        "dys.list_functions",
        "dys.list_modules",
        "dys.safe_help",
        "dyslang.dysvm_server.DysMsgException",
        "dyslang.dysvm_server.DysQueryException",
        "enum.Enum",
        "enum.EnumType",
        "enum.IntEnum",
        "enum.StrEnum",
        "findall",
        "finditer",
        "freezegun.api.Date",
        "freezegun.api.Datetime",
        "freezegun.api.FakeDatetime.astimezone",
        "freezegun.api.FakeDatetime.combine",
        "freezegun.api.FakeDatetime.ctime",
        "freezegun.api.FakeDatetime.date",
        "freezegun.api.FakeDatetime.dst",
        "freezegun.api.FakeDatetime.fromisoformat",
        "freezegun.api.FakeDatetime.fromtimestamp",
        "freezegun.api.FakeDatetime.isoformat",
        "freezegun.api.FakeDatetime.now",
        "freezegun.api.FakeDatetime.replace",
        "freezegun.api.FakeDatetime.strptime",
        "freezegun.api.FakeDatetime.time",
        "freezegun.api.FakeDatetime.timestamp",
        "freezegun.api.FakeDatetime.timetuple",
        "freezegun.api.FakeDatetime.timetz",
        "freezegun.api.FakeDatetime.tzname",
        "freezegun.api.FakeDatetime.utcfromtimestamp",
        "freezegun.api.FakeDatetime.utcnow",
        "freezegun.api.FakeDatetime.utcoffset",
        "freezegun.api.FakeDatetime.utctimetupleDatetime.astimezone",
        "freezegun.api.fake_time",
        "fullmatch",
        "function_schema.core.get_function_schema",
        "html.escape",
        "html.unescape",
        "json.decoder.JSONDecodeError",
        "json.dumps",
        "json.loads",
        "list.append",
        "list.clear",
        "list.copy",
        "list.count",
        "list.extend",
        "list.index",
        "list.insert",
        "list.pop",
        "list.remove",
        "list.reverse",
        "list.sort",
        "match",
        "math.acos",
        "math.asin",
        "math.atan",
        "math.atan2",
        "math.ceil",
        "math.copysign",
        "math.cos",
        "math.degrees",
        "math.dist",
        "math.fabs",
        "math.factorial",
        "math.floor",
        "math.fmod",
        "math.frexp",
        "math.fsum",
        "math.gamma",
        "math.gcd",
        "math.hypot",
        "math.isclose",
        "math.isfinite",
        "math.isinf",
        "math.isnan",
        "math.isqrt",
        "math.lcm",
        "math.lgamma",
        "math.log",
        "math.log10",
        "math.log1p",
        "math.log2",
        "math.modf",
        "math.radians",
        "math.remainder",
        "math.sin",
        "math.sqrt",
        "math.tan",
        "math.trunc",
        "math.ulp",
        "mimetypes.guess_type",
        "pathlib.PurePath",
        "random.Random.betavariate",
        "random.Random.choice",
        "random.Random.expovariate",
        "random.Random.gauss",
        "random.Random.paretovariate",
        "random.Random.randint",
        "random.Random.sample",
        "random.Random.seed",
        "random.Random.shuffle",
        "random.Random.triangular",
        "random.Random.uniform",
        "re.compile",
        "re.escape",
        "re.findall",
        "re.finditer",
        "re.fullmatch",
        "re.match",
        "re.search",
        "re.split",
        "re.sub",
        "re.subn",
        "re2._Match.groupdict",
        "re2._Match.groups",
        "re2._Regexp.match",
        "scanner",
        "script.list_api",
        "search",
        "set.add",
        "set.clear",
        "set.difference_update",
        "set.discard",
        "set.intersection_update",
        "set.pop",
        "set.remove",
        "set.symmetric_difference_update",
        "set.update",
        "split",
        "str.capitalize",
        "str.casefold",
        "str.count",
        "str.encode",
        "str.endswith",
        "str.find",
        "str.index",
        "str.isalnum",
        "str.isalpha",
        "str.isascii",
        "str.isdecimal",
        "str.isdigit",
        "str.isidentifier",
        "str.islower",
        "str.isnumeric",
        "str.isprintable",
        "str.isspace",
        "str.istitle",
        "str.isupper",
        "str.join",
        "str.lower",
        "str.lstrip",
        "str.partition",
        "str.removeprefix",
        "str.removesuffix",
        "str.rfind",
        "str.rindex",
        "str.rpartition",
        "str.rsplit",
        "str.rstrip",
        "str.split",
        "str.splitlines",
        "str.startswith",
        "str.strip",
        "str.swapcase",
        "str.title",
        "str.upper",
        "string.Template",
        "string.Template.safe_substitute",
        "string.Template.substitute",
        "string.capwords",
        "typing.Annotated",
        "typing.Any",
        "typing.Callable",
        "typing.Dict",
        "typing.Iterable",
        "typing.List",
        "typing.Literal",
        "typing.Optional",
        "typing.Tuple",
        "typing.TypedDict",
        "typing.Union",
        "typing_extensions.Doc",
        "urllib.parse.parse_qs",
        "urllib.parse.parse_qsl",
        "urllib.parse.quote",
        "urllib.parse.quote_from_bytes",
        "urllib.parse.quote_plus",
        "urllib.parse.unquote",
        "urllib.parse.unquote_plus",
        "urllib.parse.unquote_to_bytes",
        "urllib.parse.urldefrag",
        "urllib.parse.urljoin",
        "urllib.parse.urlsplit",
        "urllib.parse.urlunsplit",
        "wsgiref.handlers.BaseHandler.start_response",
        "wsgiref.handlers.BaseHandler.write"
      ],
      "list_modules": {
        "ast": {
          "ClassDef": "ClassDef(identifier name, expr* bases, keyword* keywords, stmt* body, expr* decorator_list, type_param* type_params)",
          "FunctionDef": "FunctionDef(identifier name, arguments args, stmt* body, expr* decorator_list, expr? returns, string? type_comment, type_param* type_params)",
          "NodeTransformer": "A :class:`NodeVisitor` subclass that walks the abstract syntax tree and\nallows modification of nodes.\n\nThe `NodeTransformer` will walk the AST and use the return value of the\nvisitor methods to replace or remove the old node.  If the return value of\nthe visitor method is ``None``, the node will be removed from its location,\notherwise it is replaced with the return value.  The return value may be the\noriginal node in which case no replacement takes place.\n\nHere is an example transformer that rewrites all occurrences of name lookups\n(``foo``) to ``data['foo']``::\n\n   class RewriteName(NodeTransformer):\n\n       def visit_Name(self, node):\n           return Subscript(\n               value=Name(id='data', ctx=Load()),\n               slice=Constant(value=node.id),\n               ctx=node.ctx\n           )\n\nKeep in mind that if the node you're operating on has child nodes you must\neither transform the child nodes yourself or call the :meth:`generic_visit`\nmethod for the node first.\n\nFor nodes that were part of a collection of statements (that applies to all\nstatement nodes), the visitor may also return a list of nodes rather than\njust a single node.\n\nUsually you use the transformer like this::\n\n   node = YourTransformer().visit(node)",
          "NodeVisitor": "A node visitor base class that walks the abstract syntax tree and calls a\nvisitor function for every node found.  This function may return a value\nwhich is forwarded by the `visit` method.\n\nThis class is meant to be subclassed, with the subclass adding visitor\nmethods.\n\nPer default the visitor functions for the nodes are ``'visit_'`` +\nclass name of the node.  So a `TryFinally` node visit function would\nbe `visit_TryFinally`.  This behavior can be changed by overriding\nthe `visit` method.  If no visitor function exists for a node\n(return value `None`) the `generic_visit` visitor is used instead.\n\nDon't use the `NodeVisitor` if you want to apply changes to nodes during\ntraversing.  For this a special visitor exists (`NodeTransformer`) that\nallows modifications.",
          "dump": "Return a formatted dump of the tree in node.  This is mainly useful for\ndebugging purposes.  If annotate_fields is true (by default),\nthe returned string will show the names and the values for fields.\nIf annotate_fields is false, the result string will be more compact by\nomitting unambiguous field names.  Attributes such as line\nnumbers and column offsets are not dumped by default.  If this is wanted,\ninclude_attributes can be set to true.  If indent is a non-negative\ninteger or string, then the tree will be pretty-printed with that indent\nlevel. None (the default) selects the single line representation.",
          "fix_missing_locations": "When you compile a node tree with compile(), the compiler expects lineno and\ncol_offset attributes for every node that supports them.  This is rather\ntedious to fill in for generated nodes, so this helper adds these attributes\nrecursively where not already set, by setting them to the values of the\nparent node.  It works recursively starting at *node*.",
          "get_docstring": "Return the docstring for the given node or None if no docstring can\nbe found.  If the node provided does not have docstrings a TypeError\nwill be raised.\n\nIf *clean* is `True`, all tabs are expanded to spaces and any whitespace\nthat can be uniformly removed from the second line onwards is removed.",
          "get_source_segment": "Get source code segment of the *source* that generated *node*.\n\n    If some location information (`lineno`, `end_lineno`, `col_offset`,\n    or `end_col_offset`) is missing, return None.\n\n    If *padded* is `True`, the first line of a multi-line statement will\n    be padded with spaces to match its original position.",
          "literal_eval": "Evaluate an expression node or a string containing only a Python\nexpression.  The string or node provided may only consist of the following\nPython literal structures: strings, bytes, numbers, tuples, lists, dicts,\nsets, booleans, and None.\n\nCaution: A complex expression can overflow the C stack and cause a crash.",
          "parse": "Parse the source into an AST node.\nEquivalent to compile(source, filename, mode, PyCF_ONLY_AST).\nPass type_comments=True to get back type comments where the syntax allows.",
          "unparse": "",
          "walk": "Recursively yield all descendant nodes in the tree starting at *node*\n(including *node* itself), in no specified order.  This is useful if you\nonly want to modify nodes in place and don't care about the context."
        },
        "base64": {
          "b64decode": "Decode the Base64 encoded bytes-like object or ASCII string s.\n\n    Optional altchars must be a bytes-like object or ASCII string of length 2\n    which specifies the alternative alphabet used instead of the '+' and '/'\n    characters.\n\n    The result is returned as a bytes object.  A binascii.Error is raised if\n    s is incorrectly padded.\n\n    If validate is False (the default), characters that are neither in the\n    normal base-64 alphabet nor the alternative alphabet are discarded prior\n    to the padding check.  If validate is True, these non-alphabet characters\n    in the input result in a binascii.Error.\n    For more information about the strict base64 check, see:\n\n    https://docs.python.org/3.11/library/binascii.html#binascii.a2b_base64",
          "b64encode": "Encode the bytes-like object s using Base64 and return a bytes object.\n\n    Optional altchars should be a byte string of length 2 which specifies an\n    alternative alphabet for the '+' and '/' characters.  This allows an\n    application to e.g. generate url or filesystem safe Base64 strings.",
          "decodebytes": "Decode a bytestring of base-64 data into a bytes object.",
          "encodebytes": "Encode a bytestring into a bytes object containing multiple lines\n    of base-64 data.",
          "urlsafe_b64decode": "Decode bytes using the URL- and filesystem-safe Base64 alphabet.\n\n    Argument s is a bytes-like object or ASCII string to decode.  The result\n    is returned as a bytes object.  A binascii.Error is raised if the input\n    is incorrectly padded.  Characters that are not in the URL-safe base-64\n    alphabet, and are not a plus '+' or slash '/', are discarded prior to the\n    padding check.\n\n    The alphabet uses '-' instead of '+' and '_' instead of '/'.",
          "urlsafe_b64encode": "Encode bytes using the URL- and filesystem-safe Base64 alphabet.\n\n    Argument s is a bytes-like object to encode.  The result is returned as a\n    bytes object.  The alphabet uses '-' instead of '+' and '_' instead of\n    '/'."
        },
        "bencoder": {
          "decode": "Decodes *bdata* back to a Python object.\n\n    Parameters\n    ----------\n    bdata : ``bytes`` | ``str``\n        The B\u2011encoded payload.\n    strict_bytes : bool, default ``False``\n        * ``False`` (default) \u2013 try UTF\u20118 decode; if it succeeds return ``str``.\n        * ``True``  \u2013 **always** return raw ``bytes`` even if the payload is\n          valid UTF\u20118. This lets callers disambiguate the type when needed.",
          "encode": "B\u2011encodes *obj*.\n\n    Supported types: ``None``, ``bool``, ``int``, ``float``, ``bytes``,\n    ``bytearray``, ``str``, ``list``, ``tuple``, ``set``, ``frozenset``, ``dict``.\n\n    For ``dict`` keys only ``bytes`` or ``str`` are allowed; ``str`` keys are\n    UTF\u20118 encoded automatically. Keys are sorted lexicographically (byte order)\n    to guarantee deterministic output."
        },
        "dataclasses": {
          "asdict": "Return the fields of a dataclass instance as a new dictionary mapping\n    field names to field values.\n\n    Example usage::\n\n      @dataclass\n      class C:\n          x: int\n          y: int\n\n      c = C(1, 2)\n      assert asdict(c) == {'x': 1, 'y': 2}\n\n    If given, 'dict_factory' will be used instead of built-in dict.\n    The function applies recursively to field values that are\n    dataclass instances. This will also look into built-in containers:\n    tuples, lists, and dicts. Other objects are copied with 'copy.deepcopy()'.",
          "astuple": "Return the fields of a dataclass instance as a new tuple of field values.\n\n    Example usage::\n\n      @dataclass\n      class C:\n          x: int\n          y: int\n\n      c = C(1, 2)\n      assert astuple(c) == (1, 2)\n\n    If given, 'tuple_factory' will be used instead of built-in tuple.\n    The function applies recursively to field values that are\n    dataclass instances. This will also look into built-in containers:\n    tuples, lists, and dicts. Other objects are copied with 'copy.deepcopy()'.",
          "dataclass": "Add dunder methods based on the fields defined in the class.\n\n    Examines PEP 526 __annotations__ to determine fields.\n\n    If init is true, an __init__() method is added to the class. If repr\n    is true, a __repr__() method is added. If order is true, rich\n    comparison dunder methods are added. If unsafe_hash is true, a\n    __hash__() method is added. If frozen is true, fields may not be\n    assigned to after instance creation. If match_args is true, the\n    __match_args__ tuple is added. If kw_only is true, then by default\n    all fields are keyword-only. If slots is true, a new class with a\n    __slots__ attribute is returned.",
          "field": "Return an object to identify dataclass fields.\n\n    default is the default value of the field.  default_factory is a\n    0-argument function called to initialize a field's value.  If init\n    is true, the field will be a parameter to the class's __init__()\n    function.  If repr is true, the field will be included in the\n    object's repr().  If hash is true, the field will be included in the\n    object's hash().  If compare is true, the field will be used in\n    comparison functions.  metadata, if specified, must be a mapping\n    which is stored but not otherwise examined by dataclass.  If kw_only\n    is true, the field will become a keyword-only parameter to\n    __init__().\n\n    It is an error to specify both default and default_factory."
        },
        "datetime": {
          "UTC": "Fixed offset from UTC implementation of tzinfo.",
          "date": "date(year, month, day) --> date object",
          "datetime": "datetime(year, month, day[, hour[, minute[, second[, microsecond[,tzinfo]]]]])\n\nThe year, month and day arguments are required. tzinfo may be None, or an\ninstance of a tzinfo subclass. The remaining arguments may be ints.",
          "time": "time([hour[, minute[, second[, microsecond[, tzinfo]]]]]) --> a time object\n\nAll arguments are optional. tzinfo may be None, or an instance of\na tzinfo subclass. The remaining arguments may be ints.",
          "timedelta": "Difference between two datetime values.\n\ntimedelta(days=0, seconds=0, microseconds=0, milliseconds=0, minutes=0, hours=0, weeks=0)\n\nAll arguments are optional and default to 0.\nArguments may be integers or floats, and may be positive or negative.",
          "timezone": "Fixed offset from UTC implementation of tzinfo.",
          "tzinfo": "Abstract base class for time zone info objects."
        },
        "decimal": {
          "Decimal": "Construct a new Decimal object. 'value' can be an integer, string, tuple,\nor another Decimal object. If no value is given, return Decimal('0'). The\ncontext does not affect the conversion and is only passed to determine if\nthe InvalidOperation trap is active.",
          "ROUND_05UP": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'.",
          "ROUND_CEILING": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'.",
          "ROUND_DOWN": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'.",
          "ROUND_FLOOR": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'.",
          "ROUND_HALF_DOWN": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'.",
          "ROUND_HALF_EVEN": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'.",
          "ROUND_HALF_UP": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'.",
          "ROUND_UP": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'."
        },
        "dys": {
          "DysMsgException": "Used for dysvm _msg exceptions.",
          "DysQueryException": "Used for dysvm _query exceptions.",
          "_chain": "DEPRECATED: Use _msg() and _query() functions instead.\n\n:raises DeprecationError: Always raises this error to encourage migration to _msg and _query",
          "_msg": "Wrapper function for _chain(\"Msg\") that JSON encodes the params argument.\n\n:param params: A dictionary of parameters to be JSON encoded and passed to _chain\n:returns: The response from the chain",
          "_query": "Wrapper function for _chain(\"Query\") that JSON encodes the params argument.\n\n:param params: A dictionary of parameters to be JSON encoded and passed to _chain\n:returns: The response from the chain",
          "dys_eval": "Evaluate a string of Dsyon Protocol code.\n\n:param code: the code to evaluate\n:param scope: the scope to evaluate the code in\n:param track_func: a function to call after each node is evaluated use to track gas or scope size\n:param module_dict: a dictionary of modules to make available for import in the sandbox.\n                    Keys are module names, values are dicts of attributes.\n                    Example: {\"json\": {\"loads\": json.loads}, \"foo\": {\"bar\": my_custom_func}}\n\n:returns: the result of the evaluation",
          "emit_event": "Emits an event to the blockchain.\n\n:param key: the key of the event (string)\n:param value: the value of the event (string)\n\n:returns: the response from the chain",
          "get_attached_messages": "Returns the nfts sent to this function.",
          "get_attached_msg_results": "Returns the results of the attached messages.",
          "get_block_info": "Returns a dictionary containing the following block header information:\n- Height (int): The height of the block\n- Hash (bytes): The hash of the block header\n- Time (string): The time of the block in ISO format\n- AppHash (bytes): AppHash used in the current block header\n- ChainID (string): The chain ID of the block",
          "get_cumulative_size": "The cumulative size of memory used for each node called in this query or script",
          "get_executor_address": "Returns the address of the caller of this script.",
          "get_gas_consumed": "The total amount of gas consumed so far.",
          "get_gas_limit": "The maximum amount of gas that can be used in this query or transaction",
          "get_nodes_called": "The number of Python AST nodes evaluated in this query or transaction",
          "get_script_address": "Returns the address of this current script.",
          "get_script_code": "Returns the source code of this current script.",
          "get_script_name": "Returns the script name used in the execution message, if provided.\nReturns empty string if not provided.",
          "get_script_version": "Returns the version of this current script.",
          "list_functions": "Returns a copy of the set of whitelisted functions available in the Dyson Protocol environment.",
          "list_modules": "Returns a dictionary of available modules and their functions in the Dyson Protocol environment.\nThe returned dictionary has module names as keys and lists of available functions as values."
        },
        "enum": {
          "Enum": "Create a collection of name/value pairs.\n\nExample enumeration:\n\n>>> class Color(Enum):\n...     RED = 1\n...     BLUE = 2\n...     GREEN = 3\n\nAccess them by:\n\n- attribute access:\n\n  >>> Color.RED\n  <Color.RED: 1>\n\n- value lookup:\n\n  >>> Color(1)\n  <Color.RED: 1>\n\n- name lookup:\n\n  >>> Color['RED']\n  <Color.RED: 1>\n\nEnumerations can be iterated over, and know how many members they have:\n\n>>> len(Color)\n3\n\n>>> list(Color)\n[<Color.RED: 1>, <Color.BLUE: 2>, <Color.GREEN: 3>]\n\nMethods can be added to enumerations, and members can have their own\nattributes -- see the documentation for details.",
          "EnumType": "Metaclass for Enum",
          "IntEnum": "Enum where members are also (and must be) ints",
          "StrEnum": "Enum where members are also (and must be) strings"
        },
        "function_schema": {
          "Doc": "Define the documentation of a type annotation using ``Annotated``, to be\n         used in class attributes, function and method parameters, return values,\n         and variables.\n\n        The value should be a positional-only string literal to allow static tools\n        like editors and documentation generators to use it.\n\n        This complements docstrings.\n\n        The string value passed is available in the attribute ``documentation``.\n\n        Example::\n\n            >>> from typing_extensions import Annotated, Doc\n            >>> def hi(to: Annotated[str, Doc(\"Who to say hi to\")]) -> None: ...",
          "get_function_schema": "Returns a JSON schema for the given function.\n\nYou can annotate your function parameters with the special Annotated type.\nThen get the schema for the function without writing the schema by hand.\n\nEspecially useful for OpenAI API function-call.\n\nExample:\n>>> from typing import Annotated, Optional\n>>> import enum\n>>> def get_weather(\n...     city: Annotated[str, Doc(\"The city to get the weather for\")],\n...     unit: Annotated[\n...         Optional[str],\n...         Doc(\"The unit to return the temperature in\"),\n...         enum.Enum(\"Unit\", \"celcius fahrenheit\")\n...     ] = \"celcius\",\n... ) -> str:\n...     \"\"\"Returns the weather for the given city.\"\"\"\n...     return f\"Hello {name}, you are {age} years old.\"\n>>> get_function_schema(get_weather) # doctest: +SKIP\n{\n    'name': 'get_weather',\n    'description': 'Returns the weather for the given city.',\n    'parameters': {\n        'type': 'object',\n        'properties': {\n            'city': {\n                'type': 'string',\n                'description': 'The city to get the weather for'\n            },\n            'unit': {\n                'type': 'string',\n                'description': 'The unit to return the temperature in',\n                'enum': ['celcius', 'fahrenheit'],\n                'default': 'celcius'\n            }\n        },\n        'required': ['city']\n    }\n}"
        },
        "hashlib": {
          "md5": "Returns a md5 hash object; optionally initialized with a string",
          "sha1": "Returns a sha1 hash object; optionally initialized with a string",
          "sha256": "Returns a sha256 hash object; optionally initialized with a string",
          "sha512": "Returns a sha512 hash object; optionally initialized with a string"
        },
        "html": {
          "escape": "Replace special characters \"&\", \"<\" and \">\" to HTML-safe sequences.\nIf the optional flag quote is true (the default), the quotation mark\ncharacters, both double quote (\") and single quote (') characters are also\ntranslated.",
          "unescape": "Convert all named and numeric character references (e.g. &gt;, &#62;,\n&x3e;) in the string s to the corresponding unicode characters.\nThis function uses the rules defined by the HTML 5 standard\nfor both valid and invalid character references, and the list of\nHTML 5 named character references defined in html.entities.html5."
        },
        "io": {
          "BytesIO": "Buffered I/O implementation using an in-memory bytes buffer.",
          "StringIO": "Text I/O implementation using an in-memory buffer.\n\nThe initial_value argument sets the value of object.  The newline\nargument is like the one of TextIOWrapper's constructor."
        },
        "json": {
          "JSONDecodeError": "Subclass of ValueError with the following additional properties:\n\n    msg: The unformatted error message\n    doc: The JSON document being parsed\n    pos: The start index of doc where parsing failed\n    lineno: The line corresponding to pos\n    colno: The column corresponding to pos",
          "dumps": "Serialize ``obj`` to a JSON formatted ``str``.\n\n    If ``skipkeys`` is true then ``dict`` keys that are not basic types\n    (``str``, ``int``, ``float``, ``bool``, ``None``) will be skipped\n    instead of raising a ``TypeError``.\n\n    If ``ensure_ascii`` is false, then the return value can contain non-ASCII\n    characters if they appear in strings contained in ``obj``. Otherwise, all\n    such characters are escaped in JSON strings.\n\n    If ``check_circular`` is false, then the circular reference check\n    for container types will be skipped and a circular reference will\n    result in an ``RecursionError`` (or worse).\n\n    If ``allow_nan`` is false, then it will be a ``ValueError`` to\n    serialize out of range ``float`` values (``nan``, ``inf``, ``-inf``) in\n    strict compliance of the JSON specification, instead of using the\n    JavaScript equivalents (``NaN``, ``Infinity``, ``-Infinity``).\n\n    If ``indent`` is a non-negative integer, then JSON array elements and\n    object members will be pretty-printed with that indent level. An indent\n    level of 0 will only insert newlines. ``None`` is the most compact\n    representation.\n\n    If specified, ``separators`` should be an ``(item_separator, key_separator)``\n    tuple.  The default is ``(', ', ': ')`` if *indent* is ``None`` and\n    ``(',', ': ')`` otherwise.  To get the most compact JSON representation,\n    you should specify ``(',', ':')`` to eliminate whitespace.\n\n    ``default(obj)`` is a function that should return a serializable version\n    of obj or raise TypeError. The default simply raises TypeError.\n\n    If *sort_keys* is true (default: ``False``), then the output of\n    dictionaries will be sorted by key.\n\n    To use a custom ``JSONEncoder`` subclass (e.g. one that overrides the\n    ``.default()`` method to serialize additional types), specify it with\n    the ``cls`` kwarg; otherwise ``JSONEncoder`` is used.",
          "loads": "Deserialize ``s`` (a ``str``, ``bytes`` or ``bytearray`` instance\n    containing a JSON document) to a Python object.\n\n    ``object_hook`` is an optional function that will be called with the\n    result of any object literal decode (a ``dict``). The return value of\n    ``object_hook`` will be used instead of the ``dict``. This feature\n    can be used to implement custom decoders (e.g. JSON-RPC class hinting).\n\n    ``object_pairs_hook`` is an optional function that will be called with the\n    result of any object literal decoded with an ordered list of pairs.  The\n    return value of ``object_pairs_hook`` will be used instead of the ``dict``.\n    This feature can be used to implement custom decoders.  If ``object_hook``\n    is also defined, the ``object_pairs_hook`` takes priority.\n\n    ``parse_float``, if specified, will be called with the string\n    of every JSON float to be decoded. By default this is equivalent to\n    float(num_str). This can be used to use another datatype or parser\n    for JSON floats (e.g. decimal.Decimal).\n\n    ``parse_int``, if specified, will be called with the string\n    of every JSON int to be decoded. By default this is equivalent to\n    int(num_str). This can be used to use another datatype or parser\n    for JSON integers (e.g. float).\n\n    ``parse_constant``, if specified, will be called with one of the\n    following strings: -Infinity, Infinity, NaN.\n    This can be used to raise an exception if invalid JSON numbers\n    are encountered.\n\n    To use a custom ``JSONDecoder`` subclass, specify it with the ``cls``\n    kwarg; otherwise ``JSONDecoder`` is used."
        },
        "math": {
          "acos": "Return the arc cosine (measured in radians) of x.\n\nThe result is between 0 and pi.",
          "asin": "Return the arc sine (measured in radians) of x.\n\nThe result is between -pi/2 and pi/2.",
          "atan": "Return the arc tangent (measured in radians) of x.\n\nThe result is between -pi/2 and pi/2.",
          "atan2": "Return the arc tangent (measured in radians) of y/x.\n\nUnlike atan(y/x), the signs of both x and y are considered.",
          "ceil": "Return the ceiling of x as an Integral.\n\nThis is the smallest integer >= x.",
          "copysign": "Return a float with the magnitude (absolute value) of x but the sign of y.\n\nOn platforms that support signed zeros, copysign(1.0, -0.0)\nreturns -1.0.",
          "cos": "Return the cosine of x (measured in radians).",
          "degrees": "Convert angle x from radians to degrees.",
          "dist": "Return the Euclidean distance between two points p and q.\n\nThe points should be specified as sequences (or iterables) of\ncoordinates.  Both inputs must have the same dimension.\n\nRoughly equivalent to:\n    sqrt(sum((px - qx) ** 2.0 for px, qx in zip(p, q)))",
          "e": "Convert a string or number to a floating-point number, if possible.",
          "fabs": "Return the absolute value of the float x.",
          "factorial": "Find n!.\n\nRaise a ValueError if x is negative or non-integral.",
          "floor": "Return the floor of x as an Integral.\n\nThis is the largest integer <= x.",
          "fmod": "Return fmod(x, y), according to platform C.\n\nx % y may differ.",
          "frexp": "Return the mantissa and exponent of x, as pair (m, e).\n\nm is a float and e is an int, such that x = m * 2.**e.\nIf x is 0, m and e are both 0.  Else 0.5 <= abs(m) < 1.0.",
          "fsum": "Return an accurate floating-point sum of values in the iterable seq.\n\nAssumes IEEE-754 floating-point arithmetic.",
          "gamma": "Gamma function at x.",
          "gcd": "Greatest Common Divisor.",
          "hypot": "hypot(*coordinates) -> value\n\nMultidimensional Euclidean distance from the origin to a point.\n\nRoughly equivalent to:\n    sqrt(sum(x**2 for x in coordinates))\n\nFor a two dimensional point (x, y), gives the hypotenuse\nusing the Pythagorean theorem:  sqrt(x*x + y*y).\n\nFor example, the hypotenuse of a 3/4/5 right triangle is:\n\n    >>> hypot(3.0, 4.0)\n    5.0",
          "inf": "Convert a string or number to a floating-point number, if possible.",
          "isclose": "Determine whether two floating-point numbers are close in value.\n\n  rel_tol\n    maximum difference for being considered \"close\", relative to the\n    magnitude of the input values\n  abs_tol\n    maximum difference for being considered \"close\", regardless of the\n    magnitude of the input values\n\nReturn True if a is close in value to b, and False otherwise.\n\nFor the values to be considered close, the difference between them\nmust be smaller than at least one of the tolerances.\n\n-inf, inf and NaN behave similarly to the IEEE 754 Standard.  That\nis, NaN is not close to anything, even itself.  inf and -inf are\nonly close to themselves.",
          "isfinite": "Return True if x is neither an infinity nor a NaN, and False otherwise.",
          "isinf": "Return True if x is a positive or negative infinity, and False otherwise.",
          "isnan": "Return True if x is a NaN (not a number), and False otherwise.",
          "isqrt": "Return the integer part of the square root of the input.",
          "lcm": "Least Common Multiple.",
          "lgamma": "Natural logarithm of absolute value of Gamma function at x.",
          "log": "log(x, [base=math.e])\nReturn the logarithm of x to the given base.\n\nIf the base is not specified, returns the natural logarithm (base e) of x.",
          "log10": "Return the base 10 logarithm of x.",
          "log1p": "Return the natural logarithm of 1+x (base e).\n\nThe result is computed in a way which is accurate for x near zero.",
          "log2": "Return the base 2 logarithm of x.",
          "modf": "Return the fractional and integer parts of x.\n\nBoth results carry the sign of x and are floats.",
          "nan": "Convert a string or number to a floating-point number, if possible.",
          "pi": "Convert a string or number to a floating-point number, if possible.",
          "radians": "Convert angle x from degrees to radians.",
          "remainder": "Difference between x and the closest integer multiple of y.\n\nReturn x - n*y where n*y is the closest integer multiple of y.\nIn the case where x is exactly halfway between two multiples of\ny, the nearest even value of n is used. The result is always exact.",
          "sin": "Return the sine of x (measured in radians).",
          "sqrt": "Return the square root of x.",
          "tan": "Return the tangent of x (measured in radians).",
          "tau": "Convert a string or number to a floating-point number, if possible.",
          "trunc": "Truncates the Real x to the nearest Integral toward 0.\n\nUses the __trunc__ magic method.",
          "ulp": "Return the value of the least significant bit of the float x."
        },
        "mimetypes": {
          "guess_type": "Guess the type of a file based on its URL.\n\n    Return value is a tuple (type, encoding) where type is None if the\n    type can't be guessed (no or unknown suffix) or a string of the\n    form type/subtype, usable for a MIME Content-type header; and\n    encoding is None for no encoding or the name of the program used\n    to encode (e.g. compress or gzip).  The mappings are table\n    driven.  Encoding suffixes are case sensitive; type suffixes are\n    first tried case sensitive, then case insensitive.\n\n    The suffixes .tgz, .taz and .tz (case sensitive!) are all mapped\n    to \".tar.gz\".  (This is table-driven too, using the dictionary\n    suffix_map).\n\n    Optional `strict' argument when false adds a bunch of commonly found, but\n    non-standard types."
        },
        "pathlib": {
          "PurePath": "Base class for manipulating paths without I/O.\n\n    PurePath represents a filesystem path and offers operations which\n    don't imply any actual filesystem I/O.  Depending on your system,\n    instantiating a PurePath will return either a PurePosixPath or a\n    PureWindowsPath object.  You can also instantiate either of these classes\n    directly, regardless of your system."
        },
        "random": {
          "betavariate": "Beta distribution.\n\n        Conditions on the parameters are alpha > 0 and beta > 0.\n        Returned values range between 0 and 1.\n\n        The mean (expected value) and variance of the random variable are:\n\n            E[X] = alpha / (alpha + beta)\n            Var[X] = alpha * beta / ((alpha + beta)**2 * (alpha + beta + 1))",
          "choice": "Choose a random element from a non-empty sequence.",
          "expovariate": "Exponential distribution.\n\n        lambd is 1.0 divided by the desired mean.  It should be\n        nonzero.  (The parameter would be called \"lambda\", but that is\n        a reserved word in Python.)  Returned values range from 0 to\n        positive infinity if lambd is positive, and from negative\n        infinity to 0 if lambd is negative.\n\n        The mean (expected value) and variance of the random variable are:\n\n            E[X] = 1 / lambd\n            Var[X] = 1 / lambd ** 2",
          "gauss": "Gaussian distribution.\n\n        mu is the mean, and sigma is the standard deviation.  This is\n        slightly faster than the normalvariate() function.\n\n        Not thread-safe without a lock around calls.",
          "paretovariate": "Pareto distribution.  alpha is the shape parameter.",
          "randint": "Return random integer in range [a, b], including both end points.",
          "random": "random() -> x in the interval [0, 1).",
          "seed": "Initialize internal state from a seed.\n\n        The only supported seed types are None, int, float,\n        str, bytes, and bytearray.\n\n        None or no argument seeds from current time or from an operating\n        system specific randomness source if available.\n\n        If *a* is an int, all bits are used.\n\n        For version 2 (the default), all of the bits are used if *a* is a str,\n        bytes, or bytearray.  For version 1 (provided for reproducing random\n        sequences from older versions of Python), the algorithm for str and\n        bytes generates a narrower range of seeds.",
          "shuffle": "Shuffle list x in place, and return None.",
          "triangular": "Triangular distribution.\n\n        Continuous distribution bounded by given lower and upper limits,\n        and having a given mode value in-between.\n\n        http://en.wikipedia.org/wiki/Triangular_distribution\n\n        The mean (expected value) and variance of the random variable are:\n\n            E[X] = (low + high + mode) / 3\n            Var[X] = (low**2 + high**2 + mode**2 - low*high - low*mode - high*mode) / 18",
          "uniform": "Get a random number in the range [a, b) or [a, b] depending on rounding.\n\n        The mean (expected value) and variance of the random variable are:\n\n            E[X] = (a + b) / 2\n            Var[X] = (b - a) ** 2 / 12"
        },
        "re": {
          "ASCII": "An enumeration.",
          "DOTALL": "An enumeration.",
          "IGNORECASE": "An enumeration.",
          "LOCALE": "An enumeration.",
          "MULTILINE": "An enumeration.",
          "UNICODE": "An enumeration.",
          "VERBOSE": "An enumeration.",
          "compile": "Compile a regular expression pattern, returning a Pattern object.",
          "escape": "Escape special characters in a string.",
          "findall": "Return a list of all non-overlapping matches in the string.\n\n    If one or more capturing groups are present in the pattern, return\n    a list of groups; this will be a list of tuples if the pattern\n    has more than one group.\n\n    Empty matches are included in the result.",
          "finditer": "Return an iterator over all non-overlapping matches in the\n    string.  For each match, the iterator returns a Match object.\n\n    Empty matches are included in the result.",
          "fullmatch": "Try to apply the pattern to all of the string, returning\n    a Match object, or None if no match was found.",
          "match": "Try to apply the pattern at the start of the string, returning\n    a Match object, or None if no match was found.",
          "search": "Scan through string looking for a match to the pattern, returning\n    a Match object, or None if no match was found.",
          "split": "Split the source string by the occurrences of the pattern,\n    returning a list containing the resulting substrings.  If\n    capturing parentheses are used in pattern, then the text of all\n    groups in the pattern are also returned as part of the resulting\n    list.  If maxsplit is nonzero, at most maxsplit splits occur,\n    and the remainder of the string is returned as the final element\n    of the list.",
          "sub": "Return the string obtained by replacing the leftmost\n    non-overlapping occurrences of the pattern in string by the\n    replacement repl.  repl can be either a string or a callable;\n    if a string, backslash escapes in it are processed.  If it is\n    a callable, it's passed the Match object and must return\n    a replacement string to be used.",
          "subn": "Return a 2-tuple containing (new_string, number).\n    new_string is the string obtained by replacing the leftmost\n    non-overlapping occurrences of the pattern in the source\n    string by the replacement repl.  number is the number of\n    substitutions that were made. repl can be either a string or a\n    callable; if a string, backslash escapes in it are processed.\n    If it is a callable, it's passed the Match object and must\n    return a replacement string to be used."
        },
        "re2": {
          "ASCII": "An enumeration.",
          "DOTALL": "An enumeration.",
          "IGNORECASE": "An enumeration.",
          "LOCALE": "An enumeration.",
          "MULTILINE": "An enumeration.",
          "UNICODE": "An enumeration.",
          "VERBOSE": "An enumeration.",
          "compile": "Compile a regular expression pattern, returning a Pattern object.",
          "escape": "Escape special characters in a string.",
          "findall": "Return a list of all non-overlapping matches in the string.\n\n    If one or more capturing groups are present in the pattern, return\n    a list of groups; this will be a list of tuples if the pattern\n    has more than one group.\n\n    Empty matches are included in the result.",
          "finditer": "Return an iterator over all non-overlapping matches in the\n    string.  For each match, the iterator returns a Match object.\n\n    Empty matches are included in the result.",
          "fullmatch": "Try to apply the pattern to all of the string, returning\n    a Match object, or None if no match was found.",
          "match": "Try to apply the pattern at the start of the string, returning\n    a Match object, or None if no match was found.",
          "search": "Scan through string looking for a match to the pattern, returning\n    a Match object, or None if no match was found.",
          "split": "Split the source string by the occurrences of the pattern,\n    returning a list containing the resulting substrings.  If\n    capturing parentheses are used in pattern, then the text of all\n    groups in the pattern are also returned as part of the resulting\n    list.  If maxsplit is nonzero, at most maxsplit splits occur,\n    and the remainder of the string is returned as the final element\n    of the list.",
          "sub": "Return the string obtained by replacing the leftmost\n    non-overlapping occurrences of the pattern in string by the\n    replacement repl.  repl can be either a string or a callable;\n    if a string, backslash escapes in it are processed.  If it is\n    a callable, it's passed the Match object and must return\n    a replacement string to be used.",
          "subn": "Return a 2-tuple containing (new_string, number).\n    new_string is the string obtained by replacing the leftmost\n    non-overlapping occurrences of the pattern in the source\n    string by the replacement repl.  number is the number of\n    substitutions that were made. repl can be either a string or a\n    callable; if a string, backslash escapes in it are processed.\n    If it is a callable, it's passed the Match object and must\n    return a replacement string to be used."
        },
        "string": {
          "Template": "A string class for supporting $-substitutions.",
          "ascii_letters": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'.",
          "ascii_lowercase": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'.",
          "ascii_uppercase": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'.",
          "capwords": "capwords(s [,sep]) -> string\n\n    Split the argument into words using split, capitalize each\n    word using capitalize, and join the capitalized words using\n    join.  If the optional second argument sep is absent or None,\n    runs of whitespace characters are replaced by a single space\n    and leading and trailing whitespace are removed, otherwise\n    sep is used to split and join the words.",
          "digits": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'.",
          "hexdigits": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'.",
          "octdigits": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'.",
          "printable": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'.",
          "punctuation": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'.",
          "whitespace": "str(object='') -> str\nstr(bytes_or_buffer[, encoding[, errors]]) -> str\n\nCreate a new string object from the given object. If encoding or\nerrors is specified, then the object must expose a data buffer\nthat will be decoded using the given encoding and error handler.\nOtherwise, returns the result of object.__str__() (if defined)\nor repr(object).\nencoding defaults to sys.getdefaultencoding().\nerrors defaults to 'strict'."
        },
        "time": {
          "time": ""
        },
        "typing": {
          "Annotated": "Add context-specific metadata to a type.\n\n    Example: Annotated[int, runtime_check.Unsigned] indicates to the\n    hypothetical runtime_check module that this type is an unsigned int.\n    Every other consumer of this type can ignore this metadata and treat\n    this type as int.\n\n    The first argument to Annotated must be a valid type.\n\n    Details:\n\n    - It's an error to call `Annotated` with less than two arguments.\n    - Access the metadata via the ``__metadata__`` attribute::\n\n        assert Annotated[int, '$'].__metadata__ == ('$',)\n\n    - Nested Annotated types are flattened::\n\n        assert Annotated[Annotated[T, Ann1, Ann2], Ann3] == Annotated[T, Ann1, Ann2, Ann3]\n\n    - Instantiating an annotated type is equivalent to instantiating the\n    underlying type::\n\n        assert Annotated[C, Ann1](5) == C(5)\n\n    - Annotated can be used as a generic type alias::\n\n        type Optimized[T] = Annotated[T, runtime.Optimize()]\n        # type checker will treat Optimized[int]\n        # as equivalent to Annotated[int, runtime.Optimize()]\n\n        type OptimizedList[T] = Annotated[list[T], runtime.Optimize()]\n        # type checker will treat OptimizedList[int]\n        # as equivalent to Annotated[list[int], runtime.Optimize()]\n\n    - Annotated cannot be used with an unpacked TypeVarTuple::\n\n        type Variadic[*Ts] = Annotated[*Ts, Ann1]  # NOT valid\n\n      This would be equivalent to::\n\n        Annotated[T1, T2, T3, ..., Ann1]\n\n      where T1, T2 etc. are TypeVars, which would be invalid, because\n      only one type should be passed to Annotated.",
          "Any": "Special type indicating an unconstrained type.\n\n    - Any is compatible with every type.\n    - Any assumed to have all methods.\n    - All values assumed to be instances of Any.\n\n    Note that all the above statements are true from the point of view of\n    static type checkers. At runtime, Any should not be used with instance\n    checks.",
          "Callable": "Deprecated alias to collections.abc.Callable.\n\n    Callable[[int], str] signifies a function that takes a single\n    parameter of type int and returns a str.\n\n    The subscription syntax must always be used with exactly two\n    values: the argument list and the return type.\n    The argument list must be a list of types, a ParamSpec,\n    Concatenate or ellipsis. The return type must be a single type.\n\n    There is no syntax to indicate optional or keyword arguments;\n    such function types are rarely used as callback types.",
          "Dict": "A generic version of dict.",
          "Iterable": "A generic version of collections.abc.Iterable.",
          "List": "A generic version of list.",
          "Literal": "Special typing form to define literal types (a.k.a. value types).\n\n    This form can be used to indicate to type checkers that the corresponding\n    variable or function parameter has a value equivalent to the provided\n    literal (or one of several literals)::\n\n        def validate_simple(data: Any) -> Literal[True]:  # always returns True\n            ...\n\n        MODE = Literal['r', 'rb', 'w', 'wb']\n        def open_helper(file: str, mode: MODE) -> str:\n            ...\n\n        open_helper('/some/path', 'r')  # Passes type check\n        open_helper('/other/path', 'typo')  # Error in type checker\n\n    Literal[...] cannot be subclassed. At runtime, an arbitrary value\n    is allowed as type argument to Literal[...], but type checkers may\n    impose restrictions.",
          "Optional": "Optional[X] is equivalent to Union[X, None].",
          "Tuple": "Deprecated alias to builtins.tuple.\n\n    Tuple[X, Y] is the cross-product type of X and Y.\n\n    Example: Tuple[T1, T2] is a tuple of two elements corresponding\n    to type variables T1 and T2.  Tuple[int, float, str] is a tuple\n    of an int, a float and a string.\n\n    To specify a variable-length tuple of homogeneous type, use Tuple[T, ...].",
          "TypedDict": "A simple typed namespace. At runtime it is equivalent to a plain dict.\n\n    TypedDict creates a dictionary type such that a type checker will expect all\n    instances to have a certain set of keys, where each key is\n    associated with a value of a consistent type. This expectation\n    is not checked at runtime.\n\n    Usage::\n\n        >>> class Point2D(TypedDict):\n        ...     x: int\n        ...     y: int\n        ...     label: str\n        ...\n        >>> a: Point2D = {'x': 1, 'y': 2, 'label': 'good'}  # OK\n        >>> b: Point2D = {'z': 3, 'label': 'bad'}           # Fails type check\n        >>> Point2D(x=1, y=2, label='first') == dict(x=1, y=2, label='first')\n        True\n\n    The type info can be accessed via the Point2D.__annotations__ dict, and\n    the Point2D.__required_keys__ and Point2D.__optional_keys__ frozensets.\n    TypedDict supports an additional equivalent form::\n\n        Point2D = TypedDict('Point2D', {'x': int, 'y': int, 'label': str})\n\n    By default, all keys must be present in a TypedDict. It is possible\n    to override this by specifying totality::\n\n        class Point2D(TypedDict, total=False):\n            x: int\n            y: int\n\n    This means that a Point2D TypedDict can have any of the keys omitted. A type\n    checker is only expected to support a literal False or True as the value of\n    the total argument. True is the default, and makes all items defined in the\n    class body be required.\n\n    The Required and NotRequired special forms can also be used to mark\n    individual keys as being required or not required::\n\n        class Point2D(TypedDict):\n            x: int               # the \"x\" key must always be present (Required is the default)\n            y: NotRequired[int]  # the \"y\" key can be omitted\n\n    See PEP 655 for more details on Required and NotRequired.",
          "Union": "Union type; Union[X, Y] means either X or Y.\n\n    On Python 3.10 and higher, the | operator\n    can also be used to denote unions;\n    X | Y means the same thing to the type checker as Union[X, Y].\n\n    To define a union, use e.g. Union[int, str]. Details:\n    - The arguments must be types and there must be at least one.\n    - None as an argument is a special case and is replaced by\n      type(None).\n    - Unions of unions are flattened, e.g.::\n\n        assert Union[Union[int, str], float] == Union[int, str, float]\n\n    - Unions of a single argument vanish, e.g.::\n\n        assert Union[int] == int  # The constructor actually returns int\n\n    - Redundant arguments are skipped, e.g.::\n\n        assert Union[int, str, int] == Union[int, str]\n\n    - When comparing unions, the argument order is ignored, e.g.::\n\n        assert Union[int, str] == Union[str, int]\n\n    - You cannot subclass or instantiate a union.\n    - You can use Optional[X] as a shorthand for Union[X, None]."
        },
        "urllib": {
          "parse": "dict() -> new empty dictionary\ndict(mapping) -> new dictionary initialized from a mapping object's\n    (key, value) pairs\ndict(iterable) -> new dictionary initialized as if via:\n    d = {}\n    for k, v in iterable:\n        d[k] = v\ndict(**kwargs) -> new dictionary initialized with the name=value pairs\n    in the keyword argument list.  For example:  dict(one=1, two=2)"
        }
      }
    }


## Available Syntax

Here is a table of all the python syntax that is supported by Dyslang.


<table>
<thead><tr><th>AST Node</th><th>Demo</th><th>Result</th></tr></thead>
<tbody>
<tr><td colspan="3"><h3>Literals and Constants</h3></td></tr>
<tr><td>Constant</td><td><pre><code>42</code></pre></td><td><pre><code>SUCCESS: 42</code></pre></td></tr>
<tr><td>FormattedValue</td><td><pre><code>f'The answer is {40 + 2}'</code></pre></td><td><pre><code>SUCCESS: The answer is 42</code></pre></td></tr>
<tr><td>JoinedStr</td><td><pre><code>f'Hello {"world"}'</code></pre></td><td><pre><code>SUCCESS: Hello world</code></pre></td></tr>
<tr><td colspan="3"><h3>Collections</h3></td></tr>
<tr><td>List</td><td><pre><code>[1, 2, 3]</code></pre></td><td><pre><code>SUCCESS: [1, 2, 3]</code></pre></td></tr>
<tr><td>Tuple</td><td><pre><code>(1, 2, 3)</code></pre></td><td><pre><code>SUCCESS: (1, 2, 3)</code></pre></td></tr>
<tr><td>Set</td><td><pre><code>{1, 2, 3}</code></pre></td><td><pre><code>SUCCESS: {1, 2, 3}</code></pre></td></tr>
<tr><td>Dict</td><td><pre><code>{'a': 1, 'b': 2}</code></pre></td><td><pre><code>SUCCESS: {'a': 1, 'b': 2}</code></pre></td></tr>
<tr><td colspan="3"><h3>Variables</h3></td></tr>
<tr><td>Name_Load</td><td><pre><code>x = 1; x</code></pre></td><td><pre><code>SUCCESS: 1</code></pre></td></tr>
<tr><td>Name_Store</td><td><pre><code>x = 42</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>Name_Del</td><td><pre><code>y = 10; del y</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>Starred</td><td><pre><code>a, *b = [1, 2, 3, 4]; b</code></pre></td><td><pre><code>SUCCESS: [2, 3, 4]</code></pre></td></tr>
<tr><td colspan="3"><h3>Expressions</h3></td></tr>
<tr><td>UnaryOp_Not</td><td><pre><code>not True</code></pre></td><td><pre><code>SUCCESS: False</code></pre></td></tr>
<tr><td>UnaryOp_Invert</td><td><pre><code>~42</code></pre></td><td><pre><code>SUCCESS: -43</code></pre></td></tr>
<tr><td>UnaryOp_UAdd</td><td><pre><code>+42</code></pre></td><td><pre><code>SUCCESS: 42</code></pre></td></tr>
<tr><td>UnaryOp_USub</td><td><pre><code>-42</code></pre></td><td><pre><code>SUCCESS: -42</code></pre></td></tr>
<tr><td colspan="3"><h3>Binary Operations</h3></td></tr>
<tr><td>BinOp_Add</td><td><pre><code>1 + 2</code></pre></td><td><pre><code>SUCCESS: 3</code></pre></td></tr>
<tr><td>BinOp_Sub</td><td><pre><code>1 - 2</code></pre></td><td><pre><code>SUCCESS: -1</code></pre></td></tr>
<tr><td>BinOp_Mult</td><td><pre><code>2 * 3</code></pre></td><td><pre><code>SUCCESS: 6</code></pre></td></tr>
<tr><td>BinOp_Div</td><td><pre><code>6 / 3</code></pre></td><td><pre><code>SUCCESS: 2.0</code></pre></td></tr>
<tr><td>BinOp_FloorDiv</td><td><pre><code>7 // 3</code></pre></td><td><pre><code>SUCCESS: 2</code></pre></td></tr>
<tr><td>BinOp_Mod</td><td><pre><code>7 % 3</code></pre></td><td><pre><code>SUCCESS: 1</code></pre></td></tr>
<tr><td>BinOp_Pow</td><td><pre><code>2 ** 3</code></pre></td><td><pre><code>SUCCESS: 8</code></pre></td></tr>
<tr><td>BinOp_LShift</td><td><pre><code>1 &lt;&lt; 2</code></pre></td><td><pre><code>SUCCESS: 4</code></pre></td></tr>
<tr><td>BinOp_RShift</td><td><pre><code>8 &gt;&gt; 2</code></pre></td><td><pre><code>SUCCESS: 2</code></pre></td></tr>
<tr><td>BinOp_BitOr</td><td><pre><code>1 | 2</code></pre></td><td><pre><code>SUCCESS: 3</code></pre></td></tr>
<tr><td>BinOp_BitXor</td><td><pre><code>5 ^ 3</code></pre></td><td><pre><code>SUCCESS: 6</code></pre></td></tr>
<tr><td>BinOp_BitAnd</td><td><pre><code>5 &amp; 3</code></pre></td><td><pre><code>SUCCESS: 1</code></pre></td></tr>
<tr><td>BinOp_MatMult</td><td><pre><code># Not in basic Python: a @ b</code></pre></td><td><pre><code>SKIPPED</code></pre></td></tr>
<tr><td colspan="3"><h3>Boolean Operations</h3></td></tr>
<tr><td>BoolOp_And</td><td><pre><code>True and False</code></pre></td><td><pre><code>SUCCESS: False</code></pre></td></tr>
<tr><td>BoolOp_Or</td><td><pre><code>True or False</code></pre></td><td><pre><code>SUCCESS: True</code></pre></td></tr>
<tr><td colspan="3"><h3>Comparisons</h3></td></tr>
<tr><td>Compare_Eq</td><td><pre><code>1 == 1</code></pre></td><td><pre><code>SUCCESS: True</code></pre></td></tr>
<tr><td>Compare_NotEq</td><td><pre><code>1 != 2</code></pre></td><td><pre><code>SUCCESS: True</code></pre></td></tr>
<tr><td>Compare_Lt</td><td><pre><code>1 &lt; 2</code></pre></td><td><pre><code>SUCCESS: True</code></pre></td></tr>
<tr><td>Compare_LtE</td><td><pre><code>1 &lt;= 2</code></pre></td><td><pre><code>SUCCESS: True</code></pre></td></tr>
<tr><td>Compare_Gt</td><td><pre><code>2 &gt; 1</code></pre></td><td><pre><code>SUCCESS: True</code></pre></td></tr>
<tr><td>Compare_GtE</td><td><pre><code>2 &gt;= 1</code></pre></td><td><pre><code>SUCCESS: True</code></pre></td></tr>
<tr><td>Compare_Is</td><td><pre><code>1 is 1</code></pre></td><td><pre><code>SUCCESS: True</code></pre></td></tr>
<tr><td>Compare_IsNot</td><td><pre><code>1 is not 2</code></pre></td><td><pre><code>SUCCESS: True</code></pre></td></tr>
<tr><td>Compare_In</td><td><pre><code>1 in [1, 2, 3]</code></pre></td><td><pre><code>SUCCESS: True</code></pre></td></tr>
<tr><td>Compare_NotIn</td><td><pre><code>0 not in [1, 2, 3]</code></pre></td><td><pre><code>SUCCESS: True</code></pre></td></tr>
<tr><td colspan="3"><h3>Function and Method Calls</h3></td></tr>
<tr><td>Call</td><td><pre><code>len([1, 2, 3])</code></pre></td><td><pre><code>SUCCESS: 3</code></pre></td></tr>
<tr><td>Call_Kwargs</td><td><pre><code>dict(a=1, b=2)</code></pre></td><td><pre><code>SUCCESS: {'a': 1, 'b': 2}</code></pre></td></tr>
<tr><td>Call_Starred</td><td><pre><code>sum([1, 2, 3])</code></pre></td><td><pre><code>SUCCESS: 6</code></pre></td></tr>
<tr><td>Call_KwStarred</td><td><pre><code>dict(**{'a': 1, 'b': 2})</code></pre></td><td><pre><code>SUCCESS: {'a': 1, 'b': 2}</code></pre></td></tr>
<tr><td colspan="3"><h3>Conditional Expressions</h3></td></tr>
<tr><td>IfExp</td><td><pre><code>1 if True else 2</code></pre></td><td><pre><code>SUCCESS: 1</code></pre></td></tr>
<tr><td colspan="3"><h3>Attribute Access</h3></td></tr>
<tr><td>Attribute</td><td><pre><code>'hello'.upper()</code></pre></td><td><pre><code>SUCCESS: HELLO</code></pre></td></tr>
<tr><td colspan="3"><h3>Subscripting</h3></td></tr>
<tr><td>Subscript</td><td><pre><code>[1, 2, 3][0]</code></pre></td><td><pre><code>SUCCESS: 1</code></pre></td></tr>
<tr><td>Slice</td><td><pre><code>[1, 2, 3, 4][1:3]</code></pre></td><td><pre><code>SUCCESS: [2, 3]</code></pre></td></tr>
<tr><td colspan="3"><h3>Comprehensions</h3></td></tr>
<tr><td>ListComp</td><td><pre><code>[x for x in range(5)]</code></pre></td><td><pre><code>SUCCESS: [0, 1, 2, 3, 4]</code></pre></td></tr>
<tr><td>SetComp</td><td><pre><code>{x for x in range(5)}</code></pre></td><td><pre><code>SUCCESS: {0, 1, 2, 3, 4}</code></pre></td></tr>
<tr><td>DictComp</td><td><pre><code>{x: x*x for x in range(5)}</code></pre></td><td><pre><code>SUCCESS: {0: 0, 1: 1, 2: 4, 3: 9, 4: 16}</code></pre></td></tr>
<tr><td>GeneratorExp</td><td><pre><code>(x for x in range(5))</code></pre></td><td><pre><code>SUCCESS: [0, 1, 2, 3, 4]</code></pre></td></tr>
<tr><td colspan="3"><h3>Assignments</h3></td></tr>
<tr><td>Assign</td><td><pre><code>x = 42</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>AnnAssign</td><td><pre><code>x: int = 42</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>AugAssign</td><td><pre><code>x = 1; x += 1</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>NamedExpr</td><td><pre><code>(x := 42)</code></pre></td><td><pre><code>SUCCESS: 42</code></pre></td></tr>
<tr><td colspan="3"><h3>Control Flow</h3></td></tr>
<tr><td>If</td><td><pre><code>if True: pass</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>For</td><td><pre><code>for i in range(5): pass</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>While</td><td><pre><code>while False: pass</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>Break</td><td><pre><code>for i in range(5):
    if i &gt; 2: break</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>Continue</td><td><pre><code>for i in range(5):
    if i &lt; 2: continue</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td colspan="3"><h3>Exception Handling</h3></td></tr>
<tr><td>Try</td><td><pre><code>try:
    1/0
except ZeroDivisionError:
    pass</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>Raise</td><td><pre><code>try:
    raise ValueError('example error')
except ValueError:
    pass</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>Assert</td><td><pre><code>assert True, 'message'</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td colspan="3"><h3>Function and Class Definitions</h3></td></tr>
<tr><td>FunctionDef</td><td><pre><code>def func(x): return x*2</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>Lambda</td><td><pre><code>lambda x: x*2</code></pre></td><td><pre><code>SUCCESS: &lt;function &lt;lambda&gt; at 0x1234&gt;</code></pre></td></tr>
<tr><td>Return</td><td><pre><code>def func(): return 42</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>ClassDef</td><td><pre><code>class MyClass:
    pass</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td colspan="3"><h3>Import Statements</h3></td></tr>
<tr><td>Import</td><td><pre><code>try: import json
except ImportError: pass</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>ImportFrom</td><td><pre><code>try: from json import loads
except ImportError: pass</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td colspan="3"><h3>With Statements</h3></td></tr>
<tr><td>With</td><td><pre><code>with open('file.txt', 'w') as f: pass</code></pre></td><td><pre><code>ERROR: Not Implemented</code></pre></td></tr>
<tr><td colspan="3"><h3>Async/Await</h3></td></tr>
<tr><td>AsyncFunctionDef</td><td><pre><code>async def func(): pass</code></pre></td><td><pre><code>ERROR: Not Implemented</code></pre></td></tr>
<tr><td>Await</td><td><pre><code>async def func():
    await other_func()</code></pre></td><td><pre><code>ERROR: Not Implemented</code></pre></td></tr>
<tr><td>AsyncFor</td><td><pre><code>async def func():
    async for i in aiter(): pass</code></pre></td><td><pre><code>ERROR: Not Implemented</code></pre></td></tr>
<tr><td>AsyncWith</td><td><pre><code>async def func():
    async with acontext() as a: pass</code></pre></td><td><pre><code>ERROR: Not Implemented</code></pre></td></tr>
<tr><td colspan="3"><h3>Yield Expressions</h3></td></tr>
<tr><td>Yield</td><td><pre><code>def gen(): yield 42</code></pre></td><td><pre><code>ERROR: Not Implemented</code></pre></td></tr>
<tr><td>YieldFrom</td><td><pre><code>def gen(): yield from [1, 2, 3]</code></pre></td><td><pre><code>ERROR: Not Implemented</code></pre></td></tr>
<tr><td colspan="3"><h3>Others</h3></td></tr>
<tr><td>Delete</td><td><pre><code>x = 1; del x</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>Pass</td><td><pre><code>pass</code></pre></td><td><pre><code>SUCCESS: None</code></pre></td></tr>
<tr><td>Global</td><td><pre><code>global x</code></pre></td><td><pre><code>ERROR: Not Implemented</code></pre></td></tr>
<tr><td>Nonlocal</td><td><pre><code>nonlocal x</code></pre></td><td><pre><code>ERROR: Not Implemented</code></pre></td></tr>
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
