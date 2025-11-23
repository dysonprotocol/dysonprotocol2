import json
import sys
from textwrap import dedent
import traceback
from typing import Any, Dict, Callable
from fastapi import FastAPI

from .dysvm_server import (
    eval_script,
    DecimalEncoder,
)


def _ok(result: Any) -> Dict[str, Any]:
    return {"ok": True, "result": result}


def _err_from_exc(e: Exception, source_code: str = "") -> Dict[str, Any]:
    lineno = getattr(e, "lineno", 0)
    col_offset = getattr(e, "col_offset", 0)
    end_lineno = getattr(e, "end_lineno", 0)
    end_col_offset = getattr(e, "end_col_offset", 0)
    context = getattr(e, "__class__", type("", (), {})).__name__
    try:
        # Try to pull source segment if node exists
        node = getattr(e, "node", None)
        if node is not None and source_code:
            import ast

            source_segment = ast.get_source_segment(source_code, node) or ""
        else:
            source_segment = ""
    except Exception:
        source_segment = ""
    return {
        "ok": False,
        "error": {
            "class": e.__class__.__name__,
            "msg": str(e),
            "lineno": lineno,
            "col_offset": col_offset,
            "end_lineno": end_lineno,
            "end_col_offset": end_col_offset,
            "context": context,
            "source_segment": source_segment,
        },
    }


async def _handle_exec_script(payload: Dict[str, Any]) -> Dict[str, Any]:
    msg_json = payload.get("msg_json", "{}")
    script_json = payload.get("script_json", "{}")
    attached_msg_results_json = payload.get("attached_msg_results_json", "[]")
    header_info_json = payload.get("header_info_json", "{}")
    rpc_port = int(payload.get("rpc_port", 0))
    try:
        _, response = eval_script(
            rpc_port,
            json.loads(script_json),
            json.loads(msg_json),
            json.loads(attached_msg_results_json),
            json.loads(header_info_json),
        )
        # If the script raised an exception, return ok=false to preserve legacy semantics
        if response.get("exception") is not None:
            # Preserve full response on error to match baseline shape
            print(f"##### _handle_exec_script <exception>{response}</exception>")
            return {"ok": False, "error": response}
        return _ok(
            json.dumps(
                response,
                separators=(",", ":"),
                sort_keys=True,
                ensure_ascii=True,
                cls=DecimalEncoder,
            )
        )
    except Exception as e:
        print(f"##### _handle_exec_script <error>{e}</error>")
        return _err_from_exc(e)


async def _handle_run_benchmark(payload: Dict[str, Any]) -> Dict[str, Any]:
    from . import fp_benchmark

    iterations = int(payload.get("iterations", 100))
    details = bool(payload.get("details", True))
    try:
        result = fp_benchmark.detect_fp_differences(iterations, details)
        return _ok(json.dumps(result, separators=(",", ":")))
    except Exception as e:
        return _err_from_exc(e)


async def _handle_dys_format(payload: Dict[str, Any]) -> Dict[str, Any]:
    import black
    from . import DysEval

    code = payload.get("code", "")
    print(f"##### _handle_dys_format <len_code>{len(code)}</len_code>")
    # Empty scripts are valid; bypass formatter to keep CLI/server parity.
    if code == "":
        return _ok("")
    try:
        DysEval().validate(code)
        print("is valid")
        formatted = black.format_str(code, mode=black.Mode())
        print(
            f"##### _handle_dys_format <len_formatted>{len(formatted)}</len_formatted>"
        )
        return _ok(formatted)
    except Exception as e:
        print(f"##### _handle_dys_format <error>{e}</error>")
        return _err_from_exc(e)


async def _handle_extract_function_schema(payload: Dict[str, Any]) -> Dict[str, Any]:
    import json as _json
    from .extract_schema import extract_function_schema

    script = _json.loads(payload.get("script_json", "{}"))
    block_info = _json.loads(payload.get("block_info_json", "{}"))
    rpc_port = int(payload.get("rpc_port", 0))
    executor_address = payload.get("executor_address", "")
    script_name = payload.get("script_name", "")
    try:
        result = extract_function_schema(
            script=script,
            block_info=block_info,
            executor_address=executor_address,
            script_name=script_name,
            rpc_port=rpc_port,
        )
        return _ok(json.dumps(result, separators=(",", ":"), cls=DecimalEncoder))
    except Exception as e:
        return _err_from_exc(e)


async def _handle_run_wsgi(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Reuse dyswsgi.main by capturing stdout (prints base64 response)
    import io
    from contextlib import redirect_stdout
    from . import dyswsgi

    script_name = payload.get("script_name", "")
    script_json = payload.get("script_json", "{}")
    block_info_json = payload.get("block_info_json", "{}")
    http_request = payload.get("http_request", "")
    rpc_port = int(payload.get("rpc_port", 0))
    try:
        f = io.StringIO()
        with redirect_stdout(f):
            dyswsgi.main(
                str(rpc_port), script_name, script_json, block_info_json, http_request
            )
        out = f.getvalue().strip()
        return _ok(out)
    except Exception as e:
        return _err_from_exc(e)


app = FastAPI()


@app.get("/health")
async def get_health() -> Dict[str, Any]:
    print(f"##### get_health")
    return {"ok": True, "version": sys.version}


@app.post("/exec_script")
async def post_exec_script(payload: Dict[str, Any]) -> Dict[str, Any]:
    print(f"##### post_exec_script")
    return await _handle_exec_script(payload)


@app.post("/run_benchmark")
async def post_run_benchmark(payload: Dict[str, Any]) -> Dict[str, Any]:
    print(f"##### post_run_benchmark")
    return await _handle_run_benchmark(payload)


@app.post("/dys_format")
async def post_dys_format(payload: Dict[str, Any]) -> Dict[str, Any]:
    print(f"##### post_dys_format")
    return await _handle_dys_format(payload)


@app.post("/extract_function_schema")
async def post_extract_function_schema(payload: Dict[str, Any]) -> Dict[str, Any]:
    print(f"##### post_extract_function_schema")
    return await _handle_extract_function_schema(payload)


@app.post("/run_wsgi")
async def post_run_wsgi(payload: Dict[str, Any]) -> Dict[str, Any]:
    print(f"##### post_run_wsgi")
    return await _handle_run_wsgi(payload)
