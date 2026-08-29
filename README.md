# Agent Workflow Engine

[![CI](https://github.com/mirrazaabbas/agent-workflow-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/mirrazaabbas/agent-workflow-engine/actions/workflows/ci.yml)

A small Python orchestration framework for deterministic multi-step AI-agent workflows. It keeps control flow explicit while demonstrating state transitions, retries, conditional routing, approval gates, failure handling, and execution telemetry.

## Current architecture

```text
Request → Classification → Planning → Conditional Steps → Approval Gates → Execution
                                      ↓                         ↓
                                 skip / run                allow / block
                                      ↓                         ↓
                                  event telemetry + structured workflow state
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the reliability model and remaining production roadmap.

## Implemented features

- Composable workflow steps
- Explicit shared state with copy-on-step execution
- Per-step retry policies
- Conditional step routing
- Human-approval callbacks for protected steps
- Safe blocked state when approval is missing or denied
- Configurable maximum workflow step count
- Graceful terminal failure state
- Attempt, latency, status, and error telemetry
- State/event reset between runs
- Deterministic example workflow
- Dockerized example runtime
- Compile, Ruff, branch coverage, unit-test, and smoke-test CI
- Python 3.10, 3.11, and 3.12 test matrix

## Run

```bash
python engine.py
```

## Example approval gate

```python
from engine import Step, Workflow

workflow = Workflow(
    [Step("publish", lambda state: {"published": True}, requires_approval=True)],
    approval_fn=lambda step_name, state: True,
)

result = workflow.run({"request": "publish approved content"})
```

A protected step is blocked instead of executed when no approval callback exists or when approval is denied.

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

## Remaining engineering milestones

- Async and parallel execution
- Persistent checkpoints/state store
- Timeout and cancellation controls
- Tool permission scopes
- Real LLM/model adapters
- Real external tool/function-calling adapters
- Token/cost accounting and distributed tracing
- MCP integration

## Skills demonstrated

Python · AI Agents · Orchestration · Conditional Routing · Human-in-the-loop · State Management · Reliability · Observability · Testing · Docker · CI/CD

## Current scope

This repository implements orchestration mechanics and safety controls. It does **not** claim a production LLM, autonomous external tool layer, persistent checkpoint store, or MCP server yet; those remain explicit next steps.
