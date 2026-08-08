"""Application configuration.

Centralizes runtime settings so the rest of the app never reaches for
environment variables directly. Kept simple for the MVP; swap for
pydantic-settings + Key Vault when wiring Azure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    app_name: str = "Allworth PlanEngine API"
    version: str = "1.0.0"
    environment: str = (os.getenv("APP_ENV") or "development").strip().lower()
    allowed_hosts: list[str] = field(default_factory=lambda: _split_csv(os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")))
    # Comma-separated list of allowed CORS origins.
    cors_origins: list[str] = field(
        default_factory=lambda: _split_csv(
            os.getenv(
                "PLANENGINE_CORS_ORIGINS",
                "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174",
            )
        )
    )
    # Maximum upload size in bytes (default 25 MB).
    max_upload_bytes: int = int(os.getenv("PLANENGINE_MAX_UPLOAD_BYTES", 25 * 1024 * 1024))
    # SQLAlchemy database URL. Example:
    # mssql+pyodbc://user:pass@server/database?driver=ODBC+Driver+18+for+SQL+Server
    database_url: str | None = (os.getenv("WAREHOUSE_DATABASE_URL") or "").strip() or None
    database_echo: bool = os.getenv("PLANENGINE_DATABASE_ECHO", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    # DataWarehouse pyodbc settings used when WAREHOUSE_DATABASE_URL is not set.
    dw_server: str | None = (os.getenv("DW_SERVER") or "").strip() or None
    dw_database: str | None = (os.getenv("DW_DATABASE") or "").strip() or None
    dw_port: str = (os.getenv("DW_PORT") or os.getenv("PORT") or "1433").strip()
    dw_user: str | None = (os.getenv("DW_USER") or "").strip() or None
    dw_password: str | None = (os.getenv("DW_PW") or os.getenv("DW_PASSWORD") or "").strip() or None
    odbc_driver: str = (os.getenv("ODBC_DRIVER") or "ODBC Driver 18 for SQL Server").strip("{}")
    db_encrypt: str = (os.getenv("PLANENGINE_DB_ENCRYPT") or "yes").strip()
    db_trust_server_certificate: str = (
        os.getenv("PLANENGINE_DB_TRUST_SERVER_CERTIFICATE") or "no"
    ).strip()
    db_autocommit: bool = os.getenv("PLANENGINE_DB_AUTOCOMMIT", "true").lower() in {
        "1",
        "true",
        "yes",
    }
    # ── Auth method (mirrors main branch) ──────────────────────────────────
    # ServicePrincipal  → AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID
    # SqlPassword       → DW_USER / DW_PW  (legacy, current default)
    # ActiveDirectoryInteractive → browser popup (local dev only)
    auth_method: str = (os.getenv("AUTH_METHOD") or "SqlPassword").strip()
    azure_client_id: str | None = (os.getenv("AZURE_CLIENT_ID") or "").strip() or None
    azure_client_secret: str | None = (os.getenv("AZURE_CLIENT_SECRET") or "").strip() or None
    azure_tenant_id: str | None = (os.getenv("AZURE_TENANT_ID") or "").strip() or None
    synapse_login_timeout: int = int(os.getenv("SYNAPSE_LOGIN_TIMEOUT", "15"))
    synapse_query_timeout: int = int(os.getenv("SYNAPSE_QUERY_TIMEOUT", "30"))
    auth_firm_id: str | None = (os.getenv("AUTH_FIRM_ID") or "").strip() or None


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


settings = Settings()
