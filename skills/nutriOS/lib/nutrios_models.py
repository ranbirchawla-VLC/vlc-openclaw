"""NutriOS v2 Pydantic models — single source of truth for all data contracts.

No I/O, no logic. Pure schema. All models use extra='forbid' so unknown fields
raise ValidationError at construction time (protects Tripwire 5).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


# ---------------------------------------------------------------------------
# Shared config
# ---------------------------------------------------------------------------

_strict = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Macro primitives
# ---------------------------------------------------------------------------

class MacroRange(BaseModel):
    model_config = _strict
    min: int | None = None
    max: int | None = None
    protected: bool = False


class DayMacros(BaseModel):
    model_config = _strict
    protein_g: MacroRange = Field(default_factory=MacroRange)
    carbs_g: MacroRange = Field(default_factory=MacroRange)
    fat_g: MacroRange = Field(default_factory=MacroRange)


# ---------------------------------------------------------------------------
# Mesocycle
# ---------------------------------------------------------------------------

class Mesocycle(BaseModel):
    model_config = _strict
    cycle_id: str
    phase: Literal["cut", "lean_bulk", "recomp", "maintenance"]
    label: str | None = None
    start_date: date
    end_date: date | None = None
    tdee_kcal: int | None = None   # null until setup; historical cycles stay null
    deficit_kcal: int = 0


# ---------------------------------------------------------------------------
# Goals and day patterns
# ---------------------------------------------------------------------------

class DayPattern(BaseModel):
    model_config = _strict
    day_type: str
    deficit_kcal: int | None = None
    protein_g: MacroRange = Field(default_factory=MacroRange)
    carbs_g: MacroRange = Field(default_factory=MacroRange)
    fat_g: MacroRange = Field(default_factory=MacroRange)


class Goals(BaseModel):
    model_config = _strict
    active_cycle_id: str
    weekly_schedule: dict[str, str]
    defaults: DayMacros = Field(default_factory=DayMacros)
    day_patterns: list[DayPattern] = []
    protected: dict[str, bool] = {}


# ---------------------------------------------------------------------------
# Resolution output (computed, never stored)
# ---------------------------------------------------------------------------

class ResolvedDay(BaseModel):
    model_config = _strict
    day_type: str
    kcal_target: int | None
    protein_g: MacroRange
    carbs_g: MacroRange
    fat_g: MacroRange
    tdee_kcal: int | None
    deficit_kcal: int


# ---------------------------------------------------------------------------
# Setup markers
# ---------------------------------------------------------------------------

class NeedsSetup(BaseModel):
    model_config = _strict
    gallbladder: bool = False
    tdee: bool = False
    carbs_shape: bool = False
    deficits: bool = False
    nominal_deficit: bool = False


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class Treatment(BaseModel):
    model_config = _strict
    medication: str
    brand: str
    dose_mg: float
    dose_day_of_week: str      # lowercase weekday name
    dose_time: str             # HH:MM local
    titration_notes: str | None = None
    next_transition_plan: str | None = None
    planned_stop_date: date | None = None
    restart_notes: str | None = None


class BiometricSnapshot(BaseModel):
    model_config = _strict
    start_date: date
    start_weight_lbs: float
    target_weight_lbs: float
    target_date: date | None = None
    long_term_goal: str | None = None
    lean_mass_lbs: float | None = None


class Clinical(BaseModel):
    model_config = _strict
    gallbladder_status: Literal["removed", "present", "unknown"] = "unknown"
    thyroid_medication: bool = False
    cgm_active: bool = False


class Protocol(BaseModel):
    model_config = _strict
    user_id: str
    treatment: Treatment
    biometrics: BiometricSnapshot
    clinical: Clinical
    protected: dict[str, bool] = Field(
        default_factory=lambda: {"dose_mg": True, "dose_day_of_week": True}
    )


# ---------------------------------------------------------------------------
# JSONL log entries (polymorphic, discriminated on 'kind')
# ---------------------------------------------------------------------------

class FoodLogEntry(BaseModel):
    model_config = _strict
    kind: Literal["food"] = "food"
    id: int
    ts_iso: str
    meal_slot: Literal["breakfast", "lunch", "dinner", "snack"]
    source: Literal["manual", "recipe", "alias"]
    name: str
    qty: float
    unit: str
    kcal: int
    protein_g: float
    carbs_g: float
    fat_g: float
    recipe_id: str | None = None
    supersedes: int | None = None


class DoseLogEntry(BaseModel):
    model_config = _strict
    kind: Literal["dose"] = "dose"
    id: int
    ts_iso: str
    dose_mg: float
    brand: str
    supersedes: int | None = None


LogEntry = Annotated[FoodLogEntry | DoseLogEntry, Field(discriminator="kind")]
LogEntryAdapter: TypeAdapter[FoodLogEntry | DoseLogEntry] = TypeAdapter(LogEntry)


# ---------------------------------------------------------------------------
# Weigh-ins, med notes, events
# ---------------------------------------------------------------------------

class WeighIn(BaseModel):
    model_config = _strict
    id: int
    ts_iso: str
    weight_lbs: float
    notes: str | None = None
    supersedes: int | None = None


class MedNote(BaseModel):
    model_config = _strict
    id: int
    ts_iso: str
    source: Literal["doctor", "dietitian", "nurse", "self", "other"] = "self"
    note: str
    supersedes: int | None = None


class Event(BaseModel):
    model_config = _strict
    id: int
    date: date
    title: str
    event_type: Literal[
        "surgery",
        "medication_change",
        "medication_stop",
        "medication_restart",
        "appointment",
        "milestone",
        "other",
    ]
    notes: str | None = None
    triggers: list[Literal[
        "prompt_new_mesocycle",
        "prompt_switch_day_pattern",
        "advisory_surgery_window",
    ]] = []


# ---------------------------------------------------------------------------
# State (counters)
# ---------------------------------------------------------------------------

class State(BaseModel):
    model_config = _strict
    last_entry_id: int = 0
    last_weigh_in_id: int = 0
    last_med_note_id: int = 0
    last_event_id: int = 0


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class Profile(BaseModel):
    model_config = _strict
    user_id: str
    tz: str
    units: str
    display: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Engine return types
# ---------------------------------------------------------------------------

class GateResult(BaseModel):
    model_config = _strict
    ok: bool
    reason: str | None
    applied: bool


class SetupStatus(BaseModel):
    model_config = _strict
    complete: bool
    next_marker: str | None
    markers_remaining: list[str]


class Flag(BaseModel):
    model_config = _strict
    code: str
    severity: Literal["info", "warn", "alert"]
    message: str


class Proximity(BaseModel):
    model_config = _strict
    macro: str
    end: Literal["min", "max"]
    distance_g: float


class WeightChange(BaseModel):
    model_config = _strict
    since_days: int
    delta_lbs: float
    current_lbs: float
    prior_lbs: float


class WeighInRow(BaseModel):
    model_config = _strict
    date: date
    weight_lbs: float
