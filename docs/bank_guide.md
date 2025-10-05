# Dyson Protocol Bank Module Guide

This notebook provides quick, copy-paste-ready examples for the Bank module:
- Query balances via CLI and via Dyslang (read-only)
- Send coins via CLI and via Dyslang (transaction)

It complements the high-level context in `agents.md` and `README.md`.



## 1. Prerequisites

- You have `dysond` installed and connected to a network (see `README.md`).
- You have at least one local key (e.g., `alice`) with funds.
- Replace account names and addresses as needed.


## 2. Query Balance Examples

### 2.1 Query via CLI
Use the standard bank balance query. Replace `alice` with your key name if different.




```python
import json

# Get alice address
[ALICE] = !dysond keys show -a alice
# Query balance
! dysond query bank balance {ALICE} udys -o json | jq -M

```

    {
      "balance": {
        "denom": "udys",
        "amount": "8999964567"
      }
    }


### 2.2 Query via Dyslang (read-only)
Runs a minimal script inline using `--extra-code` to query the balance from within the sandbox.




```python
import tempfile, shlex

# Get alice address
[ALICE] = !dysond keys show -a alice

extra_code = """
from dys import _query

def query_balance(address, denom="udys"):
    return _query({
        "@type": "/cosmos.bank.v1beta1.QueryBalanceRequest",
        "address": address,
        "denom": denom,
    })
"""
with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
    f.write(extra_code)
    extra_path = f.name

args = shlex.quote(json.dumps([ALICE, "udys"]))
! dysond query script run --script-address {ALICE} --executor-address {ALICE} --function-name query_balance --args {args} --extra-code-path {extra_path} -o json | jq -M

```

    {
      "result": "{\"cumsize\":4777,\"exception\":null,\"gas_limit\":18446744073709551615,\"nodes_called\":25,\"result\":{\"@type\":\"/cosmos.bank.v1beta1.QueryBalanceResponse\",\"balance\":{\"amount\":\"8999964567\",\"denom\":\"udys\"}},\"script_gas_consumed\":1009245,\"stdout\":\"\"}",
      "attached_message_results": []
    }


## 3. Send Coins Examples

### 3.1 Send via CLI
Send 123 udys from `alice` to `bob`.




```python
import json

[ALICE] = !dysond keys show -a alice
[BOB] = !dysond keys show -a bob

! dysond tx bank send alice {BOB} 123udys -y -o json | dysond query wait-tx -o json | jq -M

```

    {
      "height": "254",
      "txhash": "9B8701EDFCBF0A4706D16B6646B0E81C8982C0C0B307F3D8E61994C419CEA21B",
      "codespace": "",
      "code": 0,
      "data": "12260A242F636F736D6F732E62616E6B2E763162657461312E4D736753656E64526573706F6E7365",
      "raw_log": "",
      "logs": [],
      "info": "",
      "gas_wanted": "200000",
      "gas_used": "45812",
      "tx": null,
      "timestamp": "",
      "events": [
        {
          "type": "tx",
          "attributes": [
            {
              "key": "acc_seq",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/61",
              "index": true
            }
          ]
        },
        {
          "type": "tx",
          "attributes": [
            {
              "key": "signature",
              "value": "6G0YS5Prc3m0NqGQQFnzpuazon+aWYVYRPODjhm8T1d9FL32pquJ6/QfE9JuK/dXIqm+rIbVr7e6r4EeBUPpDA==",
              "index": true
            }
          ]
        },
        {
          "type": "message",
          "attributes": [
            {
              "key": "action",
              "value": "/cosmos.bank.v1beta1.MsgSend",
              "index": true
            },
            {
              "key": "sender",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
              "index": true
            },
            {
              "key": "module",
              "value": "bank",
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
          "type": "coin_spent",
          "attributes": [
            {
              "key": "spender",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
              "index": true
            },
            {
              "key": "amount",
              "value": "123udys",
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
          "type": "coin_received",
          "attributes": [
            {
              "key": "receiver",
              "value": "dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el",
              "index": true
            },
            {
              "key": "amount",
              "value": "123udys",
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
          "type": "transfer",
          "attributes": [
            {
              "key": "recipient",
              "value": "dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el",
              "index": true
            },
            {
              "key": "sender",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
              "index": true
            },
            {
              "key": "amount",
              "value": "123udys",
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
          "type": "message",
          "attributes": [
            {
              "key": "sender",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
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


### 3.2 Send via Dyslang (transaction)
Use an inline script executed via `dysond tx script exec` to send funds.




```python
import tempfile, shlex

[ALICE] = !dysond keys show -a alice
[BOB] = !dysond keys show -a bob

extra_code = """
from dys import _msg, get_executor_address

def send_to(recipient, amount, denom="udys"):
    return _msg({
        "@type": "/cosmos.bank.v1beta1.MsgSend",
        "from_address": get_executor_address(),
        "to_address": recipient,
        "amount": [{"denom": denom, "amount": str(amount)}],
    })
"""
with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
    f.write(extra_code)
    extra_path = f.name

args = shlex.quote(json.dumps([BOB, 123, "udys"]))
! dysond tx script exec --from alice --script-address {ALICE} --function-name send_to --args {args} --extra-code-path {extra_path} -y -o json | dysond query wait-tx -o json | jq -M

```

    {
      "height": "255",
      "txhash": "825987D07BEC835810B0D0682E66FB489A6D2FC14A3CC9DC89C2D33447AC5E75",
      "codespace": "sdk",
      "code": 11,
      "data": "",
      "raw_log": "out of gas in location: script exec base cost; gasWanted: 200000, gasUsed: 1034335: out of gas",
      "logs": [],
      "info": "",
      "gas_wanted": "200000",
      "gas_used": "1034335",
      "tx": null,
      "timestamp": "",
      "events": [
        {
          "type": "tx",
          "attributes": [
            {
              "key": "acc_seq",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/62",
              "index": true
            }
          ]
        },
        {
          "type": "tx",
          "attributes": [
            {
              "key": "signature",
              "value": "IsE+SqsmoR/rWWes67B9msufnTlt/nRpGxf1srWw/lUFFDJOcVHbwRZR/CIL0tTeOSbsBovp7TrljyHTu5SJTA==",
              "index": true
            }
          ]
        }
      ]
    }

