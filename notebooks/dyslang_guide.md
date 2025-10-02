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

    {"result":"{\"result\":{\"@type\":\"/cosmos.bank.v1beta1.QueryBalanceResponse\",\"balance\":{\"denom\":\"udys\",\"amount\":\"8976949766\"}},\"stdout\":\"\",\"exception\":null,\"nodes_called\":23,\"gas_limit\":18446744073709551615,\"script_gas_consumed\":1013342,\"cumsize\":6563}","attached_message_results":[]}
    {
      "denom": "udys",
      "amount": "8976949766"
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
    # Execute the script using dysond query script exec
    out = get_ipython().getoutput(
        f"dysond query script run --script-address {ALICE_ADDRESS} --executor-address {ALICE_ADDRESS} --function-name query_multiple_balances --extra-code-path {f.name} -o json" 
    )
out = '\n'.join(out)
print(out)
result = json.loads(out)
json_result = json.loads(result['result'])['result']
assert 'alice_balance' in json_result, "Alice's balance not found in the result"
assert 'bob_balance' in json_result, "Bob's balance not found in the result"
print(json.dumps(json_result, indent=2))
```

    {"result":"{\"result\":{\"alice_balance\":{\"@type\":\"/cosmos.bank.v1beta1.QueryBalanceResponse\",\"balance\":{\"denom\":\"udys\",\"amount\":\"8976949766\"}},\"bob_balance\":{\"@type\":\"/cosmos.bank.v1beta1.QueryBalanceResponse\",\"balance\":{\"denom\":\"udys\",\"amount\":\"10000000000\"}}},\"stdout\":\"\",\"exception\":null,\"nodes_called\":39,\"gas_limit\":18446744073709551615,\"script_gas_consumed\":1023235,\"cumsize\":15345}","attached_message_results":[]}
    {
      "alice_balance": {
        "@type": "/cosmos.bank.v1beta1.QueryBalanceResponse",
        "balance": {
          "denom": "udys",
          "amount": "8976949766"
        }
      },
      "bob_balance": {
        "@type": "/cosmos.bank.v1beta1.QueryBalanceResponse",
        "balance": {
          "denom": "udys",
          "amount": "10000000000"
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

    {"result":"{\"result\":{\"initial_gas\":1008377,\"after_query_gas\":1017181,\"final_gas\":1061601,\"query_gas\":8804,\"iterations_gas\":44420,\"per_iteration\":8884.0},\"stdout\":\"Iteration 1 of 5\\nIteration 2 of 5\\nIteration 3 of 5\\nIteration 4 of 5\\nIteration 5 of 5\\n\",\"exception\":null,\"nodes_called\":133,\"gas_limit\":18446744073709551615,\"script_gas_consumed\":1082116,\"cumsize\":75337}","attached_message_results":[]}
    Gas report for benchmark operations:
    - Initial gas consumed: 1008377
    - Gas after query: 1017181
    - Gas after iterations: 1061601
    - Total gas for query: 8804
    - Total gas for iterations: 44420
    - Average gas per iteration: 8884.0


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

    {"result":"{\"result\":{\"script_address\":\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\",\"caller_address\":\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\",\"is_self_call\":true},\"stdout\":\"\",\"exception\":null,\"nodes_called\":27,\"gas_limit\":18446744073709551615,\"script_gas_consumed\":1014469,\"cumsize\":8798}","attached_message_results":[]}
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
    - Height: 141
    - Chain ID: chain-a
    - Time: 2025-10-02T09:58:50.8775Z


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

    {"result":"{\"result\":{\"attached_messages\":[{\"@type\":\"/cosmos.bank.v1beta1.MsgSend\",\"from_address\":\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\",\"to_address\":\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\",\"amount\":[{\"denom\":\"udys\",\"amount\":\"12\"}]},{\"@type\":\"/cosmos.bank.v1beta1.MsgSend\",\"from_address\":\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\",\"to_address\":\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\",\"amount\":[{\"denom\":\"udys\",\"amount\":\"34\"}]}],\"attached_msg_results\":[{\"@type\":\"/cosmos.bank.v1beta1.MsgSendResponse\"},{\"@type\":\"/cosmos.bank.v1beta1.MsgSendResponse\"}]},\"stdout\":\"\",\"exception\":null,\"nodes_called\":18,\"gas_limit\":18446744073709551615,\"script_gas_consumed\":1057404,\"cumsize\":12601}","attached_message_results":[{"@type":"/cosmos.bank.v1beta1.MsgSendResponse"},{"@type":"/cosmos.bank.v1beta1.MsgSendResponse"}]}
    {'attached_messages': [{'@type': '/cosmos.bank.v1beta1.MsgSend', 'from_address': 'dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej', 'to_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'amount': [{'denom': 'udys', 'amount': '12'}]}, {'@type': '/cosmos.bank.v1beta1.MsgSend', 'from_address': 'dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej', 'to_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'amount': [{'denom': 'udys', 'amount': '34'}]}], 'attached_msg_results': [{'@type': '/cosmos.bank.v1beta1.MsgSendResponse'}, {'@type': '/cosmos.bank.v1beta1.MsgSendResponse'}]}
    Message: {'@type': '/cosmos.bank.v1beta1.MsgSend', 'from_address': 'dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej', 'to_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'amount': [{'denom': 'udys', 'amount': '12'}]}
    Result: {'@type': '/cosmos.bank.v1beta1.MsgSendResponse'}
    Message: {'@type': '/cosmos.bank.v1beta1.MsgSend', 'from_address': 'dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej', 'to_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'amount': [{'denom': 'udys', 'amount': '34'}]}
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
      "height": "143",
      "txhash": "2441A07E8DDB7997BE7C13497EE5D8FC99AE0D145738B33E7DF5B9A6F0BD4368",
      "codespace": "",
      "code": 0,
      "data": "12C2010A282F6479736F6E70726F746F636F6C2E7363726970742E76312E4D736745786563526573706F6E73651295010A92017B22726573756C74223A7B226576656E745F656D6974746564223A747275657D2C227374646F7574223A22222C22657863657074696F6E223A6E756C6C2C226E6F6465735F63616C6C6564223A31372C226761735F6C696D6974223A31303030303030302C227363726970745F6761735F636F6E73756D6564223A313033393833332C2263756D73697A65223A323431367D",
      "raw_log": "",
      "logs": [],
      "info": "",
      "gas_wanted": "10000000",
      "gas_used": "1039833",
      "tx": null,
      "timestamp": "",
      "events": [
        {
          "type": "tx",
          "attributes": [
            {
              "key": "acc_seq",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/43",
              "index": true
            }
          ]
        },
        {
          "type": "tx",
          "attributes": [
            {
              "key": "signature",
              "value": "v5r6Qv7MeKpyfRIELtEYmqYn+yozS0+0fxVreQ2uQNV+8UfCTBAxKqDnzU/hjqrbXotGXaginzw0ltC4+92uFw==",
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
              "value": "{\"result\":\"{\\\"result\\\":{\\\"event_emitted\\\":true},\\\"stdout\\\":\\\"\\\",\\\"exception\\\":null,\\\"nodes_called\\\":17,\\\"gas_limit\\\":10000000,\\\"script_gas_consumed\\\":1039833,\\\"cumsize\\\":2416}\",\"attached_message_results\":[]}",
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
        "acc_seq": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/43",
        "signature": "v5r6Qv7MeKpyfRIELtEYmqYn+yozS0+0fxVreQ2uQNV+8UfCTBAxKqDnzU/hjqrbXotGXaginzw0ltC4+92uFw=="
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
        "response": "{\"result\":\"{\\\"result\\\":{\\\"event_emitted\\\":true},\\\"stdout\\\":\\\"\\\",\\\"exception\\\":null,\\\"nodes_called\\\":17,\\\"gas_limit\\\":10000000,\\\"script_gas_consumed\\\":1039833,\\\"cumsize\\\":2416}\",\"attached_message_results\":[]}",
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
      "result": "{\"result\":{\"arithmetic\":14,\"string_ops\":\"hello WORLD\",\"with_variables\":50,\"multi_statement\":38},\"stdout\":\"\",\"exception\":null,\"nodes_called\":84,\"gas_limit\":18446744073709551615,\"script_gas_consumed\":1014997,\"cumsize\":12729}",
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
print(json.dumps(json_out, indent=2))
# Extract and interpret the coverage data
coverage_data = json.loads(json_out['result'])['result']
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

    {
      "result": "{\"result\":[[[3,0,8,15,\"FunctionDef\",\"\"],[1,68]],[[3,11,3,12,\"arg\",\"\"],[2,96]],[[3,14,3,15,\"arg\",\"\"],[2,96]],[[4,4,5,16,\"If\",\"\"],[2,288]],[[4,7,4,8,\"Name\",\"\"],[2,288]],[[5,8,5,16,\"Return\",\"\"],[2,288]],[[5,15,5,16,\"Name\",\"\"],[2,288]],[[6,4,7,16,\"If\",\"\"],[0,0]],[[6,7,6,8,\"Name\",\"\"],[0,0]],[[7,8,7,16,\"Return\",\"\"],[0,0]],[[7,15,7,16,\"Name\",\"\"],[0,0]],[[8,4,8,15,\"Return\",\"\"],[0,0]],[[8,11,8,15,\"Constant\",\"\"],[0,0]],[[10,0,13,16,\"FunctionDef\",\"\"],[1,117]],[[12,4,12,16,\"Expr\",\"\"],[1,128]],[[12,4,12,16,\"Call\",\"\"],[1,128]],[[12,4,12,10,\"Name\",\"\"],[1,154]],[[12,11,12,12,\"Constant\",\"\"],[1,128]],[[12,14,12,15,\"Constant\",\"\"],[1,128]],[[13,4,13,16,\"Expr\",\"\"],[1,128]],[[13,4,13,16,\"Call\",\"\"],[1,128]],[[13,4,13,10,\"Name\",\"\"],[1,154]],[[13,11,13,12,\"Constant\",\"\"],[1,128]],[[13,14,13,15,\"Constant\",\"\"],[1,128]]],\"stdout\":\"\",\"exception\":null,\"nodes_called\":23,\"gas_limit\":18446744073709551615,\"script_gas_consumed\":1008465,\"cumsize\":2794}",
      "attached_message_results": []
    }
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

## Building a Simple dApp

Let's bring everything together by building a simple counter dApp that demonstrates the integration of dyslang with the Storage module:


```python
import json
import shlex

# Create the counter dApp script
counter_app_script = '''
from dys import _query, _msg, get_script_address
import json
from datetime import datetime

def get_counter():
    """Get the current counter value or initialize it"""
    script_address = get_script_address()
    # Try to query the existing counter
    try:
        response = _query({
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": script_address,
            "index": "counter"
        })
        counter_data = json.loads(response["entry"]["data"])
        return counter_data["value"]
    except Exception as e:
        if "NotFound" in str(e):
            _msg({
                "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
                "owner": script_address,
                "index": "counter",
                "data": json.dumps({
                    "value": 0, 
                    "updated_at": datetime.now().isoformat()
                })
            })
            return 0
        else:
            raise e



def increment_counter():
    """Increment the counter and store the new value"""
    # Get the current counter value
    current_value = get_counter()
    
    # Increment it
    new_value = current_value + 1
    
    # Store the new value
    script_address = get_script_address()

    _msg({
        "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
        "owner": script_address,
         "index": "counter",
         "data": json.dumps({
            "value": new_value,
            "updated_at": datetime.now().isoformat()
        })
    })

    
    return {
        "previous_value": current_value,
        "new_value": new_value
    }

def reset_counter():
    """Reset the counter to zero"""
    script_address = get_script_address()
    _msg({
        "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
        "owner": script_address,
        "indexes": ["counter"]
    })
    return {
        "result": "Counter reset to 0"
    }
'''

# Save the counter app script
with open('/tmp/counter_app.py', 'w') as f:
    f.write(counter_app_script)
    f.close()

print(f"Setting up counter dApp for alice...")

# First, upload the script to Alice's account
out = ! dysond tx script update \
    --code-path /tmp/counter_app.py \
    --from alice \
    --gas "20000000" \
    --output json -y | dysond query wait-tx --output json
out = '\n'.join(out)
result = json.loads(out)
assert result['code'] == 0, f"Error: {result['raw_log']}"

for i in range(3):
    # Now let's test the counter app
    # 1. Get initial counter (should be 0, then set to 1)
    out = ! dysond tx script exec \
        --script-address $ALICE_ADDRESS \
        --function-name increment_counter \
        --from alice \
        --gas "10000000" \
        --output json -y | dysond query wait-tx --output json | python ../scripts/parse_exec_script_tx.py
    out = '\n'.join(out)
    result = json.loads(out)
    assert result['code'] == 0, f"Error: {result['raw_log']}"
    counter_result = result['script_result']['result']['result']
    print(f"Counter state: {counter_result['previous_value']} -> {counter_result['new_value']}")

# 4. Reset the counter for cleanup
print(f"Cleaning up...")
out = ! dysond tx script exec \
    --script-address $ALICE_ADDRESS \
    --function-name reset_counter \
    --from alice \
    --extra-code-path /tmp/counter_app.py \
    --output json -y  \
    --gas 10000000 | dysond query wait-tx --output json | python ../scripts/parse_exec_script_tx.py
out = '\n'.join(out)
result = json.loads(out)
assert result['code'] == 0, f"Error: {result['raw_log']}"

print(f"Counter dApp demo completed successfully!")
```

    Setting up counter dApp for alice...


    Counter state: 0 -> 1


    Counter state: 1 -> 2


    Counter state: 2 -> 3
    Cleaning up...


    Counter dApp demo completed successfully!


## Summary

In this guide, we've explored the powerful features of the Dyson Protocol Language Module (dyslang). We've seen how to:

1. **Query the Blockchain**: Use `_query` to retrieve blockchain state
2. **Submit Transactions**: Use `_msg` to modify blockchain state
3. **Monitor Gas**: Track and manage computational resources
4. **Access Context**: Retrieve script and block information
5. **Handle Messages**: Work with transaction messages
6. **Emit Events**: Produce blockchain events
7. **Evaluate Code**: Execute dynamic Python code
8. **Test Coverage**: Analyze script execution paths
9. **Build dApps**: Combine these features to create decentralized applications

The dyslang module provides a secure, sandboxed environment for executing Python code on the blockchain, making it possible to build sophisticated decentralized applications with familiar Python syntax and powerful blockchain capabilities.

For more information on building scripts with these functions and integrating with other modules like Storage, check out the [Script Module Documentation](SCRIPT.md) and the other guides in the Dyson Protocol documentation.
