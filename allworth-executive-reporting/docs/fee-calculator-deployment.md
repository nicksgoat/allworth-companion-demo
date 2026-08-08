# Fee Calculator — Deployment & Integration Guide

Technical plan for promoting the **Fee Calculator** feature from the
`NewFeeCalculator` branch into `dev` (for testing) and, later, `main` (production),
**without changing dev/prod authentication**.

---

## 1. Scope

The Fee Calculator is a tiered fee-pricing tool for new-client pricing and repricing
campaigns. It is delivered as:

- A **backend Flask blueprint** mounted at `/fee-calculator`
- A **frontend React SPA** route at `/fee-calculator`
- A **card on the `/home` hub** ("Live tools" section) for discoverability

It integrates into the existing executive-reporting web app as an additional
tool alongside Tamarac, SFP2 Schema, Refresh Log, and the KPI dashboard — it does
**not** replace or alter any existing page.

### Capabilities

- Manual tiered fee calculation (enter AUM, pick a schedule)
- Household search + AUM lookup from `[tho].[Household_Rollforward]`
- Bulk billing upload (CSV or `.xlsx`) with per-household proposed-fee comparison
- Scatter-plot visualization (AUM vs effective rate), lasso select, range sliders
- Per-household schedule overrides and waived-account handling
- **Excel export** with interactive dropdowns, AUM-specific tiered rate matrix
  (INDEX/MATCH), advisor summary, and a schedule reference sheet

---

## 2. Architecture

```
Browser
  │
  ├─ GET /fee-calculator                → nginx serves SPA (index.html)
  │                                        React Router mounts <FeeCalculator/>
  │
  └─ /fee-calculator/api/*              → nginx proxy → backend Flask :5000
                                           (sidecar container)
                                              │
                                              ├─ auth_middleware (JWT gate)
                                              ├─ fee_calculator blueprint
                                              └─ get_database_connection()  → Synapse
```

### Backend
- `backend/fee_calculator/__init__.py` — package marker
- `backend/fee_calculator/routes.py` — blueprint `bp`, all endpoints + fee engine
- `backend/fee_calculator/templates/index.html` — SPA host page
- Registered defensively in `backend/app.py` (try/except) at `url_prefix="/fee-calculator"`
- Reuses `app.get_database_connection()` — **no independent DB auth**

### Frontend
- `frontend/src/FeeCalculator.tsx` — main component
- `frontend/src/FeeCalculator.css` — styles
- `frontend/src/main.tsx` — route registered in both the SSO-gated pipeline
  render path and the main render path
- `frontend/vite.config.ts` — local dev proxy for `/fee-calculator/api`
- `frontend/nginx.conf` — production proxy block for `/fee-calculator/api/`
  (uses the same `BACKEND_HOST:5000` placeholder convention as `/api/`, `/home/`, `/jarvis/`)

### Dependencies added
| Layer | Dependency | Reason |
|-------|-----------|--------|
| Backend | `openpyxl>=3.1` | `pd.read_excel(engine="openpyxl")` for `.xlsx` upload + Excel export generation |
| Frontend | `recharts@^3.8.1` | Scatter-plot visualization |

---

## 3. API Endpoints (all under `/fee-calculator`)

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Serve the SPA host page |
| `/api/schedules` | GET | List fee schedules + tier definitions |
| `/api/calculate` | POST | Calculate fee for one AUM + schedule |
| `/api/calculate-all` | POST | Calculate across all schedules |
| `/api/filters` | GET | Distinct advisors / regions / channels (Synapse) |
| `/api/search` | GET | Household search by name/advisor/region/channel |
| `/api/household/<avhhid>` | GET | Household detail + current AUM |
| `/api/upload-billing` | POST | Upload CSV/XLSX, compute proposed fees |
| `/api/billing-data` | GET | Retrieve cached last upload |
| `/api/export-excel` | POST | Generate interactive `.xlsx` workbook |
| `/api/cache-clear` | POST | Clear in-memory caches |

All Synapse queries are parameterized (no string interpolation of user input).

---

## 4. Authentication — DO NOT MODIFY

**The Fee Calculator introduces no new authentication and changes none of the
existing auth wiring.** Auth remains governed entirely by the environment's
existing configuration.

### Verified: unchanged between `origin/dev` and `NewFeeCalculator`
- `backend/auth_middleware.py` — JWT (Entra ID) validation — **no diff**
- `frontend/src/services/auth.ts` — MSAL SSO gate — **no diff**
- `backend/Dockerfile`, `frontend/Dockerfile` — **no diff**
- `.github/workflows/azure-deploy-dev.yml`, `azure-deploy.yml` — **no diff**

