import tempfile
import unittest
from pathlib import Path

from production import (
    CircuitBreaker,
    SQLiteCheckpointStore,
    SQLiteIdempotencyLedger,
    TokenBucketRateLimiter,
    UsageBudget,
    fan_out,
)
from runtime import Checkpoint


class ProductionStoreTests(unittest.TestCase):
    def test_sqlite_checkpoint_store_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteCheckpointStore(Path(directory) / "runtime.db")
            checkpoint = Checkpoint("run-1", {"value": 7}, ("one", "two"))
            store.save(checkpoint)
            loaded = store.load("run-1")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.state, {"value": 7})
            self.assertEqual(loaded.completed_steps, ("one", "two"))
            store.delete("run-1")
            self.assertIsNone(store.load("run-1"))

    def test_sqlite_idempotency_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = SQLiteIdempotencyLedger(Path(directory) / "runtime.db")
            self.assertFalse(ledger.seen("run", "send", "key"))
            ledger.mark("run", "send", "key")
            ledger.mark("run", "send", "key")
            self.assertTrue(ledger.seen("run", "send", "key"))

    def test_usage_budget(self):
        budget = UsageBudget(max_input_tokens=10, max_output_tokens=5, max_cost_usd=0.1)
        budget.consume(input_tokens=4, output_tokens=2, cost_usd=0.02)
        self.assertEqual(budget.input_tokens, 4)
        with self.assertRaises(RuntimeError):
            budget.consume(input_tokens=7)
        with self.assertRaises(ValueError):
            budget.consume(cost_usd=-1)

    def test_circuit_breaker(self):
        now = [0.0]
        breaker = CircuitBreaker(
            failure_threshold=2,
            recovery_seconds=10,
            clock=lambda: now[0],
        )
        self.assertTrue(breaker.allow())
        breaker.record_failure()
        breaker.record_failure()
        self.assertEqual(breaker.state, "open")
        self.assertFalse(breaker.allow())
        now[0] = 11.0
        self.assertEqual(breaker.state, "half-open")
        breaker.record_success()
        self.assertEqual(breaker.state, "closed")


class ProductionAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_rate_limiter_uses_injected_sleep(self):
        now = [0.0]
        sleeps = []

        async def sleeper(delay):
            sleeps.append(delay)
            now[0] += delay

        limiter = TokenBucketRateLimiter(
            rate_per_second=2,
            capacity=1,
            clock=lambda: now[0],
            sleeper=sleeper,
        )
        await limiter.acquire()
        await limiter.acquire()
        self.assertEqual(len(sleeps), 1)
        self.assertAlmostEqual(sleeps[0], 0.5)

    async def test_fan_out(self):
        async def first():
            return 1

        async def second():
            return 2

        result = await fan_out({"a": first, "b": second}, max_concurrency=2)
        self.assertEqual(result, {"a": 1, "b": 2})

        async def fail():
            raise RuntimeError("boom")

        result = await fan_out({"bad": fail}, return_exceptions=True)
        self.assertIsInstance(result["bad"], RuntimeError)

        with self.assertRaises(ValueError):
            await fan_out({"a": first}, max_concurrency=0)


if __name__ == "__main__":
    unittest.main()
