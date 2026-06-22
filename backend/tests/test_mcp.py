from __future__ import annotations

import asyncio
import json

from allworth_api import mcp as mcp_module


def test_mcp_tool_surface_is_read_only_and_includes_financial_tools() -> None:
    tools = asyncio.run(mcp_module.list_tools())
    tool_names = {tool.name for tool in tools}

    assert "simulate" in tool_names
    assert "rebalance" in tool_names
    assert "update_client_profile" not in tool_names
    assert "compare_scenarios" not in tool_names


def test_mcp_rejects_mutation_tools_and_wraps_read_results_with_provenance() -> None:
    denied = asyncio.run(
        mcp_module.call_tool(
            "update_client_profile",
            {"fact": "remember this forever", "category": "preferences"},
        )
    )

    assert denied.isError is True
    assert "read-only boundary" in denied.content[0].text

    result = asyncio.run(mcp_module.call_tool("get_accounts", {}))
    envelope = json.loads(result.content[0].text)

    assert result.isError is False
    assert envelope["source"] == mcp_module.SOURCE
    assert envelope["tool"] == "get_accounts"
    assert envelope["clientId"] == mcp_module.CLIENT_ID
    assert envelope["read_only"] is True
    assert "netWorth" in envelope["data"]
