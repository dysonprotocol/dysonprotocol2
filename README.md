# Dyson Protocol – Make Dwapps, Get Paid

**Host Python scripts, serve decentralized websites, and run scheduled tasks with trustless, censorship-resistant execution. Trade names in a dynamic on-chain market, mint custom tokens and NFTs, and store arbitrary data—all fully on-chain.**

---

## What & Why

- **Problem**  
  - Blockchain DApp UIs still load from centralized servers—developers host them off-chain, and end-users can't self-host or audit the code.

- **Solution**  
  - Store HTML/CSS/JS assets in the chain's storage so browsers load UI from the ledger.  
  - Push application logic on-chain and execute periodic jobs (crontasks) without any off-chain trigger.  
  - Run a dynamic on-chain name market using Harberger-style fees.  
  - Mint custom tokens and NFT classes based on on-chain names.  
  - Store arbitrary data in the chain’s storage module.

- **Key Use Cases**  
  - **Autonomous payouts**: schedule hourly dividend distributions without users having to claim.  
  - **Timed auctions**: start and end bids exactly on-chain, with no external cron.  
  - **Game rounds**: progress players automatically through time-boxed stages.  
  - **Price oracles**: post market data at fixed intervals, fully on-chain.  
  - **Nameservice-driven assets**: register and trade domain-backed NFTs in a live marketplace.

- **Outcome**  
  - **A spectrum of security**: from fully trustless script and web UI, to fully centralized, depending on your needs.


## Installation




### 0. Build the dysvm dependencies


```bash
%%bash
make dysvm 
```

### 1. Build the Dyson Protocol binary



```bash
%%bash
make install
```

    Installing dysond binary...
    build_tags: netgo,app_v1
    commit: 132ac87
    cosmos_sdk_version: v0.53.0
    go: go version go1.24.3 darwin/arm64
    name: dyson
    server_name: dysond
    version: develop
    



```bash
%%bash
dysond version --long | tail

```

    - rsc.io/qr@v0.2.0
    - sigs.k8s.io/yaml@v1.6.0
    build_tags: netgo,app_v1
    commit: 132ac87
    cosmos_sdk_version: v0.53.0
    go: go version go1.24.3 darwin/arm64
    name: dyson
    server_name: dysond
    version: develop
    


### 2. Join the testnet

Initialize your node and join the Dyson Protocol testnet:

```bash
dysond init your_node_name                                                                            
dysond join https://dys-testnet2.dysonprotocol.com/rpc
```

### 3. Create new accounts
```bash
dysond keys add alice
dysond keys add bob
```

### 4. Update the On-chain Python Script

This example uploads a Python script that demonstrates storage operations. The full script is available at [examples/storage_example.py](examples/storage_example.py).

**Key Functions in the Script** (excerpt):

```python
def save_message(message):
    # the account that signed the transaction
    caller = get_executor_address()
    _msg({"@type":"/dysonprotocol.storage.v1.MsgStorageSet","owner": get_script_address() ,"index":f"greetings/{caller}","data": json.dumps({"greeting": message})})

def wsgi(environ, start_response):
    # Define response status and headers
    status_code = "200 OK"
    headers = [("Content-Type", "text/html")]
    start_response(status_code, headers)

    # Prepare the query parameters
    query_params = {
        "@type":"/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": get_script_address(),
        "index_prefix":"greetings/"
    }
    
# ... more code in the full example ...
```

Let's see the full script:


