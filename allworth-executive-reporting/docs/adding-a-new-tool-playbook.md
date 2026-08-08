# Playbook: Adding a New Tool / Report to the Web App

A step-by-step, repeatable process for shipping a new "Live tool" (like the Fee
Calculator) into the Allworth Executive Reporting web app — from local build all
the way to production — **without disturbing authentication or any existing feature.**

This document generalizes exactly how the Fee Calculator was promoted to `main`.
Use it as a template for the next tool/report.

---

## 0. Mental model of the app

| Layer | Where | What it does |
|-------|-------|--------------|
| Backend | `backend/` — Flask app factory in `app.py`, one **blueprint per tool** | Serves `/<tool>/api/...` JSON + optional server-rendered page |
| Frontend | `frontend/` — React + TypeScript + Vite, routes in `src/main.tsx` | SPA route per tool |
| Reverse proxy | `frontend/nginx.conf` | In the container, nginx serves the SPA and proxies `/<tool>/api/` to Flask on `:5000` |
| Home hub | `backend/home/templates/index.html` | Landing page with a card per tool |
| Auth | `backend/auth_middleware.py` (JWT) + App Service Easy Auth | **Shared, automatic** — new tools inherit it. Never edit for a feature. |
| Deploy | `.github/workflows/azure-deploy-dev.yml` (dev) / `azure-deploy.yml` (main) | Auto-deploy on push to `dev` / `main` |

**Golden rule:** a new tool is an **additive** change. If your diff touches
`auth_middleware.py`, `services/auth.ts`, either `Dockerfile`, or the deploy
workflows, stop — that's out of scope for a feature.

---

## 1. Build the tool on a feature branch

```bash
git fetch origin
git checkout -b feature/<tool-name> origin/dev
```

### 1a. Backend blueprint
Create `backend/<tool_name>/` with:

- `__init__.py` — one-line docstring; the blueprint mounts at `/<tool-name>`.
- `routes.py` — declares `bp = Blueprint("<tool_name>", __name__, template_folder="templates")`
  and defines routes under `@bp.route("/api/...")`.
- `templates/index.html` (only if the tool serves a server-rendered page).

Register it **defensively** in `backend/app.py` (so a broken import can never take
down the whole app):

```python
# <Tool> — short description
try:
    from <tool_name>.routes import bp as <tool>_bp
    app.register_blueprint(<tool>_bp, url_prefix="/<tool-name>")
    print("<emoji> <Tool> blueprint registered at /<tool-name>")
except Exception as _e:  # pragma: no cover - defensive
    print(f"⚠️  <Tool> blueprint unavailable: {type(_e).__name__}: {_e}")
```

### 1b. Frontend route
In `frontend/src/main.tsx`, add the tool in **four** places (there are two render
paths — a "pipeline" path and the main path):

1. Import: `import <Tool> from './<Tool>';`
2. `isPipelinePath` gate: add `|| p === '/<tool-name>'`
3. Pipeline `<Routes>`: `<Route path="/<tool-name>" element={<<Tool> />} />`
4. Main `<Routes>`: same `<Route ...>` line

### 1c. nginx proxy block
In `frontend/nginx.conf`, add a **new** `location` block — do **not** touch the
existing `/api/`, `/jarvis/`, or `/home/` blocks:

```nginx
# Proxy <Tool> API to backend
location ^~ /<tool-name>/api/ {
    proxy_pass http://BACKEND_HOST:5000/<tool-name>/api/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # If the tool accepts file uploads, raise the body limit (default is 1MB → 413)
    client_max_body_size 64m;

    proxy_buffering on;
    proxy_buffer_size 16k;
    proxy_buffers 8 32k;

    # Raise timeouts if the tool runs heavy queries (default is 60s → 504)
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_connect_timeout 10s;
}
```

> `BACKEND_HOST` is substituted at container startup — keep the literal token.

