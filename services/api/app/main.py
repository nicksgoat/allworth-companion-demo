from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .models import ChatRequest, ChatResponse, PlanningRunRequest, PortfolioRunRequest, ToolResult
from .orchestrator import answer_chat
from .tool_adapter import adapter

app = FastAPI(title="Allworth Mobile Planning API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "tool_mode": adapter.mode}


@app.get("/api/tools/catalog")
async def catalog() -> dict[str, list[dict[str, str]]]:
    return {"tools": adapter.catalog()}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return await answer_chat(request)


@app.post("/api/tools/planning/run", response_model=ToolResult)
async def run_planning(request: PlanningRunRequest) -> ToolResult:
    return await adapter.run_planning(request.analysis, request.household)


@app.post("/api/tools/portfolio/run", response_model=ToolResult)
async def run_portfolio(request: PortfolioRunRequest) -> ToolResult:
    return await adapter.run_portfolio(request.analysis, request.portfolio)

