"""Small provider-neutral chat client for OpenAI-compatible, Anthropic, and Gemini APIs."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


class AIClient(Protocol):
    def generate(self, system: str, user: str) -> str: ...


@dataclass(frozen=True)
class AIConfig:
    provider: str
    api_key: str
    model: str
    base_url: str
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> AIConfig:
        provider = os.getenv("AI_PROVIDER", "openai").strip().lower()
        defaults = {
            "openai": ("OPENAI_API_KEY", "gpt-4.1-mini", "https://api.openai.com/v1"),
            "anthropic": ("ANTHROPIC_API_KEY", "claude-sonnet-4-5", "https://api.anthropic.com"),
            "gemini": ("GEMINI_API_KEY", "gemini-2.5-flash", "https://generativelanguage.googleapis.com/v1beta"),
        }
        if provider not in defaults:
            raise RuntimeError("AI_PROVIDER must be openai, anthropic, or gemini.")
        key_name, default_model, default_base = defaults[provider]
        api_key = (os.getenv("AI_API_KEY") or os.getenv(key_name) or "").strip()
        if not api_key:
            raise RuntimeError(f"Configure AI_API_KEY or {key_name}.")
        try:
            timeout = float(os.getenv("AI_TIMEOUT_SECONDS", "30"))
        except ValueError as exc:
            raise RuntimeError("AI_TIMEOUT_SECONDS must be numeric.") from exc
        if timeout <= 0:
            raise RuntimeError("AI_TIMEOUT_SECONDS must be greater than zero.")
        return cls(
            provider=provider,
            api_key=api_key,
            model=os.getenv("AI_MODEL", default_model).strip() or default_model,
            base_url=os.getenv("AI_BASE_URL", default_base).rstrip("/"),
            timeout_seconds=timeout,
        )


class HTTPAIClient:
    def __init__(self, config: AIConfig):
        self.config = config

    def _post(self, url: str, payload: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"AI provider HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"AI provider connection failed: {exc.reason}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("AI provider returned invalid JSON.") from exc
        if not isinstance(data, dict):
            raise RuntimeError("AI provider returned an unexpected response shape.")
        return data

    def generate(self, system: str, user: str) -> str:
        if not system.strip() or not user.strip():
            raise ValueError("System and user messages must be non-empty.")
        provider = self.config.provider
        if provider == "openai":
            data = self._post(
                f"{self.config.base_url}/chat/completions",
                {
                    "model": self.config.model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                {"Authorization": f"Bearer {self.config.api_key}"},
            )
            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                raise RuntimeError("OpenAI-compatible provider returned no choices.")
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            text = message.get("content") if isinstance(message, dict) else None
        elif provider == "anthropic":
            data = self._post(
                f"{self.config.base_url}/v1/messages",
                {
                    "model": self.config.model,
                    "max_tokens": 1024,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                {
                    "x-api-key": self.config.api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            content = data.get("content")
            first = content[0] if isinstance(content, list) and content else None
            text = first.get("text") if isinstance(first, dict) else None
        else:
            data = self._post(
                f"{self.config.base_url}/models/{self.config.model}:generateContent?key={self.config.api_key}",
                {
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                    "generationConfig": {"temperature": 0},
                },
                {},
            )
            candidates = data.get("candidates")
            first = candidates[0] if isinstance(candidates, list) and candidates else None
            content = first.get("content") if isinstance(first, dict) else None
            parts = content.get("parts") if isinstance(content, dict) else None
            part = parts[0] if isinstance(parts, list) and parts else None
            text = part.get("text") if isinstance(part, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("AI provider returned no text.")
        return text.strip()


def create_ai_client() -> HTTPAIClient:
    return HTTPAIClient(AIConfig.from_env())
