import ast
import base64
import dataclasses
import datetime
import decimal
import importlib
import io
import random
import sys
from collections import defaultdict
from contextlib import redirect_stdout
from functools import wraps
from textwrap import dedent
import time
import typing
import enum
import forge
import re as re_module
import requests
import json
from freezegun import freeze_time
from freezegun.api import FakeDatetime, FakeDate


# Fixes to make freezegun look pretty in dyslang
FakeDatetime.__doc__ = datetime.datetime.__doc__
FakeDate.__doc__ = datetime.date.__doc__
FakeDatetime.__name__ = "Datetime"
FakeDatetime.__qualname__ = "Datetime"
FakeDate.__name__ = "Date"
FakeDate.__qualname__ = "Date"


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return str(obj)
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        if isinstance(obj, datetime.date):
            return obj.isoformat()
        if isinstance(obj, datetime.time):
            return obj.isoformat()
        if isinstance(obj, datetime.timedelta):
            return str(obj)
        return super(DecimalEncoder, self).default(obj)


import dyslang


MAX_CUM_SIZE = dyslang.MAX_SCOPE_SIZE * dyslang.MAX_NODE_CALLS
GAS_MULTIPLE = 1


class DysMsgException(Exception):
    """Used for dysvm _msg exceptions."""


class DysQueryException(Exception):
    """Used for dysvm _query exceptions."""


class DeprecationError(Exception):
    """Used for deprecated methods and functions."""

    def __init__(self, message="This feature has been deprecated."):
        """Empty init."""
        Exception.__init__(self, message)


def safe_module_import(dotted_module):
    spec = importlib.util.find_spec(dotted_module)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_docstr(source_func, target_func):
    if source_func is None or target_func is None:
        return None
    target_func.__doc__ = source_func.__doc__
    return target_func


