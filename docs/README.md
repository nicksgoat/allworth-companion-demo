# Documentation Index

This folder is the working handbook for the Allworth AI mobile planning
application.

Start here:

- [Allworth AI App Canonical Specification](ALLWORTH_AI_APP_CANONICAL.md):
  consolidated source of truth for product vision, current architecture, GPT-4o
  usage, provider-neutral LLM design, tool schemas, memory, safety, deployment,
  testing, and roadmap.

The older standalone product vision has been merged into the canonical
specification so there is one source of truth.

## Current References

- [Financial Tools](FINANCIAL_TOOLS.md): exact `simulate` and `rebalance`
  schemas, deterministic behavior, model data mapping, and tax calculations.
- [Redis Chat Memory](REDIS_CHAT_MEMORY.md): Redis-backed short-term
  conversation memory for the LLM.
- [Testing And Operations](TESTING_OPERATIONS.md): setup, run commands, test
  strategy, preview modes, and GPT-4o / Azure OpenAI deployment notes.

The old scattered planning docs were removed after consolidation. If a product,
architecture, roadmap, safety, MCP, memory, data-contract, or frontend question
is not answered by one of the current references above, use the canonical
specification and current source code as authoritative.
