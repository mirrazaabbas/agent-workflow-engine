import unittest

import engine


class WorkflowTests(unittest.TestCase):
    def test_happy_path(self):
        workflow = engine.Workflow(
            [
                engine.Step("classify", engine.classify),
                engine.Step("plan", engine.plan),
                engine.Step("compare", engine.compare_evidence, condition=engine.is_research),
                engine.Step("execute", engine.execute),
            ]
        )
        result = workflow.run({"request": "Research AI agents"})
        self.assertEqual(result["workflow_status"], "completed")
        self.assertTrue(result["evidence_compared"])
        self.assertEqual([event.status for event in workflow.events], ["ok", "ok", "ok", "ok"])

    def test_conditional_step_is_skipped(self):
        workflow = engine.Workflow(
            [
                engine.Step("classify", engine.classify),
                engine.Step("compare", engine.compare_evidence, condition=engine.is_research),
            ]
        )
        result = workflow.run({"request": "Write a short greeting"})
        self.assertEqual(result["workflow_status"], "completed")
        self.assertEqual(workflow.events[-1].status, "skipped")

    def test_approval_gate_blocks_without_callback(self):
        workflow = engine.Workflow([engine.Step("publish", lambda _state: {"published": True}, requires_approval=True)])
        result = workflow.run({"request": "publish"})
        self.assertEqual(result["workflow_status"], "blocked")
        self.assertTrue(result["approval_required"])
        self.assertEqual(workflow.events[-1].status, "blocked")

    def test_approval_gate_allows_approved_step(self):
        workflow = engine.Workflow(
            [engine.Step("publish", lambda _state: {"published": True}, requires_approval=True)],
            approval_fn=lambda _name, _state: True,
        )
        result = workflow.run({"request": "publish"})
        self.assertEqual(result["workflow_status"], "completed")
        self.assertTrue(result["published"])

    def test_validation(self):
        with self.assertRaises(ValueError):
            engine.Step("", engine.classify)
        with self.assertRaises(ValueError):
            engine.Step("x", engine.classify, retries=-1)
        with self.assertRaises(ValueError):
            engine.classify({"request": ""})
        with self.assertRaises(ValueError):
            engine.plan({})
        with self.assertRaises(ValueError):
            engine.Workflow([], max_steps=0)
        with self.assertRaises(ValueError):
            engine.Workflow([engine.Step("x", engine.classify)], max_steps=0)
        with self.assertRaises(TypeError):
            engine.Workflow([]).run("not-a-dict")

    def test_max_steps_guard(self):
        steps = [engine.Step(f"step-{index}", lambda _state: {}) for index in range(3)]
        with self.assertRaises(ValueError):
            engine.Workflow(steps, max_steps=2)

    def test_retry_failure(self):
        def fail(_state):
            raise RuntimeError("boom")

        workflow = engine.Workflow([engine.Step("fail", fail, retries=1)])
        result = workflow.run({"request": "test"})
        self.assertEqual(result["workflow_status"], "failed")
        self.assertEqual(result["failed_step"], "fail")
        self.assertEqual(len(workflow.events), 2)

    def test_invalid_step_return_is_failure(self):
        workflow = engine.Workflow([engine.Step("bad", lambda _state: "not-a-dict", retries=0)])
        result = workflow.run({"request": "test"})
        self.assertEqual(result["workflow_status"], "failed")
        self.assertIn("must return a dictionary", result["error"])

    def test_event_log_resets_between_runs(self):
        workflow = engine.Workflow([engine.Step("classify", engine.classify)])
        workflow.run({"request": "Research AI"})
        workflow.run({"request": "Research Python"})
        self.assertEqual(len(workflow.events), 1)


if __name__ == "__main__":
    unittest.main()
