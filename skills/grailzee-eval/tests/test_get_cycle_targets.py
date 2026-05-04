"""Tests for get_cycle_targets.py."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SKILL_DIR.parent))
sys.path.insert(0, str(_SCRIPTS_DIR))

from get_cycle_targets import get_cycle_targets


_FULL_FOCUS = {
    "targets": [
        {
            "reference": "79830RB",
            "brand": "Tudor",
            "model": "Black Bay GMT Pepsi",
            "cycle_reason": "Lean-hard anchor.",
            "max_buy_override": None,
        },
        {
            "reference": "WSSA0030",
            "brand": "Cartier",
            "model": "Santos de Cartier 40mm",
            "cycle_reason": "Strategic Cartier entry.",
            "max_buy_override": 5000,
        },
    ],
    "capital_target": 30000,
    "volume_target": 6,
    "target_margin_fraction": 0.05,
    "brand_emphasis": ["Tudor", "Cartier"],
    "brand_pullback": [],
    "notes": "Capital target $30,000.",
}


# ─── Missing file ─────────────────────────────────────────────────────


class TestMissingFile:
    def test_returns_ok_false(self, tmp_path: Path):
        result = get_cycle_targets(str(tmp_path / "cycle_focus.json"))
        assert result["ok"] is False

    def test_error_mentions_report(self, tmp_path: Path):
        result = get_cycle_targets(str(tmp_path / "cycle_focus.json"))
        assert "report" in result["error"].lower()


# ─── Targets present ──────────────────────────────────────────────────


class TestTargetsPresent:
    @pytest.fixture()
    def focus_path(self, tmp_path: Path) -> str:
        p = tmp_path / "cycle_focus.json"
        p.write_text(json.dumps(_FULL_FOCUS))
        return str(p)

    def test_ok_true(self, focus_path: str):
        assert get_cycle_targets(focus_path)["ok"] is True

    def test_targets_count(self, focus_path: str):
        data = get_cycle_targets(focus_path)["data"]
        assert len(data["targets"]) == 2

    def test_target_fields_preserved(self, focus_path: str):
        targets = get_cycle_targets(focus_path)["data"]["targets"]
        assert targets[0]["reference"] == "79830RB"
        assert targets[0]["brand"] == "Tudor"
        assert targets[0]["model"] == "Black Bay GMT Pepsi"
        assert targets[0]["cycle_reason"] == "Lean-hard anchor."
        assert targets[0]["max_buy_override"] is None

    def test_max_buy_override_preserved(self, focus_path: str):
        targets = get_cycle_targets(focus_path)["data"]["targets"]
        assert targets[1]["max_buy_override"] == 5000

    def test_capital_target(self, focus_path: str):
        assert get_cycle_targets(focus_path)["data"]["capital_target"] == 30000

    def test_volume_target(self, focus_path: str):
        assert get_cycle_targets(focus_path)["data"]["volume_target"] == 6

    def test_brand_emphasis(self, focus_path: str):
        assert get_cycle_targets(focus_path)["data"]["brand_emphasis"] == ["Tudor", "Cartier"]

    def test_brand_pullback_empty(self, focus_path: str):
        assert get_cycle_targets(focus_path)["data"]["brand_pullback"] == []

    def test_notes_preserved(self, focus_path: str):
        assert get_cycle_targets(focus_path)["data"]["notes"] == "Capital target $30,000."


# ─── Empty targets array ──────────────────────────────────────────────


class TestEmptyTargets:
    @pytest.fixture()
    def empty_focus_path(self, tmp_path: Path) -> str:
        p = tmp_path / "cycle_focus.json"
        p.write_text(json.dumps({**_FULL_FOCUS, "targets": []}))
        return str(p)

    def test_ok_true_on_empty_targets(self, empty_focus_path: str):
        assert get_cycle_targets(empty_focus_path)["ok"] is True

    def test_targets_empty_list(self, empty_focus_path: str):
        assert get_cycle_targets(empty_focus_path)["data"]["targets"] == []


# ─── Brand pullback populated ─────────────────────────────────────────


class TestBrandPullback:
    def test_pullback_returned(self, tmp_path: Path):
        focus = {**_FULL_FOCUS, "brand_pullback": ["Omega"]}
        p = tmp_path / "cycle_focus.json"
        p.write_text(json.dumps(focus))
        assert get_cycle_targets(str(p))["data"]["brand_pullback"] == ["Omega"]


# ─── Subprocess (standalone) ─────────────────────────────────────────


class TestSubprocess:
    def test_exit_zero_with_valid_focus(self, tmp_path: Path):
        state = tmp_path / "state"
        state.mkdir()
        p = state / "cycle_focus.json"
        p.write_text(json.dumps(_FULL_FOCUS))
        script = str(_SCRIPTS_DIR / "get_cycle_targets.py")
        env = {"GRAILZEE_ROOT": str(tmp_path), "PATH": "/usr/bin:/bin"}
        import os
        env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
        proc = subprocess.run(
            [sys.executable, script, "{}"],
            capture_output=True, text=True,
            env={**os.environ, "GRAILZEE_ROOT": str(tmp_path)},
        )
        assert proc.returncode == 0
        out = json.loads(proc.stdout)
        assert out["ok"] is True
        assert len(out["data"]["targets"]) == 2

    def test_exit_one_on_missing_file(self, tmp_path: Path):
        script = str(_SCRIPTS_DIR / "get_cycle_targets.py")
        import os
        proc = subprocess.run(
            [sys.executable, script, "{}"],
            capture_output=True, text=True,
            env={**os.environ, "GRAILZEE_ROOT": str(tmp_path)},
        )
        assert proc.returncode == 1
        out = json.loads(proc.stdout)
        assert out["ok"] is False
