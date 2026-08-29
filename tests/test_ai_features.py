from __future__ import annotations

import unittest
from unittest.mock import patch

import ai_features
import ai_platform
import engine


class FakeClient:
    def generate(self, system: str, user: str) -> str:
        self.system = system
        self.user = user
        return "AI workflow result"


class AiFeatureTests(unittest.TestCase):
    def test_ai_execute_step(self) -> None:
        client = FakeClient()
        workflow = engine.Workflow(
            [
                engine.Step("classify", engine.classify),
                engine.Step("plan", engine.plan),
                engine.Step("ai_execute", ai_features.make_ai_execute(client)),
            ]
        )
        result = workflow.run({"request": "Compare RAG architectures"})
        self.assertEqual(result["workflow_status"], "completed")
        self.assertEqual(result["ai_result"], "AI workflow result")
        self.assertIn("Request:", client.user)

    def test_provider_response_shapes(self) -> None:
        cases = [
            ("openai", {"choices": [{"message": {"content": "openai ok"}}]}, "openai ok"),
            ("anthropic", {"content": [{"text": "claude ok"}]}, "claude ok"),
            (
                "gemini",
                {"candidates": [{"content": {"parts": [{"text": "gemini ok"}]}}]},
                "gemini ok",
            ),
        ]
        for provider, payload, expected in cases:
            client = ai_platform.HTTPAIClient(
                ai_platform.AIConfig(provider, "key", "model", "https://example.test")
            )
            with patch.object(client, "_post", return_value=payload):
                self.assertEqual(client.generate("system", "user"), expected)


if __name__ == "__main__":
    unittest.main()
