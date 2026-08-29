"""Optional AI-powered execution step for the deterministic workflow engine."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ai_platform import AIClient


def make_ai_execute(client: AIClient) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def execute_with_ai(state: dict[str, Any]) -> dict[str, Any]:
        request = state.get("request")
        plan = state.get("plan")
        if not isinstance(request, str) or not request.strip():
            raise ValueError("Workflow state must contain a non-empty request.")
        if not isinstance(plan, list) or not plan:
            raise ValueError("Workflow state must contain a non-empty plan.")
        system = (
            "You are the execution model inside a controlled workflow. Follow the supplied plan, "
            "do not claim tool actions that were not actually performed, and return a concise result."
        )
        user = f"Request: {request}\nPlan: {json.dumps(plan)}"
        return {"ai_result": client.generate(system, user)}

    return execute_with_ai
