"""Fixture-under-test verification.

The conftest.py setup_user helper is shared infrastructure across every tool
test file. A bug in the fixture is a bug in every dependent test. These tests
verify the fixture itself: tree shape, model validity, and per-user isolation.
"""
import json

import pytest

from nutrios_models import (
    Goals, Mesocycle, NeedsSetup, Profile, Protocol, State,
)


def test_setup_user_produces_valid_tree(tmp_data_root, setup_user):
    """Every file written by setup_user must exist and parse against its model."""
    result = setup_user("alice")

    user_dir = tmp_data_root / "users" / "alice"
    assert user_dir.exists()

    # Each file must exist on disk and parse cleanly into its Pydantic model
    profile = Profile.model_validate_json((user_dir / "profile.json").read_text())
    assert profile.user_id == "alice"

    goals = Goals.model_validate_json((user_dir / "goals.json").read_text())
    assert goals.active_cycle_id == result["mesocycle"].cycle_id

    mesocycle_path = user_dir / "mesocycles" / f"{goals.active_cycle_id}.json"
    mesocycle = Mesocycle.model_validate_json(mesocycle_path.read_text())
    assert mesocycle.tdee_kcal is not None  # default-complete user has TDEE set

    protocol = Protocol.model_validate_json((user_dir / "protocol.json").read_text())
    assert protocol.user_id == "alice"
    assert protocol.protected.get("dose_mg") is True

    needs_setup = NeedsSetup.model_validate_json(
        (user_dir / "_needs_setup.json").read_text()
    )
    # Default fixture user is setup-complete (all markers False)
    assert needs_setup.gallbladder is False
    assert needs_setup.tdee is False
    assert needs_setup.carbs_shape is False
    assert needs_setup.deficits is False
    assert needs_setup.nominal_deficit is False

    state = State.model_validate_json((user_dir / "state.json").read_text())
    # Counters all zero on a fresh tree
    assert state.last_entry_id == 0
    assert state.last_weigh_in_id == 0
    assert state.last_med_note_id == 0
    assert state.last_event_id == 0


def test_setup_user_isolation(tmp_data_root, setup_user):
    """Two users' trees must be independent — write to one, the other is unaffected."""
    setup_user("alice")
    setup_user("bob")

    alice_dir = tmp_data_root / "users" / "alice"
    bob_dir = tmp_data_root / "users" / "bob"
    assert alice_dir.exists()
    assert bob_dir.exists()
    assert alice_dir != bob_dir

    # Mutate alice's profile via direct file write
    alice_profile_path = alice_dir / "profile.json"
    alice_data = json.loads(alice_profile_path.read_text())
    alice_data["tz"] = "Europe/London"
    alice_profile_path.write_text(json.dumps(alice_data))

    # Bob's profile must be unchanged
    bob_profile = Profile.model_validate_json((bob_dir / "profile.json").read_text())
    assert bob_profile.tz != "Europe/London"

    # Alice's profile reflects the mutation
    alice_profile = Profile.model_validate_json(alice_profile_path.read_text())
    assert alice_profile.tz == "Europe/London"


def test_setup_user_accepts_needs_setup_override(tmp_data_root, setup_user):
    """Caller can pass a NeedsSetup instance to scaffold an in-progress-setup user."""
    pending = NeedsSetup(tdee=True, deficits=True, nominal_deficit=True)
    setup_user("carol", needs_setup=pending)

    user_dir = tmp_data_root / "users" / "carol"
    needs_setup = NeedsSetup.model_validate_json(
        (user_dir / "_needs_setup.json").read_text()
    )
    assert needs_setup.tdee is True
    assert needs_setup.deficits is True
    assert needs_setup.nominal_deficit is True
    assert needs_setup.gallbladder is False  # not set in override
