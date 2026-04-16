import pytest

from warden.telemetry.tracing import Tracer, configure


def test_configure_returns_tracer_without_otel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WARDEN_TRACING", "disabled")
    tracer = configure()
    assert isinstance(tracer, Tracer)
    assert tracer.enabled is False


def test_noop_span_context_is_safe() -> None:
    tracer = Tracer(None)
    with tracer.span("warden.test", {"answer": 42}) as span:
        span.set_attribute("extra", "value")
        span.record_exception(RuntimeError("noop"))
        span.set_status(None)
