"""nutrios_migrate.py — Phase 1 v1→v2 structural migrator.

Headless, deterministic, fixture-tested. Reads a v1 NutriOS data root, writes a
fresh v2 user tree under <dest>/users/<user_id>/, plus a markdown report at
<dest>/_migration_report_<timestamp>.md. Every transformation rule comes from
NutriOS_v2_Build_Brief_v2_Extension_v3.md Part 6.1.

Key disciplines:
- Tripwire 2: every JSONL write goes through nutrios_store.append_jsonl or
  write_jsonl_batch — both share the same temp+fsync+os.replace primitive.
- Tripwire 3: every timestamp comes from nutrios_time.parse (v1 dates) or
  nutrios_time.now() (migration marker). The stdlib clock calls are forbidden;
  the engine's frozen-time seam is the only path.
- Tripwire 4: every line in the migration report comes from a named template
  function in this module. Free-form f"..." composition is forbidden.
- Tripwire 5: _pending_kcal is migration scratch on raw goals.json, written
  via store.write_json_raw. It never enters the DayPattern Pydantic model
  (extra='forbid' would reject it).

Path safety: --force only ever rmtree's <dest>/users/<user_id>/ after
verifying the path's shape. Files outside the user dir are never touched.

CLI: python -m nutrios_migrate --source <v1_root> --dest <v2_root> --user-id <id> [--force]
Exit codes:
    0 — success, marker + report written
    1 — runtime failure during migration (partial writes possible)
    2 — re-run refused (marker present, --force not passed)
    3 — invalid arguments (paths missing/unreadable, user_id malformed)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# Allow `python -m nutrios_migrate ...` from anywhere by registering the lib dir
# on sys.path before importing siblings. Mirrors the convention the tools/
# entrypoints use; harmless when conftest already did the insert.
sys.path.insert(0, str(Path(__file__).parent))

from pydantic import BaseModel, ConfigDict, Field, ValidationError

import nutrios_store as store
import nutrios_time
from nutrios_models import (
    BiometricSnapshot, Clinical, DayMacros, DayPattern, Event, FoodLogEntry,
    DoseLogEntry, Goals, MacroRange, MedNote, Mesocycle, NeedsSetup, Profile,
    Protocol, Recipe, RecipeMacros, State, Treatment, WeighIn,
)


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------

class MigrationResult(BaseModel):
    """Structured outcome of a migrate() call. Used by tests; main() returns
    only the exit code."""
    model_config = ConfigDict(extra="forbid")
    success: bool
    exit_code: int
    user_dir: str
    report_path: str | None = None
    report_text: str | None = None
    counts_per_kind: dict[str, int] = Field(default_factory=dict)
    markers_set: list[str] = Field(default_factory=list)
    rule_fired: int | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# v1 input shapes — these are migration-only and never join nutrios_models.py
# ---------------------------------------------------------------------------

class _V1Treatment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    current_medication: str
    current_dose_mg: float
    brand: str
    dose_day_of_week: str
    dose_time: str
    titration_notes: str | None = None
    next_transition_plan: str | None = None
    planned_stop_date: date | None = None
    restart_notes: str | None = None


class _V1WeighIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: date
    weight_lbs: float
    notes: str | None = None


class _V1MedNote(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: date
    source: str | None = None
    note: str


class _V1Biometrics(BaseModel):
    model_config = ConfigDict(extra="ignore")
    start_date: date
    start_weight_lbs: float
    target_weight_lbs: float
    target_date: date | None = None
    long_term_goal: str | None = None
    lean_mass_lbs: float | None = None
    whoop_tdee_kcal: int | None = None
    weigh_ins: list[_V1WeighIn] = []


class _V1Protocol(BaseModel):
    model_config = ConfigDict(extra="ignore")
    treatment: _V1Treatment
    biometrics: _V1Biometrics
    med_team_notes: list[_V1MedNote] = []
    thyroid_medication: bool = False
    cgm_active: bool = False


class _V1DayPattern(BaseModel):
    model_config = ConfigDict(extra="ignore")
    day_type: str
    kcal: int
    carbs_g: int | None = None
    is_deficit_day: bool = False


class _V1Defaults(BaseModel):
    model_config = ConfigDict(extra="ignore")
    protein_g: int
    protein_protected: bool = False
    fat_g_maintenance: int = 65
    fat_g_deficit: int = 58
    fat_protected: bool = False


class _V1DayPatternsFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    defaults: _V1Defaults
    weekly_schedule: dict[str, str]
    day_patterns: list[_V1DayPattern]


class _V1Cycle(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cycle_id: str
    phase: str  # validated against v2 Mesocycle Literal at write time
    label: str | None = None
    start_date: date
    end_date: date | None = None


class _V1Event(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: date
    title: str
    event_type: str
    notes: str | None = None


class _V1LogEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    meal_slot: str
    source: str
    name: str
    qty: float
    unit: str
    kcal: int
    protein_g: float
    carbs_g: float
    fat_g: float


class _V1DailyLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: date
    entries: list[_V1LogEntry] = []
    dose_logged: bool = False
    water_count: int = 0
    day_notes: str = ""


# ---------------------------------------------------------------------------
# Discard / quarantine / report intermediate types
# ---------------------------------------------------------------------------

class _Discards(BaseModel):
    model_config = ConfigDict(extra="forbid")
    water_per_day: list[tuple[date, int]] = []
    nonempty_day_notes: list[tuple[date, str]] = []
    bak_files: list[str] = []


class _QuarantinedRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload: dict
    reason: str
    name: str


# Known event types come straight off the Event model; keep one source of truth
_KNOWN_EVENT_TYPES = frozenset({
    "surgery", "medication_change", "medication_stop", "medication_restart",
    "appointment", "milestone", "other",
})

_KNOWN_PHASES = frozenset({"cut", "lean_bulk", "recomp", "maintenance"})


# ---------------------------------------------------------------------------
# Tripwire 4 — every report line comes from one of these named templates.
# No free-form f"..." in the writer.
# ---------------------------------------------------------------------------

def _tpl_header(source: Path, dest: Path, user_id: str, now_iso: str, rule_fired: int) -> str:
    return (
        "# NutriOS Migration Report\n\n"
        f"**Source:** {source}\n"
        f"**Destination:** {dest}\n"
        f"**User ID:** {user_id}\n"
        f"**Run at:** {now_iso}\n"
        f"**TDEE/Deficit Rule Fired:** {rule_fired}\n"
    )


def _tpl_counts_section(clean: int, repaired: int, quarantined: int) -> str:
    return (
        "\n## Counts\n\n"
        f"- Migrated cleanly: {clean}\n"
        f"- Repaired (with rules): {repaired}\n"
        f"- Quarantined: {quarantined}\n"
    )


def _tpl_by_kind_table(rows: list[tuple[str, int, int, int]]) -> str:
    out = (
        "\n## By kind\n\n"
        "| Kind | Migrated | Repaired | Quarantined |\n"
        "|---|---|---|---|\n"
    )
    for kind, migrated, repaired, quarantined in rows:
        out += f"| {kind} | {migrated} | {repaired} | {quarantined} |\n"
    return out


def _tpl_discarded_section(d: _Discards) -> str:
    out = "\n## Discarded\n\n"
    water_total = sum(c for _, c in d.water_per_day)
    breakdown = ", ".join(f"{dt}={c}" for dt, c in d.water_per_day) if d.water_per_day else "—"
    out += f"- water_count: total {water_total} (per-day: {breakdown})\n"
    if d.nonempty_day_notes:
        out += "- day_notes (non-empty values surfaced verbatim):\n"
        for dt, txt in d.nonempty_day_notes:
            out += f"  - {dt}: {txt}\n"
    else:
        out += "- day_notes: none\n"
    out += f"- .bak files: {len(d.bak_files)} ({', '.join(d.bak_files) if d.bak_files else 'none'})\n"
    return out


def _tpl_markers_table(rows: list[tuple[str, str]]) -> str:
    out = (
        "\n## Markers set\n\n"
        "| Marker | Reason |\n"
        "|---|---|\n"
    )
    for marker, reason in rows:
        out += f"| {marker} | {reason} |\n"
    return out


def _tpl_warnings_section(
    synthesized_dose_count: int,
    synthesized_doses: list[tuple[date, str, float]],
    historical_null_tdee_cycles: list[str],
    extra_warnings: list[str],
) -> str:
    out = "\n## Warnings\n\n"
    if synthesized_doses:
        out += (
            f"- Historical dose lines synthesized from current protocol snapshot: "
            f"{synthesized_dose_count}\n"
        )
        for dt, brand, mg in synthesized_doses:
            out += f"  - {dt}: brand={brand}, dose_mg={mg}\n"
    else:
        out += "- Historical dose lines synthesized from current protocol snapshot: 0\n"
    if historical_null_tdee_cycles:
        out += "- Historical mesocycles with null TDEE (v1 did not carry historical TDEE; null preserved):\n"
        for cid in historical_null_tdee_cycles:
            out += f"  - {cid}\n"
    else:
        out += "- Historical mesocycles with null TDEE: none\n"
    for warning in extra_warnings:
        out += f"- {warning}\n"
    return out


def _tpl_tdee_resolution_section(
    rule: int,
    active_tdee: int | None,
    deficits: list[tuple[str, int | None]],
    nominal: int | None,
) -> str:
    out = (
        "\n## TDEE/Deficit Resolution\n\n"
        f"Rule fired: {rule}\n"
        "Resulting state:\n"
        f"- Active mesocycle TDEE: {active_tdee if active_tdee is not None else 'null'}\n"
    )
    if deficits and any(d is not None for _, d in deficits):
        out += "- Per-day-type deficits:\n"
        for day_type, d in deficits:
            out += f"  - {day_type}: {d if d is not None else 'deferred to Phase 2'}\n"
    else:
        out += "- Per-day-type deficits: deferred to Phase 2\n"
    out += f"- Nominal cycle deficit: {nominal if nominal is not None else 'deferred to Phase 2'}\n"
    return out


# Templated error/warning lines for return-path messages (Tripwire 4 again — no
# free-form f"..." inside the writer paths).

def _err_missing_v1_file(filename: str) -> str:
    return f"Missing required v1 file: {filename}"


def _err_invalid_v1_file(filename: str, detail: str) -> str:
    return f"v1 file {filename} failed validation: {detail}"


def _err_invalid_user_id(user_id: str) -> str:
    return f"Invalid user_id {user_id!r}: must match [A-Za-z0-9_-]+"


def _err_source_missing(source: Path) -> str:
    return f"Source path does not exist or is not readable: {source}"


def _err_dest_invalid(dest: Path) -> str:
    return f"Destination path is not writable or creatable: {dest}"


def _err_marker_present() -> str:
    return "User already migrated; use --force to rebuild"


def _err_source_equals_dest(path: Path) -> str:
    return f"--source and --dest must be different paths; both resolved to {path}"


def _warn_whoop_negative(value: int) -> str:
    return (
        f"v1 whoop_tdee_kcal had non-positive value {value}; treated as null "
        "for Rule 2 fallback. Confirm or correct via Phase 2 setup_resume."
    )


def _quarantine_reason_missing_macros() -> str:
    return "macros_per_serving missing; v2 requires cached per-serving macros."


# ---------------------------------------------------------------------------
# Path safety — validate user_id and the rmtree shape under --force
# ---------------------------------------------------------------------------

_VALID_USER_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_user_id(uid: str) -> None:
    if not uid or not _VALID_USER_ID.match(uid):
        raise ValueError(_err_invalid_user_id(uid))


def _scoped_user_dir_for_rm(dest: Path, user_id: str) -> Path:
    """Return <dest>/users/<user_id>/ after verifying its shape exactly.

    Defensive: even though _validate_user_id rejects path traversal, this
    additional check ensures the rmtree target is constructed from `dest`
    plus the literal "users" segment plus a clean uid.
    """
    _validate_user_id(user_id)
    dest_resolved = dest.resolve()
    target = (dest_resolved / "users" / user_id).resolve()
    if target.parent != (dest_resolved / "users").resolve():
        raise ValueError(f"Refusing rmtree: target shape unexpected: {target}")
    if target.name != user_id:
        raise ValueError(f"Refusing rmtree: target leaf {target.name!r} != user_id")
    if not str(target).startswith(str(dest_resolved)):
        raise ValueError(f"Refusing rmtree: target outside dest")
    return target


# ---------------------------------------------------------------------------
# v1 tree loader
# ---------------------------------------------------------------------------

class _V1Tree(BaseModel):
    """Loaded v1 inputs, validated against migration-internal Pydantic shapes."""
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    profile: dict
    protocol: _V1Protocol
    day_patterns: _V1DayPatternsFile
    active_cycle: _V1Cycle
    historical_cycles: list[_V1Cycle]
    events: list[_V1Event]
    recipes: list[dict]                       # validated per-recipe at transform
    daily_logs: list[_V1DailyLog]
    bak_files: list[str]
    file_count: int


def _load_v1_tree(source: Path) -> _V1Tree:
    """Read all v1 files into a structured tree. Raises ValueError with a
    templated message on missing required files or validation errors."""
    if not source.exists() or not source.is_dir():
        raise ValueError(_err_source_missing(source))

    file_count = 0
    bak_files: list[str] = []
    for f in source.rglob("*"):
        if f.is_file():
            file_count += 1
            if f.suffix == ".bak":
                bak_files.append(str(f.relative_to(source)))

    profile_path = source / "profile.json"
    protocol_path = source / "protocol.json"
    day_patterns_path = source / "day-patterns" / "active.json"
    cycles_dir = source / "cycles"
    cycles_active_path = cycles_dir / "active.json"
    events_path = source / "events.json"
    recipes_path = source / "recipes.json"
    logs_dir = source / "logs"

    for required in (profile_path, protocol_path, day_patterns_path, cycles_active_path):
        if not required.exists():
            raise ValueError(_err_missing_v1_file(str(required.relative_to(source))))

    try:
        profile = json.loads(profile_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(_err_invalid_v1_file("profile.json", str(exc))) from exc
    if "tz" not in profile:
        raise ValueError(_err_invalid_v1_file("profile.json", "missing tz"))

    try:
        protocol = _V1Protocol.model_validate_json(protocol_path.read_text())
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(_err_invalid_v1_file("protocol.json", str(exc))) from exc

    try:
        day_patterns = _V1DayPatternsFile.model_validate_json(day_patterns_path.read_text())
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(
            _err_invalid_v1_file("day-patterns/active.json", str(exc))
        ) from exc

    try:
        active_cycle = _V1Cycle.model_validate_json(cycles_active_path.read_text())
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(_err_invalid_v1_file("cycles/active.json", str(exc))) from exc

    historical_cycles: list[_V1Cycle] = []
    if cycles_dir.exists():
        for cf in sorted(cycles_dir.iterdir()):
            if cf.suffix != ".json" or cf.name == "active.json":
                continue
            try:
                historical_cycles.append(_V1Cycle.model_validate_json(cf.read_text()))
            except (json.JSONDecodeError, ValidationError) as exc:
                raise ValueError(
                    _err_invalid_v1_file(f"cycles/{cf.name}", str(exc))
                ) from exc

    events: list[_V1Event] = []
    if events_path.exists():
        try:
            raw = json.loads(events_path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(_err_invalid_v1_file("events.json", str(exc))) from exc
        items = raw["events"] if isinstance(raw, dict) and "events" in raw else raw
        if not isinstance(items, list):
            raise ValueError(_err_invalid_v1_file(
                "events.json", "expected list of events or wrapped {events: [...]}",
            ))
        for e in items:
            try:
                events.append(_V1Event.model_validate(e))
            except ValidationError as exc:
                raise ValueError(_err_invalid_v1_file("events.json", str(exc))) from exc

    recipes: list[dict] = []
    if recipes_path.exists():
        try:
            raw = json.loads(recipes_path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(_err_invalid_v1_file("recipes.json", str(exc))) from exc
        items = raw["recipes"] if isinstance(raw, dict) and "recipes" in raw else raw
        if not isinstance(items, list):
            raise ValueError(_err_invalid_v1_file(
                "recipes.json", "expected list of recipes or wrapped {recipes: [...]}",
            ))
        recipes = list(items)

    daily_logs: list[_V1DailyLog] = []
    if logs_dir.exists():
        for lf in sorted(logs_dir.iterdir()):
            if lf.suffix != ".json":
                continue
            try:
                daily_logs.append(_V1DailyLog.model_validate_json(lf.read_text()))
            except (json.JSONDecodeError, ValidationError) as exc:
                raise ValueError(_err_invalid_v1_file(f"logs/{lf.name}", str(exc))) from exc

    return _V1Tree(
        profile=profile,
        protocol=protocol,
        day_patterns=day_patterns,
        active_cycle=active_cycle,
        historical_cycles=historical_cycles,
        events=events,
        recipes=recipes,
        daily_logs=daily_logs,
        bak_files=bak_files,
        file_count=file_count,
    )


# ---------------------------------------------------------------------------
# Transformation helpers
# ---------------------------------------------------------------------------

def _ts_iso_noon_local(d: date, tz: str) -> str:
    """v1 weigh-in / med-note timestamp construction: date + 12:00 local → UTC ISO8601."""
    local_dt = datetime.combine(d, time(12, 0, 0), tzinfo=ZoneInfo(tz))
    return local_dt.astimezone(timezone.utc).isoformat()


def _ts_iso_at_local_time(d: date, hhmm: str, tz: str) -> str:
    """date + HH:MM local → UTC ISO8601. Used for synthesized dose lines."""
    h, m = hhmm.split(":")
    local_dt = datetime.combine(d, time(int(h), int(m), 0), tzinfo=ZoneInfo(tz))
    return local_dt.astimezone(timezone.utc).isoformat()


def _transform_protocol(v1p: _V1Protocol, user_id: str) -> Protocol:
    """Field renames + clinical defaulting + protected mirroring."""
    return Protocol(
        user_id=user_id,
        treatment=Treatment(
            medication=v1p.treatment.current_medication,
            brand=v1p.treatment.brand,
            dose_mg=v1p.treatment.current_dose_mg,
            dose_day_of_week=v1p.treatment.dose_day_of_week.lower(),
            dose_time=v1p.treatment.dose_time,
            titration_notes=v1p.treatment.titration_notes,
            next_transition_plan=v1p.treatment.next_transition_plan,
            planned_stop_date=v1p.treatment.planned_stop_date,
            restart_notes=v1p.treatment.restart_notes,
        ),
        biometrics=BiometricSnapshot(
            start_date=v1p.biometrics.start_date,
            start_weight_lbs=v1p.biometrics.start_weight_lbs,
            target_weight_lbs=v1p.biometrics.target_weight_lbs,
            target_date=v1p.biometrics.target_date,
            long_term_goal=v1p.biometrics.long_term_goal,
            lean_mass_lbs=v1p.biometrics.lean_mass_lbs,
        ),
        clinical=Clinical(
            gallbladder_status="unknown",
            thyroid_medication=v1p.thyroid_medication,
            cgm_active=v1p.cgm_active,
        ),
    )


def _transform_weigh_ins(v1p: _V1Protocol, tz: str) -> list[WeighIn]:
    out: list[WeighIn] = []
    for i, w in enumerate(v1p.biometrics.weigh_ins, start=1):
        out.append(WeighIn(
            id=i,
            ts_iso=_ts_iso_noon_local(w.date, tz),
            weight_lbs=w.weight_lbs,
            notes=w.notes,
        ))
    return out


def _transform_med_notes(v1p: _V1Protocol, tz: str) -> list[MedNote]:
    out: list[MedNote] = []
    for i, n in enumerate(v1p.med_team_notes, start=1):
        source = n.source if n.source in {"doctor", "dietitian", "nurse", "self", "other"} else "self"
        out.append(MedNote(
            id=i,
            ts_iso=_ts_iso_noon_local(n.date, tz),
            source=source,
            note=n.note,
        ))
    return out


def _transform_events(v1_events: list[_V1Event]) -> list[Event]:
    """Re-key with monotonic id, normalize event_type. Unknown → 'other' with
    original type appended to notes (delimiter '[original_type=...]' so the
    original is grep-recoverable).

    Notes-merge policy: when the original type is unknown, the original type
    string is APPENDED to existing notes with a leading '[original_type=foo]'
    marker. Documented here per spec request.
    """
    out: list[Event] = []
    for i, e in enumerate(v1_events, start=1):
        if e.event_type in _KNOWN_EVENT_TYPES:
            out.append(Event(
                id=i,
                date=e.date,
                title=e.title,
                event_type=e.event_type,
                notes=e.notes,
            ))
        else:
            tag = f"[original_type={e.event_type}]"
            merged_notes = (
                f"{tag} {e.notes}".strip() if e.notes
                else tag
            )
            out.append(Event(
                id=i,
                date=e.date,
                title=e.title,
                event_type="other",
                notes=merged_notes,
            ))
    return out


def _transform_daily_logs(
    daily_logs: list[_V1DailyLog],
    current_protocol: Protocol,
    tz: str,
) -> tuple[
    dict[date, list[FoodLogEntry | DoseLogEntry]],
    _Discards,
    list[tuple[date, str, float]],
    int,                             # last_entry_id (max id assigned)
]:
    """Build per-date JSONL lines, accumulate discards, track synthesized doses."""
    by_date: dict[date, list[FoodLogEntry | DoseLogEntry]] = {}
    discards = _Discards()
    synthesized_doses: list[tuple[date, str, float]] = []
    counter = 0

    for log in sorted(daily_logs, key=lambda d: d.date):
        lines: list[FoodLogEntry | DoseLogEntry] = []
        # Food entries: 'estimated' → 'manual', else pass through if a v2 source
        for entry in log.entries:
            counter += 1
            v1_source = entry.source
            v2_source = "manual" if v1_source == "estimated" else v1_source
            if v2_source not in {"manual", "recipe", "alias"}:
                v2_source = "manual"
            meal_slot = entry.meal_slot if entry.meal_slot in {"breakfast", "lunch", "dinner", "snack"} else "snack"
            lines.append(FoodLogEntry(
                id=counter,
                ts_iso=_ts_iso_at_local_time(log.date, "12:00", tz),
                meal_slot=meal_slot,
                source=v2_source,
                name=entry.name,
                qty=entry.qty,
                unit=entry.unit,
                kcal=entry.kcal,
                protein_g=entry.protein_g,
                carbs_g=entry.carbs_g,
                fat_g=entry.fat_g,
            ))
        # Dose synthesis: one DoseLogEntry per day where dose_logged was true
        if log.dose_logged:
            counter += 1
            ts = _ts_iso_at_local_time(
                log.date, current_protocol.treatment.dose_time, tz,
            )
            lines.append(DoseLogEntry(
                id=counter,
                ts_iso=ts,
                dose_mg=current_protocol.treatment.dose_mg,
                brand=current_protocol.treatment.brand,
            ))
            synthesized_doses.append(
                (log.date, current_protocol.treatment.brand, current_protocol.treatment.dose_mg),
            )

        # Discards
        if log.water_count:
            discards.water_per_day.append((log.date, log.water_count))
        if log.day_notes and log.day_notes.strip():
            discards.nonempty_day_notes.append((log.date, log.day_notes))

        if lines:
            by_date[log.date] = lines

    return by_date, discards, synthesized_doses, counter


def _transform_recipes(v1_recipes: list[dict]) -> tuple[list[Recipe], list[_QuarantinedRecipe], int]:
    """Pass through recipes whose payload validates against v2 Recipe.
    Quarantine those missing macros_per_serving.

    Returns (clean_recipes, quarantined, max_id_seen).
    """
    clean: list[Recipe] = []
    quarantined: list[_QuarantinedRecipe] = []
    max_id = 0
    for r in v1_recipes:
        rid = r.get("id", 0)
        max_id = max(max_id, rid if isinstance(rid, int) else 0)
        if "macros_per_serving" not in r:
            quarantined.append(_QuarantinedRecipe(
                payload=r,
                reason=_quarantine_reason_missing_macros(),
                name=r.get("name", f"recipe_{rid}"),
            ))
            continue
        try:
            clean.append(Recipe.model_validate(r))
        except ValidationError as exc:
            quarantined.append(_QuarantinedRecipe(
                payload=r,
                reason=str(exc),
                name=r.get("name", f"recipe_{rid}"),
            ))
    return clean, quarantined, max_id


def _build_goals_payload(
    v1_dp_file: _V1DayPatternsFile,
    active_cycle_id: str,
    rule: int,
    active_tdee: int | None,
) -> tuple[dict, list[tuple[str, int | None, int]]]:
    """Construct goals.json payload as a raw dict (Tripwire 5).

    For Rule 1: deficit_kcal computed per day_pattern.
    For Rule 2: deficit_kcal stays null; _pending_kcal carries v1 scalar kcal.

    Returns (goals_dict, day_pattern_summaries) where each summary is
    (day_type, deficit_or_None, v1_kcal).
    """
    defaults_d = v1_dp_file.defaults
    defaults_dict = {
        "protein_g": {
            "min": defaults_d.protein_g,
            "max": None,
            "protected": defaults_d.protein_protected,
        },
        "carbs_g": {"min": None, "max": None, "protected": False},
        "fat_g": {
            "min": None,
            "max": defaults_d.fat_g_maintenance,
            "protected": defaults_d.fat_protected,
        },
    }

    day_patterns_out: list[dict] = []
    summaries: list[tuple[str, int | None, int]] = []
    for dp in v1_dp_file.day_patterns:
        # Per-day-type fat override on deficit days
        fat_override = (
            {"min": None, "max": defaults_d.fat_g_deficit, "protected": defaults_d.fat_protected}
            if dp.is_deficit_day
            else {"min": None, "max": None, "protected": defaults_d.fat_protected}
        )
        carbs_override = (
            {"min": dp.carbs_g, "max": None, "protected": False}
            if dp.carbs_g is not None
            else {"min": None, "max": None, "protected": False}
        )
        deficit: int | None
        if rule == 1 and active_tdee is not None:
            deficit = active_tdee - dp.kcal
        else:
            deficit = None

        entry: dict[str, Any] = {
            "day_type": dp.day_type,
            "deficit_kcal": deficit,
            "protein_g": {"min": None, "max": None, "protected": False},
            "carbs_g": carbs_override,
            "fat_g": fat_override,
        }
        if rule == 2:
            # Tripwire 5: scratch field on raw goals dict only
            entry["_pending_kcal"] = dp.kcal

        day_patterns_out.append(entry)
        summaries.append((dp.day_type, deficit, dp.kcal))

    goals = {
        "active_cycle_id": active_cycle_id,
        "weekly_schedule": v1_dp_file.weekly_schedule,
        "defaults": defaults_dict,
        "day_patterns": day_patterns_out,
        "protected": {},
    }
    return goals, summaries


def _compute_nominal_deficit(
    summaries: list[tuple[str, int | None, int]],
    weekly_schedule: dict[str, str],
) -> int | None:
    """Most-common deficit across day types. Tie-break: pick the deficit of the
    most-common day type in weekly_schedule. Returns None when no deficits."""
    deficits = [d for _, d, _ in summaries if d is not None]
    if not deficits:
        return None
    counter = Counter(deficits)
    top = counter.most_common()
    if len(top) == 1 or top[0][1] > top[1][1]:
        return top[0][0]
    # Tie-break: most common day_type in weekly_schedule
    day_type_freq = Counter(weekly_schedule.values())
    by_type = {dt: d for dt, d, _ in summaries if d is not None}
    sorted_day_types = sorted(by_type, key=lambda dt: -day_type_freq.get(dt, 0))
    if sorted_day_types:
        return by_type[sorted_day_types[0]]
    return top[0][0]


def _transform_mesocycle(v1c: _V1Cycle, tdee_kcal: int | None, deficit_kcal: int) -> Mesocycle:
    phase = v1c.phase if v1c.phase in _KNOWN_PHASES else "cut"
    return Mesocycle(
        cycle_id=v1c.cycle_id,
        phase=phase,             # type: ignore[arg-type]
        label=v1c.label,
        start_date=v1c.start_date,
        end_date=v1c.end_date,
        tdee_kcal=tdee_kcal,
        deficit_kcal=deficit_kcal,
    )


# ---------------------------------------------------------------------------
# Idempotency marker
# ---------------------------------------------------------------------------

def _check_migration_marker(dest: Path, user_id: str) -> dict | None:
    """Return the parsed marker, or a sentinel dict if the marker is present
    but unreadable (corrupt JSON, IO error). None when no marker exists.

    A corrupt marker is treated as "present" — re-run is refused without
    --force. Without this, a partial / hand-edited / truncated marker would
    raise JSONDecodeError out of migrate(), violating the no-exceptions-escape
    contract. With --force the user dir is rmtree'd anyway, so a corrupt
    marker is a recoverable state.
    """
    p = dest / "users" / user_id / "_migration_marker.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {"_corrupt": True}


# ---------------------------------------------------------------------------
# Writer — atomic per file. Order: user dir, simple JSON, JSONL batches, marker.
# ---------------------------------------------------------------------------

def _write_v2_tree(
    user_id: str,
    profile: Profile,
    protocol: Protocol,
    goals_payload: dict,
    active_mesocycle: Mesocycle,
    historical_mesocycles: list[Mesocycle],
    weigh_ins: list[WeighIn],
    med_notes: list[MedNote],
    events: list[Event],
    recipes: list[Recipe],
    quarantined: list[_QuarantinedRecipe],
    daily_logs: dict[date, list[FoodLogEntry | DoseLogEntry]],
    needs_setup: NeedsSetup,
    state: State,
    dest_root: Path,
) -> int:
    """Write the v2 user tree. Returns count of files written."""
    files_written = 0
    udir = dest_root / "users" / user_id
    udir.mkdir(parents=True, exist_ok=True)

    store.write_json(user_id, "profile.json", profile);             files_written += 1
    store.write_json(user_id, "protocol.json", protocol);           files_written += 1
    store.write_json_raw(user_id, "goals.json", goals_payload);     files_written += 1
    store.write_json(user_id, "_needs_setup.json", needs_setup);    files_written += 1
    store.write_json(user_id, "state.json", state);                 files_written += 1

    store.write_json(user_id, f"mesocycles/{active_mesocycle.cycle_id}.json", active_mesocycle)
    files_written += 1
    for m in historical_mesocycles:
        store.write_json(user_id, f"mesocycles/{m.cycle_id}.json", m)
        files_written += 1

    store.write_events(user_id, events);   files_written += 1
    store.write_recipes(user_id, recipes); files_written += 1

    # JSONL batches via shared atomicity primitive (Tripwire 2)
    store.write_jsonl_batch(user_id, "weigh_ins.jsonl", weigh_ins); files_written += 1
    store.write_jsonl_batch(user_id, "med_notes.jsonl", med_notes); files_written += 1

    for d, lines in daily_logs.items():
        store.write_jsonl_batch(user_id, f"log/{d.isoformat()}.jsonl", lines)
        files_written += 1

    # Quarantined recipes — payload + sidecar reason. Slug disambiguated by id
    # so two v1 recipes whose names slugify identically don't collide. Writes
    # go through the same temp+fsync+replace primitive the rest of the writer
    # uses (Tripwire 2 atomicity at the file level extends here too).
    if quarantined:
        qdir = udir / "_quarantine" / "recipes"
        qdir.mkdir(parents=True, exist_ok=True)
        for q in quarantined:
            base = re.sub(r"[^A-Za-z0-9_-]+", "_", q.name).strip("_") or "recipe"
            rid = q.payload.get("id")
            slug = f"{base}_id{rid}" if rid is not None else base
            _atomic_write_local(qdir / f"{slug}.json", json.dumps(q.payload, indent=2))
            _atomic_write_local(qdir / f"{slug}.reason.txt", q.reason)
            files_written += 2

    return files_written


def _atomic_write_local(path: Path, content: str) -> None:
    """Atomic-write helper for non-allowlisted paths inside the user dir
    (quarantine sidecars). Mirrors store._atomic_write_text but is local to
    the migrator so the store's allowlist doesn't have to grow for one-off
    sidecar files. Same primitive: tempfile.mkstemp + fsync + os.replace.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _write_migration_marker(
    dest: Path,
    user_id: str,
    source_root: Path,
    counts_per_kind: dict[str, int],
    markers_set: list[str],
    v1_file_count: int,
    v2_file_count: int,
) -> None:
    marker = {
        "source_root": str(source_root.resolve()),
        "migrated_at_iso": nutrios_time.now().isoformat(),
        "v1_file_count": v1_file_count,
        "v2_file_count": v2_file_count,
        "counts_per_kind": counts_per_kind,
        "markers_set": markers_set,
    }
    store.write_json_raw(user_id, "_migration_marker.json", marker)


