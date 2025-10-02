# Dyson Protocol Scripting Guide

This guide provides an end-to-end demonstration of the Dyson Protocol Script Module for developers. It covers script management, execution, data handling, and web access through name resolution in the least number of steps.

## Fetch Your Address

First, we'll retrieve the address associated with the 'alice' account. This address will serve as our identity throughout this guide and will be referenced in subsequent commands.



```python
[address] = ! dysond keys show alice -a
print(address)
```

    dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej


## Update Script on Chain
Now, let's deploy our script to the blockchain. We'll create a simple Python script with two functions:
1. An `add` function that performs basic arithmetic
2. A WSGI application that serves a welcome HTML page when accessed via web

This demonstrates how Dyson Protocol enables both computational functions and web hosting capabilities.



```python
import os

code = """
def add(a, b):
    print(f"Adding {a} and {b}")
    return {"a": a, "b": b, "add_result": a + b}

def wsgi(environ, start_response):
    status = '200 OK'
    headers = [('Content-type', 'text/html')]
    start_response(status, headers)
    return [b'''
<html>
    <body>
        <h1>Hello from Dyson Protocol!</h1>
    </body>
</html>''']
"""
import tempfile
import json

with tempfile.NamedTemporaryFile(suffix='.py', delete=True) as tmp:
    tmp.write(code.encode())
    tmp.flush()
    path = tmp.name
    
    tx = ! dysond tx script update --code-path $path \
        --from alice \
        --gas 2000000 \
        -y | dysond query wait-tx -o json
    
res = json.loads('\n'.join(tx))
assert res.get("code", 1) == 0, f"script update failed: {res}"

```

## Access Script via Web Interface
Dyson Protocol allows scripts to be accessed as web applications through the WSGI interface. Let's access our script directly using its address. This demonstrates how Dyson Protocol enables decentralized web hosting without traditional servers.

We'll use the script address to construct a URL that points to our deployed application. The format is:
`http://<script_address>.host.tld`

For local development, we'll use localhost:8000 as our domain suffix.


