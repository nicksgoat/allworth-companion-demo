from __future__ import annotations

from .models import ChatRequest, ChatResponse
from .tool_adapter import adapter


SUGGESTED_PROMPTS = [
    "Can I retire at 62?",
    "Should I do a Roth conversion this year?",
    "Find tax-loss harvesting opportunities.",
    "Review my portfolio drift.",
]


def classify_intent(text: str) -> tuple[str, str]:
    q = text.lower()
    if any(term in q for term in ["roth", "conversion"]):
        return "planning", "roth_conversion"
    if any(term in q for term in ["social security", "claiming", "claim at"]):
        return "planning", "social_security"
    if any(term in q for term in ["tax", "deduction", "bracket"]) and "loss" not in q:
        return "planning", "tax_optimization"
    if any(term in q for term in ["loss", "harvest", "tlh"]):
        return "portfolio", "tax_loss_harvesting"
    if "wash" in q:
        return "portfolio", "wash_sale_check"
    if any(term in q for term in ["portfolio", "drift", "allocation", "rebalance", "risk"]):
        return "portfolio", "portfolio_review"
    return "planning", "retirement_readiness"


async def answer_chat(request: ChatRequest) -> ChatResponse:
    latest = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
    family, analysis = classify_intent(latest)
    if family == "portfolio":
        result = await adapter.run_portfolio(analysis, request.portfolio)
    else:
        result = await adapter.run_planning(analysis, request.household)

    answer = (
        f"{result.summary}\n\n"
        "I would treat this as an advisor-prep answer: useful for narrowing the decision, "
        "but worth validating against live account, tax, and household data before action."
    )
    return ChatResponse(
        answer=answer,
        intent=analysis,
        result=result,
        suggested_prompts=[p for p in SUGGESTED_PROMPTS if p.lower() != latest.lower()][:3],
    )

