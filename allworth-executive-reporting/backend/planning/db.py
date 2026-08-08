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

from collections.abc import Generator
from urllib.parse import quote_plus

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from planning.config import settings

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
    server_endpoint = f"tcp:{server},{settings.dw_port}"
    encrypt = settings.db_encrypt
    trust = settings.db_trust_server_certificate
    timeout = settings.synapse_login_timeout

    method = settings.auth_method

    if method == "ServicePrincipal":
        client_id = settings.azure_client_id
        client_secret = settings.azure_client_secret
        tenant_id = settings.azure_tenant_id
        if not all([client_id, client_secret, tenant_id]) or any(
            "your-" in str(value).lower() for value in (client_id, client_secret, tenant_id)
        ):
            raise ValueError(
                "Service Principal credentials not configured. "
                "Set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, and AZURE_TENANT_ID."
            )
        return (
            f"DRIVER={driver};"
            f"SERVER={server_endpoint};"
            f"DATABASE={database};"
            f"Authentication=ActiveDirectoryServicePrincipal;"
            f"UID={client_id};"
            f"PWD={client_secret};"
            f"Encrypt={encrypt};"
            f"TrustServerCertificate={trust};"
            f"Connection Timeout={timeout}"
        )

    if method == "SqlPassword":
        username = settings.dw_user
        password = settings.dw_password
        if not all([username, password]):
            raise ValueError(
                "SQL credentials not configured. Set DW_USER and DW_PW."
            )
        return (
            f"DRIVER={driver};"
            f"SERVER={server_endpoint};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            f"Encrypt={encrypt};"
            f"TrustServerCertificate={trust};"
            f"Connection Timeout={timeout}"
        )

    if method == "ActiveDirectoryInteractive":
        return (
            f"DRIVER={driver};"
            f"SERVER={server_endpoint};"
            f"DATABASE={database};"
            f"Authentication=ActiveDirectoryInteractive;"
            f"Encrypt={encrypt};"
            f"TrustServerCertificate={trust};"
            f"Connection Timeout={timeout}"
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
            isolation_level="AUTOCOMMIT" if settings.db_autocommit else None,
            future=True,
        )

        @event.listens_for(_engine, "before_cursor_execute")
        def _synapse_long_strings(conn, cursor, statement, parameters, context,
                                  executemany):
            """Synapse dedicated pools have no ntext type, but pyodbc binds
            Python strings longer than 4000 chars as SQL_WLONGVARCHAR (ntext).
            Force long string params to nvarchar(max) at the driver level."""
            import pyodbc

            rows = parameters if executemany else [parameters]
            if not rows or not rows[0]:
                return
            sizes = [
                (pyodbc.SQL_WVARCHAR, 0, 0)
                if any(isinstance(row[index], str) and len(row[index]) > 2000
                       for row in rows)
                else None
                for index in range(len(rows[0]))
            ]
            if any(size is not None for size in sizes):
                cursor.setinputsizes(sizes)

        if settings.auth_firm_id:
            firm_id = settings.auth_firm_id

            @event.listens_for(_engine, "checkout")
            def _set_firm_context(dbapi_connection, _connection_record, _connection_proxy):
                """Reset the pooled connection's RLS tenant on every checkout."""
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute(
                        "EXEC sys.sp_set_session_context @key=N'firm_id', @value=?",
                        firm_id,
                    )
                finally:
                    cursor.close()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _session_factory


def get_db_session() -> Generator[Session, None, None]:
    """Request-scoped DB session generator."""
    try:
        session = get_session_factory()()
    except (RuntimeError, ValueError) as exc:
        raise RuntimeError(str(exc)) from exc
    try:
        yield session
    finally:
        try:
            session.close()
        except Exception:
            # Some SQL Server/Synapse scenarios can emit rollback errors when
            # no matching transaction exists; suppress on close.
            pass