def _write_migration_report(dest: Path, body: str) -> Path:
    """Place the report at <dest>/_migration_report_<UTC YYYYMMDD_HHMMSS>.md.

    The dest root sits OUTSIDE the user dir, mirroring the spec — one report
    per migration run, regardless of user.
    """
    now = nutrios_time.now().astimezone(timezone.utc)
    stamp = now.strftime("%Y%m%d_%H%M%S")
    path = dest / f"_migration_report_{stamp}.md"
    path.write_text(body)
    return path


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def migrate(*, source: Path, dest: Path, user_id: str, force: bool = False) -> MigrationResult:
    """Run Phase 1 structural migration.

    All exit-code branches return a MigrationResult — no exceptions propagate
    out of this function for known failure modes. main() consults exit_code.
    """
    user_dir_str = str((dest / "users" / user_id))

    # 1. Argument validation (exit 3)
    try:
        _validate_user_id(user_id)
    except ValueError as exc:
        return MigrationResult(
            success=False, exit_code=3, user_dir=user_dir_str, error=str(exc),
        )
    if not source.exists() or not source.is_dir():
        return MigrationResult(
            success=False, exit_code=3, user_dir=user_dir_str,
            error=_err_source_missing(source),
        )
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return MigrationResult(
            success=False, exit_code=3, user_dir=user_dir_str,
            error=f"{_err_dest_invalid(dest)}: {exc}",
        )
    if source.resolve() == dest.resolve():
        return MigrationResult(
            success=False, exit_code=3, user_dir=user_dir_str,
            error=_err_source_equals_dest(source),
        )

    # 2. Idempotency check (exit 2 if marker present and not --force)
    existing = _check_migration_marker(dest, user_id)
    if existing is not None and not force:
        return MigrationResult(
            success=False, exit_code=2, user_dir=user_dir_str,
            error=_err_marker_present(),
        )
    if existing is not None and force:
        try:
            target = _scoped_user_dir_for_rm(dest, user_id)
        except ValueError as exc:
            return MigrationResult(
                success=False, exit_code=1, user_dir=user_dir_str, error=str(exc),
            )
        if target.exists():
            shutil.rmtree(target)

    # 3. Load v1 (exit 1 on validation failure)
    try:
        tree = _load_v1_tree(source)
    except ValueError as exc:
        return MigrationResult(
            success=False, exit_code=1, user_dir=user_dir_str, error=str(exc),
        )

    # 4. Pull tz from v1 profile; nutrios_store reads NUTRIOS_DATA_ROOT from
    # the env, so we point it at `dest` for the duration of the run and
    # restore the prior value in finally so in-process callers (orchestrator,
    # future Phase 2 invocation) don't have their env silently rewritten.
    tz = tree.profile["tz"]
    prior_root = os.environ.get("NUTRIOS_DATA_ROOT")
    os.environ["NUTRIOS_DATA_ROOT"] = str(dest)
    try:
        return _migrate_with_env(
            source=source, dest=dest, user_id=user_id, tree=tree, tz=tz,
            user_dir_str=user_dir_str,
        )
    finally:
        if prior_root is None:
            os.environ.pop("NUTRIOS_DATA_ROOT", None)
        else:
            os.environ["NUTRIOS_DATA_ROOT"] = prior_root


