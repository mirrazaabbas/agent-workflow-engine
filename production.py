"""Production reliability primitives for multi-worker agent runtimes."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from runtime import Checkpoint

State = dict[str, Any]
AsyncJob = Callable[[], Any | Awaitable[Any]]


class SQLiteCheckpointStore:
    """SQLite-backed checkpoint store suitable for multiple processes on one host."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    run_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    completed_steps_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    def load(self, run_id: str) -> Checkpoint | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json, completed_steps_json FROM checkpoints WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return Checkpoint(
            run_id=run_id,
            state=dict(json.loads(row[0])),
            completed_steps=tuple(json.loads(row[1])),
        )

    def save(self, checkpoint: Checkpoint) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO checkpoints(run_id, state_json, completed_steps_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    completed_steps_json = excluded.completed_steps_json,
                    updated_at = excluded.updated_at
                """,
                (
                    checkpoint.run_id,
                    json.dumps(checkpoint.state, sort_keys=True),
                    json.dumps(list(checkpoint.completed_steps)),
                    time.time(),
                ),
            )

    def delete(self, run_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM checkpoints WHERE run_id = ?", (run_id,))


class SQLiteIdempotencyLedger:
    """Persistent idempotency ledger for duplicate side-effect protection."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency (
                    run_id TEXT NOT NULL,
                    step_name TEXT NOT NULL,
                    key TEXT NOT NULL,
                    completed_at REAL NOT NULL,
                    PRIMARY KEY(run_id, step_name, key)
                )
                """
            )

    def seen(self, run_id: str, step_name: str, key: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM idempotency
                WHERE run_id = ? AND step_name = ? AND key = ?
                """,
                (run_id, step_name, key),
            ).fetchone()
        return row is not None

    def mark(self, run_id: str, step_name: str, key: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO idempotency(run_id, step_name, key, completed_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, step_name, key, time.time()),
            )


@dataclass
class UsageBudget:
    """Enforces token and cost ceilings across a workflow run."""

    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    max_cost_usd: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def __post_init__(self) -> None:
        for value in (self.max_input_tokens, self.max_output_tokens):
            if value is not None and value < 0:
                raise ValueError("token budgets cannot be negative")
        if self.max_cost_usd is not None and self.max_cost_usd < 0:
            raise ValueError("cost budget cannot be negative")

    def consume(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        if min(input_tokens, output_tokens) < 0 or cost_usd < 0:
            raise ValueError("usage cannot be negative")
        next_input = self.input_tokens + input_tokens
        next_output = self.output_tokens + output_tokens
        next_cost = self.cost_usd + cost_usd
        if self.max_input_tokens is not None and next_input > self.max_input_tokens:
            raise RuntimeError("input token budget exceeded")
        if self.max_output_tokens is not None and next_output > self.max_output_tokens:
            raise RuntimeError("output token budget exceeded")
        if self.max_cost_usd is not None and next_cost > self.max_cost_usd:
            raise RuntimeError("cost budget exceeded")
        self.input_tokens = next_input
        self.output_tokens = next_output
        self.cost_usd = next_cost


@dataclass
class CircuitBreaker:
    """Small CLOSED/OPEN circuit breaker with time-based recovery."""

    failure_threshold: int = 3
    recovery_seconds: float = 30.0
    clock: Callable[[], float] = time.monotonic
    _failures: int = 0
    _opened_at: float | None = None

    def __post_init__(self) -> None:
        if self.failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if self.recovery_seconds < 0:
            raise ValueError("recovery_seconds cannot be negative")

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if self.clock() - self._opened_at >= self.recovery_seconds:
            return "half-open"
        return "open"

    def allow(self) -> bool:
        return self.state != "open"

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = self.clock()


@dataclass
class TokenBucketRateLimiter:
    """Async token-bucket limiter with injectable clock/sleeper for tests."""

    rate_per_second: float
    capacity: float = 1.0
    clock: Callable[[], float] = time.monotonic
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep
    _tokens: float = field(init=False)
    _updated: float = field(init=False)

    def __post_init__(self) -> None:
        if self.rate_per_second <= 0 or self.capacity <= 0:
            raise ValueError("rate_per_second and capacity must be positive")
        self._tokens = self.capacity
        self._updated = self.clock()

    async def acquire(self, amount: float = 1.0) -> None:
        if amount <= 0 or amount > self.capacity:
            raise ValueError("amount must be positive and no greater than capacity")
        while True:
            now = self.clock()
            elapsed = max(0.0, now - self._updated)
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate_per_second)
            self._updated = now
            if self._tokens >= amount:
                self._tokens -= amount
                return
            wait_for = (amount - self._tokens) / self.rate_per_second
            await self.sleeper(wait_for)


async def fan_out(
    jobs: dict[str, AsyncJob],
    *,
    max_concurrency: int = 4,
    return_exceptions: bool = False,
) -> dict[str, Any]:
    """Run independent jobs concurrently while preserving deterministic labels."""
    if max_concurrency <= 0:
        raise ValueError("max_concurrency must be positive")
    if len(jobs) != len(set(jobs)):
        raise ValueError("job labels must be unique")
    semaphore = asyncio.Semaphore(max_concurrency)

    async def run_one(label: str, job: AsyncJob) -> tuple[str, Any]:
        async with semaphore:
            try:
                value = job()
                if isinstance(value, Awaitable):
                    value = await value
                return label, value
            except Exception as exc:
                if return_exceptions:
                    return label, exc
                raise

    pairs = await asyncio.gather(*(run_one(label, job) for label, job in jobs.items()))
    return dict(pairs)
