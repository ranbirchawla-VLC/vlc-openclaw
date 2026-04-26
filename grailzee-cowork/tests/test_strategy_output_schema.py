"""Tests for the strategy_output_v1 hand-rolled validator.

Coverage matrix:
- Happy paths: minimal payload (single decision), max payload (all four)
- Top-level: required-field-missing x 7; unknown-key rejected; version != 1;
  session_mode enum mis-value; cycle_id malformed; generated_at malformed;
  produced_by prefix missing
- decisions: empty-all-null rejected; one-section-populated accepted
- cycle_focus: shape errors including target_margin_fraction out of range
  (percentage-vs-fraction mistake), empty targets, missing required sub-keys
- monthly_goals: empty platform_mix accepted (partial update); bad pct; bad month
- quarterly_allocation: bad quarter; bad bucket value
- config_updates: change_notes missing; all-subs-null rejected; envelope missing
- session_artifacts: cycle_brief_md empty
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from grailzee_bundle.strategy_schema import (
    StrategyOutputValidationError,
    validate_strategy_output,
)


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "strategy_output_v1.json"


def _valid_cycle_focus() -> dict:
    return {
        "targets": [
            {
                "reference": "79830RB",
                "brand": "Tudor",
                "model": "BB GMT Pepsi",
                "cycle_reason": "Core performer with momentum signal",
                "max_buy_override": None,
            }
        ],
        "capital_target": 15000,
        "volume_target": 5,
        "target_margin_fraction": 0.05,
        "brand_emphasis": ["Tudor"],
        "brand_pullback": [],
        "notes": "Leaning into Tudor sourcing this cycle.",
    }


def _valid_monthly_goals() -> dict:
    return {
        "month": "2026-04",
        "revenue_target": 40000,
        "volume_target": 12,
        "platform_mix": {"Grailzee": 60, "eBay": 30, "Chrono24": 10},
        "focus_notes": "Premium performers on Grailzee; test Chrono24 lane.",
        "review_notes": "March hit volume, missed revenue by 8%.",
    }


def _valid_quarterly_allocation() -> dict:
    return {
        "quarter": "2026-Q2",
        "capital_allocation": {"Tudor": 25000, "Rolex": 40000, "Cartier": 10000},
        "inventory_mix_target": {"Strong": 70, "Normal": 30},
        "review_notes": "Q1 was capital-heavy in Rolex; rebalancing into Tudor.",
    }


def _valid_config_updates() -> dict:
    return {
        "signal_thresholds": {
            "version": 2,
            "updated_at": "2026-04-19T12:00:00Z",
            "updated_by": "strategy_session",
            "notes": "Raising Strong cutoff based on Q1 retrospective.",
            "strong_score_floor": 7.5,
        },
        "scoring_thresholds": None,
        "momentum_thresholds": None,
        "window_config": None,
        "premium_config": None,
        "margin_config": None,
        "change_notes": "Only signal_thresholds changed this session.",
    }


def _valid_minimal_payload() -> dict:
    """Minimum viable strategy_output: cycle_focus only."""
    return {
        "strategy_output_version": 1,
        "generated_at": "2026-04-19T10:30:00Z",
        "cycle_id": "cycle_2026-04",
        "session_mode": "cycle_planning",
        "produced_by": "grailzee-strategy/0.1.0",
        "decisions": {
            "cycle_focus": _valid_cycle_focus(),
            "monthly_goals": None,
            "quarterly_allocation": None,
            "config_updates": None,
        },
        "session_artifacts": {
            "cycle_brief_md": "# Cycle Brief\n\nFocus: Tudor.",
        },
    }


def _valid_max_payload() -> dict:
    payload = _valid_minimal_payload()
    payload["decisions"]["monthly_goals"] = _valid_monthly_goals()
    payload["decisions"]["quarterly_allocation"] = _valid_quarterly_allocation()
    payload["decisions"]["config_updates"] = _valid_config_updates()
    return payload


# ─── happy paths ──────────────────────────────────────────────────────

def test_minimal_payload_is_valid() -> None:
    validate_strategy_output(_valid_minimal_payload())


def test_max_payload_is_valid() -> None:
    validate_strategy_output(_valid_max_payload())


def test_cycle_focus_with_max_buy_override_accepted() -> None:
    p = _valid_minimal_payload()
    p["decisions"]["cycle_focus"]["targets"][0]["max_buy_override"] = 2400.0
    validate_strategy_output(p)


def test_generated_at_with_microseconds_accepted() -> None:
    p = _valid_minimal_payload()
    p["generated_at"] = "2026-04-19T10:30:00.123456Z"
    validate_strategy_output(p)


def test_monthly_goals_empty_platform_mix_accepted() -> None:
    """Empty platform_mix is permitted (partial-update convention)."""
    p = _valid_minimal_payload()
    p["decisions"]["monthly_goals"] = _valid_monthly_goals()
    p["decisions"]["monthly_goals"]["platform_mix"] = {}
    validate_strategy_output(p)


def test_all_four_session_modes_accepted() -> None:
    for mode in ("cycle_planning", "monthly_review", "quarterly_allocation", "config_tuning"):
        p = _valid_minimal_payload()
        p["session_mode"] = mode
        validate_strategy_output(p)


# ─── top-level errors ────────────────────────────────────────────────

def test_top_level_required_keys_all_rejected_when_missing() -> None:
    required = [
        "strategy_output_version",
        "generated_at",
        "cycle_id",
        "session_mode",
        "produced_by",
        "decisions",
        "session_artifacts",
    ]
    for key in required:
        p = _valid_minimal_payload()
        del p[key]
        with pytest.raises(StrategyOutputValidationError, match=key):
            validate_strategy_output(p)


def test_unknown_top_level_key_rejected() -> None:
    p = _valid_minimal_payload()
    p["extra_field"] = "unexpected"
    with pytest.raises(StrategyOutputValidationError, match="unknown keys"):
        validate_strategy_output(p)


def test_version_must_be_1() -> None:
    p = _valid_minimal_payload()
    p["strategy_output_version"] = 2
    with pytest.raises(StrategyOutputValidationError, match="strategy_output_version"):
        validate_strategy_output(p)


def test_session_mode_enum_rejected() -> None:
    p = _valid_minimal_payload()
    p["session_mode"] = "strategic_planning"  # not in enum
    with pytest.raises(StrategyOutputValidationError, match="session_mode"):
        validate_strategy_output(p)


def test_cycle_id_pattern_rejected() -> None:
    p = _valid_minimal_payload()
    p["cycle_id"] = "2026-15"  # missing cycle_ prefix
    with pytest.raises(StrategyOutputValidationError, match="cycle_id"):
        validate_strategy_output(p)


def test_generated_at_pattern_rejected() -> None:
    p = _valid_minimal_payload()
    p["generated_at"] = "2026-04-19 10:30:00"  # missing T, Z
    with pytest.raises(StrategyOutputValidationError, match="generated_at"):
        validate_strategy_output(p)


def test_produced_by_prefix_required() -> None:
    p = _valid_minimal_payload()
    p["produced_by"] = "some-other-tool/1.0"
    with pytest.raises(StrategyOutputValidationError, match="produced_by"):
        validate_strategy_output(p)


# ─── decisions section ───────────────────────────────────────────────

def test_empty_decisions_rejected() -> None:
    p = _valid_minimal_payload()
    p["decisions"] = {
        "cycle_focus": None,
        "monthly_goals": None,
        "quarterly_allocation": None,
        "config_updates": None,
    }
    with pytest.raises(StrategyOutputValidationError, match="at least one"):
        validate_strategy_output(p)


def test_decisions_missing_required_subkey_rejected() -> None:
    """Every decision sub-field must be present (possibly null), not absent."""
    p = _valid_minimal_payload()
    del p["decisions"]["monthly_goals"]
    with pytest.raises(StrategyOutputValidationError, match="monthly_goals"):
        validate_strategy_output(p)


# ─── cycle_focus ─────────────────────────────────────────────────────

def test_cycle_focus_empty_targets_rejected() -> None:
    p = _valid_minimal_payload()
    p["decisions"]["cycle_focus"]["targets"] = []
    with pytest.raises(StrategyOutputValidationError, match="targets"):
        validate_strategy_output(p)


def test_target_margin_fraction_out_of_range_rejected() -> None:
    """Percentage-as-fraction mistake: passing 5 instead of 0.05."""
    p = _valid_minimal_payload()
    p["decisions"]["cycle_focus"]["target_margin_fraction"] = 5
    with pytest.raises(StrategyOutputValidationError, match="fraction"):
        validate_strategy_output(p)


def test_target_margin_fraction_zero_rejected() -> None:
    p = _valid_minimal_payload()
    p["decisions"]["cycle_focus"]["target_margin_fraction"] = 0
    with pytest.raises(StrategyOutputValidationError, match="target_margin_fraction"):
        validate_strategy_output(p)


def test_target_margin_fraction_one_rejected() -> None:
    """Upper bound is exclusive: a 100% fraction is a data-entry error
    (probably someone passed a percent the wrong way)."""
    p = _valid_minimal_payload()
    p["decisions"]["cycle_focus"]["target_margin_fraction"] = 1.0
    with pytest.raises(StrategyOutputValidationError, match="target_margin_fraction"):
        validate_strategy_output(p)


def test_cycle_focus_negative_capital_target_rejected() -> None:
    p = _valid_minimal_payload()
    p["decisions"]["cycle_focus"]["capital_target"] = -100
    with pytest.raises(StrategyOutputValidationError, match="capital_target"):
        validate_strategy_output(p)


def test_cycle_focus_target_missing_reference_rejected() -> None:
    p = _valid_minimal_payload()
    del p["decisions"]["cycle_focus"]["targets"][0]["reference"]
    with pytest.raises(StrategyOutputValidationError, match="reference"):
        validate_strategy_output(p)


def test_cycle_focus_unknown_target_key_rejected() -> None:
    p = _valid_minimal_payload()
    p["decisions"]["cycle_focus"]["targets"][0]["extra"] = "nope"
    with pytest.raises(StrategyOutputValidationError, match="unknown"):
        validate_strategy_output(p)


# ─── monthly_goals ───────────────────────────────────────────────────

def test_monthly_goals_bad_month_pattern_rejected() -> None:
    p = _valid_minimal_payload()
    p["decisions"]["monthly_goals"] = _valid_monthly_goals()
    p["decisions"]["monthly_goals"]["month"] = "2026-4"  # single digit
    with pytest.raises(StrategyOutputValidationError, match="month"):
        validate_strategy_output(p)


def test_monthly_goals_platform_pct_out_of_range_rejected() -> None:
    p = _valid_minimal_payload()
    p["decisions"]["monthly_goals"] = _valid_monthly_goals()
    p["decisions"]["monthly_goals"]["platform_mix"]["Grailzee"] = 120
    with pytest.raises(StrategyOutputValidationError, match="platform_mix"):
        validate_strategy_output(p)


# ─── quarterly_allocation ────────────────────────────────────────────

def test_quarterly_bad_quarter_pattern_rejected() -> None:
    p = _valid_minimal_payload()
    p["decisions"]["quarterly_allocation"] = _valid_quarterly_allocation()
    p["decisions"]["quarterly_allocation"]["quarter"] = "2026-Q5"
    with pytest.raises(StrategyOutputValidationError, match="quarter"):
        validate_strategy_output(p)


def test_quarterly_negative_capital_allocation_rejected() -> None:
    p = _valid_minimal_payload()
    p["decisions"]["quarterly_allocation"] = _valid_quarterly_allocation()
    p["decisions"]["quarterly_allocation"]["capital_allocation"]["Tudor"] = -500
    with pytest.raises(StrategyOutputValidationError, match="capital_allocation"):
        validate_strategy_output(p)


# ─── config_updates ──────────────────────────────────────────────────

def test_config_updates_missing_change_notes_rejected() -> None:
    p = _valid_minimal_payload()
    p["decisions"]["config_updates"] = _valid_config_updates()
    del p["decisions"]["config_updates"]["change_notes"]
    with pytest.raises(StrategyOutputValidationError, match="change_notes"):
        validate_strategy_output(p)


def test_config_updates_empty_change_notes_rejected() -> None:
    p = _valid_minimal_payload()
    p["decisions"]["config_updates"] = _valid_config_updates()
    p["decisions"]["config_updates"]["change_notes"] = ""
    with pytest.raises(StrategyOutputValidationError, match="change_notes"):
        validate_strategy_output(p)


def test_config_updates_all_subs_null_rejected() -> None:
    p = _valid_minimal_payload()
    p["decisions"]["config_updates"] = {
        "signal_thresholds": None,
        "scoring_thresholds": None,
        "momentum_thresholds": None,
        "window_config": None,
        "premium_config": None,
        "margin_config": None,
        "change_notes": "Placeholder for no changes",
    }
    with pytest.raises(StrategyOutputValidationError, match="at least one"):
        validate_strategy_output(p)


def test_config_sub_block_missing_envelope_key_rejected() -> None:
    p = _valid_minimal_payload()
    p["decisions"]["config_updates"] = _valid_config_updates()
    del p["decisions"]["config_updates"]["signal_thresholds"]["version"]
    with pytest.raises(StrategyOutputValidationError, match="version"):
        validate_strategy_output(p)


# ─── session_artifacts ───────────────────────────────────────────────

def test_session_artifacts_empty_brief_rejected() -> None:
    p = _valid_minimal_payload()
    p["session_artifacts"]["cycle_brief_md"] = ""
    with pytest.raises(StrategyOutputValidationError, match="cycle_brief_md"):
        validate_strategy_output(p)


def test_session_artifacts_unknown_key_rejected() -> None:
    p = _valid_minimal_payload()
    p["session_artifacts"]["extra"] = "nope"
    with pytest.raises(StrategyOutputValidationError, match="unknown"):
        validate_strategy_output(p)


# ─── type coercion guards ────────────────────────────────────────────

def test_bool_rejected_where_integer_expected() -> None:
    """bool is a subclass of int in Python; validator should guard."""
    p = _valid_minimal_payload()
    p["decisions"]["cycle_focus"]["volume_target"] = True  # looks like 1, isn't
    with pytest.raises(StrategyOutputValidationError, match="volume_target"):
        validate_strategy_output(p)


# ─── monthly_return_pct (Step 0 Schema 1 amendment) ─────────────────


def _payload_with_monthly_goals(monthly_goals: dict) -> dict:
    p = _valid_minimal_payload()
    p["decisions"]["monthly_goals"] = monthly_goals
    return p


def test_monthly_return_pct_valid_fraction_accepted() -> None:
    """0.12 (12%) is within (0, 1) exclusive."""
    mg = _valid_monthly_goals()
    mg["monthly_return_pct"] = 0.12
    validate_strategy_output(_payload_with_monthly_goals(mg))


def test_monthly_return_pct_null_accepted() -> None:
    """null is explicitly accepted (optional field with oneOf null)."""
    mg = _valid_monthly_goals()
    mg["monthly_return_pct"] = None
    validate_strategy_output(_payload_with_monthly_goals(mg))


def test_monthly_return_pct_absent_accepted() -> None:
    """Absent field is accepted; monthly_return_pct is optional."""
    mg = _valid_monthly_goals()
    assert "monthly_return_pct" not in mg
    validate_strategy_output(_payload_with_monthly_goals(mg))


def test_monthly_return_pct_zero_rejected() -> None:
    """0 is not > 0 (exclusiveMinimum)."""
    mg = _valid_monthly_goals()
    mg["monthly_return_pct"] = 0
    with pytest.raises(StrategyOutputValidationError, match="monthly_return_pct"):
        validate_strategy_output(_payload_with_monthly_goals(mg))


def test_monthly_return_pct_one_rejected() -> None:
    """1 is not < 1 (exclusiveMaximum)."""
    mg = _valid_monthly_goals()
    mg["monthly_return_pct"] = 1
    with pytest.raises(StrategyOutputValidationError, match="monthly_return_pct"):
        validate_strategy_output(_payload_with_monthly_goals(mg))


def test_monthly_return_pct_negative_rejected() -> None:
    mg = _valid_monthly_goals()
    mg["monthly_return_pct"] = -0.1
    with pytest.raises(StrategyOutputValidationError, match="monthly_return_pct"):
        validate_strategy_output(_payload_with_monthly_goals(mg))


def test_monthly_return_pct_above_one_rejected() -> None:
    mg = _valid_monthly_goals()
    mg["monthly_return_pct"] = 1.5
    with pytest.raises(StrategyOutputValidationError, match="monthly_return_pct"):
        validate_strategy_output(_payload_with_monthly_goals(mg))


def test_monthly_return_pct_percentage_integer_rejected() -> None:
    """12 (as a percentage rather than fraction) is above 1 and rejected."""
    mg = _valid_monthly_goals()
    mg["monthly_return_pct"] = 12
    with pytest.raises(StrategyOutputValidationError, match="monthly_return_pct"):
        validate_strategy_output(_payload_with_monthly_goals(mg))


# ─── schema file well-formedness ─────────────────────────────────────

def test_schema_file_is_valid_json() -> None:
    """The canonical JSON Schema file at grailzee-cowork/schema/ must
    parse as JSON regardless of whether we programmatically use it."""
    assert SCHEMA_PATH.exists(), f"Schema file missing: {SCHEMA_PATH}"
    data = json.loads(SCHEMA_PATH.read_text())
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert data["title"] == "Grailzee Strategy Output v1"
