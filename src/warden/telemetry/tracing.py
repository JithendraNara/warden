"""OpenTelemetry tracing for warden.

Every major runtime boundary — agent loop iterations, thinker calls,
tool execution, verification — emits a structured span. When the
OpenTelemetry SDK is not available the module exposes the same
surface but produces no-op spans, so the rest of the codebase stays
import-safe.

Configuration is driven by environment variables following the OTel
conventions, plus a short alias:

- ``OTEL_EXPORTER_OTLP_ENDPOINT`` / ``OTEL_SERVICE_NAME``
- ``WARDEN_TRACING`` — set to ``"disabled"`` to force the no-op
  implementation even when OTel is installed.

Langfuse works out of the box because it exposes an OTLP endpoint
(``/api/public/otel``). The operator only has to point
``OTEL_EXPORTER_OTLP_ENDPOINT`` and ``OTEL_EXPORTER_OTLP_HEADERS`` at
their Langfuse project.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

logger = logging.getLogger("warden.telemetry")

_TRACING_DISABLED_ENV = "WARDEN_TRACING"
_SERVICE_NAME_DEFAULT = "warden"


class _NoopSpan:
    """Span replacement used when OpenTelemetry is not installed."""

    def set_attribute(self, _key: str, _value: Any) -> None:
        return None

    def set_status(self, _status: Any) -> None:
        return None

    def record_exception(self, _exception: BaseException) -> None:
        return None


class _NoopTracer:
    @contextmanager
    def span(self, _name: str, _attributes: Mapping[str, Any] | None = None) -> Iterator[_NoopSpan]:
        yield _NoopSpan()


class Tracer:
    """Thin wrapper around an OpenTelemetry tracer (or a noop fallback)."""

    def __init__(self, impl: Any | None) -> None:
        self._impl = impl

    @property
    def enabled(self) -> bool:
        return self._impl is not None

    @contextmanager
    def span(
        self,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[Any]:
        if self._impl is None:
            yield _NoopSpan()
            return
        cm = self._impl.start_as_current_span(name)
        span = cm.__enter__()
        try:
            if attributes:
                for key, value in attributes.items():
                    try:
                        span.set_attribute(key, value)
                    except Exception:  # noqa: BLE001
                        pass
            yield span
        except BaseException as exc:
            try:
                span.record_exception(exc)
            except Exception:  # noqa: BLE001
                pass
            raise
        finally:
            cm.__exit__(None, None, None)


def configure(service_name: str = _SERVICE_NAME_DEFAULT) -> Tracer:
    """Initialize tracing and return a :class:`Tracer`.

    We only touch OpenTelemetry imports inside this function so the
    rest of the project stays dependency-light.
    """

    if os.environ.get(_TRACING_DISABLED_ENV, "").lower() == "disabled":
        return Tracer(None)

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        exporter: Any | None = None
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                    OTLPSpanExporter,
                )

                exporter = OTLPSpanExporter()
            except ImportError:
                logger.info("OTLP exporter not installed, skipping exporter wiring")

        provider = TracerProvider(
            resource=Resource.create({"service.name": service_name})
        )
        if exporter is not None:
            provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        impl = trace.get_tracer(service_name)
        return Tracer(impl)
    except ImportError:
        logger.debug("OpenTelemetry SDK not installed; tracing disabled.")
        return Tracer(None)
