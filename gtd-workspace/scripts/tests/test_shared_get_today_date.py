"""Tests for ~/.openclaw/workspace/scripts/shared/get_today_date.py.

3 tests: GTD_TZ env honored, default America/Denver fallback, span tz attribute.

Imports shared script by path; confirms RED when shared script is absent.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime as _datetime
from pathlib import Path
import zoneinfo as _zoneinfo

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

_SHARED_SCRIPT = Path.home() / ".openclaw" / "workspace" / "scripts" / "shared" / "get_today_date.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("shared_get_today_date", _SHARED_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_profile_tz_used_when_gtd_tz_set(monkeypatch) -> None:
    """Production failure: GTD_TZ injected from profile is ignored; wrong date served."""
    monkeypatch.setenv("GTD_TZ", "Europe/London")
    mod = _load_mod()
    result = mod.run_get_today_date()
    expected = _datetime.now(_zoneinfo.ZoneInfo("Europe/London")).strftime("%Y-%m-%d")
    assert result["date"] == expected


def test_default_tz_used_when_gtd_tz_unset(monkeypatch) -> None:
    """Production failure: env fallback not applied; date is wrong when GTD_TZ absent."""
    monkeypatch.delenv("GTD_TZ", raising=False)
    mod = _load_mod()
    result = mod.run_get_today_date()
    expected = _datetime.now(_zoneinfo.ZoneInfo("America/Denver")).strftime("%Y-%m-%d")
    assert result["date"] == expected


def test_main_span_has_tz_attribute(monkeypatch, capsys) -> None:
    """Production failure: tz attribute absent from shared span; Honeycomb cannot query tz."""
    monkeypatch.setenv("GTD_TZ", "America/Denver")
    mod = _load_mod()
    exporter = InMemorySpanExporter()
    mod._configure_tracer(exporter)
    with pytest.raises(SystemExit):
        mod.main()
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "gtd.get_today_date"
    assert span.attributes.get("tz")