def get_module_dict():
    import datetime
    import decimal
    import hashlib
    import html
    import math
    import mimetypes
    import pathlib
    import random
    import string
    import urllib
    import time
    import bencoder
    import function_schema

    @forge.copy(random.seed)
    def safe_random_seed(a=None, version=2):
        assert a is not None, "in Dyson seed must not be None"
        return random.seed(a, version)

    safe_random_seed.__doc__ = random.Random.seed.__doc__
    safe_random_seed.__module__ = random.Random.seed.__module__
    safe_random_seed.__qualname__ = random.Random.seed.__qualname__
    allow_func(safe_random_seed)

    @forge.copy(json.dumps)
    def safe_json_dumps(**kwargs):
        if kwargs.get("separators", None):
            assert kwargs["separators"] == (
                ",",
                ":",
            ), "separators can only be (',', ': ')"
        if check_circular := kwargs.get("check_circular", None):
            assert check_circular is True, "check_circular must be True"
        if indent := kwargs.get("indent", None):
            if isinstance(indent, str):
                assert (
                    len(kwargs["indent"]) <= 4
                ), f"indent must be less than or equal 4, got: {indent}"
            if isinstance(indent, int):
                assert (
                    kwargs["indent"] <= 4
                ), f"indent must be less than or equal 4, got: {indent}"
        return json.dumps(**kwargs)

    safe_json_dumps.__doc__ = json.dumps.__doc__
    safe_json_dumps.__module__ = "json"
    safe_json_dumps.__qualname__ = "dumps"
    allow_func(safe_json_dumps)

    mod_dict = {
        "ast": {
            "parse": ast.parse,
            "literal_eval": ast.literal_eval,
            "unparse": ast.unparse,
            "dump": ast.dump,
            "walk": ast.walk,
            "FunctionDef": ast.FunctionDef,
            "ClassDef": ast.ClassDef,
            "get_source_segment": ast.get_source_segment,
            "get_docstring": ast.get_docstring,
            "fix_missing_locations": ast.fix_missing_locations,
            "NodeTransformer": ast.NodeTransformer,
            "NodeVisitor": ast.NodeVisitor,
        },
        "datetime": {
            "date": datetime.date,
            "datetime": datetime.datetime,
            "time": datetime.time,
            "timedelta": datetime.timedelta,
            "timezone": datetime.timezone,
            "tzinfo": datetime.tzinfo,
            "UTC": datetime.UTC,
        },
        "dataclasses": {
            "dataclass": dataclasses.dataclass,
            "field": dataclasses.field,
            "asdict": dataclasses.asdict,
            "astuple": dataclasses.astuple,
        },
        "enum": {
            "Enum": enum.Enum,
            "EnumType": enum.EnumType,
            "IntEnum": enum.IntEnum,
            "StrEnum": enum.StrEnum,
        },
        "function_schema": {
            "get_function_schema": function_schema.get_function_schema,
            "Doc": function_schema.Doc,
        },
        "time": {
            "time": time.time,
        },
        "pathlib": {"PurePath": pathlib.PurePath},
        "mimetypes": {"guess_type": mimetypes.guess_type},
        "urllib": {
            "parse": {
                "parse_qs": urllib.parse.parse_qs,
                "parse_qsl": urllib.parse.parse_qsl,
                "urlsplit": urllib.parse.urlsplit,
                "urlunsplit": urllib.parse.urlunsplit,
                "urljoin": urllib.parse.urljoin,
                "urldefrag": urllib.parse.urldefrag,
                "quote": urllib.parse.quote,
                "quote_plus": urllib.parse.quote_plus,
                "quote_from_bytes": urllib.parse.quote_from_bytes,
                "unquote": urllib.parse.unquote,
                "unquote_plus": urllib.parse.unquote_plus,
                "unquote_to_bytes": urllib.parse.unquote_to_bytes,
            }
        },
        "base64": {
            "decodebytes": base64.decodebytes,
            "encodebytes": base64.encodebytes,
            "b64decode": base64.b64decode,
            "b64encode": base64.b64encode,
            "urlsafe_b64encode": base64.urlsafe_b64encode,
            "urlsafe_b64decode": base64.urlsafe_b64decode,
        },
        "decimal": {
            "Decimal": decimal.Decimal,
            "ROUND_CEILING": decimal.ROUND_CEILING,
            "ROUND_DOWN": decimal.ROUND_DOWN,
            "ROUND_FLOOR": decimal.ROUND_FLOOR,
            "ROUND_HALF_DOWN": decimal.ROUND_HALF_DOWN,
            "ROUND_HALF_EVEN": decimal.ROUND_HALF_EVEN,
            "ROUND_HALF_UP": decimal.ROUND_HALF_UP,
            "ROUND_UP": decimal.ROUND_UP,
            "ROUND_05UP": decimal.ROUND_05UP,
        },
        "json": {
            "dumps": safe_json_dumps,
            "loads": json.loads,
            "JSONDecodeError": json.JSONDecodeError,
        },
        "html": {"escape": html.escape, "unescape": html.unescape},
        "io": {"StringIO": io.StringIO, "BytesIO": io.BytesIO},
        "hashlib": {
            "sha1": hashlib.sha1,
            "sha256": hashlib.sha256,
            "sha512": hashlib.sha512,
            "md5": hashlib.md5,
        },
        "string": {
            "Template": string.Template,
            "capwords": string.capwords,
            "ascii_letters": string.ascii_letters,
            "ascii_lowercase": string.ascii_lowercase,
            "ascii_uppercase": string.ascii_uppercase,
            "digits": string.digits,
            "hexdigits": string.hexdigits,
            "octdigits": string.octdigits,
            "punctuation": string.punctuation,
            "printable": string.printable,
            "whitespace": string.whitespace,
        },
        "random": {
            "betavariate": random.betavariate,
            "choice": random.choice,
            "expovariate": random.expovariate,
            "gauss": random.gauss,
            "paretovariate": random.paretovariate,
            "random": random.random,
            "sample": random.sample,
            "shuffle": random.shuffle,
            "triangular": random.triangular,
            "seed": safe_random_seed,
            "uniform": random.uniform,
            "randint": random.randint,
        },
        "re2": {
            "compile": copy_docstr(re_module.compile, re_module.compile),
            "escape": copy_docstr(re_module.escape, re_module.escape),
            "findall": copy_docstr(re_module.findall, re_module.findall),
            "finditer": copy_docstr(re_module.finditer, re_module.finditer),
            "fullmatch": copy_docstr(re_module.fullmatch, re_module.fullmatch),
            "match": copy_docstr(re_module.match, re_module.match),
            "search": copy_docstr(re_module.search, re_module.search),
            "split": copy_docstr(re_module.split, re_module.split),
            "sub": copy_docstr(re_module.sub, re_module.sub),
            "subn": copy_docstr(re_module.subn, re_module.subn),
            "IGNORECASE": re_module.IGNORECASE,
            "ASCII": re_module.ASCII,
            "VERBOSE": re_module.VERBOSE,
            "LOCALE": re_module.LOCALE,
            "UNICODE": re_module.UNICODE,
            "DOTALL": re_module.DOTALL,
            "MULTILINE": re_module.MULTILINE,
        },
        "re": {
            "compile": copy_docstr(re_module.compile, re_module.compile),
            "escape": copy_docstr(re_module.escape, re_module.escape),
            "findall": copy_docstr(re_module.findall, re_module.findall),
            "finditer": copy_docstr(re_module.finditer, re_module.finditer),
            "fullmatch": copy_docstr(re_module.fullmatch, re_module.fullmatch),
            "match": copy_docstr(re_module.match, re_module.match),
            "search": copy_docstr(re_module.search, re_module.search),
            "split": copy_docstr(re_module.split, re_module.split),
            "sub": copy_docstr(re_module.sub, re_module.sub),
            "subn": copy_docstr(re_module.subn, re_module.subn),
            "IGNORECASE": re_module.IGNORECASE,
            "ASCII": re_module.ASCII,
            "VERBOSE": re_module.VERBOSE,
            "LOCALE": re_module.LOCALE,
            "UNICODE": re_module.UNICODE,
            "DOTALL": re_module.DOTALL,
            "MULTILINE": re_module.MULTILINE,
        },
        "math": {
            "ceil": math.ceil,
            "copysign": math.copysign,
            "fabs": math.fabs,
            "factorial": math.factorial,
            "floor": math.floor,
            "fmod": math.fmod,
            "fsum": math.fsum,
            "frexp": math.frexp,
            "gcd": math.gcd,
            "isclose": math.isclose,
            "isfinite": math.isfinite,
            "isinf": math.isinf,
            "isnan": math.isnan,
            "isqrt": math.isqrt,
            "lcm": math.lcm,
            "modf": math.modf,
            "remainder": math.remainder,
            "trunc": math.trunc,
            "ulp": math.ulp,
            "log": math.log,
            "log1p": math.log1p,
            "log2": math.log2,
            "log10": math.log10,
            "sqrt": math.sqrt,
            "acos": math.acos,
            "asin": math.asin,
            "atan": math.atan,
            "atan2": math.atan2,
            "cos": math.cos,
            "dist": math.dist,
            "hypot": math.hypot,
            "sin": math.sin,
            "tan": math.tan,
            "degrees": math.degrees,
            "radians": math.radians,
            "gamma": math.gamma,
            "lgamma": math.lgamma,
            "pi": math.pi,
            "e": math.e,
            "tau": math.tau,
            "inf": math.inf,
            "nan": math.nan,
        },
        "typing": {
            "Annotated": typing.Annotated,
            "Any": typing.Any,
            "Callable": typing.Callable,
            "Dict": typing.Dict,
            "List": typing.List,
            "Literal": typing.Literal,
            "Optional": typing.Optional,
            "TypedDict": typing.TypedDict,
            "Union": typing.Union,
            "Tuple": typing.Tuple,
            "Iterable": typing.Iterable,
        },
        "bencoder": {
            "encode": bencoder.encode,
            "decode": bencoder.decode,
        },
    }

    def walk(node):
        for key, item in node.items():
            if isinstance(item, dict):
                walk(item)
            else:
                allow_func(item)

    walk(mod_dict)
    return mod_dict