```bash
%%bash
cat examples/storage_example.py
```

    import json
    from html import escape
    from dys import get_script_address, get_executor_address, _msg, _query
    
    
    def save_message(message):
        # the account that signed the transaction
        caller = get_executor_address()
        return _msg(
            {
                "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
                "owner": get_script_address(),
                "index": f"greetings/{caller}",
                "data": json.dumps({"greeting": message}),
            }
        )
    
    
    def wsgi(environ, start_response):
        # Define response status and headers
        status_code = "200 OK"
        headers = [("Content-Type", "text/html")]
        start_response(status_code, headers)
    
        # Prepare the query parameters
        query_params = {
            "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
            "owner": get_script_address(),
            "index_prefix": "greetings/",
        }
    
        # Get messages from storage
        storage_result = _query(query_params)
    
        # Start building HTML output
        output = "<html><body>\n"
        output += "<h2>Storage Messages</h2>\n"
    
        # Process each entry from storage
        for entry in storage_result["entries"]:
            # Parse the JSON data
            data = json.loads(entry["data"])
            # Extract the address from the index (format: greetings/{address})
            sender_address = entry["index"].split("/")[1]
            output += f"<p>Message from {escape(sender_address)}: {escape(data['greeting'])}</p>\n"
        else:
            output += "<p>No messages found</p>\n"
    
        # Add the full storage query result for debugging
        output += "<h3>Storage Query Result</h3>\n"
        output += "<pre>" + escape(json.dumps(storage_result, indent=2)) + "</pre>\n"
        output += "<h3>Environment</h3>\n"
        output += (
            "<pre>"
            + escape(json.dumps(environ, indent=2, sort_keys=True, default=str))
            + "</pre>\n"
        )
        output += "</body></html>"
    
        return [output.encode()]


Now let's upload the script to the chain using Alice's address:


```bash
%%bash
ALICE_ADDRESS=$(dysond keys show -a alice)
dysond tx script update --from alice -y -o json --gas 500000 --code "$(cat examples/storage_example.py)" |  dysond q wait-tx -o json | jq '{height, txhash, code, gas_wanted, gas_used, "script_version": .events[] | select(.type=="dysonprotocol.script.v1.EventUpdateScript") | .attributes[] | select(.key=="version") | .value}'

```

    {
      "height": "4805",
      "txhash": "5005A9043FEBC44D68A3F63E82417DE6385F0232ED969E509865EE5CEF4B6197",
      "code": 0,
      "gas_wanted": "500000",
      "gas_used": "118062",
      "script_version": "\"9\""
    }


### 5. Execute the Script Function

Invoke the `save_message` function using Bob's account, passing `"my name is bob"` as an argument:


