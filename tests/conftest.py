import sys
import shlex
import subprocess
import tempfile
import os
import json
from decimal import Decimal, ROUND_CEILING
import shutil
import pytest
from pathlib import Path
import random
import string
import time
import io
import signal
import atexit
from typing import Dict
from utils import poll_until_condition
import secrets  # new
import ast
import warnings
from typing import List, Tuple, Iterable
from textwrap import dedent

NUM_CHAINS = 2
NUM_NODES = 1

# Global constants
CHAINNET_SCRIPT = str(Path(__file__).parent.parent / "scripts" / "chainnet.py")

from _pytest.assertion import truncate

truncate.DEFAULT_MAX_LINES = 999999
truncate.DEFAULT_MAX_CHARS = 999999


# add tests utils to the path
sys.path.append(str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    # Append the --disable-quic flag to any existing launch args
    print(f"========== Browser type launch args: {browser_type_launch_args}")
    return {
        **browser_type_launch_args,
        "args": browser_type_launch_args.get("args", []) + ["--disable-quic"],
    }


# -----------------------------------------------------------------------------
# AST Checking Plugin - Enforce test code quality
# -----------------------------------------------------------------------------


def enforce_except_has_name(src_path: str | Path) -> str:
    """
    Scan *src_path* and locate all ``except SomeError:`` clauses that
    fail to bind the caught exception (missing ``as exc``).

    Returns
    -------
    List[Tuple[int, str]]
        Every tuple is (lineno, stripped_source_line).

    Raises
    ------
    ValueError
        If *fail_fast* is True and a violation is found.
    SyntaxError
        Propagated if *src_path* contains invalid Python.
    """
    path = Path(src_path)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    lines = source.splitlines()
    violations = ""

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if (
                node.type is not None
                and node.name is None
                and node.name != "_"
                and node.name != "__"
            ):
                src = ast.get_source_segment(source, node)
                violations += dedent(
                    f"""
# ----- Exception without `as <var>` violation.
You MUST use a variable name and you MUST print the exception or use the exception in the error message -----
Bad:
{path}:{node.lineno}:
```python
{src}
```
Good:
```python
except SomeException as e:
    print(f"A helpful error message: {{e}}")
    # or
    return "A helpful error message: " + str(e)
    ...
```

"""
                )

    return violations


# -----------------------------------------------------------------------------
# Chainnet Fixture
# -----------------------------------------------------------------------------


def make_run_command(dysond_bin, node_home):
    """
    Returns a function that can be used to run dysond commands.
    The function takes the same arguments as dysond, and returns the output of the command.
    """

    def run_command(*args, raw=False):
        """
        Run a dysond command.
        If the command is a tx command, it will wait for confirmation and return the tx hash.
        If the command is a query command, it will return the output of the command.
        If raw is True, the command will be run as is without any extra arguments.
        """
        commands = [dysond_bin, *args]
        if "--home" not in args:
            commands += ["--home", str(node_home)]

        # Check if this is a tx script update command with --code-path
        if "--code-path" in args:
            # Find the code path
            code_path_index = args.index("--code-path") + 1
            if code_path_index < len(args):
                code_path = args[code_path_index]

                # Check for forbidden code
                violations = enforce_except_has_name(code_path)
                if violations:
                    raise Exception(
                        f"Forbidden code found in {code_path}:\n{violations}"
                    )

                # Run ruff
                print(f"Running ruff on {code_path}")
                ruff_result = subprocess.run(
                    ["ruff", "check", code_path], capture_output=True, text=True
                )
                if ruff_result.returncode != 0:
                    raise Exception(
                        f"Ruff check failed for {code_path}:\n{ruff_result.stdout}\n{ruff_result.stderr}"
                    )

                ## Run pyright
                # print(f"Running pyright on {code_path}")
                # pyright_result = subprocess.run(["pyright", code_path], capture_output=True, text=True)
                # if pyright_result.returncode != 0:
                #    raise Exception(f"Pyright check failed for {code_path}:\n{pyright_result.stdout}\n{pyright_result.stderr}")

        print(f"Running command: {shlex.join(commands)}")
        # if this is wait-tx and it has a "timed out waiting for transaction" error try again
        if not raw:
            if len(args) > 0 and args[0] == "query" and args[1] == "wait-tx":
                out = None
                stdout = "None"
                stderr = "None"
                if "--timeout" not in args:
                    commands += ["--timeout", "500s"]
                for i in range(20, 0, -1):
                    out = subprocess.run(commands, capture_output=True, text=True)
                    stdout = out.stdout
                    stderr = out.stderr
                    try:
                        # find the first and last curly braces in stdout
                        first_brace = stdout.find("{")
                        last_brace = stdout.rfind("}")
                        if first_brace != -1 and last_brace != -1:
                            json_out = json.loads(stdout[first_brace : last_brace + 1])
                        else:
                            json_out = json.loads(stdout)
                        if (
                            json_out.get("code") == 0 or i == 1
                        ):  # Last attempt should return the result
                            return json_out
                        continue
                    except json.JSONDecodeError:
                        if "timed out waiting for transaction" in out.stderr:
                            time.sleep(0.1)
                            continue
                        if "connect: connection refused" in out.stderr:
                            time.sleep(0.1)
                            continue
                        print(
                            f"Error parsing tx response: \nOUT: {out.stdout}\nERR: {out.stderr}"
                        )
                        return stdout + "\n" + stderr
                return stdout + "\n" + stderr

            # If this is an online tx command, execute and wait for confirmation
            if len(args) > 0 and args[0] == "tx" and "--offline" not in args:
                # Ensure --yes is present for tx commands
                if "--yes" not in args and "-y" not in args:
                    commands += ["--yes"]

                # This must be set for all tx commands that dont set gas themselves
                if "--gas" not in args:  #
                    commands += ["--gas", "20000000"]
                # Run the tx command
                original_out = subprocess.run(commands, capture_output=True, text=True)

                try:
                    tx_response = json.loads(original_out.stdout)
                    if tx_response.get("code") == 0:
                        # Use longer timeout for script update transactions as they may take more time

                        wait_tx_response = run_command(
                            "query",
                            "wait-tx",
                            tx_response["txhash"],
                        )
                        return wait_tx_response
                    else:

                        raise Exception(
                            f"Error in tx command, code: {tx_response['code']}, raw_log: {tx_response['raw_log']}"
                        )
                except json.JSONDecodeError as e:
                    combined_out = (
                        original_out.stdout + "\n" + original_out.stderr
                    ).strip()
                    last_line = combined_out.split("\n")[-1]
                    first_brace = last_line.find("{")
                    last_brace = last_line.rfind("}")

                    if first_brace != -1 and last_brace != -1:
                        try:
                            json_out = json.loads(
                                last_line[first_brace : last_brace + 1]
                            )
                            return {
                                "code": 666,
                                "raw_log": last_line,
                                "data": json_out,
                            }
                        except json.JSONDecodeError:
                            pass

                    raise Exception(
                        f"Error parsing tx response: \nOUT: {original_out.stdout}\nERR: {original_out.stderr}"
                    )
        for attempt in range(10):
            # Otherwise, just run the command and return the output
            out = subprocess.run(commands, capture_output=True, text=True)
            return_out = out.stdout + "\n" + out.stderr
            try:
                first_brace = return_out.find("{")
                last_brace = return_out.rfind("}")
                if first_brace != -1 and last_brace != -1:
                    json_out = json.loads(return_out[first_brace : last_brace + 1])
                else:
                    json_out = json.loads(return_out)
                return json_out
            except json.JSONDecodeError:
                return return_out
            except Exception as e:
                if attempt < 9:
                    if "account sequence mismatch" in str(e):
                        time.sleep(0.1)
                        continue
                    if "connect: connection refused" in str(e):
                        time.sleep(0.1)
                        continue

                raise e

    return run_command


@pytest.fixture(scope="session")
def test_base_dir(worker_id):
    """Fixture that returns the test base directory based on worker_id."""
    env_base = os.getenv("DYSON_BASE_DIR")
    if env_base:
        # Append worker_id to avoid conflicts when running with pytest-xdist
        if worker_id == "master":
            p = Path(env_base)
        else:
            p = Path(env_base) / worker_id
        p.mkdir(parents=True, exist_ok=True)
        return p
    base_dir = Path(tempfile.mkdtemp())
    return base_dir


@pytest.fixture(scope="session")
def test_config_path(test_base_dir):
    """Fixture that returns the chainnet config file path."""
    return test_base_dir / "chains.json"


@pytest.fixture(scope="session")
def chainnet(worker_id, test_base_dir, test_config_path):
    """Session-scoped fixture to set up and tear down a chainnet network.
    The fixture returns a list of run_commands, one for each chain.
    The run_commands can be used to run dysond commands on the respective chain.
    """

    print(f"Worker ID: {worker_id}")

    # Convert worker_id to numeric value for chainnet offset
    if worker_id == "master":
        worker_offset = 0
    else:
        worker_offset = int(worker_id[2:])

    config_path = test_config_path
    base_dir = test_base_dir
    dysond_bin = shutil.which("dysond")
    assert dysond_bin, "dysond binary not found in PATH"

    # 1. Generate config
    proc = subprocess.run(
        [
            "python3",
            CHAINNET_SCRIPT,
            "generate",
            "--chains",
            str(NUM_CHAINS),
            "--nodes",
            str(NUM_NODES),
            "--base-dir",
            str(base_dir),
            "--output",
            str(config_path),
            "--dysond-bin",
            dysond_bin,
            "--hermes-config",
            "--chainnet-offset",
            str(
                worker_offset + 2
            ),  # so that we don't interfere with the "make start" command
        ],
        check=True,
    )
    assert config_path.exists(), f"Config file not created: {config_path}"
    print(f"Config file: {config_path}")

    # 2. Setup network
    proc = subprocess.run(
        [
            "python3",
            CHAINNET_SCRIPT,
            "setup",
            "--config-file",
            str(config_path),
            "--force",
        ]
    )

    # 3. Start network (this starts both dysond nodes and hermes)
    start_cmd = [
        "python3",
        CHAINNET_SCRIPT,
        "start",
        "--config-file",
        str(config_path),
        "--block-speed",
        "300ms",
        "--no-blocks-timeout",
        "15",
        #"--logs",
    ]
    
    # Support optional log module filtering via environment variable
    log_module = os.getenv("LOG_MODULE")
    if log_module:
        start_cmd.extend(["--log-module", log_module])
        print(f"Filtering logs to module: {log_module}")
    
    dysond_proc = subprocess.Popen(
        start_cmd,
        preexec_fn=os.setsid,
    )

    # Track processes for cleanup
    processes = [dysond_proc]

    run_commands = []
    with open(config_path, "r") as f:
        # get node_home from config file
        config = json.load(f)
        for chain in config["chains"]:
            run_commands.append(make_run_command(dysond_bin, chain["nodes"][0]["home"]))
            run_commands[-1]("config", "set", "client", "output", "json")

    # wait for dysond to be ready
    def _ready():
        """
        Check if the node is ready (produced blocks).
        """
        try:
            for dysond_bin in run_commands:
                status = dysond_bin("status")
                if int(status["sync_info"]["latest_block_height"]) < 1:
                    return False
            return True
        except Exception as e:
            return False

    poll_until_condition(
        _ready, timeout=20, poll_interval=1, error_message="Node did not produce blocks"
    )

    yield run_commands

    # Simple fixture cleanup - just kill the process groups
    for proc in processes:
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=3)
            except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    proc.wait(timeout=3)
                except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
                    pass


