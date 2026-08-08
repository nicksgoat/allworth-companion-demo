"""NFBC — agentic Net Flows Bonus Calculation adjustment console.

Mounted at /nfbc by backend/app.py. Serves a spreadsheet-style queue where
Claude proposes an NFBC adjustment for each open Jira ticket (labeled
``NFBC_Adjustment``); the user verifies/edits each row; confirming a row writes
the adjustment to live Synapse, runs the rollforward stored procedures, posts
the drafted reply as a Jira comment, and transitions the ticket to Done.

Principle: **Claude proposes; code is the source of truth for numbers and
writes.** All dollar amounts/periods are computed/validated in ``compute.py``
and all SQL writes go through ``synapse_nfbc.py``.
"""
