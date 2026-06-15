"""FastMCP server entrypoint:  python -m paperless141_mcp.server"""
from mcp.server.fastmcp import FastMCP
from . import tools

mcp = FastMCP("paperless141")


@mcp.tool()
async def session_status() -> dict:
    """Check whether the server currently holds a logged-in Paperless141 session."""
    return await tools.session_status()


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
