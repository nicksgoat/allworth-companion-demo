"""Azure credential helpers shared across the backend.

Two credential *shapes* were duplicated across the feature packages:

* **Storage credential** (``file_explorer/adls.py``, ``admin/store.py``,
  ``sfp2/delta_admin.py``): an account-key string when present, otherwise an
  azure-identity credential resolved as Service Principal → Managed Identity →
  Azure CLI. Suitable as the ``credential=`` for ``DataLakeServiceClient``.

* **Key Vault access** (``nfbc/kv.py``, ``nfbc/jira_client.py``,
  ``sfp2/salesforce_client.py``): a ``ChainedTokenCredential`` of Managed
  Identity → Service Principal → DefaultAzureCredential, wrapped in a
  ``SecretClient``.

All azure-identity imports are done lazily and guarded so a missing wheel never
breaks import of the backend; callers get ``None`` (storage) or a raised
``RuntimeError`` they already handle (Key Vault).
"""

from __future__ import annotations

import os
from typing import Any


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------- #
# Storage (ADLS) credential — account key OR an azure-identity credential
# --------------------------------------------------------------------------- #
def storage_credential() -> Any | None:
    """Return an ADLS credential: account-key string, an azure-identity
    credential, or ``None`` if azure-identity is unavailable and no key is set.

    Precedence: account key (``AZURE_STORAGE_ACCOUNT_KEY`` / ``ADLS_ACCOUNT_KEY``)
    → Service Principal (``AZURE_CLIENT_ID``/``_SECRET``/``_TENANT_ID``) →
    Managed Identity (when ``AZURE_USE_MANAGED_IDENTITY`` is truthy) → Azure CLI.
    """
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

    if _truthy(os.getenv("AZURE_USE_MANAGED_IDENTITY")):
        msi = os.getenv("AZURE_MSI_CLIENT_ID")
        return ManagedIdentityCredential(client_id=msi) if msi else ManagedIdentityCredential()

    try:
        return AzureCliCredential()
    except Exception:  # pragma: no cover - env-dependent
        return None


# --------------------------------------------------------------------------- #
# Key Vault — chained credential + SecretClient
# --------------------------------------------------------------------------- #
def keyvault_client(vault: str | None = None):
    """Return a ``SecretClient`` backed by a Managed Identity → Service
    Principal → DefaultAzureCredential chain.

    ``vault`` may be a bare name (``allworthsynapse``) or a full vault URL. When
    omitted, ``AZURE_KEY_VAULT_NAME`` (default ``allworthsynapse``) is used.
    Raises on import/config failure; callers already handle that by falling back
    to environment variables.
    """
    from azure.identity import (  # type: ignore
        ChainedTokenCredential,
        ClientSecretCredential,
        DefaultAzureCredential,
        ManagedIdentityCredential,
    )
    from azure.keyvault.secrets import SecretClient  # type: ignore

    name = vault or os.getenv("AZURE_KEY_VAULT_NAME", "allworthsynapse")
    vault_url = name if name.startswith("http") else f"https://{name}.vault.azure.net/"

    creds: list[Any] = []
    msi = os.getenv("AZURE_MSI_CLIENT_ID")
    creds.append(ManagedIdentityCredential(client_id=msi) if msi else ManagedIdentityCredential())
    cid, csec, tid = (
        os.getenv("AZURE_CLIENT_ID"),
        os.getenv("AZURE_CLIENT_SECRET"),
        os.getenv("AZURE_TENANT_ID"),
    )
    if cid and csec and tid:
        creds.append(ClientSecretCredential(tid, cid, csec))
    creds.append(
        DefaultAzureCredential(
            exclude_environment_credential=True,
            exclude_managed_identity_credential=True,
        )
    )
    return SecretClient(vault_url=vault_url, credential=ChainedTokenCredential(*creds))


def keyvault_secret(names, *, vault: str | None = None, default: str | None = None) -> str | None:
    """Return the first non-empty secret among ``names`` from Key Vault.

    ``names`` may be a single name or an iterable of candidate names. Never
    raises: on any failure it returns ``default``. For callers that need
    caching or error diagnostics (e.g. ``nfbc/kv.py``), use ``keyvault_client``
    directly and keep that logic local.
    """
    if isinstance(names, str):
        names = [names]
    names = [n for n in names if n]
    if not names:
        return default
    try:
        client = keyvault_client(vault)
    except Exception:
        return default
    for name in names:
        try:
            val = client.get_secret(name).value
        except Exception:
            continue
        if val:
            return val
    return default
