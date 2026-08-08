# Sending email from a Synapse (or any Azure) pipeline

The `mailer` module exposes a tiny HTTP endpoint the pipeline calls to send mail.
The pipeline authenticates with its **managed identity** — no user login, no API
key, no change to the app's auth layer. The send runs **app-only** from a
service mailbox, so it works unattended.

```
POST https://allworth-executive-reporting.azurewebsites.net/mailer/api/send
Content-Type: application/json
Authorization: Bearer <managed-identity token for this app>   ← Synapse adds this

{
  "to": ["cfo@allworthfinancial.com"],          // string or array
  "subject": "Nightly flows report is ready",
  "body": "The July net-flows report finished at 06:00.",
  "cc": ["analytics@allworthfinancial.com"],     // optional
  "html": false,                                  // optional
  "mailbox": "automations@allworthfinancial.com"  // optional; defaults to MAILER_FROM
}
```

Response: `{ "success": true, "sent": true }` (or `{ "success": false, "error": … }` with a matching HTTP status).

## Synapse Web activity settings

Add a **Web** activity in your pipeline:

| Field | Value |
|-------|-------|
| URL | `https://allworth-executive-reporting.azurewebsites.net/mailer/api/send` |
| Method | `POST` |
| Headers | `Content-Type: application/json` |
| Body | the JSON above (use `@concat(...)`/pipeline params for dynamic values) |
| Authentication | **System-Assigned Managed Identity** |
| Resource | `<this app's Entra client id>` — `7943565d-4f1c-4eff-98b6-f43eb8f5dcd5` (or `api://7943565d-4f1c-4eff-98b6-f43eb8f5dcd5`) |

Synapse mints a token for that Resource with its workspace managed identity and
attaches it. App Service Easy Auth + the app's JWT middleware validate it exactly
like any tool request — that's the whole auth story.

## One-time setup (owner/admin)

1. **Application Graph permission (send as a mailbox, no user):**
   On app registration `7943565d-4f1c-4eff-98b6-f43eb8f5dcd5` add **Application**
   permission **Mail.Send** (and Mail.Read if pipelines will also read) →
   **Grant admin consent**. (This is the *Application* column, distinct from the
   Delegated Mail.Send used by the interactive Brief.)

2. **Service mailbox + app setting:** pick a sending mailbox (e.g.
   `automations@allworthfinancial.com`) and set app setting `MAILER_FROM` to it
   (add it to the deploy workflow's app-settings, like the other settings).

3. **Scope which mailbox the app may send as (recommended):** create an Exchange
   **ApplicationAccessPolicy** restricting this app id to only the service
   mailbox, so app-only Mail.Send can't send as arbitrary users:
   ```powershell
   New-ApplicationAccessPolicy -AppId 7943565d-4f1c-4eff-98b6-f43eb8f5dcd5 `
     -PolicyScopeGroupId automations@allworthfinancial.com `
     -AccessRight RestrictAccess -Description "Mailer app: automations mailbox only"
   ```

4. **Authorize the pipeline's identity:** the Synapse workspace managed identity
   must present a token this app accepts. With no email allowlist configured, any
   valid tenant token for the app's audience is accepted. To lock it down, add an
   app role (e.g. `Mailer.Send`) and assign it to the Synapse MI, then set
   `AUTH_REQUIRED_ROLES=Mailer.Send` (optional hardening).

## Calling it from Python (in-repo jobs / notebooks)

Skip HTTP entirely and import the library:

```python
from mailer import send_email

send_email(
    to="cfo@allworthfinancial.com",
    subject="Nightly flows report is ready",
    body="The July net-flows report finished at 06:00.",
    mailbox="automations@allworthfinancial.com",   # app-only
)
```

Same one-time setup (application Mail.Send consent + mailbox) applies.

## Event-driven ("an email triggers the pipeline") — BUILT (poll model)

An incoming email can now kick off a pipeline. You register a **rule** (which
mailbox + optional match → which pipeline trigger URL); a scheduled caller pings
`/mailer/api/poll` every few minutes; the app reads new mail app-only, and POSTs
each matching message to your rule's `target_url`. No public webhook, no auth
changes.

### 1. Create a trigger rule (once)
```
POST /mailer/api/rules
{
  "mailbox": "automations@allworthfinancial.com",   // or omit → MAILER_FROM
  "target_url": "https://<your-pipeline-trigger>",   // where the email is POSTed
  "subject_contains": "sync complete",                // optional match
  "from_contains": "envestnet.com"                    // optional match
}
```
Rules are watermarked from creation time, so only NEW mail fires them.
Manage with `GET /mailer/api/rules` and `DELETE /mailer/api/rules/<id>`.

### 2. Schedule the poll
Add a **timer/tumbling-window trigger** in Synapse/ADF that runs a Web activity
every 2–5 minutes:

| Field | Value |
|-------|-------|
| URL | `https://allworth-executive-reporting.azurewebsites.net/mailer/api/poll` |
| Method | `POST` |
| Authentication | System-Assigned Managed Identity |
| Resource | `7943565d-4f1c-4eff-98b6-f43eb8f5dcd5` |

Response: `{ "dispatched": N, "rules": M }`.

### 3. What your pipeline receives
For each matching email the app POSTs to your `target_url`:
```json
{ "rule_id": "…", "mailbox": "…",
  "message": { "id": "…", "from": "…", "fromName": "…",
               "subject": "…", "receivedAt": "…", "preview": "…" } }
```
If you set the `MAILER_EVENT_SECRET` app setting, each POST is signed with an
`X-Mailer-Signature: sha256=<hmac>` header so your receiver can verify it came
from us. Dispatch is at-least-once and in order: a failed POST is retried on the
next poll (the watermark only advances past successes).

> Needs **Application Mail.Read** admin-consented (same place you added Mail.Send)
> so the poll can read the mailbox app-only.

### Want real-time instead of polling?
A Graph **webhook subscription** delivers within seconds, but its callback must be
a *public* endpoint (Microsoft calls it anonymously), which requires opening the
app's auth boundary (an `auth_middleware` bypass + an Easy Auth excluded path).
That's a deliberate, separately-reviewed security change — ask and we'll do it.
