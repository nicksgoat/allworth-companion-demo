"""Database connectivity helpers.

Provides a lazily initialized SQLAlchemy engine/session factory so the app
can run without a database for upload-only flows while enabling account-based
analysis when the database is configured.

Auth methods (set AUTH_METHOD env var — mirrors the main branch):
  ServicePrincipal         → AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID
  SqlPassword              → DW_USER, DW_PW  (legacy default)
  ActiveDirectoryInteractive → browser popup, local dev only
"""

from __future__ import annotations

from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from investments.config import settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def build_pyodbc_database_url(
    *,
    server: str,
    database: str,
    username: str,
    password: str,
    driver: str,
    port: str = "1433",
    encrypt: str = "yes",
    trust_server_certificate: str = "no",
) -> str:
    """Build a username/password SQLAlchemy URL for legacy callers/tests."""
    query = (
        f"driver={quote_plus(driver)}"
        f"&Encrypt={quote_plus(encrypt)}"
        f"&TrustServerCertificate={quote_plus(trust_server_certificate)}"
    )
    return (
        "mssql+pyodbc://"
        f"{quote_plus(username)}:{quote_plus(password)}"
        f"@{server}:{port}/{database}?{query}"
    )


def _build_conn_str() -> str:
    """Build the ODBC connection string from AUTH_METHOD (same logic as main branch)."""
    server = settings.dw_server or "allworthsynapse.sql.azuresynapse.net"
    database = settings.dw_database or "DataWarehouse"
    driver = f"{{{settings.odbc_driver}}}"
    encrypt = settings.db_encrypt
    trust = settings.db_trust_server_certificate

    method = settings.auth_method

    if method == "ServicePrincipal":
        client_id = settings.azure_client_id
        client_secret = settings.azure_client_secret
        tenant_id = settings.azure_tenant_id
        if not all([client_id, client_secret, tenant_id]):
            raise ValueError(
                "Service Principal credentials not configured. "
                "Set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, and AZURE_TENANT_ID."
            )
        return (
            f"DRIVER={driver};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"Authentication=ActiveDirectoryServicePrincipal;"
            f"UID={client_id}@{tenant_id};"
            f"PWD={client_secret};"
            f"Encrypt={encrypt};"
            f"TrustServerCertificate={trust}"
        )

    if method == "SqlPassword":
        username = settings.dw_user
        password = settings.dw_password
        if not all([username, password]):
            raise ValueError(
                "SQL credentials not configured. Set SYNAPSE_USERNAME and "
                "SYNAPSE_PASSWORD (or DW_USER and DW_PW locally)."
            )
        return (
            f"DRIVER={driver};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            f"Encrypt={encrypt};"
            f"TrustServerCertificate={trust}"
        )

    if method == "ActiveDirectoryInteractive":
        return (
            f"DRIVER={driver};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"Authentication=ActiveDirectoryInteractive;"
            f"Encrypt={encrypt};"
            f"TrustServerCertificate={trust}"
        )

    raise ValueError(
        f"Unknown AUTH_METHOD: {method!r}. "
        "Use ServicePrincipal, SqlPassword, or ActiveDirectoryInteractive."
    )


def resolve_database_url() -> str:
    """Resolve effective SQLAlchemy URL from explicit URL or AUTH_METHOD settings."""
    if settings.database_url:
        return settings.database_url

    conn_str = _build_conn_str()
    # SQLAlchemy mssql+pyodbc via raw connection string
    return f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}"


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            resolve_database_url(),
            echo=settings.database_echo,
            pool_pre_ping=True,
            pool_recycle=1500,
            isolation_level="AUTOCOMMIT" if settings.db_autocommit else None,
            future=True,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _session_factory