### 1d. Home hub card
In `backend/home/templates/index.html`:
- Bump the `<span class="count">N available</span>` by one.
- Add an `<a class="card" href="/<tool-name>" style="animation-delay: <N>ms">…</a>`
  block, incrementing the `animation-delay` by 40ms after the last card.

### 1e. Dependencies + local-dev proxy
- Backend: add any new package to `backend/requirements.txt` (e.g. `openpyxl>=3.1`).
- Frontend: add any new package to `frontend/package.json` (e.g. `recharts`), then
  `npm install` to update the lockfile.
- Local dev only: add the tool to the Vite proxy in `frontend/vite.config.ts` so
  `npm run dev` reaches Flask:

```ts
server: {
  proxy: {
    '/<tool-name>/api': 'http://127.0.0.1:5000',
    '/api': 'http://127.0.0.1:5000',
  },
},
```

### 1f. Tests
- Add `backend/tests/test_<tool_name>.py` for the tool's logic.
- Add an auth-coverage test in `backend/tests/test_auth_middleware.py` proving the
  new `/<tool-name>/api/...` routes are JWT-gated (register the blueprint in the
  test app, assert 401 without a token and 200 with a valid one).

---

## 2. Pre-merge verification (read-only, do this every time)

```bash
git fetch origin

# 1) What am I actually changing vs dev?
git diff --stat origin/dev...feature/<tool-name>

# 2) AUTH SAFETY — this MUST be empty:
git diff origin/dev...feature/<tool-name> -- \
  backend/auth_middleware.py \
  frontend/src/services/auth.ts \
  backend/Dockerfile frontend/Dockerfile \
  .github/workflows/
```

If the auth check is not empty, revert those hunks — dev/prod auth always wins.

---

## 3. Validate locally (use the REAL build command)

```bash
# Frontend — MUST be `npm run build`, not `tsc --noEmit`.
# CI runs `tsc -b && vite build`, which is stricter (noUnusedLocals, recharts
# types). `tsc --noEmit` will pass on code that CI rejects.
cd frontend && npm run build      # expect exit 0

# Backend
cd ../backend && python -m pytest -q   # all tests pass
```

> **Lesson learned:** validating with `tsc --noEmit` let unused-var and recharts
> type errors through, which then failed the dev container build. Always
> `npm run build`.

---

## 4. Merge to `dev` for testing

Use a staging branch so **you** open the PR (the PR merge is what triggers the
auto-deploy — keep that as a deliberate human action).

```bash
git checkout -b merge/<tool-name>-to-dev origin/dev
git merge --no-commit --no-ff feature/<tool-name>
# resolve any conflicts KEEPING BOTH dev's features and yours
git diff --check                  # no conflict markers
cd frontend && npm run build      # re-validate the merged tree
cd ../backend && python -m pytest -q
git commit
git push -u origin merge/<tool-name>-to-dev
```

Open PR **base: `dev`**, compare: `merge/<tool-name>-to-dev`, and merge it.

Common conflict spots when dev has advanced: `main.tsx` (route lists),
`requirements.txt`, `home/templates/index.html` (card count + card block).

---

## 5. Validate on the dev slot after deploy

Wait for the "Build and Deploy to Azure Web App (Dev)" Action to go **green**, then
on the dev URL (`https://allworth-executive-reporting-dev.azurewebsites.net`, or
confirm the exact host in the Action log / Portal → slot → Default domain):

- `/home` shows the new card
- `/<tool-name>` loads
- `/<tool-name>/api/<probe>` returns 200 (proves data-warehouse auth works in-container)
- Any upload / export features work end to end
- **Regression:** `/`, `/tamarac`, `/sfp2`, `/refresh_log`, `/repcodes`, `/nfbc`
  all still work

### Debugging "works locally, fails on dev"
The container path differs from local (nginx + Werkzeug). Watch for:

| Symptom | Cause | Fix |
|--------|-------|-----|
| Upload fails, "413" | nginx default 1MB body cap | `client_max_body_size` on the proxy block |
| Upload "failed" / 504 | request exceeds `proxy_read_timeout 60s` | raise `proxy_read_timeout` / `proxy_send_timeout` |
| "failed (HTTP 200)" | response body is invalid JSON (`NaN`/`Infinity` from pandas) | sanitize non-finite floats → `null` before `jsonify` |

> Make the frontend surface the **real HTTP status** on error — it turns
> guesswork into a one-shot diagnosis.

---

## 6. Promote to `main` (production) — preserve prod-only config

**Do NOT plain-merge `dev → main`.** `main` may hold deliberate prod-only settings
(e.g. `azure-deploy.yml` disables client-side MSAL so prod uses Easy Auth only).
A blind merge would overwrite them.

```bash
git fetch origin --prune

# 6a. Confirm what dev→main would change, and check for prod-only files:
git diff --stat origin/main origin/dev
git diff origin/main origin/dev -- .github/workflows/azure-deploy.yml

# 6b. Prove auth is unchanged (blob SHAs must match):
git rev-parse origin/main:backend/auth_middleware.py origin/dev:backend/auth_middleware.py
git rev-parse origin/main:frontend/src/services/auth.ts origin/dev:frontend/src/services/auth.ts

# 6c. Build the promote branch OFF main, merge dev, then restore any prod-only file:
git checkout -b promote/<tool-name>-to-main origin/main
git merge --no-commit --no-ff origin/dev
git checkout origin/main -- .github/workflows/azure-deploy.yml   # keep prod's workflow
git add .github/workflows/azure-deploy.yml

# 6d. VERIFY the sensitive files are byte-identical to main (all must be empty):
git diff --cached origin/main -- \
  .github/workflows/azure-deploy.yml \
  backend/auth_middleware.py \
  frontend/src/services/auth.ts \
  backend/Dockerfile frontend/Dockerfile

# 6e. Confirm the full staged diff is ONLY your additive tool files:
git diff --cached --stat origin/main

# 6f. Validate + ship:
cd frontend && npm run build
cd ../backend && python -m pytest -q
cd ..
git commit -m "Promote <Tool> to main (additive only; preserves prod auth/workflow)"
git push -u origin promote/<tool-name>-to-main
```

Open PR **base: `main`**, compare: `promote/<tool-name>-to-main`. On the PR's
"Files changed", confirm `azure-deploy.yml` and the auth files are **not listed**.
Merging triggers the **prod** deploy.

---

## 7. Post-prod validation

Run the same checklist as Step 5 on the production URL, especially the
`/<tool-name>/api/<probe>` 200 (data-warehouse auth) and the regression pass on
existing tools.

**Rollback:** `git revert -m 1 <merge-commit>` on `main`, then push to redeploy.

---

## 8. Cleanup

After each merge is confirmed:

```bash
git checkout dev && git pull
git branch -d feature/<tool-name> merge/<tool-name>-to-dev promote/<tool-name>-to-main
git push origin --delete feature/<tool-name> merge/<tool-name>-to-dev promote/<tool-name>-to-main
```

Use `-d` (not `-D`) locally — it refuses to delete anything not fully merged, a
built-in safety check.

---

## Checklist (quick reference)

- [ ] Backend blueprint + defensive registration in `app.py`
- [ ] `main.tsx`: import + `isPipelinePath` + both `<Routes>` (4 edits)
- [ ] New `location ^~ /<tool>/api/` block in `nginx.conf` (body size / timeouts if needed)
- [ ] Home hub card + `count` bumped
- [ ] Deps in `requirements.txt` / `package.json` (+ lockfile), Vite proxy for local dev
- [ ] Tests, including JWT-gating auth coverage
- [ ] Auth-safety diff is EMPTY
- [ ] `npm run build` + `pytest` pass
- [ ] Dev PR → green deploy → dev validation + regression
- [ ] Promote branch off `main`, prod-only files restored, sensitive diffs EMPTY
- [ ] Prod PR merged → prod validation → cleanup
