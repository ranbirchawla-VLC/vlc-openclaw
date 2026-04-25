"""Tests for nutrios_recipe — full lifecycle: save/update/list/get/delete."""
import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from nutrios_models import Recipe, RecipeMacros, ToolResult
import nutrios_store as store
import nutrios_recipe as tool


_NOW = datetime(2026, 4, 24, 18, 0, 0, tzinfo=timezone.utc)
_TZ = "America/Denver"


def _argv(**kwargs) -> str:
    payload = {"user_id": "alice", "now": _NOW.isoformat(), "tz": _TZ}
    payload.update(kwargs)
    return json.dumps(payload, default=str)


def _macros(kcal=500, p=40.0, c=50.0, f=15.0) -> dict:
    return {"kcal": kcal, "protein_g": p, "carbs_g": c, "fat_g": f}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_recipe_rejects_unknown_action(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(_argv(action="bogus"))


def test_recipe_rejects_extra_field(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(_argv(action="list", bogus=1))


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------

def test_recipe_save_happy_path(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(
        action="save", name="protein shake", macros_per_serving=_macros(),
        ingredients=["50g whey", "200ml milk"],
    ))
    assert "saved" in result.display_text.lower()
    assert "protein shake" in result.display_text
    assert result.state_delta["last_recipe_id"] == 1

    recipes = store.read_recipes("alice")
    assert len(recipes) == 1
    assert recipes[0].name == "protein shake"
    assert recipes[0].ingredients == ["50g whey", "200ml milk"]


def test_recipe_save_duplicate_name_case_insensitive_rejected(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(action="save", name="Protein Shake", macros_per_serving=_macros()))
    result = tool.main(_argv(action="save", name="protein shake", macros_per_serving=_macros()))
    assert "already exists" in result.display_text.lower()
    # Disk has only one recipe
    assert len(store.read_recipes("alice")) == 1


def test_recipe_save_after_delete_allows_name_reuse(tmp_data_root, setup_user):
    """Deleted recipes are removed=True; their names can be reused for new actives."""
    setup_user("alice")
    tool.main(_argv(action="save", name="oats", macros_per_serving=_macros()))
    tool.main(_argv(action="delete", id=1))
    # Name "oats" now belongs to a removed recipe; saving a fresh "oats" must succeed
    result = tool.main(_argv(action="save", name="oats", macros_per_serving=_macros(kcal=400)))
    assert "saved" in result.display_text.lower()
    # Two recipes on disk: one removed, one active
    recipes = store.read_recipes("alice")
    assert len(recipes) == 2
    actives = [r for r in recipes if not r.removed]
    assert len(actives) == 1
    assert actives[0].macros_per_serving.kcal == 400


def test_recipe_save_missing_macros_raises(tmp_data_root, setup_user):
    setup_user("alice")
    with pytest.raises(ValueError):
        tool.main(_argv(action="save", name="oats"))


def test_recipe_save_consecutive_increments_counter(tmp_data_root, setup_user):
    setup_user("alice")
    r1 = tool.main(_argv(action="save", name="a", macros_per_serving=_macros()))
    r2 = tool.main(_argv(action="save", name="b", macros_per_serving=_macros()))
    assert r1.state_delta["last_recipe_id"] == 1
    assert r2.state_delta["last_recipe_id"] == 2


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------

def test_recipe_update_by_id(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(action="save", name="oats", macros_per_serving=_macros(kcal=300)))
    result = tool.main(_argv(
        action="update", id=1, macros_per_serving=_macros(kcal=350),
    ))
    assert "updated" in result.display_text.lower()
    recipes = store.read_recipes("alice")
    assert recipes[0].macros_per_serving.kcal == 350


def test_recipe_update_by_name(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(action="save", name="oats", macros_per_serving=_macros(kcal=300)))
    tool.main(_argv(
        action="update", name="oats", macros_per_serving=_macros(kcal=400),
    ))
    recipes = store.read_recipes("alice")
    assert recipes[0].macros_per_serving.kcal == 400


def test_recipe_update_replaces_ingredients_when_provided(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(
        action="save", name="oats", macros_per_serving=_macros(),
        ingredients=["original"],
    ))
    tool.main(_argv(
        action="update", id=1, macros_per_serving=_macros(),
        ingredients=["new", "list"],
    ))
    recipes = store.read_recipes("alice")
    assert recipes[0].ingredients == ["new", "list"]


def test_recipe_update_keeps_ingredients_when_omitted(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(
        action="save", name="oats", macros_per_serving=_macros(),
        ingredients=["keep"],
    ))
    tool.main(_argv(action="update", id=1, macros_per_serving=_macros(kcal=999)))
    recipes = store.read_recipes("alice")
    assert recipes[0].ingredients == ["keep"]


def test_recipe_update_not_found_returns_supersedes_error(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(action="update", id=99, macros_per_serving=_macros()))
    assert "doesn't exist" in result.display_text or "does not exist" in result.display_text
    assert "recipe" in result.display_text.lower()


def test_recipe_update_missing_macros_raises(tmp_data_root, setup_user):
    setup_user("alice")
    with pytest.raises(ValueError):
        tool.main(_argv(action="update", id=1))


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def test_recipe_list_empty(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(action="list"))
    assert result.display_text == "No recipes saved."


def test_recipe_list_active(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(action="save", name="protein shake", macros_per_serving=_macros()))
    tool.main(_argv(action="save", name="oats", macros_per_serving=_macros()))
    result = tool.main(_argv(action="list"))
    assert "protein shake" in result.display_text
    assert "oats" in result.display_text


def test_recipe_list_query_filter(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(action="save", name="protein shake", macros_per_serving=_macros()))
    tool.main(_argv(action="save", name="oats", macros_per_serving=_macros()))
    result = tool.main(_argv(action="list", query="oat"))
    assert "oats" in result.display_text
    assert "protein shake" not in result.display_text


def test_recipe_list_filters_removed(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(action="save", name="kept", macros_per_serving=_macros()))
    tool.main(_argv(action="save", name="trashed", macros_per_serving=_macros()))
    tool.main(_argv(action="delete", id=2))
    result = tool.main(_argv(action="list"))
    assert "kept" in result.display_text
    assert "trashed" not in result.display_text


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

def test_recipe_get_by_id(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(
        action="save", name="protein shake", macros_per_serving=_macros(),
        ingredients=["whey", "milk"],
    ))
    result = tool.main(_argv(action="get", id=1))
    assert "protein shake" in result.display_text
    assert "whey" in result.display_text
    assert "500" in result.display_text


def test_recipe_get_by_name(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(action="save", name="oats", macros_per_serving=_macros()))
    result = tool.main(_argv(action="get", name="oats"))
    assert "oats" in result.display_text


def test_recipe_get_not_found(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(action="get", id=999))
    assert "doesn't exist" in result.display_text or "does not exist" in result.display_text


def test_recipe_get_missing_id_and_name_raises(tmp_data_root, setup_user):
    setup_user("alice")
    with pytest.raises(ValueError):
        tool.main(_argv(action="get"))


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_recipe_delete_flips_removed_flag(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(action="save", name="oats", macros_per_serving=_macros()))
    result = tool.main(_argv(action="delete", id=1))
    assert "deleted" in result.display_text.lower()
    recipes = store.read_recipes("alice")
    assert recipes[0].removed is True


def test_recipe_delete_idempotent(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(action="save", name="oats", macros_per_serving=_macros()))
    tool.main(_argv(action="delete", id=1))
    result = tool.main(_argv(action="delete", id=1))  # second
    assert "deleted" in result.display_text.lower()


def test_recipe_delete_not_found(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(action="delete", id=99))
    assert "doesn't exist" in result.display_text or "does not exist" in result.display_text


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------

def test_recipe_isolation(tmp_data_root, setup_user):
    setup_user("alice")
    setup_user("bob")
    tool.main(_argv(action="save", name="alice-recipe", macros_per_serving=_macros()))
    assert store.read_recipes("bob") == []


# ---------------------------------------------------------------------------
# Soft-delete bug fix — id lookup must skip removed for get/update
# ---------------------------------------------------------------------------

def test_recipe_get_by_id_skips_removed(tmp_data_root, setup_user):
    """A removed recipe must NOT be viewable via id lookup — that would let
    the user see soft-deleted content as if active."""
    setup_user("alice")
    tool.main(_argv(action="save", name="oats", macros_per_serving=_macros()))
    tool.main(_argv(action="delete", id=1))
    result = tool.main(_argv(action="get", id=1))
    # Expect not-found, NOT a render of the removed recipe's details
    assert "doesn't exist" in result.display_text or "does not exist" in result.display_text
    assert "oats" not in result.display_text or "deleted" in result.display_text.lower()


def test_recipe_update_by_id_skips_removed(tmp_data_root, setup_user):
    """Updating a removed recipe by id must fail — silent mutation of
    soft-deleted state would create a 'ghost' updated removed recipe."""
    setup_user("alice")
    tool.main(_argv(action="save", name="oats", macros_per_serving=_macros(kcal=300)))
    tool.main(_argv(action="delete", id=1))
    result = tool.main(_argv(
        action="update", id=1, macros_per_serving=_macros(kcal=999),
    ))
    assert "doesn't exist" in result.display_text or "does not exist" in result.display_text

    # Disk: the removed recipe still has its original macros (300), not 999
    recipes = store.read_recipes("alice")
    assert recipes[0].macros_per_serving.kcal == 300
    assert recipes[0].removed is True


def test_recipe_update_by_id_does_not_resurrect_removed(tmp_data_root, setup_user):
    """Combined with name-reuse-after-delete: updating the removed by id
    must not silently re-surface it via a different code path."""
    setup_user("alice")
    tool.main(_argv(action="save", name="oats", macros_per_serving=_macros(kcal=300)))
    tool.main(_argv(action="delete", id=1))
    # Save a fresh active "oats" — id=2
    tool.main(_argv(action="save", name="oats", macros_per_serving=_macros(kcal=400)))
    # Try to update the OLD removed one by its id; must reject
    result = tool.main(_argv(
        action="update", id=1, macros_per_serving=_macros(kcal=999),
    ))
    assert "doesn't exist" in result.display_text or "does not exist" in result.display_text

    recipes = store.read_recipes("alice")
    # Two recipes: one removed (oats, 300 kcal), one active (oats, 400 kcal)
    removed_one = next(r for r in recipes if r.removed)
    active_one = next(r for r in recipes if not r.removed)
    assert removed_one.macros_per_serving.kcal == 300  # unchanged by attempted update
    assert active_one.macros_per_serving.kcal == 400


def test_recipe_delete_idempotent_still_works_after_fix(tmp_data_root, setup_user):
    """The include_removed=True escape hatch keeps _delete idempotent:
    re-removing returns the same confirm even though _find_by_id_or_name
    now defaults to active-only."""
    setup_user("alice")
    tool.main(_argv(action="save", name="oats", macros_per_serving=_macros()))
    tool.main(_argv(action="delete", id=1))
    result = tool.main(_argv(action="delete", id=1))  # second remove
    assert "deleted" in result.display_text.lower()
