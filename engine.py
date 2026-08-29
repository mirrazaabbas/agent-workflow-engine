"""Small production-style workflow engine for deterministic AI-agent orchestration."""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

StepFn = Callable[[dict[str, Any]], dict[str, Any]]
ConditionFn = Callable[[dict[str, Any]], bool]
ApprovalFn = Callable[[str, dict[str, Any]], bool]


@dataclass(frozen=True)
class Step:
    name: str
    fn: StepFn
    retries: int = 1
    condition: ConditionFn | None = None
    requires_approval: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Step name cannot be empty.")
        if self.retries < 0:
            raise ValueError("Step retries cannot be negative.")


@dataclass(frozen=True)
class RunEvent:
    step: str
    status: str
    attempt: int
    elapsed_ms: int
    detail: str = ""


@dataclass
class Workflow:
    steps: list[Step]
    approval_fn: ApprovalFn | None = None
    max_steps: int = 50
    events: list[RunEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.max_steps <= 0:
            raise ValueError("max_steps must be greater than zero.")
        if len(self.steps) > self.max_steps:
            raise ValueError("Workflow exceeds configured max_steps limit.")

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(state, dict):
            raise TypeError("Workflow state must be a dictionary.")

        self.events.clear()
        current = dict(state)
        for key in ("workflow_status", "failed_step", "error", "approval_required"):
            current.pop(key, None)

        for step in self.steps:
            if step.condition is not None and not step.condition(dict(current)):
                self.events.append(RunEvent(step.name, "skipped", 0, 0, "condition=false"))
                continue

            if step.requires_approval:
                if self.approval_fn is None:
                    current["workflow_status"] = "blocked"
                    current["failed_step"] = step.name
                    current["approval_required"] = True
                    self.events.append(
                        RunEvent(step.name, "blocked", 0, 0, "approval callback missing")
                    )
                    return current
                if not self.approval_fn(step.name, dict(current)):
                    current["workflow_status"] = "blocked"
                    current["failed_step"] = step.name
                    current["approval_required"] = True
                    self.events.append(RunEvent(step.name, "blocked", 0, 0, "approval denied"))
                    return current

            last_error: Exception | None = None
            for attempt in range(1, step.retries + 2):
                started = time.perf_counter()
                try:
                    update = step.fn(dict(current))
                    if not isinstance(update, dict):
                        raise TypeError(f"Step '{step.name}' must return a dictionary.")
                    current.update(update)
                    elapsed = int((time.perf_counter() - started) * 1000)
                    self.events.append(RunEvent(step.name, "ok", attempt, elapsed))
                    last_error = None
                    break
                except Exception as exc:
                    elapsed = int((time.perf_counter() - started) * 1000)
                    self.events.append(RunEvent(step.name, "error", attempt, elapsed, str(exc)))
                    last_error = exc

            if last_error is not None:
                current["workflow_status"] = "failed"
                current["failed_step"] = step.name
                current["error"] = str(last_error)
                return current

        current["workflow_status"] = "completed"
        return current


def classify(state: dict[str, Any]) -> dict[str, Any]:
    request = state.get("request")
    if not isinstance(request, str) or not request.strip():
        raise ValueError("State must contain a non-empty 'request' string.")
    text = request.lower()
    intent = "research" if any(term in text for term in ("research", "compare", "find")) else "general"
    return {"intent": intent}


def plan(state: dict[str, Any]) -> dict[str, Any]:
    if "intent" not in state:
        raise ValueError("Workflow state is missing 'intent'.")
    tasks = ["understand request", "collect relevant context", "produce structured result"]
    if state["intent"] == "research":
        tasks.insert(2, "compare evidence")
    return {"plan": tasks}


def compare_evidence(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("intent") != "research":
        raise ValueError("Evidence comparison is only valid for research requests.")
    return {"evidence_compared": True}


def execute(state: dict[str, Any]) -> dict[str, Any]:
    if "request" not in state or "plan" not in state:
        raise ValueError("Workflow state is missing request or plan data.")
    return {
        "result": {
            "summary": f"Workflow prepared for: {state['request']}",
            "tasks": list(state["plan"]),
        }
    }


def is_research(state: dict[str, Any]) -> bool:
    return state.get("intent") == "research"


def main() -> None:
    workflow = Workflow(
        [
            Step("classify", classify),
            Step("plan", plan),
            Step("compare_evidence", compare_evidence, condition=is_research),
            Step("execute", execute, retries=2),
        ]
    )
    state = workflow.run({"request": "Research and compare AI assistant architectures"})
    print(json.dumps(state, indent=2))
    print("\nObservability events:")
    print(json.dumps([asdict(event) for event in workflow.events], indent=2))


if __name__ == "__main__":
    main()
