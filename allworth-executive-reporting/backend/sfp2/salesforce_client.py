"""Live Salesforce describe() helper backed by Key Vault-stored credentials.

Auth path:
  1. DefaultAzureCredential (uses the same AZURE_CLIENT_ID/_SECRET/_TENANT_ID
     Service Principal already configured for ADLS, or local az login)
  2. Pull 3 secrets from Key Vault `allworthsynapse`:
        - salesforceprodusername
        - Salesforce-Prod-Password
        - Salesforce-Prod-Token
  3. Build a simple_salesforce.Salesforce session and memoize for ~1 hour.

The SP must have **Key Vault Secrets User** on the `allworthsynapse` KV.

Key Vault is always the primary source of truth. As a backup, when
SFP2_ALLOW_ENV_SF_CREDS=1 and the Key Vault read fails (e.g. network
firewall / RBAC not yet in place), this module falls back to the
SF_USERNAME / SF_PASSWORD / SF_TOKEN env vars (injected from GitHub repo
secrets in the deploy workflow). The moment Key Vault becomes reachable it
takes precedence again — no redeploy needed.
"""
from __future__ import annotations

import logging
import os
import time
from threading import Lock
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Guarded imports — a missing wheel must not break the rest of the app.
try:
    from azure.identity import (  # type: ignore
        ChainedTokenCredential,
        ClientSecretCredential,
        DefaultAzureCredential,
        ManagedIdentityCredential,
    )
    from azure.keyvault.secrets import SecretClient  # type: ignore
    from simple_salesforce import Salesforce  # type: ignore
    SFP2_AVAILABLE = True
    SFP2_IMPORT_ERROR: Optional[str] = None
except Exception as _e:  # pragma: no cover - env-dependent
    DefaultAzureCredential = None  # type: ignore
    ManagedIdentityCredential = None  # type: ignore
    ClientSecretCredential = None  # type: ignore
    ChainedTokenCredential = None  # type: ignore
    SecretClient = None  # type: ignore
    Salesforce = None  # type: ignore
    SFP2_AVAILABLE = False
    SFP2_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"


KEY_VAULT_NAME = os.getenv('SFP2_KEY_VAULT_NAME', 'allworthsynapse')
KEY_VAULT_URL = f"https://{KEY_VAULT_NAME}.vault.azure.net/"

# Match the secret names used by the Synapse ingestion notebook.
SECRET_USERNAME = os.getenv('SFP2_KV_SECRET_USERNAME', 'salesforceprodusername')
SECRET_PASSWORD = os.getenv('SFP2_KV_SECRET_PASSWORD', 'Salesforce-Prod-Password')
SECRET_TOKEN = os.getenv('SFP2_KV_SECRET_TOKEN', 'Salesforce-Prod-Token')

SF_DOMAIN = os.getenv('SFP2_SF_DOMAIN', 'login')  # 'login' or 'test'
SESSION_TTL_SECONDS = int(os.getenv('SFP2_SESSION_TTL_SECONDS', '3600'))


def _truthy(val: str | None) -> bool:
    return (val or '').strip().lower() in ('1', 'true', 'yes', 'on')


# Key Vault is always tried first. This flag only enables the SF_* env-var
# *fallback* used when the Key Vault read fails. Default off = Key Vault only
# (fail loud) so production can't silently run on env creds.
ALLOW_ENV_SF_CREDS = _truthy(os.getenv('SFP2_ALLOW_ENV_SF_CREDS'))

_sf_cache: dict[str, Any] = {'sf': None, 'fetched_at': 0.0}
_sf_lock = Lock()


def _ensure_available() -> None:
    if not SFP2_AVAILABLE:
        raise RuntimeError(
            f"SFP2 dependencies unavailable: {SFP2_IMPORT_ERROR}. "
            "Install simple-salesforce, azure-identity, azure-keyvault-secrets."
        )


def _build_credential() -> Any:
    """Build a deterministic credential chain.

    Order:
      1. Managed Identity (App Service / VM) — system-assigned, or user-assigned
         when AZURE_MSI_CLIENT_ID is set.
      2. Service Principal (only when ALL three of AZURE_CLIENT_ID/SECRET/TENANT_ID
         are set; avoids the EnvironmentCredential failure when only CLIENT_ID is
         provided for non-SP purposes).
      3. DefaultAzureCredential as a last resort (covers az CLI for local dev).
    """
    _ensure_available()
    creds: list[Any] = []

    msi_client_id = os.getenv('AZURE_MSI_CLIENT_ID')
    if msi_client_id:
        creds.append(ManagedIdentityCredential(client_id=msi_client_id))
    else:
        creds.append(ManagedIdentityCredential())

    client_id = os.getenv('AZURE_CLIENT_ID')
    client_secret = os.getenv('AZURE_CLIENT_SECRET')
    tenant_id = os.getenv('AZURE_TENANT_ID')
    if client_id and client_secret and tenant_id:
        creds.append(ClientSecretCredential(tenant_id, client_id, client_secret))

    # az CLI fallback — only really useful locally.
    creds.append(DefaultAzureCredential(
        exclude_environment_credential=True,
        exclude_managed_identity_credential=True,
    ))

    return ChainedTokenCredential(*creds)


