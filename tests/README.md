# Dyson Protocol Test Suite

This directory contains the test suite for the Dyson Protocol blockchain.

## Running Tests

To run the entire test suite:

```bash
make test
```

**⚠️ Important**: Never use pipe (`|`) after the `make test` command. Piping can hide important error output and interfere with test execution. Always run `make test` directly without any pipes.

This will:
1. Set up a test environment
2. Initialize a test node
3. Start the node in daemon mode
4. Run all tests with pytest
5. Stop the node when tests are complete

The test output includes timing information for each test, which helps identify slow tests.

## Troubleshooting

If tests are failing or timing out:

1. Check the node logs in `tests/.dysonprotocol/node.log`
2. Increase verbosity with `-v` or `-vv` flags
3. Run a specific test with `TEST_PATTERN=nameservice/test_denom_metadata_cli.py make test`
