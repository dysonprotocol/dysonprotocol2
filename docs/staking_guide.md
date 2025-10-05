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
          "operator_address": "dys2valoper1l0t4l4hepuezjxjww3jud4tlx6qew86h7z48zj",
          "consensus_pubkey": {
            "type": "/cosmos.crypto.ed25519.PubKey",
            "value": "mJ3xy0pDqxoQ/o7klH0fn4T9ADglInPjSoYR3mKyvT8="
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
            "update_time": "2025-10-05T08:55:51.073783Z"
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
              "update_time": "2025-10-05T08:55:51.073783Z"
            },
            "consensus_pubkey": {
              "@type": "/cosmos.crypto.ed25519.PubKey",
              "key": "mJ3xy0pDqxoQ/o7klH0fn4T9ADglInPjSoYR3mKyvT8="
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
            "operator_address": "dys2valoper1l0t4l4hepuezjxjww3jud4tlx6qew86h7z48zj",
            "status": "BOND_STATUS_BONDED",
            "tokens": "1000000",
            "unbonding_height": "0",
            "unbonding_ids": [],
            "unbonding_on_hold_ref_count": "0",
            "unbonding_time": "1970-01-01T00:00:00Z"
          }
        ]
      },
      "script_gas_consumed": 1009633,
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

    Delegating 1000udys from dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej to dys2valoper1l0t4l4hepuezjxjww3jud4tlx6qew86h7z48zj


    gas estimate: 105648


    {
      "height": "60",
      "txhash": "09C407BFAC358241C4B231F4D1971AA6783DDE17F8ABDDAF91529F2D4291688F",
      "codespace": "",
      "code": 0,
      "data": "122D0A2B2F636F736D6F732E7374616B696E672E763162657461312E4D736744656C6567617465526573706F6E7365",
      "raw_log": "",
      "logs": [],
      "info": "",
      "gas_wanted": "105648",
      "gas_used": "103700",
      "tx": null,
      "timestamp": "",
      "events": [
        {
          "type": "tx",
          "attributes": [
            {
              "key": "acc_seq",
              "value": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/13",
              "index": true
            }
          ]
        },
        {
          "type": "tx",
          "attributes": [
            {
              "key": "signature",
              "value": "gxXXDvILtse6DPA5Eh9fcoHzHdQ/TgFU/p8QWm/2L5BjxqXcj9sqqQ05jGwvAGQgmUc1HitpMUsjTPlUCO5r7g==",
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
              "value": "dys2valoper1l0t4l4hepuezjxjww3jud4tlx6qew86h7z48zj",
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

    gas estimate: 1057130


    {"height":"61","txhash":"35D32036C2B59A9BF79F1E8C758C3DDFB62F81C565ABD8E1808276802529F2B4","codespace":"","code":0,"data":"12360A302F6479736F6E70726F746F636F6C2E7363726970742E76312E4D7367557064617465536372697074526573706F6E736512020803","raw_log":"","logs":[],"info":"","gas_wanted":"1057130","gas_used":"1055182","tx":null,"timestamp":"","events":[{"type":"tx","attributes":[{"key":"acc_seq","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/14","index":true}]},{"type":"tx","attributes":[{"key":"signature","value":"618+MuAJkR4gHO9bCuW8P10zmf5GlVynEuGJgW8Zbetfj1TKWLTrkKreolcPGyXi2Urr73TjhIlpTz3hR5hoBw==","index":true}]},{"type":"message","attributes":[{"key":"action","value":"/dysonprotocol.script.v1.MsgUpdateScript","index":true},{"key":"sender","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej","index":true},{"key":"module","value":"script","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"dysonprotocol.script.v1.EventUpdateScript","attributes":[{"key":"script_address","value":"\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"","index":true},{"key":"version","value":"\"3\"","index":true},{"key":"msg_index","value":"0","index":true}]}]}


    gas estimate: 1143676


## 4. Query Rewards

We’ll query rewards for a delegator using both CLI and dyslang.


```python
! dysond query distribution rewards {ALICE} -o json | jq -M
```

    {
      "rewards": [
        {
          "validator_address": "dys2valoper1l0t4l4hepuezjxjww3jud4tlx6qew86h7z48zj",
          "reward": [
            "2.175482517482517000udys"
          ]
        }
      ],
      "total": [
        "2.175482517482517000udys"
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
                "amount": "2.900643356643356000",
                "denom": "udys"
              }
            ],
            "validator_address": "dys2valoper1l0t4l4hepuezjxjww3jud4tlx6qew86h7z48zj"
          }
        ],
        "total": [
          {
            "amount": "2.900643356643356000",
            "denom": "udys"
          }
        ]
      },
      "script_gas_consumed": 1030578,
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

    gas estimate: 1176943


    {
      "cumsize": 73084,
      "exception": null,
      "gas_limit": 1176943,
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
      "script_gas_consumed": 1174995,
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
    _ = !dysond tx script update --from alice --code-path {path} -y -o json --gas auto | dysond q wait-tx -o json > /dev/null

out = !dysond tx script exec --from alice --script-address $ALICE --function-name harvest_and_restake -y -o json --gas auto | dysond q wait-tx -o json | jq -M '.events[] | select(.type | startswith("dyson")) | .attributes[] | select(.key == "response") | .value  | fromjson | .result | fromjson'
out = "\n".join(out[1:])

print(out)

exec_result = json.loads(out)
assert int(exec_result['result']['delegations']) > 0, "Expected at least one delegation"
# Sum all denoms to ensure some positive total was delegated
assert int(exec_result['result']['total']['udys']) > 0, "Expected a positive amount to be restaked"
```

    {
      "cumsize": 121503,
      "exception": null,
      "gas_limit": 1344166,
      "nodes_called": 133,
      "result": {
        "delegations": 1,
        "total": {
          "udys": "2"
        }
      },
      "script_gas_consumed": 1342155,
      "stdout": ""
    }


## 7. Notes and Caveats

- `dysond tx distribution withdraw-all-rewards` is convenient; the dyslang scripts above mirror its behavior for automation.
- Staking is required to subscribe to events in the Crontask module; ensure your account has sufficient stake.
- Storage writes may require stake depending on `storage_stake_multiple`; large payloads consume more gas.
- Prefer narrowly scoped Authz grants if executing staking/distribution messages via scripts on behalf of users.
- Always use `--gas auto` for multi-message transactions (withdraw + delegate).

