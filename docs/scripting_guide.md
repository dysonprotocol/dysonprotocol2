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

    Accessing your DWapp at 'http://dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej.localhost:3317'


    * Host dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej.localhost:3317 was resolved.
    * IPv6: ::1
    * IPv4: 127.0.0.1
    *   Trying [::1]:3317...
    * connect to ::1 port 3317 from ::1 port 58809 failed: Connection refused
    *   Trying 127.0.0.1:3317...
    * Connected to dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej.localhost (127.0.0.1) port 3317
    > GET /hi HTTP/1.1
    > Host: dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej.localhost:3317
    > User-Agent: curl/8.7.1
    > Accept: */*
    > 
    * Request completely sent off
    < HTTP/1.1 200 OK
    < Content-Length: 82
    < Content-Type: text/html
    < Date: Sat, 24 Jan 2026 01:00:10 GMT
    < Server: WSGIServer/0.2 CPython/3.12.11
    < X-Server-Time: 1769216410
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

    {"script":{"address":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej","version":"1","code":"def add(a, b):\n    print(f\"Adding {a} and {b}\")\n    return {\"a\": a, \"b\": b, \"add_result\": a + b}\n\n\ndef wsgi(environ, start_response):\n    status = \"200 OK\"\n    headers = [(\"Content-type\", \"text/html\")]\n    start_response(status, headers)\n    return [\n        b\"\"\"\n\u003chtml\u003e\n    \u003cbody\u003e\n        \u003ch1\u003eHello from Dyson Protocol!\u003c/h1\u003e\n    \u003c/body\u003e\n\u003c/html\u003e\"\"\"\n    ]\n\n","update_height":"149"}}
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
      "raw_log": "out of gas in location: script exec base cost; gasWanted: 200000, gasUsed: 1030645: out of gas",
      "events": [
        {
          "type": "tx",
          "attributes": [
            {
              "key": "acc_seq",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/18",
              "index": true
            }
          ]
        },
        {
          "type": "tx",
          "attributes": [
            {
              "key": "signature",
              "value": "Yl7amCBd4HY2xnX/ov8sduRXg47fIanb9sL3tJispYF7MxOmEbj5G2hcH50HtQMDRitsUXleQG5RW6x3T3uN5g==",
              "index": true
            }
          ]
        }
      ]
    }


## Authz Exec With Attached Messages

ScriptExecAuthorization can now include attached message authorizations. This lets a grantee execute a script on behalf of the granter and attach allowed messages (like `MsgSend`) that execute under the granter's authority. The attached message signer must be the granter, and each attached message type must be authorized by an embedded authz grant.



```python
import json
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone

[bob_address] = ! dysond keys show bob -a
bob_address = bob_address.strip()


def parse_json_output(raw):
    raw = raw.strip()
    assert raw, f"empty command output: {raw}"
    first = raw.find("{")
    last = raw.rfind("}")
    assert first != -1 and last != -1, f"no json object in output: {raw}"
    return json.loads(raw[first : last + 1])


def run_cmd(args):
    result = subprocess.run(args, capture_output=True, text=True)
    output = result.stdout + "\n" + result.stderr
    assert result.returncode == 0, f"command failed: {args}\n{output}"
    return output


def wait_tx(tx_output):
    tx = parse_json_output(tx_output)
    assert tx.get("code", 1) == 0, f"tx failed: {tx}"
    txhash = tx.get("txhash")
    assert txhash, f"txhash missing: {tx}"
    wait_output = run_cmd(["dysond", "query", "wait-tx", txhash, "-o", "json"])
    return parse_json_output(wait_output)


expiration = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

msg_grant = {
    "@type": "/cosmos.authz.v1beta1.MsgGrant",
    "granter": address,
    "grantee": bob_address,
    "grant": {
        "authorization": {
            "@type": "/dysonprotocol.script.v1.ScriptExecAuthorization",
            "script_address": address,
            "function_names": ["add"],
            "attached_msg_authorizations": [
                {
                    "@type": "/cosmos.bank.v1beta1.SendAuthorization",
                    "spend_limit": [{"denom": "udys", "amount": "25"}],
                }
            ],
        },
        "expiration": expiration,
    },
}

print("MsgGrant payload:")
print(json.dumps(msg_grant, indent=2))

grant_output = run_cmd(
    [
        "dysond",
        "tx",
        "script",
        "exec",
        "--script-address",
        address,
        "--function-name",
        "add",
        "--args",
        "[0, 0]",
        "--kwargs",
        "{}",
        "--attached-message",
        json.dumps(msg_grant),
        "--from",
        "alice",
        "--gas",
        "2000000",
        "-y",
        "-o",
        "json",
    ]
)

grant_res = wait_tx(grant_output)
assert grant_res.get("code", 1) == 0, f"authz grant failed: {grant_res}"

balances_before = run_cmd(["dysond", "query", "bank", "balances", bob_address, "-o", "json"])
balances_before = parse_json_output(balances_before)
print("Balances before:")
print(json.dumps(balances_before, indent=2))
coins_before = balances_before.get("balances", [])
udys_before = [c for c in coins_before if c.get("denom") == "udys"]
assert udys_before, f"udys balance missing: {balances_before}"
before_amount = int(udys_before[0]["amount"])

msg_exec = {
    "@type": "/dysonprotocol.script.v1.MsgExec",
    "executor_address": address,
    "script_address": address,
    "function_name": "add",
    "args": "[2, 3]",
    "kwargs": "{}",
    "attached_messages": [
        {
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": address,
            "to_address": bob_address,
            "amount": [{"denom": "udys", "amount": "5"}],
        }
    ],
}

tx_body = {"body": {"messages": [msg_exec]}}

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as tx_file:
    json.dump(tx_body, tx_file)
    tx_file.flush()
    exec_output = run_cmd(
        [
            "dysond",
            "tx",
            "authz",
            "exec",
            tx_file.name,
            "--from",
            "bob",
            "--gas",
            "2000000",
            "-y",
            "-o",
            "json",
        ]
    )

exec_res = wait_tx(exec_output)
assert exec_res.get("code", 1) == 0, f"authz exec failed: {exec_res}"

balances_after = run_cmd(["dysond", "query", "bank", "balances", bob_address, "-o", "json"])
balances_after = parse_json_output(balances_after)
print("Balances after:")
print(json.dumps(balances_after, indent=2))
coins_after = balances_after.get("balances", [])
udys_after = [c for c in coins_after if c.get("denom") == "udys"]
assert udys_after, f"udys balance missing: {balances_after}"
after_amount = int(udys_after[0]["amount"])
assert after_amount == before_amount + 5, f"balance mismatch: {before_amount} -> {after_amount}"

grant_state = run_cmd(["dysond", "query", "authz", "grants", address, bob_address, "-o", "json"])
grant_state = parse_json_output(grant_state)
print("MsgGrant state after exec:")
print(json.dumps(grant_state, indent=2))
exec_grants = []
for grant in grant_state.get("grants", []):
    auth = grant.get("authorization", {})
    auth_type = auth.get("@type") or auth.get("type")
    if auth_type == "/dysonprotocol.script.v1.ScriptExecAuthorization":
        exec_grants.append(grant)

assert exec_grants, f"ScriptExecAuthorization missing: {grant_state}"
exec_auth = exec_grants[0].get("authorization", {})
exec_value = exec_auth.get("value", exec_auth)
attached_auths = exec_value.get("attached_msg_authorizations", [])
assert isinstance(attached_auths, list), f"attached_msg_authorizations missing: {exec_value}"

send_auths = []
for auth in attached_auths:
    auth_type = auth.get("@type") or auth.get("type")
    if auth_type == "/cosmos.bank.v1beta1.SendAuthorization":
        send_auths.append(auth)

assert send_auths, f"SendAuthorization missing: {attached_auths}"
send_value = send_auths[0].get("value", send_auths[0])
spend_limit = send_value.get("spend_limit", [])
assert spend_limit, f"spend_limit missing: {send_value}"
udys_limit = [c for c in spend_limit if c.get("denom") == "udys"]
assert udys_limit, f"udys spend_limit missing: {spend_limit}"
print(f"Updated spend_limit: {udys_limit[0]}")
assert udys_limit[0].get("amount") == "20", f"spend_limit not updated: {udys_limit[0]}"

```

    MsgGrant payload:
    {
      "@type": "/cosmos.authz.v1beta1.MsgGrant",
      "granter": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
      "grantee": "dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el",
      "grant": {
        "authorization": {
          "@type": "/dysonprotocol.script.v1.ScriptExecAuthorization",
          "script_address": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
          "function_names": [
            "add"
          ],
          "attached_msg_authorizations": [
            {
              "@type": "/cosmos.bank.v1beta1.SendAuthorization",
              "spend_limit": [
                {
                  "denom": "udys",
                  "amount": "25"
                }
              ]
            }
          ]
        },
        "expiration": "2026-01-24T02:00:12Z"
      }
    }


    Balances before:
    {
      "balances": [
        {
          "denom": "bar-kktzty.dys",
          "amount": "100551"
        },
        {
          "denom": "foo-pfxgdk.dys",
          "amount": "100046"
        },
        {
          "denom": "udys",
          "amount": "10000000001"
        }
      ],
      "pagination": {
        "total": "3"
      }
    }


    Balances after:
    {
      "balances": [
        {
          "denom": "bar-kktzty.dys",
          "amount": "100551"
        },
        {
          "denom": "foo-pfxgdk.dys",
          "amount": "100046"
        },
        {
          "denom": "udys",
          "amount": "10000000006"
        }
      ],
      "pagination": {
        "total": "3"
      }
    }
    MsgGrant state after exec:
    {
      "grants": [
        {
          "authorization": {
            "type": "/dysonprotocol.script.v1.ScriptExecAuthorization",
            "value": {
              "script_address": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
              "function_names": [
                "add"
              ],
              "attached_msg_authorizations": [
                {
                  "type": "/cosmos.bank.v1beta1.SendAuthorization",
                  "value": {
                    "spend_limit": [
                      {
                        "denom": "udys",
                        "amount": "20"
                      }
                    ]
                  }
                }
              ]
            }
          },
          "expiration": "2026-01-24T02:00:12Z"
        }
      ],
      "pagination": {
        "total": "1"
      }
    }
    Updated spend_limit: {'denom': 'udys', 'amount': '20'}


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

    Name: alice-uuq3a.dys
    Salt: 0saasred0j
    Hex Hash: 568dfce65cb2d403d620077859f9ee08a53b75161572ff60984c42f2dfc7cde8



```python
valuation = "100udys"
commit_output = run_cmd(
    [
        "dysond",
        "tx",
        "nameservice",
        "commit",
        "--commitment",
        hex_hash,
        "--valuation",
        valuation,
        "--from",
        "alice",
        "--gas",
        "2000000",
        "-y",
        "-o",
        "json",
    ]
)

commit_res = wait_tx(commit_output)
assert commit_res.get("code", 1) == 0, f"nameservice commit failed: {commit_res}"

```

## Reveal Name Registration
Reveal the name to complete registration.


```python
reveal_output = run_cmd(
    [
        "dysond",
        "tx",
        "nameservice",
        "reveal",
        "--name",
        name,
        "--salt",
        salt,
        "--from",
        "alice",
        "--gas",
        "2000000",
        "-y",
        "-o",
        "json",
    ]
)

reveal_res = wait_tx(reveal_output)
assert reveal_res.get("code", 1) == 0, f"nameservice reveal failed: {reveal_res}"

```

## Set Destination for Name
Set the destination of the registered name to Alice's address.


```python
set_output = run_cmd(
    [
        "dysond",
        "tx",
        "nameservice",
        "set-destination",
        "--name",
        name,
        "--destination",
        address,
        "--from",
        "alice",
        "--gas",
        "2000000",
        "-y",
        "-o",
        "json",
    ]
)

set_res = wait_tx(set_output)
assert set_res.get("code", 1) == 0, f"nameservice set-destination failed: {set_res}"

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

    Accessing your DWapp at 'http://alice-uuq3a.localhost:3317'


    * Host alice-uuq3a.localhost:3317 was resolved.
    * IPv6: ::1
    * IPv4: 127.0.0.1
    *   Trying [::1]:3317...
    * connect to ::1 port 3317 from ::1 port 63144 failed: Connection refused
    *   Trying 127.0.0.1:3317...
    * Connected to alice-uuq3a.localhost (127.0.0.1) port 3317
    > GET /hi HTTP/1.1
    > Host: alice-uuq3a.localhost:3317
    > User-Agent: curl/8.7.1
    > Accept: */*
    > 
    * Request completely sent off
    < HTTP/1.1 200 OK
    < Content-Length: 82
    < Content-Type: text/html
    < Date: Sat, 24 Jan 2026 01:00:14 GMT
    < Server: WSGIServer/0.2 CPython/3.12.11
    < X-Server-Time: 1769216415
    < 
    { [82 bytes data]
    * Connection #0 to host alice-uuq3a.localhost left intact
    
    <html>
        <body>
            <h1>Hello from Dyson Protocol!</h1>
        </body>
    </html>

