"""ADLS Gen2 directory listing for File Explorer.

Isolated from ``delta_reader`` (which reads table *contents* via delta-rs). Here
we only need to *enumerate* the sub-directories of a root and confirm which ones
are Delta tables, so the UI can surface them without hardcoding table names.

Auth precedence matches ``delta_reader`` and ``admin.store``:
    1. Storage account key   (AZURE_STORAGE_ACCOUNT_KEY / ADLS_ACCOUNT_KEY)
    2. Service Principal      (AZURE_CLIENT_ID / _SECRET / _TENANT_ID)
    3. Managed Identity       (AZURE_USE_MANAGED_IDENTITY=1, optional AZURE_MSI_CLIENT_ID)
    4. Azure CLI              (local dev; `az login`)
"""

from __future__ import annotations

import os
from typing import Any, Optional

ADLS_ACCOUNT_NAME = os.getenv("ADLS_ACCOUNT_NAME", "dlallworthai")

try:
    from azure.storage.filedatalake import DataLakeServiceClient  # type: ignore

    ADLS_AVAILABLE = True
    ADLS_IMPORT_ERROR: Optional[str] = None
except Exception as _e:  # pragma: no cover - env-dependent
    DataLakeServiceClient = None  # type: ignore
    ADLS_AVAILABLE = False
    ADLS_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"


def _credential() -> Any:
    """Return an account-key string or an azure-identity credential, or None."""
    key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY") or os.getenv("ADLS_ACCOUNT_KEY")
    if key:
        return key
    try:
        from azure.identity import (  # type: ignore
            AzureCliCredential,
            ClientSecretCredential,
            ManagedIdentityCredential,
        )
    except Exception:  # pragma: no cover - env-dependent
        return None

    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    tenant_id = os.getenv("AZURE_TENANT_ID")
    if client_id and client_secret and tenant_id:
        return ClientSecretCredential(tenant_id, client_id, client_secret)
    if os.getenv("AZURE_USE_MANAGED_IDENTITY", "").lower() in ("1", "true", "yes"):
        msi = os.getenv("AZURE_MSI_CLIENT_ID")
        return ManagedIdentityCredential(client_id=msi) if msi else ManagedIdentityCredential()
    try:
        return AzureCliCredential()
    except Exception:  # pragma: no cover - env-dependent
        return None


def _service_client():
    if not ADLS_AVAILABLE:
        raise RuntimeError(
            f"azure-storage-file-datalake is not available: {ADLS_IMPORT_ERROR}"
        )
    return DataLakeServiceClient(
        account_url=f"https://{ADLS_ACCOUNT_NAME}.dfs.core.windows.net",
        credential=_credential(),
    )


def list_delta_tables(container: str, path: str) -> list[str]:
    """Return the names of immediate sub-directories under ``path`` that are
    Delta tables (contain a ``_delta_log`` folder), sorted alphabetically."""
    fs = _service_client().get_file_system_client(container)
    base = path.strip("/")
    prefix = f"{base}/" if base else ""

    names: list[str] = []
    for item in fs.get_paths(path=base or None, recursive=False):
        if not getattr(item, "is_directory", False):
            continue
        name = item.name
        if prefix and name.startswith(prefix):
            name = name[len(prefix):]
        name = name.strip("/")
        if name:
            names.append(name)

    tables = [n for n in names if _is_delta_table(fs, f"{prefix}{n}")]
    return sorted(tables)


def _is_delta_table(fs, table_path: str) -> bool:
    try:
        return fs.get_directory_client(f"{table_path.strip('/')}/_delta_log").exists()
    except Exception:  # pragma: no cover - network/permission dependent
        return False
