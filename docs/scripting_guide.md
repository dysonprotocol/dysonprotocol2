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

    Accessing your DWapp at 'http://dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej.localhost:2317'


    * Host dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej.localhost:2317 was resolved.
    * IPv6: ::1
    * IPv4: 127.0.0.1
    *   Trying [::1]:2317...
    * connect to ::1 port 2317 from ::1 port 57291 failed: Connection refused
    *   Trying 127.0.0.1:2317...
    * Connected to dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej.localhost (127.0.0.1) port 2317
    > GET /hi HTTP/1.1
    > Host: dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej.localhost:2317
    > User-Agent: curl/8.7.1
    > Accept: */*
    > 
    * Request completely sent off
    < HTTP/1.1 200 OK
    < Content-Length: 82
    < Content-Type: text/html
    < Date: Wed, 22 Oct 2025 10:36:22 GMT
    < Server: WSGIServer/0.2 CPython/3.12.11
    < X-Server-Time: 1761129383
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

    {"script":{"address":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej","version":"1","code":"def add(a, b):\n    print(f\"Adding {a} and {b}\")\n    return {\"a\": a, \"b\": b, \"add_result\": a + b}\n\n\ndef wsgi(environ, start_response):\n    status = \"200 OK\"\n    headers = [(\"Content-type\", \"text/html\")]\n    start_response(status, headers)\n    return [\n        b\"\"\"\n\u003chtml\u003e\n    \u003cbody\u003e\n        \u003ch1\u003eHello from Dyson Protocol!\u003c/h1\u003e\n    \u003c/body\u003e\n\u003c/html\u003e\"\"\"\n    ]\n","update_height":"247"}}
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
      "raw_log": "out of gas in location: script exec base cost; gasWanted: 200000, gasUsed: 1030642: out of gas",
      "events": [
        {
          "type": "tx",
          "attributes": [
            {
              "key": "acc_seq",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/52",
              "index": true
            }
          ]
        },
        {
          "type": "tx",
          "attributes": [
            {
              "key": "signature",
              "value": "r9dAlLvbPzjRziUQBKy+cCKlz4hUgdzVjJLGy8ELupEaCcSGQAkLoDC6/Yz3OfDn4is/KkudbfQEP5ed2T68ZA==",
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

    Name: alice-y59xx.dys
    Salt: 4fx69gnm5z
    Hex Hash: 8cfb1affaabf28ed1017694bd47534228319869697f97e5cff778646bed4e0a0



```python
valuation = '100udys'
res = ! dysond tx nameservice commit --commitment "$hex_hash" --valuation "$valuation" --from alice -y | dysond query wait-tx -o json
res = json.loads('\n'.join(res))
assert res.get("code", 1) == 0, f"script update failed: {res}"
```

## Reveal Name Registration
Reveal the name to complete registration.


```python
res = ! dysond tx nameservice reveal \
    --name "$name" \
    --salt "$salt" \
    --from alice \
    -y | dysond query wait-tx -o json

res = json.loads('\n'.join(res))
assert res.get("code", 1) == 0, f"script update failed: {res}"
```

## Set Destination for Name
Set the destination of the registered name to Alice's address.


```python
res = ! dysond tx nameservice set-destination \
    --name "$name" \
    --destination "$address" \
    --from alice \
    -y | dysond query wait-tx -o json

res = json.loads('\n'.join(res))
assert res.get("code", 1) == 0, f"script update failed: {res}"

```

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

    Accessing your DWapp at 'http://alice-y59xx.localhost:2317'


    * Host alice-y59xx.localhost:2317 was resolved.
    * IPv6: ::1
    * IPv4: 127.0.0.1
    *   Trying [::1]:2317...
    * connect to ::1 port 2317 from ::1 port 59996 failed: Connection refused
    *   Trying 127.0.0.1:2317...
    * Connected to alice-y59xx.localhost (127.0.0.1) port 2317
    > GET /hi HTTP/1.1
    > Host: alice-y59xx.localhost:2317
    > User-Agent: curl/8.7.1
    > Accept: */*
    > 
    * Request completely sent off
    < HTTP/1.1 200 OK
    < Content-Length: 82
    < Content-Type: text/html
    < Date: Wed, 22 Oct 2025 10:36:25 GMT
    < Server: WSGIServer/0.2 CPython/3.12.11
    < X-Server-Time: 1761129386
    < 
    { [82 bytes data]
    * Connection #0 to host alice-y59xx.localhost left intact
    
    <html>
        <body>
            <h1>Hello from Dyson Protocol!</h1>
        </body>
    </html>

