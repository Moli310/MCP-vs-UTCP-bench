"""Path A: MCP server over stdio. Tools call the shared queries module."""
from mcp.server.fastmcp import FastMCP

from shared import queries

# WARNING log level matches the quiet uvicorn settings, so neither side pays for logging
mcp = FastMCP("iam-sql", log_level="WARNING")


@mcp.tool()
def find_identity(name: str) -> list[dict]:
    """Search identities by display name (partial match). Returns up to 10."""
    return queries.find_identity(name)


@mcp.tool()
def get_entitlements(user_id: str) -> list[dict]:
    """List the applications and entitlements held by one identity."""
    return queries.get_entitlements(user_id)


@mcp.tool()
def find_orphaned_accounts() -> list[dict]:
    """List accounts that are not correlated to any identity."""
    return queries.find_orphaned_accounts()


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
