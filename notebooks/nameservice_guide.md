# Dyson Protocol Nameservice Guide

The Nameservice module represents a cornerstone of the Dyson Protocol ecosystem, providing a sophisticated decentralized identity and asset management system. This comprehensive guide walks you through the elegant architecture of name registration, NFT integration, and token creation—demonstrating how these components harmoniously interact to enable a new paradigm of digital ownership. By following these carefully crafted examples, you'll gain hands-on experience with the full spectrum of Nameservice capabilities, from secure two-phase name registration to advanced NFT collection management and custom asset creation.

## Fetch Your Address

First, we'll retrieve the addresses associated with the 'alice' and 'bob' accounts. These addresses will serve as our identities throughout this guide.


```python
[alice_address] = ! dysond keys show alice -a
[bob_address] = ! dysond keys show bob -a
print(f"Alice address: {alice_address}")
print(f"Bob address: {bob_address}")
```

    Alice address: dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej
    Bob address: dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el


## Check Nameservice Parameters

Let's examine the current parameters of the nameservice module to understand the rules for bidding, valuations, and accepted denominations.


```python
! dysond query nameservice params -o json | jq -M
```

    {
      "params": {
        "mint_fee_per_coin": "0.01",
        "min_bid_timeout_class": "0s",
        "max_bid_timeout_class": "2160h0m0s",
        "min_reject_bid_valuation_fee_percent": "0.0",
        "max_reject_bid_valuation_fee_percent": "1.0",
        "min_minimum_bid_percent_increase": "0.0",
        "max_minimum_bid_percent_increase": "1.0",
        "min_valuation_fee_pct": "0.0",
        "max_valuation_fee_pct": "1.0",
        "min_valuation_period": "1h0m0s",
        "max_valuation_period": "8760h0m0s"
      }
    }


## Name Registration Process

Registering a name in Dyson Protocol uses a two-step commit-reveal process to prevent front-running. Let's register a name following this process.

### Generate Salt and Name

First, let's prepare a name and generate a random salt value for the commitment.


```python
import random
import string
import json

def random_string(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


name = f"alice-{random_string(5)}.dys"
salt = random_string(20)


print(f"Name: {name}")
print(f"Salt: {salt}")
```

    Name: alice-ri1rr.dys
    Salt: 21a2f759208zss9z272e


### Compute Hash for Commitment

Now, we'll compute a hash using the name, salt, and committer address. This hash will be used in the commitment phase.


```python
[name_commit_hex_hash] = ! dysond query nameservice compute-hash \
    --name "$name" \
    --salt "$salt" \
    --committer "$alice_address"  -o json| jq '.hex_hash' -r
print(f"Hex Hash: {name_commit_hex_hash}")
```

    Hex Hash: dd61d1b139033b515021d59adf0a38bfce182b3a3cdf024073a545460a44d1ce


### Commit Phase

In this first phase, we commit to registering the name by submitting the hash and setting an initial valuation.


