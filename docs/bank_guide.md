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
[ALICE] = get_ipython().getoutput("dysond keys show -a alice")
# Query balance
! dysond query bank balance {ALICE} udys -o json | jq -M

```

    {
      "balance": {
        "denom": "udys",
        "amount": "9999999999"
      }
    }


### 2.2 Query via Dyslang (read-only)
Runs a minimal script inline using `--extra-code` to query the balance from within the sandbox.




```python
import tempfile, shlex

# Get alice address
[ALICE] = get_ipython().getoutput("dysond keys show -a alice")

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
      "result": "{\"cumsize\":4777,\"exception\":null,\"gas_limit\":18446744073709551615,\"nodes_called\":25,\"result\":{\"@type\":\"/cosmos.bank.v1beta1.QueryBalanceResponse\",\"balance\":{\"amount\":\"9999999999\",\"denom\":\"udys\"}},\"script_gas_consumed\":1009242,\"stdout\":\"\"}",
      "attached_message_results": []
    }


## 3. Send Coins Examples

### 3.1 Send via CLI
Send 123 udys from `alice` to `bob`.




```python
import json

[ALICE] = get_ipython().getoutput("dysond keys show -a alice")
[BOB] = get_ipython().getoutput("dysond keys show -a bob")

! dysond tx bank send alice {BOB} 123udys -y -o json | dysond query wait-tx -o json | jq -M

```

    {
      "height": "38",
      "txhash": "F2941BC43431D98A23546D62D0A731F9206E633CD56061BC35E1DFD708E94C6E",
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
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/11",
              "index": true
            }
          ]
        },
        {
          "type": "tx",
          "attributes": [
            {
              "key": "signature",
              "value": "ie33BLHjqRkkT6zDlSp2AK9VG0HnlL+k6S+uuD0dLZcvNiy/l6bGTQEUSMVrC7Rb1Q4LbJRCRbVR2LyszuyPZw==",
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

[ALICE] = get_ipython().getoutput("dysond keys show -a alice")
[BOB] = get_ipython().getoutput("dysond keys show -a bob")

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
      "height": "39",
      "txhash": "4A664CA33594BF6398E53D91EF79046E45E3F3D64681C2BCA0CE8ADFE0F3C761",
      "codespace": "sdk",
      "code": 11,
      "data": "",
      "raw_log": "out of gas in location: script exec base cost; gasWanted: 200000, gasUsed: 1034332: out of gas",
      "logs": [],
      "info": "",
      "gas_wanted": "200000",
      "gas_used": "1034332",
      "tx": null,
      "timestamp": "",
      "events": [
        {
          "type": "tx",
          "attributes": [
            {
              "key": "acc_seq",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/12",
              "index": true
            }
          ]
        },
        {
          "type": "tx",
          "attributes": [
            {
              "key": "signature",
              "value": "QGbe0Uih6MJiT7G3wU+B3PH+q8HaK2kr6+53uvq98iAWh7D8V3JI+3+aGDWtngIzT8gPvh44IEuUxi8CQJOrKA==",
              "index": true
            }
          ]
        }
      ]
    }

