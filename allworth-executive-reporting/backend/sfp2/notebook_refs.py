"""Inverted index of column names → notebook files that reference them.

Built once at app startup by walking ``SFP2_NOTEBOOK_DIR`` (default
``/app/synapse-notebooks`` inside the container). The index lets the
``/api/sfp2/diff`` endpoint annotate each row with ``referenced_in: [...]``
so the UI can flag columns that are still consumed by downstream notebooks
before someone removes them.

Tokenization is deliberately permissive (regex over raw cell text). It
catches ``df['Foo__c']``, ``"Foo__c"``, ``[Foo__c]``, comments, etc. It
does NOT catch dynamic column construction or ``SELECT *`` patterns —
treat the result as "best effort, lower-bound".
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from threading import Lock
from typing import Iterable

logger = logging.getLogger(__name__)

# Tokens that are too generic to be useful — they would match every notebook
# and produce noise. Salesforce custom columns (the ones users care about)
# all end in __c so they aren't filtered.
_GENERIC_DENYLIST: frozenset[str] = frozenset({
    'id', 'name', 'type', 'value', 'count', 'data', 'date', 'time',
    'true', 'false', 'none', 'null', 'self', 'cls', 'def', 'class',
    'return', 'import', 'from', 'as', 'if', 'else', 'elif', 'for',
    'while', 'in', 'and', 'or', 'not', 'is', 'lambda', 'with', 'try',
    'except', 'finally', 'raise', 'pass', 'break', 'continue',
    'print', 'len', 'str', 'int', 'float', 'list', 'dict', 'set',
    'tuple', 'bool', 'object', 'super', 'self', 'cls',
})

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_INDEX: dict[str, list[str]] = {}
_NOTEBOOK_COUNT: int = 0
_LOCK = Lock()


def _iter_cell_text(notebook_json: dict) -> Iterable[str]:
    """Yield every cell's source text from a Synapse notebook JSON."""
    cells = (notebook_json.get('properties') or {}).get('cells') or []
    for cell in cells:
        source = cell.get('source')
        if isinstance(source, list):
            yield ''.join(s for s in source if isinstance(s, str))
        elif isinstance(source, str):
            yield source


def build_index(notebook_dir: str) -> tuple[dict[str, list[str]], int]:
    """Walk ``notebook_dir`` for ``*.json`` and return (index, notebook_count).

    The returned index keys are lowercase tokens. Values are sorted lists of
    relative notebook paths (with forward slashes) where the token appears.
    """
    root = Path(notebook_dir)
    if not root.exists() or not root.is_dir():
        logger.warning('sfp2.notebook_refs: directory not found: %s', notebook_dir)
        return {}, 0

    raw: dict[str, set[str]] = {}
    notebook_count = 0

    for path in sorted(root.rglob('*.json')):
        try:
            with path.open('r', encoding='utf-8') as fh:
                doc = json.load(fh)
        except (OSError, ValueError) as e:
            logger.warning('sfp2.notebook_refs: skipped %s: %s', path, e)
            continue

        rel = path.relative_to(root).as_posix()
        notebook_count += 1
        seen_in_notebook: set[str] = set()
        for text in _iter_cell_text(doc):
            for match in _TOKEN_RE.findall(text):
                lower = match.lower()
                if lower in _GENERIC_DENYLIST:
                    continue
                seen_in_notebook.add(lower)
        for tok in seen_in_notebook:
            raw.setdefault(tok, set()).add(rel)

    index = {tok: sorted(refs) for tok, refs in raw.items()}
    return index, notebook_count


def init(notebook_dir: str | None = None) -> None:
    """Build the index from ``notebook_dir`` (or env ``SFP2_NOTEBOOK_DIR``).

    Safe to call multiple times. On failure the index is left empty and a
    warning is logged — the app must boot regardless.
    """
    global _INDEX, _NOTEBOOK_COUNT
    target = notebook_dir or os.getenv('SFP2_NOTEBOOK_DIR') or '/app/synapse-notebooks'
    try:
        index, count = build_index(target)
    except Exception as e:  # pragma: no cover - defensive
        logger.exception('sfp2.notebook_refs: build_index failed for %s', target)
        with _LOCK:
            _INDEX = {}
            _NOTEBOOK_COUNT = 0
        return
    with _LOCK:
        _INDEX = index
        _NOTEBOOK_COUNT = count
    logger.info(
        'sfp2.notebook_refs: indexed %d notebooks, %d unique tokens (dir=%s)',
        count, len(index), target,
    )


def references_for(column: str) -> list[str]:
    """Return notebook paths that reference ``column`` (case-insensitive)."""
    if not column:
        return []
    with _LOCK:
        return list(_INDEX.get(column.lower(), ()))


def stats() -> dict[str, int]:
    """Return basic stats for diagnostics."""
    with _LOCK:
        return {'notebooks': _NOTEBOOK_COUNT, 'tokens': len(_INDEX)}
