import json
import os
import unittest
from unittest.mock import patch

import adapters
import portfolio_pipeline
import telemetry
from runtime import RuntimeEvent


class FakeRagTool:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    async def answer(self, query, *, top_k=3):
        self.calls += 1
        if self.fail:
            raise RuntimeError("rag unavailable")
        return {
            "answer": f"Grounded answer for {query}",
            "passages": [
                {"rank": 1, "score": 0.9, "source": "doc-a", "text": "Evidence A"},
                {"rank": 2, "score": 0.8, "source": "doc-b", "text": "Evidence B"},
            ][:top_k],
        }


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_compatible_adapter(self):
        def transport(request, timeout):
            self.assertEqual(timeout, 5)
            self.assertEqual(request.method, "POST")
            self.assertTrue(request.get_header("Authorization").startswith("Bearer "))
            return json.dumps(
                {
                    "choices": [{"message": {"content": "hello"}}],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                }
            ).encode()

        adapter = adapters.OpenAICompatibleModelAdapter(
            model="test-model", timeout_seconds=5, transport=transport
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-secret"}):
            result = await adapter.generate([{"role": "user", "content": "Hi"}])
        self.assertEqual(result.text, "hello")
        self.assertEqual(result.input_tokens, 4)
        self.assertEqual(result.output_tokens, 2)

    async def test_model_adapter_failure_modes(self):
        adapter = adapters.OpenAICompatibleModelAdapter(
            model="test-model", transport=lambda _request, _timeout: b"{}"
        )
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            await adapter.generate([{"role": "user", "content": "Hi"}])
        with patch.dict(os.environ, {"OPENAI_API_KEY": "x"}):
            with self.assertRaises(ValueError):
                await adapter.generate([])
            with self.assertRaises(RuntimeError):
                await adapter.generate([{"role": "user", "content": "Hi"}])

    async def test_rag_http_tool(self):
        def transport(request, timeout):
            self.assertEqual(timeout, 4)
            self.assertTrue(request.full_url.endswith("/answer"))
            return json.dumps(
                {"answer": "ok", "passages": [{"source": "s", "text": "t"}]}
            ).encode()

        tool = adapters.RagHttpTool("https://rag.example.test/", 4, transport)
        response = await tool.answer("query", top_k=1)
        self.assertEqual(response["answer"], "ok")
        with self.assertRaises(ValueError):
            await tool.answer("")
        with self.assertRaises(ValueError):
            await tool.answer("query", top_k=11)

    def test_adapter_validation(self):
        with self.assertRaises(ValueError):
            adapters.OpenAICompatibleModelAdapter(model="")
        with self.assertRaises(ValueError):
            adapters.OpenAICompatibleModelAdapter(model="x", endpoint="file:///tmp/model")
        with self.assertRaises(ValueError):
            adapters.RagHttpTool("not-a-url")
        with self.assertRaises(ValueError):
            adapters.RagHttpTool("https://rag.example", timeout_seconds=0)
        with self.assertRaises(RuntimeError):
            adapters._optional_int("nope")

    async def test_portfolio_pipeline_builds_shared_contract(self):
        result = await portfolio_pipeline.run_portfolio_pipeline(
            "Explain grounded RAG", FakeRagTool(), run_id="integration-1", top_k=2
        )
        self.assertEqual(result["workflow_status"], "completed")
        record = result["evaluation_record"]
        self.assertEqual(record["schema_version"], "portfolio-evidence/v1")
        self.assertEqual(record["producer"], "agent-workflow-engine")
        self.assertEqual(record["upstream_system"], "rag-knowledge-assistant")
        self.assertEqual(record["retrieved_ids"], ["doc-a", "doc-b"])
        self.assertEqual(record["tool_calls"][0]["name"], "rag.answer")
        self.assertTrue(record["runtime_events"])

    async def test_portfolio_pipeline_failure_and_validation(self):
        with self.assertRaises(ValueError):
            await portfolio_pipeline.run_portfolio_pipeline("", FakeRagTool())
        failing = FakeRagTool(fail=True)
        result = await portfolio_pipeline.run_portfolio_pipeline("question", failing)
        self.assertEqual(result["workflow_status"], "failed")
        self.assertEqual(failing.calls, 2)
        with self.assertRaises(RuntimeError):
            portfolio_pipeline.build_agent_evidence_record(
                "q", {"answer": "a", "passages": [{}]}, latency_ms=1, runtime_events=[]
            )


class FakeSpan:
    def __init__(self):
        self.attributes = {}

    def set_attribute(self, key, value):
        self.attributes[key] = value


class FakeSpanContext:
    def __init__(self, span):
        self.span = span

    def __enter__(self):
        return self.span

    def __exit__(self, exc_type, exc, traceback):
        return None


class FakeTracer:
    def __init__(self):
        self.spans = []

    def start_as_current_span(self, name):
        span = FakeSpan()
        span.attributes["span.name"] = name
        self.spans.append(span)
        return FakeSpanContext(span)


class TelemetryTests(unittest.TestCase):
    def test_json_and_tracer_export(self):
        events = [
            RuntimeEvent("retrieve", "ok", 1, 12),
            RuntimeEvent("publish", "blocked", detail="approval denied"),
        ]
        payload = json.loads(telemetry.events_as_json(events))
        self.assertEqual(payload[0]["step"], "retrieve")
        tracer = FakeTracer()
        exported = telemetry.export_events_to_tracer(events, tracer, run_id="run-1")
        self.assertEqual(exported, 2)
        self.assertEqual(tracer.spans[0].attributes["agent.status"], "ok")
        self.assertEqual(tracer.spans[1].attributes["agent.detail"], "approval denied")
        with self.assertRaises(ValueError):
            telemetry.export_events_to_tracer(events, tracer, run_id="")


if __name__ == "__main__":
    unittest.main()
