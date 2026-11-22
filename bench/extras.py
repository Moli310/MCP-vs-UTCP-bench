"""Checks run once before timing: correctness, response sizes, tool description sizes, environment.

Nothing in this file is timed. bench/run_bench.py adds these results to the CSV.
"""
import json
import os
import platform
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from importlib import metadata

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from utcp.utcp_client import UtcpClient

from shared.utcp_templates import API_TEMPLATE, MCP_TEMPLATE, ROOT

API_BASE = "http://127.0.0.1:8000"
PACKAGES = ["mcp", "fastapi", "uvicorn", "utcp", "utcp-http", "utcp-mcp"]


def rest_url(tool, args):
    """The REST address for each tool, built from the same arguments the benchmark uses."""
    if tool == "find_identity":
        return f"{API_BASE}/identities/search?{urllib.parse.urlencode(args)}"
    if tool == "get_entitlements":
        return f"{API_BASE}/identities/{urllib.parse.quote(args['user_id'])}/entitlements"
    if tool == "find_orphaned_accounts":
        return f"{API_BASE}/accounts/orphaned"
    raise ValueError(f"No REST address defined for tool '{tool}'")


def rest_body_bytes(tool, args):
    with urllib.request.urlopen(rest_url(tool, args), timeout=10) as resp:
        return len(resp.read())


def mcp_rows(result):
    """Rows from an MCP result: the structured copy if present, otherwise the text blocks."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and "result" in structured:
        return structured["result"]
    rows = []
    for block in result.content:
        if getattr(block, "type", "") == "text":
            data = json.loads(block.text)
            rows.extend(data if isinstance(data, list) else [data])
    return rows


def utcp_rows(value):
    """Rows from a UTCP result, whichever shape the library returns."""
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, dict) and "result" in value:
        value = value["result"]
    return value


def schema_dict(schema):
    if schema is None:
        return {}
    if hasattr(schema, "model_dump"):
        return schema.model_dump(exclude_none=True, by_alias=True)
    return schema


def llm_view_bytes(name, description, schema):
    """Size of what an AI agent reads for one tool: its name, description and input schema."""
    view = {"name": name, "description": description or "", "input_schema": schema_dict(schema)}
    return len(json.dumps(view, separators=(",", ":"), sort_keys=True).encode("utf-8"))


async def utcp_tools(client):
    """The tools a UTCP client registered. The library is young, so try two ways."""
    try:
        return await client.config.tool_repository.get_tools()
    except Exception:
        pass
    try:
        return await client.search_tools("", limit=100)
    except Exception:
        return None


def environment_info():
    packages = {}
    for name in PACKAGES:
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = "not installed"
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "os": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "packages": packages,
    }


async def collect_extras(cases):
    extras = {"environment": environment_info(), "correctness": {},
              "response_bytes": {}, "tool_description_bytes": {}}

    b_client = await UtcpClient.create(config={"manual_call_templates": [API_TEMPLATE]})
    c_client = await UtcpClient.create(config={"manual_call_templates": [MCP_TEMPLATE]})
    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "path_a_mcp.mcp_server"], cwd=str(ROOT))

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = (await session.list_tools()).tools
            extras["tool_description_bytes"]["A_mcp"] = sum(
                llm_view_bytes(t.name, t.description, t.inputSchema) for t in mcp_tools)
            for label, client in (("B_utcp_http", b_client), ("C_utcp_mcp_bridge", c_client)):
                tools = await utcp_tools(client)
                extras["tool_description_bytes"][label] = sum(
                    llm_view_bytes(t.name, t.description, getattr(t, "inputs", None))
                    for t in tools) if tools else None

            for tool, args in cases:
                a_result = await session.call_tool(tool, args)
                a_rows = mcp_rows(a_result)
                b_rows = utcp_rows(await b_client.call_tool("sql_api." + tool, args))
                c_rows = utcp_rows(await c_client.call_tool("sql_mcp.iam." + tool, args))
                extras["correctness"][tool] = {
                    "rows": len(a_rows),
                    "match": a_rows == b_rows == c_rows,
                }
                extras["response_bytes"][tool] = {
                    "rows": len(a_rows),
                    "rest_body": rest_body_bytes(tool, args),
                    "mcp_message": len(a_result.model_dump_json(
                        by_alias=True, exclude_none=True).encode("utf-8")),
                    "mcp_text_blocks": sum(
                        1 for b in a_result.content if getattr(b, "type", "") == "text"),
                    "mcp_has_structured_copy":
                        getattr(a_result, "structuredContent", None) is not None,
                }

    extras["all_match"] = all(c["match"] for c in extras["correctness"].values())
    return extras