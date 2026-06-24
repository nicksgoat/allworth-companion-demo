# Allworth Companion — Launch Page

A professional, Apple-style **sales-pitch launch page** for the Allworth Companion product.
One main pitch page (Overview) with top tabs to non-pitch views (Updates / changelog). It is a
self-contained static site served by a tiny zero-dependency Node server that enforces a shared
password. No build step.

```
launch/
  server.js        zero-dep Node server: HTTP Basic Auth gate + static serving of public/
  package.json     start script (node server.js) + engines
  web.config       iisnode entry point for a Windows Azure App Service (ignored on Linux)
  public/
    index.html     single document; sticky tab bar + hash-routed views (#/ , #/updates)
    assets/
      styles.css   brand design system (mirrors frontend/src/theme.ts)
      app.js       hash router, content rendering, screenshot lightbox
      content.js   EDIT THIS to update releases (changelog), features, and screenshots
      logo.svg     official Allworth lockup (ported, never redrawn)
      screenshots/ real app captures
```

## Run locally

```bash
cd launch
node server.js          # http://localhost:8080
```

The browser prompts for a username + password (Basic Auth). Defaults:

- user: `allworth`
- password: `ally-for-life`  ← override in production (see below)

Override locally with env vars:

```bash
SITE_USER=allworth SITE_PASSWORD='your-password' node server.js
```

## Update the content

Everything that changes over time lives in **`public/assets/content.js`** — no code edits needed:

- `releases[]` — the Updates / changelog tab (newest first).
- `features[]` — the feature grid on the pitch.
- `screenshots[]` — the Screens gallery (filename + caption; drop the image in `public/assets/screenshots/`).

Add a new tab by adding a route + render function in `public/assets/app.js` and a `<button>` in the
tab bar in `public/index.html`.

## Deploy to the Azure Web App

> The page is built deploy-ready. The actual push is deferred until the Azure resource is accessible.
> Confirm before deploying: **app name, resource group, OS (Linux vs Windows), and push method.**

1. **Set the password** as App Settings (so it is never committed):

   ```bash
   az webapp config appsettings set -g <resource-group> -n <app-name> \
     --settings SITE_USER='allworth' SITE_PASSWORD='<strong-password>'
   ```

2. **Push the code** — use whichever matches the existing workflow:

   - Zip deploy:
     ```bash
     cd launch && zip -r ../launch.zip . -x 'node_modules/*'
     az webapp deploy -g <resource-group> -n <app-name> --src-path ../launch.zip --type zip
     ```
   - Or `az webapp up` from inside `launch/`:
     ```bash
     cd launch && az webapp up -g <resource-group> -n <app-name> --runtime 'NODE:18-lts'
     ```
   - Or push to the App Service git remote (deploy from the `launch/` folder).

The platform runs `npm start` (Linux) or routes through `web.config` (Windows) → `node server.js`,
which listens on the injected `PORT`. No `npm install` is required (zero dependencies).

---

*Internal / confidential. Synthetic data only — educational information, not investment advice.*
