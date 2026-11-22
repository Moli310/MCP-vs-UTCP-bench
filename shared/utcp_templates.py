"""UTCP call templates, shared by the benchmark and the demo."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Path B: UTCP converts FastAPI's OpenAPI spec into tools named sql_api.<operation_id>
API_TEMPLATE = {
    "name": "sql_api",
    "call_template_type": "http",
    "http_method": "GET",
    "url": "http://127.0.0.1:8000/openapi.json",
}

# Path C: utcp-mcp launches the same MCP server as Path A.
# Tools are named sql_mcp.iam.<tool>. sys.executable uses your venv's Python.
MCP_TEMPLATE = {
    "name": "sql_mcp",
    "call_template_type": "mcp",
    "config": {"mcpServers": {"iam": {
        "command": sys.executable,
        "args": ["-m", "path_a_mcp.mcp_server"],
        "cwd": str(ROOT),
    }}},
}
