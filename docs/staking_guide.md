# Dyson Protocol Staking Module Guide

This notebook demonstrates common staking operations in Dyson Protocol and how to perform them via CLI and via on-chain Python (dyslang) scripts.

What you'll learn:
- List validators (CLI and dyslang)
- Delegate to a validator (CLI and via script)
- Query rewards (CLI and dyslang)
- Withdraw-all-rewards re-implemented as a dyslang script
- Harvest-and-restake script (claim rewards and re-delegate the claimed amount)

Notes
- Staking is required to subscribe to Crontask events and may be required to store data in Storage when `storage_stake_multiple` > 0.
- Always verify chain params and gas; use `--gas auto` for large or multi-message transactions.


## 1. Prerequisites

- An initialized Dyson node connected to a network (see `README.md`)
- Funded keys (e.g., `alice`, `bob`)
- The `dysond` CLI on your PATH
- Basic familiarity with notebooks in this repo


## 2. List Validators

We demonstrate both CLI and dyslang-based queries.



```python
! dysond query staking validators -o json | jq -M

```

    {
      "validators": [
        {
          "operator_address": "dys2valoper1tcx55yxmg3a49upmg0nxgs5jc3d3t9udnpxn62",
          "consensus_pubkey": {
            "type": "/cosmos.crypto.ed25519.PubKey",
            "value": "9Igke7OEqMFvujy/M55yDMDKA4GFPV7732aOUcFhYso="
          },
          "status": "BOND_STATUS_BONDED",
          "tokens": "1000000",
          "delegator_shares": "1000000.000000000000000000",
          "description": {
            "moniker": "node-1"
          },
          "unbonding_time": "1970-01-01T00:00:00Z",
          "commission": {
            "commission_rates": {
              "rate": "0.100000000000000000",
              "max_rate": "0.200000000000000000",
              "max_change_rate": "0.010000000000000000"
            },
            "update_time": "2025-11-13T18:43:28.494108Z"
          },
          "min_self_delegation": "1"
        }
      ],
      "pagination": {
        "total": "1"
      }
    }



```python
# Query validators using dyslang extra code
import json, tempfile

# Minimal script that queries validators via _query
code = '''
from dys import _query

def fetch_validators():
    return _query({
        "@type": "/cosmos.staking.v1beta1.QueryValidatorsRequest",
        "status": "BOND_STATUS_BONDED"
    })
'''

with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=True) as f:
    f.write(code)
    f.flush()
    [ALICE] = ! dysond keys show -a alice
    path = f.name
    ! dysond query script run --script-address {ALICE} --executor-address {ALICE} --function-name fetch_validators --extra-code-path {path} -o json | jq -M '.result | fromjson'
```

    {
      "cumsize": 4584,
      "exception": null,
      "gas_limit": 18446744073709551615,
      "nodes_called": 19,
      "result": {
        "@type": "/cosmos.staking.v1beta1.QueryValidatorsResponse",
        "pagination": {
          "next_key": null,
          "total": "1"
        },
        "validators": [
          {
            "commission": {
              "commission_rates": {
                "max_change_rate": "0.010000000000000000",
                "max_rate": "0.200000000000000000",
                "rate": "0.100000000000000000"
              },
              "update_time": "2025-11-13T18:43:28.494108Z"
            },
            "consensus_pubkey": {
              "@type": "/cosmos.crypto.ed25519.PubKey",
              "key": "9Igke7OEqMFvujy/M55yDMDKA4GFPV7732aOUcFhYso="
            },
            "delegator_shares": "1000000.000000000000000000",
            "description": {
              "details": "",
              "identity": "",
              "moniker": "node-1",
              "security_contact": "",
              "website": ""
            },
            "jailed": false,
            "min_self_delegation": "1",
            "operator_address": "dys2valoper1tcx55yxmg3a49upmg0nxgs5jc3d3t9udnpxn62",
            "status": "BOND_STATUS_BONDED",
            "tokens": "1000000",
            "unbonding_height": "0",
            "unbonding_ids": [],
            "unbonding_on_hold_ref_count": "0",
            "unbonding_time": "1970-01-01T00:00:00Z"
          }
        ]
      },
      "script_gas_consumed": 1009639,
      "stdout": ""
    }


## 3. Delegate to a Validator

We’ll delegate using the CLI, then show how to submit a delegation via a dyslang script.



