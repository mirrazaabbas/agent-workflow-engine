# Changelog

All notable changes to this project are documented here. The project follows semantic versioning for tagged releases.

## 1.0.0 - 2026-08-30

### Added
- Installable `agent-workflow-engine` Python package and `agent-workflow` CLI.
- Async workflow runtime with retries, exponential backoff, timeouts, checkpoints and resume support.
- Permission scopes, human approval gates and idempotency protection.
- SQLite-backed checkpoints and idempotency for durable single-host/multi-process execution.
- Concurrent fan-out helper, token/cost budgets, token-bucket rate limiting and circuit breaker primitives.
- OpenAI-compatible model and RAG HTTP adapters.
- Permission-aware MCP-style JSON-RPC adapter boundary.
- OpenTelemetry SDK/OTLP integration and Jaeger verification in CI.
- Cross-project `portfolio-evidence/v1` integration with the RAG and Evaluation projects.
- Package build verification, CodeQL, dependency auditing, CycloneDX SBOM generation and container scanning.
- Tagged release workflow with build provenance attestation.

### Scope
This release is a portfolio-grade orchestration framework, not a hosted distributed agent platform. Queue-backed distributed workers and a complete MCP protocol implementation remain separate future extensions.
