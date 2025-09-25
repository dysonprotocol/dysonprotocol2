import types
import ast
import io
from contextlib import redirect_stdout
from freezegun import freeze_time


def extract_function_schema(
    script, block_info, executor_address, script_name, rpc_port
):
    """Build a sandbox, evaluate script code, and extract public function schemas.

    Returns a list of {"function_name": str, "schema"|"error": any}.
    Raises exceptions from sandbox construction/evaluation to be handled by caller.
    """
    from .dysvm_server import build_sandbox
    from function_schema.core import get_function_schema

    if "Time" not in block_info:
        raise Exception("Time not in block_info: %s" % block_info)

    with freeze_time(block_info["Time"]):
        with io.StringIO() as buf, redirect_stdout(buf):
            try:
                sandbox = build_sandbox(
                    msg={
                        "executor_address": executor_address,
                        "function_name": "",
                        "args": "[]",
                        "kwargs": "{}",
                        "extra_code": "",
                        "attached_messages": [],
                        "script_name": script_name,
                    },
                    script=script,
                    attached_msg_results=[],
                    block_info=block_info,
                    port=rpc_port,
                )
                # Evaluate script code only to populate scope
                sandbox.consume_gas()
                sandbox.eval(script.get("code", ""))
                sandbox.consume_gas()

                scope = sandbox.scope
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

                result = []
                for name in public_scope_all:
                    obj = scope.get(name)
                    if (
                        isinstance(obj, types.FunctionType)
                        and getattr(obj, "__module__", None) == "script"
                    ):
                        try:
                            result.append(
                                {
                                    "function_name": name,
                                    "schema": get_function_schema(obj, "openai"),
                                }
                            )
                        except Exception as e:
                            result.append({"function_name": name, "error": str(e)})

                return result
            except Exception as exception:
                # Return exception formatted like eval_script
                try:
                    source_code = script.get("code", "")
                    exception_dict = {
                        "class": exception.__class__.__name__,
                        "msg": str(exception),
                        "lineno": getattr(exception, "lineno", 0),
                        "col_offset": getattr(exception, "col_offset", 0),
                        "end_lineno": getattr(exception, "end_lineno", 0),
                        "end_col_offset": getattr(exception, "end_col_offset", 0),
                        "context": "NoneType",
                        "source_segment": "",
                    }
                    node = getattr(exception, "node", None)
                    if node is not None:
                        try:
                            exception_dict["source_segment"] = ast.get_source_segment(
                                source_code, node
                            )
                        except Exception:
                            pass
                    ctx = getattr(exception, "__context__", None)
                    if ctx is not None and not isinstance(ctx, bool):
                        try:
                            exception_dict["context"] = ctx.__class__.__name__
                        except Exception:
                            pass
                    return exception_dict
                except Exception:
                    return {
                        "class": "Exception",
                        "msg": str(exception),
                        "lineno": 0,
                        "col_offset": 0,
                        "end_lineno": 0,
                        "end_col_offset": 0,
                        "context": "extract_schema",
                        "source_segment": "",
                    }
