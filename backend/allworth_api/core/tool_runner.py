"""Tool execution orchestration.

Concrete tool implementations live in focused registries:
- `financial_tools.tools` for the FINANCIAL_TOOLS.md contract
- `core.demo_tools` for legacy demo/app tools
"""

import time

from allworth_api.core.audit import estimate_tokens, log_tool_call
from allworth_api.core.demo_tools import is_demo_tool, run_demo_tool
from allworth_api.core.vision_tools import VISION_TOOL_NAMES, is_vision_tool, run_vision_tool
from allworth_api.data.seed import set_current_client
from allworth_api.financial_tools.tools import FINANCIAL_TOOL_NAMES, is_financial_tool, run_financial_tool

SCHEMA_GOVERNED_TOOLS = {"get_portfolio", *FINANCIAL_TOOL_NAMES, *VISION_TOOL_NAMES}


def run_tool(name: str, tool_input: dict | None, client_id: str) -> dict:
    """Execute a tool and return result wrapped with diagnostics."""
    # Bind the client so every tool reads the right client's seed.
    set_current_client(client_id)
    tool_input = tool_input or {}
    t0 = time.perf_counter()
    try:
        result = _dispatch(name, tool_input, client_id)
    except Exception as err:
        result = {
            "error": f"{name} failed: {err}",
            "hint": "Check the tool input shape and retry with values returned by prior tools.",
        }
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Append diagnostics envelope (timing + token estimates)
    if isinstance(result, dict) and "error" not in result and name not in SCHEMA_GOVERNED_TOOLS:
        result["_diagnostics"] = {
            "tool": name,
            "elapsed_ms": round(elapsed_ms, 1),
            "tokens_in": estimate_tokens(tool_input),
            "tokens_out": estimate_tokens(result),
        }

    # Audit trail
    log_tool_call(
        tool=name,
        client_id=client_id,
        params=tool_input,
        result=result,
        elapsed_ms=elapsed_ms,
    )
    return result


def _dispatch(name: str, tool_input: dict, client_id: str) -> dict:
    if is_vision_tool(name):
        return run_vision_tool(name, tool_input, client_id)
    if is_financial_tool(name):
        return run_financial_tool(name, tool_input, client_id)
    if is_demo_tool(name):
        return run_demo_tool(name, tool_input, client_id)
    return {"error": f"Unknown tool: {name}"}
