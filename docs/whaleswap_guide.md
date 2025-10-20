# Whaleswap Module Guide

This notebook demonstrates end-to-end usage of the Whaleswap module:
- AMM pools (create/update/liquidity, exact-in and exact-out swaps)
- Orderbook offers (make/take)
- Liquid conversions
- Auctions (open + redeem without active bid)
- Discovery queries and metrics

We’ll register `foo.dys` and `bar.dys` and mint those denoms for use in demos.

## Setup

We’ll use `alice`, `bob`, and `charlie`. We'll register two names `foo.dys` and `bar.dys` via commit–reveal and then mint coins under these names for Whaleswap operations.


```python
# Addresses
[ALICE] = ! dysond keys show -a alice
[BOB]   = ! dysond keys show -a bob
[CHARLIE] = ! dysond keys show -a charlie
print("ALICE:", ALICE)
print("BOB  :", BOB)
print("CHARLIE:", CHARLIE)

# Helpers
import json
from IPython.core.magic import register_line_magic

@register_line_magic
def sh(line):
    ip = get_ipython()
    out = ip.getoutput(line)
    joined = '\n'.join(out)
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        print("Error parsing as json: ", joined)
        return joined
```

    ALICE: dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej
    BOB  : dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el
    CHARLIE: dys21cvqzw2968lq5wzldcglds02gnxg3d49fpmzt7e


## Register `foo.dys` and `bar.dys` (commit–reveal)

We’ll commit with a random salt and a reasonable valuation, then reveal each name.