```bash
%%bash
ALICE_ADDRESS=$(dysond keys show -a alice)
# Save the message to the storage
dysond tx script exec --from alice --script-address $ALICE_ADDRESS --function-name save_message --args '["my name is <b>bob</b>"]' -y  | dysond query wait-tx -o json | ./scripts/parse_exec_script_tx.py | jq 
```

    {
      "code": 0,
      "script_result": {
        "result": {
          "cumsize": 15409,
          "exception": null,
          "gas_limit": 200000,
          "nodes_called": 40,
          "result": {
            "@type": "/dysonprotocol.storage.v1.MsgStorageSetResponse"
          },
          "script_gas_consumed": 37673,
          "stdout": ""
        },
        "attached_message_results": []
      },
      "raw_log": "",
      "events": [
        {
          "type": "tx",
          "attributes": [
            {
              "key": "acc_seq",
              "value": "dys219e7k3qjn4che6r3n7cmew2pkfa8mph49ekwchk/61",
              "index": true
            }
          ]
        },
        {
          "type": "tx",
          "attributes": [
            {
              "key": "signature",
              "value": "VYrj3ptFc7OZVhxtBWyq/1YpzHP9DGMQ7InVAePPC3hkpaVXq6WNMhnRM3ek0AJ18LdhhS+R9k90hv3eA0Qtug==",
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
              "value": "dys219e7k3qjn4che6r3n7cmew2pkfa8mph49ekwchk",
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
          "type": "dysonprotocol.storage.v1.EventStorageUpdated",
          "attributes": [
            {
              "key": "address",
              "value": "\"dys219e7k3qjn4che6r3n7cmew2pkfa8mph49ekwchk\"",
              "index": true
            },
            {
              "key": "index",
              "value": "\"greetings/dys219e7k3qjn4che6r3n7cmew2pkfa8mph49ekwchk\"",
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
              "key": "request",
              "value": "{\"executor_address\":\"dys219e7k3qjn4che6r3n7cmew2pkfa8mph49ekwchk\",\"script_address\":\"dys219e7k3qjn4che6r3n7cmew2pkfa8mph49ekwchk\",\"script_name\":\"\",\"extra_code\":\"\",\"function_name\":\"save_message\",\"args\":\"[\\\"my name is \\u003cb\\u003ebob\\u003c/b\\u003e\\\"]\",\"kwargs\":\"\",\"attached_messages\":[]}",
              "index": true
            },
            {
              "key": "response",
              "value": "{\"result\":\"{\\\"cumsize\\\":15409,\\\"exception\\\":null,\\\"gas_limit\\\":200000,\\\"nodes_called\\\":40,\\\"result\\\":{\\\"@type\\\":\\\"/dysonprotocol.storage.v1.MsgStorageSetResponse\\\"},\\\"script_gas_consumed\\\":37673,\\\"stdout\\\":\\\"\\\"}\",\"attached_message_results\":[]}",
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


### 6. Query the WSGI Endpoint

Finally, confirm the data is stored and accessible via an HTTP request to the script's WSGI endpoint:


```bash
%%bash
ALICE_ADDRESS=$(dysond keys show -a alice)
DWAPP_SERVER_ADDRESS=$(dysond config get app dwapp.address | tr -d '"')
DWAPP_URL="http://$ALICE_ADDRESS.$DWAPP_SERVER_ADDRESS/some-path?query=some-query"
curl -v $DWAPP_URL
```

## Notes & Edge Cases
- Always escape user generated content when rendering it in the browser.
- Ensure that you have a valid account (e.g., `alice`, `bob`) with sufficient balance to pay for gas fees.
- Always verify that you're interacting with the right script address.
- Make sure to provide sufficient gas for script updates (as seen in the example, we used `--gas 500000`).

## Conclusion

This example demonstrates how to:
1. Update on-chain Python code.
2. Execute a function that stores data on the Dyson Protocol.
3. Retrieve data via a WSGI endpoint.

Feel free to adapt the `save_message` function or the WSGI application for more advanced use cases, such as multi-key storage or complex business logic.

## More Documentation

For more detailed information about specific modules, please refer to the following documentation:

### Module Guides

- [Script Module](notebooks/scripting_guide.md): Comprehensive guide to the Script module for on-chain Python execution
- [Storage Module](notebooks/storage_guide.md): Detailed documentation on the Storage module for on-chain data persistence
- [Crontask Module](notebooks/crontask_guide.md): Complete guide to the Crontask module for scheduled transaction execution
- [Nameservice Module](notebooks/nameservice_guide.md): Guide to the Nameservice module for registering names and creating NFTs
- [DysLang Guide](notebooks/dyslang_guide.md): Complete programming reference for the Dyson Language

### Interactive Notebooks

The same guides are also available as interactive Jupyter notebooks in the `notebooks/` directory:

- [Script Module Notebook](notebooks/scripting_guide.ipynb)
- [Storage Module Notebook](notebooks/storage_guide.ipynb)
- [Crontask Module Notebook](notebooks/crontask_guide.ipynb)
- [Nameservice Module Notebook](notebooks/nameservice_guide.ipynb)
- [DysLang Guide Notebook](notebooks/dyslang_guide.ipynb)

### Code Examples

Explore practical examples in the `examples/` directory:

- [Storage Example](examples/storage_example.py): Basic storage operations and WSGI endpoint
- [Crontask Example](examples/crontask_countdown.py): Scheduled task countdown implementation
- [Crontask Script](examples/crontask_script.py): Advanced scheduled transaction execution
- [DysLang Example](examples/dyslang_example.py): Comprehensive language feature demonstration
- [Balance Example](examples/balance_example.py): Account balance querying
- [WSGI Example](examples/simple_wsgi_example.py): Simple web application server
- [AST Explorer](examples/ast_explorer.py): Python Abstract Syntax Tree exploration
- [ICA Example](examples/ica_e2e.py): Inter-Chain Account end-to-end example
- [ICA Module](examples/ica.py): Inter-Chain Account implementation
- [Script Query Height](examples/script_query_height.py): Query blockchain height from scripts

