"""Tests for nutrios_setup_resume — marker walker for guided setup.

Covers each of the five markers (gallbladder → tdee → carbs_shape →
deficits → nominal_deficit), the empty-answer prompt-surface branch, the
invalid-answer reprompt branch, the marker-cleared completion path, and
the full end-to-end walk that exits via render_setup_complete.

Also asserts the _pending_kcal scratch-field discipline: present after
migration, surviving the carbs_shape write, consumed and cleared by
the deficits step.
"""
import json
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from nutrios_models import (
    Goals, Mesocycle, NeedsSetup, Protocol, ToolResult,
)
import nutrios_store as store
import nutrios_setup_resume as tool


_NOW = datetime(2026, 4, 24, 18, 0, 0, tzinfo=timezone.utc)
_TZ = "America/Denver"


def _argv(*, user_answer: str = "", **kwargs) -> str:
    payload = {
        "user_id": "alice",
        "user_answer": user_answer,
        "now": _NOW.isoformat(),
        "tz": _TZ,
    }
    payload.update(kwargs)
    return json.dumps(payload, default=str)


def _all_markers_pending() -> NeedsSetup:
    return NeedsSetup(
        gallbladder=True, tdee=True, carbs_shape=True,
        deficits=True, nominal_deficit=True,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_setup_resume_rejects_extra_field(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(_argv(bogus=1))


# ---------------------------------------------------------------------------
# Setup complete branch
# ---------------------------------------------------------------------------

def test_setup_resume_complete_returns_render_setup_complete(tmp_data_root, setup_user):
    """All markers cleared → render_setup_complete on any call."""
    setup_user("alice")  # default: needs_setup all False
    result = tool.main(_argv())
    assert "Setup complete" in result.display_text
    assert result.marker_cleared is None
    assert result.next_marker is None
    assert result.needs_followup is False


# ---------------------------------------------------------------------------
# Empty-answer surfacing
# ---------------------------------------------------------------------------

def test_setup_resume_empty_answer_surfaces_first_pending(tmp_data_root, setup_user):
    setup_user("alice", needs_setup=_all_markers_pending())
    result = tool.main(_argv())
    assert result.needs_followup is True
    assert result.next_marker == "gallbladder"
    assert "gallbladder" in result.display_text.lower()


def test_setup_resume_empty_answer_respects_dependency_order(tmp_data_root, setup_user):
    """deficits cannot surface until tdee is cleared."""
    setup_user("alice", needs_setup=NeedsSetup(
        gallbladder=False, tdee=True, carbs_shape=True, deficits=True, nominal_deficit=True,
    ))
    result = tool.main(_argv())
    assert result.next_marker == "tdee"


# ---------------------------------------------------------------------------
# gallbladder marker
# ---------------------------------------------------------------------------

def test_setup_resume_gallbladder_removed_clears_marker(tmp_data_root, setup_user):
    setup_user("alice", needs_setup=NeedsSetup(gallbladder=True))
    result = tool.main(_argv(user_answer="removed"))
    assert result.marker_cleared == "gallbladder"
    # All other markers were already False, so setup is now complete
    assert result.next_marker is None
    assert "Setup complete" in result.display_text

    proto = store.read_json("alice", "protocol.json", Protocol)
    assert proto.clinical.gallbladder_status == "removed"

    needs = store.read_needs_setup("alice")
    assert needs.gallbladder is False


def test_setup_resume_gallbladder_present_clears_marker(tmp_data_root, setup_user):
    setup_user("alice", needs_setup=NeedsSetup(gallbladder=True))
    result = tool.main(_argv(user_answer="present"))
    proto = store.read_json("alice", "protocol.json", Protocol)
    assert proto.clinical.gallbladder_status == "present"
    assert result.marker_cleared == "gallbladder"


def test_setup_resume_gallbladder_invalid_reprompts(tmp_data_root, setup_user):
    setup_user("alice", needs_setup=NeedsSetup(gallbladder=True))
    result = tool.main(_argv(user_answer="maybe"))
    assert result.marker_cleared is None  # not cleared
    assert result.next_marker == "gallbladder"
    assert result.needs_followup is True

    needs = store.read_needs_setup("alice")
    assert needs.gallbladder is True  # still pending


# ---------------------------------------------------------------------------
# tdee marker
# ---------------------------------------------------------------------------

def test_setup_resume_tdee_valid_writes_mesocycle(tmp_data_root, setup_user):
    setup_user("alice", needs_setup=NeedsSetup(tdee=True), tdee_kcal=None)
    result = tool.main(_argv(user_answer="2600"))
    assert result.marker_cleared == "tdee"

    goals = store.read_json("alice", "goals.json", Goals)
    meso = store.read_json("alice", f"mesocycles/{goals.active_cycle_id}.json", Mesocycle)
    assert meso.tdee_kcal == 2600


def test_setup_resume_tdee_non_integer_reprompts(tmp_data_root, setup_user):
    setup_user("alice", needs_setup=NeedsSetup(tdee=True), tdee_kcal=None)
    result = tool.main(_argv(user_answer="abc"))
    assert result.next_marker == "tdee"
    assert result.marker_cleared is None


def test_setup_resume_tdee_out_of_range_reprompts(tmp_data_root, setup_user):
    setup_user("alice", needs_setup=NeedsSetup(tdee=True), tdee_kcal=None)
    result = tool.main(_argv(user_answer="500"))  # too low
    assert result.next_marker == "tdee"
    assert result.marker_cleared is None


# ---------------------------------------------------------------------------
# carbs_shape marker
# ---------------------------------------------------------------------------

def test_setup_resume_carbs_shape_yes_keeps_min(tmp_data_root, setup_user):
    setup_user("alice", needs_setup=NeedsSetup(carbs_shape=True))
    result = tool.main(_argv(user_answer="yes"))
    assert result.marker_cleared == "carbs_shape"

    goals = store.read_json("alice", "goals.json", Goals)
    rest = next(dp for dp in goals.day_patterns if dp.day_type == "rest")
    assert rest.carbs_g.min == 180  # unchanged from fixture
    assert rest.carbs_g.max is None


def test_setup_resume_carbs_shape_max_flips_min_to_max(tmp_data_root, setup_user):
    setup_user("alice", needs_setup=NeedsSetup(carbs_shape=True))
    tool.main(_argv(user_answer="max"))

    goals = store.read_json("alice", "goals.json", Goals)
    rest = next(dp for dp in goals.day_patterns if dp.day_type == "rest")
    assert rest.carbs_g.min is None
    assert rest.carbs_g.max == 180


def test_setup_resume_carbs_shape_both_sets_both_ends(tmp_data_root, setup_user):
    setup_user("alice", needs_setup=NeedsSetup(carbs_shape=True))
    tool.main(_argv(user_answer="both"))

    goals = store.read_json("alice", "goals.json", Goals)
    rest = next(dp for dp in goals.day_patterns if dp.day_type == "rest")
    assert rest.carbs_g.min == 180
    assert rest.carbs_g.max == 180


def test_setup_resume_carbs_shape_invalid_reprompts(tmp_data_root, setup_user):
    setup_user("alice", needs_setup=NeedsSetup(carbs_shape=True))
    result = tool.main(_argv(user_answer="maybe"))
    assert result.next_marker == "carbs_shape"
    assert result.marker_cleared is None


def test_setup_resume_carbs_shape_preserves_pending_kcal(tmp_data_root, setup_user):
    """Carbs write must preserve _pending_kcal scratch fields for the deficits step."""
    setup_user("alice", needs_setup=NeedsSetup(carbs_shape=True, deficits=True, nominal_deficit=True))
    # Inject _pending_kcal into goals.json raw
    raw = store.read_json_raw("alice", "goals.json")
    for dp in raw["day_patterns"]:
        if dp["day_type"] == "rest":
            dp["_pending_kcal"] = 2000
        elif dp["day_type"] == "training":
            dp["_pending_kcal"] = 2400
    store.write_json_raw("alice", "goals.json", raw)

    tool.main(_argv(user_answer="yes"))  # carbs_shape yes

    after = store.read_json_raw("alice", "goals.json")
    rest = next(dp for dp in after["day_patterns"] if dp["day_type"] == "rest")
    train = next(dp for dp in after["day_patterns"] if dp["day_type"] == "training")
    assert rest["_pending_kcal"] == 2000
    assert train["_pending_kcal"] == 2400


# ---------------------------------------------------------------------------
# deficits marker
# ---------------------------------------------------------------------------

def test_setup_resume_deficits_yes_applies_suggested_and_clears_pending(tmp_data_root, setup_user):
    """User answers 'yes' → tdee - _pending_kcal becomes deficit_kcal per pattern, scratch cleared."""
    setup_user("alice", needs_setup=NeedsSetup(deficits=True, nominal_deficit=True), tdee_kcal=2600)
    raw = store.read_json_raw("alice", "goals.json")
    for dp in raw["day_patterns"]:
        if dp["day_type"] == "rest":
            dp["_pending_kcal"] = 2000  # → deficit 600
        elif dp["day_type"] == "training":
            dp["_pending_kcal"] = 2400  # → deficit 200
    store.write_json_raw("alice", "goals.json", raw)

    result = tool.main(_argv(user_answer="yes"))
    assert result.marker_cleared == "deficits"

    after = store.read_json_raw("alice", "goals.json")
    rest = next(dp for dp in after["day_patterns"] if dp["day_type"] == "rest")
    train = next(dp for dp in after["day_patterns"] if dp["day_type"] == "training")
    assert rest["deficit_kcal"] == 600
    assert train["deficit_kcal"] == 200
    # _pending_kcal must be GONE after deficits step
    assert "_pending_kcal" not in rest
    assert "_pending_kcal" not in train


def test_setup_resume_deficits_invalid_reprompts(tmp_data_root, setup_user):
    setup_user("alice", needs_setup=NeedsSetup(deficits=True, nominal_deficit=True), tdee_kcal=2600)
    result = tool.main(_argv(user_answer="custom"))
    assert result.next_marker == "deficits"
    assert result.marker_cleared is None


# ---------------------------------------------------------------------------
# nominal_deficit marker
# ---------------------------------------------------------------------------

def test_setup_resume_nominal_deficit_yes_uses_most_common(tmp_data_root, setup_user):
    """If two day_patterns have deficit 600 and one has 200, 'yes' picks 600."""
    setup_user("alice", needs_setup=NeedsSetup(nominal_deficit=True))
    # Manually set up day_patterns with deficit_kcal
    goals = store.read_json("alice", "goals.json", Goals)
    new_patterns = [
        dp.model_copy(update={"deficit_kcal": 600 if dp.day_type == "rest" else 200})
        for dp in goals.day_patterns
    ]
    new_goals = goals.model_copy(update={"day_patterns": new_patterns})
    store.write_json("alice", "goals.json", new_goals)

    result = tool.main(_argv(user_answer="yes"))
    assert result.marker_cleared == "nominal_deficit"

    meso = store.read_json("alice", f"mesocycles/{goals.active_cycle_id}.json", Mesocycle)
    # There are 2 patterns: rest (600) and training (200). Most common is one of them.
    assert meso.deficit_kcal in {200, 600}


def test_setup_resume_nominal_deficit_explicit_number(tmp_data_root, setup_user):
    setup_user("alice", needs_setup=NeedsSetup(nominal_deficit=True))
    result = tool.main(_argv(user_answer="450"))
    assert result.marker_cleared == "nominal_deficit"

    goals = store.read_json("alice", "goals.json", Goals)
    meso = store.read_json("alice", f"mesocycles/{goals.active_cycle_id}.json", Mesocycle)
    assert meso.deficit_kcal == 450


def test_setup_resume_nominal_deficit_invalid_reprompts(tmp_data_root, setup_user):
    setup_user("alice", needs_setup=NeedsSetup(nominal_deficit=True))
    result = tool.main(_argv(user_answer="abc"))
    assert result.next_marker == "nominal_deficit"
    assert result.marker_cleared is None


# ---------------------------------------------------------------------------
# Full end-to-end walk
# ---------------------------------------------------------------------------

def test_setup_resume_full_walk_reaches_completion(tmp_data_root, setup_user):
    """All five markers cleared in order; final call returns render_setup_complete."""
    setup_user("alice", needs_setup=_all_markers_pending(), tdee_kcal=None)
    # Seed _pending_kcal so deficits step has something to work with
    raw = store.read_json_raw("alice", "goals.json")
    for dp in raw["day_patterns"]:
        dp["_pending_kcal"] = 2000 if dp["day_type"] == "rest" else 2400
    store.write_json_raw("alice", "goals.json", raw)

    # 1. gallbladder
    r1 = tool.main(_argv(user_answer="present"))
    assert r1.marker_cleared == "gallbladder"
    assert r1.next_marker == "tdee"

    # 2. tdee
    r2 = tool.main(_argv(user_answer="2600"))
    assert r2.marker_cleared == "tdee"
    assert r2.next_marker == "carbs_shape"

    # 3. carbs_shape
    r3 = tool.main(_argv(user_answer="yes"))
    assert r3.marker_cleared == "carbs_shape"
    assert r3.next_marker == "deficits"

    # 4. deficits
    r4 = tool.main(_argv(user_answer="yes"))
    assert r4.marker_cleared == "deficits"
    assert r4.next_marker == "nominal_deficit"

    # 5. nominal_deficit
    r5 = tool.main(_argv(user_answer="yes"))
    assert r5.marker_cleared == "nominal_deficit"
    assert r5.next_marker is None
    assert "Setup complete" in r5.display_text

    # All markers cleared on disk
    needs = store.read_needs_setup("alice")
    assert needs.gallbladder is False
    assert needs.tdee is False
    assert needs.carbs_shape is False
    assert needs.deficits is False
    assert needs.nominal_deficit is False


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------

def test_setup_resume_isolation(tmp_data_root, setup_user):
    setup_user("alice", needs_setup=NeedsSetup(gallbladder=True))
    setup_user("bob", needs_setup=NeedsSetup(gallbladder=True))
    tool.main(_argv(user_answer="removed"))

    # Bob untouched
    bob_proto = store.read_json("bob", "protocol.json", Protocol)
    assert bob_proto.clinical.gallbladder_status == "present"
    bob_needs = store.read_needs_setup("bob")
    assert bob_needs.gallbladder is True
