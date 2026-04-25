"""Shared test fixtures for nutrios test suite.

Loaded automatically by pytest for every test in this directory and below.
Fixtures provided:
    tmp_data_root  — pytest tmp_path with NUTRIOS_DATA_ROOT pointed at it.
    setup_user     — callable that scaffolds a minimal valid v2 user tree.

The sys.path.insert below is the single place where the lib directory is
registered. Existing per-file inserts in test_nutrios_*.py become harmless
no-ops once the path is already present.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make lib/ importable for every test in this tree
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from datetime import date

import pytest

from nutrios_models import (
    BiometricSnapshot, Clinical, DayMacros, DayPattern, Goals, MacroRange,
    Mesocycle, NeedsSetup, Profile, Protocol, State, Treatment,
)
import nutrios_store as store


@pytest.fixture
def tmp_data_root(monkeypatch, tmp_path):
    """Set NUTRIOS_DATA_ROOT to a per-test temp dir; return the Path."""
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def setup_user(tmp_data_root):
    """Return a callable that scaffolds a minimal valid v2 tree for a user.

    Defaults model a fully-set-up cut-cycle user: TDEE 2600, 500 deficit,
    Tirzepatide on Thursdays, gallbladder present, all _needs_setup markers
    cleared. Override via kwargs to model in-progress setup states.

    Returns a dict of the constructed Pydantic models for assertion convenience.
    """
    def _setup(
        user_id: str,
        *,
        tz: str = "America/Denver",
        cycle_id: str = "cycle1",
        tdee_kcal: int | None = 2600,
        deficit_kcal: int = 500,
        dose_day_of_week: str = "thursday",
        needs_setup: NeedsSetup | None = None,
    ) -> dict:
        profile = Profile(user_id=user_id, tz=tz, units="lbs", display={})

        mesocycle = Mesocycle(
            cycle_id=cycle_id,
            phase="cut",
            start_date=date(2026, 1, 1),
            tdee_kcal=tdee_kcal,
            deficit_kcal=deficit_kcal,
        )

        goals = Goals(
            active_cycle_id=cycle_id,
            weekly_schedule={
                "monday": "rest", "tuesday": "training", "wednesday": "rest",
                "thursday": "training", "friday": "rest", "saturday": "training",
                "sunday": "rest",
            },
            defaults=DayMacros(
                protein_g=MacroRange(min=175, protected=True),
                fat_g=MacroRange(max=65, protected=True),
            ),
            day_patterns=[
                DayPattern(day_type="rest", carbs_g=MacroRange(min=180)),
                DayPattern(day_type="training", carbs_g=MacroRange(min=220)),
            ],
        )

        protocol = Protocol(
            user_id=user_id,
            treatment=Treatment(
                medication="Tirzepatide",
                brand="Mounjaro",
                dose_mg=10.0,
                dose_day_of_week=dose_day_of_week,
                dose_time="07:00",
            ),
            biometrics=BiometricSnapshot(
                start_date=date(2026, 1, 1),
                start_weight_lbs=220.0,
                target_weight_lbs=180.0,
            ),
            clinical=Clinical(gallbladder_status="present"),
        )

        marker_state = needs_setup if needs_setup is not None else NeedsSetup()
        state = State()

        store.write_json(user_id, "profile.json", profile)
        store.write_json(user_id, f"mesocycles/{cycle_id}.json", mesocycle)
        store.write_json(user_id, "goals.json", goals)
        store.write_json(user_id, "protocol.json", protocol)
        store.write_json(user_id, "_needs_setup.json", marker_state)
        store.write_json(user_id, "state.json", state)

        return {
            "profile": profile,
            "mesocycle": mesocycle,
            "goals": goals,
            "protocol": protocol,
            "needs_setup": marker_state,
            "state": state,
        }

    return _setup