```python
# --- foo.dys commit-reveal ---
FOO_NAME = "foo.dys"
FOO_SALT = "this is random"

out = %sh dysond query nameservice compute-hash --name "$FOO_NAME" --salt "$FOO_SALT" --committer "$ALICE" -o json
foo_hash = out['hex_hash']
print("foo hash:", foo_hash)

foo_commit_tx = %sh  dysond tx nameservice commit --commitment "$foo_hash" --valuation "100udys" --from alice -y -o json | dysond query wait-tx -o json
assert foo_commit_tx['code'] == 0, foo_commit_tx['raw_log']
events = [e for e in foo_commit_tx['events'] if e['type'].startswith('dysonprotocol')]
print(json.dumps(events, indent=2))

foo_reveal_tx = %sh dysond tx nameservice reveal --name "$FOO_NAME" --salt "$FOO_SALT" --from alice -y -o json | dysond query wait-tx -o json
assert foo_reveal_tx['code'] == 0, foo_reveal_tx['raw_log']
events = [e for e in foo_reveal_tx['events'] if e['type'].startswith('dysonprotocol')]
print(json.dumps(events, indent=2))
print("Registered:", FOO_NAME)
```

    foo hash: 388992452ccbe30bb24ca8befab89fe4d9c85577f03005e58ecb0322ae212901


    [
      {
        "type": "dysonprotocol.nameservice.v1.EventCommitmentCreated",
        "attributes": [
          {
            "key": "hexhash",
            "value": "\"388992452ccbe30bb24ca8befab89fe4d9c85577f03005e58ecb0322ae212901\"",
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


    [
      {
        "type": "dysonprotocol.nft.v1beta1.EventMint",
        "attributes": [
          {
            "key": "class_id",
            "value": "\"nameservice.dys\"",
            "index": true
          },
          {
            "key": "id",
            "value": "\"foo.dys\"",
            "index": true
          },
          {
            "key": "owner",
            "value": "\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"",
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
        "type": "dysonprotocol.nameservice.v1.EventNameRegistered",
        "attributes": [
          {
            "key": "fee",
            "value": "[{\"denom\":\"udys\",\"amount\":\"1\"}]",
            "index": true
          },
          {
            "key": "name",
            "value": "\"foo.dys\"",
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
    Registered: foo.dys



```python
# --- bar.dys commit-reveal ---
BAR_NAME = "bar.dys"
BAR_SALT = "this is random"

out = %sh dysond query nameservice compute-hash --name "$BAR_NAME" --salt "$BAR_SALT" --committer "$ALICE" -o json
bar_hash = out['hex_hash']
print("bar hash:", bar_hash)

bar_commit_tx = %sh dysond tx nameservice commit --commitment "$bar_hash" --valuation "100udys" --from alice -y -o json | dysond query wait-tx -o json
assert bar_commit_tx['code'] == 0, bar_commit_tx['raw_log']
events = [e for e in bar_commit_tx['events'] if e['type'].startswith('dysonprotocol')]
print(json.dumps(events, indent=2))

bar_reveal_tx = %sh dysond tx nameservice reveal --name "$BAR_NAME" --salt "$BAR_SALT" --from alice -y -o json | dysond query wait-tx -o json
assert bar_reveal_tx['code'] == 0, bar_reveal_tx['raw_log']
events = [e for e in bar_reveal_tx['events'] if e['type'].startswith('dysonprotocol')]
print(json.dumps(events, indent=2))
print("Registered:", BAR_NAME)
```

    bar hash: a3176c48695eb8cd9204477235c64357d6337daec6b643a7e36aeb8ec5dd0d3f


    [
      {
        "type": "dysonprotocol.nameservice.v1.EventCommitmentCreated",
        "attributes": [
          {
            "key": "hexhash",
            "value": "\"a3176c48695eb8cd9204477235c64357d6337daec6b643a7e36aeb8ec5dd0d3f\"",
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


    [
      {
        "type": "dysonprotocol.nft.v1beta1.EventMint",
        "attributes": [
          {
            "key": "class_id",
            "value": "\"nameservice.dys\"",
            "index": true
          },
          {
            "key": "id",
            "value": "\"bar.dys\"",
            "index": true
          },
          {
            "key": "owner",
            "value": "\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"",
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
        "type": "dysonprotocol.nameservice.v1.EventNameRegistered",
        "attributes": [
          {
            "key": "fee",
            "value": "[{\"denom\":\"udys\",\"amount\":\"1\"}]",
            "index": true
          },
          {
            "key": "name",
            "value": "\"bar.dys\"",
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
    Registered: bar.dys


## Mint coins for `foo.dys` and `bar.dys`

We’ll mint solid denoms under each name for liquidity and trading.


```python
from decimal import Decimal, ROUND_CEILING

params = %sh dysond query nameservice params -o json

fee_per = Decimal(params["params"].get("mint_fee_per_coin", "0"))
units = Decimal("1000000")
mint_fee = int((units * fee_per).to_integral_value(rounding=ROUND_CEILING))
print("mint_fee_per_coin:", str(fee_per), "computed mint_fee:", mint_fee)

foo_mint_tx = %sh dysond tx nameservice mint-coins --amount "1000000$FOO_NAME" --mint-fee {mint_fee}udys --from alice -y -o json | dysond query wait-tx -o json
assert foo_mint_tx['code'] == 0, foo_mint_tx['raw_log']
events = [e for e in foo_mint_tx['events'] if e['type'].startswith('dysonprotocol')]
print(json.dumps(events, indent=2))

bar_mint_tx = %sh dysond tx nameservice mint-coins --amount "1000000$BAR_NAME" --mint-fee {mint_fee}udys --from alice -y -o json | dysond query wait-tx -o json
assert bar_mint_tx['code'] == 0, bar_mint_tx['raw_log']
events = [e for e in bar_mint_tx['events'] if e['type'].startswith('dysonprotocol')]
print(json.dumps(events, indent=2))

```

    mint_fee_per_coin: 0.01 computed mint_fee: 10000


    [
      {
        "type": "dysonprotocol.nameservice.v1.EventCoinsMinted",
        "attributes": [
          {
            "key": "msg_index",
            "value": "0",
            "index": true
          }
        ]
      }
    ]


    [
      {
        "type": "dysonprotocol.nameservice.v1.EventCoinsMinted",
        "attributes": [
          {
            "key": "msg_index",
            "value": "0",
            "index": true
          }
        ]
      }
    ]


## Create AMM pool (foo.dys / bar.dys)

We’ll seed a pool with initial reserves and a fee (e.g., 0.3%).


```python
# Create the pool with two repeated --coins flags; fee 0.003
create_pool_tx = %sh dysond tx whaleswap create-pool --coins "100000$FOO_NAME" --coins "100000$BAR_NAME" --fee-pct "0.003" --from alice -y -o json | dysond query wait-tx -o json
assert create_pool_tx['code'] == 0, create_pool_tx['raw_log']

# Resolve pool_id by pair
pools_by_pair  = %sh dysond query whaleswap pools-by-pair --base-denom "$FOO_NAME" --quote-denom "$BAR_NAME" -o json
assert len(pools_by_pair.get('pools', [])) > 0, "No pool found for pair"
POOL_ID = pools_by_pair['pools'][0]['pool_id']
print("POOL_ID:", POOL_ID)

# Inspect the pool
%sh dysond query whaleswap pool --pool-id "$POOL_ID" -o json
```

    POOL_ID: 1





    {'pool': {'pool_id': '1',
      'coins': [{'denom': 'bar.dys', 'amount': '100000'},
       {'denom': 'foo.dys', 'amount': '100000'}],
      'shares_denom': 'whaleswap.dys/pools/1',
      'fee_pct': '0.003',
      'block_height': '13',
      'created': '2025-10-20T10:29:08.517955Z',
      'updated': '2025-10-20T10:29:08.517955Z'}}



## Add and remove liquidity

Demonstrate adding more reserves and later removing some shares.


```python
# Add liquidity using the pool's canonical coin order (keep earlier setup)
pool_info = %sh dysond query whaleswap pool --pool-id "{POOL_ID}" -o json


DENOM0 = pool_info['pool']['coins'][0]['denom']
DENOM1 = pool_info['pool']['coins'][1]['denom']
SHARES = pool_info['pool']['shares_denom']

ADD1 = f"10000{DENOM0}"
ADD2 = f"10000{DENOM1}"

add_liq_tx = %sh dysond tx whaleswap add-liquidity --pool-id "{POOL_ID}" --amount1 "{ADD1}" --amount2 "{ADD2}" --from alice -y -o json | dysond query wait-tx -o json

print("add-liquidity raw:")
assert add_liq_tx['code'] == 0, add_liq_tx['raw_log']
events = [e for e in add_liq_tx['events'] if e['type'].startswith('dysonprotocol')]
print(json.dumps(events, indent=2))

# Check Alice's shares before remove
alice_bal = %sh dysond query bank balance "{ALICE}" "{SHARES}" -o json
avail = int(alice_bal['balance']['amount'])
print("Alice shares before remove:", alice_bal)
assert avail > 0, "No shares available"

# Remove a small portion of liquidity (ensure >0 and small)
REMOVE_SHARES = avail // 10
rm_liq_tx = %sh dysond tx whaleswap remove-liquidity --pool-id "{POOL_ID}" --shares "{REMOVE_SHARES}" --from alice -y -o json | dysond query wait-tx -o json
assert rm_liq_tx['code'] == 0, rm_liq_tx['raw_log']

events = [e for e in rm_liq_tx['events'] if e['type'].startswith('dysonprotocol')]
print("Removed shares:")
print(json.dumps(events, indent=2))

# Check Alice's shares after remove
alice_bal = %sh dysond query bank balance "{ALICE}" "{SHARES}" -o json
avail = int(alice_bal['balance']['amount'])
print("Alice shares after remove:", alice_bal)
assert avail > 0, "No shares available"
```

    add-liquidity raw:
    [
      {
        "type": "dysonprotocol.whaleswap.v1.EventPoolUpdate",
        "attributes": [
          {
            "key": "pool_id",
            "value": "\"1\"",
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
        "type": "dysonprotocol.nameservice.v1.EventCoinsMinted",
        "attributes": [
          {
            "key": "msg_index",
            "value": "0",
            "index": true
          }
        ]
      },
      {
        "type": "dysonprotocol.whaleswap.v1.EventPoolLiquidityAdded",
        "attributes": [
          {
            "key": "pool_id",
            "value": "\"1\"",
            "index": true
          },
          {
            "key": "shares",
            "value": "\"10000\"",
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


    Alice shares before remove: {'balance': {'denom': 'whaleswap.dys/pools/1', 'amount': '110000'}}


    Removed shares:
    [
      {
        "type": "dysonprotocol.whaleswap.v1.EventPoolUpdate",
        "attributes": [
          {
            "key": "pool_id",
            "value": "\"1\"",
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
        "type": "dysonprotocol.whaleswap.v1.EventPoolLiquidityRemoved",
        "attributes": [
          {
            "key": "pool_id",
            "value": "\"1\"",
            "index": true
          },
          {
            "key": "shares",
            "value": "\"11000\"",
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


    Alice shares after remove: {'balance': {'denom': 'whaleswap.dys/pools/1', 'amount': '99000'}}


## Pool swaps (exact-in and exact-out)

We show:
- Exact-in: provide `swap_in` and cap with `--max-input`
- Exact-out: provide `swap_out`, module computes required input


```python
# Fund demo accounts for swaps, takes, and liquid conversions
# - Bob needs foo.dys and bar.dys (for pool swap and taking Alice's offer)
# - Charlie needs foo.dys (to convert to liquid and back)

tx = %sh dysond tx bank send alice "$BOB" "100000$FOO_NAME" -y -o json | dysond query wait-tx -o json
assert tx['code'] == 0, tx['raw_log']

tx = %sh dysond tx bank send alice "$BOB" "100000$BAR_NAME" -y -o json | dysond query wait-tx -o json
assert tx['code'] == 0, tx['raw_log']

tx = %sh dysond tx bank send alice "$CHARLIE" "5000$FOO_NAME" -y -o json | dysond query wait-tx -o json
assert tx['code'] == 0, tx['raw_log']

# (Optional) quick balance peek
print("Bob balances:")
! dysond query bank balances "$BOB" -o json | jq -M
print("Charlie balances:")
! dysond query bank balances "$CHARLIE" -o json | jq -M
```

    Bob balances:


    {
      "balances": [
        {
          "denom": "bar.dys",
          "amount": "100000"
        },
        {
          "denom": "foo.dys",
          "amount": "100000"
        },
        {
          "denom": "udys",
          "amount": "10000000000"
        }
      ],
      "pagination": {
        "total": "3"
      }
    }


    Charlie balances:


    {
      "balances": [
        {
          "denom": "foo.dys",
          "amount": "5000"
        },
        {
          "denom": "udys",
          "amount": "10000000000"
        }
      ],
      "pagination": {
        "total": "2"
      }
    }



```python
# Pool swap (exact-in): single leg object + min-output safety; keep intermediate output
import json, shlex

max_in = f"500{FOO_NAME}"
legs = json.dumps({"pool_id": int(POOL_ID), "swap_in": {"denom": FOO_NAME, "amount": "500"}})
legs_q = shlex.quote(legs)

swap_in_tx = %sh dysond tx whaleswap swap --from bob --max-input {max_in} --legs {legs_q} --min-output "1$BAR_NAME" -y -o json | dysond query wait-tx -o json
events = [e for e in swap_in_tx['events'] if e['type'].startswith('dysonprotocol')]

assert swap_in_tx['code'] == 0, swap_in_tx['raw_log']
print("Exact-in swap success")
print(json.dumps(events, indent=2))
```

    Exact-in swap success
    [
      {
        "type": "dysonprotocol.whaleswap.v1.EventPoolUpdate",
        "attributes": [
          {
            "key": "pool_id",
            "value": "\"1\"",
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
        "type": "dysonprotocol.whaleswap.v1.EventPoolSwap",
        "attributes": [
          {
            "key": "pool_id",
            "value": "\"1\"",
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
        "type": "dysonprotocol.whaleswap.v1.EventTradeRecorded",
        "attributes": [
          {
            "key": "auction_id",
            "value": "\"0\"",
            "index": true
          },
          {
            "key": "note",
            "value": "\"\"",
            "index": true
          },
          {
            "key": "offer_id",
            "value": "\"0\"",
            "index": true
          },
          {
            "key": "pool_id",
            "value": "\"1\"",
            "index": true
          },
          {
            "key": "trade_id",
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
    ]



```python
# Pool swap (exact-out): single leg object + provide cap for inferred input denom; keep intermediate output
import json, shlex

legs = json.dumps({"pool_id": int(POOL_ID), "swap_out": {"denom": BAR_NAME, "amount": "250"}})
legs_q = shlex.quote(legs)

swap_out_tx = %sh dysond tx whaleswap swap --from bob --max-input "100000$FOO_NAME" --legs {legs_q} -y -o json | dysond query wait-tx -o json
assert swap_out_tx['code'] == 0, swap_out_tx['raw_log']

events = [e for e in swap_out_tx['events'] if e['type'].startswith('dysonprotocol')]
print("Exact-out swap success")
print(json.dumps(events, indent=2))
```

    Exact-out swap success
    [
      {
        "type": "dysonprotocol.whaleswap.v1.EventPoolUpdate",
        "attributes": [
          {
            "key": "pool_id",
            "value": "\"1\"",
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
        "type": "dysonprotocol.whaleswap.v1.EventPoolSwap",
        "attributes": [
          {
            "key": "pool_id",
            "value": "\"1\"",
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
        "type": "dysonprotocol.whaleswap.v1.EventTradeRecorded",
        "attributes": [
          {
            "key": "auction_id",
            "value": "\"0\"",
            "index": true
          },
          {
            "key": "note",
            "value": "\"\"",
            "index": true
          },
          {
            "key": "offer_id",
            "value": "\"0\"",
            "index": true
          },
          {
            "key": "pool_id",
            "value": "\"1\"",
            "index": true
          },
          {
            "key": "trade_id",
            "value": "\"2\"",
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


## Update pool config (optional)

Adjust fee or set price bands.


```python
# Lower fee to 0.25% (example)
upd_tx = %sh dysond tx whaleswap update-pool-config --pool-id "$POOL_ID" --fee-pct "0.0025" --from alice -y -o json | dysond query wait-tx -o json
assert upd_tx['code'] == 0, upd_tx['raw_log']
print("Pool fee updated")

events = [e for e in upd_tx['events'] if e['type'].startswith('dysonprotocol')]
print("Pool fee updated")
print(json.dumps(events, indent=2))

# Re-check pool
! dysond query whaleswap pool --pool-id "$POOL_ID" -o json
```

    Pool fee updated
    Pool fee updated
    [
      {
        "type": "dysonprotocol.whaleswap.v1.EventPoolUpdate",
        "attributes": [
          {
            "key": "pool_id",
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
    ]


    {
      "pool": {
        "pool_id": "1",
        "coins": [
          {
            "denom": "bar.dys",
            "amount": "98254"
          },
          {
            "denom": "foo.dys",
            "amount": "99754"
          }
        ],
        "shares_denom": "whaleswap.dys/pools/1",
        "fee_pct": "0.0025",
        "block_height": "21",
        "created": "2025-10-20T10:29:08.517955Z",
        "updated": "2025-10-20T10:29:13.995234Z",
        "num_trades": "2",
        "fees_earned": [
          {
            "denom": "foo.dys",
            "amount": "3"
          }
        ]
      }
    }


## Orderbook offers (make + take)

- Maker posts an offer (have → want)
- Taker executes with full remaining (no `take_units`) or partial (`take_units`).


```python
# Alice makes an offer: she has foo.dys and wants bar.dys
# Autocli typically accepts coin syntax for Coin fields; adjust if your CLI differs
mk_offer_tx = %sh dysond tx whaleswap make-offer --have "1000$FOO_NAME" --want "400$BAR_NAME" --from alice -y -o json | dysond query wait-tx -o json
assert mk_offer_tx['code'] == 0, mk_offer_tx['raw_log']
print("Offer created")
events = [e for e in mk_offer_tx['events'] if e['type'].startswith('dysonprotocol')]
print(json.dumps(events, indent=2))

# Find the offer id by owner
offers_by_owner = %sh dysond query whaleswap offers-by-owner --owner "$ALICE" -o json
assert len(offers_by_owner.get('offers', [])) > 0, "No offers found for Alice"
OFFER_ID = offers_by_owner['offers'][0]['offer_id']
print("OFFER_ID:", OFFER_ID)
print(json.dumps(offers_by_owner, indent=2))

# Bob takes the offer fully (omit take_units to take remaining)
take_tx = %sh dysond tx whaleswap take-offer --trades "offer_id=$OFFER_ID" --from bob -y -o json | dysond query wait-tx -o json
assert take_tx['code'] == 0, take_tx['raw_log']
print("Offer taken by Bob")
events = [e for e in take_tx['events'] if e['type'].startswith('dysonprotocol')]
print(json.dumps(events, indent=2))
```

    Offer created
    [
      {
        "type": "dysonprotocol.whaleswap.v1.EventOfferCreated",
        "attributes": [
          {
            "key": "offer_id",
            "value": "1",
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


    OFFER_ID: 1
    {
      "offers": [
        {
          "offer_id": "1",
          "status": "open",
          "maker": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
          "updated_height": "23",
          "updated_timestamp": "2025-10-20T10:29:14.55588Z",
          "initial_have": {
            "denom": "foo.dys",
            "amount": "1000"
          },
          "initial_want": {
            "denom": "bar.dys",
            "amount": "400"
          },
          "remaining_have": {
            "denom": "foo.dys",
            "amount": "1000"
          },
          "remaining_want": {
            "denom": "bar.dys",
            "amount": "400"
          },
          "unit_have_int": "5",
          "unit_want_int": "2",
          "remaining_units": "200",
          "pfand_locked": {
            "denom": "whaleswap.dys/pfand",
            "amount": "0"
          }
        }
      ],
      "pagination": {
        "total": "1"
      }
    }


    Offer taken by Bob
    [
      {
        "type": "dysonprotocol.whaleswap.v1.EventTradeRecorded",
        "attributes": [
          {
            "key": "auction_id",
            "value": "\"0\"",
            "index": true
          },
          {
            "key": "note",
            "value": "\"\"",
            "index": true
          },
          {
            "key": "offer_id",
            "value": "\"1\"",
            "index": true
          },
          {
            "key": "pool_id",
            "value": "\"0\"",
            "index": true
          },
          {
            "key": "trade_id",
            "value": "\"3\"",
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
        "type": "dysonprotocol.whaleswap.v1.EventOfferTaken",
        "attributes": [
          {
            "key": "offer_id",
            "value": "\"1\"",
            "index": true
          },
          {
            "key": "trade_id",
            "value": "\"3\"",
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


## Liquid conversions

Convert solid → liquid and back.


```python
# Charlie converts foo.dys to liquid and then back
to_liq_tx = %sh dysond tx whaleswap convert-to-liquid --denom "$FOO_NAME" --amount "250" --from charlie -y -o json | dysond query wait-tx -o json
assert to_liq_tx['code'] == 0, to_liq_tx['raw_log']
print("Converted to liquid")
events = [e for e in to_liq_tx['events'] if e['type'].startswith('dysonprotocol')]
print(json.dumps(events, indent=2))


LIQ_DENOM = f"whaleswap.dys/coins/{FOO_NAME}"
to_sol_tx = %sh dysond tx whaleswap convert-to-solid --liquid-denom "$LIQ_DENOM" --amount "100" --from charlie -y -o json | dysond query wait-tx -o json
assert to_sol_tx['code'] == 0, to_sol_tx['raw_log']
print("Converted back to solid")
events = [e for e in to_sol_tx['events'] if e['type'].startswith('dysonprotocol')]
print(json.dumps(events, indent=2))
```

    Converted to liquid
    [
      {
        "type": "dysonprotocol.nameservice.v1.EventCoinsMinted",
        "attributes": [
          {
            "key": "msg_index",
            "value": "0",
            "index": true
          }
        ]
      }
    ]


    Converted back to solid
    [
      {
        "type": "dysonprotocol.nameservice.v1.EventCoinsBurned",
        "attributes": [
          {
            "key": "amount",
            "value": "[{\"denom\":\"whaleswap.dys/coins/foo.dys\",\"amount\":\"100\"}]",
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


## Auctions: open and redeem (no active bid)

- Seller escrows one solid coin in whaleswap and gets an NFT (class per bid denom).
- Without active bids, owner can redeem and burn the NFT.


```python
# Alice opens an auction: sell bar.dys, bid denom is foo.dys
open_auc_tx = %sh dysond tx whaleswap open-auction --sell "200$BAR_NAME" --bid-denom "$FOO_NAME" --from alice -y --gas 300000 -o json | dysond query wait-tx -o json
assert open_auc_tx['code'] == 0, open_auc_tx['raw_log']
print("Auction opened")
events = [e for e in open_auc_tx['events'] if e['type'].startswith('dysonprotocol')]
print(json.dumps(events, indent=2))

# Resolve auction id by seller
aucs_by_seller = %sh dysond query whaleswap auctions-by-seller --seller "$ALICE" -o json
assert len(aucs_by_seller.get('auctions', [])) > 0, "No auctions found"
print(json.dumps(aucs_by_seller, indent=2))
AUC_ID = aucs_by_seller['auctions'][-1]['auction_id']
print("AUC_ID:", AUC_ID)

# No active bid; owner redeems escrow
redeem_tx = %sh dysond tx whaleswap redeem-auction --auction-id "$AUC_ID" --from alice -y -o json | dysond query wait-tx -o json
assert redeem_tx['code'] == 0, redeem_tx['raw_log']
print("Auction redeemed and closed")
events = [e for e in redeem_tx['events'] if e['type'].startswith('dysonprotocol')]
print(json.dumps(events, indent=2))

```

    Auction opened
    [
      {
        "type": "dysonprotocol.nameservice.v1.EventClassSaved",
        "attributes": [
          {
            "key": "class_id",
            "value": "\"whaleswap.dys/auction/foo.dys\"",
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
        "type": "dysonprotocol.nameservice.v1.EventNFTClassAlwaysListedUpdated",
        "attributes": [
          {
            "key": "class_id",
            "value": "\"whaleswap.dys/auction/foo.dys\"",
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
        "type": "dysonprotocol.nameservice.v1.EventNFTClassDataUpdated",
        "attributes": [
          {
            "key": "class_id",
            "value": "\"whaleswap.dys/auction/foo.dys\"",
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
        "type": "dysonprotocol.nameservice.v1.EventNFTClassDataUpdated",
        "attributes": [
          {
            "key": "class_id",
            "value": "\"whaleswap.dys/auction/foo.dys\"",
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
        "type": "dysonprotocol.nameservice.v1.EventNFTClassDataUpdated",
        "attributes": [
          {
            "key": "class_id",
            "value": "\"whaleswap.dys/auction/foo.dys\"",
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
        "type": "dysonprotocol.nameservice.v1.EventNFTClassDataUpdated",
        "attributes": [
          {
            "key": "class_id",
            "value": "\"whaleswap.dys/auction/foo.dys\"",
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
        "type": "dysonprotocol.nameservice.v1.EventNFTClassDataUpdated",
        "attributes": [
          {
            "key": "class_id",
            "value": "\"whaleswap.dys/auction/foo.dys\"",
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
        "type": "dysonprotocol.nft.v1beta1.EventMint",
        "attributes": [
          {
            "key": "class_id",
            "value": "\"whaleswap.dys/auction/foo.dys\"",
            "index": true
          },
          {
            "key": "id",
            "value": "\"0000000001\"",
            "index": true
          },
          {
            "key": "owner",
            "value": "\"dys21zkclxp4w9q88sndatgvatzcesr0qmm4qhhl33q\"",
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
        "type": "dysonprotocol.nameservice.v1.EventNFTMinted",
        "attributes": [
          {
            "key": "class_id",
            "value": "\"whaleswap.dys/auction/foo.dys\"",
            "index": true
          },
          {
            "key": "nft_id",
            "value": "\"0000000001\"",
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
        "type": "dysonprotocol.nameservice.v1.EventNftMoved",
        "attributes": [
          {
            "key": "class_id",
            "value": "\"whaleswap.dys/auction/foo.dys\"",
            "index": true
          },
          {
            "key": "from_address",
            "value": "\"dys21zkclxp4w9q88sndatgvatzcesr0qmm4qhhl33q\"",
            "index": true
          },
          {
            "key": "nft_id",
            "value": "\"0000000001\"",
            "index": true
          },
          {
            "key": "to_address",
            "value": "\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"",
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
        "type": "dysonprotocol.whaleswap.v1.EventAuctionCreated",
        "attributes": [
          {
            "key": "auction_id",
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
    ]


    {
      "auctions": [
        {
          "auction_id": "1",
          "class_id": "whaleswap.dys/auction/foo.dys",
          "nft_id": "0000000001",
          "sell": {
            "denom": "bar.dys",
            "amount": "200"
          },
          "bid_denom": "foo.dys",
          "seller": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej"
        }
      ],
      "pagination": {
        "total": "1"
      }
    }
    AUC_ID: 1


    Auction redeemed and closed
    [
      {
        "type": "dysonprotocol.nft.v1beta1.EventBurn",
        "attributes": [
          {
            "key": "class_id",
            "value": "\"whaleswap.dys/auction/foo.dys\"",
            "index": true
          },
          {
            "key": "id",
            "value": "\"0000000001\"",
            "index": true
          },
          {
            "key": "owner",
            "value": "\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"",
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
        "type": "dysonprotocol.nameservice.v1.EventNFTBurned",
        "attributes": [
          {
            "key": "class_id",
            "value": "\"whaleswap.dys/auction/foo.dys\"",
            "index": true
          },
          {
            "key": "nft_id",
            "value": "\"0000000001\"",
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
        "type": "dysonprotocol.whaleswap.v1.EventAuctionRedeemed",
        "attributes": [
          {
            "key": "auction_id",
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
    ]


## Mixed Trade (MakeTrade) with Note

Demonstrate `MsgMakeTrade` which combines pool swaps and orderbook takes in one transaction, with an optional note recorded on each resulting Trade.

We'll use a single swap leg for simplicity, including a note.




```python
# Mixed trade: single swap leg via MakeTrade, with a note
# Note: MsgMakeTrade requires JSON for operations; here a swap leg

import json, shlex

# Define a swap operation: exact-in 300 foo.dys for bar.dys output
# The autocli --op flag expects either {"swap": {...}} or {"take": {...}}
op = {
    "swap": {
        "pool_id": int(POOL_ID),
        "swap_in": {"denom": FOO_NAME, "amount": "300"}
    }
}
op_json = json.dumps(op)
op_q = shlex.quote(op_json)

note = "Demo mixed trade with note"

make_trade_tx = %sh dysond tx whaleswap make-trade --from bob --max-input "100000$FOO_NAME" --op {op_q} --min-output "1$BAR_NAME" --trade-note "{note}" -y -o json | dysond query wait-tx -o json
assert isinstance(make_trade_tx, dict) and make_trade_tx['code'] == 0, make_trade_tx

print("MakeTrade success with note")
events = [e for e in make_trade_tx['events'] if e['type'].startswith('dysonprotocol')]
print(json.dumps(events, indent=2))

# Query recent trade to verify note (look for EventTradeRecorded and extract trade_id)
trade_events = [e for e in events if 'EventTradeRecorded' in e['type']]
if trade_events:
    # Find trade_id attribute
    for attr in trade_events[0]['attributes']:
        if attr['key'] == 'trade_id':
            recent_trade_id = int(attr['value'].strip('"'))
            trade = %sh dysond query whaleswap trade --trade-id {recent_trade_id} -o json
            print("Recent trade with note:")
            print(json.dumps(trade, indent=2))
            break
else:
    print("No EventTradeRecorded found")

```

    MakeTrade success with note
    [
      {
        "type": "dysonprotocol.whaleswap.v1.EventPoolUpdate",
        "attributes": [
          {
            "key": "pool_id",
            "value": "\"1\"",
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
        "type": "dysonprotocol.whaleswap.v1.EventPoolSwap",
        "attributes": [
          {
            "key": "pool_id",
            "value": "\"1\"",
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
        "type": "dysonprotocol.whaleswap.v1.EventTradeRecorded",
        "attributes": [
          {
            "key": "auction_id",
            "value": "\"0\"",
            "index": true
          },
          {
            "key": "note",
            "value": "\"Demo mixed trade with note\"",
            "index": true
          },
          {
            "key": "offer_id",
            "value": "\"0\"",
            "index": true
          },
          {
            "key": "pool_id",
            "value": "\"1\"",
            "index": true
          },
          {
            "key": "trade_id",
            "value": "\"4\"",
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


    Recent trade with note:
    {
      "trade": {
        "trade_id": "4",
        "taker": "dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el",
        "height": "29",
        "timestamp": "2025-10-20T10:29:17.934736Z",
        "sent": {
          "denom": "foo.dys",
          "amount": "300"
        },
        "received": {
          "denom": "bar.dys",
          "amount": "293"
        },
        "pool_id": "1",
        "note": "Demo mixed trade with note"
      }
    }


## Discovery queries and metrics

Explore indexes and health metrics.


```python
# Pools by denom
print("Pools mentioning foo.dys")
! dysond query whaleswap pools-by-denom --denom "$FOO_NAME" -o json | jq -M

# Offers by denom (role unspecified: either side)
print("Offers mentioning bar.dys (if any now):")
! dysond query whaleswap offers-by-denom --denom "$BAR_NAME" -o json | jq -M

# Auctions by pair price range (placeholder scanning endpoint)
print("Auctions (pair price range) foo.dys/bar.dys:")
! dysond query whaleswap auctions-by-pair-price-range --sell-denom "$BAR_NAME" --bid-denom "$FOO_NAME" -o json | jq -M

# Metrics
print("Module metrics:")
! dysond query whaleswap metrics -o json | jq -M
```

    Pools mentioning foo.dys


    {
      "pools": [
        {
          "pool_id": "1",
          "coins": [
            {
              "denom": "bar.dys",
              "amount": "97961"
            },
            {
              "denom": "foo.dys",
              "amount": "100054"
            }
          ],
          "shares_denom": "whaleswap.dys/pools/1",
          "fee_pct": "0.0025",
          "block_height": "29",
          "created": "2025-10-20T10:29:08.517955Z",
          "updated": "2025-10-20T10:29:17.934736Z",
          "num_trades": "3",
          "fees_earned": [
            {
              "denom": "foo.dys",
              "amount": "4"
            }
          ]
        }
      ],
      "pagination": {
        "total": "1"
      }
    }


    Offers mentioning bar.dys (if any now):


    {
      "offers": [
        {
          "offer_id": "1",
          "status": "closed",
          "maker": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
          "updated_height": "24",
          "updated_timestamp": "2025-10-20T10:29:15.118835Z",
          "initial_have": {
            "denom": "foo.dys",
            "amount": "1000"
          },
          "initial_want": {
            "denom": "bar.dys",
            "amount": "400"
          },
          "remaining_have": {
            "denom": "foo.dys",
            "amount": "0"
          },
          "remaining_want": {
            "denom": "bar.dys",
            "amount": "0"
          },
          "unit_have_int": "5",
          "unit_want_int": "2",
          "remaining_units": "0",
          "pfand_locked": {
            "denom": "whaleswap.dys/pfand",
            "amount": "0"
          }
        }
      ],
      "pagination": {
        "total": "1"
      }
    }


    Auctions (pair price range) foo.dys/bar.dys:


    {
      "pagination": {}
    }


    Module metrics:


    {
      "metrics": {
        "num_trades": "4",
        "escrowed_pool_coins": [
          {
            "denom": "bar.dys",
            "amount": "97961"
          },
          {
            "denom": "foo.dys",
            "amount": "100054"
          }
        ],
        "escrowed_liquid_coins": [
          {
            "denom": "foo.dys",
            "amount": "150"
          }
        ],
        "fees_earned": [
          {
            "denom": "foo.dys",
            "amount": "4"
          }
        ]
      }
    }


## Summary

- Registered `foo.dys` and `bar.dys`, minted denoms, and created an AMM pool with fee control and liquidity ops.
- Performed pool swaps (exact-in and exact-out).
- Demonstrated orderbook make/take using coins.
- Wrapped and unwrapped liquid coins.
- Opened and redeemed an auction without active bids.
- Ran discovery queries and fetched module metrics.

Tip: If any CLI flag formats differ in your environment (autocli vs custom CLI), run `dysond tx whaleswap --help` or the subcommand `--help` to confirm accepted flags and adjust accordingly.