```python
valuation = '100udys'
[txhash] = ! dysond tx nameservice commit \
    --commitment "$name_commit_hex_hash" \
    --valuation "$valuation" \
    --from alice -y -o json | jq -r .txhash ; sleep 0.01
# Some delay to ensure the transaction is available

print(f"Transaction hash: {txhash}")
tx_result = ! dysond query wait-tx $txhash -o json --timeout 3s
print(tx_result)
tx_result = json.loads("".join(tx_result))

assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"
print(f"Tx error code: {tx_result['code']}")

for event in tx_result['events']:
    if 'dysonprotocol' in event['type']:
        print(json.dumps(event, indent=2))

```

    Transaction hash: 6B270C67F431BCBF2D7D8C67B4D953ACD81DCA6667A1A1140F1AC6BBAF658B04


    ['{"height":"364","txhash":"6B270C67F431BCBF2D7D8C67B4D953ACD81DCA6667A1A1140F1AC6BBAF658B04","codespace":"","code":0,"data":"12310A2F2F6479736F6E70726F746F636F6C2E6E616D65736572766963652E76312E4D7367436F6D6D6974526573706F6E7365","raw_log":"","logs":[],"info":"","gas_wanted":"200000","gas_used":"42370","tx":null,"timestamp":"","events":[{"type":"tx","attributes":[{"key":"acc_seq","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/95","index":true}]},{"type":"tx","attributes":[{"key":"signature","value":"9ZjkfvQpFPLIf1d5OVrhjP24UrFuex3el5UN3KOF3Txs74bJs2JQXnCuUig6Mqbk3UzJywJay2dDnRGFEEt71g==","index":true}]},{"type":"message","attributes":[{"key":"action","value":"/dysonprotocol.nameservice.v1.MsgCommit","index":true},{"key":"sender","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej","index":true},{"key":"module","value":"nameservice","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"dysonprotocol.nameservice.v1.EventCommitmentCreated","attributes":[{"key":"hexhash","value":"\\"dd61d1b139033b515021d59adf0a38bfce182b3a3cdf024073a545460a44d1ce\\"","index":true},{"key":"msg_index","value":"0","index":true}]}]}']
    Tx error code: 0
    {
      "type": "dysonprotocol.nameservice.v1.EventCommitmentCreated",
      "attributes": [
        {
          "key": "hexhash",
          "value": "\"dd61d1b139033b515021d59adf0a38bfce182b3a3cdf024073a545460a44d1ce\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }


### Reveal Phase

In the second phase, we reveal the actual name and salt to complete the registration process.


```python
[txhash] = ! dysond tx nameservice reveal \
    --name "$name" \
    --salt "$salt" \
    --from alice \
    -y -o json | jq -r .txhash ; sleep 0.01

print(f"Transaction hash: {txhash}")
tx_result = ! dysond query wait-tx $txhash -o json
tx_result = json.loads("".join(tx_result))

print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

for event in tx_result['events']:
    if 'dysonprotocol' in event['type']:
        print(json.dumps(event, indent=2))

```

    Transaction hash: 1D3AE03AB49F77CF9190AE41017455EF61C90BDB1A5EE9153EDD2DE720A0982F


    Tx error code: 0
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
          "value": "\"alice-ri1rr.dys\"",
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
    }
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
          "value": "\"alice-ri1rr.dys\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }


### Verify Name Registration

Let's verify that the name was properly registered by querying the NFT details. Each registered name becomes an NFT in the 'nameservice.dys' class.


```python
! dysond query nft nft "nameservice.dys" "$name" 
```

    {
      "nft": {
        "class_id": "nameservice.dys",
        "id": "alice-ri1rr.dys",
        "uri": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
        "data": {
          "type": "/dysonprotocol.nameservice.v1.NFTData",
          "value": {
            "listed": true,
            "valuation": {
              "denom": "udys",
              "amount": "100"
            },
            "valuation_expiry": "2026-10-01T22:07:52.420291Z",
            "current_bid": {
              "amount": "0"
            }
          }
        }
      }
    }


## Name Destination Management

Setting a destination for a name allows it to resolve to a specific address, enabling service discovery within the Dyson Protocol ecosystem.


```python
[txhash] = ! dysond tx nameservice set-destination \
    --name "$name" \
    --destination "$alice_address" \
    --from alice \
    -y -o json | jq -r .txhash ; sleep 0.01
# Some delay to ensure the transaction is available

print(f"Transaction hash: {txhash}")
tx_result = ! dysond query wait-tx $txhash -o json
tx_result = json.loads("".join(tx_result))

print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

for event in tx_result['events']:
    if 'dysonprotocol' in event['type']:
        print(json.dumps(event, indent=2))

```

    Transaction hash: 748EB5C2D64704D4618FEC1C1EE908A9FC860D0CAF439B3AD8BBAF966E5D97B1


    Tx error code: 0
    {
      "type": "dysonprotocol.nameservice.v1.EventNameDestinationSet",
      "attributes": [
        {
          "key": "destination",
          "value": "\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"",
          "index": true
        },
        {
          "key": "name",
          "value": "\"alice-ri1rr.dys\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }


### Verify Destination Setting

Let's confirm that the destination was correctly set by checking the NFT's URI field, which stores the destination address.


```python
! dysond query nft nft nameservice.dys "$name"
```

    {
      "nft": {
        "class_id": "nameservice.dys",
        "id": "alice-ri1rr.dys",
        "uri": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
        "data": {
          "type": "/dysonprotocol.nameservice.v1.NFTData",
          "value": {
            "listed": true,
            "valuation": {
              "denom": "udys",
              "amount": "100"
            },
            "valuation_expiry": "2026-10-01T22:07:52.420291Z",
            "current_bid": {
              "amount": "0"
            }
          }
        }
      }
    }


# Update your script to serve the DWapp
Use the following command to update the script to serve the DWapp.


```python

[txhash] = ! dysond tx script update --code-path "../examples/simple_wsgi_example.py" \
    --from alice \
    -y -o json --gas 20000000 | jq -r .txhash

print(f"Transaction hash: {txhash}")

```

    Transaction hash: 567345080376D2AB738B638D0126F5173041FFB5BA641EA8D712B3FA8DBE5187



```python
tx_result = ! dysond query wait-tx $txhash -o json
tx_result = json.loads("".join(tx_result))

print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

for event in tx_result['events']:
    if 'dysonprotocol' in event['type']:
        print(json.dumps(event, indent=2))

```

    Tx error code: 0
    {
      "type": "dysonprotocol.script.v1.EventUpdateScript",
      "attributes": [
        {
          "key": "script_address",
          "value": "\"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej\"",
          "index": true
        },
        {
          "key": "version",
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


# Accessing your DWapp

Note that the DWapp is a simple WSGI app that can be accessed at the address of the name you registered.

For example, if you registered the name "alice.dys", you can access the DWapp at "http://alice.dys.localhost:8000"

All requests to the DWapp are queries to the blockchain state, not transactions. So you can't change the state of the blockchain through the DWapp even with a POST request.


```python
[output] = ! dysond config get app api.address
port = output.split(":")[-1].strip("\"")

dwapp_url = f"http://{name}.localhost:{port}"

print(f"=== Making a GET request to your DWapp at '{dwapp_url}' ===")
out = ! curl -s "$dwapp_url/hi?name=bob"
out = "\n".join(out).strip()
print(out)

assert "hi bob" in out, "Expected 'hi bob' in output, got: " + out
assert "Request Method: GET" in out, "Expected 'Request Method: GET' in output, got: " + out

print()
print(f"=== Making a POST request to your DWapp at '{dwapp_url}' ===")
out = ! curl -s -X POST "$dwapp_url/hi" -d "name=bob"
out = "\n".join(out).strip()
print(out)

assert "hi bob" in out, "Expected 'hi bob' in output, got: " + out
assert "Request Method: POST" in out, "Expected 'Request Method: POST' in output, got: " + out
```

    === Making a GET request to your DWapp at 'http://alice-ri1rr.dys.localhost:2317' ===


    hi bob
    
    Request Method: GET
    Query String: name=bob
    Path Info: /hi
    
    === Making a POST request to your DWapp at 'http://alice-ri1rr.dys.localhost:2317' ===


    hi bob
    
    Request Method: POST
    Query String: 
    Path Info: /hi
    Content Type: application/x-www-form-urlencoded
    Content Length: 8


## Name Valuation Management

Names in the system have a value, which act as a starting point for bids when trading names. Let's update the valuation for our name.


```python

new_valuation = "200udys"

[txhash] =! dysond tx nameservice set-valuation \
    --class-id="nameservice.dys" \
    --nft-id="$name" \
    --valuation="$new_valuation" \
    --from=alice \
    -y \
    -o json | jq -r .txhash ; sleep 0.01

print(f"Transaction hash: {txhash}")

```

    Transaction hash: 00F33C3BBCCC08C73DC18C53B371066BC83F0F5F7C6C343165C1A4ED32C8D0D0



```python

tx_result = ! dysond query wait-tx $txhash -o json
tx_result = json.loads("".join(tx_result))

print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

for event in tx_result['events']:
    if 'dysonprotocol' in event['type']:
        print(json.dumps(event, indent=2))

```

    Tx error code: 0
    {
      "type": "dysonprotocol.nameservice.v1.EventNameValuationUpdated",
      "attributes": [
        {
          "key": "name",
          "value": "\"alice-ri1rr.dys\"",
          "index": true
        },
        {
          "key": "new_valuation",
          "value": "{\"denom\":\"udys\",\"amount\":\"200\"}",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }


### Verify Updated Valuation

Let's confirm the updated valuation by querying the NFT data.


```python
! dysond query nft nft "nameservice.dys" "$name" 
```

    {
      "nft": {
        "class_id": "nameservice.dys",
        "id": "alice-ri1rr.dys",
        "uri": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
        "data": {
          "type": "/dysonprotocol.nameservice.v1.NFTData",
          "value": {
            "listed": true,
            "valuation": {
              "denom": "udys",
              "amount": "200"
            },
            "valuation_expiry": "2026-10-01T22:07:52.420291Z",
            "current_bid": {
              "amount": "0"
            }
          }
        }
      }
    }


## NFT Collection Creation

One of the powerful features of the nameservice module is the ability to create NFT collections under your registered name.

### Create Main NFT Class

Let's create a main NFT collection using our registered name as the class ID.


```python
[txhash] = ! dysond tx nameservice save-class \
        --class-id=$name \
        --from=alice \
        --name="Main Collection" \
        --symbol=MAINCOL \
        --description="My Main Collection" \
        --uri=https://example.com/main \
        -y | dysond query wait-tx -o json | jq -r .txhash ; sleep 0.01

print(f"Transaction hash: {txhash}")
tx_result = ! dysond query wait-tx $txhash -o json
tx_result = json.loads("".join(tx_result))

print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

for event in tx_result['events']:
    if 'dysonprotocol' in event['type']:
        print(json.dumps(event, indent=2))

```

    Transaction hash: ED4D6B7921E0C577439012FF184F8AF6596E471BFD8634F65E623F9A6E7971C9


    Tx error code: 0
    {
      "type": "dysonprotocol.nameservice.v1.EventClassSaved",
      "attributes": [
        {
          "key": "class_id",
          "value": "\"alice-ri1rr.dys\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }


### Create a Sub-Collection

We can also create sub-collections under our main collection by using a hierarchical class ID.


```python
subcollection_id = f"{name}/subcollection"
tx = ! dysond tx nameservice save-class --class-id=$subcollection_id --name="Sub Collection" --symbol=SUBCOL --description="My Sub-Collection" --uri=https://example.com/sub --from=alice -y -o json | jq -r .txhash
txhash = tx[0]
print(f"Transaction hash: {txhash}")
tx_result = ! dysond query wait-tx $txhash -o json
tx_result = json.loads("".join(tx_result))

print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

for event in tx_result['events']:
    if 'dysonprotocol' in event['type']:
        print(json.dumps(event, indent=2))

```

    Transaction hash: FB78AE119480B60559FE5992C286C259F150483E3E6D22CE78F822DDCCA452A0


    Tx error code: 0
    {
      "type": "dysonprotocol.nameservice.v1.EventClassSaved",
      "attributes": [
        {
          "key": "class_id",
          "value": "\"alice-ri1rr.dys/subcollection\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }


### View All NFT Classes

Let's view all the NFT classes in the system to confirm our collections were created successfully.


```python
! dysond query nft classes -o json | jq -M
```

    {
      "classes": [
        {
          "id": "alice-ri1rr.dys",
          "name": "Main Collection",
          "symbol": "MAINCOL",
          "description": "My Main Collection",
          "uri": "https://example.com/main",
          "data": {
            "type": "/dysonprotocol.nameservice.v1.NFTClassData",
            "value": {
              "always_listed": true,
              "valuation_fee_pct": "0.01",
              "valuation_period": "8760h0m0s",
              "bid_timeout": "2s",
              "allowed_denoms": [
                "udys"
              ],
              "reject_bid_valuation_fee_percent": "0.03",
              "minimum_bid_percent_increase": "0.01"
            }
          }
        },
        {
          "id": "alice-ri1rr.dys/subcollection",
          "name": "Sub Collection",
          "symbol": "SUBCOL",
          "description": "My Sub-Collection",
          "uri": "https://example.com/sub",
          "data": {
            "type": "/dysonprotocol.nameservice.v1.NFTClassData",
            "value": {
              "always_listed": true,
              "valuation_fee_pct": "0.01",
              "valuation_period": "8760h0m0s",
              "bid_timeout": "2s",
              "allowed_denoms": [
                "udys"
              ],
              "reject_bid_valuation_fee_percent": "0.03",
              "minimum_bid_percent_increase": "0.01"
            }
          }
        },
        {
          "id": "cdgpje.dys",
          "data": {
            "type": "/dysonprotocol.nameservice.v1.NFTClassData",
            "value": {
              "always_listed": true,
              "valuation_fee_pct": "0.01",
              "valuation_period": "8760h0m0s",
              "bid_timeout": "2s",
              "allowed_denoms": [
                "udys"
              ],
              "reject_bid_valuation_fee_percent": "0.03",
              "minimum_bid_percent_increase": "0.01"
            }
          }
        },
        {
          "id": "cxrwmr.dys",
          "data": {
            "type": "/dysonprotocol.nameservice.v1.NFTClassData",
            "value": {
              "always_listed": true,
              "valuation_fee_pct": "0.01",
              "valuation_period": "8760h0m0s",
              "bid_timeout": "2s",
              "allowed_denoms": [
                "udys"
              ],
              "reject_bid_valuation_fee_percent": "0.03",
              "minimum_bid_percent_increase": "0.01"
            }
          }
        },
        {
          "id": "dkgwxd.dys/col",
          "data": {
            "type": "/dysonprotocol.nameservice.v1.NFTClassData",
            "value": {
              "always_listed": true,
              "valuation_fee_pct": "0.01",
              "valuation_period": "8760h0m0s",
              "bid_timeout": "2s",
              "allowed_denoms": [
                "udys"
              ],
              "reject_bid_valuation_fee_percent": "0.03",
              "minimum_bid_percent_increase": "0.01"
            }
          }
        },
        {
          "id": "fpbpjo.dys",
          "data": {
            "type": "/dysonprotocol.nameservice.v1.NFTClassData",
            "value": {
              "always_listed": true,
              "valuation_fee_pct": "0.01",
              "valuation_period": "8760h0m0s",
              "bid_timeout": "2s",
              "allowed_denoms": [
                "udys"
              ],
              "reject_bid_valuation_fee_percent": "0.03",
              "minimum_bid_percent_increase": "0.01"
            }
          }
        },
        {
          "id": "nameservice.dys",
          "name": "Dyson Names",
          "symbol": "DYSNAME",
          "description": "Dyson Protocol registered names",
          "data": {
            "type": "/dysonprotocol.nameservice.v1.NFTClassData",
            "value": {
              "always_listed": true,
              "valuation_fee_pct": "0.01",
              "valuation_period": "8760h0m0s",
              "bid_timeout": "2s",
              "allowed_denoms": [
                "udys"
              ],
              "reject_bid_valuation_fee_percent": "0.03",
              "minimum_bid_percent_increase": "0.01"
            }
          }
        },
        {
          "id": "qmmwrg.dys/col",
          "data": {
            "type": "/dysonprotocol.nameservice.v1.NFTClassData",
            "value": {
              "always_listed": true,
              "valuation_fee_pct": "0.01",
              "valuation_period": "8760h0m0s",
              "bid_timeout": "100ms",
              "allowed_denoms": [
                "udys"
              ],
              "reject_bid_valuation_fee_percent": "0.03",
              "minimum_bid_percent_increase": "0.01"
            }
          }
        },
        {
          "id": "smixrg.dys/col",
          "data": {
            "type": "/dysonprotocol.nameservice.v1.NFTClassData",
            "value": {
              "always_listed": true,
              "valuation_fee_pct": "0.01",
              "valuation_period": "8760h0m0s",
              "bid_timeout": "2s",
              "allowed_denoms": [
                "udys"
              ],
              "reject_bid_valuation_fee_percent": "0.03",
              "minimum_bid_percent_increase": "0.01"
            }
          }
        },
        {
          "id": "stolsz.dys/col",
          "data": {
            "type": "/dysonprotocol.nameservice.v1.NFTClassData",
            "value": {
              "always_listed": true,
              "valuation_fee_pct": "0.01",
              "valuation_period": "8760h0m0s",
              "bid_timeout": "2s",
              "allowed_denoms": [
                "udys"
              ],
              "reject_bid_valuation_fee_percent": "0.03",
              "minimum_bid_percent_increase": "0.01"
            }
          }
        },
        {
          "id": "whaleswap.dys/auction/udys",
          "name": "Whaleswap Auction",
          "symbol": "WSA",
          "description": "Auction class for escrowed solid coins",
          "data": {
            "type": "/dysonprotocol.nameservice.v1.NFTClassData",
            "value": {
              "always_listed": true,
              "valuation_fee_pct": "0",
              "valuation_period": "1h0m0s",
              "bid_timeout": "5s",
              "allowed_denoms": [
                "udys"
              ],
              "reject_bid_valuation_fee_percent": "0.03",
              "minimum_bid_percent_increase": "0"
            }
          }
        }
      ],
      "pagination": {
        "total": "11"
      }
    }


## NFT Minting

Now that we have created NFT collections, let's mint some NFTs within these collections.


```python
# Mint an NFT in the main collection
nft_id = "nft1"
tx_result = ! dysond tx nameservice mint-nft \
    --class-id=$name \
    --nft-id=$nft_id \
    --uri=https://example.com/nft1 \
    --from=alice \
    -y \
    -o json | dysond q wait-tx -o json

tx_result = json.loads("".join(tx_result))

print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

for event in tx_result['events']:
    if 'dysonprotocol' in event['type']:
        print(json.dumps(event, indent=2))

```

    Tx error code: 0
    {
      "type": "dysonprotocol.nft.v1beta1.EventMint",
      "attributes": [
        {
          "key": "class_id",
          "value": "\"alice-ri1rr.dys\"",
          "index": true
        },
        {
          "key": "id",
          "value": "\"nft1\"",
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
    }
    {
      "type": "dysonprotocol.nameservice.v1.EventNFTMinted",
      "attributes": [
        {
          "key": "class_id",
          "value": "\"alice-ri1rr.dys\"",
          "index": true
        },
        {
          "key": "nft_id",
          "value": "\"nft1\"",
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
# Mint an NFT in the sub-collection
subnft_id = f"subnft1-{random_string(5)}"
tx = ! dysond tx nameservice mint-nft --class-id=$subcollection_id --nft-id=$subnft_id --uri=https://example.com/subnft1 --from=alice -y -o json | jq -r .txhash
txhash = tx[0]
print(f"Transaction hash: {txhash}")
tx_result = ! dysond query wait-tx $txhash -o json
tx_result = json.loads("".join(tx_result))

print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

for event in tx_result['events']:
    if 'dysonprotocol' in event['type']:
        print(json.dumps(event, indent=2))

```

    Transaction hash: 0195153B7F1FB4E5D7BA43975D0D92DB2AC31CA3A59F54F00319CD324D0775C7


    Tx error code: 0
    {
      "type": "dysonprotocol.nft.v1beta1.EventMint",
      "attributes": [
        {
          "key": "class_id",
          "value": "\"alice-ri1rr.dys/subcollection\"",
          "index": true
        },
        {
          "key": "id",
          "value": "\"subnft1-9kyid\"",
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
    }
    {
      "type": "dysonprotocol.nameservice.v1.EventNFTMinted",
      "attributes": [
        {
          "key": "class_id",
          "value": "\"alice-ri1rr.dys/subcollection\"",
          "index": true
        },
        {
          "key": "nft_id",
          "value": "\"subnft1-9kyid\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }


### View NFTs in Collection

Let's verify the NFTs in our main collection.


```python
! dysond query nft nfts $name -o json | jq -M
```

    {
      "nfts": [
        {
          "class_id": "alice-ri1rr.dys",
          "id": "nft1",
          "uri": "https://example.com/nft1",
          "data": {
            "type": "/dysonprotocol.nameservice.v1.NFTData",
            "value": {
              "valuation": {
                "amount": "0"
              },
              "valuation_expiry": "2026-10-01T22:07:59.551529Z",
              "current_bid": {
                "amount": "0"
              }
            }
          }
        }
      ],
      "pagination": {
        "total": "1"
      }
    }


# Verify the NFTs in the sub-collection



```python
! dysond query nft nfts $subcollection_id -o json | jq -M
```

    {
      "nfts": [
        {
          "class_id": "alice-ri1rr.dys/subcollection",
          "id": "subnft1-9kyid",
          "uri": "https://example.com/subnft1",
          "data": {
            "type": "/dysonprotocol.nameservice.v1.NFTData",
            "value": {
              "valuation": {
                "amount": "0"
              },
              "valuation_expiry": "2026-10-01T22:08:00.172152Z",
              "current_bid": {
                "amount": "0"
              }
            }
          }
        }
      ],
      "pagination": {
        "total": "1"
      }
    }


## NFT Metadata Management

NFTs can have additional text metadata to describe their properties and attributes. Let's add metadata to our NFT.


```python
import json
import shlex

# Set metadata for the NFT, note that the metadata should be escaped for the shell

metadata = shlex.quote(json.dumps({"some_key":"some_value", "another_key": "He doesn't eat his vegetables"}))
print(f"Metadata: {metadata}")
print(f"Alice address: {alice_address}")

tx = ! dysond tx nameservice set-nft-metadata \
    --from=$alice_address \
    --class-id="$name" \
    --nft-id="$nft_id" \
    --metadata=$metadata \
    -y \
    -o json | jq .txhash -r ; sleep 0.01

txhash = tx[0]
print(f"Transaction hash: {txhash}")
```

    Metadata: '{"some_key": "some_value", "another_key": "He doesn'"'"'t eat his vegetables"}'
    Alice address: dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej


    Transaction hash: C8CDEFFC545E508D5A8659C974FD63BD47B8A0AC5288A11E7EF3B50FBFB5660A



```python
tx_result = ! dysond query wait-tx "$txhash" -o json
tx_result = "".join(tx_result)
print("".join(tx_result))
tx_result = json.loads(tx_result)
print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

# Verify the NFT with metadata
! dysond query nft nft $name $nft_id
```

    {"height":"379","txhash":"C8CDEFFC545E508D5A8659C974FD63BD47B8A0AC5288A11E7EF3B50FBFB5660A","codespace":"","code":0,"data":"12390A372F6479736F6E70726F746F636F6C2E6E616D65736572766963652E76312E4D73675365744E46544D65746164617461526573706F6E7365","raw_log":"","logs":[],"info":"","gas_wanted":"200000","gas_used":"55824","tx":null,"timestamp":"","events":[{"type":"tx","attributes":[{"key":"acc_seq","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/104","index":true}]},{"type":"tx","attributes":[{"key":"signature","value":"2D8p1zAiCJbuq7RvfJMsPapkrQOEIVJbxaqSiaRnAUA7RXd9YpSWNKDCzizKiOf3TxhzZFyBeB0XZNbx7F3drg==","index":true}]},{"type":"message","attributes":[{"key":"action","value":"/dysonprotocol.nameservice.v1.MsgSetNFTMetadata","index":true},{"key":"sender","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej","index":true},{"key":"module","value":"nameservice","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"dysonprotocol.nameservice.v1.EventNFTMetadataUpdated","attributes":[{"key":"class_id","value":"\"alice-ri1rr.dys\"","index":true},{"key":"nft_id","value":"\"nft1\"","index":true},{"key":"msg_index","value":"0","index":true}]}]}
    Tx error code: 0


    {
      "nft": {
        "class_id": "alice-ri1rr.dys",
        "id": "nft1",
        "data": {
          "type": "/dysonprotocol.nameservice.v1.NFTData",
          "value": {
            "valuation": {
              "amount": "0"
            },
            "valuation_expiry": "2026-10-01T22:07:59.551529Z",
            "current_bid": {
              "amount": "0"
            },
            "metadata": "{\"some_key\": \"some_value\", \"another_key\": \"He doesn't eat his vegetables\"}"
          }
        }
      }
    }


### Add Extra Data to NFT Class

We can also add additional data to the NFT class itself to provide more information about the collection.


```python
# Set extra data for the NFT class

extra_data = shlex.quote(json.dumps({"website":"https://example.com/details"}))

tx = ! dysond tx nameservice set-nft-class-extra-data --class-id=$name --extra-data=$extra_data --from=alice -y -o json | jq -r .txhash
txhash = tx[0]
print(f"Transaction hash: {txhash}")
tx_result = ! dysond query wait-tx $txhash -o json
tx_result = json.loads("".join(tx_result))
print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

# Verify the NFT class with extra data
print("NFT class with new extra data:")
! dysond query nft class $name -o json
```

    Transaction hash: 6E11618283BDF299B9CF07520A048993ED92E988748CA1DFC23FFC11C343BE2E


    Tx error code: 0
    NFT class with new extra data:


    {
      "class": {
        "id": "alice-ri1rr.dys",
        "name": "Main Collection",
        "symbol": "MAINCOL",
        "description": "My Main Collection",
        "uri": "https://example.com/main",
        "data": {
          "type": "/dysonprotocol.nameservice.v1.NFTClassData",
          "value": {
            "always_listed": true,
            "valuation_fee_pct": "0.01",
            "extra_data": "{\"website\": \"https://example.com/details\"}",
            "valuation_period": "8760h0m0s",
            "bid_timeout": "2s",
            "allowed_denoms": [
              "udys"
            ],
            "reject_bid_valuation_fee_percent": "0.03",
            "minimum_bid_percent_increase": "0.01"
          }
        }
      }
    }


## Custom Coin Operations

Dyson Protocol allows name owners to mint custom coins using their registered names as denominations.

### Mint Coins with Name Denomination

Let's mint some coins using our registered name as the denomination.


```python
# Mint coins with the name as denomination
amount = f"1000{name}"
tx = ! dysond tx nameservice mint-coins --amount=$amount --mint-fee 10udys --from=alice -y -o json | jq -r .txhash
txhash = tx[0]
print(f"Transaction hash: {txhash}")
tx_result = ! dysond query wait-tx $txhash -o json
tx_result = json.loads("".join(tx_result))

print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

for event in tx_result['events']:
    if 'dysonprotocol' in event['type']:
        print(json.dumps(event, indent=2))

```

    Transaction hash: 7D731B5B117BD12EB2542653AB5C3BC24E394CB970239CA6282A751B3A9DF775


    Tx error code: 0
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


### Mint Coins with Subdenom

We can also mint coins with subdenominations for more specific token creation.


```python
# Mint coins with a subdenom
subdenom = f"{name}/token1"
amount = f"500{subdenom}"
tx = ! dysond tx nameservice mint-coins --amount=$amount --mint-fee 5udys --from=alice -y -o json | jq -r .txhash
txhash = tx[0]
print(f"Transaction hash: {txhash}")
tx_result = ! dysond query wait-tx $txhash -o json
tx_result = json.loads("".join(tx_result))

print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

for event in tx_result['events']:
    if 'dysonprotocol' in event['type']:
        print(json.dumps(event, indent=2))

```

    Transaction hash: 8B1A0010DC6F3FCCCD267F98EF6692C88748D9B614C7BCFDA7158E8ED0F6BB20


    Tx error code: 0
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


### Check Balance

Let's check Alice's balance to confirm the minted coins have been added to her account.


```python
! dysond query bank balances $alice_address -o json | jq -M
```

    {
      "balances": [
        {
          "denom": "alice-ri1rr.dys",
          "amount": "1000"
        },
        {
          "denom": "alice-ri1rr.dys/token1",
          "amount": "500"
        },
        {
          "denom": "udys",
          "amount": "9886648815"
        }
      ],
      "pagination": {
        "total": "3"
      }
    }


### Transfer Custom Coins

Now that we have minted custom coins, let's send some to Bob's account.


```python
# Send custom coins to Bob
transfer_amount = f"200{name}"
tx = ! dysond tx bank send alice $bob_address $transfer_amount -y -o json | jq -r .txhash
txhash = tx[0]
print(f"Transaction hash: {txhash}")
tx_result = ! dysond query wait-tx $txhash -o json
tx_result = json.loads("".join(tx_result))

print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

for event in tx_result['events']:
    if 'dysonprotocol' in event['type']:
        print(json.dumps(event, indent=2))

```

    Transaction hash: D94C5355479FBFC8F23C6775647CAD80B52E4E3045818591109F556E5AF06089


    Tx error code: 0


### Verify Bob's Balance

Let's check Bob's balance to confirm the transfer was successful.


```python
! dysond query bank balances $bob_address -o json | jq
```

    [1;39m{
      [0m[1;34m"balances"[0m[1;39m: [0m[1;39m[
        [1;39m{
          [0m[1;34m"denom"[0m[1;39m: [0m[0;32m"alice-ri1rr.dys"[0m[1;39m,
          [0m[1;34m"amount"[0m[1;39m: [0m[0;32m"200"[0m[1;39m
        [1;39m}[0m[1;39m,
        [1;39m{
          [0m[1;34m"denom"[0m[1;39m: [0m[0;32m"udys"[0m[1;39m,
          [0m[1;34m"amount"[0m[1;39m: [0m[0;32m"10000000000"[0m[1;39m
        [1;39m}[0m[1;39m
      [1;39m][0m[1;39m,
      [0m[1;34m"pagination"[0m[1;39m: [0m[1;39m{
        [0m[1;34m"total"[0m[1;39m: [0m[0;32m"2"[0m[1;39m
      [1;39m}[0m[1;39m
    [1;39m}[0m


## Name Trading Process

The Nameservice module allows names to be traded through a secure bidding system. Let's demonstrate how Bob can bid on Alice's name.


```python
print(f"Bob places a bid on Alice's name: {name}")

current_bid_result = ! dysond query nft nft nameservice.dys $name -o json 
current_bid_result = json.loads("".join(current_bid_result))
print(f"Current bid result: {current_bid_result}")
current_bid = current_bid_result['nft']['data']['value']['current_bid']

current_valuation = current_bid_result['nft']['data']['value']['valuation']

print(f"Current bid: {current_bid}") # Current bid: {'amount': '0'}
print(f"Current valuation: {current_valuation}") # Current valuation: {'amount': '100'}


min_bid_amount = max(int(current_bid['amount']) + 100, int(current_valuation['amount'])) 
bid_amount = f"{min_bid_amount}udys"
print(f"Bob's bid amount: {bid_amount}")
#  dysond tx nameservice place-bid --nft-class-id=<class-id> --nft-id=<nft-id> --bid-amount=<amount> [flags]
[txhash] = ! dysond tx nameservice place-bid \
    --nft-class-id="nameservice.dys" \
    --nft-id=$name \
    --bid-amount=$bid_amount \
    --from=bob \
    -y \
    -o json | jq -r .txhash

print(f"Transaction hash: {txhash}")
tx_result = ! dysond query wait-tx $txhash -o json
tx_result = json.loads("".join(tx_result))

print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

for event in tx_result['events']:
    if 'dysonprotocol' in event['type']:
        print(json.dumps(event, indent=2))

```

    Bob places a bid on Alice's name: alice-ri1rr.dys


    Current bid result: {'nft': {'class_id': 'nameservice.dys', 'id': 'alice-ri1rr.dys', 'uri': 'dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej', 'data': {'type': '/dysonprotocol.nameservice.v1.NFTData', 'value': {'listed': True, 'valuation': {'denom': 'udys', 'amount': '200'}, 'valuation_expiry': '2026-10-01T22:07:52.420291Z', 'current_bid': {'amount': '0'}}}}}
    Current bid: {'amount': '0'}
    Current valuation: {'denom': 'udys', 'amount': '200'}
    Bob's bid amount: 200udys


    Transaction hash: ED23853073AC8AE1CC559F559A9F3A28ACF3335DF669EF02FD5B413D8F3BC348


    Tx error code: 0
    {
      "type": "dysonprotocol.nameservice.v1.EventBidPlaced",
      "attributes": [
        {
          "key": "bid_amount",
          "value": "{\"denom\":\"udys\",\"amount\":\"200\"}",
          "index": true
        },
        {
          "key": "bidder",
          "value": "\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\"",
          "index": true
        },
        {
          "key": "class_id",
          "value": "\"nameservice.dys\"",
          "index": true
        },
        {
          "key": "nft_id",
          "value": "\"alice-ri1rr.dys\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }


### Verify Current Bid

Let's check the current bid on the name.


```python
! dysond query nft nft nameservice.dys $name -o json | jq -M '.nft.data.value.current_bid' 
```

    {
      "denom": "udys",
      "amount": "200"
    }


### Accept Bid

Alice can choose to accept Bob's bid, which will transfer the name to Bob and the bid amount to Alice.


```python
# Alice accepts Bob's bid
#   dysond tx nameservice accept-bid --nft-class-id=<class-id> --nft-id=<nft-id> [flags]

tx = ! dysond tx nameservice accept-bid \
    --nft-class-id="nameservice.dys" \
    --nft-id=$name \
    --from=alice \
    -y \
    -o json | jq -r .txhash

txhash = tx[0]

print(f"Transaction hash: {txhash}")
tx_result = ! dysond query wait-tx $txhash -o json
tx_result = json.loads("".join(tx_result))

print(f"Tx error code: {tx_result['code']}")
assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"

for event in tx_result['events']:
    if 'dysonprotocol' in event['type']:
        print(json.dumps(event, indent=2))

```

    Transaction hash: E1B066741D8ED9BDCD326AB3383B4F73A2D1888465BEC6F21BE45DC90C70541B


    Tx error code: 0
    {
      "type": "dysonprotocol.nameservice.v1.EventBidAccepted",
      "attributes": [
        {
          "key": "class_id",
          "value": "\"nameservice.dys\"",
          "index": true
        },
        {
          "key": "new_owner",
          "value": "\"dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el\"",
          "index": true
        },
        {
          "key": "nft_id",
          "value": "\"alice-ri1rr.dys\"",
          "index": true
        },
        {
          "key": "msg_index",
          "value": "0",
          "index": true
        }
      ]
    }


### Verify Name Ownership

Let's verify that the name has been transferred to Bob.


```python
out = ! dysond keys show bob -a
bob_address = "\n".join(out).strip()
print(f"Bob's address: {out}")

out = ! dysond query nft owner nameservice.dys $name -o json | jq 
out = "\n".join(out).strip()
nft_owner_data = json.loads(out)
nft_owner = nft_owner_data['owner']
print(nft_owner)

assert nft_owner == bob_address, "Expected 'alice' in output, got: " + nft_owner
```

    Bob's address: ['dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el']


    dys21fhhxp9xveswc4yhxekr32eqe80rkwpur3vu0el


## Conclusion

This guide has demonstrated the key features of the Dyson Protocol Nameservice Module. We've covered:

1. Name registration through a commit-reveal process
2. Setting name destinations for resolution
3. Creating NFT collections and minting NFTs
4. Managing metadata for NFTs and collections
5. Minting custom coins with name-based denominations
6. Trading names through a bidding system

These capabilities enable a powerful decentralized namespace system that integrates with NFTs and custom tokens, forming a foundation for various applications on the Dyson Protocol blockchain.