def build_sandbox(
    msg,
    script,
    attached_msg_results,
    block_info,
    port,
):
    url = f"http://localhost:{port}/rpc"

    def _chain(method, **params):
        """
        The main way to interact with the chain from a script.

        :param method: the command to call on the chain, see TxBuilder for a list of possible commands
        `**kwargs` will depend on the command being called

        :returns: the response of the command or error

        """

        if port == 0:
            print("Port Not Set")
            print(method, params)
            return {"error": "", "result": {}}

        payload = {
            "method": f"RpcService.{method}",
            "params": [params],
            "jsonrpc": "2.0",
            "id": 0,
        }
        try:
            res = requests.post(url, json=payload)
            # print(f"rpc {method}: {res.status_code} response from golang: {res.text}")
            ret_json = res.json()
            try:
                # some rpc responses are json encoded
                ret_json["result"] = json.loads(str(ret_json["result"]).encode())
            except json.JSONDecodeError as e:
                # print(f"JSONDecodeError: {e} - {res.text}")
                pass

            if error := ret_json.get("error", None):
                if "out of gas" in str(error).lower():
                    raise MemoryError(str(error))
                return {"exception": error}

            return ret_json
        except json.JSONDecodeError:
            return {"exception": res.text}

    _chain.__qualname__ = "_chain"
    allow_dys_func(_chain)

    gas_state = {
        "unconsumed_size": 1,
        "gas_consumed": 0,
        "gas_limit": 0,
        "cumsize": 0,
        "nodes_called": 0,
    }

    seen_nodes = {}

    CALLS_INDEX = 0
    CUM_SIZE_INDEX = 1

    class ScopedDysonEval(dyslang.DysEval):
        last_node = None
        cumsize = 0
        size = 0
        _seen_nodes = seen_nodes
        expr = None

        def eval(self, expr):
            self.expr = expr
            for n in ast.walk(ast.parse(expr)):
                if hasattr(n, "col_offset"):
                    self._seen_nodes[
                        (
                            n.lineno,
                            n.col_offset,
                            n.end_lineno,
                            n.end_col_offset,
                            n.__class__.__name__,
                            "",
                            # ast.get_source_segment(self.expr, n, padded=False),
                        )
                    ] = [0, 0]
            return super(ScopedDysonEval, self).eval(expr)

        def gas_state(self):
            return gas_state

        def consume_gas(self):
            amount = int(gas_state["unconsumed_size"] * GAS_MULTIPLE)
            if amount:
                resp = _chain("ConsumeGas", amount=amount)
                gas_state["unconsumed_size"] = 0
                if resp.get("exception"):
                    resp = _chain("GasLimit")
            else:
                resp = _chain("GasLimit")

            gas_state["gas_consumed"] = resp["result"].get("GasConsumed", 0)
            gas_state["gas_limit"] = resp["result"].get("GasLimit", 0)
            if (
                gas_state["gas_limit"] > 0
                and gas_state["gas_consumed"] > gas_state["gas_limit"]
            ):
                raise MemoryError(f"Out of Gas: {gas_state}")

        def track(self, node):
            if hasattr(node, "nodes_called"):
                return

            if hasattr(node, "lineno"):
                self.size = len(repr(self.scope)) + len(repr(self._last_eval_result))

                node_info = self._seen_nodes[
                    (
                        node.lineno,
                        node.col_offset,
                        node.end_lineno,
                        node.end_col_offset,
                        node.__class__.__name__,
                        "",
                        # ast.get_source_segment(self.expr, node, padded=False),
                    )
                ]
                node_info[CALLS_INDEX] += 1
                node_info[CUM_SIZE_INDEX] += self.size

                if self.size > dyslang.MAX_SCOPE_SIZE:
                    raise MemoryError("Scope has used too much memory")

                if node is not self.last_node:
                    self.last_node = node
                    gas_state["nodes_called"] += 1

                    if gas_state["nodes_called"] > dyslang.MAX_NODE_CALLS:
                        raise MemoryError("This program has too many evaluations")

                    gas_state["cumsize"] += self.size
                    gas_state["unconsumed_size"] += self.size
                    if gas_state["cumsize"] > MAX_CUM_SIZE:
                        raise MemoryError("Cumsize too large")
                if gas_state["unconsumed_size"] > 1_000_000 or isinstance(
                    node, ast.Module
                ):
                    sandbox.consume_gas()

    scope = {"__name__": "dyslang"}
    sandbox = ScopedDysonEval(
        scope=scope,
    )

    @forge.copy(print)
    def dyson_print(*args, sep=" ", end="\n", file=None, flush=False):
        assert len(sep) <= 5, AssertionError("sep len greater than 5")
        assert len(end) <= 5, AssertionError("end len greater than 5")
        print(*args, end=end)

    dyson_print.__doc__ = print.__doc__
    dyson_print.__module__ = "builtins"
    dyson_print.__qualname__ = "print"
    dyson_print = allow_func(dyson_print)

    sandbox.scope.dicts[0]["print"] = dyson_print

    @allow_dys_func
    def safe_help(a):
        """
        Returns the docstring of the given object.
        """
        if not a.__doc__:
            return ""
        return dedent(a.__doc__).strip()

    sandbox.scope.dicts[0]["help"] = safe_help

    @allow_dys_func
    def emit_event(key: str, value: str) -> typing.Any:
        """
        Emits an event to the blockchain.

        :param key: the key of the event (string)
        :param value: the value of the event (string)

        :returns: the response from the chain
        """
        if not isinstance(value, str):
            raise ValueError("emit_event value must be a string")
        if not isinstance(key, str):
            raise ValueError("emit_event key must be a string")
        resp = _chain("EmitEvent", key=key, value=value)
        if resp.get("exception"):
            raise Exception(resp["exception"])
        return resp["result"]

    @allow_dys_func
    def get_gas_consumed():
        """
        The total amount of gas consumed so far.
        """
        return gas_state["gas_consumed"] + gas_state["unconsumed_size"]

    @allow_dys_func
    def get_gas_limit():
        """
        The maximum amount of gas that can be used in this query or transaction
        """
        return gas_state["gas_limit"]

    @allow_dys_func
    def get_nodes_called():
        """
        The number of Python AST nodes evaluated in this query or transaction
        """
        return gas_state["nodes_called"]

    @allow_dys_func
    def get_cumulative_size():
        """
        The cumulative size of memory used for each node called in this query or script
        """
        return gas_state["cumsize"]

    @allow_dys_func
    def get_script_address() -> str:
        """
        Returns the address of this current script.
        """
        return script.get("address")

    @allow_dys_func
    def get_script_version() -> str:
        """
        Returns the version of this current script.
        """
        return script.get("version")

    @allow_dys_func
    def get_script_code() -> str:
        """
        Returns the source code of this current script.
        """
        return script.get("code", "")

    @allow_dys_func
    def get_script_name() -> str:
        """
        Returns the script name used in the execution message, if provided.
        Returns empty string if not provided.
        """
        return msg.get("script_name", "")

    @allow_dys_func
    def get_executor_address() -> str:
        """
        Returns the address of the caller of this script.
        """
        return msg.get("executor_address", None)

    @allow_dys_func
    def get_block_info() -> dict:
        """
        Returns a dictionary containing the following block header information:
        - Height (int): The height of the block
        - Hash (bytes): The hash of the block header
        - Time (string): The time of the block in ISO format
        - AppHash (bytes): AppHash used in the current block header
        - ChainID (string): The chain ID of the block
        """
        return {
            "height": block_info.get("Height", None),
            "hash": block_info.get("Hash", None),
            "time": block_info.get("Time", None),
            "app_hash": block_info.get("AppHash", None),
            "chain_id": block_info.get("ChainID", None),
        }

    @allow_dys_func
    def get_attached_messages():
        """
        Returns the nfts sent to this function.
        """
        return msg.get("attached_messages", [])

    @allow_dys_func
    def get_attached_msg_results():
        """
        Returns the results of the attached messages.
        """
        return attached_msg_results

    @allow_dys_func
    def dys_eval(
        code,
        scope=None,
        max_node_calls=None,
        max_scope_size=None,
        track_func=None,
        module_dict=None,
    ):
        """
        Evaluate a string of Dsyon Protocol code.

        :param code: the code to evaluate
        :param scope: the scope to evaluate the code in
        :param track_func: a function to call after each node is evaluated use to track gas or scope size
        :param module_dict: a dictionary of modules to make available for import in the sandbox.
                            Keys are module names, values are dicts of attributes.
                            Example: {"json": {"loads": json.loads}, "foo": {"bar": my_custom_func}}

        :returns: the result of the evaluation

        """

        sandbox = ScopedDysonEval(
            scope=scope,
            local_track_func=track_func,
            max_node_calls=max_node_calls,
            max_scope_size=max_scope_size,
            modules=dyslang.make_modules(module_dict or {}),
        )
        result = sandbox.eval(code)
        sandbox.consume_gas()
        if not result:
            return None
        return result[-1]

    @allow_dys_func
    def list_functions():
        """
        Returns a copy of the set of whitelisted functions available in the Dyson Protocol environment.
        """
        return sorted(set(dyslang.WHITELIST_FUNCTIONS))

    @allow_dys_func
    def list_modules():
        """
        Returns a dictionary of available modules and their functions in the Dyson Protocol environment.
        The returned dictionary has module names as keys and lists of available functions as values.
        """
        modules_dict = {}
        for module_name, module_content in module_dict.items():
            if isinstance(module_content, dict):
                modules_dict[module_name] = {
                    k: safe_help(v) for k, v in module_content.items()
                }
            else:
                modules_dict[module_name] = {}
        return modules_dict

    @allow_dys_func
    def _msg(params):
        """
        Wrapper function for _chain("Msg") that JSON encodes the params argument.

        :param params: A dictionary of parameters to be JSON encoded and passed to _chain
        :returns: The response from the chain
        """
        resp = _chain(
            "Msg",
            json_msg=json.dumps(
                params,
                separators=(",", ":"),
                check_circular=True,
                indent=None,
                sort_keys=True,
                cls=DecimalEncoder,
            ),
        )
        if resp.get("exception"):
            raise DysMsgException(resp["exception"])
        return resp["result"]

    @allow_dys_func
    def _query(params, query_height=None):
        """
        Wrapper function for _chain("Query") that JSON encodes the params argument.

        :param params: A dictionary of parameters to be JSON encoded and passed to _chain
        :returns: The response from the chain
        """
        resp = _chain(
            "Query",
            json_query=json.dumps(
                params,
                separators=(",", ":"),
                check_circular=True,
                indent=None,
                sort_keys=True,
                cls=DecimalEncoder,
            ),
        )
        if resp.get("exception", None):
            raise DysQueryException(resp["exception"])

        return resp["result"]

    @allow_dys_func
    def deprecated_chain(method, **params):
        """
        DEPRECATED: Use _msg() and _query() functions instead.

        :raises DeprecationError: Always raises this error to encourage migration to _msg and _query
        """
        raise DeprecationError(
            "The _chain function is deprecated. Please use _msg() for transactions and _query() for queries instead. "
            "Example: replace _chain('Msg', json_msg=json.dumps(params)) with _msg(params)"
        )

    module_dict = get_module_dict()

    module_dict["dys"] = {
        "get_gas_consumed": get_gas_consumed,
        "get_gas_limit": get_gas_limit,
        "get_script_address": get_script_address,
        "get_script_version": get_script_version,
        "get_script_code": get_script_code,
        "get_script_name": get_script_name,
        "get_executor_address": get_executor_address,
        "get_block_info": get_block_info,
        "get_nodes_called": get_nodes_called,
        "get_cumulative_size": get_cumulative_size,
        "emit_event": emit_event,
        "get_attached_messages": get_attached_messages,
        "get_attached_msg_results": get_attached_msg_results,
        "dys_eval": dys_eval,
        "list_functions": list_functions,
        "list_modules": list_modules,
        "_msg": _msg,
        "_query": _query,
        "_chain": deprecated_chain,
        "DysMsgException": DysMsgException,
        "DysQueryException": DysQueryException,
    }

    sandbox.modules = dyslang.make_modules(module_dict)
    return sandbox


