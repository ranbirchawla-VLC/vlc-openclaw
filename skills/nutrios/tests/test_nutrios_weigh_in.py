"""Tests for nutrios_weigh_in — append-only, supersedes-aware."""
import json
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from nutrios_models import ToolResult, WeighIn
import nutrios_store as store
import nutrios_weigh_in as tool


_NOW = datetime(2026, 4, 24, 18, 0, 0, tzinfo=timezone.utc)
_TZ = "America/Denver"


def _argv(**kwargs) -> str:
    payload = {"user_id": "alice", "now": _NOW.isoformat(), "tz": _TZ}
    payload.update(kwargs)
    return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_weigh_in_rejects_extra_field(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(_argv(weight_lbs=200.0, bogus=1))


def test_weigh_in_rejects_missing_weight(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(_argv())


# ---------------------------------------------------------------------------
# Weight bounds — rendered rejection (Tripwire 4)
# ---------------------------------------------------------------------------

def test_weigh_in_zero_weight_rendered_reject(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(weight_lbs=0))
    assert isinstance(result, ToolResult)
    assert "Invalid weight" in result.display_text


def test_weigh_in_negative_weight_rendered_reject(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(weight_lbs=-10.0))
    assert "Invalid weight" in result.display_text


def test_weigh_in_excessive_weight_rendered_reject(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(weight_lbs=1500.0))
    assert "Invalid weight" in result.display_text


def test_weigh_in_invalid_weight_does_not_write(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(weight_lbs=0))
    assert store.tail_jsonl("alice", "weigh_ins.jsonl", 10) == []


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_weigh_in_happy_path(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(weight_lbs=218.5))
    assert "218.5 lbs" in result.display_text
    assert result.state_delta["last_weigh_in_id"] == 1

    raw = store.tail_jsonl("alice", "weigh_ins.jsonl", 10)
    assert len(raw) == 1
    assert raw[0]["id"] == 1
    assert raw[0]["weight_lbs"] == 218.5
    assert raw[0]["supersedes"] is None


def test_weigh_in_consecutive_increments_counter(tmp_data_root, setup_user):
    setup_user("alice")
    r1 = tool.main(_argv(weight_lbs=220.0))
    r2 = tool.main(_argv(weight_lbs=219.0))
    assert r1.state_delta["last_weigh_in_id"] == 1
    assert r2.state_delta["last_weigh_in_id"] == 2


def test_weigh_in_default_date_is_local_today(tmp_data_root, setup_user):
    """Without weigh_in_date, ts_iso anchors to noon-local on local-today."""
    setup_user("alice")
    tool.main(_argv(weight_lbs=218.0))
    raw = store.tail_jsonl("alice", "weigh_ins.jsonl", 1)
    # The local date should be 2026-04-24 (Friday in Denver)
    ts = raw[0]["ts_iso"]
    # Noon local Denver = 18:00 UTC (MDT is UTC-6 in late April)
    assert "2026-04-24" in ts


def test_weigh_in_explicit_date(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(weight_lbs=219.5, weigh_in_date="2026-04-22"))
    raw = store.tail_jsonl("alice", "weigh_ins.jsonl", 1)
    assert "2026-04-22" in raw[0]["ts_iso"]


# ---------------------------------------------------------------------------
# supersedes
# ---------------------------------------------------------------------------

def test_weigh_in_supersedes_existing_id_succeeds(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(weight_lbs=220.0))  # id=1
    result = tool.main(_argv(weight_lbs=219.5, supersedes=1))  # id=2 supersedes id=1
    assert result.state_delta["last_weigh_in_id"] == 2

    raw = store.tail_jsonl("alice", "weigh_ins.jsonl", 10)
    assert len(raw) == 2
    assert raw[1]["supersedes"] == 1


def test_weigh_in_supersedes_missing_id_rendered_reject(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(weight_lbs=219.5, supersedes=99))
    assert "doesn't exist" in result.display_text or "does not exist" in result.display_text
    assert "weigh-in" in result.display_text
    # No write occurred
    assert store.tail_jsonl("alice", "weigh_ins.jsonl", 10) == []


# ---------------------------------------------------------------------------
# Trend rendering — change line appears when prior data older than since_days
# ---------------------------------------------------------------------------

def test_weigh_in_change_line_appears_with_old_prior(tmp_data_root, setup_user):
    """A weigh-in older than 7d shows up as 'prior' in the trend line."""
    setup_user("alice")
    # Seed via the tool itself so id monotonicity matches engine assumptions
    tool.main(_argv(weight_lbs=220.0, weigh_in_date="2026-04-14"))  # 10 days prior
    result = tool.main(_argv(weight_lbs=218.0))
    assert "lbs" in result.display_text
    # current 218.0, prior 220.0 → delta -2.0
    assert "2.0" in result.display_text
    # Sign should reflect a loss (U+2212 minus or plain '-')
    assert "−" in result.display_text or "-" in result.display_text


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------

def test_weigh_in_isolation(tmp_data_root, setup_user):
    setup_user("alice")
    setup_user("bob")
    tool.main(_argv(weight_lbs=218.0))
    assert store.tail_jsonl("bob", "weigh_ins.jsonl", 10) == []
