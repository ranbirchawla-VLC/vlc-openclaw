"""Tests for nutrios_log — locked recipe contract from D1."""
import json
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from nutrios_models import (
    FoodLogEntry, Recipe, RecipeMacros, ToolResult, State,
)
import nutrios_store as store
import nutrios_log as tool


# Fixed Friday afternoon UTC; America/Denver still on the same calendar day.
_NOW = datetime(2026, 4, 24, 18, 0, 0, tzinfo=timezone.utc)
_TZ = "America/Denver"
_LOCAL_DATE = _NOW.astimezone(ZoneInfo(_TZ)).date()
_LOG_FILE = f"log/{_LOCAL_DATE}.jsonl"


def _argv(**kwargs) -> str:
    payload = {
        "user_id": "alice",
        "now": _NOW.isoformat(),
        "tz": _TZ,
    }
    payload.update(kwargs)
    return json.dumps(payload, default=str)


def _r(name: str, kcal=500, p=40.0, c=50.0, f=15.0, removed=False) -> Recipe:
    return Recipe(
        id=1, name=name, servings=1,
        macros_per_serving=RecipeMacros(kcal=kcal, protein_g=p, carbs_g=c, fat_g=f),
        removed=removed,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_log_rejects_missing_user_id(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(json.dumps({
            "name": "x", "now": _NOW.isoformat(), "tz": _TZ,
        }))


def test_log_rejects_extra_field(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(_argv(name="x", bogus=1))


# ---------------------------------------------------------------------------
# Step 2: qty missing → followup
# ---------------------------------------------------------------------------

def test_log_qty_missing_returns_quantity_clarify(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(name="chicken breast"))
    assert isinstance(result, ToolResult)
    assert result.needs_followup is True
    assert result.display_text == "How much chicken breast?"


# ---------------------------------------------------------------------------
# Step 3: alias resolution (case-insensitive)
# ---------------------------------------------------------------------------

def test_log_alias_resolves_to_recipe(tmp_data_root, setup_user):
    setup_user("alice")
    # Alias "shake" → "Protein Shake" (recipe name)
    aliases_path = tmp_data_root / "users" / "alice" / "aliases.json"
    aliases_path.write_text(json.dumps({"version": 1, "aliases": {"shake": "Protein Shake"}}))
    store.write_recipes("alice", [_r("Protein Shake")])

    result = tool.main(_argv(name="shake", qty=2, unit="serving"))
    assert isinstance(result, ToolResult)
    # Recipe path: kcal = 2 * 500 = 1000
    assert "Protein Shake" in result.display_text
    assert "1000" in result.display_text
    # No recipe_save_eligible flag on recipe path
    assert "recipe_save_eligible" not in (result.state_delta or {})


def test_log_alias_legacy_flat_format(tmp_data_root, setup_user):
    """Aliases.json may exist in raw-dict format from prior workspaces."""
    setup_user("alice")
    aliases_path = tmp_data_root / "users" / "alice" / "aliases.json"
    aliases_path.write_text(json.dumps({"shake": "Protein Shake"}))
    store.write_recipes("alice", [_r("Protein Shake")])

    result = tool.main(_argv(name="Shake", qty=1))  # case-insensitive match too
    assert "Protein Shake" in result.display_text


# ---------------------------------------------------------------------------
# Step 4: recipe path
# ---------------------------------------------------------------------------

def test_log_recipe_match_uses_expand_recipe(tmp_data_root, setup_user):
    setup_user("alice")
    store.write_recipes("alice", [_r("oats", kcal=400, p=12.0, c=70.0, f=6.0)])

    result = tool.main(_argv(name="oats", qty=1.5))
    assert "oats" in result.display_text
    # 400 * 1.5 = 600
    assert "600 kcal" in result.display_text
    # NO recipe_save_eligible flag — this is a recipe log
    assert (result.state_delta or {}).get("recipe_save_eligible") is None


def test_log_recipe_appends_entry_with_recipe_id(tmp_data_root, setup_user):
    setup_user("alice")
    store.write_recipes("alice", [_r("oats")])
    tool.main(_argv(name="oats", qty=1))

    raw = store.tail_jsonl("alice", _LOG_FILE, 10)
    assert len(raw) == 1
    assert raw[0]["source"] == "recipe"
    assert raw[0]["recipe_id"] == "1"
    assert raw[0]["name"] == "oats"


def test_log_recipe_skips_removed_recipe(tmp_data_root, setup_user):
    """A removed recipe must not match — falls through to manual path."""
    setup_user("alice")
    store.write_recipes("alice", [_r("oats", removed=True)])

    # Without macros, manual path returns followup
    result = tool.main(_argv(name="oats", qty=1))
    assert result.needs_followup is True
    assert "macros" in result.display_text.lower() or "kcal" in result.display_text.lower()


# ---------------------------------------------------------------------------
# Step 5: manual path
# ---------------------------------------------------------------------------

def test_log_manual_missing_macros_returns_followup(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(name="dragonfruit smoothie", qty=200, unit="ml"))
    assert result.needs_followup is True
    # Renderer mentions macros
    text_lower = result.display_text.lower()
    assert "kcal" in text_lower
    assert "protein" in text_lower


def test_log_manual_partial_macros_returns_followup(tmp_data_root, setup_user):
    """Even one missing macro → followup; all four required."""
    setup_user("alice")
    result = tool.main(_argv(
        name="x", qty=100, unit="g", kcal=200, protein_g=10, carbs_g=20,
        # fat_g missing
    ))
    assert result.needs_followup is True


def test_log_manual_full_macros_succeeds_with_recipe_save_eligible(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(
        name="chicken breast", qty=150, unit="g",
        kcal=248, protein_g=46.5, carbs_g=0, fat_g=5.4,
    ))
    assert result.needs_followup is False
    assert "Logged: chicken breast" in result.display_text
    assert "248 kcal" in result.display_text
    # Manual path SETS recipe_save_eligible
    assert result.state_delta["recipe_save_eligible"] is True
    assert result.state_delta["last_entry_id"] == 1


def test_log_manual_appends_entry_with_source_manual(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(
        name="apple", qty=1, unit="ea",
        kcal=95, protein_g=0.5, carbs_g=25, fat_g=0.3,
    ))
    raw = store.tail_jsonl("alice", _LOG_FILE, 10)
    assert len(raw) == 1
    assert raw[0]["source"] == "manual"
    assert raw[0]["recipe_id"] is None
    assert raw[0]["name"] == "apple"


# ---------------------------------------------------------------------------
# Counter behavior
# ---------------------------------------------------------------------------

def test_log_consecutive_entries_increment_counter(tmp_data_root, setup_user):
    setup_user("alice")
    store.write_recipes("alice", [_r("oats")])
    r1 = tool.main(_argv(name="oats", qty=1))
    r2 = tool.main(_argv(name="oats", qty=1))
    r3 = tool.main(_argv(name="oats", qty=1))
    assert r1.state_delta["last_entry_id"] == 1
    assert r2.state_delta["last_entry_id"] == 2
    assert r3.state_delta["last_entry_id"] == 3


# ---------------------------------------------------------------------------
# TZ-aware date routing
# ---------------------------------------------------------------------------

def test_log_uses_local_date_for_log_file(tmp_data_root, setup_user):
    """UTC 2026-04-25T03:00Z is local Denver 2026-04-24 21:00 — log file
    must use local date 2026-04-24, not UTC date 2026-04-25."""
    setup_user("alice")
    store.write_recipes("alice", [_r("oats")])

    late_utc = datetime(2026, 4, 25, 3, 0, 0, tzinfo=timezone.utc)
    late_argv = json.dumps({
        "user_id": "alice", "now": late_utc.isoformat(), "tz": _TZ,
        "name": "oats", "qty": 1,
    })
    tool.main(late_argv)

    # Local 2026-04-24 file should have the entry
    local_log = f"log/{date(2026, 4, 24)}.jsonl"
    assert len(store.tail_jsonl("alice", local_log, 10)) == 1


def test_log_meal_slot_from_now(tmp_data_root, setup_user):
    """meal_slot is derived from local hour."""
    setup_user("alice")
    store.write_recipes("alice", [_r("oats")])

    # 18:00 UTC = 12:00 MDT → "lunch"
    tool.main(_argv(name="oats", qty=1))
    raw = store.tail_jsonl("alice", _LOG_FILE, 10)
    assert raw[0]["meal_slot"] == "lunch"


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------

def test_log_isolation(tmp_data_root, setup_user):
    setup_user("alice")
    setup_user("bob")
    tool.main(_argv(
        name="apple", qty=1, unit="ea",
        kcal=95, protein_g=0.5, carbs_g=25, fat_g=0.3,
    ))
    # Bob's log untouched
    bob_log = store.tail_jsonl("bob", _LOG_FILE, 10)
    assert bob_log == []