```python
[output] = ! dysond config get app api.address
port = output.split(":")[-1].strip("\"")

dwapp_url = f"http://{address}.localhost:{port}"

print(f"Accessing your DWapp at '{dwapp_url}'")
output = ! curl -s "$dwapp_url/hi" -v
output = "\n".join(output).strip()
print(output)
assert "Hello from Dyson Protocol!" in output, "Expected 'Hello from Dyson Protocol!' in output, got: " + output
```

    Accessing your DWapp at 'http://dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej.localhost:4317'


    * Host dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej.localhost:4317 was resolved.
    * IPv6: ::1
    * IPv4: 127.0.0.1
    *   Trying [::1]:4317...
    * connect to ::1 port 4317 from ::1 port 65276 failed: Connection refused
    *   Trying 127.0.0.1:4317...
    * Connected to dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej.localhost (127.0.0.1) port 4317
    > GET /hi HTTP/1.1
    > Host: dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej.localhost:4317
    > User-Agent: curl/8.7.1
    > Accept: */*
    > 
    * Request completely sent off
    < HTTP/1.1 200 OK
    < Content-Length: 82
    < Content-Type: text/html
    < Date: Thu, 02 Oct 2025 09:57:31 GMT
    < Server: WSGIServer/0.2 CPython/3.12.11
    < X-Server-Time: 1759399053
    < 
    { [82 bytes data]
    * Connection #0 to host dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej.localhost left intact
    
    <html>
        <body>
            <h1>Hello from Dyson Protocol!</h1>
        </body>
    </html>


## Query Script Information
Let's examine the script we just deployed to the blockchain. This query retrieves the script's metadata and code content, allowing us to verify our update was successful.



```python
import json

output = ! dysond query script script-info --address "$address" -o json 

print("\n".join(output))
script_info = json.loads('\n'.join(output))
print(f"✓ Script query successful for address: {address}")

```

    {"script":{"address":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej","version":"1","code":"def add(a, b):\n    print(f\"Adding {a} and {b}\")\n    return {\"a\": a, \"b\": b, \"add_result\": a + b}\n\n\ndef wsgi(environ, start_response):\n    status = \"200 OK\"\n    headers = [(\"Content-type\", \"text/html\")]\n    start_response(status, headers)\n    return [\n        b\"\"\"\n\u003chtml\u003e\n    \u003cbody\u003e\n        \u003ch1\u003eHello from Dyson Protocol!\u003c/h1\u003e\n    \u003c/body\u003e\n\u003c/html\u003e\"\"\"\n    ]\n","update_height":"71"}}
    ✓ Script query successful for address: dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej


## Execute Script
## Execute Script Function
Now we'll invoke the `add` function we deployed in our script. This demonstrates how Dyson Protocol enables 
decentralized computation by executing functions directly on the blockchain. We'll pass the arguments `5` and `7`, 
and observe how the function processes these values and returns the calculated sum of `12` along with additional metadata.


```python
! dysond tx script exec \
    --script-address "$address" \
    --function-name add \
    --args '[5, 7]' \
    --from alice \
    -y \
    -o json  | dysond query wait-tx -o json | python ../scripts/parse_exec_script_tx.py
```

    {
      "code": 11,
      "script_result": null,
      "raw_log": "out of gas in location: script exec base cost; gasWanted: 200000, gasUsed: 1032639: out of gas",
      "events": [
        {
          "type": "tx",
          "attributes": [
            {
              "key": "acc_seq",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/17",
              "index": true
            }
          ]
        },
        {
          "type": "tx",
          "attributes": [
            {
              "key": "signature",
              "value": "S1fWa0oIY1w+UbxcKsory0Eo3LNUJ9nTZ+FtCkpNHoZmJ+XowbHtDS7oH7l77aZZTkZ1HDdqn8Hu0TeKT21eGw==",
              "index": true
            }
          ]
        }
      ]
    }


# Encoding JSON for Blockchain Operations
Your project may require converting complex JSON structures into a compact binary format for efficient on-chain storage and transmission. The following example demonstrates how to encode a standard transaction message into its binary representation.


```python
! dysond query script encode-json --json '{\
  "@type": "/cosmos.bank.v1beta1.MsgSend", \
  "from_address": "dys1example1", \
  "to_address": "dys1example2", \
  "amount": [ { "denom": "dys", "amount": "100" } ] \
}' -o json
```

    {
      "bytes": "CgxkeXMxZXhhbXBsZTESDGR5czFleGFtcGxlMhoKCgNkeXMSAzEwMA=="
    }


## Decode Bytes
Decoding Binary Data
In this step, we'll convert the previously encoded binary data back into its original JSON format. This bidirectional conversion capability is essential for working with blockchain data that needs to be both efficiently stored on-chain and human-readable when retrieved.


```python
! dysond query script decode-bytes --bytes "CgxkeXMxZXhhbXBsZTESDGR5czFleGFtcGxlMhoKCgNkeXMSAzEwMA=="  --type-url "/cosmos.bank.v1beta1.MsgSend" -o json
```

    {
      "json": "{\"@type\":\"/cosmos.bank.v1beta1.MsgSend\",\"from_address\":\"dys1example1\",\"to_address\":\"dys1example2\",\"amount\":[{\"denom\":\"dys\",\"amount\":\"100\"}]}"
    }


## Commit Name Registration
More details on name registration can be found in the Name Service section of the documentation.
Commit to registering a name using a computed hash. First, compute the hash.


```python
import random
import string

def random_string(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

name = f"alice-{random_string(5)}.dys"
salt = random_string(10)

output = ! dysond query nameservice compute-hash \
    --name "$name" \
    --salt "$salt" \
    --committer "$address" \
    -o json

import json
hex_hash = json.loads('\n'.join(output)).get('hex_hash', '')

print(f"Name: {name}")
print(f"Salt: {salt}")
print(f"Hex Hash: {hex_hash}")
```

    Name: alice-t7x2f.dys
    Salt: 9fvf049y0h
    Hex Hash: 901051f4d7bda2b0e9e6530a571987bff0c2e5ba13192737e7a4393b2dc47934



```python
valuation = '100udys'
! dysond tx nameservice commit --commitment "$hex_hash" --valuation "$valuation" --from alice -y | dysond query wait-tx -o json
```

    {"height":"74","txhash":"35B5919AA8167EC7394CA9BC9DA7EEE96FFA406A7079F7A0C2E5394E7790442A","codespace":"","code":0,"data":"12310A2F2F6479736F6E70726F746F636F6C2E6E616D65736572766963652E76312E4D7367436F6D6D6974526573706F6E7365","raw_log":"","logs":[],"info":"","gas_wanted":"200000","gas_used":"42340","tx":null,"timestamp":"","events":[{"type":"tx","attributes":[{"key":"acc_seq","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/18","index":true}]},{"type":"tx","attributes":[{"key":"signature","value":"wGc+V9EfRCBeYim9Wes9opLeB+V85otk0tLMVTNNCDtWOZKwp06xUSEAESTj0dhon7IPRaeeE41FDnILimGN6A==","index":true}]},{"type":"message","attributes":[{"key":"action","value":"/dysonprotocol.nameservice.v1.MsgCommit","index":true},{"key":"sender","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej","index":true},{"key":"module","value":"nameservice","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"dysonprotocol.nameservice.v1.EventCommitmentCreated","attributes":[{"key":"hexhash","value":"\"901051f4d7bda2b0e9e6530a571987bff0c2e5ba13192737e7a4393b2dc47934\"","index":true},{"key":"msg_index","value":"0","index":true}]}]}


## Reveal Name Registration
Reveal the name to complete registration.


```python
! dysond tx nameservice reveal \
    --name "$name" \
    --salt "$salt" \
    --from alice \
    -y | dysond query wait-tx -o json
```

    {"height":"75","txhash":"9ACCC59490F175BA1114C4D3CF16BDCB542BBB53BA3A63BEFD86976455772577","codespace":"","code":0,"data":"12310A2F2F6479736F6E70726F746F636F6C2E6E616D65736572766963652E76312E4D736752657665616C526573706F6E7365","raw_log":"","logs":[],"info":"","gas_wanted":"200000","gas_used":"86783","tx":null,"timestamp":"","events":[{"type":"tx","attributes":[{"key":"acc_seq","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/19","index":true}]},{"type":"tx","attributes":[{"key":"signature","value":"KMuAAmRSxUpo929Sk+6kUhDiulZ4CDf5z6uxHuRZSY1ugUjrw1ju7cu+oi7XIPTYKgGgHdST6CQiryeE/tPOWA==","index":true}]},{"type":"message","attributes":[{"key":"action","value":"/dysonprotocol.nameservice.v1.MsgReveal","index":true},{"key":"sender","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej","index":true},{"key":"module","value":"nameservice","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"coin_spent","attributes":[{"key":"spender","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej","index":true},{"key":"amount","value":"1udys","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"coin_received","attributes":[{"key":"receiver","value":"dys21jv65s3grqf6v6jl3dp4t6c9t9rk99cd8d0l2ev","index":true},{"key":"amount","value":"1udys","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"transfer","attributes":[{"key":"recipient","value":"dys21jv65s3grqf6v6jl3dp4t6c9t9rk99cd8d0l2ev","index":true},{"key":"sender","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej","index":true},{"key":"amount","value":"1udys","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"message","attributes":[{"key":"sender","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"dysonprotocol.nft.v1beta1.EventMint","attributes":[{"key":"class_id","value":"\"nameservice.dys\"","index":true},{"key":"id","value":"\"alice-t7x2f.dys\"","index":true},{"key":"owner","value":"\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"dysonprotocol.nameservice.v1.EventNameRegistered","attributes":[{"key":"fee","value":"[{\"denom\":\"udys\",\"amount\":\"1\"}]","index":true},{"key":"name","value":"\"alice-t7x2f.dys\"","index":true},{"key":"msg_index","value":"0","index":true}]}]}


## Set Destination for Name
Set the destination of the registered name to Alice's address.


```python
! dysond tx nameservice set-destination \
    --name "$name" \
    --destination "$address" \
    --from alice \
    -y | dysond query wait-tx -o json

```

    {"height":"76","txhash":"7AD0356C7480E2F0766D85CF4AE515B6C9CF6642680C952028945E4D581D54AF","codespace":"","code":0,"data":"12390A372F6479736F6E70726F746F636F6C2E6E616D65736572766963652E76312E4D736753657444657374696E6174696F6E526573706F6E7365","raw_log":"","logs":[],"info":"","gas_wanted":"200000","gas_used":"48614","tx":null,"timestamp":"","events":[{"type":"tx","attributes":[{"key":"acc_seq","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/20","index":true}]},{"type":"tx","attributes":[{"key":"signature","value":"ErpMtcl4IWZrrLtliPGsItIXlRj83fpZhB96n7ao5Fg+IGP4RwQuKFwkLUKKFHym2AsnccpkluITsZIhHWR5UA==","index":true}]},{"type":"message","attributes":[{"key":"action","value":"/dysonprotocol.nameservice.v1.MsgSetDestination","index":true},{"key":"sender","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej","index":true},{"key":"module","value":"nameservice","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"dysonprotocol.nameservice.v1.EventNameDestinationSet","attributes":[{"key":"destination","value":"\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"","index":true},{"key":"name","value":"\"alice-t7x2f.dys\"","index":true},{"key":"msg_index","value":"0","index":true}]}]}


## Access Script via Name
Access the script via the registered name to demonstrate decentralized web hosting.


```python
[output] = ! dysond config get app api.address
port = output.split(":")[-1].strip("\"")

dwapp_url = f"http://{name.strip(".dys")}.localhost:{port}"

print(f"Accessing your DWapp at '{dwapp_url}'")
output = ! curl -s "$dwapp_url/hi" -v
output = "\n".join(output).strip()
print(output)
assert "Hello from Dyson Protocol!" in output, "Expected 'Hello from Dyson Protocol!' in output, got: " + output
```

    Accessing your DWapp at 'http://alice-t7x2f.localhost:4317'


    * Host alice-t7x2f.localhost:4317 was resolved.
    * IPv6: ::1
    * IPv4: 127.0.0.1
    *   Trying [::1]:4317...
    * connect to ::1 port 4317 from ::1 port 52552 failed: Connection refused
    *   Trying 127.0.0.1:4317...
    * Connected to alice-t7x2f.localhost (127.0.0.1) port 4317
    > GET /hi HTTP/1.1
    > Host: alice-t7x2f.localhost:4317
    > User-Agent: curl/8.7.1
    > Accept: */*
    > 
    * Request completely sent off
    < HTTP/1.1 200 OK
    < Content-Length: 82
    < Content-Type: text/html
    < Date: Thu, 02 Oct 2025 09:57:37 GMT
    < Server: WSGIServer/0.2 CPython/3.12.11
    < X-Server-Time: 1759399058
    < 
    { [82 bytes data]
    * Connection #0 to host alice-t7x2f.localhost left intact
    
    <html>
        <body>
            <h1>Hello from Dyson Protocol!</h1>
        </body>
    </html>