@pytest.fixture(autouse=True, scope="session")
def node_ready(chainnet):
    """Session fixture to ensure the node is ready (produced blocks)."""
    dysond_bin = chainnet[0]

    def _ready():
        """
        Check if the node is ready (produced blocks).
        """
        try:
            status = dysond_bin("status")
            return int(status["sync_info"]["latest_block_height"]) > 1
        except Exception as e:
            print(f"Error getting status: {e}")
            return False

    poll_until_condition(
        _ready,
        timeout=15,
        poll_interval=0.3,
        error_message="Node did not produce blocks",
    )


@pytest.fixture(scope="session")
def generate_account(chainnet, faucet):
    """Fixture that returns a function to create new accounts."""
    created = []
    default_dysond_bin = chainnet[0]

    def _gen(
        name_prefix,
        faucet_amount=1,
        dysond_bin=default_dysond_bin,
        return_mnemonic=False,
    ):
        """
        Create a new account.
        Args:
            name_prefix: The prefix for the account name.
            dysond_bin: The dysond binary to use. If not provided, the default dysond binary is used.
            return_mnemonic: If True, also return the mnemonic phrase
        Returns:
            If return_mnemonic is False: A tuple of the name and address of the account.
            If return_mnemonic is True: A tuple of the name, address, and mnemonic of the account.
        """
        name = (
            name_prefix
            + "_"
            + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        )
        # Create key and capture output including mnemonic
        out = dysond_bin(
            "keys", "add", name, "--keyring-backend", "test", "--output", "json"
        )
        dysond_bin("config", "set", "client", "output", "json")

        # Extract address and mnemonic from the output
        address = out["address"]
        mnemonic = out.get("mnemonic", "")

        created.append(name)
        if faucet_amount:
            faucet(address, amount=faucet_amount)

        if return_mnemonic:
            return [name, address, mnemonic]
        else:
            return [name, address]

    return _gen