def eval_script(
    port,
    script,
    msg=None,
    attached_msg_results=None,
    block_info=None,
):
    result = None
    stdout = None
    exception = None
    sandbox = None
    # Port is non-deteministic, don't output it in the logs

    msg = msg or {}
    attached_msg_results = attached_msg_results or []
    block_info = block_info or {}

    if "Time" not in block_info:
        raise Exception("Time not in block_info: %s" % block_info)
    with freeze_time(block_info["Time"]):
        with io.StringIO() as buf, redirect_stdout(buf):
            try:
                sandbox = build_sandbox(
                    msg,
                    script,
                    attached_msg_results,
                    block_info,
                    port,
                )
                sandbox.consume_gas()

                random.seed(
                    json.dumps(
                        {
                            "block_info": block_info,
                            "msg": msg,
                            "script": script,
                            "attached_msg_results": attached_msg_results,
                        },
                        separators=(",", ":"),
                        sort_keys=True,
                        cls=DecimalEncoder,
                    )
                )
                result = (
                    sandbox.eval(
                        script["code"] + "\n" + msg["extra_code"],
                    )
                    or [None]
                )[-1]
                scope = sandbox.scope.flatten()
                public_scope_all = scope.get(
                    "__all__",
                    [
                        k
                        for k, v in scope.items()
                        if getattr(v, "__module__", None) == "script"
                        and not k.startswith("_")
                        and k not in ["wsgi"]
                    ],
                )

                if msg["function_name"]:
                    if msg["function_name"] in scope:
                        if msg["function_name"] in public_scope_all:
                            # parse the args and kwargs from json
                            args = json.loads(msg["args"] or "[]")
                            assert isinstance(args, list), "args must be a list"
                            kwargs = json.loads(msg["kwargs"] or "{}")
                            assert isinstance(kwargs, dict), "kwargs must be a dict"
                            if not callable(scope[msg["function_name"]]):
                                raise Exception(
                                    f"function not callable: {msg['function_name']}"
                                )
                            result = scope[msg["function_name"]](*args, **kwargs)
                            if msg["function_name"].startswith("test_"):
                                result = sorted(
                                    sandbox._seen_nodes.items(),
                                    key=(
                                        lambda x: (x[0][0], x[0][1], -x[0][2], -x[0][3])
                                    ),
                                )
                        else:
                            raise Exception(
                                f"function not public: {msg['function_name']}"
                            )
                    else:
                        raise Exception(
                            f"function not defined [{msg['function_name']}] available functions: {public_scope_all}"
                        )
                # consume final gas
                sandbox.consume_gas()
            except dyslang.DysRuntimeError as e:
                exception = e
                # print("========== DysRuntimeError", e.lineno, e.col_offset, e.end_lineno, e.end_col_offset, getattr(e, "__context__", None))
            except Exception as e:
                exception = e
                # print("========== Exception", type(e), type(type(e)), type(e).__module__)
            finally:
                stdout = buf.getvalue()[-10000:]

    if exception is not None:
        try:
            source_code = script["code"] + "\n" + msg["extra_code"]
            exception_dict = {
                "class": exception.__class__.__name__,
                "msg": str(exception),
                "lineno": getattr(exception, "lineno", 0),
                "col_offset": getattr(exception, "col_offset", 0),
                "end_lineno": getattr(exception, "end_lineno", 0),
                "end_col_offset": getattr(exception, "end_col_offset", 0),
                "context": "NoneType",  # Default value
                "source_segment": "",
            }
            if hasattr(exception, "node") and exception.node is not None:
                exception_dict["source_segment"] = ast.get_source_segment(
                    source_code, exception.node
                )

            # Safely get context class name
            if hasattr(exception, "__context__") and exception.__context__ is not None:
                if not isinstance(exception.__context__, bool) and hasattr(
                    exception.__context__, "__class__"
                ):
                    exception_dict["context"] = exception.__context__.__class__.__name__

            exception = exception_dict
        except Exception as e:
            # If anything goes wrong during exception processing, use a simple fallback
            exception = {
                "class": "Exception",
                "msg": (
                    str(exception) if hasattr(exception, "__str__") else "Unknown error"
                ),
                "lineno": 0,
                "col_offset": 0,
                "end_lineno": 0,
                "end_col_offset": 0,
                "context": f"dysvm_server: {e}",
            }

    return sandbox, {
        "result": result,
        "stdout": stdout,
        "exception": exception,
        # TODO wait for gas fix
        # https://github.com/tendermint/vue/issues/147
        # https://github.com/tendermint/starport/blob/develop/starport/pkg/cosmosgen/templates/vuex/store/index.ts.tpl#L170
        "nodes_called": sandbox.modules.dys.get_nodes_called() if sandbox else None,
        "gas_limit": sandbox.modules.dys.get_gas_limit() if sandbox else None,
        "script_gas_consumed": (
            sandbox.modules.dys.get_gas_consumed() if sandbox else None
        ),
        "cumsize": sandbox.modules.dys.get_cumulative_size() if sandbox else None,
    }


