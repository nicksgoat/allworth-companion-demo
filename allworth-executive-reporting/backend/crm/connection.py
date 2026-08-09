"""Shared read-only warehouse connection for CRM-domain repositories."""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

_connection: dict[str, Any] = {"value": None}
_connection_lock = Lock()


def get_db_connection():
    """Return a verified dedicated CRM warehouse connection.

    Reconnection is serialized so routes and workspace aggregations do not
    create competing connection holders or import one another's private APIs.
    """
    with _connection_lock:
        connection = _connection["value"]
        if connection is not None:
            try:
                cursor = connection.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                return connection
            except Exception as exc:  # stale network connection; reconnect below
                logger.warning("CRM warehouse connection was stale: %s", exc)
                _connection["value"] = None

        import pyodbc
        from nfbc.synapse_nfbc import build_connection_string

        connection = pyodbc.connect(build_connection_string(), timeout=60)
        connection.timeout = 60
        _connection["value"] = connection
        return connection
