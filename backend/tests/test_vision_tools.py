from __future__ import annotations

from allworth_api.core.tool_defs import TOOL_DEFINITIONS
from allworth_api.core.tool_runner import run_tool
from allworth_api.core.vision_tools import VISION_TOOL_NAMES


def test_allworth_ai_vision_tools_are_registered() -> None:
    tool_names = {tool["name"] for tool in TOOL_DEFINITIONS}

    assert {
        "get_client_context",
        "get_portfolio_analytics",
        "run_monte_carlo",
        "run_mock_rebalance",
        "get_document",
    } == VISION_TOOL_NAMES
    assert tool_names >= VISION_TOOL_NAMES


def test_get_client_context_matches_vision_shape() -> None:
    result = run_tool("get_client_context", {}, "maya")

    assert result["client_id"] == "maya"
    assert result["accounts"]
    assert result["goals"]
    assert "tax_bracket" in result
    assert "_diagnostics" not in result


def test_portfolio_analytics_reports_drift_and_concentration() -> None:
    result = run_tool("get_portfolio_analytics", {}, "maya")

    assert result["total_value"] > 0
    assert set(result["target_allocation"]) == {"cash", "equity", "fixed_income"}
    assert "drift_score" in result
    assert result["holdings"]
    assert result["concentration_flags"]


def test_vision_rebalance_wraps_tax_calculation() -> None:
    result = run_tool(
        "run_mock_rebalance",
        {"tax_bracket": 0.32, "loss_carryforward": 1000},
        "maya",
    )

    assert result["proposed_trades"]
    assert "tax_calculation" in result
    assert "underlying_rebalance" in result
    assert result["estimated_transition_cost"] >= 0


def test_document_tool_returns_qualitative_context() -> None:
    result = run_tool("get_document", {"document_type": "meeting_notes"}, "maya")

    assert result["document_type"] == "meeting_notes"
    assert result["key_extracts"]["advisor_notes"]
