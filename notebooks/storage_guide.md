# Dyson Protocol Storage Module Guide

This notebook demonstrates the key features of the Dyson Protocol's Storage module, which provides on-chain persistent key-value storage functionality. The Storage module allows dApps and scripts to maintain state between transactions and serves as a foundation for building robust decentralized applications.

## Introduction to Storage

The Storage module provides a simple yet powerful key-value store with these key features:

- **Key-Value Store**: Persistent on-chain storage of data
- **Owner-Based Access Control**: Only owners can modify their storage entries
- **Prefix-Based Queries**: List entries with common prefixes for efficient data organization
- **JSON Support**: Easy storage of complex data structures as JSON
- **Script Integration**: Seamless interaction with on-chain Python scripts

## Command Overview

Let's explore the available commands for the Storage module:


```python
# Transaction commands
! dysond tx storage -h
```

    Storage subcommands
    
    Usage:
      dysond tx storage [flags]
      dysond tx storage [command]
    
    Available Commands:
      delete        Delete storage entries by indexes
      set           Set or update a storage entry with the specified index and data
      update-params Execute the UpdateParams RPC method
    
    Flags:
      -h, --help   help for storage
    
    Global Flags:
          --home string         directory for config and data (default "/var/folders/th/nv7lq13d7gx0jfhfg68wdh040000gn/T/tmpurco0hch/chain-a-node-1")
          --log_format string   The logging format (json|plain) (default "plain")
          --log_level string    The logging level (trace|debug|info|warn|error|fatal|panic|disabled or '*:<level>,<key>:<level>') (default "info")
          --log_no_color        Disable colored logs
          --trace               print out full stack trace on errors
    
    Use "dysond tx storage [command] --help" for more information about a command.



```python
# Query commands
! dysond query storage -h
```

    Querying commands for the storage module
    
    Usage:
      dysond query storage [flags]
      dysond query storage [command]
    
    Available Commands:
      get         Query the value of an index in the storage by owner
      list        List all storage entries for an owner, optionally filtered by index prefix
      metrics     Query storage metrics for a given owner address
      params      Query the storage module parameters
    
    Flags:
      -h, --help   help for storage
    
    Global Flags:
          --home string         directory for config and data (default "/var/folders/th/nv7lq13d7gx0jfhfg68wdh040000gn/T/tmpurco0hch/chain-a-node-1")
          --log_format string   The logging format (json|plain) (default "plain")
          --log_level string    The logging level (trace|debug|info|warn|error|fatal|panic|disabled or '*:<level>,<key>:<level>') (default "info")
          --log_no_color        Disable colored logs
          --trace               print out full stack trace on errors
    
    Use "dysond query storage [command] --help" for more information about a command.


## Setting Up Your Account

Let's set up our account for the following examples:


```python
# Get the address from bob account
[ADDRESS] = ! dysond keys show -a bob
print(f"Using address: {ADDRESS}")
```

    Using address: dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el


## Basic Storage Operations

The Storage module provides basic CRUD operations. Let's explore these operations with practical examples.

### Creating/Updating Storage Entries

Let's store some user profile data. The Storage module accepts JSON data, making it ideal for structured information:


```python
# Store a user profile as JSON
import json
import shlex

PROFILE_DATA = shlex.quote(json.dumps({"name": "Bob", "bio": "Blockchain enthusiast", "skills": ["Smart Contracts", "DeFi", "Web3"]}))

out = ! dysond tx storage set \
    --index "profile/info" \
    --data $PROFILE_DATA \
    --from $ADDRESS \
    -y | dysond q wait-tx -o json

out = '\n'.join(out)
print(out)
tx_result = json.loads(out)

for event in tx_result['events']:
    if "dysonprotocol" in event['type']:
        print(json.dumps(event, indent=2))
        break



```

    {"height":"76","txhash":"2DECF8A5602AF1F4A87510563B61FC1E522124BC1D9B50CECF386A970FE3B2EE","codespace":"","code":0,"data":"12310A2F2F6479736F6E70726F746F636F6C2E73746F726167652E76312E4D736753746F72616765536574526573706F6E7365","raw_log":"","logs":[],"info":"","gas_wanted":"200000","gas_used":"54081","tx":null,"timestamp":"","events":[{"type":"tx","attributes":[{"key":"acc_seq","value":"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el/5","index":true}]},{"type":"tx","attributes":[{"key":"signature","value":"4A+jieI740XiLBPkzqW/t5TdsHAkm8Oh6dicOrdkTwJlvIlEHId/ihZVh8+xbaAnnZf8GYkt1NN3edggkEikOA==","index":true}]},{"type":"message","attributes":[{"key":"action","value":"/dysonprotocol.storage.v1.MsgStorageSet","index":true},{"key":"sender","value":"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el","index":true},{"key":"module","value":"storage","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"dysonprotocol.storage.v1.EventStorageUpdated","attributes":[{"key":"address","value":"\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\"","index":true},{"key":"index","value":"\"profile/info\"","index":true},{"key":"msg_index","value":"0","index":true}]}]}
    {
      "type": "dysonprotocol.storage.v1.EventStorageUpdated",
      "attributes": [
        {
          "key": "address",
          "value": "\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\"",
          "index": true
        },
        {
          "key": "index",
          "value": "\"profile/info\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }


Let's store some additional entries to demonstrate the prefix-based querying feature:


```python
# Store some example settings
SETTINGS_DATA = shlex.quote(json.dumps({"theme": "dark", "notifications": True}))

out = ! dysond tx storage set \
    --index "settings/app" \
    --data $SETTINGS_DATA \
    --from $ADDRESS \
    -y | dysond q wait-tx -o json 
out = '\n'.join(out)
print(out)
tx_result = json.loads(out)

for event in tx_result['events']:
    if "dysonprotocol" in event['type']:
        print(json.dumps(event, indent=2))
        break
```

    {"height":"77","txhash":"581EC8F7965C6E63C316B709D4F2ED9ACF1DC0DA0392FE6CF3DC1E4BB56DC585","codespace":"","code":0,"data":"12310A2F2F6479736F6E70726F746F636F6C2E73746F726167652E76312E4D736753746F72616765536574526573706F6E7365","raw_log":"","logs":[],"info":"","gas_wanted":"200000","gas_used":"50181","tx":null,"timestamp":"","events":[{"type":"tx","attributes":[{"key":"acc_seq","value":"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el/6","index":true}]},{"type":"tx","attributes":[{"key":"signature","value":"fjnbVnmNg72sKVwp9J5qcR2t7zK/UEe32+hzogwxOnoQfUCfy06CQMVRvi0Jskj/s4cz2MlDQQ23Ii7Zbtt+0Q==","index":true}]},{"type":"message","attributes":[{"key":"action","value":"/dysonprotocol.storage.v1.MsgStorageSet","index":true},{"key":"sender","value":"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el","index":true},{"key":"module","value":"storage","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"dysonprotocol.storage.v1.EventStorageUpdated","attributes":[{"key":"address","value":"\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\"","index":true},{"key":"index","value":"\"settings/app\"","index":true},{"key":"msg_index","value":"0","index":true}]}]}
    {
      "type": "dysonprotocol.storage.v1.EventStorageUpdated",
      "attributes": [
        {
          "key": "address",
          "value": "\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\"",
          "index": true
        },
        {
          "key": "index",
          "value": "\"settings/app\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }



```python
# Store a blog post
POST_DATA = shlex.quote(json.dumps({
    "title": "Introduction to Blockchain",
    "content": "Blockchain is a distributed ledger technology...",
    "tags": ["blockchain", "crypto", "beginner"],
    "published_at": "2023-10-25T15:30:00Z"
}))

out = ! dysond tx storage set \
    --index "content/posts/1" \
    --data $POST_DATA \
    --from $ADDRESS \
    -y | dysond q wait-tx -o json
out = ''.join(out)
tx_result = json.loads(out)

for event in tx_result['events']:
    if "dysonprotocol" in event['type']:
        print(json.dumps(event, indent=2))
        break


```

    {
      "type": "dysonprotocol.storage.v1.EventStorageUpdated",
      "attributes": [
        {
          "key": "address",
          "value": "\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\"",
          "index": true
        },
        {
          "key": "index",
          "value": "\"content/posts/1\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }


### Reading Storage Entries

Let's retrieve the storage entries we've created:


```python
# Query a specific entry
out = ! dysond query storage get $ADDRESS --index "profile/info" -o json 
print(out)
out = ''.join(out)
query_result = json.loads(out)

profile_data = json.loads(query_result['entry']['data'])
print(profile_data)

assert profile_data['name'] == "Bob", "Expected 'Bob' in output, got: " + profile_data['name']
assert profile_data['bio'] == "Blockchain enthusiast", "Expected 'Blockchain enthusiast' in output, got: " + profile_data['bio']
assert profile_data['skills'] == ["Smart Contracts", "DeFi", "Web3"], "Expected ['Smart Contracts', 'DeFi', 'Web3'] in output, got: " + str(profile_data['skills'])
```

    ['{"entry":{"owner":"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el","index":"profile/info","data":"{\\"name\\": \\"Bob\\", \\"bio\\": \\"Blockchain enthusiast\\", \\"skills\\": [\\"Smart Contracts\\", \\"DeFi\\", \\"Web3\\"]}","updated_height":"76","updated_timestamp":"2025-10-02T10:49:55Z","hash":"sha256-1d2LVY9EgE8yTZQ+84JJEwikcA6JNAg8waPXRBvntUo="}}']
    {'name': 'Bob', 'bio': 'Blockchain enthusiast', 'skills': ['Smart Contracts', 'DeFi', 'Web3']}


### Prefix-Based Queries

The Storage module allows you to query entries with a common prefix, which is useful for organizing related data:


```python
# List all entries with the "profile/" prefix
! dysond query storage list $ADDRESS --index-prefix "profile/" -o json 
```

    {"entries":[{"owner":"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el","index":"profile/info","data":"{\"name\": \"Bob\", \"bio\": \"Blockchain enthusiast\", \"skills\": [\"Smart Contracts\", \"DeFi\", \"Web3\"]}","updated_height":"76","updated_timestamp":"2025-10-02T10:49:55Z","hash":"sha256-1d2LVY9EgE8yTZQ+84JJEwikcA6JNAg8waPXRBvntUo="}],"pagination":{"next_key":null,"total":"0"}}



```python
# List all entries with the "content/" prefix
! dysond query storage list $ADDRESS --index-prefix "content/" -o json
```

    {"entries":[{"owner":"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el","index":"content/posts/1","data":"{\"title\": \"Introduction to Blockchain\", \"content\": \"Blockchain is a distributed ledger technology...\", \"tags\": [\"blockchain\", \"crypto\", \"beginner\"], \"published_at\": \"2023-10-25T15:30:00Z\"}","updated_height":"78","updated_timestamp":"2025-10-02T10:49:57Z","hash":"sha256-ZHL5Y1S9UvkhTzc5u78zZ2K0Uvxp6LTpFD2T4OctMjk="}],"pagination":{"next_key":null,"total":"0"}}



```python
# List all entries (empty prefix matches everything)
! dysond query storage list $ADDRESS --index-prefix "" -o json --limit 3 --count-total
```

    {"entries":[{"owner":"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el","index":"content/posts/1","data":"{\"title\": \"Introduction to Blockchain\", \"content\": \"Blockchain is a distributed ledger technology...\", \"tags\": [\"blockchain\", \"crypto\", \"beginner\"], \"published_at\": \"2023-10-25T15:30:00Z\"}","updated_height":"78","updated_timestamp":"2025-10-02T10:49:57Z","hash":"sha256-ZHL5Y1S9UvkhTzc5u78zZ2K0Uvxp6LTpFD2T4OctMjk="},{"owner":"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el","index":"profile/info","data":"{\"name\": \"Bob\", \"bio\": \"Blockchain enthusiast\", \"skills\": [\"Smart Contracts\", \"DeFi\", \"Web3\"]}","updated_height":"76","updated_timestamp":"2025-10-02T10:49:55Z","hash":"sha256-1d2LVY9EgE8yTZQ+84JJEwikcA6JNAg8waPXRBvntUo="},{"owner":"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el","index":"settings/app","data":"{\"theme\": \"dark\", \"notifications\": true}","updated_height":"77","updated_timestamp":"2025-10-02T10:49:56Z","hash":"sha256-W5j+Aa98S2rm66ch2QXtBLYx8yEOG08aRMp9tep/wBU="}],"pagination":{"next_key":null,"total":"3"}}


### Deleting Storage Entries

Now let's delete some of our storage entries:


```python
# Delete a single entry
out = ! dysond tx storage delete \
  --indexes "settings/app" \
  --from $ADDRESS \
  -y |  dysond q wait-tx -o json 
out = ''.join(out)
tx_result = json.loads(out)

for event in tx_result['events']:
    if "dysonprotocol" in event['type']:
        print(json.dumps(event, indent=2))
        break
```

    {
      "type": "dysonprotocol.storage.v1.EventStorageDelete",
      "attributes": [
        {
          "key": "deleted_indexes",
          "value": "[\"settings/app\"]",
          "index": true
        },
        {
          "key": "owner",
          "value": "\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }


The Storage module also supports deleting multiple entries at once:


```python
# Delete multiple entries at once
out = ! dysond tx storage delete \
  --indexes "profile/info,content/posts/1" \
  --from $ADDRESS \
  -y |  dysond q wait-tx -o json 
out = ''.join(out)
tx_result = json.loads(out)

for event in tx_result['events']:
    if "dysonprotocol" in event['type']:
        print(json.dumps(event, indent=2))
        break

```

    {
      "type": "dysonprotocol.storage.v1.EventStorageDelete",
      "attributes": [
        {
          "key": "deleted_indexes",
          "value": "[\"profile/info\",\"content/posts/1\"]",
          "index": true
        },
        {
          "key": "owner",
          "value": "\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }


Let's verify that the entries were deleted:


```python
# List all entries (should be empty now)
! dysond query storage list $ADDRESS --index-prefix "" -o json --limit 3 --count-total
```

    {"entries":[],"pagination":{"next_key":null,"total":"0"}}


## Binary Data Storage Example

While the Storage module primarily works with text data, you can store binary data by encoding it as base64 or hex. Here's a practical example using base64 encoding:


```python
import base64

# Create some binary data (a simple PNG image in this case)
binary_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06\x00\x00\x00\x1f\xf3\xffa'

# Encode as base64
base64_data = base64.b64encode(binary_data).decode('utf-8')
base64_json = shlex.quote(json.dumps({"data": base64_data, "mime_type": "image/png"}))

# Store the base64 encoded data
out = ! dysond tx storage set \
    --index "files/logo.png" \
    --data {base64_json} \
    --from $ADDRESS \
    -y  | dysond q wait-tx -o json 
out = ''.join(out)
tx_result = json.loads(out)

assert tx_result['code'] == 0, f"Error setting storage entry: {tx_result['raw_log']}"

for event in tx_result['events']:
    if "dysonprotocol" in event['type']:
        print(json.dumps(event, indent=2))
        break

```

    {
      "type": "dysonprotocol.storage.v1.EventStorageUpdated",
      "attributes": [
        {
          "key": "address",
          "value": "\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\"",
          "index": true
        },
        {
          "key": "index",
          "value": "\"files/logo.png\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }



```python
# Retrieve and decode the binary data
binary_entry = ! dysond query storage get $ADDRESS --index "files/logo.png" -o json
binary_entry_json = json.loads(''.join(binary_entry))
stored_data = json.loads(binary_entry_json['entry']['data'])
decoded_data = base64.b64decode(stored_data['data'])

print(f"Retrieved binary data of {len(decoded_data)} bytes with MIME type: {stored_data['mime_type']}")
print(f"First 20 bytes: {decoded_data[:20]}")
```

    Retrieved binary data of 33 bytes with MIME type: image/png
    First 20 bytes: b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10'


## Cleanup

Let's clean up by deleting all the entries we've created:


```python
# Get all entries to prepare for cleanup
entries = ! dysond query storage list $ADDRESS --index-prefix "" -o json
entries_json = json.loads(''.join(entries))

# Extract all indexes
indexes = [entry['index'] for entry in entries_json.get('entries', [])]

# Print what we're about to delete
print(f"Found {len(indexes)} entries to delete:")
for index in indexes:
    print(f"- {index}")
```

    Found 1 entries to delete:
    - files/logo.png



```python
# Delete all entries in batches of 5 to avoid command line length limits

for i in range(0, len(indexes), 5):
    index_list = indexes[i:i+5]
    print(f"Deleting [{len(index_list)}] files: {','.join(index_list)}: ", end="")

    out = ! dysond tx storage delete --indexes "{','.join(index_list)}" --from bob -y | dysond q wait-tx -o json 
    out = ''.join(out)
    tx_result = json.loads(out)

    assert tx_result['code'] == 0, f"Error deleting storage entries: {tx_result['raw_log']}"
    print(f"success")
   

```

    Deleting [1] files: files/logo.png: 

    success



```python
# Verify all entries were deleted
final_check = ! dysond query storage list $ADDRESS --index-prefix "" -o json
final_json = json.loads(''.join(final_check))
remaining = final_json.get('entries', [])

assert len(remaining) == 0, "Expected 0 entries remaining, got: " + str(remaining)
print(f"Cleanup complete. {len(remaining)} entries remaining.")
```

    Cleanup complete. 0 entries remaining.


## Summary

The Dyson Protocol Storage module provides a powerful and flexible way to store persistent data on-chain. Key takeaways:

1. **Simple API**: Easy-to-use commands for setting, getting, and deleting key-value pairs
2. **Structured Data**: Support for JSON and hierarchical data organization with prefix-based queries
3. **Efficient Retrieval**: Pagination support for handling large datasets
4. **Versatility**: Can store text, JSON, and even binary data (with encoding)
5. **Access Control**: Owner-based write permissions with public read access

These features make the Storage module ideal for a wide range of applications, from simple key-value stores to complex data structures for dApps.