dyslang.WHITELIST_FUNCTIONS.update(
    [
        "dyslang.dysvm_server.DysQueryException",
        "dyslang.dysvm_server.DysMsgException",
        # Freezegun: time-generating functions
        "freezegun.api.FakeDatetime.astimezone",
        "freezegun.api.FakeDatetime.combine",
        "freezegun.api.FakeDatetime.ctime",
        "freezegun.api.FakeDatetime.date",
        "freezegun.api.FakeDatetime.dst",
        "freezegun.api.FakeDatetime.fromisoformat",
        "freezegun.api.FakeDatetime.fromtimestamp",
        "freezegun.api.FakeDatetime.isoformat",
        "freezegun.api.FakeDatetime.now",
        "freezegun.api.FakeDatetime.replace",
        "freezegun.api.FakeDatetime.strptime",
        "freezegun.api.FakeDatetime.time",
        "freezegun.api.FakeDatetime.timestamp",
        "freezegun.api.FakeDatetime.timetuple",
        "freezegun.api.FakeDatetime.timetz",
        "freezegun.api.FakeDatetime.tzname",
        "freezegun.api.FakeDatetime.utcfromtimestamp",
        "freezegun.api.FakeDatetime.utcnow",
        "freezegun.api.FakeDatetime.utcoffset",
        "freezegun.api.FakeDatetime.utctimetuple"
        # Datetime: parsing/formatting functions
        "Datetime.astimezone",
        "Datetime.combine",
        "Datetime.ctime",
        "Datetime.date",
        "Datetime.dst",
        "Datetime.fromisoformat",
        "Datetime.fromtimestamp",
        "Datetime.isoformat",
        "Datetime.now",
        "Datetime.replace",
        "Datetime.strptime",
        "Datetime.time",
        "Datetime.timestamp",
        "Datetime.timetuple",
        "Datetime.timetz",
        "Datetime.tzname",
        "Datetime.utcfromtimestamp",
        "Datetime.utcnow",
        "Datetime.utcoffset",
        "Datetime.utctimetuple",
        # decimal
        "Decimal.to_integral_value",
        "Decimal.to_integral",
        "Decimal.to_integral_exact",
        "Decimal.round",
        "Decimal.quantize",
        "Decimal.as_integer_ratio",
        "Decimal.as_tuple",
        "Decimal.exp",
        "Decimal.sqrt",
        # re2.Match.re
        "re2._Regexp.match",
        "re2._Match.groupdict",
        "re2._Match.groups",
        "Match.group",
        "Match.groupdict",
        "Match.start",
        "Match.end",
        "Match.span",
        "Match.pos",
        "Match.endpos",
        "Match.re",
        "contains",
        "count",
        "findall",
        "finditer",
        "fullmatch",
        "match",
        "scanner",
        "search",
        "split",
        # BytesIO
        "BytesIO.read",
        "bytes.decode",
        "bytes.join",
        "bytes.hex",
        # str
        "str.capitalize",
        "str.casefold",
        "str.count",
        "str.encode",
        "str.endswith",
        "str.find",
        "str.index",
        "str.isalnum",
        "str.isalpha",
        "str.isascii",
        "str.isdecimal",
        "str.isdigit",
        "str.isidentifier",
        "str.islower",
        "str.isnumeric",
        "str.isprintable",
        "str.isspace",
        "str.istitle",
        "str.isupper",
        "str.join",
        "str.lower",
        "str.lstrip",
        "str.partition",
        "str.removeprefix",
        "str.removesuffix",
        "str.rfind",
        "str.rindex",
        "str.rpartition",
        "str.rsplit",
        "str.rstrip",
        "str.split",
        "str.splitlines",
        "str.startswith",
        "str.strip",
        "str.swapcase",
        "str.title",
        "str.upper",
        # set
        "set.update",
        "set.intersection_update",
        "set.difference_update",
        "set.symmetric_difference_update",
        "set.add",
        "set.remove",
        "set.discard",
        "set.pop",
        "set.clear",
        # list
        "list.append",
        "list.clear",
        "list.copy",
        "list.count",
        "list.extend",
        "list.index",
        "list.insert",
        "list.pop",
        "list.remove",
        "list.reverse",
        "list.sort",
        # dict
        "dict.clear",
        "dict.copy",
        "dict.fromkeys",
        "dict.get",
        "dict.items",
        "dict.keys",
        "dict.pop",
        "dict.popitem",
        "dict.setdefault",
        "dict.update",
        "dict.values",
        # Template
        "string.Template.safe_substitute",
        "string.Template.substitute",
        # random
        "Random.random",
        "random.Random.uniform",
        "random.Random.expovariate",
        "random.Random.choice",
        "random.Random.shuffle",
        "random.Random.sample",
        "random.Random.randint",
        # wsgi
        "wsgiref.handlers.BaseHandler.start_response",
        "wsgiref.handlers.BaseHandler.write",
        # hashlib
        "HASH.hexdigest",
        "HASH.digest",
        "HASH.update",
    ]
)


