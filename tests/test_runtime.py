import asyncio
import tempfile
import unittest
from pathlib import Path

import runtime


class AsyncWorkflowRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_then_success(self):
        calls = {"count": 0}

        async def flaky(_state):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("temporary")
            return {"ok": True}

        workflow = runtime.AsyncWorkflow(
            [runtime.AsyncStep("flaky", flaky, retries=1, retry_delay_seconds=0)]
        )
        result = await workflow.run({"request": "x"}, run_id="retry")
        self.assertEqual(result["workflow_status"], "completed")
        self.assertEqual([event.status for event in workflow.events], ["error", "ok"])

    async def test_timeout_fails_safely(self):
        async def slow(_state):
            await asyncio.sleep(0.05)
            return {"done": True}

        workflow = runtime.AsyncWorkflow(
            [runtime.AsyncStep("slow", slow, timeout_seconds=0.005)]
        )
        result = await workflow.run({}, run_id="timeout")
        self.assertEqual(result["workflow_status"], "failed")
        self.assertEqual(result["failed_step"], "slow")
        self.assertEqual(workflow.events[-1].status, "timeout")

    async def test_permission_scope_blocks_write(self):
        workflow = runtime.AsyncWorkflow(
            [runtime.AsyncStep("publish", lambda _state: {"published": True}, permission_scope="write")]
        )
        result = await workflow.run({}, run_id="permission")
        self.assertEqual(result["workflow_status"], "blocked")
        self.assertIn("permission scope", result["error"])

    async def test_permission_scope_allows_explicit_write(self):
        workflow = runtime.AsyncWorkflow(
            [runtime.AsyncStep("publish", lambda _state: {"published": True}, permission_scope="write")],
            permission_policy=runtime.PermissionPolicy(frozenset({"read", "write"})),
        )
        result = await workflow.run({}, run_id="permission-ok")
        self.assertEqual(result["workflow_status"], "completed")
        self.assertTrue(result["published"])

    async def test_idempotency_prevents_duplicate_side_effect(self):
        calls = {"count": 0}

        def publish(state):
            calls["count"] += 1
            return {"published": state["document_id"]}

        step = runtime.AsyncStep(
            "publish",
            publish,
            permission_scope="write",
            idempotency_key_fn=lambda state: state["document_id"],
        )
        ledger = runtime.IdempotencyLedger()
        policy = runtime.PermissionPolicy(frozenset({"read", "write"}))
        workflow = runtime.AsyncWorkflow([step], permission_policy=policy, idempotency_ledger=ledger)

        first = await workflow.run({"document_id": "doc-1"}, run_id="same-run")
        second = await workflow.run({"document_id": "doc-1"}, run_id="same-run")

        self.assertEqual(first["workflow_status"], "completed")
        self.assertEqual(second["workflow_status"], "completed")
        self.assertEqual(calls["count"], 1)
        self.assertEqual(workflow.events[-1].status, "idempotent_skip")

    async def test_checkpoint_resume_skips_completed_steps(self):
        store = runtime.InMemoryCheckpointStore()
        calls = []

        async def first(_state):
            calls.append("first")
            return {"first": True}

        async def second(_state):
            calls.append("second")
            return {"second": True}

        workflow = runtime.AsyncWorkflow(
            [runtime.AsyncStep("first", first), runtime.AsyncStep("second", second)],
            checkpoint_store=store,
        )
        result = await workflow.run({}, run_id="resume")
        self.assertEqual(result["workflow_status"], "completed")

        calls.clear()
        resumed = await workflow.run({}, run_id="resume", resume=True)
        self.assertEqual(resumed["workflow_status"], "completed")
        self.assertEqual(calls, [])
        self.assertIn("checkpoint_skip", [event.status for event in workflow.events])

    async def test_approval_gate(self):
        workflow = runtime.AsyncWorkflow(
            [
                runtime.AsyncStep(
                    "dangerous",
                    lambda _state: {"done": True},
                    requires_approval=True,
                )
            ],
            approval_fn=lambda _step, _state: False,
        )
        result = await workflow.run({}, run_id="approval")
        self.assertEqual(result["workflow_status"], "blocked")
        self.assertTrue(result["approval_required"])


class CheckpointStoreTests(unittest.TestCase):
    def test_json_checkpoint_round_trip_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            store = runtime.JsonCheckpointStore(Path(directory))
            checkpoint = runtime.Checkpoint("run_1", {"value": 3}, ("one",))
            store.save(checkpoint)
            loaded = store.load("run_1")
            self.assertEqual(loaded, checkpoint)
            store.delete("run_1")
            self.assertIsNone(store.load("run_1"))

    def test_json_checkpoint_rejects_unsafe_run_id(self):
        with tempfile.TemporaryDirectory() as directory:
            store = runtime.JsonCheckpointStore(Path(directory))
            with self.assertRaises(ValueError):
                store.load("../escape")

    def test_validation(self):
        with self.assertRaises(ValueError):
            runtime.AsyncStep("", lambda _state: {})
        with self.assertRaises(ValueError):
            runtime.AsyncStep("x", lambda _state: {}, retries=-1)
        with self.assertRaises(ValueError):
            runtime.AsyncStep("x", lambda _state: {}, timeout_seconds=0)
        with self.assertRaises(ValueError):
            runtime.AsyncStep("x", lambda _state: {}, backoff_multiplier=0.5)
        with self.assertRaises(ValueError):
            runtime.AsyncWorkflow([], max_steps=0)
        with self.assertRaises(ValueError):
            runtime.AsyncWorkflow(
                [runtime.AsyncStep("same", lambda _state: {}), runtime.AsyncStep("same", lambda _state: {})]
            )


if __name__ == "__main__":
    unittest.main()
