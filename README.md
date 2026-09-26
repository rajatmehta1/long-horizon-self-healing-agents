# Long-Horizon Self-Healing Agents

A demo of a durable, multi-agent customer support workflow: a refund case is
taken from complaint to payout, and survives crashes, transient failures, and
waits for human approval along the way.

[Temporal](https://temporal.io/) provides durability and orchestration;
[LangGraph](https://langchain-ai.github.io/langgraph/) agents do the reasoning.

## What it demonstrates

| Pattern | Where |
|---|---|
| **Durable execution** — the workflow resumes from the event log after a worker crash | `app/workflow.py` |
| **Transient retry** — `process_refund` fails twice, then succeeds via `RetryPolicy` | `app/activities.py` |
| **Human in the loop** — high-value refunds pause on a durable signal wait | `app/workflow.py` |
| **Policy gate** — refunds over the hard limit have no forward path, and no agent can route around it | `app/workflow.py` |

## Architecture

```
CustomerSupportWorkflow (Temporal)
  ├─ intake_agent       LLM  — order lookup + complaint classification
  ├─ eligibility_agent  rules — return window check + refund amount
  ├─ policy gate        rules — auto-approve / human review / hard block
  └─ comms_agent        LLM  — drafts the customer-facing message
```

Workflow code stays deterministic; all LLM and I/O work lives in activities.

Thresholds are in `app/contracts.py`:

- refund **≤ $500** → auto-approved
- **$500–$2000** → waits for human approval (90s, then escalates)
- **> $2000** → blocked by policy

## Setup

Requires Python 3.13+ and a running Temporal server.

```bash
pip install temporalio langgraph langchain-anthropic langchain-openrouter pydantic python-dotenv
temporal server start-dev --ui-port 3001
```

Create a `.env` in the project root:

```
DEFAULT_MODEL_PROVIDER=anthropic
DEFAULT_MODEL=claude-sonnet-5
DEFAULT_API_KEY=sk-ant-...
```

Set `DEFAULT_MODEL_PROVIDER=openrouter` to use OpenRouter instead, with
`OPENROUTER_API_KEY` and `OPENROUTER_MODEL`.

> `.env` is gitignored — never commit real keys.

## Running

Start the worker in one terminal:

```bash
python -m app.worker
```

Then drive it from another:

```bash
python -m app.trigger start ORDER-SMALL-001 "The laptop stand arrived bent and unusable."
python -m app.trigger status  customer-support-ORDER-MID-002
python -m app.trigger approve customer-support-ORDER-MID-002 reviewer-1 "Photos confirm damage"
python -m app.trigger reject  customer-support-ORDER-MID-002 reviewer-1 "Out of policy"
```

Watch it run at http://localhost:3001.

## Demo scenarios

Orders are hardcoded in `app/data.py`:

| Order | Value | Expected outcome |
|---|---|---|
| `ORDER-SMALL-001` | $149.99 | auto-approved, refund processed |
| `ORDER-MID-002` | $1,299.00 | pauses for human approval |
| `ORDER-LARGE-003` | $2,499.00 | blocked by policy gate |
| `ORDER-EXPIRED-004` | $89.99 | not eligible — return window expired |

Dates are evaluated against a fixed `DEMO_TODAY` so runs stay reproducible.

## Layout

```
app/
  workflow.py    Temporal workflow — orchestration and policy gate
  activities.py  activity implementations (LLM + I/O)
  worker.py      worker process
  trigger.py     CLI: start / approve / reject / status / demo
  contracts.py   pydantic models, thresholds, config
  data.py        hardcoded orders
  agents/        intake, eligibility, comms
```
