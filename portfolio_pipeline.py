"""End-to-end RAG -> agent orchestration -> evaluation-record pipeline."""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict
from typing import Any, Protocol

from adapters import RagHttpTool
from runtime import AsyncStep, AsyncWorkflow, InMemoryCheckpointStore, PermissionPolicy

SCHEMA_VERSION = "portfolio-evidence/v1"


class RagTool(Protocol):
    async def answer(self, query: str, *, top_k: int = 3) -> dict[str, Any]: ...


def build_agent_evidence_record(
    query: str,
    rag_response: dict[str, Any],
    *,
    latency_ms: int,
    runtime_events: list[dict[str, Any]],
) -> dict[str, Any]:
    passages = rag_response.get("passages") or []
    retrieved_ids: list[str] = []
    context: list[str] = []
    retrieval: list[dict[str, Any]] = []
    for fallback_rank, passage in enumerate(passages, start=1):
        if not isinstance(passage, dict):
            raise RuntimeError("RAG passage must be an object")
        source = str(passage.get("source", "")).strip()
        text = str(passage.get("text", "")).strip()
        if not source or not text:
            raise RuntimeError("RAG passage is missing source or text")
        retrieved_ids.append(source)
        context.append(text)
        retrieval.append(
            {
                "id": source,
                "rank": int(passage.get("rank", fallback_rank)),
                "score": float(passage.get("score", 0.0)),
            }
        )

    answer = rag_response.get("answer")
    if not isinstance(answer, str):
        raise RuntimeError("RAG response is missing answer")
    return {
        "schema_version": SCHEMA_VERSION,
        "producer": "agent-workflow-engine",
        "upstream_system": "rag-knowledge-assistant",
        "query": query,
        "output": answer,
        "retrieved_ids": retrieved_ids,
        "citations": list(dict.fromkeys(retrieved_ids)),
        "context": context,
        "retrieval": retrieval,
        "tool_calls": [{"name": "rag.answer", "arguments": {"top_k": len(passages)}}],
        "latency_ms": latency_ms,
        "runtime_events": runtime_events,
    }


async def run_portfolio_pipeline(
    query: str,
    rag_tool: RagTool,
    *,
    run_id: str = "portfolio-demo",
    top_k: int = 3,
) -> dict[str, Any]:
    """Run a permission-scoped RAG tool call and package evaluator-ready evidence."""
    if not query.strip():
        raise ValueError("query cannot be empty")

    async def retrieve(state: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        response = await rag_tool.answer(state["query"], top_k=top_k)
        elapsed = int((time.perf_counter() - started) * 1000)
        return {"rag_response": response, "rag_latency_ms": elapsed}

    workflow = AsyncWorkflow(
        [
            AsyncStep(
                "retrieve_rag_evidence",
                retrieve,
                retries=1,
                retry_delay_seconds=0.01,
                timeout_seconds=30,
                permission_scope="external-read",
            )
        ],
        checkpoint_store=InMemoryCheckpointStore(),
        permission_policy=PermissionPolicy(frozenset({"read", "external-read"})),
    )
    result = await workflow.run({"query": query}, run_id=run_id)
    if result.get("workflow_status") != "completed":
        return result
    result["evaluation_record"] = build_agent_evidence_record(
        query,
        result["rag_response"],
        latency_ms=int(result["rag_latency_ms"]),
        runtime_events=[asdict(event) for event in workflow.events],
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RAG -> agent -> evaluation evidence demo.")
    parser.add_argument("query")
    parser.add_argument("--rag-url", default="http://127.0.0.1:8000")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    result = asyncio.run(
        run_portfolio_pipeline(args.query, RagHttpTool(args.rag_url), top_k=args.top_k)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
