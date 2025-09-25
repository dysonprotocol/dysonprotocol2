# Dyson Protocol Crontask Module Guide

This notebook serves as a comprehensive guide to the Crontask module in Dyson Protocol, demonstrating how to schedule on-chain transactions for future execution.

## 1. Introduction to Crontasks

The Crontask module enables scheduled execution of transactions on the Dyson Protocol blockchain. It allows users to create tasks that will execute at a specific time in the future, with an expiration deadline.

**Key Features**:
- **Scheduled Transactions**: Schedule any transaction to be executed at a future block height
- **Flexible Timing**: Set execution times up to the maximum allowed by chain parameters
- **Expiration Management**: Tasks expire if not executed by their expiry timestamp
- **Gas Configuration**: Set gas limits and prices for task execution
- **Script Integration**: Seamless interaction with on-chain Python scripts for advanced automation

**Use Cases**:
- Autonomous payouts
- Timed auctions
- Game rounds with automatic progression
- Price oracles with regular updates
- Scheduled maintenance operations

## 2. Understanding Module Parameters

First, let's check the current module parameters:


```python
import json
import shlex
import time
from datetime import datetime

# Get module parameters
! dysond query crontask params -o json
```

    {
      "params": {
        "block_gas_limit": "3000000",
        "expiry_limit": "86400",
        "max_scheduled_time": "86400",
        "clean_up_time": "86400",
        "max_subscription_duration": "24h0m0s",
        "min_stake_per_subscription": {
          "denom": "udys",
          "amount": "1000"
        }
      }
    }


The module parameters include:
- `block_gas_limit`: Maximum gas that can be consumed by scheduled tasks in a single block
- `expiry_limit`: Maximum time (in seconds) that a task can be scheduled for before expiration
- `max_scheduled_time`: Maximum time (in seconds) in the future that a task can be scheduled

## 3. Command Overview

The Crontask module provides the following commands:


### Transaction Commands


```python
! dysond tx crontask
```

    Transactions commands for the crontask module
    
    Usage:
      dysond tx crontask [flags]
      dysond tx crontask [command]
    
    Available Commands:
      create-subscription Create a new event subscription
      create-task         Create a new scheduled task
      delete-subscription Delete a subscription
      delete-task         Delete a scheduled task
      renew-subscription  Renew a subscription and recharge the fee
      update-params       Update crontask module parameters (governance authority only)
    
    Flags:
      -h, --help   help for crontask
    
    Global Flags:
          --home string         directory for config and data (default "/var/folders/th/nv7lq13d7gx0jfhfg68wdh040000gn/T/tmpmqxio3oi/chain-a-node-1")
          --log_format string   The logging format (json|plain) (default "plain")
          --log_level string    The logging level (trace|debug|info|warn|error|fatal|panic|disabled or '*:<level>,<key>:<level>') (default "info")
          --log_no_color        Disable colored logs
          --trace               print out full stack trace on errors
    
    Use "dysond tx crontask [command] --help" for more information about a command.


### Query Commands


```python
! dysond query crontask 
```

    Querying commands for the crontask module
    
    Usage:
      dysond query crontask [flags]
      dysond query crontask [command]
    
    Available Commands:
      metrics                   Execute the Metrics RPC method
      params                    Query module parameters
      subscription-by-id        Query a subscription by ID
      subscriptions-all         Query all subscriptions
      subscriptions-by-creator  Query subscriptions by creator address
      subscriptions-by-status   Execute the SubscriptionsByStatus RPC method
      task-by-id                Query a task by ID
      tasks-all                 Query all tasks
      tasks-by-address          Query tasks by creator address
      tasks-by-status-gas-price Query tasks by status and gas price
      tasks-by-status-timestamp Query tasks by status and timestamp
    
    Flags:
      -h, --help   help for crontask
    
    Global Flags:
          --home string         directory for config and data (default "/var/folders/th/nv7lq13d7gx0jfhfg68wdh040000gn/T/tmpmqxio3oi/chain-a-node-1")
          --log_format string   The logging format (json|plain) (default "plain")
          --log_level string    The logging level (trace|debug|info|warn|error|fatal|panic|disabled or '*:<level>,<key>:<level>') (default "info")
          --log_no_color        Disable colored logs
          --trace               print out full stack trace on errors
    
    Use "dysond query crontask [command] --help" for more information about a command.


