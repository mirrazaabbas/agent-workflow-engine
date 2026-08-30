"""Production-oriented async runtime primitives for agent workflows.

This module intentionally uses only the Python standard library so the core
orchestration mechanics remain easy to inspect and test. It complements the
simple synchronous engine in ``engine.py`` with resumability, timeout controls,
permission scopes, idempotency, and exponential-backoff retries.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

State = dict[str, Any]
AsyncStepFn = Callable[[State], State | Awaitable[State]]
ConditionFn = Callable[[State], bool]
ApprovalFn = Callable[[str, State], bool | Awaitable[bool]]
IdempotencyKeyFn = Callable[[State], str]


@dataclass(frozen=True)
class RuntimeEvent:
    step: str
    status: str
    attempt: int = 0
    elapsed_ms: int = 0
    detail: str = ""


@dataclass(frozen=True)
class AsyncStep:
    name: str
    fn: AsyncStepFn
    retries: int = 0
    retry_delay_seconds: float = 0.0
    backoff_multiplier: float = 2.0
    timeout_seconds: float | None = None
    condition: ConditionFn | None = None
    requires_approval: bool = False
    permission_scope: str = "read"
    idempotency_key_fn: IdempotencyKeyFn | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Step name cannot be empty.")
        if self.retries < 0:
            raise ValueError("Step retries cannot be negative.")
        if self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds cannot be negative.")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be at least 1.")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive when provided.")
        if not self.permission_scope.strip():
            raise ValueError("permission_scope cannot be empty.")


@dataclass(frozen=True)
class Checkpoint:
    run_id: str
    state: State
    completed_steps: tuple[str, ...]


class CheckpointStore(Protocol):
    def load(self, run_id: str) -> Checkpoint | None: ...

    def save(self, checkpoint: Checkpoint) -> None: ...

    def delete(self, run_id: str) -> None: ...


@dataclass
class InMemoryCheckpointStore:
    _items: dict[str, Checkpoint] = field(default_factory=dict)

    def load(self, run_id: str) -> Checkpoint | None:
        checkpoint = self._items.get(run_id)
        if checkpoint is None:
            return None
        return Checkpoint(
            run_id=checkpoint.run_id,
            state=dict(checkpoint.state),
            completed_steps=tuple(checkpoint.completed_steps),
        )

    def save(self, checkpoint: Checkpoint) -> None:
        self._items[checkpoint.run_id] = Checkpoint(
            run_id=checkpoint.run_id,
            state=dict(checkpoint.state),
            completed_steps=tuple(checkpoint.completed_steps),
        )

    def delete(self, run_id: str) -> None:
        self._items.pop(run_id, None)


@dataclass
class JsonCheckpointStore:
    directory: Path

    def __post_init__(self) -> None:
        self.directory = Path(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        safe = "".join(ch for ch in run_id if ch.isalnum() or ch in {"-", "_"})
        if not safe or safe != run_id:
            raise ValueError("run_id must contain only letters, numbers, '-' or '_'.")
        return self.directory / f"{safe}.json"

    def load(self, run_id: str) -> Checkpoint | None:
        path = self._path(run_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return Checkpoint(
            run_id=str(payload["run_id"]),
            state=dict(payload["state"]),
            completed_steps=tuple(payload["completed_steps"]),
        )

    def save(self, checkpoint: Checkpoint) -> None:
        path = self._path(checkpoint.run_id)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(checkpoint), indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp, path)

    def delete(self, run_id: str) -> None:
        path = self._path(run_id)
        if path.exists():
            path.unlink()


@dataclass(frozen=True)
class PermissionPolicy:
    allowed_scopes: frozenset[str] = frozenset({"read"})

    def allows(self, scope: str) -> bool:
        return scope in self.allowed_scopes


@dataclass
class IdempotencyLedger:
    completed_keys: set[tuple[str, str, str]] = field(default_factory=set)

    def seen(self, run_id: str, step_name: str, key: str) -> bool:
        return (run_id, step_name, key) in self.completed_keys

    def mark(self, run_id: str, step_name: str, key: str) -> None:
        self.completed_keys.add((run_id, step_name, key))


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


@dataclass
class AsyncWorkflow:
    steps: list[AsyncStep]
    approval_fn: ApprovalFn | None = None
    checkpoint_store: CheckpointStore | None = None
    permission_policy: PermissionPolicy = field(default_factory=PermissionPolicy)
    idempotency_ledger: IdempotencyLedger = field(default_factory=IdempotencyLedger)
    max_steps: int = 100
    events: list[RuntimeEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.max_steps <= 0:
            raise ValueError("max_steps must be greater than zero.")
        if len(self.steps) > self.max_steps:
            raise ValueError("Workflow exceeds configured max_steps limit.")
        names = [step.name for step in self.steps]
        if len(names) != len(set(names)):
            raise ValueError("Step names must be unique for checkpoint-safe execution.")

    async def run(self, state: State, *, run_id: str, resume: bool = False) -> State:
        if not isinstance(state, dict):
            raise TypeError("Workflow state must be a dictionary.")
        if not run_id.strip():
            raise ValueError("run_id cannot be empty.")

        self.events.clear()
        current = dict(state)
        completed: list[str] = []

        if resume and self.checkpoint_store is not None:
            checkpoint = self.checkpoint_store.load(run_id)
            if checkpoint is not None:
                current = dict(checkpoint.state)
                completed = list(checkpoint.completed_steps)
                self.events.append(RuntimeEvent("workflow", "resumed", detail=run_id))

        for key in ("workflow_status", "failed_step", "error", "approval_required"):
            current.pop(key, None)

        for step in self.steps:
            if step.name in completed:
                self.events.append(RuntimeEvent(step.name, "checkpoint_skip"))
                continue

            if step.condition is not None and not step.condition(dict(current)):
                self.events.append(RuntimeEvent(step.name, "skipped", detail="condition=false"))
                completed.append(step.name)
                self._checkpoint(run_id, current, completed)
                continue

            if not self.permission_policy.allows(step.permission_scope):
                current.update(
                    workflow_status="blocked",
                    failed_step=step.name,
                    approval_required=False,
                    error=f"permission scope '{step.permission_scope}' is not allowed",
                )
                self.events.append(
                    RuntimeEvent(step.name, "blocked", detail=f"permission={step.permission_scope}")
                )
                return current

            if step.requires_approval:
                if self.approval_fn is None:
                    current.update(
                        workflow_status="blocked",
                        failed_step=step.name,
                        approval_required=True,
                    )
                    self.events.append(RuntimeEvent(step.name, "blocked", detail="approval missing"))
                    return current
                approved = bool(await _maybe_await(self.approval_fn(step.name, dict(current))))
                if not approved:
                    current.update(
                        workflow_status="blocked",
                        failed_step=step.name,
                        approval_required=True,
                    )
                    self.events.append(RuntimeEvent(step.name, "blocked", detail="approval denied"))
                    return current

            idempotency_key = None
            if step.idempotency_key_fn is not None:
                idempotency_key = step.idempotency_key_fn(dict(current))
                if not idempotency_key:
                    raise ValueError(f"Step '{step.name}' produced an empty idempotency key.")
                if self.idempotency_ledger.seen(run_id, step.name, idempotency_key):
                    self.events.append(RuntimeEvent(step.name, "idempotent_skip"))
                    completed.append(step.name)
                    self._checkpoint(run_id, current, completed)
                    continue

            last_error: Exception | None = None
            for attempt in range(1, step.retries + 2):
                started = asyncio.get_running_loop().time()
                try:
                    operation = _maybe_await(step.fn(dict(current)))
                    if step.timeout_seconds is None:
                        update = await operation
                    else:
                        update = await asyncio.wait_for(operation, timeout=step.timeout_seconds)
                    if not isinstance(update, dict):
                        raise TypeError(f"Step '{step.name}' must return a dictionary.")
                    current.update(update)
                    elapsed = int((asyncio.get_running_loop().time() - started) * 1000)
                    self.events.append(RuntimeEvent(step.name, "ok", attempt, elapsed))
                    if idempotency_key is not None:
                        self.idempotency_ledger.mark(run_id, step.name, idempotency_key)
                    completed.append(step.name)
                    self._checkpoint(run_id, current, completed)
                    last_error = None
                    break
                except Exception as exc:  # noqa: BLE001 - workflow boundary records failures
                    elapsed = int((asyncio.get_running_loop().time() - started) * 1000)
                    status = "timeout" if isinstance(exc, asyncio.TimeoutError) else "error"
                    self.events.append(RuntimeEvent(step.name, status, attempt, elapsed, str(exc)))
                    last_error = exc
                    if attempt <= step.retries:
                        delay = step.retry_delay_seconds * (step.backoff_multiplier ** (attempt - 1))
                        if delay:
                            await asyncio.sleep(delay)

            if last_error is not None:
                current.update(
                    workflow_status="failed",
                    failed_step=step.name,
                    error=str(last_error) or last_error.__class__.__name__,
                )
                return current

        current["workflow_status"] = "completed"
        self._checkpoint(run_id, current, completed)
        return current

    def _checkpoint(self, run_id: str, state: State, completed_steps: list[str]) -> None:
        if self.checkpoint_store is None:
            return
        self.checkpoint_store.save(
            Checkpoint(run_id=run_id, state=dict(state), completed_steps=tuple(completed_steps))
        )