def _env_credentials() -> Optional[tuple[str, str, str]]:
    """Return (username, password, token) from SF_* env vars, or None if any are missing."""
    env_user = os.getenv('SF_USERNAME')
    env_pass = os.getenv('SF_PASSWORD')
    env_tok = os.getenv('SF_TOKEN')
    if env_user and env_pass and env_tok:
        return env_user, env_pass, env_tok
    return None


def _fetch_from_key_vault() -> tuple[str, str, str]:
    """Read the three Salesforce secrets from Key Vault. Raises on any failure."""
    _ensure_available()
    credential = _build_credential()
    client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
    username = client.get_secret(SECRET_USERNAME).value
    password = client.get_secret(SECRET_PASSWORD).value
    token = client.get_secret(SECRET_TOKEN).value
    if not username or not password or not token:
        raise RuntimeError("One or more Salesforce secrets came back empty from Key Vault")
    return username, password, token


def _fetch_credentials() -> tuple[str, str, str]:
    """Return (username, password, token).

    Key Vault is the primary source. If the Key Vault read fails and the env
    fallback is enabled (SFP2_ALLOW_ENV_SF_CREDS) with all SF_* vars present,
    fall back to those so the page keeps working while Key Vault access is
    being fixed. If the fallback is unavailable, the original Key Vault error
    is re-raised so the failure is visible.
    """
    try:
        return _fetch_from_key_vault()
    except Exception as kv_err:
        if ALLOW_ENV_SF_CREDS:
            env_creds = _env_credentials()
            if env_creds is not None:
                logger.warning(
                    "SFP2: Key Vault credential fetch failed (%s: %s); "
                    "falling back to SF_* env-var credentials.",
                    type(kv_err).__name__, kv_err,
                )
                return env_creds
        raise


def get_salesforce() -> Any:
    """Return a memoized simple_salesforce.Salesforce client."""
    _ensure_available()
    with _sf_lock:
        sf = _sf_cache.get('sf')
        fetched_at = _sf_cache.get('fetched_at', 0.0)
        if sf is not None and (time.time() - fetched_at) < SESSION_TTL_SECONDS:
            return sf

        username, password, token = _fetch_credentials()
        sf = Salesforce(
            username=username,
            password=password,
            security_token=token,
            domain=SF_DOMAIN,
        )
        _sf_cache['sf'] = sf
        _sf_cache['fetched_at'] = time.time()
        return sf


def list_sobjects(custom_only: bool = False) -> list[dict[str, Any]]:
    """Return [{name, label, custom, queryable}] for all SObjects the SP can see."""
    sf = get_salesforce()
    desc = sf.describe()
    rows: list[dict[str, Any]] = []
    for obj in desc.get('sobjects', []):
        if custom_only and not obj.get('custom'):
            continue
        if not obj.get('queryable'):
            continue
        rows.append({
            'name': obj.get('name'),
            'label': obj.get('label'),
            'custom': bool(obj.get('custom')),
            'queryable': bool(obj.get('queryable')),
        })
    rows.sort(key=lambda r: (not r['custom'], r['name'] or ''))
    return rows


def describe_object(name: str) -> list[dict[str, Any]]:
    """Return [{name, label, type, length, nillable, custom}] for a single SObject."""
    if not name or not name.replace('_', '').isalnum():
        raise ValueError(f"Invalid SObject name: {name!r}")
    sf = get_salesforce()
    sobject = getattr(sf, name)
    desc = sobject.describe()
    fields = []
    for f in desc.get('fields', []):
        fields.append({
            'name': f.get('name'),
            'label': f.get('label'),
            'type': f.get('type'),
            'length': f.get('length'),
            'precision': f.get('precision'),
            'scale': f.get('scale'),
            'nillable': bool(f.get('nillable')),
            'custom': bool(f.get('custom')),
        })
    fields.sort(key=lambda r: (r.get('name') or '').lower())
    return fields
