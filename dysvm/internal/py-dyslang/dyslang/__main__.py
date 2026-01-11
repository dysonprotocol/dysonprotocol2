import types


if __name__ == "__main__":
    import sys

    if sys.argv[1] == "exec_script":
        from . import dysvm_server

        dysvm_server.main(*sys.argv[2:])

    elif sys.argv[1] == "run_wsgi":
        from . import dyswsgi

        dyswsgi.main(*sys.argv[2:])

    elif sys.argv[1] == "run_benchmark":
        import json
        from . import fp_benchmark

        iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 100
        details = sys.argv[3].lower() == "true" if len(sys.argv) > 3 else True
        result = fp_benchmark.detect_fp_differences(iterations, details)
        print(json.dumps(result))

    elif sys.argv[1] == "dys_format":
        import black
        from . import DysEval

        code = sys.stdin.read()

        def _pos(exc):
            n = getattr(exc, "lineno", None)
            c = (
                getattr(exc, "offset", None)
                or getattr(exc, "col_offset", None)
                or getattr(exc, "colno", None)
            )
            if n is None:
                node = getattr(exc, "node", None)
                if node is not None:
                    n = getattr(node, "lineno", None)
                    c = getattr(node, "col_offset", None)
            return n, c

        try:
            DysEval().validate(code)
        except Exception as e:
            n, c = _pos(e)
            print(f"Error validating code: {e} line={n} col={c} type={type(e)}")
            sys.exit(1)

        try:
            formatted_code = black.format_str(code, mode=black.Mode())
            print(formatted_code)
        except Exception as e:
            n, c = _pos(e)
            if n is None:
                inner = getattr(e, "exc", None)
                if inner is not None:
                    n, c = _pos(inner)
            print(f"Error formatting code: {e} line={n} col={c}")
            sys.exit(1)

    elif sys.argv[1] == "extract_function_schema":
        import json
        from .dysvm_server import DecimalEncoder
        from .extract_schema import extract_function_schema

        # Args: script_json, block_info_json, port, executor_address, script_name
        script = json.loads(sys.argv[2])
        block_info = json.loads(sys.argv[3])
        port = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        executor_address = sys.argv[5]
        script_name = sys.argv[6]

        try:
            result = extract_function_schema(
                script=script,
                block_info=block_info,
                executor_address=executor_address,
                script_name=script_name,
                rpc_port=port,
            )
        except Exception as e:
            print(
                f"Error evaluating script: {e} line={getattr(e, 'lineno', None)} col={getattr(e, 'col_offset', None)}"
            )
            sys.exit(1)

        print(
            json.dumps(result, separators=(",", ":"), cls=DecimalEncoder),
            end="",
        )

    elif sys.argv[1] == "serve":
        import os
        import sys
        import uvicorn

        # Prefer argv for host/port (index 2,3) to avoid relying solely on environment
        host = (len(sys.argv) > 2 and sys.argv[2]) or os.getenv(
            "DYSLANG_HOST", "127.0.0.1"
        )
        port_env = (len(sys.argv) > 3 and sys.argv[3]) or os.getenv("DYSLANG_PORT", "0")
        try:
            port = int(port_env)
        except Exception:
            port = 0
        # Port 0 selects an ephemeral free port

        uvicorn.run(
            "dyslang.server_asgi:app",
            host=host,
            port=port,
            log_level="info",
            timeout_keep_alive=60,
            workers=30,
        )
