# Agent Workflow Engine

[![CI](https://github.com/mirrazaabbas/agent-workflow-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/mirrazaabbas/agent-workflow-engine/actions/workflows/ci.yml)

A Python orchestration framework for explicit, testable AI-agent workflows. It keeps control flow visible while demonstrating state transitions, conditional routing, retries, approval gates, permission scopes, resumability, idempotency, real model/tool adapter boundaries, and execution telemetry.

## Architecture

```text
Request
  ↓
Workflow runtime
  ├─ conditions / routing
  ├─ retries + exponential backoff
  ├─ timeout controls
  ├─ permission scopes
  ├─ human approval gates
  ├─ idempotency protection
  └─ checkpoints / resume
        ↓
   Tool / model adapters
     ├─ RAG HTTP tool
     └─ OpenAI-compatible model adapter
        ↓
portfolio-evidence/v1
        ↓
AI Evaluation Harness
```

The original synchronous `engine.py` API remains available for simple deterministic workflows. `runtime.py` adds the production-oriented async execution layer.

## Implemented engineering features

### Workflow reliability

- Sync and async-compatible workflow steps
- Explicit shared state
- Conditional routing
- Per-step retries
- Exponential retry backoff
- Step timeouts
- Configurable maximum-step protection
- Graceful blocked and failed states
- Duplicate step-name validation

### Safety and side effects

- Human approval gates
- Explicit permission scopes
- Idempotency ledger for duplicate side-effect protection
- Checkpoint-safe execution

### Persistence and resumability

- In-memory checkpoint store
- Atomic JSON-file checkpoint store
- Resume-from-checkpoint execution
- Completed-step skipping during recovery

### Real integration boundaries

`adapters.py` includes:

- `OpenAICompatibleModelAdapter` for OpenAI-compatible chat-completion APIs
- `RagHttpTool` for the RAG Knowledge Assistant `/answer` API
- Structured model result metadata including provider, model, latency and token usage when supplied by the provider
- Credential lookup through environment variables rather than source code

The real provider adapter is unit-tested with an injected transport. CI does not require or expose external model credentials.

### Observability

- Attempt, latency, status and error events
- JSON event export
- OpenTelemetry-compatible tracer bridge in `telemetry.py`
- Runtime-event metadata suitable for downstream audit/evaluation records

## Cross-project portfolio integration

`portfolio_pipeline.py` demonstrates an actual contract between three portfolio systems:

```text
RAG Knowledge Assistant
        ↓ HTTP /answer
Agent Workflow Engine
        ↓ portfolio-evidence/v1
AI Evaluation Harness
```

The pipeline executes the RAG call through an `external-read` permission scope and emits an evaluator-ready record containing:

- final output
- retrieved source IDs
- citation IDs
- retrieved context
- retrieval ranks/scores
- tool-call metadata
- latency
- agent runtime events

Run it against a running RAG Knowledge Assistant:

```bash
python portfolio_pipeline.py \
  "Explain how grounded RAG reduces unsupported claims" \
  --rag-url http://127.0.0.1:8000 \
  --top-k 3
```

## Basic workflow example

```python
from engine import Step, Workflow

workflow = Workflow(
    [Step("publish", lambda state: {"published": True}, requires_approval=True)],
    approval_fn=lambda step_name, state: True,
)

result = workflow.run({"request": "publish approved content"})
```

A protected step is blocked instead of executed when approval is missing or denied.

## Docker

```bash
docker build -t agent-workflow-engine .
docker run --rm agent-workflow-engine
```

## Quality checks

```bash
python -m pip install -r requirements-dev.txt
ruff check .
coverage run -m unittest discover -s tests -v
coverage report --fail-under=85
python engine.py
```

CI verifies Python 3.10, 3.11 and 3.12, compiles all integration modules, runs lint and branch coverage, executes the test suite, smoke-tests the original workflow, and validates cross-project imports.

## Dependency maintenance

Dependabot is configured for weekly Python and GitHub Actions dependency updates.

## Remaining engineering milestones

The repository intentionally does **not** claim every distributed-agent capability. High-value next steps include:

- Parallel/fan-out workflow execution
- Database-backed checkpoint and idempotency stores for multi-worker deployments
- Queue/distributed worker execution
- Full OpenTelemetry SDK/collector integration test similar to the RAG project
- Real-provider integration tests in an opt-in secret-enabled environment
- MCP server/client adapters with permission enforcement
- More complete token/cost budgets and rate-limit policies

## Skills demonstrated

Python · AI Agents · Orchestration · Async Workflows · Conditional Routing · Human-in-the-loop · Permission Scopes · Idempotency · Checkpointing · Reliability · OpenTelemetry Interfaces · RAG Integration · Model Adapters · Testing · Docker · CI/CD

## Scope and evidence

The repository implements and tests orchestration, resumability, safety controls, model/tool adapter boundaries, and cross-project evidence generation. It does not claim an autonomous production agent platform, distributed scheduler, hosted model service, or MCP server that is not present in the code.
