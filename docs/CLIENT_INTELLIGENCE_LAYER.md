# Client Intelligence Layer

## Purpose

The client intelligence layer is the future memory and learning system behind the app. It should help the app and advisor know the client better over time without retraining models on client data.

## What Self-Improving Means

The model itself does not retrain on client data. The system improves through three loops:

1. **Per-client learning**: interactions, transactions, and life events update that client's profile.
2. **Cross-client learning**: anonymized patterns across the book improve rules and advisor briefs.
3. **Outcome learning**: nudges and briefs are measured by outcomes such as opened, acted on, meeting created, or consolidation started.

## Nightly Learning Loop

Recommended loop:

```text
ingest daily episodes
  -> extract facts
  -> consolidate profiles
  -> supersede stale facts
  -> run nudge rules
  -> refresh advisor briefs
  -> log what changed and why
```

## Storage Model

The learning tree should be a view, not the database.

Recommended layers:

### Episode Store

Append-only record of source events:

- Conversations.
- Notes.
- Transactions.
- Emails.
- SMS metadata/content where approved.
- Meeting transcripts where approved.
- Advisor updates.

### Fact Atoms

Small facts with provenance:

```text
fact_id
client_id
fact_type
value
source_episode_id
confidence
status
created_at
superseded_at
deleted_at
```

Statuses:

- `active`
- `superseded`
- `deleted`
- `needs_review`

### Graph Edges

Facts link to:

- Accounts.
- Goals.
- People.
- Advisors.
- Tax topics.
- Life events.
- Preferences.

### Generated Views

The same fact base can render:

- Client transparency view.
- Advisor prep brief.
- Compliance audit view.
- Product nudge view.

## Taxonomy

Recommended fact map:

- Goals.
- Assets and held-away assets.
- Liabilities.
- Family and household.
- Risk tolerance.
- Tax considerations.
- Life events.
- Preferences.
- Advisor relationship.
- Engagement patterns.
- Open questions.
- Next best actions.

## Mobile App Use Cases

Near term:

- Show client-known assumptions.
- Explain why an insight appears.
- Prepare advisor brief cards.
- Show missing data questions.

Later:

- "What changed since last time?"
- "Why do you think this?"
- "Forget this detail."
- "Send this to my advisor."
- "What should I ask at my review?"

## Advisor Brief Use Cases

Advisor brief should summarize:

- Material changes.
- Open questions.
- Engagement signals.
- Held-away opportunities.
- Tax-sensitive items.
- Client preferences.
- Suggested next touch.

## Governance Requirements

Before persistence:

- Consent model.
- Retention policy.
- Deletion workflow.
- Role-based access.
- Source-level audit.
- Compliance review.
- Redaction policy for demos.

## Relation To The Current App

Current app:

- Uses synthetic data.
- Keeps chat in local state.
- Does not persist client memory.

Future app:

- Fetches governed facts from backend.
- Shows source/provenance for insights.
- Creates advisor briefs from current facts.
- Logs outcomes from nudges and advisor actions.
