"""API request/response schemas (the transport contract)."""

from __future__ import annotations

from pydantic import BaseModel


class PortfolioSummary(BaseModel):
    id: str
    name: str
    source_filename: str
    holdings: int
    accounts: list[str]
    created_at: str


class UploadResponse(BaseModel):
    portfolio: PortfolioSummary
    message: str


class AISummary(BaseModel):
    strengths: list[str]
    risks: list[str]
    concentration_warnings: list[str]
    reinvestment_needs: list[str]
    recommendations: list[str]
