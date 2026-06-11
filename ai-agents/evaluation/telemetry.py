"""
OpenTelemetry setup for MindSafe.

Configures a tracer that exports to Jaeger via OTLP gRPC when
OTEL_EXPORTER_OTLP_ENDPOINT is set (e.g. "http://jaeger:4317").
Falls back to a no-op tracer when the env var is absent so local
runs and tests work without a running collector.
"""

import os
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
_SERVICE_NAME  = os.getenv("OTEL_SERVICE_NAME", "mindsafe-api")

_tracer: trace.Tracer | None = None


def init_tracing() -> trace.Tracer:
    """
    Call once at app startup. Returns a configured tracer.
    If no OTLP endpoint is configured, returns a no-op tracer.
    """
    global _tracer
    if _tracer is not None:
        return _tracer

    if _OTLP_ENDPOINT:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            resource = Resource.create({SERVICE_NAME: _SERVICE_NAME})
            provider = TracerProvider(resource=resource)
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=_OTLP_ENDPOINT))
            )
            trace.set_tracer_provider(provider)
        except ImportError:
            # OTLP exporter not installed; fall through to no-op
            pass

    _tracer = trace.get_tracer("mindsafe")
    return _tracer


def get_tracer() -> trace.Tracer:
    global _tracer
    if _tracer is None:
        return init_tracing()
    return _tracer


@contextmanager
def span(name: str, **attrs):
    """Convenience context manager: creates a span and sets string attributes."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as s:
        for k, v in attrs.items():
            s.set_attribute(k, str(v))
        yield s