```python
# Delegate to a validator via CLI (executed from Python using bangs)

[VALOPER] = !dysond query staking validators -o json | jq -r '.validators[0].operator_address'
AMOUNT = "1000udys"
print(f"Delegating {AMOUNT} from {ALICE} to {VALOPER}")
! dysond tx staking delegate {VALOPER} {AMOUNT} --from alice -y -o json --gas auto | dysond q wait-tx -o json | jq -M

```

    Delegating 1000udys from dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej to dys2valoper1tcx55yxmg3a49upmg0nxgs5jc3d3t9udnpxn62


    gas estimate: 105783


    {
      "height": "160",
      "txhash": "61A68057C359F74DC35C01A43FA3D73E01675C2F99AF29E1B1042C6B81FF2C62",
      "codespace": "",
      "code": 0,
      "data": "122D0A2B2F636F736D6F732E7374616B696E672E763162657461312E4D736744656C6567617465526573706F6E7365",
      "raw_log": "",
      "logs": [],
      "info": "",
      "gas_wanted": "105783",
      "gas_used": "103835",
      "tx": null,
      "timestamp": "",
      "events": [
        {
          "type": "tx",
          "attributes": [
            {
              "key": "acc_seq",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/8",
              "index": true
            }
          ]
        },
        {
          "type": "tx",
          "attributes": [
            {
              "key": "signature",
              "value": "UHCayliToIHf4Xz6J3W+6Wxw+kZ3zP0hSxs/P+QGHCJq9S95KCkuPyc4LZ9vF79ykeOCYW2q7Vh9HVt1cEFguw==",
              "index": true
            }
          ]
        },
        {
          "type": "message",
          "attributes": [
            {
              "key": "action",
              "value": "/cosmos.staking.v1beta1.MsgDelegate",
              "index": true
            },
            {
              "key": "sender",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
              "index": true
            },
            {
              "key": "module",
              "value": "staking",
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
              "value": "1000udys",
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
              "value": "dys21fl48vsnmsdzcv85q5d2q4z5ajdha8yu3ltjefy",
              "index": true
            },
            {
              "key": "amount",
              "value": "1000udys",
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
          "type": "delegate",
          "attributes": [
            {
              "key": "validator",
              "value": "dys2valoper1tcx55yxmg3a49upmg0nxgs5jc3d3t9udnpxn62",
              "index": true
            },
            {
              "key": "delegator",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
              "index": true
            },
            {
              "key": "amount",
              "value": "1000udys",
              "index": true
            },
            {
              "key": "new_shares",
              "value": "1000.000000000000000000",
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


### Delegate via Script (update + exec)
We’ll upload a tiny script that constructs a `MsgDelegate` and returns its result.



```python
# Write delegate script and execute via CLI with jq output
import json, shlex

code = """
from dys import _msg, get_executor_address

# delegate(amount: str like "1000udys", valoper: str)
def delegate(amount, valoper):
    denom = "udys" if amount.endswith("udys") else "udys"
    amt = amount[:-4] if amount.endswith("udys") else amount
    return _msg({
        "@type": "/cosmos.staking.v1beta1.MsgDelegate",
        "delegator_address": get_executor_address(),
        "validator_address": valoper,
        "amount": {"denom": denom, "amount": str(amt)}
    })
"""

path = "/tmp/delegate_script.py"
with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=True) as f:
    f.write(code)
    f.flush()

    # Upload and execute
    path = f.name
    ! dysond tx script update --from alice --code-path {path} -y -o json --gas auto | dysond q wait-tx -o json

args = shlex.quote(json.dumps(["100udys", VALOPER]))
! dysond tx script exec --from alice --script-address {ALICE} --function-name delegate --args {args} -y -o json --gas auto | dysond q wait-tx -o json  | jq -M '.events[] | select(.type | startswith("dyson")) | .attributes[] | select(.key == "response") | .value  | fromjson | .result | fromjson'

```

    gas estimate: 1057160


    {"height":"162","txhash":"E930626324F68485BA27B8DBE2D6628442234FF2F62E7047AA055F394C35F160","codespace":"","code":0,"data":"12360A302F6479736F6E70726F746F636F6C2E7363726970742E76312E4D7367557064617465536372697074526573706F6E736512020802","raw_log":"","logs":[],"info":"","gas_wanted":"1057160","gas_used":"1055212","tx":null,"timestamp":"","events":[{"type":"tx","attributes":[{"key":"acc_seq","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/9","index":true}]},{"type":"tx","attributes":[{"key":"signature","value":"LACfXcK/JJWS+dCVI3fTjxwLuc8d2K2WGpV0DO+e/XUg2cukNfQtmA7AMrVxRcar953rLt3UIW4An0cumILrQw==","index":true}]},{"type":"message","attributes":[{"key":"action","value":"/dysonprotocol.script.v1.MsgUpdateScript","index":true},{"key":"sender","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej","index":true},{"key":"module","value":"script","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"dysonprotocol.script.v1.EventUpdateScript","attributes":[{"key":"script_address","value":"\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"","index":true},{"key":"version","value":"\"2\"","index":true},{"key":"msg_index","value":"0","index":true}]}]}


    gas estimate: 1161194


    {
      "cumsize": 13086,
      "exception": null,
      "gas_limit": 1161194,
      "nodes_called": 46,
      "result": {
        "@type": "/cosmos.staking.v1beta1.MsgDelegateResponse"
      },
      "script_gas_consumed": 1159279,
      "stdout": ""
    }


## 4. Query Rewards

We’ll query rewards for a delegator using both CLI and dyslang.


```python
! dysond query distribution rewards {ALICE} -o json | jq -M
```

    {
      "rewards": [
        {
          "validator_address": "dys2valoper1tcx55yxmg3a49upmg0nxgs5jc3d3t9udnpxn62",
          "reward": [
            "0.797597243032663700udys"
          ]
        }
      ],
      "total": [
        "0.797597243032663700udys"
      ]
    }



```python
# Dyslang: query rewards via extra code (Python + shlex)
import shlex

code = """
from dys import _query, get_executor_address

# Query all rewards for current executor (delegator)
def my_rewards():
    delegator = get_executor_address()
    return _query({
        "@type": "/cosmos.distribution.v1beta1.QueryDelegationTotalRewardsRequest",
        "delegator_address": delegator
    })
"""
path = "/tmp/query_rewards.py"
with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=True) as f:
    f.write(code)
    f.flush()
    path = f.name
    ! dysond query script run --script-address {ALICE} --executor-address {ALICE} --function-name my_rewards --extra-code-path {path} -o json | jq -M '.result | fromjson'
```

    {
      "cumsize": 6514,
      "exception": null,
      "gas_limit": 18446744073709551615,
      "nodes_called": 23,
      "result": {
        "@type": "/cosmos.distribution.v1beta1.QueryDelegationTotalRewardsResponse",
        "rewards": [
          {
            "reward": [
              {
                "amount": "1.595194486065327400",
                "denom": "udys"
              }
            ],
            "validator_address": "dys2valoper1tcx55yxmg3a49upmg0nxgs5jc3d3t9udnpxn62"
          }
        ],
        "total": [
          {
            "amount": "1.595194486065327400",
            "denom": "udys"
          }
        ]
      },
      "script_gas_consumed": 1030659,
      "stdout": ""
    }


## 5. Withdraw-All-Rewards (CLI and Dyslang)

CLI supports:

- `dysond tx distribution withdraw-all-rewards --from <name>`

Below we re-implement this as a dyslang script that fetches delegations, builds `MsgWithdrawDelegatorReward` messages per validator, and submits them.



```python
# Re-implement withdraw-all-rewards as a Dyslang script using Python write
code = """
from dys import _query, _msg, get_executor_address
import json

def withdraw_all_rewards():
    delegator = get_executor_address()
    # 1) list delegations
    dels = _query({
        "@type": "/cosmos.staking.v1beta1.QueryDelegatorDelegationsRequest",
        "delegator_addr": delegator
    })
    msgs = []
    for d in dels.get("delegation_responses", []):
        valoper = d["delegation"]["validator_address"]
        msgs.append({
            "@type": "/cosmos.distribution.v1beta1.MsgWithdrawDelegatorReward",
            "delegator_address": delegator,
            "validator_address": valoper
        })
    if not msgs:
        return {"result": "no delegations"}

    # 2) submit all msgs in one transaction
    results = []
    for m in msgs:
        results.append(_msg(m))
    return {"withdrawn": len(results), "results": results}
"""
path = "/tmp/withdraw_all_rewards.py"
with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=True) as f:
    f.write(code)
    f.flush()
    path = f.name
    out = ! dysond tx script update --from alice --code-path {path} -y -o json --gas auto | dysond q wait-tx -o json | jq -M

! dysond tx script exec --from alice --script-address {ALICE} --function-name withdraw_all_rewards -y -o json --gas auto | dysond q wait-tx -o json | jq -M '.events[] | select(.type | startswith("dyson")) | .attributes[] | select(.key == "response") | .value  | fromjson | .result | fromjson'

```

    gas estimate: 1177195


    {
      "cumsize": 73084,
      "exception": null,
      "gas_limit": 1177195,
      "nodes_called": 72,
      "result": {
        "results": [
          {
            "@type": "/cosmos.distribution.v1beta1.MsgWithdrawDelegatorRewardResponse",
            "amount": [
              {
                "amount": "5",
                "denom": "udys"
              }
            ]
          }
        ],
        "withdrawn": 1
      },
      "script_gas_consumed": 1175247,
      "stdout": ""
    }


## 6. Harvest and Restake (Claimed Amount Only)

This script queries claimable rewards, withdraws them, then delegates exactly the claimed amount back to the validator(s). It prevents over-delegation by not touching the existing balance.



```python
code = """
from dys import _query, _msg, get_executor_address

# harvest_and_restake:
# - query per-validator outstanding rewards
# - withdraw with MsgWithdrawDelegatorReward
# - immediately delegate the returned amount back to the same validator
# - submit messages as they are constructed (atomic within one tx)

def harvest_and_restake():
    delegator = get_executor_address()

    # Identify validators we have delegations to
    dels = _query({
        "@type": "/cosmos.staking.v1beta1.QueryDelegatorDelegationsRequest",
        "delegator_addr": delegator,
    })
    vals = [d["delegation"]["validator_address"] for d in dels.get("delegation_responses", [])]
    if not vals:
        return {"result": "no delegations"}

    delegated_msgs = 0
    totals = {}

    for val in vals:
        # 1) Query outstanding rewards for delegator ↔ validator
        _query({
            "@type": "/cosmos.distribution.v1beta1.QueryDelegationRewardsRequest",
            "delegator_address": delegator,
            "validator_address": val,
        })

        # 2) Withdraw rewards for this validator
        wd = _msg({
            "@type": "/cosmos.distribution.v1beta1.MsgWithdrawDelegatorReward",
            "delegator_address": delegator,
            "validator_address": val,
        })

        # 3) Immediately delegate the withdrawn coins back to the same validator
        for coin in wd.get("amount", []):
            amt = coin.get("amount", "0")
            if amt == "0":
                continue
            denom = coin.get("denom", "udys")
            _msg({
                "@type": "/cosmos.staking.v1beta1.MsgDelegate",
                "delegator_address": delegator,
                "validator_address": val,
                "amount": {"denom": denom, "amount": amt},
            })
            delegated_msgs += 1
            totals[denom] = str(int(totals.get(denom, "0")) + int(amt))

    return {"delegations": delegated_msgs, "total": totals}
"""

with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=True) as f:
    f.write(code)
    f.flush()
    path = f.name
    _ = !dysond tx script update --from alice --code-path {path} -y -o json --gas 2000000 | dysond q wait-tx -o json > /dev/null

out = ! dysond tx script exec --from alice --script-address $ALICE --function-name harvest_and_restake -y -o json --gas 2000000 | dysond q wait-tx -o json | jq -M '.events[] | select(.type | startswith("dyson")) | .attributes[] | select(.key == "response") | .value  | fromjson | .result | fromjson'

print("out: ", "\n".join(out))

exec_result = json.loads("\n".join(out))

assert int(exec_result['result']['delegations']) > 0, "Expected at least one delegation"
# Sum all denoms to ensure some positive total was delegated
assert int(exec_result['result']['total']['udys']) > 0, "Expected a positive amount to be restaked"
```

    out:  {
      "cumsize": 121503,
      "exception": null,
      "gas_limit": 2000000,
      "nodes_called": 133,
      "result": {
        "delegations": 1,
        "total": {
          "udys": "3"
        }
      },
      "script_gas_consumed": 1342665,
      "stdout": ""
    }


## 7. Notes and Caveats

- `dysond tx distribution withdraw-all-rewards` is convenient; the dyslang scripts above mirror its behavior for automation.
- Staking is required to subscribe to events in the Crontask module; ensure your account has sufficient stake.
- Storage writes may require stake depending on `storage_stake_multiple`; large payloads consume more gas.
- Prefer narrowly scoped Authz grants if executing staking/distribution messages via scripts on behalf of users.
- Always use `--gas auto` for multi-message transactions (withdraw + delegate).

