# Dyson Protocol – Make Dwapps, Get Paid


## Installation

### Build the dysvm dependencies

This only needs to be done once.

```bash
make dysvm 
```

### Build the Dyson Protocol binary

This needs to be done everytime you pull the latest changes.

```bash
make install
```

### Join the testnet

Initialize your node and join the Dyson Protocol testnet:

```bash
dysond join https://dys-testnet2.dysonprotocol.com/rpc
dysond start
```

### Create new accounts

In a different terminal, create a new account:

```bash
export NAME="my_name"
dysond keys add $NAME
```

### Become a validator

Make sure your node is fully synced and you have funds in your key.

1) Export your key name and addresses

```bash
export NAME="my_name"
export DELEGATOR=$(dysond keys show $NAME -a)
export VALOPER=$(dysond keys show $NAME --bech val -a)
```

2) Get your validator pubkey

```bash
# Newer SDKs use `comet`; older use `tendermint`. Either works on this binary.
dysond comet show-validator > validator-pubkey.json || dysond tendermint show-validator > validator-pubkey.json
```

3) Create a `validator.json` message

```bash
cat > validator.json <<EOF
{
  "pubkey": $(cat validator-pubkey.json),
  "amount": "1udys",
  "moniker": "my-validator-name",
  "identity": "my-identity",
  "website": "https://example.com",
  "security": "my-security-contact",
  "details": "Dyson Protocol validator",
  "commission-rate": "0.10",
  "commission-max-rate": "0.20",
  "commission-max-change-rate": "0.05",
  "min-self-delegation": "1"
}
EOF
```

4) Create the validator

```bash
dysond tx staking create-validator validator.json --from $NAME --gas auto
```

5) Verify your validator

```bash
dysond query staking validator $VALOPER
```

6) (Optional) Delegate more stake later

```bash
dysond tx staking delegate $VALOPER 5000000udys --from $NAME --gas auto
```


## More Documentation

For more detailed information about specific modules, please refer to the following documentation:

- [Bank Guide](docs/bank_guide.md)
- [Crontask Guide](docs/crontask_guide.md)
- [Dyslang Guide](docs/dyslang_guide.md)
- [Nameservice Guide](docs/nameservice_guide.md)
- [Scripting Guide](docs/scripting_guide.md)
- [Staking Guide](docs/staking_guide.md)
- [Storage Guide](docs/storage_guide.md)

## Examples

 - [Examples](examples/)
 - [Ast Explorer](examples/ast_explorer.py)
 - [Balance Example](examples/balance_example.py)
 - [Crontask Countdown](examples/crontask_countdown.py)
 - [Crontask Schedule Self](examples/crontask_schedule_self.py)
 - [Crontask Script](examples/crontask_script.py)
 - [Dyslang Example](examples/dyslang_example.py)
 - [Dystorrent](examples/dystorrent/)
 - [Exec Other Script](examples/exec_other_script.py)
 - [Ica](examples/ica.py)
 - [Ica E2e](examples/ica_e2e.py)
 - [Script Query Height](examples/script_query_height.py)
 - [Simple Wsgi Example](examples/simple_wsgi_example.py)
 - [Storage Example](examples/storage_example.py)