## 4. Creating a Crontask

### Getting your address for the examples


```python
# Get the address from bob account (best case scenario)
NAME = "bob"
out = ! dysond keys show -a {NAME}
print(out)
ADDRESS = out[0]
print(f"Using address: {ADDRESS}")
```

    ['dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el']
    Using address: dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el


### Creating a Simple Bank Transfer Task

Let's create a task to send a small amount of tokens back to ourselves as a simple example.


```python
# Create the task
import time
import json

# adjust as needed
SCHEDULED_TIME = int(time.time() + 1)
EXPIRY_TIME = int(time.time() + 86400)

# Print in human-readable format for reference
from datetime import datetime
print(f"Scheduled time: {datetime.fromtimestamp(SCHEDULED_TIME).strftime('%Y-%m-%d %H:%M:%S')} (Unix: {SCHEDULED_TIME})")
print(f"Expiry time: {datetime.fromtimestamp(EXPIRY_TIME).strftime('%Y-%m-%d %H:%M:%S')} (Unix: {EXPIRY_TIME})")

# Create a message for the task
TASK_MSG = {
    "@type": "/cosmos.bank.v1beta1.MsgSend",
    "from_address": ADDRESS,
    "to_address": ADDRESS,
    "amount": [{"denom": "udys", "amount": "1"}]
}

# Convert the message to a properly escaped JSON string for shell use
TASK_MSG_JSON = shlex.quote(json.dumps(TASK_MSG))


tx = ! dysond tx crontask create-task \
  --scheduled-timestamp {SCHEDULED_TIME} \
  --expiry-timestamp {EXPIRY_TIME} \
  --task-gas-limit 200000 \
  --task-gas-fee 1udys \
  --msgs {TASK_MSG_JSON} \
  --from {NAME} -y -o json | jq .txhash -r ; sleep 0.01
txhash = tx[0]
print(f"Transaction hash: {txhash}")

```

    Scheduled time: 2025-09-25 02:24:37 (Unix: 1758759877)
    Expiry time: 2025-09-26 02:24:36 (Unix: 1758846276)


    Transaction hash: 5F006928C675D413A15815C7BF2B597CFDAB553DB5224801CC70C0A644866E1F



```python

# Wait for transaction to be processed
tx_result = ! dysond query wait-tx "{txhash}" -o json
print(tx_result)
tx_result = json.loads("".join(tx_result))
print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

```

    ['{"height":"535","txhash":"5F006928C675D413A15815C7BF2B597CFDAB553DB5224801CC70C0A644866E1F","codespace":"","code":0,"data":"12360A302F6479736F6E70726F746F636F6C2E63726F6E7461736B2E76312E4D73674372656174655461736B526573706F6E736512020801","raw_log":"","logs":[],"info":"","gas_wanted":"200000","gas_used":"69610","tx":null,"timestamp":"","events":[{"type":"tx","attributes":[{"key":"acc_seq","value":"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el/0","index":true}]},{"type":"tx","attributes":[{"key":"signature","value":"+j3oNMjsFz36cbJTucZcFd0En2n8AGNDLfXuLKVNAdoa10zSArk0/6ycEXCezdenrh7CcHE0m7eOejt86wsL8g==","index":true}]},{"type":"message","attributes":[{"key":"action","value":"/dysonprotocol.crontask.v1.MsgCreateTask","index":true},{"key":"sender","value":"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el","index":true},{"key":"module","value":"crontask","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"dysonprotocol.crontask.v1.EventTaskCreated","attributes":[{"key":"creator","value":"\\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\\"","index":true},{"key":"task_id","value":"\\"1\\"","index":true},{"key":"msg_index","value":"0","index":true}]}]}']
    Tx error code: 0