@pytest.fixture(scope="session")
def faucet(chainnet):
    """Fixture that returns a function to send coins from alice to a given address."""
    default_dysond_bin = chainnet[0]

    def _faucet(
        address, denom="udys", amount=10000, dysond_bin=default_dysond_bin, **kwargs
    ):
        """
        Send coins from alice to a given address.
        Args:
            address: The address to send coins to.
            denom: The denom of the coins to send.
            amount: The amount of coins to send.
        """

        # Normalize amount to integer if provided as string
        if isinstance(amount, str):
            amount = int(amount)

        # Check alice's balance before attempting transfer
        alice_balances = dysond_bin("query", "bank", "balances", "alice")
        alice_balance = 0
        for bal in alice_balances.get("balances", []):
            if bal.get("denom") == denom:
                alice_balance = int(bal.get("amount", 0))
                break

        if alice_balance < amount:
            raise Exception(
                f"Faucet insufficient funds: alice has {alice_balance} {denom} "
                f"but test requested {amount} {denom}. "
                f"Consider reducing faucet_amount or running tests in isolation."
            )

        # Send tx from alice (run_command already waits for tx internally)
        dysond_bin(
            "tx",
            "bank",
            "send",
            "alice",
            address,
            str(amount) + denom,
            "--from",
            "alice",
            "--yes",
            **kwargs,
        )

    return _faucet


