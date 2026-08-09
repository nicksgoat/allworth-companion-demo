# CLAUDE.md — Allworth Executive Reporting

This file gives Claude the same working context as GitHub Copilot.

## Primary instructions

**Read and follow [`.github/copilot-instructions.md`](.github/copilot-instructions.md).**
It is the single source of truth for this repo and covers:

- The architecture (React + TypeScript SPA in `frontend/`, Flask API in `backend/`).
- The canonical tool manifest (`tool-manifest.json`) that drives navigation,
  home widgets, assignment presets, and access keys.
- The manifest-driven checklist for adding a new user-facing tool/page.
- The rule that **Home hub cards must always mirror the SideNav rail**.
- Access enforcement (`ADMIN_ENFORCEMENT`) and bootstrap-owner safety.
- The **standard development workflow** (branch from `dev` → local preview →
  PR into `dev`; the `dev`→`main` PR is the user's own call in the GitHub UI).

Anything in that file applies here verbatim. This file only adds the coding
best practices below.

## Coding best practices

Optimize for a codebase that is easy to navigate and safe to change. Favor
**modularity** and **consistency** over cleverness.

### Modularity
- **One responsibility per module.** A file/component/function should do one
  thing. Split a page into a container + presentational pieces rather than one
  giant component.
- **Extract shared logic, don't duplicate it.** Cross-cutting concerns live in
  `frontend/src/services/*` (e.g. access resolution in `services/access.ts`);
  reuse them instead of re-implementing. Backend shared logic lives in its
  blueprint's module, not inlined into `app.py`.
- **Keep boundaries clean.** UI components render and delegate; data fetching,
  auth, and business rules stay in services/blueprints. Don't reach across
  layers.
- **Small, composable units.** Prefer several small pure functions/components
  that compose over one large one with many branches.

### Consistency
- **Follow existing patterns before inventing new ones.** Match the structure,
  naming, and style of the nearest similar file (e.g. model a new tool page on
  `Repcodes.tsx`, a new blueprint on the existing `try/except` registration in
  `app.py`).
- **Keep consumers on the manifest.** A tool's identity, route, navigation,
  assignment eligibility, and widget definition belong in `tool-manifest.json`;
  consumers derive from it rather than maintaining parallel catalogs.
- **Consistent naming.** Lowercase-slug tool `id`s, `PascalCase` components,
  `camelCase` functions/vars, page-scoped CSS classes (`.t2-*` glass theme).
- **Predictable file placement.** New React pages under `frontend/src/`, shared
  logic under `frontend/src/services/`, shared UI under
  `frontend/src/components/`, backend features under their own `backend/<tool>/`
  package.

### Structure that stays navigable
- Colocate a page with its styles and helpers so a feature is easy to find and
  delete as a unit.
- Name things for what they are; avoid abbreviations that only the author
  understands.
- Keep functions short and single-purpose; prefer clear names over comments.
- Don't add features, refactors, or abstractions beyond what the task needs —
  make only the change requested.
- Validate inputs at system boundaries; never hardcode secrets (read from
  `backend/.env`).
- Keep `tsc -b && vite build` green before opening a PR.
