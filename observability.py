"""Optional OpenTelemetry SDK integration for agent runtime events."""
from __future__ import annotations

import os
from typing import Any

from runtime import RuntimeEvent
from telemetry import export_events_to_tracer


def configure_tracer(
    *,
    service_name: str = "agent-workflow-engine",
    endpoint: str | None = None,
) -> Any:
    """Create an OTLP/HTTP tracer without making OpenTelemetry a core dependency."""
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        raise RuntimeError(
            "OpenTelemetry SDK dependencies are not installed; install the observability extra."
        ) from exc

    if not service_name.strip():
        raise ValueError("service_name cannot be empty")
    resolved_endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if not resolved_endpoint:
        raise ValueError("an OTLP/HTTP traces endpoint is required")

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=resolved_endpoint)))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


def export_runtime_events(
    events: list[RuntimeEvent],
    *,
    run_id: str,
    tracer: Any,
) -> int:
    """Export runtime events through the existing tracer bridge."""
    return export_events_to_tracer(events, tracer, run_id=run_id)