@pytest.fixture(scope="session")
def api_address(chainnet) -> Dict[str, str]:
    """
    Get the API host string (host:port) from the dysond config.
    This is used for Host headers in HTTP requests to access scripts via web.

    Returns:
        str: Host:port string (e.g. "0.0.0.0:1317")
    """
    dysond_bin = chainnet[0]

    # Get the API address from the config (format: tcp://0.0.0.0:1317)
    address = dysond_bin("config", "get", "app", "api.address", raw=True)

    # Extract host and port from tcp://host:port format
    host, port = address.split("//")[1].split(":")

    return {"host": host, "port": port}


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Get the project root directory."""
    return Path(os.path.abspath(__file__)).parent.parent


@pytest.fixture(scope="session")
def ibc_setup(
    chainnet,
    test_config_path,
    generate_account,
    worker_id,
    faucet,
    test_base_dir,
    node_ready,
):
    """Fixture to set up IBC connections between chains. Use this fixture when your test needs IBC functionality."""
    config_path = test_config_path

    # Create a unique IBC account for this worker to avoid sequence conflicts
    ibc_name, ibc_address, ibc_mnemonic = generate_account(
        f"ibc_{worker_id}", return_mnemonic=True, faucet_amount=1000_000_000
    )
    print(
        f"Created unique IBC account for worker {worker_id}: {ibc_name} ({ibc_address})"
    )

    # Also fund the account on the second chain if it exists
    if len(chainnet) > 1:
        dysond_bin2 = chainnet[1]
        # Create a temporary mnemonic file
        mnemonic_file = test_base_dir / f"{ibc_name}_mnemonic.txt"
        mnemonic_file.write_text(ibc_mnemonic)

        # Import the key on the second chain using the mnemonic file
        dysond_bin2(
            "keys",
            "add",
            ibc_name,
            "--recover",
            "--source",
            str(mnemonic_file),
            "--keyring-backend",
            "test",
        )

        # Clean up the mnemonic file
        mnemonic_file.unlink()

        # Fund the account on the second chain
        faucet(ibc_address, dysond_bin=dysond_bin2, amount=100_000_000)

    # Pre-flight diagnostics to surface common causes early
    import shutil as _shutil

    hermes_path = _shutil.which("hermes")
    print(f"Hermes binary: {hermes_path}")
    assert hermes_path, "Hermes binary not found in PATH; required for IBC tests"
    try:
        hermes_ver = subprocess.run(
            [hermes_path, "version"], capture_output=True, text=True
        )
        print(
            f"Hermes version: {hermes_ver.stdout.strip() or hermes_ver.stderr.strip()}"
        )
    except Exception as _exc:
        print(f"Warning: failed to get hermes version: {_exc}")

    # Basic node readiness snapshot (heights) before starting IBC setup
    try:
        status_a = chainnet[0]("status")
        print(
            f"Pre-IBC Chain A height: {status_a.get('sync_info', {}).get('latest_block_height')}"
        )
        if len(chainnet) > 1:
            status_b = chainnet[1]("status")
            print(
                f"Pre-IBC Chain B height: {status_b.get('sync_info', {}).get('latest_block_height')}"
            )
    except Exception as _exc:
        print(f"Warning: failed pre-IBC status snapshot: {_exc}")

    print(f"Starting IBC setup in background with account {ibc_name}")
    ibc_proc = subprocess.Popen(
        [
            "python3",
            CHAINNET_SCRIPT,
            "ibc",
            "--config-file",
            str(config_path),
            "--ibc-account-name",
            ibc_name,
            "--ibc-account-address",
            ibc_address,
            "--ibc-account-mnemonic",
            ibc_mnemonic,
        ],
        preexec_fn=os.setsid,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Poll until IBC setup is complete
    def _ibc_setup_ready():
        """
        Check if IBC setup is complete.
        """
        print(f"Checking if IBC setup is complete: {ibc_proc.poll()}")
        return ibc_proc.poll() is not None

    try:
        poll_until_condition(
            _ibc_setup_ready,
            timeout=45,
            poll_interval=1,
            error_message="IBC setup did not complete",
        )
    except Exception as _timeout_exc:
        # On timeout, dump rich diagnostics to narrow failure point
        print("\n===== IBC setup timeout diagnostics =====")
        try:
            cfg = json.load(open(test_config_path))
            print(f"chains.json path: {test_config_path}")
            print(
                f"Chains present: {[c.get('chain_id') for c in cfg.get('chains', [])]}"
            )
        except Exception as _exc:
            print(f"Failed reading chains.json: {_exc}")

        try:
            # Query basic per-chain health
            for i, rc in enumerate(chainnet):
                st = rc("status")
                print(
                    f"Chain[{i}] height={st.get('sync_info', {}).get('latest_block_height')} catching_up={st.get('sync_info', {}).get('catching_up')}"
                )
        except Exception as _exc:
            print(f"Failed querying node status: {_exc}")

        try:
            # Force-stop the IBC process to capture its stdout/stderr
            if ibc_proc.poll() is None:
                try:
                    os.killpg(os.getpgid(ibc_proc.pid), signal.SIGTERM)
                except Exception:
                    pass
            out, err = ibc_proc.communicate(timeout=3)
            print(
                f"IBC STDOUT:\n{out.decode('utf-8', errors='ignore') if isinstance(out, bytes) else out}"
            )
            print(
                f"IBC STDERR:\n{err.decode('utf-8', errors='ignore') if isinstance(err, bytes) else err}"
            )
        except subprocess.TimeoutExpired:
            print("Failed to capture IBC process output: communicate timeout")
        except Exception as _exc:
            print(f"Failed to capture IBC process output: {_exc}")
        print("===== End IBC diagnostics =====\n")
        raise

    # Check if IBC setup was successful
    if ibc_proc.returncode != 0:
        # Get the process output to understand what went wrong
        stdout, stderr = ibc_proc.communicate()
        print(f"IBC setup failed with exit code {ibc_proc.returncode}")
        print(f"STDOUT: {stdout.decode('utf-8')}\nSTDERR: {stderr.decode('utf-8')}")
        raise Exception(f"IBC setup failed with exit code {ibc_proc.returncode}")

    # Post-IBC setup: poll for transfer channel OPEN on both chains
    dysond_a = chainnet[0]
    dysond_b = chainnet[1] if len(chainnet) > 1 else chainnet[0]

    def _resolve_transfer_channel_pair():
        chs_a = dysond_a("query", "ibc", "channel", "channels")
        chs_b = dysond_b("query", "ibc", "channel", "channels")

        a_open = [
            c
            for c in chs_a.get("channels", [])
            if c.get("port_id") == "transfer" and c.get("state") == "STATE_OPEN"
        ]
        if not a_open:
            return None
        a_chan_id = a_open[0].get("channel_id")
        b_matches = [
            c
            for c in chs_b.get("channels", [])
            if c.get("port_id") == "transfer"
            and c.get("state") == "STATE_OPEN"
            and c.get("counterparty", {}).get("channel_id") == a_chan_id
        ]
        if not b_matches:
            return None
        return a_chan_id, b_matches[0].get("channel_id")

    def _transfer_open_on_both():
        pair = _resolve_transfer_channel_pair()
        if pair is None:
            return False
        a_id, b_id = pair
        end_a = dysond_a("query", "ibc", "channel", "end", "transfer", a_id)
        end_b = dysond_b("query", "ibc", "channel", "end", "transfer", b_id)
        a_open = end_a.get("channel", {}).get("state") == "STATE_OPEN"
        b_open = end_b.get("channel", {}).get("state") == "STATE_OPEN"
        print(
            f"[ibc_setup] transfer/{a_id} open on A: {a_open}; transfer/{b_id} open on B: {b_open}"
        )
        return a_open and b_open

    poll_until_condition(
        _transfer_open_on_both,
        timeout=30,
        poll_interval=1,
        error_message="transfer channel not open on both chains after IBC setup",
    )

    yield chainnet

    # Cleanup IBC process
    if ibc_proc.poll() is None:  # Process is still running
        try:
            print(f"Terminating IBC process {ibc_proc.pid}")
            os.killpg(os.getpgid(ibc_proc.pid), signal.SIGTERM)
            ibc_proc.wait(timeout=3)
        except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
            print(f"Warning: Could not gracefully terminate IBC process {ibc_proc.pid}")

        # If process still running after SIGTERM, force kill
        if ibc_proc.poll() is None:
            try:
                print(f"Force killing IBC process {ibc_proc.pid}")
                os.killpg(os.getpgid(ibc_proc.pid), signal.SIGKILL)
                ibc_proc.wait(timeout=3)
            except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
                print(f"Warning: Could not force kill IBC process {ibc_proc.pid}")


# -----------------------------------------------------------------------------
# Auto-patch the crontask_guide notebook before any docs tests run
# -----------------------------------------------------------------------------
import json


@pytest.fixture(scope="session", autouse=True)
def _patch_crontask_notebook():
    """Ensure the notebook waits for both SCHEDULED and PENDING statuses.

    The notebooks/crontask_guide.ipynb was originally written to poll only for
    tasks in the PENDING state. Recent refactors changed the state flow so that
    tasks remain in SCHEDULED until execution, causing a KeyError when the
    notebook tries to access msg_results too early. We patch the affected cell
    at test-time to wait for either SCHEDULED or PENDING before proceeding.
    """
    nb_path = Path(__file__).parent.parent / "notebooks" / "crontask_guide.ipynb"
    if not nb_path.exists():
        return  # Nothing to patch

    try:
        with nb_path.open("r", encoding="utf-8") as fh:
            nb_data = json.load(fh)
    except Exception as exc:
        print(f"[Notebook patch] Failed to load notebook JSON: {exc}")
        return

    changed = False

    for cell in nb_data.get("cells", []):
        if cell.get("cell_type") != "code":
            continue

        new_source = []
        for line in cell.get("source", []):
            if "task_status = 'PENDING'" in line:
                line = line.replace(
                    "task_status = 'PENDING'", "task_status = 'SCHEDULED'"
                )
                changed = True
            if "while task_status == 'PENDING':" in line:
                line = line.replace(
                    "while task_status == 'PENDING':",
                    "while task_status in ('SCHEDULED', 'PENDING'):",
                )
                changed = True
            new_source.append(line)
        if changed:
            cell["source"] = new_source

    if changed:
        try:
            # Write back the patched notebook JSON
            with nb_path.open("w", encoding="utf-8") as fh:
                json.dump(nb_data, fh, indent=1)
            print(
                "[Notebook patch] Patched notebooks/crontask_guide.ipynb for updated status handling."
            )
        except Exception as exc:
            print(f"[Notebook patch] Failed to write patched notebook: {exc}")


# -----------------------------------------------------------------------------
# Session-level fixture: ensure crontask.clean_up_time param is <=2 seconds so
# tests that rely on quick task cleanup don't need to replicate governance logic.
# -----------------------------------------------------------------------------


@pytest.fixture(scope="session")
def update_crontask_params(chainnet):
    """Ensure clean_up_time is 2 s using MsgUpdateParams (fast, single-tx)."""

    dysond = chainnet[0]

    current = dysond("query", "crontask", "params")["params"]
    print(f"Current crontask params: {current}")
    # Build new params JSON – keep everything else unchanged
    new_params = dict(current)
    new_params["clean_up_time"] = "2"

    # Normalize google.protobuf.Duration to JSON format (e.g. "86400s")
    dur_val = new_params.get("max_subscription_duration")
    if isinstance(dur_val, str):
        import re

        m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", dur_val)
        if m:
            h = int(m.group(1) or 0)
            mm = int(m.group(2) or 0)
            ss = int(m.group(3) or 0)
            total = h * 3600 + mm * 60 + ss
            new_params["max_subscription_duration"] = f"{total}s"

    # Resolve alice bech32 address for authority field
    alice_info = dysond("keys", "show", "alice")
    alice_address = alice_info["address"]

    tx = dysond(
        "tx",
        "crontask",
        "update-params",
        "--authority",
        alice_address,
        "--params",
        json.dumps(new_params),
        "--from",
        "alice",
        "--keyring-backend",
        "test",
        "--yes",
    )

    assert tx.get("code", 1) == 0, f"update-params failed: {tx}"

    def _updated():
        val = dysond("query", "crontask", "params")["params"]
        if int(val["clean_up_time"]) == 2:
            print(f"New crontask params: {val}")
            return True
        return False

    poll_until_condition(
        _updated,
        timeout=10,
        poll_interval=0.5,
        error_message="clean_up_time did not update to 2s in time",
    )


# -----------------------------------------------------------------------------
# Shared helper utilities
# -----------------------------------------------------------------------------


def generate_name() -> str:
    """
    Generate a random `.dys` root name (6-char prefix).
    If base_name is provided, it will be used as the prefix.
    """
    """Return a random `.dys` root name (6-char prefix)."""
    rand_suffix = "".join(random.choices(string.ascii_lowercase, k=6))
    return f"{rand_suffix}.dys"


# -----------------------------------------------------------------------------
# register_name fixture (commit + reveal)
# -----------------------------------------------------------------------------


@pytest.fixture(scope="session")
def register_name():
    """Fixture providing a helper to register a new name via a single tx script exec.

    Usage::

        def test_something(chainnet, generate_account, register_name):
            dysond_bin = chainnet[0]
            owner_keychain_name, owner_addr = generate_account("owner")
            name = register_name(dysond_bin, owner_keychain_name, owner_addr, "10udys")
    """

    def _register(
        dysond_bin, owner_keychain_name: str, owner_addr: str, valuation: str = "10udys"
    ) -> str:
        name = generate_name()
        salt = secrets.token_hex(8)

        extra_code = """
