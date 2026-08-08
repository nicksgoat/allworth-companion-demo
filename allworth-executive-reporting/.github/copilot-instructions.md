# Copilot instructions — Allworth Executive Reporting

React + TypeScript SPA (`frontend/`) with a Flask API (`backend/`). Each
user-facing feature is a "tool" reachable at its own route (e.g. `/nfbc`,
`/fee-calculator`, `/admin`). The **Admin** console (`/admin`) manages who can
open which tool; access is enforced per-user when `ADMIN_ENFORCEMENT` is on.

## The tool registry & where the navigation lives

`backend/home/tools.yaml` is the canonical **access** registry. Every entry there:

- appears in the **Admin access console** (`/admin`) as a grantable tool
  (the admin API reads it via `admin/store.available_tools()`), and
- can be gated per-user (the tool `id` is the access key).

The **navigation is React and shared across every page**:

- The left rail is `frontend/src/components/SideNav.tsx` (the `GROUPS` / `REPORTS`
  arrays). It is mounted by the Home hub and every tool page, and it hides links
  the current (or impersonated) user can't reach.
- The **Home hub** is `frontend/src/Home.tsx` (a React route at `/` and `/home`,
  no longer a Flask template). It renders the launcher cards from its `SECTIONS`
  catalog and also mounts `<SideNav />`.
- Access is resolved once by `frontend/src/services/access.ts`
  (`useEffectiveAccess`), which applies the "view as" impersonation overlay so
  the rail, hub cards, and `ToolGuard` all hide the same things.

Keep the `id` identical across `tools.yaml`, `SideNav.tsx`, and `Home.tsx` — it
is the access key checked by `ToolGuard`, `/api/admin/me`, and the nav filter.

**The Home hub cards must always mirror the SideNav rail.** Every launcher card
in `Home.tsx` `SECTIONS` should live in the section that matches its `SideNav`
`GROUPS` group (Live tools → Live tools, Admin → Admin, etc.), and the two must
be reorganized together. When you move, add, or remove a tool in one, make the
same change in the other so the hub and the rail never disagree on where a tool
belongs. (Reporting drill-in reports and "soon" placeholder cards are the only
entries that don't have a 1:1 rail link.)

## Required checklist when you add a NEW user-facing tool/page

Do ALL of these so the tool is launchable AND access-controlled. Use one
stable `id` (lowercase slug, e.g. `fee_calculator`) everywhere.

1. **Register it in `backend/home/tools.yaml`** — add a `tools:` entry with
   `id`, `name`, `kicker`, `description`, `url`, `host`, `category`
   (`live` | `analytics` | `utilities`), `color`, `status`, and an `icon`.
   This is what surfaces it in the Admin access console.
2. **Frontend route + gate** in `frontend/src/main.tsx` — add the `<Route>` in
   BOTH the `isPipelinePath` block and `renderApp`, wrapped in the guard:
   `<Route path="/my-tool" element={<ToolGuard toolId="my_tool"><MyTool /></ToolGuard>} />`.
   Also add the path to the `isPipelinePath` list if it needs SSO before render.
3. **Navigation + hub card (ASK FIRST — see next section)** — add the tool to
   the shared rail in `frontend/src/components/SideNav.tsx` (a `NavLink` in the
   right `GROUPS` section, carrying its `toolId`) and, if it belongs on the
   landing page, add a card to the `SECTIONS` catalog in `frontend/src/Home.tsx`.
   Both are gated by the tool `id` so they hide for users without access.
4. **Backend blueprint** (if it has an API) — register it in `backend/app.py`
   following the existing defensive `try/except` pattern.
5. **App Usage logging** — add the tool's route to `_TOOL_ROUTES` (consumed by
   `_page_to_tool`) in `backend/app.py`, mapping its path prefix to the same
   tool `id` and a display name. Page views are auto-tracked on every route by
   `frontend/src/components/PageTracker.tsx`, but **paths with no `_TOOL_ROUTES`
   entry group under "Other"** in the App Usage dashboard — this step attributes
   them to the tool. Also add the tool to `DEMO_TOOLS` in
   `frontend/src/services/analytics.ts` so it appears in the offline App Usage
   demo. (Entries are matched most-specific-first, so list nested paths like
   `/reporting/kpi` before their parents.)
6. **Demo list** — add the tool to `DEMO_TOOLS` in
   `frontend/src/services/admin.ts` so it also shows in the offline demo admin.
7. **Keep "view as" mirroring true access** — the impersonation overlay must
   reflect exactly what the impersonated user can do. If the tool adds a new
   *dimension* of access (beyond plain view — e.g. the share right), thread it
   through the whole chain: `Impersonation` in `services/access.ts`, the
   overlay written by `applyImpersonation`/`viewAsUser` in `Admin.tsx`, and the
   `EffectiveAccess` returned by `useEffectiveAccess`. See the *view-as mirrors
   true access* rule below.

The `id` in steps 1–3/5/6 must match exactly — it is the access key checked by
`ToolGuard`, the `/api/admin/me` enforcement, and the hub filter.

## Ask the tool's creator about navigation

Navigation is opt-in per page — do NOT assume. Whenever you add a new
user-facing tool/page, ASK the person adding it (and only wire up what they
confirm):

1. **Should this page show the shared left nav rail (`<SideNav />`)?** Most tool
   pages do — render `<SideNav />` inside a `has-sidenav` wrapper (see
   `Repcodes.tsx`). Some full-screen or embedded views intentionally omit it.
