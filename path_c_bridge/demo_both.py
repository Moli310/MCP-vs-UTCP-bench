"""Path C demo: one UTCP client calls the same tool via REST and via your MCP server."""
import asyncio
import logging

from utcp.utcp_client import UtcpClient

from shared.utcp_templates import API_TEMPLATE, MCP_TEMPLATE

# Hide library INFO logs so the output shows only the results
logging.disable(logging.INFO)


async def main():
    client = await UtcpClient.create(config={
        "manual_call_templates": [API_TEMPLATE, MCP_TEMPLATE]
    })
    args = {"user_id": "U1001"}
    via_rest = await client.call_tool("sql_api.get_entitlements", args)
    via_mcp = await client.call_tool("sql_mcp.iam.get_entitlements", args)
    print("Via REST (UTCP direct):", via_rest)
    print("Via MCP (utcp-mcp bridge):", via_mcp)
    print("Results match:", via_rest == via_mcp)


if __name__ == "__main__":
    asyncio.run(main())