import re
from dys import _msg, _query, get_executor_address

def _parse_coin(s):
    m = re.fullmatch(r"(\\d+)([a-zA-Z0-9./_]+)", s)
    if not m:
        raise Exception("invalid valuation: " + str(s))
    return {"denom": m.group(2), "amount": m.group(1)}

def register(name, salt, valuation):
    owner = get_executor_address()
    # Compute commitment hash
    hexhash = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": owner,
    })["hex_hash"]

    # Commit then reveal
    _msg({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": hexhash,
        "valuation": _parse_coin(valuation),
    })
    _msg({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    })

    # Set destination to owner so future name-bound ops authorize correctly
    _msg({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": owner,
    })

    return name
"""

        args = json.dumps([name, salt, valuation])
        tx = dysond_bin(
            "tx",
            "script",
            "exec",
            "--script-address",
            owner_addr,
            "--function-name",
            "register",
            "--args",
            args,
            "--from",
            owner_keychain_name,
            "--gas",
            "100000000",
            "--extra-code",
            extra_code,
        )
        assert tx.get("code", 1) == 0, f"register_name script failed: {tx}"

        return name

    return _register


# -----------------------------------------------------------------------------
# DEX helper: create a session-scoped DYS root name for a given owner
# -----------------------------------------------------------------------------


@pytest.fixture(scope="session")
def dex_dys_name(register_name):
    """Create a session-wide DEX root name for a given owner on demand.

    Usage:
        name = dex_dys_name(dysond_bin, owner_key_name, owner_address)
    """

    def _mk(dysond_bin, owner_key_name: str, owner_addr: str) -> str:
        return register_name(dysond_bin, owner_key_name, owner_addr)

    return _mk


## Whaleswap scripts are deprecated; module tests do not need these fixtures.


@pytest.fixture
def fresh_denoms(chainnet, whales_scripts_loaded):
    """Mint per-test unique denoms under the session root and return their full names.

    Usage: a, b = fresh_denoms(["a", "b"], units=100)
    """
    import secrets

    dysond = chainnet[0]
    owner_name = whales_scripts_loaded["orderbook"]["owner_name"]
    root = whales_scripts_loaded["root"]

    def _ceil_dec(x: Decimal) -> int:
        return int(x.to_integral_value(rounding=ROUND_CEILING))

    def _mk(names, units=100):
        suffix = secrets.token_hex(3)
        params = dysond("query", "nameservice", "params")
        fee_per = Decimal(params["params"]["mint_fee_per_coin"])  # e.g., 0.01
        fee = _ceil_dec(Decimal(units) * fee_per)
        out = []
        for n in names:
            denom = f"{root}/{suffix}/{n}"
            resp = dysond(
                "tx",
                "nameservice",
                "mint-coins",
                "--amount",
                f"{units}{denom}",
                "--mint-fee",
                f"{fee}udys",
                "--from",
                owner_name,
                "--gas",
                "100000000",
            )
            assert resp.get("code", 1) == 0, f"mint failed: {resp}"
            out.append(denom)
        return out if len(out) > 1 else out[0]

    return _mk


# -----------------------------------------------------------------------------
# AST Checking Plugin - Enforce test code quality
# -----------------------------------------------------------------------------


def _walk_ast_forbidding_nodes(tree, filename):
    errors = []
    warnings_list = []

    class Visitor(ast.NodeVisitor):
        def visit_Try(self, node):
            errors.append(
                f"{filename}:{node.lineno} - use of 'try/except' and 'if' statements is disallowed"
            )
            self.generic_visit(node)

        def visit_If(self, node):
            errors.append(
                f"{filename}:{node.lineno} - 'if' and 'try/except' statement usage is disallowed"
            )
            self.generic_visit(node)

        def visit_Assert(self, node):
            # Forbid boolean 'or' within assert expressions
            for sub in ast.walk(node.test):
                if isinstance(sub, ast.BoolOp) and isinstance(sub.op, ast.Or):
                    errors.append(
                        f"{filename}:{node.lineno} - use of 'or' in assert is disallowed"
                    )
                    break
            # Forbid any() within assert expressions
            for sub in ast.walk(node.test):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Name)
                    and sub.func.id == "any"
                ):
                    errors.append(
                        f"{filename}:{node.lineno} - use of 'any' in assert is disallowed"
                    )
                    break
            self.generic_visit(node)

        # forbid "wait_for_timeout" attribute in playwright
        def visit_Attribute(self, node):
            if (
                isinstance(node.value, ast.Attribute)
                and node.value.attr == "wait_for_timeout"
            ):
                errors.append(
                    f"{filename}:{node.lineno} - 'wait_for_timeout' attribute usage is disallowed"
                )
            # time.sleep is disallowed
            if isinstance(node.value, ast.Attribute) and node.value.attr == "sleep":
                errors.append(
                    f"{filename}:{node.lineno} - 'time.sleep' function usage is disallowed"
                )
            self.generic_visit(node)

        # sleep is disallowed
        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id == "sleep":
                errors.append(
                    f"{filename}:{node.lineno} - 'sleep' function usage is disallowed"
                )
            self.generic_visit(node)

    Visitor().visit(tree)
    return errors, warnings_list


def _check_file_for_ast_rules(path):
    try:
        source = path.read_text()
        tree = ast.parse(source, filename=str(path))
        return _walk_ast_forbidding_nodes(tree, str(path))
    except SyntaxError as e:
        return [f"{path}: SyntaxError: {e}"], []


@pytest.hookimpl(tryfirst=True)
def pytest_collection_finish(session):
    """
    Check for forbidden constructs in pytest test files.
    Forbidden constructs:
    - try/except
    - if
    - time.sleep
    - wait_for_timeout
    - sleep
    - 'or' in assert expressions
    - 'any' in assert expressions

    For any of these constructs, the test will fail with a clear error message.
    Utility functions and fixtures (like this one) are exempt from this check.
    """
    # Only consider .py test files collected by pytest
    seen_files = {
        Path(item.fspath) for item in session.items if Path(item.fspath).suffix == ".py"
    }
    seen_files = list(seen_files)

    total_errors = []
    total_warnings = []

    for file_path in seen_files:
        errors, warns = _check_file_for_ast_rules(file_path)
        total_errors.extend(errors)
        total_warnings.extend(warns)

    for warn in total_warnings:
        warnings.warn(UserWarning(warn))

    if total_errors:
        raise pytest.UsageError(
            "Forbidden constructs found:\n"
            + "\n".join(total_errors)
            + """
            Now I understand that you are trying to use forbidden constructs in your test code.
            There are many other ways to get around the limitations of the test harness.
            But you must respect the spirit of the these limits and not try to trick the test harness into thinking you are not using forbidden constructs.
            The goal is that all tests have a singular logical path to assert that the test passed.
            The goal is that the tests are specific and notify us of future breakign changes
            The goal is that devs can look at the test and understand how to use the project.
            It may be required to rewrite a test to achieve this, and that is ok.
            """
        )


# -----------------------------------------------------------------------------
# Whaleswap environment setup fixture (moved from tests/whaleswap/amm/conftest.py)
# -----------------------------------------------------------------------------


@pytest.fixture(scope="function")
def ws_setup_env(chainnet, generate_account, faucet):
    """
    Single-tx dyslang setup for whaleswap tests:
    - register 1 name
    - mint 3 denoms name/coin/a, name/coin/b, name/coin/c with 1800 units each
    - distribute to three accounts: for each denom, send 300 base to each

    Returns dict with keys: owner_name, owner_addr, acc1, acc2, acc3, name, denoms
    """
    dysond = chainnet[0]

    # Create owner and recipients
    [owner_name, owner_addr] = generate_account("ws_owner", faucet_amount=2_000_000)
    [a1_name, a1_addr] = generate_account("ws_a1", faucet_amount=1)
    [a2_name, a2_addr] = generate_account("ws_a2", faucet_amount=1)
    [a3_name, a3_addr] = generate_account("ws_a3", faucet_amount=1)

    # Ensure owner has enough udys to pay mint fees and gas
    faucet(owner_addr, amount=5_000_000)

    import random, string  # local imports

    name = "".join(random.choices(string.ascii_lowercase, k=6)) + ".dys"
    salt = "s" + "".join(random.choices(string.ascii_lowercase + string.digits, k=7))

    # Dyslang script executed with --extra-code to avoid persistent script updates
    extra_code = """
