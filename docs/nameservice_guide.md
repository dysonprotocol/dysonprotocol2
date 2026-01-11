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
        "max_valuation_period": "8760h0m0s",
        "name_suffix": ".dys"
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

    Name: alice-6hrlb.dys
    Salt: tw3ya7ce75lp2oy0y9bk


### Compute Hash for Commitment

Now, we'll compute a hash using the name, salt, and committer address. This hash will be used in the commitment phase.


```python
[name_commit_hex_hash] = ! dysond query nameservice compute-hash \
    --name "$name" \
    --salt "$salt" \
    --committer "$alice_address"  -o json| jq '.hex_hash' -r
print(f"Hex Hash: {name_commit_hex_hash}")
```

    Hex Hash: 0f36d6942df91ba5dbc684fc8c34c3534a23f69b7b721209389edf6397c6b075


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
tx_result = ! dysond query wait-tx $txhash -o json
tx_result = json.loads("".join(tx_result))

assert tx_result['code'] == 0, f"Tx failed with code {tx_result['code']}, {tx_result['raw_log']}"
print(f"Tx error code: {tx_result['code']}")

for event in tx_result['events']:
    if 'dysonprotocol' in event['type']:
        print(json.dumps(event, indent=2))

```

    Transaction hash: 8A63751AA763591659C1D6318480153DEAB29AF213B173F8C7732F8EDC053457


    Tx error code: 0
    {
      "type": "dysonprotocol.nameservice.v1.EventCommitmentCreated",
      "attributes": [
        {
          "key": "hexhash",
          "value": "\"0f36d6942df91ba5dbc684fc8c34c3534a23f69b7b721209389edf6397c6b075\"",
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

    Transaction hash: B15A65BC7F726D25C08F21C74BDE5FFAED4F977A5EBEF4AA93CEC04DDEB6229B


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
          "value": "\"alice-6hrlb.dys\"",
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
          "value": "\"alice-6hrlb.dys\"",
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
        "id": "alice-6hrlb.dys",
        "uri": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
        "data": {
          "type": "/dysonprotocol.nameservice.v1.NFTData",
          "value": {
            "listed": true,
            "valuation": {
              "denom": "udys",
              "amount": "100"
            },
            "valuation_expiry": "2026-12-27T13:59:43.162602Z",
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

    Transaction hash: B9C2805C79756E5E47A58D4C50112D66C82A4E26B9AC6CC8B01B22BEFABAF713


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
          "value": "\"alice-6hrlb.dys\"",
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
        "id": "alice-6hrlb.dys",
        "uri": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
        "data": {
          "type": "/dysonprotocol.nameservice.v1.NFTData",
          "value": {
            "listed": true,
            "valuation": {
              "denom": "udys",
              "amount": "100"
            },
            "valuation_expiry": "2026-12-27T13:59:43.162602Z",
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

    Transaction hash: D5728629DEAF20914B5DC7B650250C20A7F04FC242F74A9F0C2BB16B8980870F



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

    === Making a GET request to your DWapp at 'http://alice-6hrlb.dys.localhost:3317' ===


    hi bob
    
    Request Method: GET
    Query String: name=bob
    Path Info: /hi
    
    === Making a POST request to your DWapp at 'http://alice-6hrlb.dys.localhost:3317' ===


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

    Transaction hash: 8734E091DCDB63DADD2F2023D7F53C52D2C1476DF77479DD6038F4F2A4AF8C16



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
          "value": "\"alice-6hrlb.dys\"",
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
        "id": "alice-6hrlb.dys",
        "uri": "dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej",
        "data": {
          "type": "/dysonprotocol.nameservice.v1.NFTData",
          "value": {
            "listed": true,
            "valuation": {
              "denom": "udys",
              "amount": "200"
            },
            "valuation_expiry": "2026-12-27T13:59:43.162602Z",
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

    Transaction hash: B617547EC9E6261A529035C79D5C5FBDE30CA1D60D9C94C57D9D0E8346A9CE67


    Tx error code: 0
    {
      "type": "dysonprotocol.nameservice.v1.EventClassSaved",
      "attributes": [
        {
          "key": "class_id",
          "value": "\"alice-6hrlb.dys\"",
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
tx = ! dysond tx nameservice save-class --class-id=$subcollection_id --name="Sub Collection" --symbol=SUBCOL --description="My Sub-Collection" --uri=https://example.com/sub --from=alice -y -o json | jq -r .txhash ; sleep 0.01
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

    Transaction hash: 447C688ADDE64090035872B22BE0C19E40A798F5CE647035A569E612D71DA623


    Tx error code: 0
    {
      "type": "dysonprotocol.nameservice.v1.EventClassSaved",
      "attributes": [
        {
          "key": "class_id",
          "value": "\"alice-6hrlb.dys/subcollection\"",
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
          "id": "alice-6hrlb.dys",
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
          "id": "alice-6hrlb.dys/subcollection",
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
          "id": "nameservice.dys",
          "name": "DYS Names",
          "symbol": "DYSNAME",
          "description": "DYS Protocol registered names",
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
        }
      ],
      "pagination": {
        "total": "3"
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
          "value": "\"alice-6hrlb.dys\"",
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
          "value": "\"alice-6hrlb.dys\"",
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

    Transaction hash: 44B1F461A2FCA1ACD2339827350F899DCC9E64F62C8CDAAA567EA6A83D0D5F06


    Tx error code: 0
    {
      "type": "dysonprotocol.nft.v1beta1.EventMint",
      "attributes": [
        {
          "key": "class_id",
          "value": "\"alice-6hrlb.dys/subcollection\"",
          "index": true
        },
        {
          "key": "id",
          "value": "\"subnft1-n1zaz\"",
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
          "value": "\"alice-6hrlb.dys/subcollection\"",
          "index": true
        },
        {
          "key": "nft_id",
          "value": "\"subnft1-n1zaz\"",
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
          "class_id": "alice-6hrlb.dys",
          "id": "nft1",
          "uri": "https://example.com/nft1",
          "data": {
            "type": "/dysonprotocol.nameservice.v1.NFTData",
            "value": {
              "valuation": {
                "amount": "0"
              },
              "valuation_expiry": "2026-12-27T13:59:47.064267Z",
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
          "class_id": "alice-6hrlb.dys/subcollection",
          "id": "subnft1-n1zaz",
          "uri": "https://example.com/subnft1",
          "data": {
            "type": "/dysonprotocol.nameservice.v1.NFTData",
            "value": {
              "valuation": {
                "amount": "0"
              },
              "valuation_expiry": "2026-12-27T13:59:47.350625Z",
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


    Transaction hash: 852FDC6BD3F89B0A12245CE73B2A27915DE62B1A6C9D997428CB9E566A15C39E



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

    {"height":"32","txhash":"852FDC6BD3F89B0A12245CE73B2A27915DE62B1A6C9D997428CB9E566A15C39E","codespace":"","code":0,"data":"12390A372F6479736F6E70726F746F636F6C2E6E616D65736572766963652E76312E4D73675365744E46544D65746164617461526573706F6E7365","raw_log":"","logs":[],"info":"","gas_wanted":"200000","gas_used":"57346","tx":null,"timestamp":"","events":[{"type":"tx","attributes":[{"key":"acc_seq","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej/9","index":true}]},{"type":"tx","attributes":[{"key":"signature","value":"8dYAH6XgvBy4CEuhOf8mKf52hYI9byCjnxwcg9C6DnlOu02HEAYpgtTkgbwHTaelck0WR0poUNoY3VR577pddQ==","index":true}]},{"type":"message","attributes":[{"key":"action","value":"/dysonprotocol.nameservice.v1.MsgSetNFTMetadata","index":true},{"key":"sender","value":"dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej","index":true},{"key":"module","value":"nameservice","index":true},{"key":"msg_index","value":"0","index":true}]},{"type":"dysonprotocol.nameservice.v1.EventNFTMetadataUpdated","attributes":[{"key":"class_id","value":"\"alice-6hrlb.dys\"","index":true},{"key":"nft_id","value":"\"nft1\"","index":true},{"key":"msg_index","value":"0","index":true}]}]}
    Tx error code: 0


    {
      "nft": {
        "class_id": "alice-6hrlb.dys",
        "id": "nft1",
        "data": {
          "type": "/dysonprotocol.nameservice.v1.NFTData",
          "value": {
            "valuation": {
              "amount": "0"
            },
            "valuation_expiry": "2026-12-27T13:59:47.064267Z",
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

    Transaction hash: 0832E4088488C8521696AC1EE93F12073E8432FFF18E45ACDCBD58EC29B3F09E


    Tx error code: 0
    NFT class with new extra data:


    {
      "class": {
        "id": "alice-6hrlb.dys",
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

    Transaction hash: D1B00E044E52661A65320FE28DFB9D0DBDC34E6E4C4E41BFE801F9C5B3E26B77


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

    Transaction hash: 35F80A286033DD3DD38BFDECD21EF382F5F8161A4174B8EE8DBE70CBFFC46A9B


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
          "denom": "alice-6hrlb.dys",
          "amount": "1000"
        },
        {
          "denom": "alice-6hrlb.dys/token1",
          "amount": "500"
        },
        {
          "denom": "udys",
          "amount": "9999999984"
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

    Transaction hash: 640BDB1458F7D6BA15A51111988F134F22E0F331C04AE91C89E1D2CAEA5F578D

    


    Tx error code: 0


### Verify Bob's Balance

Let's check Bob's balance to confirm the transfer was successful.


```python
! dysond query bank balances $bob_address -o json | jq
```

    [1;39m{
      [0m[1;34m"balances"[0m[1;39m: [0m[1;39m[
        [1;39m{
          [0m[1;34m"denom"[0m[1;39m: [0m[0;32m"alice-6hrlb.dys"[0m[1;39m,
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

    Bob places a bid on Alice's name: alice-6hrlb.dys


    Current bid result: {'nft': {'class_id': 'nameservice.dys', 'id': 'alice-6hrlb.dys', 'uri': 'dys21tvhkv3gqr90jpycaky02xa5ukhaxllu3jlwnej', 'data': {'type': '/dysonprotocol.nameservice.v1.NFTData', 'value': {'listed': True, 'valuation': {'denom': 'udys', 'amount': '200'}, 'valuation_expiry': '2026-12-27T13:59:43.162602Z', 'current_bid': {'amount': '0'}}}}}
    Current bid: {'amount': '0'}
    Current valuation: {'denom': 'udys', 'amount': '200'}
    Bob's bid amount: 200udys


    Transaction hash: 7DC723F3F5BD9BE444DD8616B5741C5D9A47404448794425D89ECBC1C21B0084


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
          "value": "\"alice-6hrlb.dys\"",
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

    Transaction hash: 43E62D868E5F8585E90B47A5253B3E14878BE6C6AA275FEDBB776C6D1B00A480


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
          "value": "\"alice-6hrlb.dys\"",
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


## Denom Metadata Management

The Nameservice module provides governance-controlled denom metadata management for custom tokens created through name-based denominations.

### Setting Denom Metadata

Governance can set comprehensive metadata for custom denominations, including display names, symbols, descriptions, and denomination units. This enables rich token metadata for name-based coins.

```python
# Set comprehensive metadata for a custom denom
denom_metadata = {
    "base": name,  # The full denom name (e.g., "alice-token.dys")
    "display": base_name,  # Display name (e.g., "alice-token")
    "symbol": symbol_name,  # Symbol (e.g., "ALICE-TOKEN")
    "name": "Alice's Custom Token",  # Human-readable name
    "description": "A custom token created by Alice using Dyson Protocol nameservice",
    "uri": "https://alice-tokens.example.com/metadata",
    "uri_hash": "",
    "denom_units": [
        {
            "denom": name,  # Base unit (full denom)
            "exponent": 0,
            "aliases": []
        },
        {
            "denom": base_name,  # Display unit
            "exponent": 6,  # 6 decimal places
            "aliases": []
        }
    ]
}

