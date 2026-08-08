"""Azure Synapse ODBC connections, built from the app's ``AUTH_METHOD`` env path.

This is the single source of truth for the connection string that ``app.py``,
``catalog/sql_publish.py`` and ``nfbc/synapse_nfbc.py`` previously each built by
hand. It is a strict superset of all three: the four supported auth methods are
``ServicePrincipal``, ``SqlPassword``, ``ActiveDirectoryInteractive`` and
``AccessToken`` (an AAD token supplied out-of-band via ``AZURE_SQL_ACCESS_TOKEN``).

Callers keep their own connection *pools* and transaction semantics; this module
only owns the string and the low-level ``pyodbc.connect`` call (including the
AccessToken struct injection, which is easy to get wrong).
"""

from __future__ import annotations

import os
import struct
from typing import Any

# ODBC attribute id for an AAD access token (SQL_COPT_SS_ACCESS_TOKEN).
_SQL_COPT_SS_ACCESS_TOKEN = 1256


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def build_conn_str() -> str:
    """Return the ODBC connection string for the configured ``AUTH_METHOD``.

    Raises ``ValueError`` if the method is unknown or its required credentials
    are missing.
    """
    server = _env("SYNAPSE_SERVER", "allworthsynapse.sql.azuresynapse.net")
    database = _env("SYNAPSE_DATABASE", "DataWarehouse")
    driver = _env("ODBC_DRIVER", "{ODBC Driver 18 for SQL Server}")
    auth = _env("AUTH_METHOD", "ActiveDirectoryInteractive")
    base = f"DRIVER={driver};SERVER={server};DATABASE={database};"

    if auth == "AccessToken":
        # The token is injected via attrs_before in connect(); the string only
        # needs the encryption settings.
        return base + "Encrypt=yes;TrustServerCertificate=no"

    if auth == "ServicePrincipal":
        client_id = os.getenv("AZURE_CLIENT_ID")
        client_secret = os.getenv("AZURE_CLIENT_SECRET")
        tenant_id = os.getenv("AZURE_TENANT_ID")
        if not all([client_id, client_secret, tenant_id]):
            raise ValueError(
                "Service Principal credentials not configured. Set AZURE_CLIENT_ID, "
                "AZURE_CLIENT_SECRET, and AZURE_TENANT_ID"
            )
        return (
            base + "Authentication=ActiveDirectoryServicePrincipal;"
            f"UID={client_id}@{tenant_id};PWD={client_secret};"
            "Encrypt=yes;TrustServerCertificate=no"
        )

    if auth == "SqlPassword":
        username = os.getenv("SYNAPSE_USERNAME")
        password = os.getenv("SYNAPSE_PASSWORD")
        if not all([username, password]):
            raise ValueError(
                "SQL credentials not configured. Set SYNAPSE_USERNAME and SYNAPSE_PASSWORD"
            )
        return base + f"UID={username};PWD={password};Encrypt=yes;TrustServerCertificate=no"

    if auth == "ActiveDirectoryInteractive":
        return (
            base + "Authentication=ActiveDirectoryInteractive;"
            "Encrypt=yes;TrustServerCertificate=no"
        )

    raise ValueError(
        f"Unknown AUTH_METHOD: {auth}. "
        "Use ServicePrincipal, SqlPassword, ActiveDirectoryInteractive, or AccessToken"
    )


def connect(*, autocommit: bool = False, timeout: int | None = None) -> Any:
    """Open a pyodbc connection using ``build_conn_str()``.

    ``timeout`` bounds both the login and (via ``conn.timeout``) per-query time.
    When it is ``None`` the ``SYNAPSE_QUERY_TIMEOUT`` env var is used, defaulting
    to 60s. Under ``AUTH_METHOD=AccessToken`` the AAD token from
    ``AZURE_SQL_ACCESS_TOKEN`` is injected via ``attrs_before``.
    """
    import pyodbc

    conn_str = build_conn_str()
    if timeout is None:
        timeout = int(os.getenv("SYNAPSE_QUERY_TIMEOUT", "60"))

    if os.getenv("AUTH_METHOD") == "AccessToken":
        token = os.environ["AZURE_SQL_ACCESS_TOKEN"]
        # ODBC expects the UTF-16-LE token prefixed with its 4-byte length.
        token_bytes = token.encode("utf-16-le")
        token_struct = struct.pack("<i", len(token_bytes)) + token_bytes
        conn = pyodbc.connect(
            conn_str,
            autocommit=autocommit,
            timeout=timeout,
            attrs_before={_SQL_COPT_SS_ACCESS_TOKEN: token_struct},
        )
    else:
        conn = pyodbc.connect(conn_str, autocommit=autocommit, timeout=timeout)

    conn.timeout = timeout
    return conn