def _migrate_with_env(
    *,
    source: Path,
    dest: Path,
    user_id: str,
    tree: _V1Tree,
    tz: str,
    user_dir_str: str,
) -> MigrationResult:
    """Inner migration body. Runs with NUTRIOS_DATA_ROOT pointed at `dest`.
    Split out so the public migrate() can wrap the env mutation in try/finally
    while still returning a MigrationResult from any branch.
    """
    # 5. Determine TDEE rule. A negative whoop value falls into Rule 2 (the
    # spec covers null/zero; negatives are treated equivalently as "missing")
    # and a warning is recorded so the report surfaces the corruption.
    whoop = tree.protocol.biometrics.whoop_tdee_kcal
    rule_fired = 1 if (whoop is not None and whoop > 0) else 2
    active_tdee = whoop if rule_fired == 1 else None
    extra_warnings: list[str] = []
    if whoop is not None and whoop < 0:
        extra_warnings.append(_warn_whoop_negative(whoop))

    # 6. Transform
    profile = Profile(
        user_id=user_id,
        tz=tz,
        units=tree.profile.get("units", "lbs"),
        display=tree.profile.get("display", {}),
    )
    protocol = _transform_protocol(tree.protocol, user_id)

    goals_payload, day_summaries = _build_goals_payload(
        tree.day_patterns, tree.active_cycle.cycle_id, rule_fired, active_tdee,
    )
    nominal_deficit = (
        _compute_nominal_deficit(day_summaries, tree.day_patterns.weekly_schedule)
        if rule_fired == 1 else None
    )
    active_mesocycle = _transform_mesocycle(
        tree.active_cycle, active_tdee, nominal_deficit if nominal_deficit is not None else 0,
    )
    historical_mesocycles = [
        _transform_mesocycle(c, None, 0) for c in tree.historical_cycles
    ]

    weigh_ins = _transform_weigh_ins(tree.protocol, tz)
    med_notes = _transform_med_notes(tree.protocol, tz)
    events = _transform_events(tree.events)
    recipes_clean, quarantined, max_recipe_id = _transform_recipes(tree.recipes)
    daily_logs, discards, synthesized_doses, last_entry_id = _transform_daily_logs(
        tree.daily_logs, protocol, tz,
    )
    discards.bak_files = list(tree.bak_files)

    # 7. Markers
    needs_setup = NeedsSetup(
        gallbladder=True,
        tdee=(rule_fired == 2),
        carbs_shape=True,
        deficits=True,
        nominal_deficit=True,
    )
    markers_set: list[str] = [m for m, on in needs_setup.model_dump().items() if on]

    # 8. State counters
    state = State(
        last_entry_id=last_entry_id,
        last_weigh_in_id=len(weigh_ins),
        last_med_note_id=len(med_notes),
        last_event_id=len(events),
        last_recipe_id=max_recipe_id,
    )

    # 9. Write — partial failure rolls the user dir back so the next run can
    # start fresh without --force. Without this, a half-written tree with no
    # marker would cause the next run to silently proceed on top of partial files.
    counts_per_kind = {
        "weigh_ins": len(weigh_ins),
        "med_notes": len(med_notes),
        "events": len(events),
        "log_entries": last_entry_id,
        "recipes": len(recipes_clean),
    }
    try:
        v2_file_count = _write_v2_tree(
            user_id=user_id,
            profile=profile,
            protocol=protocol,
            goals_payload=goals_payload,
            active_mesocycle=active_mesocycle,
            historical_mesocycles=historical_mesocycles,
            weigh_ins=weigh_ins,
            med_notes=med_notes,
            events=events,
            recipes=recipes_clean,
            quarantined=quarantined,
            daily_logs=daily_logs,
            needs_setup=needs_setup,
            state=state,
            dest_root=dest,
        )
    except (OSError, ValidationError, ValueError) as exc:
        _rollback_partial_user_dir(dest, user_id)
        return MigrationResult(
            success=False, exit_code=1, user_dir=user_dir_str,
            error=f"write failed: {exc}",
        )

    # 10. Marker (separate from tree — a write-success witness)
    _write_migration_marker(
        dest=dest, user_id=user_id, source_root=source,
        counts_per_kind=counts_per_kind, markers_set=markers_set,
        v1_file_count=tree.file_count, v2_file_count=v2_file_count + 1,
    )

    # 11. Report — assembled from named templates only (Tripwire 4)
    report = _build_report(
        source=source,
        dest=dest,
        user_id=user_id,
        rule_fired=rule_fired,
        active_tdee=active_tdee,
        nominal=nominal_deficit,
        day_summaries=day_summaries,
        weigh_ins=weigh_ins,
        med_notes=med_notes,
        events=events,
        recipes_clean=recipes_clean,
        quarantined=quarantined,
        log_entry_count=last_entry_id,
        discards=discards,
        synthesized_doses=synthesized_doses,
        historical_null_tdee_cycles=[m.cycle_id for m in historical_mesocycles],
        markers_set=markers_set,
        extra_warnings=extra_warnings,
    )
    report_path = _write_migration_report(dest, report)

    return MigrationResult(
        success=True,
        exit_code=0,
        user_dir=user_dir_str,
        report_path=str(report_path),
        report_text=report,
        counts_per_kind=counts_per_kind,
        markers_set=markers_set,
        rule_fired=rule_fired,
    )


