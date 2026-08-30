"""Observability bridges for workflow runtime events.

This module has no hard OpenTelemetry dependency. Any tracer implementing the
small ``start_as_current_span`` interface can be supplied, including a real
``opentelemetry.trace.Tracer`` in production or a fake tracer in tests.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Protocol

from runtime import RuntimeEvent


class Span(Protocol):
    def set_attribute(self, key: str, value: Any) -> None: ...


class SpanContext(Protocol):
    def __enter__(self) -> Span: ...

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None: ...


class Tracer(Protocol):
    def start_as_current_span(self, name: str) -> SpanContext: ...


def events_as_json(events: list[RuntimeEvent]) -> str:
    return json.dumps([asdict(event) for event in events], sort_keys=True)


def export_events_to_tracer(events: list[RuntimeEvent], tracer: Tracer, *, run_id: str) -> int:
    """Export one span per runtime event and return the number exported."""
    if not run_id.strip():
        raise ValueError("run_id cannot be empty")
    exported = 0
    for event in events:
        with tracer.start_as_current_span(f"agent.step.{event.step}") as span:
            span.set_attribute("agent.run_id", run_id)
            span.set_attribute("agent.step", event.step)
            span.set_attribute("agent.status", event.status)
            span.set_attribute("agent.attempt", event.attempt)
            span.set_attribute("agent.elapsed_ms", event.elapsed_ms)
            if event.detail:
                span.set_attribute("agent.detail", event.detail)
        exported += 1
    return exported
