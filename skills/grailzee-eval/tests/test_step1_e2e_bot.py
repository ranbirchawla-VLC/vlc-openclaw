"""Step 1 §4.7: end-to-end bot loop against the mock strategy_output.

Wire: mock strategy_output.json → unpack_bundle.apply_strategy_output
→ state/cycle_focus.json → evaluate() reads state → returns yes/no.

This is the closure test for Step 1: the bot capability invocation
returns a verdict + math against state files written from a mock
strategy session, with no Telegram round-trip required. The release
check (operator-driven, Telegram) is the third leg of the §5 gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.grailzee_common import (
    CACHE_SCHEMA_VERSION,
    _reset_analyzer_config_cache,
)
from scripts.evaluate_deal import evaluate

# Cowork unpack_bundle is in a sibling top-level package; pytest config
# adds the repo root to sys.path via testpaths/rootdir, so the import
# resolves at test-collection time without monkey patching.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "grailzee-cowork"))
from grailzee_bundle.unpack_bundle import apply_strategy_output  # noqa: E402


MOCK_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "grailzee-cowork" / "tests" / "fixtures" / "mock_strategy_output.json"
)
MOCK_CYCLE_ID = "cycle_2026-15"


def _build_v3_cache_with_target() -> dict:
    """Minimal v3 cache containing one of the mock's 12 targets.

    Tudor 79830RB is on the mock plan. Single bucket so the matcher
    resolves cleanly: Black / Arabic / NR. Median 3200 → premium-adjusted
    max_buy 3210 (matches test_evaluate_deal hand-computed math).
    """
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "generated_at": "2026-04-25T10:30:00",
        "source_report": "grailzee_2026-04-25.csv",
        "cycle_id": MOCK_CYCLE_ID,
        "premium_status": {
            "avg_premium": 0,
            "trade_count": 0,
            "threshold_met": False,
            "adjustment": 0,
            "trades_to_threshold": 10,
        },
        "references": {
            "79830RB": {
                "brand": "Tudor",
                "model": "BB GMT Pepsi",
                "reference": "79830RB",
                "named": True,
                "trend_signal": None,
                "trend_median_change": None,
                "trend_median_pct": None,
                "momentum": None,
                "confidence": None,
                "buckets": {
                    "arabic|nr|black": {
                        "dial_numerals": "Arabic",
                        "auction_type": "nr",
                        "dial_color": "Black",
                        "named_special": "pepsi",
                        "signal": "Strong",
                        "median": 3200,
                        "max_buy_nr": 2910,
                        "max_buy_res": 2860,
                        "risk_nr": 8.5,
                        "volume": 12,
                        "st_pct": 0.78,
                        "condition_mix": '{"very good":0.5,"like new":0.5}',
                        "capital_required_nr": None,
                        "capital_required_res": None,
                        "expected_net_at_median_nr": None,
                        "expected_net_at_median_res": None,
                    }
                },
            },
        },
        "dj_configs": {},
    }


@pytest.fixture(autouse=True)
def _reset_config():
    _reset_analyzer_config_cache()
    yield
    _reset_analyzer_config_cache()


@pytest.fixture
def grailzee_root_with_mock_state(tmp_path: Path) -> Path:
    """Build a fake GrailzeeData root, install a v3 cache with cycle_id
    matching the mock, then apply the mock strategy_output to populate
    state/cycle_focus.json + state/monthly_goals.json atomically."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "analysis_cache.json").write_text(
        json.dumps(_build_v3_cache_with_target(), indent=2)
    )
    apply_strategy_output(MOCK_FIXTURE_PATH, tmp_path, write_archive=False)
    assert (state_dir / "cycle_focus.json").exists()
    assert (state_dir / "monthly_goals.json").exists()
    return tmp_path


def test_e2e_yes_on_plan(grailzee_root_with_mock_state: Path):
    """Mock plan includes 79830RB; cache has matching bucket; price
    well below max_buy → yes + on_plan True."""
    cache_path = str(grailzee_root_with_mock_state / "state" / "analysis_cache.json")
    focus_path = str(grailzee_root_with_mock_state / "state" / "cycle_focus.json")

    result = evaluate(
        "Tudor", "79830RB", 2000,
        cache_path=cache_path,
        cycle_focus_path=focus_path,
    )
    assert result["decision"] == "yes"
    assert result["match_resolution"] == "single_bucket"
    assert result["math"]["max_buy"] == 3210
    assert result["math"]["listing_price"] == 2000
    assert result["cycle_context"]["on_plan"] is True
    assert result["cycle_context"]["target_match"]["brand"] == "Tudor"
    assert result["cycle_context"]["target_match"]["reference"] == "79830RB"


def test_e2e_no_on_plan_math_fails(grailzee_root_with_mock_state: Path):
    """Same target, but price above premium-adjusted max_buy → no.
    on_plan stays True (cycle is metadata, math gates)."""
    cache_path = str(grailzee_root_with_mock_state / "state" / "analysis_cache.json")
    focus_path = str(grailzee_root_with_mock_state / "state" / "cycle_focus.json")

    result = evaluate(
        "Tudor", "79830RB", 3500,
        cache_path=cache_path,
        cycle_focus_path=focus_path,
    )
    assert result["decision"] == "no"
    assert result["match_resolution"] == "single_bucket"
    assert result["cycle_context"]["on_plan"] is True


def test_e2e_off_plan_reference_not_found(grailzee_root_with_mock_state: Path):
    """A reference that's neither in the cache nor on the mock plan."""
    cache_path = str(grailzee_root_with_mock_state / "state" / "analysis_cache.json")
    focus_path = str(grailzee_root_with_mock_state / "state" / "cycle_focus.json")

    result = evaluate(
        "Patek Philippe", "5711/1A-010", 100000,
        cache_path=cache_path,
        cycle_focus_path=focus_path,
    )
    assert result["decision"] == "no"
    assert result["match_resolution"] == "reference_not_found"
    assert result["cycle_context"]["on_plan"] is False
