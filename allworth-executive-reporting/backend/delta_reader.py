"""
ADLS Gen2 Delta Lake reader for the executive-reporting backend.

Isolated from the Synapse/pyodbc code path on purpose: a failure to import
`deltalake` must not prevent the existing Synapse routes from booting. If the
wheel is missing or fails at runtime, `DELTA_AVAILABLE` is False and callers
should return a 503 rather than crash.

Auth reuses the existing Service Principal env vars used by Synapse:
  AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID
The SP must have **Storage Blob Data Reader** on the `silver` container of
`dlallworthai`.
"""
from __future__ import annotations

import os
from typing import Any

import pandas as pd

# Guarded import: a delta-rs install problem must not break the rest of the app.
try:
    from deltalake import DeltaTable  # type: ignore
    DELTA_AVAILABLE = True
    DELTA_IMPORT_ERROR: str | None = None
except Exception as _e:  # pragma: no cover - env-dependent
    DeltaTable = None  # type: ignore
    DELTA_AVAILABLE = False
    DELTA_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

ADLS_ACCOUNT_NAME = os.getenv('ADLS_ACCOUNT_NAME', 'dlallworthai')
ADLS_SILVER_CONTAINER = os.getenv('ADLS_SILVER_CONTAINER', 'silver')

TRANSFORMATION_LOG_PATH = (
    f"abfss://{ADLS_SILVER_CONTAINER}@{ADLS_ACCOUNT_NAME}"
    f".dfs.core.windows.net/logging/transformation_log/"
)


def _build_storage_options() -> dict[str, str]:
    """Assemble storage_options for delta-rs from env vars.

    Auth order:
      1. Storage account key (AZURE_STORAGE_ACCOUNT_KEY) — simple, works in
         any container; matches what the GitHub Actions deploy injects.
      2. Service Principal (AZURE_CLIENT_ID/_SECRET/_TENANT_ID)
      3. Managed Identity — enabled by AZURE_USE_MANAGED_IDENTITY=1 (App Service
         system- or user-assigned identity; no az CLI required in the container)
      4. Azure CLI (local dev only; requires `az login`)
    """
    opts: dict[str, str] = {
        'azure_storage_account_name': ADLS_ACCOUNT_NAME,
    }

    account_key = os.getenv('AZURE_STORAGE_ACCOUNT_KEY') or os.getenv('ADLS_ACCOUNT_KEY')
    client_id = os.getenv('AZURE_CLIENT_ID')
    client_secret = os.getenv('AZURE_CLIENT_SECRET')
    tenant_id = os.getenv('AZURE_TENANT_ID')
    use_msi = os.getenv('AZURE_USE_MANAGED_IDENTITY', '').lower() in ('1', 'true', 'yes')

    if account_key:
        opts['azure_storage_account_key'] = account_key
    elif client_id and client_secret and tenant_id:
        opts['azure_client_id'] = client_id
        opts['azure_client_secret'] = client_secret
        opts['azure_tenant_id'] = tenant_id
    elif use_msi:
        # App Service / VM managed identity. Set both naming conventions for
        # cross-version safety with object_store / delta-rs.
        opts['azure_use_azure_managed_identity'] = 'true'
        opts['use_azure_managed_identity'] = 'true'
        # If a user-assigned identity is targeted, expose its client id.
        msi_client_id = os.getenv('AZURE_MSI_CLIENT_ID')
        if msi_client_id:
            opts['azure_msi_client_id'] = msi_client_id
            opts['azure_client_id'] = msi_client_id
    else:
        # Local-dev fallback: `az login` identity. Both spellings accepted by
        # object_store; set both to be safe across delta-rs versions.
        opts['use_azure_cli'] = 'true'
        opts['azure_use_azure_cli'] = 'true'

    return opts


def read_delta_table(
    path: str,
    columns: list[str] | None = None,
    filters: Any | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """Read a Delta table from ADLS Gen2 into a pandas DataFrame.

    - columns: optional projection list (pyarrow pushdown)
    - filters: optional pyarrow.compute expression for row filtering
    - limit:   optional cap on rows returned (applied after filter)
    """
    if not DELTA_AVAILABLE:
        raise RuntimeError(
            f"deltalake package is not available: {DELTA_IMPORT_ERROR}"
        )

    dt = DeltaTable(path, storage_options=_build_storage_options())
    dataset = dt.to_pyarrow_dataset()

    scanner_kwargs: dict[str, Any] = {}
    if columns:
        scanner_kwargs['columns'] = columns
    if filters is not None:
        scanner_kwargs['filter'] = filters

    table = dataset.to_table(**scanner_kwargs)
    if limit is not None and limit >= 0:
        table = table.slice(0, limit)

    return table.to_pandas()


def get_schema(path: str) -> list[dict[str, str]]:
    """Return a lightweight [{name, type}] list for the Delta table schema."""
    if not DELTA_AVAILABLE:
        raise RuntimeError(
            f"deltalake package is not available: {DELTA_IMPORT_ERROR}"
        )

    dt = DeltaTable(path, storage_options=_build_storage_options())
    arrow_schema = dt.schema().to_arrow()
    return [{'name': f.name, 'type': str(f.type)} for f in arrow_schema]
