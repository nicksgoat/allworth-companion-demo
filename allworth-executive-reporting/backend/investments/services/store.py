"""In-memory portfolio store.

A small abstraction that holds uploaded portfolios for the lifetime of
the process. It mirrors the interface a real repository (Azure SQL via
SQLAlchemy) would expose, so swapping persistence in later is a localized
change. Thread-safe for the simple read/write patterns the API uses.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from investments.models.bond import Bond


@dataclass
class Portfolio:
    id: str
    name: str
    bonds: list[Bond]
    source_filename: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def account_ids(self) -> list[str]:
        seen: dict[str, None] = {}
        for bond in self.bonds:
            if bond.account_id:
                seen.setdefault(bond.account_id, None)
        return list(seen.keys())


class PortfolioStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, Portfolio] = {}

    def add(self, name: str, bonds: list[Bond], source_filename: str) -> Portfolio:
        portfolio = Portfolio(
            id=uuid.uuid4().hex[:12],
            name=name,
            bonds=bonds,
            source_filename=source_filename,
        )
        with self._lock:
            self._items[portfolio.id] = portfolio
        return portfolio

    def get(self, portfolio_id: str) -> Portfolio | None:
        with self._lock:
            return self._items.get(portfolio_id)

    def list(self) -> list[Portfolio]:
        with self._lock:
            return sorted(self._items.values(), key=lambda p: p.created_at, reverse=True)

    def bonds_for_accounts(self, portfolio_id: str, account_ids: list[str]) -> list[Bond] | None:
        portfolio = self.get(portfolio_id)
        if portfolio is None:
            return None
        if not account_ids:
            return list(portfolio.bonds)
        wanted = set(account_ids)
        return [b for b in portfolio.bonds if b.account_id in wanted]


# Process-wide singleton used by the routers.
store = PortfolioStore()