### How auth applies to the Fee Calculator
1. **Frontend SSO gate** — `/fee-calculator` is listed in the pipeline-path SSO
   gate in `main.tsx`. When `VITE_ENTRA_CLIENT_ID` + `VITE_ENTRA_TENANT_ID` are
   configured, the SPA acquires an ID token before rendering and attaches it as
   `Authorization: Bearer <token>` to every `/fee-calculator/api/*` call.
2. **Backend JWT validation** — `auth_middleware` runs before the blueprint's
   `before_request` hooks (installed first in `app.py`). It validates the bearer
   token against the configured Entra issuer.
3. **Test coverage** — `backend/tests/test_auth_middleware.py` registers the
   fee-calculator blueprint and asserts:
   - `GET /fee-calculator/api/schedules` → **401** with no token
   - `GET /fee-calculator/api/schedules` → **200** with a valid token

### Environment behavior (governed by existing App Settings — not by this feature)
| Environment | Frontend SSO | Backend JWT | Synapse `AUTH_METHOD` |
|-------------|-------------|-------------|-----------------------|
| Local dev | off (no `VITE_ENTRA_*`) | bypassed (`AUTH_DISABLE=1` or unset tenant) | `ActiveDirectoryInteractive` (`.env`, gitignored) |
| Dev slot | per existing workflow build-args | per existing App Settings | per existing App Settings |
| Prod | per existing workflow build-args | per existing App Settings | per existing App Settings |

> **Rule:** if any local auth configuration conflicts with what dev/prod use,
> the dev/prod configuration wins. `.env` is gitignored and never deployed.

The Fee Calculator inherits Synapse connectivity from `get_database_connection()`,
which already supports `ActiveDirectoryInteractive`, `ServicePrincipal`, and
`SqlPassword` via existing env vars — **no new secrets required.**

---

## 5. Pre-Merge Checklist

- [x] Diff between `origin/dev` and `NewFeeCalculator` limited to fee-calculator
      files, `app.py` blueprint block, `main.tsx` routes, nginx/vite proxy,
      home hub card, and tests
- [x] No changes to `auth_middleware.py`, `services/auth.ts`, Dockerfiles, or
      CI/CD workflows
- [x] `openpyxl>=3.1` added to `backend/requirements.txt`
- [x] Backend imports cleanly; fee-calculator blueprint loads
- [x] `pytest tests/test_fee_calculator.py tests/test_auth_middleware.py` — all pass
- [x] `tsc --noEmit` clean
- [x] nginx `/fee-calculator/api/` proxy present (uses `BACKEND_HOST` convention)

---

## 6. Merge & Deploy to `dev`

The `dev` branch auto-deploys via `.github/workflows/azure-deploy-dev.yml` on push.

```bash
git fetch origin
git checkout -b merge/fee-calculator-to-dev origin/dev
git merge NewFeeCalculator          # resolve any conflict favoring dev for shared/infra files
git push -u origin merge/fee-calculator-to-dev
# open PR → dev, review, merge. Merge to dev triggers the dev deploy.
```

Conflict policy: for any shared or infrastructure file (`app.py`, `main.tsx`,
`nginx.conf`, workflows, Dockerfiles, `auth_*`), **keep the dev version's
auth/infra semantics** and re-apply only the fee-calculator additions.

---

## 7. Dev Validation

After the dev deploy completes, on the dev slot URL:

1. `/home` shows the **Fee Calculator** card under "Live tools"
2. `/fee-calculator` loads the SPA
3. `/fee-calculator/api/filters` returns **200** (proves Synapse auth via App
   Settings works in the container)
4. Household search returns results
5. Billing upload (CSV **and** `.xlsx`) succeeds → confirms `openpyxl` present
6. **Export Excel** downloads a valid workbook with working dropdowns/formulas
7. Regression: `/` (KPI dashboard), `/tamarac`, `/sfp2`, `/refresh_log` unaffected

### Rollback
Revert the merge commit on `dev`; the workflow redeploys the prior state.
No data migrations or schema changes are involved.

---

## 8. Production (later — out of current scope)

Promote via PR `dev → main` only after dev sign-off. **Do not** alter the
commented-out `VITE_ENTRA_*` build-args or backend auth App Settings as part of
this feature; production auth posture is managed independently.
