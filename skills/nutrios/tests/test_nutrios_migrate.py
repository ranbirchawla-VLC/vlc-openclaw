"""Tests for nutrios_migrate — Phase 1 structural transformation.

Test discipline: one test (or tightly-scoped cluster) per row of the
v1-to-v2 mapping table in NutriOS_v2_Build_Brief_v2_Extension_v3.md Part 6.1,
plus TDEE rules, idempotency, --force, exit codes, and tripwire grep.

Fixtures live under tests/fixtures/v1/{rule_1_full, rule_2_minimal, missing_protocol}.
A golden report under tests/fixtures/golden/ pins the report shape with a
monkeypatched migration timestamp.

The migrator is invoked through its public entrypoint (`migrate(...)`).
The CLI surface (main()) is exercised via subprocess for exit-code tests.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Path inserts handled by conftest.py
import nutrios_migrate
import nutrios_store as store
import nutrios_time
from nutrios_migrate import migrate
from nutrios_models import (
    Event, FoodLogEntry, DoseLogEntry, Goals, MacroRange, MedNote,
    Mesocycle, NeedsSetup, Protocol, Recipe, State, WeighIn,
)


# ---------------------------------------------------------------------------
# Fixture helpers — copy a static v1 tree to a tmp location for migration
# ---------------------------------------------------------------------------

FIXTURES_V1 = Path(__file__).parent / "fixtures" / "v1"
FIXTURES_GOLDEN = Path(__file__).parent / "fixtures" / "golden"

# Fixed UTC instant used for migrated_at_iso so reports compare deterministically
FIXED_NOW = datetime(2026, 4, 24, 18, 30, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _freeze_time(monkeypatch):
    """All migration tests run with nutrios_time.now() pinned to FIXED_NOW.

    This is the single seam Tripwire 3 cares about — every ts_iso the
    migrator writes either comes from a v1 date + tz conversion, or from
    nutrios_time.now() for the migration marker.
    """
    monkeypatch.setattr(nutrios_time, "now", lambda: FIXED_NOW)


@pytest.fixture
def v1_root(tmp_path):
    """Return a callable that copies a named v1 fixture tree under tmp_path."""
    def _copy(name: str) -> Path:
        src = FIXTURES_V1 / name
        dest = tmp_path / "v1" / name
        shutil.copytree(src, dest)
        return dest
    return _copy


@pytest.fixture
def v2_root(tmp_path, monkeypatch):
    """Return a fresh v2 root and point NUTRIOS_DATA_ROOT at it.

    Setting NUTRIOS_DATA_ROOT lets the migrator's writes flow through
    nutrios_store helpers, which require the env var.
    """
    dest = tmp_path / "v2"
    dest.mkdir(parents=True)
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(dest))
    return dest


# ---------------------------------------------------------------------------
# Migration result fixtures — run once, assert many
# ---------------------------------------------------------------------------

@pytest.fixture
def migrated_rule_1(v1_root, v2_root):
    src = v1_root("rule_1_full")
    result = migrate(source=src, dest=v2_root, user_id="alice", force=False)
    return {"src": src, "dest": v2_root, "user_id": "alice", "result": result}


@pytest.fixture
def migrated_rule_2(v1_root, v2_root):
    src = v1_root("rule_2_minimal")
    result = migrate(source=src, dest=v2_root, user_id="bob", force=False)
    return {"src": src, "dest": v2_root, "user_id": "bob", "result": result}


# ---------------------------------------------------------------------------
# Helpers that read v2 outputs through Pydantic (validates schema in passing)
# ---------------------------------------------------------------------------

def _user_dir(dest: Path, uid: str) -> Path:
    return dest / "users" / uid


def _read_protocol(dest: Path, uid: str) -> Protocol:
    return Protocol.model_validate_json((_user_dir(dest, uid) / "protocol.json").read_text())


def _read_goals_raw(dest: Path, uid: str) -> dict:
    return json.loads((_user_dir(dest, uid) / "goals.json").read_text())


def _read_goals(dest: Path, uid: str) -> Goals:
    """Goals via Pydantic — strips _pending_kcal first since DayPattern is extra='forbid'."""
    raw = _read_goals_raw(dest, uid)
    cleaned = dict(raw)
    cleaned["day_patterns"] = [
        {k: v for k, v in dp.items() if k != "_pending_kcal"}
        for dp in raw.get("day_patterns", [])
    ]
    return Goals.model_validate(cleaned)


def _read_mesocycle(dest: Path, uid: str, cycle_id: str) -> Mesocycle:
    return Mesocycle.model_validate_json(
        (_user_dir(dest, uid) / "mesocycles" / f"{cycle_id}.json").read_text()
    )


def _read_jsonl(dest: Path, uid: str, rel: str) -> list[dict]:
    p = _user_dir(dest, uid) / rel
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def _read_needs_setup(dest: Path, uid: str) -> NeedsSetup:
    return NeedsSetup.model_validate_json(
        (_user_dir(dest, uid) / "_needs_setup.json").read_text()
    )


def _read_state(dest: Path, uid: str) -> State:
    return State.model_validate_json((_user_dir(dest, uid) / "state.json").read_text())


def _read_events(dest: Path, uid: str) -> list[Event]:
    raw = json.loads((_user_dir(dest, uid) / "events.json").read_text())
    return [Event.model_validate(e) for e in raw["events"]]


def _read_recipes(dest: Path, uid: str) -> list[Recipe]:
    raw = json.loads((_user_dir(dest, uid) / "recipes.json").read_text())
    return [Recipe.model_validate(r) for r in raw["recipes"]]


def _read_marker(dest: Path, uid: str) -> dict:
    return json.loads((_user_dir(dest, uid) / "_migration_marker.json").read_text())


# ===========================================================================
# Treatment field renames (mapping table row 1)
# ===========================================================================

def test_treatment_field_renames(migrated_rule_1):
    p = _read_protocol(migrated_rule_1["dest"], "alice")
    assert p.treatment.medication == "Tirzepatide"
    assert p.treatment.dose_mg == 10.0
    assert p.treatment.brand == "Mounjaro"


def test_treatment_optional_fields_carry(migrated_rule_1):
    p = _read_protocol(migrated_rule_1["dest"], "alice")
    assert p.treatment.titration_notes == "Increased from 7.5 on 2026-02-01"
    assert p.treatment.dose_day_of_week == "thursday"
    assert p.treatment.dose_time == "07:00"


# ===========================================================================
# Biometrics direct carry / discard rules
# ===========================================================================

def test_biometrics_direct_carry(migrated_rule_1):
    p = _read_protocol(migrated_rule_1["dest"], "alice")
    assert p.biometrics.start_weight_lbs == 220.0
    assert p.biometrics.target_weight_lbs == 180.0
    assert str(p.biometrics.start_date) == "2026-01-01"
    assert p.biometrics.long_term_goal == "Maintain after target reached."


def test_current_weight_lbs_discarded(migrated_rule_1):
    """current_weight_lbs is recoverable from the last weigh-in — not stored on protocol."""
    raw = json.loads((_user_dir(migrated_rule_1["dest"], "alice") / "protocol.json").read_text())
    assert "current_weight_lbs" not in raw.get("biometrics", {})


# ===========================================================================
# Thyroid + CGM clinical carry
# ===========================================================================

def test_thyroid_and_cgm_to_clinical(migrated_rule_1):
    p = _read_protocol(migrated_rule_1["dest"], "alice")
    assert p.clinical.thyroid_medication is False
    assert p.clinical.cgm_active is False


# ===========================================================================
# Gallbladder default + marker
# ===========================================================================

def test_gallbladder_defaults_unknown(migrated_rule_1):
    p = _read_protocol(migrated_rule_1["dest"], "alice")
    assert p.clinical.gallbladder_status == "unknown"


def test_gallbladder_marker_always_set(migrated_rule_1, migrated_rule_2):
    """gallbladder marker is always set — v1 has no field, regardless of TDEE rule."""
    assert _read_needs_setup(migrated_rule_1["dest"], "alice").gallbladder is True
    assert _read_needs_setup(migrated_rule_2["dest"], "bob").gallbladder is True


# ===========================================================================
# TDEE Rule 1 — whoop_tdee_kcal present, > 0
# ===========================================================================

def test_rule_1_active_mesocycle_carries_tdee(migrated_rule_1):
    m = _read_mesocycle(migrated_rule_1["dest"], "alice", "cycle_apr")
    assert m.tdee_kcal == 2600


def test_rule_1_no_tdee_marker(migrated_rule_1):
    assert _read_needs_setup(migrated_rule_1["dest"], "alice").tdee is False


def test_rule_1_deficits_computed_per_day_pattern(migrated_rule_1):
    g = _read_goals(migrated_rule_1["dest"], "alice")
    by_type = {dp.day_type: dp.deficit_kcal for dp in g.day_patterns}
    # rest: 2600 - 2000 = 600; training: 2600 - 2400 = 200
    assert by_type["rest"] == 600
    assert by_type["training"] == 200


def test_rule_1_nominal_cycle_deficit_tie_break_uses_most_common_day_type(migrated_rule_1):
    """Two deficits each appear once across day types (rest=600, training=200).
    Tie-break: weekly_schedule has 4 rest days, 3 training. Nominal = rest's deficit (600).
    """
    m = _read_mesocycle(migrated_rule_1["dest"], "alice", "cycle_apr")
    assert m.deficit_kcal == 600


def test_rule_1_deficits_and_nominal_markers_set_anyway(migrated_rule_1):
    ns = _read_needs_setup(migrated_rule_1["dest"], "alice")
    assert ns.deficits is True
    assert ns.nominal_deficit is True


def test_rule_1_no_pending_kcal_field(migrated_rule_1):
    raw = _read_goals_raw(migrated_rule_1["dest"], "alice")
    for dp in raw["day_patterns"]:
        assert "_pending_kcal" not in dp, "Rule 1 must NOT write _pending_kcal"


# ===========================================================================
# TDEE Rule 2 — whoop_tdee_kcal null
# ===========================================================================

def test_rule_2_active_mesocycle_tdee_null(migrated_rule_2):
    m = _read_mesocycle(migrated_rule_2["dest"], "bob", "bob_cycle1")
    assert m.tdee_kcal is None


def test_rule_2_pending_kcal_written_as_raw_dict_field(migrated_rule_2):
    """Tripwire 5: _pending_kcal lives only as a raw-dict scratch field on day_patterns.
    Never enters DayPattern (extra='forbid'). Migration writes via raw dict.
    """
    raw = _read_goals_raw(migrated_rule_2["dest"], "bob")
    by_type = {dp["day_type"]: dp["_pending_kcal"] for dp in raw["day_patterns"]}
    assert by_type == {"rest": 1900, "training": 2200, "post_dose": 1700}


def test_rule_2_no_deficits_computed(migrated_rule_2):
    """deficit_kcal stays unset on day_patterns — the user supplies it in Phase 2."""
    g = _read_goals(migrated_rule_2["dest"], "bob")
    for dp in g.day_patterns:
        assert dp.deficit_kcal is None


def test_rule_2_all_three_markers_set(migrated_rule_2):
    ns = _read_needs_setup(migrated_rule_2["dest"], "bob")
    assert ns.tdee is True
    assert ns.deficits is True
    assert ns.nominal_deficit is True


# ===========================================================================
# Weigh-ins (mapping row: protocol.biometrics.weigh_ins[] → weigh_ins.jsonl)
# ===========================================================================

def test_weigh_ins_to_jsonl_with_monotonic_ids(migrated_rule_1):
    rows = _read_jsonl(migrated_rule_1["dest"], "alice", "weigh_ins.jsonl")
    assert [r["id"] for r in rows] == [1, 2, 3]
    assert [r["weight_lbs"] for r in rows] == [215.0, 213.5, 211.5]


def test_weigh_ins_ts_iso_uses_noon_local_to_utc(migrated_rule_1):
    """v1 date '2026-04-01' + 12:00 America/Denver (UTC-06 in April DST) → 18:00Z."""
    rows = _read_jsonl(migrated_rule_1["dest"], "alice", "weigh_ins.jsonl")
    # 2026-04-01 was MDT (UTC-06) — noon local = 18:00 UTC
    parsed = nutrios_time.parse(rows[0]["ts_iso"])
    assert parsed == datetime(2026, 4, 1, 18, 0, 0, tzinfo=timezone.utc)


def test_weigh_in_notes_carry_through(migrated_rule_1):
    rows = _read_jsonl(migrated_rule_1["dest"], "alice", "weigh_ins.jsonl")
    assert rows[0]["notes"] == "post-vacation"
    assert rows[1]["notes"] is None


# ===========================================================================
# Med team notes
# ===========================================================================

def test_med_notes_to_jsonl_with_monotonic_ids(migrated_rule_1):
    rows = _read_jsonl(migrated_rule_1["dest"], "alice", "med_notes.jsonl")
    assert [r["id"] for r in rows] == [1, 2]
    assert rows[0]["note"] == "Bloodwork on 4/30."
    assert rows[1]["note"] == "Reminder: hydration."


def test_med_notes_default_source_self(migrated_rule_1):
    rows = _read_jsonl(migrated_rule_1["dest"], "alice", "med_notes.jsonl")
    assert rows[0]["source"] == "doctor"
    assert rows[1]["source"] == "self"  # missing in v1 → defaults to "self"


# ===========================================================================
# Events — re-keyed, normalized
# ===========================================================================

def test_events_re_keyed_with_monotonic_id(migrated_rule_1):
    events = _read_events(migrated_rule_1["dest"], "alice")
    assert sorted([e.id for e in events]) == [1, 2, 3, 4]


def test_events_known_types_pass_through(migrated_rule_1):
    events = _read_events(migrated_rule_1["dest"], "alice")
    by_title = {e.title: e for e in events}
    assert by_title["Wisdom tooth surgery"].event_type == "surgery"
    assert by_title["Bloodwork"].event_type == "appointment"
    assert by_title["Reached 210!"].event_type == "milestone"


def test_events_unknown_type_maps_to_other_with_original_in_notes(migrated_rule_1):
    events = _read_events(migrated_rule_1["dest"], "alice")
    family_event = next(e for e in events if e.title == "Mom's birthday dinner")
    assert family_event.event_type == "other"
    # Original type is appended to notes; the policy is documented in nutrios_migrate
    assert "family" in (family_event.notes or "")
    assert "out of town" in (family_event.notes or "")  # original notes preserved too


# ===========================================================================
# Daily logs — food, dose synthesis, discards
# ===========================================================================

def test_food_estimated_becomes_manual(migrated_rule_1):
    rows = _read_jsonl(migrated_rule_1["dest"], "alice", "log/2026-04-15.jsonl")
    food_rows = [r for r in rows if r["kind"] == "food"]
    sources = {r["source"] for r in food_rows}
    # v1 had one 'estimated' (yogurt) and one 'manual' (salad); both become 'manual'
    assert sources == {"manual"}


def test_dose_logged_true_synthesizes_dose_entry(migrated_rule_1):
    rows = _read_jsonl(migrated_rule_1["dest"], "alice", "log/2026-04-16.jsonl")
    dose_rows = [r for r in rows if r["kind"] == "dose"]
    assert len(dose_rows) == 1
    d = dose_rows[0]
    # Snapshot of current protocol: 10mg, Mounjaro
    assert d["dose_mg"] == 10.0
    assert d["brand"] == "Mounjaro"
    # ts_iso = 2026-04-16 + 07:00 America/Denver (MDT, UTC-06) → 13:00Z
    parsed = nutrios_time.parse(d["ts_iso"])
    assert parsed == datetime(2026, 4, 16, 13, 0, 0, tzinfo=timezone.utc)


def test_dose_logged_false_no_dose_entry(migrated_rule_1):
    rows_15 = _read_jsonl(migrated_rule_1["dest"], "alice", "log/2026-04-15.jsonl")
    rows_17 = _read_jsonl(migrated_rule_1["dest"], "alice", "log/2026-04-17.jsonl")
    assert all(r["kind"] != "dose" for r in rows_15)
    assert all(r["kind"] != "dose" for r in rows_17)


def test_log_entries_use_single_monotonic_id_counter(migrated_rule_1):
    """Per spec: a single monotonic counter for both food and dose entries."""
    rows_15 = _read_jsonl(migrated_rule_1["dest"], "alice", "log/2026-04-15.jsonl")
    rows_16 = _read_jsonl(migrated_rule_1["dest"], "alice", "log/2026-04-16.jsonl")
    all_ids = sorted([r["id"] for r in rows_15] + [r["id"] for r in rows_16])
    assert all_ids == list(range(1, len(all_ids) + 1))


def test_water_count_discarded(migrated_rule_1):
    """No water_count appears anywhere in v2 output (all kinds, all dates)."""
    for date_str in ("2026-04-15", "2026-04-16", "2026-04-17"):
        rows = _read_jsonl(migrated_rule_1["dest"], "alice", f"log/{date_str}.jsonl")
        for r in rows:
            assert "water_count" not in r


def test_day_notes_discarded_from_log_entries(migrated_rule_1):
    for date_str in ("2026-04-15", "2026-04-16", "2026-04-17"):
        rows = _read_jsonl(migrated_rule_1["dest"], "alice", f"log/{date_str}.jsonl")
        for r in rows:
            assert "day_notes" not in r


def test_running_totals_remaining_targets_discarded(migrated_rule_1):
    rows = _read_jsonl(migrated_rule_1["dest"], "alice", "log/2026-04-15.jsonl")
    for r in rows:
        for forbidden in ("running_totals", "remaining", "targets"):
            assert forbidden not in r


# ===========================================================================
# Mesocycles — historical TDEE always null
# ===========================================================================

def test_active_mesocycle_carries_cycle_fields(migrated_rule_1):
    m = _read_mesocycle(migrated_rule_1["dest"], "alice", "cycle_apr")
    assert m.phase == "cut"
    assert m.label == "April cut"
    assert str(m.start_date) == "2026-04-01"


def test_historical_mesocycles_get_null_tdee(migrated_rule_1):
    m_jan = _read_mesocycle(migrated_rule_1["dest"], "alice", "cut_jan")
    m_q4 = _read_mesocycle(migrated_rule_1["dest"], "alice", "recomp_q4")
    assert m_jan.tdee_kcal is None
    assert m_q4.tdee_kcal is None


def test_historical_mesocycles_flagged_in_report(migrated_rule_1):
    report = migrated_rule_1["result"].report_text
    assert "cut_jan" in report
    assert "recomp_q4" in report
    assert "null TDEE" in report or "tdee" in report.lower()


# ===========================================================================
# Goals — ranges, protected mirroring
# ===========================================================================

def test_protein_to_min_protected(migrated_rule_1):
    g = _read_goals(migrated_rule_1["dest"], "alice")
    assert g.defaults.protein_g.min == 175
    assert g.defaults.protein_g.max is None
    assert g.defaults.protein_g.protected is True  # v1 protein was protected


def test_fat_max_65_in_defaults_with_protected_mirroring(migrated_rule_1):
    g = _read_goals(migrated_rule_1["dest"], "alice")
    assert g.defaults.fat_g.max == 65
    assert g.defaults.fat_g.min is None
    assert g.defaults.fat_g.protected is False  # v1 fat_protected was False


def test_fat_deficit_override_58_on_deficit_day_pattern(migrated_rule_1):
    g = _read_goals(migrated_rule_1["dest"], "alice")
    by_type = {dp.day_type: dp for dp in g.day_patterns}
    # rest is is_deficit_day=true → fat_g.max = 58
    assert by_type["rest"].fat_g.max == 58
    # training is_deficit_day=false → no fat override
    assert by_type["training"].fat_g.max is None


def test_carbs_to_min_only(migrated_rule_1):
    g = _read_goals(migrated_rule_1["dest"], "alice")
    by_type = {dp.day_type: dp for dp in g.day_patterns}
    assert by_type["rest"].carbs_g.min == 180
    assert by_type["rest"].carbs_g.max is None
    assert by_type["training"].carbs_g.min == 220
    assert by_type["training"].carbs_g.max is None


def test_carbs_shape_marker_always_set(migrated_rule_1, migrated_rule_2):
    assert _read_needs_setup(migrated_rule_1["dest"], "alice").carbs_shape is True
    assert _read_needs_setup(migrated_rule_2["dest"], "bob").carbs_shape is True


def test_weekly_schedule_carries_through(migrated_rule_1):
    g = _read_goals(migrated_rule_1["dest"], "alice")
    assert g.weekly_schedule["monday"] == "rest"
    assert g.weekly_schedule["tuesday"] == "training"


def test_active_cycle_id_points_at_active_mesocycle(migrated_rule_1):
    g = _read_goals(migrated_rule_1["dest"], "alice")
    assert g.active_cycle_id == "cycle_apr"


# ===========================================================================
# Recipes — pass-through and quarantine
# ===========================================================================

def test_recipes_valid_pass_through(migrated_rule_1):
    recipes = _read_recipes(migrated_rule_1["dest"], "alice")
    by_id = {r.id: r for r in recipes}
    assert 1 in by_id and by_id[1].name == "Greek chicken bowl"
    assert 2 in by_id and by_id[2].name == "Whey shake"
    # Mystery soup (id=3) lacked macros_per_serving — quarantined, not in recipes.json
    assert 3 not in by_id


def test_recipes_missing_macros_quarantined_with_reason(migrated_rule_1):
    qdir = _user_dir(migrated_rule_1["dest"], "alice") / "_quarantine" / "recipes"
    assert qdir.exists()
    files = sorted(qdir.iterdir())
    # Two files: the recipe itself + a sidecar .reason.txt
    payloads = [f for f in files if f.suffix == ".json"]
    reasons = [f for f in files if f.name.endswith(".reason.txt")]
    assert len(payloads) == 1
    assert len(reasons) == 1
    reason_text = reasons[0].read_text()
    assert "macros_per_serving" in reason_text


# ===========================================================================
# .bak files
# ===========================================================================

def test_bak_files_discarded_with_count_in_report(migrated_rule_1):
    # protocol.json.bak exists in fixture; it must NOT propagate
    assert not (_user_dir(migrated_rule_1["dest"], "alice") / "protocol.json.bak").exists()
    assert ".bak" in migrated_rule_1["result"].report_text


# ===========================================================================
# state.json counters reflect totals
# ===========================================================================

def test_state_counters_reflect_totals(migrated_rule_1):
    s = _read_state(migrated_rule_1["dest"], "alice")
    assert s.last_weigh_in_id == 3
    assert s.last_med_note_id == 2
    assert s.last_event_id == 4
    # 3 food (one per log: 2 + 1 + 0 = 3) + 1 dose = 4 entries total
    assert s.last_entry_id == 4
    # last_recipe_id reflects max id across ALL v1 recipes (including quarantined)
    # so future adds don't collide if a quarantined recipe is later un-quarantined.
    assert s.last_recipe_id == 3


# ===========================================================================
# Idempotency — marker present blocks re-run unless --force
# ===========================================================================

def test_migration_marker_written_with_required_fields(migrated_rule_1):
    marker = _read_marker(migrated_rule_1["dest"], "alice")
    assert marker["source_root"] == str(migrated_rule_1["src"].resolve())
    assert "migrated_at_iso" in marker
    assert marker["v1_file_count"] >= 1
    assert marker["v2_file_count"] >= 1
    assert "counts_per_kind" in marker
    assert "markers_set" in marker


def test_rerun_without_force_exits_2(migrated_rule_1):
    src = migrated_rule_1["src"]
    dest = migrated_rule_1["dest"]
    second = migrate(source=src, dest=dest, user_id="alice", force=False)
    assert second.exit_code == 2
    assert second.success is False


def test_rerun_with_force_rebuilds(migrated_rule_1):
    src = migrated_rule_1["src"]
    dest = migrated_rule_1["dest"]
    # Drop a marker file inside the user dir to confirm it gets removed
    canary = _user_dir(dest, "alice") / "extra_canary.txt"
    canary.write_text("would be removed")
    third = migrate(source=src, dest=dest, user_id="alice", force=True)
    assert third.exit_code == 0
    assert not canary.exists()
    # Marker recreated
    assert (_user_dir(dest, "alice") / "_migration_marker.json").exists()


def test_force_does_not_delete_outside_user_dir(v1_root, v2_root):
    src = v1_root("rule_1_full")
    # Plant a sibling file at the dest root, plus a different user dir
    (v2_root / "OTHER_FILE.txt").write_text("untouchable")
    other = v2_root / "users" / "carol"
    other.mkdir(parents=True)
    (other / "important.json").write_text("{}")

    migrate(source=src, dest=v2_root, user_id="alice", force=False)
    result = migrate(source=src, dest=v2_root, user_id="alice", force=True)
    assert result.exit_code == 0
    assert (v2_root / "OTHER_FILE.txt").exists()
    assert (other / "important.json").exists()


# ===========================================================================
# Argument validation / missing v1 files
# ===========================================================================

def test_missing_protocol_exits_1(v1_root, v2_root):
    src = v1_root("missing_protocol")
    result = migrate(source=src, dest=v2_root, user_id="carl", force=False)
    assert result.exit_code == 1
    assert result.success is False
    assert result.error is not None


def test_invalid_user_id_exits_3(v1_root, v2_root):
    src = v1_root("rule_1_full")
    result = migrate(source=src, dest=v2_root, user_id="../nope", force=False)
    assert result.exit_code == 3


def test_nonexistent_source_exits_3(tmp_path, v2_root):
    result = migrate(source=tmp_path / "does_not_exist", dest=v2_root,
                     user_id="alice", force=False)
    assert result.exit_code == 3


# ===========================================================================
# Report — sections, golden comparison
# ===========================================================================

def test_report_contains_required_sections(migrated_rule_1):
    r = migrated_rule_1["result"].report_text
    for section in (
        "# NutriOS Migration Report",
        "## Counts",
        "## By kind",
        "## Discarded",
        "## Markers set",
        "## Warnings",
        "## TDEE/Deficit Resolution",
    ):
        assert section in r, f"Missing section: {section!r}"


def test_report_path_printed_to_stdout_via_main(v1_root, v2_root, monkeypatch):
    src = v1_root("rule_1_full")
    monkeypatch.setattr(sys, "argv", [
        "nutrios_migrate",
        "--source", str(src),
        "--dest", str(v2_root),
        "--user-id", "alice",
    ])
    # main() returns exit code; capture stdout via capsys-style
    import io
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    code = nutrios_migrate.main()
    out = buf.getvalue().strip()
    assert code == 0
    assert out.endswith(".md")
    assert Path(out).exists()


def test_report_lists_water_count_per_day(migrated_rule_1):
    r = migrated_rule_1["result"].report_text
    # water_count totals: 2026-04-15=6, 2026-04-16=8, 2026-04-17=5 → total 19
    assert "19" in r
    # Per-day breakdown — at least one of the dates labelled
    assert "2026-04-15" in r


def test_report_lists_day_notes_verbatim(migrated_rule_1):
    r = migrated_rule_1["result"].report_text
    assert "Felt good, gym in afternoon." in r
    assert "Rough day." in r


def test_report_records_synthesized_dose_count(migrated_rule_1):
    r = migrated_rule_1["result"].report_text
    assert "1" in r
    assert "synthesiz" in r.lower()  # "synthesized" — match either spelling


def test_report_records_rule_fired_1(migrated_rule_1):
    assert "Rule fired: 1" in migrated_rule_1["result"].report_text


def test_report_records_rule_fired_2(migrated_rule_2):
    assert "Rule fired: 2" in migrated_rule_2["result"].report_text


def test_golden_report_matches_for_rule_1_full(migrated_rule_1):
    golden = (FIXTURES_GOLDEN / "rule_1_full_report.md").read_text()
    actual = migrated_rule_1["result"].report_text
    # Replace absolute paths and timestamps in actual to match golden's placeholders
    actual_normalized = re.sub(
        r"^\*\*Source:\*\* .*$", "**Source:** <SOURCE>", actual, flags=re.M,
    )
    actual_normalized = re.sub(
        r"^\*\*Destination:\*\* .*$", "**Destination:** <DEST>", actual_normalized, flags=re.M,
    )
    assert actual_normalized == golden


# ===========================================================================
# Tripwire grep verifications (file scans against the migrate module)
# ===========================================================================

LIB_DIR = Path(__file__).parent.parent / "lib"
MIGRATE_PATH = LIB_DIR / "nutrios_migrate.py"


def _migrate_source() -> str:
    return MIGRATE_PATH.read_text()


def test_tripwire_3_no_datetime_now_in_migrate(migrated_rule_1):
    """Reject the call form 'datetime.now(' / 'date.today('. The bare name
    can appear in docstring acknowledgments (existing project convention,
    progress.md notes the same allowance for tools/)."""
    src = _migrate_source()
    assert "datetime.now(" not in src, "Tripwire 3: migrator must not call datetime.now()"
    assert "date.today(" not in src, "Tripwire 3: migrator must not call date.today()"


def test_tripwire_5_pending_kcal_only_in_migrate_within_lib(migrated_rule_1):
    """_pending_kcal must NOT appear in nutrios_models.py. lib hits limited to migrate + setup_resume's strip helpers."""
    models_src = (LIB_DIR / "nutrios_models.py").read_text()
    assert "_pending_kcal" not in models_src, (
        "Tripwire 5: _pending_kcal must not enter the canonical model surface"
    )
    assert "_pending_kcal" in _migrate_source(), (
        "Tripwire 5: migrator is the writer of the _pending_kcal scratch field"
    )


def test_tripwire_2_no_open_w_jsonl_in_migrate(migrated_rule_1):
    """Migrator never opens a .jsonl path in 'w' mode directly — all JSONL writes
    go through nutrios_store helpers (append_jsonl or write_jsonl_batch)."""
    src = _migrate_source()
    # The acceptable patterns: store.write_jsonl_batch and store.append_jsonl
    assert "write_jsonl_batch" in src
    # Reject any direct open('...jsonl', 'w')-shaped pattern
    pattern = re.compile(r"open\([^)]*\.jsonl[^)]*['\"]w['\"]")
    assert not pattern.search(src), "Tripwire 2: no direct open(... .jsonl, 'w') in migrate"
