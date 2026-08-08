# Jarvis — knowledge-base blueprint

Mounted at `/jarvis` in the main Flask app. Serves an HTML page that lets the
team browse, search, and edit the YAML knowledge base that powers the
Allworth MCP server. The same YAMLs are read by `wealth-mcp` (via the
``WEALTH_MCP_FRAMEWORKS_DIR``/``JARVIS_FRAMEWORKS_DIR`` env var) so edits
made here are source-of-truth for both surfaces.

## Layout

```
backend/jarvis/
├── __init__.py           # Package marker
├── knowledge_loader.py   # YAML scanner + keyword search (no web deps)
├── handler.py            # search / list / get / diff logic
├── storage.py            # write / delete / restore + history log
├── routes.py             # Flask Blueprint (mount at /jarvis)
├── templates/
│   └── index.html        # SPA shell rendered by Flask
├── static/
│   └── logo.png          # Populated by install-jarvis-content.ps1
└── knowledge/
    ├── *.yaml            # 45+ atomic entries (populated by install script)
    └── .jarvis-history/
        └── events.jsonl  # Append-only audit log
```

## First-time setup

```powershell
# From the repo root
.\scripts\install-jarvis-content.ps1    # copies YAMLs + logo from SynapseMCP
pip install -r backend\requirements.txt # pulls pyyaml + markdown
cd backend
python app.py                            # Flask dev server on :5000
# Open http://localhost:5000/jarvis/
```

## Env vars

| Var | Purpose |
|---|---|
| `JARVIS_FRAMEWORKS_DIR` | Override the YAML directory. Defaults to `backend/jarvis/knowledge`. |
| `JARVIS_RELOAD_CHECK_SECONDS` | How often to poll YAML mtimes for hot-reload (default 30). |
| `JARVIS_USER` | Dev-mode identity fallback when no SSO header is present. |
| `JARVIS_ADMIN_TOKEN` | Required to call `POST /jarvis/api/admin/reload`. |

Identity for history attribution is pulled from `X-MS-Client-Principal-Name`
(Azure Easy Auth) or `X-User-Email` at request time; both are forwarded by
nginx via the `/jarvis/` location block.

## API

- `GET  /jarvis/` — HTML page (SPA shell).
- `GET  /jarvis/logo.png`
- `GET  /jarvis/api/search?q=...` — single best match.
- `GET  /jarvis/api/search/all?q=...` — ranked matches.
- `GET  /jarvis/api/docs` — grouped list for the sidebar.
- `GET  /jarvis/api/docs/<key>` — full doc + rendered HTML.
- `PUT  /jarvis/api/docs/<key>` — create or update.
- `DELETE /jarvis/api/docs/<key>` — delete (history preserved).
- `GET  /jarvis/api/docs/<key>/history` — per-doc audit log.
- `GET  /jarvis/api/history` — global recent changes.
- `GET  /jarvis/api/docs/<key>/history/<ts>/diff` — unified diff for one event.
- `POST /jarvis/api/docs/<key>/restore` — restore a past version.
- `GET  /jarvis/api/me` — current request's identity.
- `POST /jarvis/api/admin/reload` — force re-scan (auth via `X-Admin-Token`).

## Sync with the MCP server

When deployed, both services read YAMLs from the same directory. In Azure,
that typically means mounting an Azure File Share at the same path for both
containers. Edits made through the Jarvis UI are visible to the MCP's next
call to `reload_resources()`.