def allow_func(func=None):
    if callable(func):
        return _allow_func(func)
    return func


def allow_dys_func(function):
    if callable(function):
        try:
            function.__qualname__ = function.__name__
            function.__module__ = "dys"
            return wraps(function)(_allow_func)(function)
        except (AttributeError, TypeError):
            return function
    return function


def _allow_func(func):
    if not callable(func):
        return func

    # Ensure we have a valid callable with the necessary attributes
    try:
        modname = getattr(func, "__module__", None)
        qualname = getattr(
            func,
            "__qualname__",
            getattr(func, "__name__", getattr(func, "_name", None)),
        )

        if modname is not None and qualname is not None:
            fullname = modname + "." + qualname
            dyslang.WHITELIST_FUNCTIONS.add(fullname)
    except (AttributeError, TypeError):
        # If we can't get module or qualname, just skip adding to whitelist
        pass

    return func


def ascii_format_coverage(coverage, source):
    pct = sum(v > 0 for k, v in coverage) / len(coverage)
    # total = sum(v for k, v in coverage)
    out = ""
    for (r, c, name), v in coverage:
        if v:
            continue
        out += f"Missing {name} on line: {r} col: {c}\n"
        out += (source.splitlines()[r - 1]) + "\n"
        out += (c * "-") + "^\n"
    out += f"{ int(pct * 100) }% coverage\n"
    return out


