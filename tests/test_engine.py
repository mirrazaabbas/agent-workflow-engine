import unittest

import engine


class WorkflowTests(unittest.TestCase):
    def test_happy_path(self):
        workflow = engine.Workflow([
            engine.Step("classify", engine.classify),
            engine.Step("plan", engine.plan),
            engine.Step("execute", engine.execute),
        ])
        result = workflow.run({"request": "Research AI agents"})
        self.assertEqual(result["workflow_status"], "completed")
        self.assertEqual(len(workflow.events), 3)

    def test_validation(self):
        with self.assertRaises(ValueError):
            engine.Step("", engine.classify)
        with self.assertRaises(ValueError):
            engine.Step("x", engine.classify, retries=-1)
        with self.assertRaises(ValueError):
            engine.classify({"request": ""})
        with self.assertRaises(ValueError):
            engine.plan({})

    def test_retry_failure(self):
        def fail(_state):
            raise RuntimeError("boom")

        workflow = engine.Workflow([engine.Step("fail", fail, retries=1)])
        result = workflow.run({"request": "test"})
        self.assertEqual(result["workflow_status"], "failed")
        self.assertEqual(result["failed_step"], "fail")
        self.assertEqual(len(workflow.events), 2)


if __name__ == "__main__":
    unittest.main()
