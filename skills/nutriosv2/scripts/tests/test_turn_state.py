"""Tests for scripts/turn_state.py."""

from __future__ import annotations
import io
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import turn_state as ts_mod
from turn_state import (
    _find_session_file,
    _load_capability_prompt,
    _read_prior_intent,
    _reset_session_file,
    _write_intent_state,
    compute_turn_state,
)


def _make_sessions_json(session_dir: str, user_id: int, session_file_path: str) -> None:
    entry = {
        "origin": {
            "accountId": "nutriosv2",
            "from": f"telegram:{user_id}",
        },
        "sessionFile": session_file_path,
    }
    path = os.path.join(session_dir, "sessions.json")
    with open(path, "w") as f:
        json.dump({"agent:nutriosv2:main": entry}, f, indent=2)


def _make_caps(caps_dir: Path, content: str = "capability content") -> None:
    (caps_dir / "mesocycle_setup.md").write_text(content)


USER_ID = 8712103657


# ── capability prompt; fresh disk read ───────────────────────────────────────

def test_capability_prompt_reads_from_disk(tmp_path: Path) -> None:
    """_load_capability_prompt returns current file content without caching."""
    caps_dir = tmp_path / "caps"
    caps_dir.mkdir()
    (caps_dir / "mesocycle_setup.md").write_text("version 1")

    assert _load_capability_prompt("mesocycle_setup", str(caps_dir)) == "version 1"

    (caps_dir / "mesocycle_setup.md").write_text("version 2")

    assert _load_capability_prompt("mesocycle_setup", str(caps_dir)) == "version 2"


def test_capability_prompt_fresh_per_turn_via_compute(tmp_path: Path) -> None:
    """compute_turn_state returns mutated capability file content on second call."""
    caps_dir = tmp_path / "caps"
    caps_dir.mkdir()
    cap_file = caps_dir / "mesocycle_setup.md"
    cap_file.write_text("initial content")
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()

    r1 = compute_turn_state(
        "set up a new cycle",
        USER_ID,
        session_dir=str(session_dir),
        capabilities_dir=str(caps_dir),
    )
    assert r1["capability_prompt"] == "initial content"

    cap_file.write_text("mutated content")

    r2 = compute_turn_state(
        "set up a new cycle",
        USER_ID,
        session_dir=str(session_dir),
        capabilities_dir=str(caps_dir),
    )
    assert r2["capability_prompt"] == "mutated content"


def test_capability_prompt_empty_for_default_intent(tmp_path: Path) -> None:
    """Default intent has no capability file; capability_prompt is empty string."""
    caps_dir = tmp_path / "caps"
    caps_dir.mkdir()
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()

    result = compute_turn_state(
        "what's up",
        USER_ID,
        session_dir=str(session_dir),
        capabilities_dir=str(caps_dir),
    )
    assert result["capability_prompt"] == ""


def test_today_date_is_iso_date_string(tmp_path: Path) -> None:
    """compute_turn_state result includes today_date as YYYY-MM-DD."""
    import re
    caps_dir = tmp_path / "caps"
    caps_dir.mkdir()
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()

    result = compute_turn_state(
        "what's up",
        USER_ID,
        session_dir=str(session_dir),
        capabilities_dir=str(caps_dir),
    )
    assert "today_date" in result
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", result["today_date"]), (
        f"today_date must be YYYY-MM-DD; got {result['today_date']!r}"
    )


def test_today_view_capability_file_loaded(tmp_path: Path) -> None:
    """today_view intent maps to today_view.md and loads its content."""
    caps_dir = tmp_path / "caps"
    caps_dir.mkdir()
    (caps_dir / "today_view.md").write_text("today view prompt")
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()

    result = compute_turn_state(
        "what have i eaten today",
        USER_ID,
        session_dir=str(session_dir),
        capabilities_dir=str(caps_dir),
    )
    assert result["intent"] == "today_view"
    assert result["capability_prompt"] == "today view prompt"


# ── intent state persistence ──────────────────────────────────────────────────

