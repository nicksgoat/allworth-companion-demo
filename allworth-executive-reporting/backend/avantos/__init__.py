"""Avantos — the Allworth advisor operating console.

Aggregates the planning book of business into one deterministic cockpit feed:
plan health, ledger shortfalls, drift alerts, publication state, and open
portal work items per household, with book-level rollups. Read-only over the
planning store, projection cache, and publication registry — no Synapse calls,
so the cockpit stays fast and testable.
"""
