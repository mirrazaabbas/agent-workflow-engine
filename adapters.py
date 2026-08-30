"""Provider and tool adapters for real agent integrations.

The core workflow runtime stays provider-independent. These adapters offer a
small, inspectable bridge to OpenAI-compatible chat APIs and the public HTTP
contract exposed by the RAG Knowledge Assistant.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

Transport = Callable[[urllib.request.Request, float], bytes]


@dataclass(frozen=True)
class ModelResult:
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0


class ModelAdapter(Protocol):
    async def generate(self, messages: list[dict[str, str]]) -> ModelResult: ...


def _default_transport(request: urllib.request.Request, timeout: float) -> bytes:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"HTTP request failed: {exc.reason}") from exc


def _validated_http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be an absolute http(s) URL")
    return value.rstrip("/")


@dataclass
class OpenAICompatibleModelAdapter:
    """Minimal async adapter for OpenAI-compatible chat-completion endpoints."""

    model: str
    endpoint: str = "https://api.openai.com/v1/chat/completions"
    api_key_env: str = "OPENAI_API_KEY"
    timeout_seconds: float = 30.0
    transport: Transport = _default_transport

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model cannot be empty")
        self.endpoint = _validated_http_url(self.endpoint)
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    async def generate(self, messages: list[dict[str, str]]) -> ModelResult:
        return await asyncio.to_thread(self._generate_sync, messages)

    def _generate_sync(self, messages: list[dict[str, str]]) -> ModelResult:
        if not messages:
            raise ValueError("messages cannot be empty")
        api_key = os.getenv(self.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(f"Missing model credential in {self.api_key_env}")

        payload = json.dumps({"model": self.model, "messages": messages}).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = time.perf_counter()
        raw = self.transport(request, self.timeout_seconds)
        elapsed = int((time.perf_counter() - started) * 1000)
        try:
            response = json.loads(raw.decode("utf-8"))
            text = response["choices"][0]["message"]["content"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Model provider returned an invalid response") from exc
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Model provider returned an empty response")
        usage = response.get("usage") or {}
        return ModelResult(
            text=text,
            provider=urlparse(self.endpoint).netloc,
            model=self.model,
            input_tokens=_optional_int(usage.get("prompt_tokens")),
            output_tokens=_optional_int(usage.get("completion_tokens")),
            latency_ms=elapsed,
        )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Provider token usage must be numeric") from exc


@dataclass
class RagHttpTool:
    """HTTP tool adapter for the RAG Knowledge Assistant ``/answer`` endpoint."""

    base_url: str
    timeout_seconds: float = 20.0
    transport: Transport = _default_transport

    def __post_init__(self) -> None:
        self.base_url = _validated_http_url(self.base_url)
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    async def answer(self, query: str, *, top_k: int = 3) -> dict[str, Any]:
        return await asyncio.to_thread(self._answer_sync, query, top_k)

    def _answer_sync(self, query: str, top_k: int) -> dict[str, Any]:
        if not query.strip():
            raise ValueError("query cannot be empty")
        if top_k < 1 or top_k > 10:
            raise ValueError("top_k must be between 1 and 10")
        payload = json.dumps({"query": query, "top_k": top_k}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/answer",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        raw = self.transport(request, self.timeout_seconds)
        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("RAG service returned invalid JSON") from exc
        if not isinstance(response, dict):
            raise RuntimeError("RAG service response must be an object")
        if not isinstance(response.get("answer"), str):
            raise RuntimeError("RAG service response is missing answer")
        if not isinstance(response.get("passages"), list):
            raise RuntimeError("RAG service response is missing passages")
        return response