def test_prior_intent_is_none_on_first_turn(tmp_path: Path) -> None:
    assert _read_prior_intent(USER_ID, str(tmp_path)) is None


def test_write_then_read_intent_state(tmp_path: Path) -> None:
    _write_intent_state(USER_ID, "mesocycle_setup", str(tmp_path))
    assert _read_prior_intent(USER_ID, str(tmp_path)) == "mesocycle_setup"


# ── boundary detection ────────────────────────────────────────────────────────

def test_boundary_true_on_intent_transition(tmp_path: Path) -> None:
    """boundary=True when confident intent differs from prior non-None intent."""
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    caps_dir = tmp_path / "caps"
    caps_dir.mkdir()
    _make_caps(caps_dir)

    _write_intent_state(USER_ID, "mesocycle_setup", str(session_dir))

    result = compute_turn_state(
        "what's my cycle",
        USER_ID,
        session_dir=str(session_dir),
        capabilities_dir=str(caps_dir),
    )
    assert result["boundary"] is True
    assert result["intent"] == "cycle_read_back"


def test_boundary_false_on_same_intent(tmp_path: Path) -> None:
    """boundary=False when current intent matches prior."""
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    caps_dir = tmp_path / "caps"
    caps_dir.mkdir()
    _make_caps(caps_dir)

    _write_intent_state(USER_ID, "mesocycle_setup", str(session_dir))

    result = compute_turn_state(
        "set up a new cycle",
        USER_ID,
        session_dir=str(session_dir),
        capabilities_dir=str(caps_dir),
    )
    assert result["boundary"] is False


def test_boundary_false_on_ambiguous_intent(tmp_path: Path) -> None:
    """boundary=False when classification is ambiguous, regardless of prior."""
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()

    _write_intent_state(USER_ID, "mesocycle_setup", str(session_dir))

    result = compute_turn_state(
        "sounds good",
        USER_ID,
        session_dir=str(session_dir),
        capabilities_dir=str(tmp_path / "caps"),
    )
    assert result["boundary"] is False
    assert result["ambiguous"] is True


def test_boundary_false_on_first_turn_no_prior(tmp_path: Path) -> None:
    """boundary=False when there is no prior intent (first turn)."""
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    caps_dir = tmp_path / "caps"
    caps_dir.mkdir()
    _make_caps(caps_dir)

    result = compute_turn_state(
        "set up a new cycle",
        USER_ID,
        session_dir=str(session_dir),
        capabilities_dir=str(caps_dir),
    )
    assert result["boundary"] is False


# ── session file rename ───────────────────────────────────────────────────────

