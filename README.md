# Agent Workflow Engine

A small Python orchestration framework for deterministic multi-step AI-agent workflows. It models explicit steps, state updates, retry policies, failure states, and execution telemetry without hiding the control flow behind a large framework.

## Current architecture

`Request → Intent Classification → Planning → Execution → Structured Result`

See [ARCHITECTURE.md](ARCHITECTURE.md) for the reliability model and production roadmap.

## Features

- Composable workflow steps
- Explicit shared state
- Per-step retries
- Graceful failure state
- Attempt/latency/error telemetry
- State reset between runs
- Deterministic sample workflow
- Automated tests and CI across Python 3.10–3.12
- Dockerized example runtime

## Run

```bash
python engine.py
```

## Docker

```bash
docker build -t agent-workflow-engine .
docker run --rm agent-workflow-engine
```

## Next engineering milestones

- Async and parallel execution
- Conditional routing
- Persistent checkpoints
- Tool permission scopes
- Timeout/cancellation support
- Human approval for high-impact actions
- Model/tool adapters
- Token/cost tracing

## Skills demonstrated

Python · AI Agents · Orchestration · State Management · Reliability · Observability · Testing · Docker

## Current scope

This repository demonstrates workflow orchestration mechanics. It does not claim to include a production LLM or autonomous tool-execution layer yet.
