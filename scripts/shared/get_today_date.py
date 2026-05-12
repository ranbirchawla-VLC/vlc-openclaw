"""get_today_date -- return today's date in the agent timezone (shared version).

Usage: python3 get_today_date.py [ignored]

Self-contained: zero workspace imports. Reads GTD_TZ from env; falls back to
America/Denver. Returns {ok: true, data: {date: "YYYY-MM-DD"}}.
"""

from __future__ import annotations

import json
import os
import sys
import zoneinfo
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from opentelemetry import context as otel_context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace import StatusCode

_tracer_provider: Optional[TracerProvider] = None


def _configure_tracer(exporter=None) -> None:
    global _tracer_provider
    if exporter is None:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
        exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    from opentelemetry.propagate import set_global_textmap
    set_global_textmap(TraceContextTextMapPropagator())
    _tracer_provider = provider


def _get_tracer():
    if _tracer_provider is None:
        _configure_tracer()
    return _tracer_provider.get_tracer("shared-get-today-date")


@contextmanager
def _attach_parent_context():
    traceparent = os.environ.get("TRACEPARENT")
    if traceparent:
        from opentelemetry.propagate import extract
        ctx = extract({"traceparent": traceparent})
        token = otel_context.attach(ctx)
    else:
        token = otel_context.attach(otel_context.get_current())
    try:
        yield
    finally:
        otel_context.detach(token)


def _ok(data: dict) -> None:
    print(json.dumps({"ok": True, "data": data}))
    sys.exit(0)


def _err(code: str, message: str) -> None:
    print(json.dumps({"ok": False, "error": {"code": code, "message": message}}))
    sys.exit(1)


def run_get_today_date(tz_str: str | None = None) -> dict:
    """Return today's date and timezone as YYYY-MM-DD and IANA string."""
    tz_name = tz_str if tz_str is not None else os.environ.get("GTD_TZ", "America/Denver")
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except zoneinfo.ZoneInfoNotFoundError as exc:
        raise ValueError(f"invalid_timezone: not a valid IANA timezone: {tz_name!r}") from exc
    return {"date": datetime.now(tz).strftime("%Y-%m-%d"), "timezone": tz_name}


def _resolve_tz(user_id: str | None) -> str:
    """Resolve timezone: profile > GTD_TZ env var > America/Denver fallback."""
    tz_name = os.environ.get("GTD_TZ", "America/Denver")
    if user_id:
        storage_root = os.environ.get("GTD_STORAGE_ROOT", "")
        if storage_root:
            from pathlib import Path as _Path
            profile_path = _Path(storage_root) / "gtd-agent" / "users" / user_id / "profile.json"
            if profile_path.exists():
                try:
                    tz_name = json.loads(profile_path.read_text(encoding="utf-8")).get("timezone", tz_name)
                except (json.JSONDecodeError, OSError):
                    pass
    return tz_name


def main() -> None:
    user_id: str | None = None
    if len(sys.argv) > 1:
        try:
            parsed = json.loads(sys.argv[1])
            if isinstance(parsed, dict):
                user_id = parsed.get("user_id")
        except (json.JSONDecodeError, ValueError):
            pass

    with _attach_parent_context():
        tz_name = _resolve_tz(user_id)
        with _get_tracer().start_as_current_span("gtd.get_today_date") as span:
            try:
                result = run_get_today_date(tz_name)
                span.set_attribute("tz", tz_name)
                if user_id:
                    span.set_attribute("user.id", user_id)
                _ok(result)
            except ValueError as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.set_attributes({
                    "error.code": "invalid_timezone",
                    "error.type": type(exc).__name__,
                    "error.location": "run_get_today_date",
                    "error.context": f"tz={tz_name!r}",
                })
                _err("invalid_timezone", str(exc))


if __name__ == "__main__":
    main()