2. **Where should it live in the rail?** Which `SideNav` group (e.g. *Live
   tools*, *Pipeline & data*, the *Reporting* drill-in) and what label + icon.
3. **Should it get a Home hub launcher card, and in which section** (*Live
   tools*, *Analytics & reports*, *Utilities*)?
4. **Should the page have a Share button?** Creators can drop the reusable
   `<ShareTool toolId="my_tool" toolName="My Tool" />` (from
   `components/ShareTool.tsx`) into the page header. It renders ONLY for users
   allowed to share that tool and lets them grant/revoke its view access to
   other users. See `Repcodes.tsx` for the pattern.

Add only the rail entry / hub card the creator asks for, and keep it consistent
with existing entries (icon style, group placement, and `toolId` gating).

## Access enforcement (safety)

- Enforcement is **ON in production** (`ADMIN_ENFORCEMENT=1`, set in
  `.github/workflows/azure-deploy.yml`). It stays OFF for local dev and the dev
  slot (`azure-deploy-dev.yml` runs `AUTH_DISABLE=1`, so enabling it there would
  lock out anonymous callers). Only enable enforcement where SSO is active.
- The all-access **Admin** group and the bootstrap owner emails
  (`ADMIN_BOOTSTRAP_EMAILS`, plus the built-in owner) are guaranteed by
  `admin/store.ensure_bootstrap()` so an admin can never be locked out.
- `all_tools` groups auto-grant every current AND future tool, so tools added
  to `tools.yaml` are immediately available to those members.
- **Auto-provisioning:** the first authenticated hit on `/api/admin/me` calls
  `store.ensure_user()`, so a brand-new user is added to the roster and joins
  the derived **All Users** group automatically (no tools until granted).
- **"View as" must mirror true access.** The impersonation overlay is meant to
  show the site EXACTLY as the impersonated user experiences it, so it must stay
  in lockstep with the real access model. Whenever you add a tool, a page, or a
  new access dimension, update the *view-as* path so it reflects the change:
  - `viewAsUser`/`applyImpersonation` in `Admin.tsx` write the overlay from the
    impersonated user's roster entry (direct grants + group cascade).
  - `Impersonation` + `useEffectiveAccess` in `services/access.ts` read it back
    into `EffectiveAccess` for `SideNav`, `Home`, `ToolGuard`, and `ShareTool`.
  A new dimension that isn't threaded through both sides will make view-as lie
  about what the user can do (e.g. share access was added to this overlay for
  exactly this reason). Prefer resolving *effective* access (including group
  cascade), not just direct grants, so view-as matches enforcement.
- **Per-tool level (view vs share):** each direct/group grant is either
  *view* or *share*. Share implies view AND lets that user re-share the tool.
  It is stored as a `share_tools` subset of `tools` on users and groups.
- **Delegated sharing:** a user who can share a tool (a `share`-level grant, a
  group that shares it, or an all-access admin) gets a `<ShareTool />` button on
  the tool page (`components/ShareTool.tsx`) to grant/revoke that tool's *view*
  access to others via `POST /api/admin/share` + `/share/revoke`. `access.ts`
  `canShareTool()` gates the button.

## Conventions

- Keep new pages styled with the shared `.t2-*` glass theme (see
  `Tamarac2.css`) and scope page-specific CSS under a page class.
- Backend persistence uses atomic JSON writes under a `.` -prefixed state dir
  (see `admin/store.py`, `nfbc/queue_store.py`); those dirs are git-ignored.
- The admin roster is one shared JSON file in ADLS
  (`dlallworthai/silver/admin/admin_state.json`); prod reads+writes it, and the
  **dev site is a read-only replica** (`ADMIN_STATE_READONLY=1`) that mirrors the
  same users/groups on a short refresh but never uploads, so dev can't clobber
  prod's roster. Only one instance may write.
- **The roster is never committed to git** (`admin_state.seed.json` is
  git-ignored) so a PR/merge can't carry a stale user list. A deploy only uploads
  a roster it actually **restored from ADLS**; a seed/bootstrap-only start serves
  locally with uploads disabled (`ADMIN_STATE_ALLOW_SEED_BACKUP=1` opts in for
  genuine first-time setup) so it can never overwrite the live list.
- **Every roster write persists to ADLS immediately** (`_schedule_backup` on the
  writer), because the container volume is ephemeral on Azure — so a redeploy
  can't lose changes made since the last daily backup. Admins can also **restore
  a daily snapshot** from the console (`GET/POST /api/admin/backups*`,
  `store.list_backups`/`restore_backup`) via the *Restore backup* button.
- Never hardcode secrets; read from environment (`backend/.env`).

## Standard development workflow

1. **Start every feature from `dev`.** Branch off the latest `dev`
   (`git checkout dev && git pull && git checkout -b my-feature`), never off
   `main` or another feature branch.
2. **Iterate with local previews.** Do short-term development against the
   no-auth demo preview — from `frontend/`, run `npm run dev:demo`
   (Vite, `http://localhost:5173/`). Run the Flask backend only when a page
   needs it (e.g. `/catalog/`). Keep `tsc -b && vite build` green.
3. **Open a PR from the feature branch into `dev`** once the results look good.
   That is the review target for all feature work.
4. **`dev` → `main` is the user's call.** When the user decides a feature is
   complete, they open their own PR from `dev` to `main` in the GitHub UI — do
   not open or merge `dev`→`main` PRs automatically.