# Only governance can set denom metadata
[txhash] = ! dysond tx nameservice set-denom-metadata \
    --authority "$gov_addr" \
    --metadata "$denom_metadata" \
    --from gov \
    -y -o json | jq -r .txhash

print(f"Transaction hash: {txhash}")
tx_result = ! dysond query wait-tx $txhash -o json
tx_result = json.loads("".join(tx_result))

assert tx_result['code'] == 0, f"Tx failed: {tx_result['raw_log']}"
```


# Verify metadata was set
```bash
dysond query bank denom-metadata "$name" -o json | jq
```

The denom metadata includes:
- **Base**: The full denomination string (required)
- **Display**: Human-readable display name
- **Symbol**: Token symbol for exchanges
- **Name**: Full token name
- **Description**: Detailed token description
- **URI**: Link to additional metadata or logo
- **Denom Units**: Conversion rates between base and display units

This metadata enhances the usability of custom tokens by providing rich information for wallets, exchanges, and dApps.

## Conclusion

This guide has demonstrated the key features of the Dyson Protocol Nameservice Module. We've covered:

1. Name registration through a commit-reveal process
2. Setting name destinations for resolution
3. Creating NFT collections and minting NFTs
4. Managing metadata for NFTs and collections
5. Minting custom coins with name-based denominations
6. Setting comprehensive denom metadata for custom tokens
7. Trading names through a bidding system

These capabilities enable a powerful decentralized namespace system that integrates with NFTs and custom tokens, forming a foundation for various applications on the Dyson Protocol blockchain.
