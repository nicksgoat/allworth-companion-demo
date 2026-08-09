"""Versioned relational persistence for governed workspace assignments."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path
from threading import Lock
from typing import Any

from sqlalchemy import Column, MetaData, String, Table, Text, create_engine, delete, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


metadata = MetaData()

schema_migrations = Table(
    "schema_migrations",
    metadata,
    Column("version", String(20), primary_key=True),
)

assignments = Table(
    "assignments",
    metadata,
    Column("id", String(120), primary_key=True),
    Column("name", String(240), nullable=False),
    Column("type", String(40), nullable=False),
    Column("home_tool_ids", Text, nullable=False),
    Column("created_at", String(40)),
    Column("created_by", String(320)),
)


class AssignmentRepository:
    """Transactional repository that works with SQLite and shared SQL databases.

    ``database_url_provider`` is evaluated lazily so test stores can relocate
    their database. Production should set ``ADMIN_ASSIGNMENTS_DATABASE_URL``
    to a durable SQLAlchemy URL; local development falls back to SQLite.
    """

    def __init__(self, database_url_provider: Callable[[], str]):
        self._database_url_provider = database_url_provider
        self._engine: Engine | None = None
        self._engine_url: str | None = None
        self._lock = Lock()

    def _get_engine(self) -> Engine:
        url = self._database_url_provider()
        with self._lock:
            if self._engine is None or self._engine_url != url:
                if self._engine is not None:
                    self._engine.dispose()
                connect_args = {"timeout": 10} if url.startswith("sqlite") else {}
                self._engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
                self._engine_url = url
                metadata.create_all(self._engine)
                with self._engine.begin() as connection:
                    existing = connection.execute(
                        select(schema_migrations.c.version).where(schema_migrations.c.version == "1")
                    ).first()
                    if existing is None:
                        connection.execute(insert(schema_migrations).values(version="1"))
            return self._engine

    @staticmethod
    def _decode(row: Any) -> dict[str, Any]:
        values = row._mapping
        return {
            "id": values["id"],
            "name": values["name"],
            "type": values["type"],
            "home_tool_ids": json.loads(values["home_tool_ids"]),
            "created_at": values["created_at"],
            "created_by": values["created_by"],
        }

    @staticmethod
    def _values(assignment: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": assignment["id"],
            "name": assignment["name"],
            "type": assignment.get("type", "general"),
            "home_tool_ids": json.dumps(assignment.get("home_tool_ids", [])),
            "created_at": assignment.get("created_at"),
            "created_by": assignment.get("created_by"),
        }

    def list(self) -> list[dict[str, Any]]:
        with self._get_engine().connect() as connection:
            rows = connection.execute(select(assignments).order_by(assignments.c.name, assignments.c.id)).all()
        return [self._decode(row) for row in rows]

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return {assignment["id"]: assignment for assignment in self.list()}

    def get(self, assignment_id: str) -> dict[str, Any] | None:
        with self._get_engine().connect() as connection:
            row = connection.execute(select(assignments).where(assignments.c.id == assignment_id)).first()
        return self._decode(row) if row else None

    def create(self, assignment: dict[str, Any]) -> dict[str, Any]:
        try:
            with self._get_engine().begin() as connection:
                connection.execute(insert(assignments).values(**self._values(assignment)))
        except IntegrityError as exc:
            raise ValueError(f"Assignment {assignment['id']} already exists") from exc
        return dict(assignment)

    def update(self, assignment_id: str, *, name: str, assignment_type: str,
               home_tool_ids: list[str]) -> dict[str, Any]:
        with self._get_engine().begin() as connection:
            result = connection.execute(
                update(assignments)
                .where(assignments.c.id == assignment_id)
                .values(name=name, type=assignment_type, home_tool_ids=json.dumps(home_tool_ids))
            )
            if result.rowcount != 1:
                raise ValueError(f"Unknown assignment {assignment_id}")
        resolved = self.get(assignment_id)
        if resolved is None:
            raise ValueError(f"Unknown assignment {assignment_id}")
        return resolved

    def delete(self, assignment_id: str) -> None:
        with self._get_engine().begin() as connection:
            result = connection.execute(delete(assignments).where(assignments.c.id == assignment_id))
            if result.rowcount != 1:
                raise ValueError(f"Unknown assignment {assignment_id}")

    def migrate_legacy(self, legacy_assignments: dict[str, dict[str, Any]]) -> None:
        if legacy_assignments and not self.list():
            self.replace_all(legacy_assignments.values())

    def replace_all(self, replacement_assignments: Iterable[dict[str, Any]]) -> None:
        values = [self._values(assignment) for assignment in replacement_assignments]
        with self._get_engine().begin() as connection:
            connection.execute(delete(assignments))
            if values:
                connection.execute(insert(assignments), values)


def sqlite_database_url(path: Path) -> str:
    return f"sqlite:///{path.resolve()}"