def _rollback_partial_user_dir(dest: Path, user_id: str) -> None:
    """Best-effort cleanup of a partially-written user dir after a write
    failure. Uses _scoped_user_dir_for_rm so the path-shape check still
    fires; if that check fails we silently swallow — the original write
    error is the operator-facing message and shouldn't be obscured."""
    try:
        target = _scoped_user_dir_for_rm(dest, user_id)
        if target.exists():
            shutil.rmtree(target)
    except (ValueError, OSError):
        pass


# ---------------------------------------------------------------------------
# Report assembly — pure composition of templated sections
# ---------------------------------------------------------------------------

_MARKER_REASONS = {
    "gallbladder": "v1 had no field; default \"unknown\" set, marker raised for user confirmation.",
    "tdee": "v1 whoop_tdee_kcal was null/zero; active mesocycle TDEE deferred to Phase 2.",
    "carbs_shape": "v1 carbs migrated as min-only; user confirms shape (min/max/both) in Phase 2.",
    "deficits": "Per-day-type deficits require user confirmation in Phase 2.",
    "nominal_deficit": "Cycle-level nominal deficit requires user confirmation in Phase 2.",
}


def _build_report(*,
    source: Path,
    dest: Path,
    user_id: str,
    rule_fired: int,
    active_tdee: int | None,
    nominal: int | None,
    day_summaries: list[tuple[str, int | None, int]],
    weigh_ins: list[WeighIn],
    med_notes: list[MedNote],
    events: list[Event],
    recipes_clean: list[Recipe],
    quarantined: list[_QuarantinedRecipe],
    log_entry_count: int,
    discards: _Discards,
    synthesized_doses: list[tuple[date, str, float]],
    historical_null_tdee_cycles: list[str],
    markers_set: list[str],
    extra_warnings: list[str],
) -> str:
    now_iso = nutrios_time.now().isoformat()
    clean_total = (
        len(weigh_ins) + len(med_notes) + len(events)
        + log_entry_count + len(recipes_clean)
    )
    repaired_total = 0  # No repair rules fire in this pass — would-be repairs
                        # all fall through to quarantine. Section is present
                        # for shape compatibility with future repair rules.
    quarantined_total = len(quarantined)
    by_kind_rows = [
        ("weigh_ins", len(weigh_ins), 0, 0),
        ("med_notes", len(med_notes), 0, 0),
        ("events", len(events), 0, 0),
        ("log_entries", log_entry_count, 0, 0),
        ("recipes", len(recipes_clean), 0, len(quarantined)),
    ]
    marker_rows = [(m, _MARKER_REASONS[m]) for m in markers_set]
    deficit_table = [(dt, d) for dt, d, _ in day_summaries]

    return (
        _tpl_header(source.resolve(), dest.resolve(), user_id, now_iso, rule_fired)
        + _tpl_counts_section(clean_total, repaired_total, quarantined_total)
        + _tpl_by_kind_table(by_kind_rows)
        + _tpl_discarded_section(discards)
        + _tpl_markers_table(marker_rows)
        + _tpl_warnings_section(
            len(synthesized_doses), synthesized_doses, historical_null_tdee_cycles,
            extra_warnings,
        )
        + _tpl_tdee_resolution_section(rule_fired, active_tdee, deficit_table, nominal)
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns the exit code; tests can call this directly.

    The script's __main__ block calls sys.exit(main()) so the exit code lands
    on the OS. main() itself does not call sys.exit so test runners can drive it.
    """
    parser = argparse.ArgumentParser(prog="nutrios_migrate")
    parser.add_argument("--source", required=True)
    parser.add_argument("--dest", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    result = migrate(
        source=Path(args.source),
        dest=Path(args.dest),
        user_id=args.user_id,
        force=args.force,
    )
    if result.exit_code == 0 and result.report_path is not None:
        print(result.report_path)
    elif result.error:
        print(result.error, file=sys.stderr)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
