from dys import _chain, dys_eval, get_script_address, get_executor_address
import json
from urllib.parse import parse_qs
from html import escape

# Dictionary of AST nodes with minimal examples
ast_examples = {
    # Basic literals and constants
    "Constant": "42",
    "FormattedValue": "f'The answer is {40 + 2}'",
    "JoinedStr": "f'Hello {\"world\"}'",
    # Collections
    "List": "[1, 2, 3]",
    "Tuple": "(1, 2, 3)",
    "Set": "{1, 2, 3}",
    "Dict": "{'a': 1, 'b': 2}",
    # Variables
    "Name_Load": "x = 1; x",
    "Name_Store": "x = 42",
    "Name_Del": "y = 10; del y",
    "Starred": "a, *b = [1, 2, 3, 4]; b",
    # Expressions
    "UnaryOp_Not": "not True",
    "UnaryOp_Invert": "~42",
    "UnaryOp_UAdd": "+42",
    "UnaryOp_USub": "-42",
    # Binary operations
    "BinOp_Add": "1 + 2",
    "BinOp_Sub": "1 - 2",
    "BinOp_Mult": "2 * 3",
    "BinOp_Div": "6 / 3",
    "BinOp_FloorDiv": "7 // 3",
    "BinOp_Mod": "7 % 3",
    "BinOp_Pow": "2 ** 3",
    "BinOp_LShift": "1 << 2",
    "BinOp_RShift": "8 >> 2",
    "BinOp_BitOr": "1 | 2",
    "BinOp_BitXor": "5 ^ 3",
    "BinOp_BitAnd": "5 & 3",
    "BinOp_MatMult": "# Not in basic Python: a @ b",
    # Boolean operations
    "BoolOp_And": "True and False",
    "BoolOp_Or": "True or False",
    # Comparisons
    "Compare_Eq": "1 == 1",
    "Compare_NotEq": "1 != 2",
    "Compare_Lt": "1 < 2",
    "Compare_LtE": "1 <= 2",
    "Compare_Gt": "2 > 1",
    "Compare_GtE": "2 >= 1",
    "Compare_Is": "1 is 1",
    "Compare_IsNot": "1 is not 2",
    "Compare_In": "1 in [1, 2, 3]",
    "Compare_NotIn": "0 not in [1, 2, 3]",
    # Function and method calls
    "Call": "len([1, 2, 3])",
    "Call_Kwargs": "dict(a=1, b=2)",
    "Call_Starred": "sum([1, 2, 3])",
    "Call_KwStarred": "dict(**{'a': 1, 'b': 2})",
    # Conditional expressions
    "IfExp": "1 if True else 2",
    # Attribute access
    "Attribute": "'hello'.upper()",
    # Subscripting
    "Subscript": "[1, 2, 3][0]",
    "Slice": "[1, 2, 3, 4][1:3]",
    # Comprehensions
    "ListComp": "[x for x in range(5)]",
    "SetComp": "{x for x in range(5)}",
    "DictComp": "{x: x*x for x in range(5)}",
    "GeneratorExp": "(x for x in range(5))",
    # Assignments
    "Assign": "x = 42",
    "AnnAssign": "x: int = 42",
    "AugAssign": "x = 1; x += 1",
    "NamedExpr": "(x := 42)",
    # Control flow
    "If": "if True: pass",
    "For": "for i in range(5): pass",
    "While": "while False: pass",
    "Break": "for i in range(5):\n    if i > 2: break",
    "Continue": "for i in range(5):\n    if i < 2: continue",
    # Exception handling
    "Try": "try:\n    1/0\nexcept ZeroDivisionError:\n    pass",
    "Raise": "try:\n    raise ValueError('example error')\nexcept ValueError:\n    pass",
    "Assert": "assert True, 'message'",
    # Function and class definitions
    "FunctionDef": "def func(x): return x*2",
    "Lambda": "lambda x: x*2",
    "Return": "def func(): return 42",
    "ClassDef": "class MyClass:\n    pass",
    # Import statements
    "Import": "try: import json\nexcept ImportError: pass",
    "ImportFrom": "try: from json import loads\nexcept ImportError: pass",
    # With statements
    "With": "with open('file.txt', 'w') as f: pass",
    # Async/await
    "AsyncFunctionDef": "async def func(): pass",
    "Await": "async def func():\n    await other_func()",
    "AsyncFor": "async def func():\n    async for i in aiter(): pass",
    "AsyncWith": "async def func():\n    async with acontext() as a: pass",
    # Yield expressions
    "Yield": "def gen(): yield 42",
    "YieldFrom": "def gen(): yield from [1, 2, 3]",
    # Others
    "Delete": "x = 1; del x",
    "Pass": "pass",
    "Global": "global x",
    "Nonlocal": "nonlocal x",
}


