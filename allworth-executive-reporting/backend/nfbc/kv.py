"""Shared Azure Key Vault secret reader for NFBC (mirrors the sfp2/jira pattern).

IMPORTANT: the App Service managed identity must have get/list secret permission
on the vault AND the vault firewall must permit the app (VNet / trusted service).
Until IT grants that, reads fail with AccessDenied/Forbidden and callers fall
back to env vars. This module never raises — it returns None and records the
last error for /health diagnostics.
"""

from __future__ import annotations

import logging
import os
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

_VAULT = os.getenv("NFBC_KEY_VAULT_NAME", "allworthsynapse")
_VAULT_URL = f"https://{_VAULT}.vault.azure.net/"

_cache: dict[str, str] = {}
_lock = Lock()
_last_error: str | None = None


def _client():
    from azure.identity import (  # type: ignore
        ChainedTokenCredential,
        ClientSecretCredential,
        DefaultAzureCredential,
        ManagedIdentityCredential,
    )
    from azure.keyvault.secrets import SecretClient  # type: ignore

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
    creds.append(DefaultAzureCredential(
        exclude_environment_credential=True,
        exclude_managed_identity_credential=True,
    ))
    return SecretClient(vault_url=_VAULT_URL, credential=ChainedTokenCredential(*creds))


def get_secret(names) -> str | None:
    """Return the first non-empty secret among the candidate name(s), or None."""
    global _last_error
    if isinstance(names, str):
        names = [names]
    names = [n for n in names if n]
    if not names:
        return None
    cache_key = "|".join(names)
    with _lock:
        if cache_key in _cache:
            return _cache[cache_key]

    try:
        client = _client()
    except Exception as exc:
        _last_error = f"KV client init failed: {type(exc).__name__}: {exc}"
        logger.info("NFBC %s", _last_error)
        return None

    for n in names:
        try:
            val = client.get_secret(n).value
        except Exception as exc:
            _last_error = f"{n}: {type(exc).__name__}: {exc}"
            continue
        if val:
            with _lock:
                _cache[cache_key] = val
            _last_error = None
            logger.info("NFBC KV: resolved secret '%s' from vault %s", n, _VAULT)
            return val

    logger.warning("NFBC KV: no secret found among %s in vault %s (%s)",
                   names, _VAULT, _last_error)
    return None


def last_error() -> str | None:
    return _last_error


def vault_name() -> str:
    return _VAULT