### Getting the Task ID

Let's extract the task ID from the transaction result. We'll query for the most recent task created by our address.


```python
# Print the transaction events to see what happened

# Extract the task ID from the event attributes
for event in tx_result.get('events', []):
    if event.get('type') == 'dysonprotocol.crontask.v1.EventTaskCreated':
        print(json.dumps(event, indent=2))

        for attr in event.get('attributes', []):
            if attr.get('key') == 'task_id':
                TASK_ID = attr.get('value').strip('"')
                break

print(f"Created task ID: {TASK_ID}")
```

    {
      "type": "dysonprotocol.crontask.v1.EventTaskCreated",
      "attributes": [
        {
          "key": "creator",
          "value": "\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\"",
          "index": true
        },
        {
          "key": "task_id",
          "value": "\"1\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }
    Created task ID: 1


## 5. Querying Task Information

### Query a Task by ID


```python
# Query task by ID
task_info = ! dysond query crontask task-by-id --task-id {TASK_ID} -o json 
task_info_str = ''.join(task_info)
print(json.dumps(json.loads(task_info_str), indent=2))
```

    {
      "task": {
        "task_id": "1",
        "creator": "dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el",
        "scheduled_timestamp": "1758759877",
        "expiry_timestamp": "1758846276",
        "task_gas_limit": "200000",
        "task_gas_price": "0.000005000000000000udys",
        "task_gas_fee": {
          "denom": "udys",
          "amount": "1"
        },
        "msgs": [
          {
            "type": "/cosmos.bank.v1beta1.MsgSend",
            "value": {
              "from_address": "dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el",
              "to_address": "dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el",
              "amount": [
                {
                  "denom": "udys",
                  "amount": "1"
                }
              ]
            }
          }
        ],
        "status": "SCHEDULED",
        "creation_time": "1758759877",
        "creation_block_height": "535"
      }
    }


### Query All Tasks by Address


```python
# Query all tasks by address (we will only return 3 tasks for this example)
out = ! dysond query crontask tasks-by-address --creator {ADDRESS} -o json
tasks_by_addr_json = json.loads(''.join(out))
tasks_by_addr_json
```




    {'tasks': [{'task_id': '1',
       'creator': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el',
       'scheduled_timestamp': '1758759877',
       'expiry_timestamp': '1758846276',
       'task_gas_limit': '200000',
       'task_gas_price': '0.000005000000000000udys',
       'task_gas_fee': {'denom': 'udys', 'amount': '1'},
       'msgs': [{'type': '/cosmos.bank.v1beta1.MsgSend',
         'value': {'from_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el',
          'to_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el',
          'amount': [{'denom': 'udys', 'amount': '1'}]}}],
       'status': 'SCHEDULED',
       'creation_time': '1758759877',
       'creation_block_height': '535'}],
     'pagination': {'total': '1'}}



### Query Tasks by Status
The status can be one of the following: 
- PENDING: The task is scheduled to be executed
- DONE: The task has been executed successfully
- FAILED: The task failed when executed
- EXPIRED: The task has expired by the expiry timestamp and was not executed


```python
# Query tasks that are status DONE

out = ! dysond query crontask tasks-by-status-timestamp --status DONE -o json
json.loads(''.join(out))
```




    {'pagination': {}}




```python
# List pending tasks
print("Pending tasks:")
! dysond query crontask tasks-by-status-timestamp --status PENDING -o json | jq -M
```

    Pending tasks:


    {
      "pagination": {}
    }


### Wait for the Task to Execute


```python
task_status = "PENDING"
# loop until the task is done or expired

print("Checking task status...", end="")

while task_status == "PENDING":
    print(".", end="")
    time.sleep(0.1)
    out = ! dysond query crontask task-by-id --task-id {TASK_ID} -o json
    task_json = json.loads(''.join(out))
    task_status = task_json['task']['status']
    scheduled_time = task_json['task']['scheduled_timestamp']
    current_time = int(time.time())

task_json
```

    Checking task status....




    {'task': {'task_id': '1',
      'creator': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el',
      'scheduled_timestamp': '1758759877',
      'expiry_timestamp': '1758846276',
      'task_gas_limit': '200000',
      'task_gas_price': '0.000005000000000000udys',
      'task_gas_fee': {'denom': 'udys', 'amount': '1'},
      'msgs': [{'type': '/cosmos.bank.v1beta1.MsgSend',
        'value': {'from_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el',
         'to_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el',
         'amount': [{'denom': 'udys', 'amount': '1'}]}}],
      'msg_results': [{'type': '/cosmos.bank.v1beta1.MsgSendResponse',
        'value': {}}],
      'status': 'DONE',
      'creation_time': '1758759877',
      'task_gas_consumed': '19539',
      'execution_timestamp': '1758759877',
      'creation_block_height': '535',
      'execution_block_height': '536'}}



## 6. Deleting a Task



```python
# Query task by ID to check current status
out = ! dysond query crontask task-by-id --task-id {TASK_ID} -o json
out = ''.join(out)
# Check if the task exists
assert 'NotFound' not in out, f"Task not found: {out}"

# Parse the JSON response
task_json = json.loads(out)
task_id = task_json['task']['task_id']

# Delete the task
out = ! dysond tx crontask delete-task --task-id {task_id} --from {NAME} -y | dysond query wait-tx -o json

tx_result = json.loads("".join(out))
print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

# Find the EventTaskDeleted event
for event in tx_result['events']:
    if event['type'] == 'dysonprotocol.crontask.v1.EventTaskDeleted':
        print(json.dumps(event, indent=2))

```

    Tx error code: 0
    {
      "type": "dysonprotocol.crontask.v1.EventTaskDeleted",
      "attributes": [
        {
          "key": "creator",
          "value": "\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\"",
          "index": true
        },
        {
          "key": "task_id",
          "value": "\"1\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }


## 7. Advanced Example: Integration with Python Scripts

One of the most powerful features of Dyson Protocol is the ability to combine the Crontask module with the Script module. This allows for complex automation directly on-chain.

Here's a Python script that creates a self-perpetuating countdown:


```python
# Create the countdown script file
countdown_script = '''
import datetime
import json
from dys import _msg, _query, get_script_address, get_executor_address

def countdown(count=10):
    """Creates a countdown that repeats every 3 seconds"""
    # Convert to int in case passed as string from CLI
    remaining = int(count)
    
    # Print current count
    print(f"COUNTDOWN: {remaining}")
    
    # Stop if we've reached zero
    if remaining <= 0:
        return "Countdown complete!"
    
    # Schedule next countdown for 1 seconds from now
    now = datetime.datetime.now()
    scheduled_time = int((now + datetime.timedelta(seconds=1)).timestamp())
    expiry_time = int((now + datetime.timedelta(days=1)).timestamp())
    
    # Create a message to call this script again with count-1
    exec_script_msg = {
        "@type": "/dysonprotocol.script.v1.MsgExec",
        "executor_address": get_executor_address(),
        "script_address": get_script_address(),
        "function_name": "countdown",
        "args": json.dumps([remaining - 1]),
        "kwargs": "{}"
    }
    
    # Create crontask to execute our script again with decremented count
    result = _msg({
        "@type": "/dysonprotocol.crontask.v1.MsgCreateTask",
        "creator": get_executor_address(),
        "scheduled_timestamp": str(scheduled_time),
        "expiry_timestamp": str(expiry_time),
        "task_gas_limit": "2000000",
        "task_gas_fee": {"denom": "udys", "amount": "1"},
        "msgs": [exec_script_msg]
    })
    
    return {
        "remaining": remaining,
        "next_execution": scheduled_time,
        "task_result": result
    }
'''

script_path = '/tmp/crontask_countdown.py'
with open(script_path, 'w') as f:
    f.write(countdown_script)

print("Created countdown script at /tmp/crontask_countdown.py")
```

    Created countdown script at /tmp/crontask_countdown.py


### Deploy the Script

Now let's upload this script to the chain:


```python
# Upload the script only if script module is avail
update_cmd = f"dysond tx script update --from {ADDRESS} --code-path {script_path} -y -o json  --gas auto | jq .txhash -r"
tx = ! {update_cmd}
txhash = tx[1]
print(f"Script update transaction hash: {txhash}")

# Wait for transaction to be processed
tx_result = ! dysond query wait-tx "{txhash}" -o json ; sleep 0.01
tx_result = json.loads("".join(tx_result))
print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

print("Script uploaded successfully.")

for event in tx_result['events']:
    if event['type'] == 'dysonprotocol.script.v1.EventUpdateScript':
        print(json.dumps(event, indent=2))

```

    Script update transaction hash: E1066928CFD65D4C0FB8C778744A0C70EEAECBC395EC14FCE80A1D16D96193A6


    Tx error code: 0
    Script uploaded successfully.
    {
      "type": "dysonprotocol.script.v1.EventUpdateScript",
      "attributes": [
        {
          "key": "script_address",
          "value": "\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\"",
          "index": true
        },
        {
          "key": "version",
          "value": "\"1\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }


### Execute the Script

Now let's execute the script with a starting countdown value of 1:


```python
# Execute the script only if script module is available and upload was successful

# Properly escape the arguments
args_escaped = shlex.quote('[1]')

exec_cmd = f"dysond tx script exec --script-address {ADDRESS} --from {ADDRESS} --function-name countdown --args {args_escaped} -y --output json --gas 10000000 | jq .txhash -r"
tx = ! {exec_cmd}
txhash = tx[0]
print(f"Script execution transaction hash: {txhash}")
# Some delay to ensure the transaction is available
time.sleep(0.01)
# Wait for transaction to be processed
tx_result = ! dysond query wait-tx "{txhash}" -o json | ../scripts/parse_exec_script_tx.py
tx_result = json.loads("".join(tx_result))
print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

print("Script executed successfully.")
tx_result
```

    Script execution transaction hash: 89501342A9641502D839E00EE06D0D0BB315B923C350A598A8F21F08A91BB895


    Tx error code: 0
    Script executed successfully.





    {'code': 0,
     'script_result': {'result': {'result': {'remaining': 1,
        'next_execution': 1758759880,
        'task_result': {'@type': '/dysonprotocol.crontask.v1.MsgCreateTaskResponse',
         'task_id': '2'}},
       'stdout': 'COUNTDOWN: 1\n',
       'exception': None,
       'nodes_called': 123,
       'gas_limit': 10000000,
       'script_gas_consumed': 1128269,
       'cumsize': 65935},
      'attached_message_results': []},
     'raw_log': '',
     'events': [{'type': 'tx',
       'attributes': [{'key': 'acc_seq',
         'value': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el/3',
         'index': True}]},
      {'type': 'tx',
       'attributes': [{'key': 'signature',
         'value': 'cEMIoQjd1h5OLgvz071QGMoO/BUJQ+sCf6JVL8nylI4If+ctqe4phmCECCje4GS1XuH9qQ6R7ZUvZ9O+GOYfZA==',
         'index': True}]},
      {'type': 'message',
       'attributes': [{'key': 'action',
         'value': '/dysonprotocol.script.v1.MsgExec',
         'index': True},
        {'key': 'sender',
         'value': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el',
         'index': True},
        {'key': 'module', 'value': 'script', 'index': True},
        {'key': 'msg_index', 'value': '0', 'index': True}]},
      {'type': 'dysonprotocol.crontask.v1.EventTaskCreated',
       'attributes': [{'key': 'creator',
         'value': '"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el"',
         'index': True},
        {'key': 'task_id', 'value': '"2"', 'index': True},
        {'key': 'msg_index', 'value': '0', 'index': True}]},
      {'type': 'dysonprotocol.script.v1.EventExecScript',
       'attributes': [{'key': 'executor_address',
         'value': '"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el"',
         'index': True},
        {'key': 'function_name', 'value': '"countdown"', 'index': True},
        {'key': 'request',
         'value': '{"executor_address":"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el","script_address":"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el","script_name":"","extra_code":"","function_name":"countdown","args":"[1]","kwargs":"","attached_messages":[]}',
         'index': True},
        {'key': 'response',
         'value': '{"result":"{\\"result\\":{\\"remaining\\":1,\\"next_execution\\":1758759880,\\"task_result\\":{\\"@type\\":\\"/dysonprotocol.crontask.v1.MsgCreateTaskResponse\\",\\"task_id\\":\\"2\\"}},\\"stdout\\":\\"COUNTDOWN: 1\\\\n\\",\\"exception\\":null,\\"nodes_called\\":123,\\"gas_limit\\":10000000,\\"script_gas_consumed\\":1128269,\\"cumsize\\":65935}","attached_message_results":[]}',
         'index': True},
        {'key': 'script_address',
         'value': '"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el"',
         'index': True},
        {'key': 'script_name', 'value': '""', 'index': True},
        {'key': 'msg_index', 'value': '0', 'index': True}]}]}



### Query all the tasks created by the script



```python
# Get the task ID from the script result
task_id = tx_result['script_result']['result']['result']['task_result']['task_id']
print(f"Created task ID: {task_id}")

# Follow the chain of tasks
current_task_id = task_id
task_count = 0
max_tasks = 10  # Safety limit to prevent infinite loops

while current_task_id and task_count < max_tasks:
    task_count += 1
    print(f"\n--- Examining task #{task_count} (ID: {current_task_id}) ---")
    
     # Wait for pending tasks to complete
    task_status = 'SCHEDULED'
    while task_status in ('SCHEDULED', 'PENDING'):
        print("Waiting for it to be executed...")
        time.sleep(0.05)
        # Query the current task
        out = ! dysond query crontask task-by-id --task-id {current_task_id} -o json
        out = ''.join(out)
        
        task_json = json.loads(out)
        print("Task details:", task_json)

        task_status = task_json['task']['status']
        print(f"Task status: {task_status}")
    
    # Parse the result to get the next task ID
    task_result = json.loads(task_json['task']['msg_results'][0]['value']['result'])
    print(f"Task result:", task_result)
    
    # Check if there's a next task
    if 'result' in task_result and 'task_result' in task_result['result']:
        # Check if we've reached the end of the countdown
        remaining = task_result['result'].get('remaining', 0)
            
        # Get the next task ID
        current_task_id = task_result['result']['task_result']['task_id']
        print(f"Next task ID: {current_task_id}")
    else:
        print("No next task found. Chain complete.")
        break
            
print(f"\nProcessed {task_count} tasks in the chain.")

```

    Created task ID: 2
    
    --- Examining task #1 (ID: 2) ---
    Waiting for it to be executed...


    Task details: {'task': {'task_id': '2', 'creator': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'scheduled_timestamp': '1758759880', 'expiry_timestamp': '1758846279', 'task_gas_limit': '2000000', 'task_gas_price': '0.000000500000000000udys', 'task_gas_fee': {'denom': 'udys', 'amount': '1'}, 'msgs': [{'type': '/dysonprotocol.script.v1.MsgExec', 'value': {'executor_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'script_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'function_name': 'countdown', 'args': '[0]', 'kwargs': '{}'}}], 'status': 'SCHEDULED', 'creation_time': '1758759879', 'creation_block_height': '539'}}
    Task status: SCHEDULED
    Waiting for it to be executed...


    Task details: {'task': {'task_id': '2', 'creator': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'scheduled_timestamp': '1758759880', 'expiry_timestamp': '1758846279', 'task_gas_limit': '2000000', 'task_gas_price': '0.000000500000000000udys', 'task_gas_fee': {'denom': 'udys', 'amount': '1'}, 'msgs': [{'type': '/dysonprotocol.script.v1.MsgExec', 'value': {'executor_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'script_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'function_name': 'countdown', 'args': '[0]', 'kwargs': '{}'}}], 'status': 'SCHEDULED', 'creation_time': '1758759879', 'creation_block_height': '539'}}
    Task status: SCHEDULED
    Waiting for it to be executed...


    Task details: {'task': {'task_id': '2', 'creator': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'scheduled_timestamp': '1758759880', 'expiry_timestamp': '1758846279', 'task_gas_limit': '2000000', 'task_gas_price': '0.000000500000000000udys', 'task_gas_fee': {'denom': 'udys', 'amount': '1'}, 'msgs': [{'type': '/dysonprotocol.script.v1.MsgExec', 'value': {'executor_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'script_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'function_name': 'countdown', 'args': '[0]', 'kwargs': '{}'}}], 'status': 'SCHEDULED', 'creation_time': '1758759879', 'creation_block_height': '539'}}
    Task status: SCHEDULED
    Waiting for it to be executed...


    Task details: {'task': {'task_id': '2', 'creator': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'scheduled_timestamp': '1758759880', 'expiry_timestamp': '1758846279', 'task_gas_limit': '2000000', 'task_gas_price': '0.000000500000000000udys', 'task_gas_fee': {'denom': 'udys', 'amount': '1'}, 'msgs': [{'type': '/dysonprotocol.script.v1.MsgExec', 'value': {'executor_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'script_address': 'dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el', 'function_name': 'countdown', 'args': '[0]', 'kwargs': '{}'}}], 'msg_results': [{'type': '/dysonprotocol.script.v1.MsgExecResponse', 'value': {'result': '{"result":"Countdown complete!","stdout":"COUNTDOWN: 0\\n","exception":null,"nodes_called":33,"gas_limit":2000000,"script_gas_consumed":1018137,"cumsize":9997}'}}], 'status': 'DONE', 'creation_time': '1758759879', 'task_gas_consumed': '1018137', 'execution_timestamp': '1758759880', 'creation_block_height': '539', 'execution_block_height': '540'}}
    Task status: DONE
    Task result: {'result': 'Countdown complete!', 'stdout': 'COUNTDOWN: 0\n', 'exception': None, 'nodes_called': 33, 'gas_limit': 2000000, 'script_gas_consumed': 1018137, 'cumsize': 9997}
    No next task found. Chain complete.
    
    Processed 1 tasks in the chain.


## 8. Best Practices

1. **Gas Management**:
   - Set appropriate gas limits based on the complexity of your task
   - Use higher gas fees for time-sensitive operations

2. **Scheduling**:
   - Be aware of the chain parameter limits for scheduling tasks
   - Set reasonable expiry times based on the importance of task execution

3. **Error Handling**:
   - In scripts that schedule tasks, implement error handling and monitoring
   - Consider creating retry mechanisms for important tasks

4. **Security**:
   - Be cautious with messages in tasks, as they will execute with the creator's permissions
   - Avoid storing sensitive information in task messages

5. **Performance**:
   - Limit the number of tasks scheduled for the same timestamp
   - Spread out tasks over time when possible to reduce blockchain congestion

## 9. Troubleshooting

### Common Issues

1. **Task not executing**: 
   - Check if the scheduled timestamp has been reached
   - Verify that the task has not expired
   - Ensure sufficient gas was provided

2. **Task execution failing**:
   - Check task status and error messages
   - Verify that message permissions are correct
   - Confirm that gas limit is sufficient

3. **Cannot delete task**:
   - Only pending tasks can be deleted
   - Only the creator can delete their tasks

4. **Task creation failing**:
   - Ensure scheduled time is within allowed parameters
   - Verify message format is correct
   - Check that sufficient funds are available for gas fees

## 10. Summary

The Crontask module in Dyson Protocol provides a powerful mechanism for scheduling on-chain transactions. By combining it with the Script module, developers can create complex automation workflows directly on-chain.

Key points to remember:
1. Tasks execute automatically when their scheduled time is reached
2. Tasks expire if not executed by their expiry time
3. Properly manage gas to ensure task execution
4. Monitor task status for successful execution
5. For complex automation, combine with on-chain scripts

With these tools, you can build truly decentralized applications with time-based automation, without relying on off-chain infrastructure.
