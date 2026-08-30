# Production Runtime Upgrade

This branch adds a provider-independent async orchestration runtime alongside the existing synchronous engine.

Implemented in this upgrade:
- async and sync-compatible step functions
- step timeouts and safe timeout failure states
- exponential-backoff retries
- in-memory and JSON checkpoint stores
- resume-from-checkpoint execution
- permission scopes with explicit allow policies
- human approval gates in async workflows
- idempotency ledger for side-effect protection
- duplicate step-name validation for checkpoint safety
- CI coverage for the new runtime across Python 3.10–3.12

The existing `engine.py` API remains intact for backwards compatibility.
