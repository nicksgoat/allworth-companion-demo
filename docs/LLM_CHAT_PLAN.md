# LLM Chat Plan

## Goal

Add a real language model to make the app feel conversational while keeping financial calculations deterministic, auditable, and safe.

## Recommended Architecture

Use a hybrid model:

```text
Mobile chat
  -> FastAPI /api/chat
  -> Orchestrator
    -> classify intent with rules or LLM
    -> run deterministic planning/portfolio tools
    -> ask LLM to explain tool results
    -> safety and audit checks
  -> structured ChatResponse
```

The LLM should not be the source of portfolio math, tax estimates, or retirement calculations. It should explain, summarize, ask clarifying questions, and prepare advisor-ready language.

## Modes

### Demo Mode

```bash
MOBILEAPP_CHAT_MODE=demo
```

Current behavior. Uses keyword intent classification and deterministic tool summaries.

### LLM Mode

```bash
MOBILEAPP_CHAT_MODE=llm
OPENAI_API_KEY=...
```

Planned behavior. Runs tools and asks the model to explain the result.

### Local Model Mode

```bash
MOBILEAPP_CHAT_MODE=local
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Optional path for local testing without cloud credentials.

## Suggested New Files

```text
services/api/app/llm_client.py
services/api/app/prompts.py
services/api/app/safety.py
services/api/app/audit.py
services/api/tests/test_llm_mode.py
```

## LLM Responsibilities

Allowed:

- Explain tool results in plain language.
- Ask follow-up questions.
- Summarize tradeoffs.
- Draft advisor-prep notes.
- Identify missing data.
- Convert structured action items into client-friendly language.

Not allowed:

- Place trades.
- Present tax/legal advice as final.
- Invent account data.
- Override deterministic tool outputs.
- Hide assumptions.
- Generate unsupported performance claims.

## Prompt Inputs

The model should receive:

- User message.
- Short conversation history.
- Household profile.
- Portfolio summary.
- Tool result.
- Safety instructions.
- Output format instructions.

The model should not receive:

- Raw secrets.
- Unnecessary PII.
- Data for other clients.
- Internal connector credentials.

## Output Requirements

The model response should:

- Be concise.
- Mention uncertainty when live data is missing.
- Reference the tool result, not invent new values.
- End with a helpful next step.
- Include advisor-review language for high-impact recommendations.

## Audit Metadata

Each LLM response should record:

- Provider.
- Model.
- Prompt version.
- Tool calls.
- Token usage.
- Latency.
- Safety result.
- Trace ID.

## Rollout Plan

1. Add LLM client behind env flag.
2. Keep current demo behavior as fallback.
3. Add tests for blocked commands and expected response shape.
4. Add prompt snapshots.
5. Add UI disclosure for model/tool trace.
6. Add advisor brief generation.
7. Add production audit logging.

## Example User Flow

User:

```text
What should I do about NVDA being 54% of my Robinhood account?
```

Backend:

1. Classifies as portfolio/concentration.
2. Runs portfolio review or concentration tool.
3. Gives the LLM the tool output.
4. LLM explains options: gradual diversification, tax-aware selling, advisor review.
5. API returns `answer`, `cards`, and `actions`.

Frontend:

1. Appends assistant message.
2. Renders structured cards.
3. Shows suggested follow-up prompts.