def test_session_rename_on_boundary(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """NB-33: on boundary=True, rename is suppressed; boundary is still detected and logged."""
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    caps_dir = tmp_path / "caps"
    caps_dir.mkdir()
    _make_caps(caps_dir)

    session_file = session_dir / "aaaa-bbbb.jsonl"
    session_file.write_text('{"turn": 1}\n')
    _make_sessions_json(str(session_dir), USER_ID, str(session_file))
    _write_intent_state(USER_ID, "mesocycle_setup", str(session_dir))

    result = compute_turn_state(
        "what's my cycle",
        USER_ID,
        session_dir=str(session_dir),
        capabilities_dir=str(caps_dir),
    )

    assert result["boundary"] is True
    assert session_file.exists(), "NB-33: rename suppressed; original file must remain"
    resets = list(session_dir.glob("aaaa-bbbb.jsonl.reset.*"))
    assert len(resets) == 0, f"NB-33: no reset files expected, found: {[f.name for f in resets]}"
    captured = capsys.readouterr()
    assert f"[NB-33] boundary detected user_id={USER_ID}; rename suppressed" in captured.err


def test_idempotent_rename_when_session_file_absent(tmp_path: Path) -> None:
    """_reset_session_file does not raise when the session file is already absent."""
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    _make_sessions_json(
        str(session_dir), USER_ID, str(session_dir / "no-such-file.jsonl")
    )
    _reset_session_file(USER_ID, str(session_dir))


def test_no_rename_when_boundary_false(tmp_path: Path) -> None:
    """Session file is not renamed when boundary=False."""
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    caps_dir = tmp_path / "caps"
    caps_dir.mkdir()
    _make_caps(caps_dir)

    session_file = session_dir / "aaaa-bbbb.jsonl"
    session_file.write_text('{"turn": 1}\n')
    _make_sessions_json(str(session_dir), USER_ID, str(session_file))
    _write_intent_state(USER_ID, "mesocycle_setup", str(session_dir))

    compute_turn_state(
        "set up a new cycle",
        USER_ID,
        session_dir=str(session_dir),
        capabilities_dir=str(caps_dir),
    )
    assert session_file.exists()


# ── prior intent preservation on ambiguous turns ─────────────────────────────

def test_prior_intent_preserved_on_ambiguous_turn(tmp_path: Path) -> None:
    """Ambiguous turn does not overwrite prior intent; continuation preserved."""
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    caps_dir = tmp_path / "caps"
    caps_dir.mkdir()
    _make_caps(caps_dir)

    _write_intent_state(USER_ID, "mesocycle_setup", str(session_dir))

    compute_turn_state(
        "sounds good",
        USER_ID,
        session_dir=str(session_dir),
        capabilities_dir=str(caps_dir),
    )

    assert _read_prior_intent(USER_ID, str(session_dir)) == "mesocycle_setup"


# ── session file lookup ───────────────────────────────────────────────────────

def test_find_session_file_returns_none_when_sessions_json_absent(tmp_path: Path) -> None:
    assert _find_session_file(USER_ID, str(tmp_path)) is None


def test_find_session_file_returns_none_for_wrong_user(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    _make_sessions_json(str(session_dir), 9999999, str(session_dir / "abc.jsonl"))
    assert _find_session_file(USER_ID, str(session_dir)) is None


# ── session-rename contract test ──────────────────────────────────────────────

def test_session_rename_contract(tmp_path: Path) -> None:
    """Python rename behavior: after _reset_session_file the original path is gone.

    Tests three properties of the atomic rename:
    1. sessions.json still references the original (now-renamed) path.
    2. The original JSONL path no longer exists.
    3. The renamed file exists and contains the original history (preserved for debugging).

    OpenClaw assumption (not enforced here): OpenClaw discovers sessions by reading
    sessions.json and opening sessionFile. When sessionFile is absent, OpenClaw
    initializes an empty session. If that assumption changes (e.g., OpenClaw falls
    back to glob-scanning the directory), the rename stopgap breaks silently. A
    separate integration test against a real OpenClaw process would be needed to
    enforce that assumption; this test only verifies the Python rename side.
    """
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()

    session_file = session_dir / "contract-test.jsonl"
    prior_history = '{"role": "assistant", "content": "prior turn"}\n'
    session_file.write_text(prior_history)
    _make_sessions_json(str(session_dir), USER_ID, str(session_file))

    _reset_session_file(USER_ID, str(session_dir))

    # Contract 1: sessions.json still references the original path
    sessions = json.loads((session_dir / "sessions.json").read_text())
    entry = sessions["agent:nutriosv2:main"]
    original_path = entry["sessionFile"]
    assert original_path == str(session_file), (
        "sessions.json sessionFile key must point to the original path"
    )

    # Contract 2: original path no longer exists (OpenClaw gets fresh session)
    assert not Path(original_path).exists(), (
        "Session file must not exist at original path after rename; "
        "OpenClaw would rehydrate stale history from it if it existed"
    )

    # Contract 3: renamed file exists and contains original history
    resets = list(session_dir.glob("contract-test.jsonl.reset.*"))
    assert len(resets) == 1, f"Expected exactly one reset file, found: {[f.name for f in resets]}"
    assert prior_history in resets[0].read_text(), (
        "Renamed file must retain original history for debugging"
    )


def test_find_session_file_returns_none_when_session_file_key_absent(tmp_path: Path) -> None:
    """Entry matches peer but has no sessionFile key; _find_session_file returns None."""
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    entry = {
        "origin": {
            "accountId": "nutriosv2",
            "from": f"telegram:{USER_ID}",
        }
        # sessionFile key intentionally absent
    }
    path = session_dir / "sessions.json"
    path.write_text(json.dumps({"agent:nutriosv2:main": entry}))
    assert _find_session_file(USER_ID, str(session_dir)) is None


# ── intent_override ───────────────────────────────────────────────────────────

def test_intent_override_skips_classifier(tmp_path: Path) -> None:
    """intent_override bypasses classify_intent; capability_prompt from override intent returned."""
    caps_dir = tmp_path / "caps"
    caps_dir.mkdir()
    (caps_dir / "mesocycle_setup.md").write_text("mesocycle setup prompt")
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()

    with patch.object(ts_mod, "classify_intent") as mock_classifier:
        result = compute_turn_state(
            "/newcycle",
            USER_ID,
            intent_override="mesocycle_setup",
            session_dir=str(session_dir),
            capabilities_dir=str(caps_dir),
        )

    mock_classifier.assert_not_called()
    assert result["intent"] == "mesocycle_setup"
    assert result["ambiguous"] is False
    assert result["capability_prompt"] == "mesocycle setup prompt"


def test_intent_override_today_view_loads_capability_prompt(tmp_path: Path) -> None:
    """intent_override='today_view' returns today_view.md content."""
    caps_dir = tmp_path / "caps"
    caps_dir.mkdir()
    (caps_dir / "today_view.md").write_text("today view prompt")
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()

    result = compute_turn_state(
        "/today",
        USER_ID,
        intent_override="today_view",
        session_dir=str(session_dir),
        capabilities_dir=str(caps_dir),
    )
    assert result["intent"] == "today_view"
    assert result["capability_prompt"] == "today view prompt"


def test_intent_override_invalid_returns_clean_error(capsys: pytest.CaptureFixture) -> None:
    """Invalid intent_override emits err() JSON and exits 1; no traceback."""
    payload = json.dumps({
        "user_message": "/unknown",
        "user_id": USER_ID,
        "intent_override": "nonexistent_intent",
    })

    with patch("sys.stdin", io.StringIO(payload)):
        with pytest.raises(SystemExit) as exc_info:
            ts_mod.main()

    assert exc_info.value.code == 1
    captured = json.loads(capsys.readouterr().out)
    assert captured["ok"] is False
    assert "nonexistent_intent" in captured["error"]


def test_no_intent_override_runs_classifier(tmp_path: Path) -> None:
    """Without intent_override, classifier routes 'I had oatmeal' to meal_log (regression)."""
    caps_dir = tmp_path / "caps"
    caps_dir.mkdir()
    (caps_dir / "meal_log.md").write_text("meal log prompt")
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()

    result = compute_turn_state(
        "I had oatmeal",
        USER_ID,
        session_dir=str(session_dir),
        capabilities_dir=str(caps_dir),
    )
    assert result["intent"] == "meal_log"
    assert result["capability_prompt"] == "meal log prompt"


# ── main() error boundary ─────────────────────────────────────────────────────

def test_main_catches_compute_turn_state_exception(capsys: pytest.CaptureFixture) -> None:
    """main() wraps compute_turn_state; exceptions emit err() JSON, not a traceback."""
    payload = json.dumps({"user_message": "hello", "user_id": USER_ID})

    with patch.object(ts_mod, "compute_turn_state", side_effect=Exception("corrupt state")):
        with patch("sys.stdin", io.StringIO(payload)):
            with pytest.raises(SystemExit) as exc_info:
                ts_mod.main()

    assert exc_info.value.code == 1
    captured = json.loads(capsys.readouterr().out)
    assert captured["ok"] is False
    assert str(USER_ID) in captured["error"]
    assert "corrupt state" in captured["error"]
