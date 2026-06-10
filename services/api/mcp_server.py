# Allworth Client Intelligence MCP server (stdio).
#
# Per docs/MCP_INTEGRATION.md connector rules: MCP is a backend capability
# layer — read-only first, entitlement-scoped to one household (clientId is
# pinned server-side, never a tool parameter), and every result carries a
# source label and timestamp so downstream consumers treat it as a source
# episode, not final client truth.
import asyncio
import json
import os
import sys

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from data import iso_now
from tools import TOOL_DEFINITIONS, run_tool

CLIENT_ID = os.environ.get("ALLWORTH_CLIENT_ID", "maya")
SOURCE = "allworth-demo-backend"

# Read-only first: writes (update_client_profile) need approval + audit design.
READ_ONLY_TOOLS = [t for t in TOOL_DEFINITIONS if t["name"] != "update_client_profile"]

server = Server("allworth-client-intelligence", version="0.1.0")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name=t["name"], description=t["description"], inputSchema=t["input_schema"])
        for t in READ_ONLY_TOOLS
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> types.CallToolResult:
    if not any(t["name"] == name for t in READ_ONLY_TOOLS):
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Tool not available over MCP (read-only boundary): {name}")],
            isError=True,
        )
    data = run_tool(name, arguments or {}, CLIENT_ID)
    envelope = {
        "source": SOURCE,
        "tool": name,
        "clientId": CLIENT_ID,
        "retrieved_at": iso_now(),
        "read_only": True,
        "data": data,
    }
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(envelope, indent=2))],
        isError=bool(isinstance(data, dict) and data.get("error")),
    )


async def main():
    async with stdio_server() as (read, write):
        print(
            f"[mcp] allworth-client-intelligence ready (client: {CLIENT_ID}, {len(READ_ONLY_TOOLS)} read-only tools)",
            file=sys.stderr,
        )
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
