"""Step 1 §4.7: INBOUND .json apply against the hand-written mock.

The mock at ``tests/fixtures/mock_strategy_output.json`` is the
operator's known-good handoff for Step 1; this test wires it through
the full ``apply_strategy_output`` pipeline (validate, cycle_id gate,
two-phase atomic write) and asserts the state files land cleanly.

Companion to test_step1_e2e_bot.py in skills/grailzee-eval/tests/
which exercises the end-to-end loop (mock → unpack → evaluate_deal).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _fixtures import build_fake_grailzee_tree

from grailzee_bundle.unpack_bundle import apply_strategy_output


MOCK_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "mock_strategy_output.json"
)
MOCK_CYCLE_ID = "cycle_2026-15"


def _load_mock() -> dict:
    return json.loads(MOCK_FIXTURE_PATH.read_text(encoding="utf-8"))


def test_mock_fixture_exists():
    assert MOCK_FIXTURE_PATH.exists(), (
        f"Mock fixture missing at {MOCK_FIXTURE_PATH}"
    )


def test_mock_fixture_shape():
    """Sanity-check the fixture before pushing it through the pipeline."""
    payload = _load_mock()
    assert payload["cycle_id"] == MOCK_CYCLE_ID
    cf = payload["decisions"]["cycle_focus"]
    assert len(cf["targets"]) == 12
    assert cf["capital_target"] == 60000
    assert cf["target_margin_fraction"] == 0.05
    brands = {t["brand"] for t in cf["targets"]}
    assert brands == {"Tudor", "Breitling", "Cartier", "Omega"}
    mg = payload["decisions"]["monthly_goals"]
    assert mg["monthly_return_pct"] == 0.12


def test_apply_writes_state_files_atomically(tmp_path: Path):
    """End-to-end .json apply: validates, gates on cycle_id, writes
    cycle_focus and monthly_goals to state/ atomically. Quarterly +
    config_updates are null so they do NOT produce writes."""
    paths = build_fake_grailzee_tree(tmp_path, cycle_id=MOCK_CYCLE_ID)

    summary = apply_strategy_output(
        MOCK_FIXTURE_PATH, tmp_path, write_archive=False,
    )
    assert summary["cycle_id"] == MOCK_CYCLE_ID
    assert summary["session_mode"] == "cycle_planning"
    assert sorted(summary["roles_written"]) == ["cycle_focus", "monthly_goals"]

    state_dir = paths["state"]
    cycle_focus = json.loads((state_dir / "cycle_focus.json").read_text())
    monthly_goals = json.loads((state_dir / "monthly_goals.json").read_text())

    assert len(cycle_focus["targets"]) == 12
    assert cycle_focus["capital_target"] == 60000
    assert cycle_focus["target_margin_fraction"] == 0.05
    assert "Tudor" in cycle_focus["brand_emphasis"]
    assert monthly_goals["monthly_return_pct"] == 0.12


def test_apply_blocks_cycle_id_mismatch(tmp_path: Path):
    """Mock cycle_id is cycle_2026-15; if the cache cycle_id differs,
    apply must reject before writing any state file."""
    build_fake_grailzee_tree(tmp_path, cycle_id="cycle_2026-08")

    from grailzee_bundle.unpack_bundle import BundleValidationError
    with pytest.raises(BundleValidationError, match="cycle_id"):
        apply_strategy_output(
            MOCK_FIXTURE_PATH, tmp_path, write_archive=False,
        )

    # No state writes leaked through the cycle_id gate.
    state_dir = tmp_path / "state"
    cycle_focus_after = json.loads((state_dir / "cycle_focus.json").read_text())
    # build_fake_grailzee_tree wrote a default cycle_focus; mock's targets
    # would have 12 entries, default fixture has none in `targets` form.
    assert "targets" not in cycle_focus_after or cycle_focus_after.get("targets") != [
        t for t in _load_mock()["decisions"]["cycle_focus"]["targets"]
    ]
