"""Permission-aware MCP-style JSON-RPC client primitives.

This is intentionally a small transport abstraction rather than a claim of a
complete Model Context Protocol implementation. It provides schema validation,
tool registration, permission enforcement, and JSON-RPC request/response
handling that can be adapted to an MCP transport.
"""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

from runtime import PermissionPolicy

JsonObject = dict[str, Any]


class McpTransport(Protocol):
    async def call(self, method: str, params: JsonObject) -> JsonObject: ...


@dataclass(frozen=True)
class McpToolSpec:
    name: str
    permission_scope: str = "read"
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool name cannot be empty")
        if not self.permission_scope.strip():
            raise ValueError("permission_scope cannot be empty")


@dataclass
class PermissionedMcpClient:
    transport: McpTransport
    permission_policy: PermissionPolicy
    tools: dict[str, McpToolSpec]

    def __post_init__(self) -> None:
        for name, spec in self.tools.items():
            if name != spec.name:
                raise ValueError("tool mapping keys must match tool names")

    async def call_tool(self, name: str, arguments: JsonObject) -> JsonObject:
        spec = self.tools.get(name)
        if spec is None:
            raise KeyError(f"unknown MCP tool: {name}")
        if not self.permission_policy.allows(spec.permission_scope):
            raise PermissionError(
                f"MCP tool '{name}' requires permission scope '{spec.permission_scope}'"
            )
        if not isinstance(arguments, dict):
            raise TypeError("tool arguments must be an object")
        response = await self.transport.call(
            "tools/call",
            {"name": name, "arguments": dict(arguments)},
        )
        if not isinstance(response, dict):
            raise RuntimeError("MCP transport returned a non-object response")
        return response


HttpTransport = Callable[[urllib.request.Request, float], bytes]


def _default_http_transport(request: urllib.request.Request, timeout: float) -> bytes:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"MCP HTTP request failed: {exc.reason}") from exc


@dataclass
class JsonRpcHttpTransport:
    """Minimal JSON-RPC-over-HTTP transport with injectable I/O for tests."""

    endpoint: str
    timeout_seconds: float = 20.0
    transport: HttpTransport = _default_http_transport
    _request_id: int = 0

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("endpoint must be an absolute http(s) URL")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    async def call(self, method: str, params: JsonObject) -> JsonObject:
        if not method.strip():
            raise ValueError("method cannot be empty")
        if not isinstance(params, dict):
            raise TypeError("params must be an object")
        return await asyncio.to_thread(self._call_sync, method, params)

    def _call_sync(self, method: str, params: JsonObject) -> JsonObject:
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        raw = self.transport(request, self.timeout_seconds)
        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("MCP endpoint returned invalid JSON") from exc
        if not isinstance(response, dict):
            raise RuntimeError("MCP endpoint returned a non-object response")
        if response.get("error") is not None:
            raise RuntimeError(f"MCP JSON-RPC error: {response['error']}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("MCP JSON-RPC result must be an object")
        return result
