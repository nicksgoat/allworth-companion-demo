"""Shared infrastructure for the executive-reporting backend.

Feature packages (mailer, brief, nfbc, sfp2, catalog, admin, file_explorer)
were each re-implementing the same three concerns: Synapse ODBC connections,
Azure credential/Key Vault access, and the Microsoft Graph HTTP layer. Those
now live here so there is a single, tested implementation of each.

    from core import db            # build_conn_str(), connect()
    from core import azure_auth    # storage_credential(), keyvault_client()/secret()
    from core import graph         # GRAPH_BASE, call(), headers(), plain(), addr()
"""

from __future__ import annotations

__all__ = ["azure_auth", "db", "graph"]
