import base64
import ast
import io
import json
import sys
from contextlib import redirect_stdout
from io import BytesIO
from freezegun import freeze_time
from wsgiref.simple_server import ServerHandler, WSGIRequestHandler, WSGIServer
from textwrap import dedent
from .dysvm_server import build_sandbox


def main(port, script_name, script_json, block_info_json, http_request):
    # print("DYSWSGI")
    # print("PORT", port)
    # print("SCRIPT_NAME", script_name)
    # print("SCRIPT", script_json)
    # print("BLOCK INFO", block_info_json)
    # print("HTTP REQUEST", http_request)

    class BetterServerHandler(ServerHandler):
        def error_output(self, environ, start_response):
            start_response(self.error_status, self.error_headers[:], sys.exc_info())
            _, exc, _ = sys.exc_info()
            lineno = getattr(exc, "lineno", None)
            col = getattr(exc, "col", None)
            return [
                f"Error: {exc} on line: {lineno} col: {col}\n\n".encode(),
                b"Logs:\n",
                buf.getvalue().encode(),
            ]

    class SimpleWSGIRequestHandler(WSGIRequestHandler):
        def finish(self):
            pass

        def setup(self):
            self.rfile = self.request[0]
            self.wfile = self.request[1]

        def handle(self):
            """Handle a single HTTP request"""

            self.raw_requestline = self.rfile.readline(65537)
            if len(self.raw_requestline) > 65536:
                self.requestline = ""
                self.request_version = ""
                self.command = ""
                self.send_error(414)
                return

            if not self.parse_request():  # An error code has been sent, just exit
                return

            handler = BetterServerHandler(
                self.rfile,
                self.wfile,
                self.get_stderr(),
                self.get_environ(),
                multithread=False,
            )
            handler.os_environ = dict()  # the key pa
            handler.request_handler = self  # backpointer for logging
            handler.run(self.server.get_app())

    class SimpleWSGIServer(WSGIServer):
        def setup(self):
            super().setup()

        def server_bind(self):
            """Override server_bind to store the server name."""
            self.server_port = ""
            self.server_name = "dysonprotocol"
            self.setup_environ()

        def handle_request(self, request_text, output):
            self.input = BytesIO(request_text.encode())
            self.output = output

            return self._handle_request_noblock()

        def get_request(self):
            return (self.input, self.output), ["0.0.0.0", ""]

        def shutdown_request(self, request):
            pass

        def close_request(self, request):
            pass

    script = json.loads(script_json)
    block_info = json.loads(block_info_json)

    with freeze_time(block_info["Time"]):
        with io.StringIO() as buf, redirect_stdout(buf):
            try:
                sandbox = build_sandbox(
                    msg={"script_name": script_name},
                    script=script,
                    attached_msg_results=None,
                    block_info=block_info,
                    port=port,
                )
                sandbox.consume_gas()
                sandbox.eval(script["code"])
                app = None
                if sandbox and (app := sandbox.scope.get("wsgi", None)):
                    s = SimpleWSGIServer("0.0.0.0", SimpleWSGIRequestHandler)
                    s.set_app(app)
                    output = BytesIO()
                    print("HTTP REQUEST", http_request)
                    s.handle_request(http_request, output)
                    wsgiout = output.getvalue()
                    print("WSGI OUT", wsgiout)
                elif app is None:
                    wsgiout = (
                        (
                            dedent(
                                f"""
                    HTTP/1.1 404
                    content-type: text/plain
                    
                    No WSGI Application defined on this DysonProtocol script.
                    
                    Dys name: {script_name if script_name else "None"}
                    Resolved address: {script["address"] if script["address"] else "None"}

                    Try this minimal Hello World example (WSGI):
                    ```python
                    def wsgi(environ, start_response):
                        start_response('200 OK', [('Content-Type', 'text/plain')])
                        return [b'Hello, world!']
                    ```

                    Logs:
                    """
                            )
                            + (buf.getvalue() or "<empty>")
                        )
                        .strip()
                        .encode()
                    )
                else:
                    wsgiout = f"""HTTP/1.1 500\ncontent-type: text/plain\n\nLogs:\n{buf.getvalue()}""".encode()
            except SyntaxError as e:
                wsgiout = (
                    dedent(
                        f"""
                        HTTP/1.1 500
                        content-type: text/plain
                        
                        SyntaxError: {e}
                        """
                    )
                    .strip()
                    .encode()
                )
            except Exception as e:
                import traceback

                lineno = getattr(e, "lineno", None)
                col_offset = getattr(e, "col_offset", None)
                end_lineno = getattr(e, "end_lineno", None)
                end_col_offset = getattr(e, "end_col_offset", None)
                col = getattr(e, "col", None)
                code_extract = ast.get_source_segment(script["code"], e.node)
                wsgiout = (
                    dedent(
                        f"""
                        HTTP/1.1 500
                        content-type: text/plain
                        
                        Exc: {e}
                        on line: {lineno} col: {col_offset} end_lineno: {end_lineno} end_col_offset: {end_col_offset}
                        
                        ```python
                        {code_extract}
                        ```

                        Logs:
                        {buf.getvalue()}"""
                    )
                    .strip()
                    .encode()
                )
                print("dyswsgi Execpetion:", traceback.format_exc())
            out = buf.getvalue()

    response_payload = json.dumps(
        {
            "response_b64": base64.b64encode(wsgiout).decode(),
            "logs": out,
        },
        separators=(",", ":"),
    )
    sys.stderr.write(out)
    print(response_payload, end="")