import json
from dys import _msg, _query, get_executor_address

def setup(name, salt, acc1, acc2, acc3):
    owner = get_executor_address()

    # Compute commitment hash
    hexhash = _query({
        "@type": "/dysonprotocol.nameservice.v1.QueryComputeHashRequest",
        "name": name,
        "salt": salt,
        "committer": owner,
    })["hex_hash"]

    # Commit then reveal
    _msg({
        "@type": "/dysonprotocol.nameservice.v1.MsgCommit",
        "committer": owner,
        "hexhash": hexhash,
        "valuation": {"denom": "udys", "amount": "10"},
    })
    _msg({
        "@type": "/dysonprotocol.nameservice.v1.MsgReveal",
        "committer": owner,
        "name": name,
        "salt": salt,
    })

    # Set destination to owner so MintCoins authz passes (dest == signer)
    _msg({
        "@type": "/dysonprotocol.nameservice.v1.MsgSetDestination",
        "owner": owner,
        "name": name,
        "destination": owner,
    })

    denoms = [f"{name}/coin/a", f"{name}/coin/b", f"{name}/coin/c"]

    # Compute mint fee = ceil(sum(units) * mint_fee_per_coin)
    params = _query({"@type": "/dysonprotocol.nameservice.v1.QueryParamsRequest"})["params"]
    fee_per = float(params["mint_fee_per_coin"]) if params.get("mint_fee_per_coin") else 0.0
    total_units = 1800 * 3
    fee = int(-(-total_units * fee_per // 1))

    # Mint 1800 units of each denom to owner
    _msg({
        "@type": "/dysonprotocol.nameservice.v1.MsgMintCoins",
        "name_destination": owner,
        "amount": [
            {"denom": denoms[0], "amount": "1800"},
            {"denom": denoms[1], "amount": "1800"},
            {"denom": denoms[2], "amount": "1800"},
        ],
        "mint_fee": {"denom": "udys", "amount": str(fee)},
    })

    # Distribute 300 base for each denom to each of the 3 accounts
    for r in [acc1, acc2, acc3]:
        sends = []
        for d in denoms:
            sends.append({"denom": d, "amount": "300"})
        # Coins array must be sorted by denom for Cosmos SDK validation
        sends = sorted(sends, key=lambda x: x["denom"])
        _msg({
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": owner,
            "to_address": r,
            "amount": sends,
        })

    return {
        "name": name,
        "denoms": denoms,
        "owner": owner,
    }
"""

    args = json.dumps([name, salt, a1_addr, a2_addr, a3_addr])
    tx = dysond(
        "tx",
        "script",
        "exec",
        "--script-address",
        owner_addr,
        "--function-name",
        "setup",
        "--args",
        args,
        "--from",
        owner_name,
        "--gas",
        "100000000",
        "--extra-code",
        extra_code,
    )

    assert tx.get("code", 1) == 0, f"setup script failed: {json.dumps(tx, indent=2)}"

    denoms = [f"{name}/coin/a", f"{name}/coin/b", f"{name}/coin/c"]
    return {
        "owner_name": owner_name,
        "owner_addr": owner_addr,
        "acc1": {"name": a1_name, "addr": a1_addr},
        "acc2": {"name": a2_name, "addr": a2_addr},
        "acc3": {"name": a3_name, "addr": a3_addr},
        "name": name,
        "denoms": denoms,
    }