def evaluate_ast_example(node_type):
    """Evaluate a single AST example and return result with status"""
    if node_type not in ast_examples:
        return {
            "node_type": node_type,
            "code": None,
            "status": "unknown",
            "message": "Node type not found in examples",
        }

    code = ast_examples[node_type]
    if code.startswith("#"):
        return {
            "node_type": node_type,
            "code": code,
            "status": "skipped",
            "message": "",
        }

    try:
        # Try to evaluate the code
        result = dys_eval(code)
        return {
            "node_type": node_type,
            "code": code,
            "status": "success",
            "result": str(result),
        }
    except NotImplementedError as e:
        return {
            "node_type": node_type,
            "code": code,
            "status": "error",
            "message": "Not Implemented",
        }
    except Exception as e:
        raise Exception(
            "Bug in ast_explorer.py with node type: "
            + node_type
            + " <code>"
            + code
            + "</code> <error>"
            + str(e)
            + "</error>"
        ) from e


def wsgi(environ, start_response):
    """WSGI application for Dyson AST Explorer"""
    # Parse path and query string
    path = environ.get("PATH_INFO", "/")
    query_string = environ.get("QUERY_STRING", "")
    query_params = parse_qs(query_string)

    # Set default response headers
    response_headers = [("Content-Type", "text/html; charset=utf-8")]

    # Get node parameter (if any)
    node_type = query_params.get("node", [""])[0]

    if path == "/":
        # Main route now handles all functionality
        if not node_type:
            # List all AST node types in a table
            start_response("200 OK", response_headers)

            html = """<!DOCTYPE html>
            <html>
            <head>
                <title>Dyson AST Explorer</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; }
                    table { width: 100%; border-collapse: collapse; margin-top: 20px; }
                    th, td { padding: 8px; text-align: left; border: 1px solid #ddd; }
                    th { background-color: #4CAF50; color: white; }
                    tr:nth-child(even) { background-color: #f2f2f2; }
                    pre { background-color: #f5f5f5; padding: 5px; border-radius: 3px; margin: 0; }
                    .category-header { background-color: #f8f8f8; font-weight: bold; }
                    a { text-decoration: none; color: #0066cc; }
                    a:hover { text-decoration: underline; }
                </style>
            </head>
            <body>
                <h1>Dyson AST Explorer</h1>
                <p>Click on an AST node type to test if it's allowed in Dyson Protocol.</p>
                
                <table>
                    <tr>
                        <th>AST Node</th>
                        <th>Demo</th>
                        <th>Result</th>
                    </tr>
            """

            # Create categories
            categories = {
                "Literals and Constants": ["Constant", "FormattedValue", "JoinedStr"],
                "Collections": ["List", "Tuple", "Set", "Dict"],
                "Variables": ["Name_Load", "Name_Store", "Name_Del", "Starred"],
                "Expressions": [
                    "UnaryOp_Not",
                    "UnaryOp_Invert",
                    "UnaryOp_UAdd",
                    "UnaryOp_USub",
                ],
                "Binary Operations": [
                    "BinOp_Add",
                    "BinOp_Sub",
                    "BinOp_Mult",
                    "BinOp_Div",
                    "BinOp_FloorDiv",
                    "BinOp_Mod",
                    "BinOp_Pow",
                    "BinOp_LShift",
                    "BinOp_RShift",
                    "BinOp_BitOr",
                    "BinOp_BitXor",
                    "BinOp_BitAnd",
                    "BinOp_MatMult",
                ],
                "Boolean Operations": ["BoolOp_And", "BoolOp_Or"],
                "Comparisons": [
                    "Compare_Eq",
                    "Compare_NotEq",
                    "Compare_Lt",
                    "Compare_LtE",
                    "Compare_Gt",
                    "Compare_GtE",
                    "Compare_Is",
                    "Compare_IsNot",
                    "Compare_In",
                    "Compare_NotIn",
                ],
                "Function and Method Calls": [
                    "Call",
                    "Call_Kwargs",
                    "Call_Starred",
                    "Call_KwStarred",
                ],
                "Conditional Expressions": ["IfExp"],
                "Attribute Access": ["Attribute"],
                "Subscripting": ["Subscript", "Slice"],
                "Comprehensions": ["ListComp", "SetComp", "DictComp", "GeneratorExp"],
                "Assignments": ["Assign", "AnnAssign", "AugAssign", "NamedExpr"],
                "Control Flow": ["If", "For", "While", "Break", "Continue"],
                "Exception Handling": ["Try", "Raise", "Assert"],
                "Function and Class Definitions": [
                    "FunctionDef",
                    "Lambda",
                    "Return",
                    "ClassDef",
                ],
                "Import Statements": ["Import", "ImportFrom"],
                "With Statements": ["With"],
                "Async/Await": ["AsyncFunctionDef", "Await", "AsyncFor", "AsyncWith"],
                "Yield Expressions": ["Yield", "YieldFrom"],
                "Others": ["Delete", "Pass", "Global", "Nonlocal"],
            }

            # Generate HTML for each category
            for category, nodes in categories.items():
                html += f"""<tr class="category-header"><td colspan="3">{category}</td></tr>
"""

                for node in nodes:
                    if node in ast_examples:
                        html += f"""<tr>
<td><a href="/?node={node}">{node}</a></td>
<td><pre>{ast_examples[node]}</pre></td>
<td><iframe src="/?node={node}" width="100%" height="120" style="border:none;"></iframe></td>
</tr>
"""

            html += """
                </table>
            </body>
            </html>
            """

            return [html.encode("utf-8")]

        elif node_type != "all":
            # Display specific node details
            result = evaluate_ast_example(node_type)

            start_response("200 OK", response_headers)

            status_color = {
                "success": "green",
                "error": "red",
                "skipped": "gray",
                "unknown": "orange",
            }.get(result["status"], "black")

            html = f"""<!DOCTYPE html>
            <html>
            <head>
                <title>Dyson AST Explorer - {node_type}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .status {{ color: {status_color}; font-weight: bold; }}
                    pre {{ background-color: #f5f5f5; padding: 10px; border-radius: 5px; }}
                    table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                    th, td {{ padding: 8px; text-align: left; border: 1px solid #ddd; }}
                    th {{ background-color: #4CAF50; color: white; }}
                </style>
            </head>
            <body>
                <h1>Dyson AST Explorer - {node_type}</h1>
                <p><a href="/">Back to all nodes</a></p>
                
                <table>
                    <tr>
                        <th>AST Node</th>
                        <th>Example</th>
                        <th>Result</th>
                    </tr>
                    <tr>
                        <td>ast.{node_type}</td>
                        <td><pre>{result['code'] if result['code'] else 'No example available'}</pre></td>
                        <td>
            """

            if result["status"] == "success":
                html += f'<span class="status">SUCCESS</span><br><pre>{escape(result["result"])}</pre>'
            elif result["status"] == "error":
                html += f'<span class="status">ERROR</span><br><pre>{escape(result["message"])}</pre>'
            elif result["status"] == "skipped":
                html += f'<span class="status">SKIPPED</span><br><pre>{escape(result["message"])}</pre>'
            else:
                html += f'<span class="status">UNKNOWN</span><br><pre>{escape(result["message"])}</pre>'

            html += """
                        </td>
                    </tr>
                </table>
            </body>
            </html>
            """

            return [html.encode("utf-8")]

    # If we get here, the path wasn't found
    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"Not Found"]


# For direct execution
def test_single_node(node_name):
    """Function to test a single node when called directly via exec-script"""
    if node_name in ast_examples:
        return evaluate_ast_example(node_name)
    else:
        return {"error": "Node not found", "available_nodes": list(ast_examples.keys())}


def main():
    """Main function for direct script execution"""
    return {"message": "Use test_single_node() to test individual AST nodes"}
