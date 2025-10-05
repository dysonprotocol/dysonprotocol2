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
dysond init your_node_name
dysond join https://dys-testnet2.dysonprotocol.com/rpc
```

### Create new accounts
```bash
export NAME="my_name"
dysond keys add $NAME
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