def main(msg_json, script_json, attached_msg_results_json, block_info_json, port):
    msg = json.loads(msg_json)
    script = json.loads(script_json)
    attached_msg_results = json.loads(attached_msg_results_json)
    block_info = json.loads(block_info_json)
    port = int(port)

    print(
        json.dumps(
            {
                "msg": msg,
                "script": script,
                "attached_msg_results": attached_msg_results,
                "block_info": block_info,
                "port": port,
            },
            indent=2,
            cls=DecimalEncoder,
        )
    )

    # import time
    # time.sleep(100)

    _, response = eval_script(
        port,
        script,
        msg,
        attached_msg_results,
        block_info,
    )

    try:
        print(
            json.dumps(
                response,
                sort_keys=True,
                # default=repr,
                ensure_ascii=False,
                separators=(",", ":"),
                cls=DecimalEncoder,
            ),
            end="",
        )  # "end" is important for parsing in go
    except Exception as e:
        response["exception"] = f"Error in return value: {repr(e)}"
        response["result"] = None
        print(
            json.dumps(
                response,
                sort_keys=True,
                # default=repr,
                ensure_ascii=True,
                separators=(",", ":"),
                cls=DecimalEncoder,
            ),
            end="",
        )
        sys.exit(1)
    if response["exception"] is not None:
        sys.exit(1)
