# NutriOS v2 — Build Brief Extension

Prepared: 2026-04-24
Owner: Ranbir Chawla
Status: Extension to `NutriOS_v2_Build_Brief_v2.md`. Read the base brief first; this document only describes additions and revisions.

---

## Purpose of this extension

The base brief scopes v2 to food logging, macro tracking, and mesocycle management. v1 carries five additional capabilities: treatment protocol, biometrics and weigh-ins, med team notes, dose logging, and event tracking. This extension brings those capabilities forward into v2 so migration has a defined home for every v1 data point and no live feature is dropped at cutover.

The extension also introduces three modeling generalizations that came from scoping this work:

1. **Macro min/max ranges.** Individual users have different clinical shapes — some need a protein floor, some a carb or fat ceiling, some both. v2 represents each macro as a range with optional `min` and `max` rather than a single scalar target. Replaces the v1 single-value target and subsumes the fat-ceiling rule.
2. **Derived kcal.** Kcal stays a scalar at the UI boundary but is derived from `tdee - deficit` rather than hand-authored per day type. Makes mesocycle transitions a one-line edit and preserves historical cycle accuracy.
3. **Structural migration with guided setup resume.** Migration runs headless with sane defaults, writes `_needs_setup` markers on fields that require human judgment, and exits deterministically. First post-migration bot interaction detects markers and walks a guided setup flow. Separates structural transformation (testable in isolation) from human input (resumable, interactive).

Architectural posture is unchanged. Python owns math and time. LLM owns intent classification and one framing sentence. State files are the contract. The orchestrator prefix stays byte-stable so prompt caching holds.

One v1 feature is explicitly dropped: water logging. v1 daily `water_count` is discarded during migration and the water intent is removed from the turn contract.

---

## Part 1 — Scope additions

### Functional additions

- Log weigh-ins and show weight trend.
- Track treatment protocol (medication, dose, dose day and time, titration and stop plans) with protected-default gating on dose changes.
- Log medication doses against the current day with dose-day awareness.
- Log med team notes as an append-only series.
- Maintain a small events list (surgery dates, medication changes, etc.) and surface upcoming events in daily summaries and on the day-of.
- Compute advisory flags from protocol + events (surgery-window posture, range-proximity warnings) and return them as pre-rendered strings from Python.
- Express macro goals as min/max ranges with optional ends, resolved at render time against the current day pattern.
- Derive daily kcal target from cycle TDEE minus day-type deficit.
- Detect incomplete state via `_needs_setup` markers and route to a guided setup resume flow.

### Non-functional additions

- Append-only weigh-ins and med notes use the same JSONL discipline as food logs. No read-then-write-full-array.
- Advisory flags are computed deterministically in `nutrios_engine` and rendered in `nutrios_render`. The LLM never authors a flag.
- Protected-default gating extends to `protocol.dose_mg`, `protocol.dose_day_of_week`, and any protected MacroRange end.
- MacroRange resolution and kcal derivation are pure engine functions; the LLM never performs either.
- Migration is headless and deterministic. No interactive prompts during the transformation itself.
- Setup resume is field-driven: any `_needs_setup.*` marker blocks non-essential intents until cleared.

### Execution additions

- Polymorphic daily JSONL: `kind ∈ {food, dose}` on every line. Food keeps existing shape. Dose carries minimal fields.
- Engine filters by `kind` when computing food totals vs. dose status.
- Migration maps v1's `dose_logged: true` to a single synthesized dose line per day (not a timestamped duplicate of the original logging moment).
- `resolve_day` returns a `ResolvedDay` with `kcal_target=None` when TDEE is unset; renderer surfaces "setup needed" instead of a number. Food logging continues to work; only target comparison is deferred.

---

## Part 2 — Data contract additions

All additions go under `$NUTRIOS_DATA_ROOT/users/{user_id}/`.

### Directory layout (delta only)

```
$NUTRIOS_DATA_ROOT/
  users/
    {user_id}/
      profile.json           # unchanged — tz, units, display prefs
      protocol.json          # NEW — treatment + biometric snapshot
      goals.json             # REVISED — macro ranges + weekly schedule + defaults
      recipes.json           # unchanged
      aliases.json           # unchanged
      portions.json          # unchanged
      events.json            # NEW
      weigh_ins.jsonl        # NEW — append-only
      med_notes.jsonl        # NEW — append-only
      log/
        YYYY-MM-DD.jsonl     # extended: mixed kinds (food, dose)
      mesocycles/
        {cycle_id}.json      # REVISED — carries tdee_kcal and deficit_kcal
      state.json             # extended: adds last_weigh_in_id, last_med_note_id, last_event_id
      _needs_setup.json      # NEW — field-level setup markers
      _migration_marker.json # NEW — idempotency marker written by migrator
```

User isolation is unchanged: every path is built from `users/{user_id}/...`, and the channel-peer to user_id mapping in `_index/users.json` is the only gate. Mesocycles live inside the user directory and are never global.

### Pydantic models

**MacroRange** (the new primitive used for all macros):

```python
class MacroRange(BaseModel):
    min: int | None = None
    max: int | None = None
    protected: bool = False
```

Either end may be null. `protected=true` gates both ends — changing min or max requires the confirmation phrase.

**DayMacros** (applied in both Goals defaults and DayPattern overrides):

```python
class DayMacros(BaseModel):
    protein_g: MacroRange = MacroRange()
    carbs_g: MacroRange = MacroRange()
    fat_g: MacroRange = MacroRange()
```

Kcal is not a MacroRange. It is a scalar target, derived.

**Mesocycle** (user-scoped by path; never global):

```python
class Mesocycle(BaseModel):
    cycle_id: str
    phase: Literal["cut", "lean_bulk", "recomp", "maintenance"]
    label: str | None = None
    start_date: date
    end_date: date | None = None
    tdee_kcal: int | None = None           # null until setup completes; active cycle must be non-null to render targets
    deficit_kcal: int = 0                  # nominal daily deficit; day_types can override
```

Historical mesocycles preserve their own TDEE. Cycle transitions update TDEE on the new cycle only; past cycles stay intact.

**DayPattern** (per-day-type overrides):

```python
class DayPattern(BaseModel):
    day_type: str                          # free-form key: "training", "rest", "post_dose", etc.
    deficit_kcal: int | None = None        # null = inherit mesocycle.deficit_kcal
    protein_g: MacroRange = MacroRange()   # sparse — only fields this day overrides
    carbs_g: MacroRange = MacroRange()
    fat_g: MacroRange = MacroRange()
```

Sparse overrides. A null range end inherits from `Goals.defaults`. A null `deficit_kcal` inherits from the cycle.

**Revised Goals**:

```python
class Goals(BaseModel):
    active_cycle_id: str                   # points at mesocycles/{cycle_id}.json
    weekly_schedule: dict[str, str]        # "monday" -> "rest", "tuesday" -> "training"
    defaults: DayMacros                    # always-on ranges, e.g. protein.min=175
    day_patterns: list[DayPattern] = []
    protected: dict[str, bool] = {}        # optional: per-path protection flags
```

`defaults` replaces the base brief's top-level macro scalars. `protected` here is for edge cases; `MacroRange.protected` is the normal route.

**Resolution** (pure engine function, not stored):

```python
class ResolvedDay(BaseModel):
    day_type: str
    kcal_target: int | None                # None when mesocycle.tdee_kcal is null
    protein_g: MacroRange                  # merged: pattern over defaults
    carbs_g: MacroRange
    fat_g: MacroRange
    tdee_kcal: int | None                  # surfaced for transparency
    deficit_kcal: int                      # surfaced for transparency

def resolve_day(now, goals, mesocycle) -> ResolvedDay:
    dow_key = weekday_name(now)
    day_type = goals.weekly_schedule[dow_key]
    pattern = find_pattern(goals.day_patterns, day_type)
    effective_deficit = pattern.deficit_kcal if pattern and pattern.deficit_kcal is not None \
                        else mesocycle.deficit_kcal
    kcal_target = (mesocycle.tdee_kcal - effective_deficit) if mesocycle.tdee_kcal is not None else None
    return ResolvedDay(
        day_type=day_type,
        kcal_target=kcal_target,
        protein_g=merge_range(goals.defaults.protein_g, pattern.protein_g if pattern else None),
        carbs_g=merge_range(goals.defaults.carbs_g, pattern.carbs_g if pattern else None),
        fat_g=merge_range(goals.defaults.fat_g, pattern.fat_g if pattern else None),
        tdee_kcal=mesocycle.tdee_kcal,
        deficit_kcal=effective_deficit,
    )
```

`merge_range` takes defaults and an optional pattern override; if either end is non-null on the pattern, it wins. Both ends on the pattern produce a fully-overridden range.

**NeedsSetup** (new — the setup resume driver):

```python
class NeedsSetup(BaseModel):
    """
    Field-level markers written by the migrator (or setup wizard) when a field
    requires human judgment that cannot be supplied deterministically.
    Each marker is cleared when the setup resume flow writes the corresponding field.
    """
    gallbladder: bool = False              # protocol.clinical.gallbladder_status = "unknown"
    tdee: bool = False                     # active mesocycle.tdee_kcal is null
    carbs_shape: bool = False              # carbs_g migrated as min-only; user must confirm min/max/both
    deficits: bool = False                 # per-day-type deficit_kcal needs confirmation
    nominal_deficit: bool = False          # cycle-level deficit_kcal needs confirmation
```

All fields default `false`. Migrator sets `true` on fields that land as defaults rather than user input. Setup resume flow checks this file every turn until all markers are cleared.

**Protocol** (treatment + slow-changing biometric snapshot):

```python
class Treatment(BaseModel):
    medication: str
    brand: str
    dose_mg: float                         # protected
    dose_day_of_week: str                  # protected; lowercase
    dose_time: str                         # HH:MM local
    titration_notes: str | None = None
    next_transition_plan: str | None = None
    planned_stop_date: date | None = None
    restart_notes: str | None = None

class BiometricSnapshot(BaseModel):
    start_date: date
    start_weight_lbs: float
    target_weight_lbs: float
    target_date: date | None = None
    long_term_goal: str | None = None
    lean_mass_lbs: float | None = None

class Clinical(BaseModel):
    gallbladder_status: Literal["removed", "present", "unknown"] = "unknown"
    thyroid_medication: bool = False
    cgm_active: bool = False

class Protocol(BaseModel):
    user_id: str
    treatment: Treatment
    biometrics: BiometricSnapshot
    clinical: Clinical
    protected: dict[str, bool] = {"dose_mg": True, "dose_day_of_week": True}
```

Current weight is not stored. `nutrios_engine.current_weight()` reads the last line of `weigh_ins.jsonl`. `whoop_tdee_kcal` does not live on protocol in the revised model — TDEE is now a mesocycle field.

**WeighIn**:

```python
class WeighIn(BaseModel):
    id: int
    ts_iso: str                            # UTC ISO8601
    weight_lbs: float
    notes: str | None = None
    supersedes: int | None = None
```

**MedNote**:

```python
class MedNote(BaseModel):
    id: int
    ts_iso: str
    source: Literal["doctor", "dietitian", "nurse", "self", "other"] = "self"
    note: str
    supersedes: int | None = None
```

**Event**:

```python
class Event(BaseModel):
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
```

**Extended LogEntry** (polymorphic):

```python
class FoodLogEntry(BaseModel):
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
    kind: Literal["dose"] = "dose"
    id: int
    ts_iso: str
    dose_mg: float                         # snapshot of protocol.treatment.dose_mg at log time
    brand: str                             # snapshot
    supersedes: int | None = None

LogEntry = Annotated[FoodLogEntry | DoseLogEntry, Field(discriminator="kind")]
```

**Extended State**:

```python
class State(BaseModel):
    last_entry_id: int = 0
    last_weigh_in_id: int = 0
    last_med_note_id: int = 0
    last_event_id: int = 0
```

---

## Part 3 — Module additions

### `nutrios_engine.py` — additions

Pure functions, no I/O. Time source always passed in.

Macro and kcal:

- `merge_range(default: MacroRange, override: MacroRange | None) -> MacroRange`
- `resolve_day(now, goals, mesocycle) -> ResolvedDay`
- `macro_range_check(actual: float, r: MacroRange) -> Literal["LOW", "OK", "OVER", "UNSET"]`
- `range_proximity(actual, r: MacroRange, threshold_pct: float = 0.2) -> Proximity | None` — structured hint when actual is within threshold of an active bound; used for progress-bar-equivalent warnings.

Protocol and weight:

- `current_weight(weigh_ins: list[WeighIn]) -> float | None`
- `weight_change(weigh_ins, since_days: int = 7) -> WeightChange`
- `weight_trend(weigh_ins, last_n: int = 5) -> list[WeighInRow]`

Dose and events:

- `event_next(events, now, n: int = 2) -> list[Event]`
- `event_today(events, now) -> Event | None`
- `dose_reminder_due(protocol, today_log_entries, now) -> bool`
- `dose_status(today_log_entries) -> Literal["logged", "pending", "not_due"]`

Advisory, protection, and setup:

- `advisory_flags(protocol, events, mesocycle, now) -> list[Flag]`
- `protected_gate_protocol(current, proposed, confirm_phrase) -> GateResult`
- `protected_gate_range(current: MacroRange, proposed: MacroRange, confirm_phrase) -> GateResult`
- `setup_status(needs_setup: NeedsSetup) -> SetupStatus` — returns `{complete: bool, next_marker: str | None, markers_remaining: list[str]}`. Next marker is determined by fixed order (see Part 6.5).

Fat-ceiling as a named function does not exist in v2. Its behavior is covered by `macro_range_check(actual, goals.defaults.fat_g)` returning `OVER` when daily total exceeds `fat_g.max`, and by `range_proximity` returning a hint when a single meal would push close.

### `nutrios_store.py` — additions

- `append_jsonl(user_id, filename, model)` — atomic JSONL append for weigh-ins, med notes, daily logs.
- `tail_jsonl(user_id, filename, n)` — bounded read.
- `read_events(user_id)` / `write_events(user_id, events)`
- `next_id(user_id, counter: str) -> int` — atomic increment in `state.json`. Covers all four counters.
- `read_needs_setup(user_id) -> NeedsSetup` — returns a default (all false) if file is missing.
- `clear_needs_setup_marker(user_id, field: str)` — sets a single marker to false. Atomic write.

### `nutrios_render.py` — additions

All returns are Telegram plain text. Numbers are formatted here, never in the LLM.

- `render_macro_line(name: str, actual: float, r: MacroRange, status)` — adapts to which ends are set:
  - Min only: `Protein:   148g / min 175g   LOW`
  - Max only: `Fat:        42g / max 65g    OK`
  - Both set: `Carbs:     180g / 150–200g   OK`
  - Unset: line is suppressed
- `render_kcal_line(actual, target, tdee, deficit)` — surfaces derivation compactly when space allows, target-only when terse. Renders `"Calories: setup needed"` when `target is None`.
- `render_weigh_in_confirm(weigh_in, change, progress)`
- `render_weight_trend(rows, rate_per_week)`
- `render_dose_confirm(dose_entry)`
- `render_dose_not_due(next_dose_day, next_dose_date)`
- `render_med_note_confirm(note)`
- `render_protocol_view(protocol, recent_notes)`
- `render_event_added(event)`
- `render_event_trigger(event)` — prepended to response when today matches an event date.
- `render_advisory(flags)` — prepended to summary and weigh-in confirm.
- `render_setup_resume_prompt(marker: str, context: dict) -> str` — one renderer per marker (gallbladder, tdee, carbs_shape, deficits, nominal_deficit). Pulls context from already-loaded state so the prompt is specific (e.g. computed deficit suggestions).
- `render_setup_complete() -> str` — one-time confirmation when the last marker clears.
- Revised `render_daily_summary` — uses resolved day, range-aware macro lines, dose status, upcoming event proximity (≤14 days), advisory flags.

### `nutrios_time.py` — no additions

Existing surface covers all new features.

---

## Part 4 — Turn contract additions

Base brief's six-step turn contract is unchanged. Intent set expands to twelve:

```
log | summary | goals | setup | clarify | smalltalk
  | weigh_in | dose | med_note | event | weight_trend | protocol_edit | setup_resume
```

### Context pass extensions

The orchestrator's silent context load is extended with:

- `needs_setup = read_needs_setup(user_id)`
- `setup_status = engine.setup_status(needs_setup)`
- `protocol = read_protocol(user_id)`
- `mesocycle = read_mesocycle(user_id, goals.active_cycle_id)`
- `resolved = engine.resolve_day(now, goals, mesocycle)` — every turn uses this.
- `events = read_events(user_id)`
- `event_today = engine.event_today(events, now)`
- `dose_due = engine.dose_reminder_due(protocol, today_log_entries, now)`
- `advisory = engine.advisory_flags(protocol, events, mesocycle, now)`

All deterministic engine calls on already-loaded state.

### Setup gate

If `setup_status.complete is False`, the orchestrator enforces a setup gate:

- **Allowed intents:** `setup_resume`, `log` (food entry, logs without target comparison), `weigh_in`, `smalltalk`.
- **Blocked intents:** `summary`, `goals`, `dose`, `med_note`, `event`, `weight_trend`, `protocol_edit`, `setup` (the original, pre-migration setup). Blocked intents respond with a short renderer output: "Setup isn't finished. Next: [marker question]. Answer to continue."
- Any allowed intent that runs while `setup_status.complete is False` appends a one-line prompt at the end: "Still need: [marker]. Type 'setup' to continue." Non-intrusive but visible.

When the user types anything matching the setup_resume classification (including just "setup"), orchestrator routes to the `setup_resume` intent regardless of other signals in the message.

### Tool routing

New Python tool entrypoints, single-JSON-argv contract:

- `nutrios_weigh_in.py` — add, edit via `supersedes`.
- `nutrios_dose.py` — logs dose for today; rejects with rendered message if not dose day; snapshots `dose_mg` and `brand`.
- `nutrios_med_note.py` — append; `protocol_view` sub-action returns protocol + last 3 notes.
- `nutrios_event.py` — add, list upcoming, remove.
- `nutrios_protocol_edit.py` — gated edits via `protected_gate_protocol`.
- `nutrios_setup_resume.py` — reads next marker, accepts one answer, validates, writes through the appropriate gated tool path, clears the marker. Returns `{display_text, needs_followup, marker_cleared, next_marker}`.

Existing `nutrios_read`, `nutrios_write`, `nutrios_log` keep roles; `nutrios_log` gains dose-kind awareness when reading mixed JSONL. Goal edits that touch a protected MacroRange route through `protected_gate_range` before the write.

---

## Part 5 — Prompt layout additions

Target unchanged: each prompt under 60 lines, orchestrator free of user-specific data.

- `prompts/orchestrator.md` — router covers 12 intents. Enforces the setup gate (blocked intents return a renderer string, no LLM reasoning). No rules, no formulas.
- `prompts/module-weigh-in.md` — phrasing for weigh-in confirm and weight trend.
- `prompts/module-dose.md` — phrasing for dose confirmation, dose-day-gate messaging, protected-change confirmation phrase.
- `prompts/module-events.md` — phrasing for event add and event trigger day-of surfacing.
- `prompts/module-protocol.md` — phrasing for protocol view and med note capture.
- `prompts/module-setup-resume.md` — phrasing for the five setup markers. Each marker has a canonical prompt and a canonical confirmation. No math, no validation — engine and tool handle both. Structure: "We still need X. [Context-specific prompt.] Reply with [format]."

Revised: `prompts/module-goals.md` covers range edits (min/max separately), TDEE edits, deficit edits, protected-gate confirmation phrasing. `prompts/module-setup.md` is retired — its role is split between the migrator (structural defaults) and `module-setup-resume.md` (human input). Historical reference only; not loaded at runtime.

---

## Part 6 — Migration and setup resume

Migration has two phases with hard separation:

- **Phase 1 — Structural transformation (headless).** Deterministic, testable in isolation, no human input. Writes v2 files, writes `_needs_setup.json`, writes `_migration_marker.json`, produces report. Exits.
- **Phase 2 — Setup resume (guided flow).** Runs on first post-migration bot interaction. Walks markers in fixed order, one at a time, through the standard turn contract.

### Part 6.1 — Phase 1: Structural transformation

Runs via `python -m nutrios_migrate --source <v1_root> --dest <v2_root> --user-id <id>`. Headless.

### v1-to-v2 data mapping

| v1 source | v2 destination | Transformation | Sets marker? |
|---|---|---|---|
| `protocol.json.treatment.*` | `protocol.json.treatment.*` | Field renames: `current_medication` → `medication`, `current_dose_mg` → `dose_mg`. | — |
| `protocol.json.biometrics.start_*, target_*, long_term_goal, lean_mass_lbs, start_date` | `protocol.json.biometrics.*` | Direct. | — |
| `protocol.json.biometrics.current_weight_lbs` | discarded (derived) | Recoverable from last weigh-in. | — |
| `protocol.json.biometrics.whoop_tdee_kcal` | `mesocycles/{active_cycle_id}.json.tdee_kcal` | If non-null and > 0 in v1, carried forward and marker NOT set. If null/zero, field stays null and `_needs_setup.tdee = true`. | conditional |
| `protocol.json.biometrics.weigh_ins[]` | `weigh_ins.jsonl` | Monotonic `id` in source order. `ts_iso` from `date` + noon local + TZ → UTC. | — |
| `protocol.json.med_team_notes[]` | `med_notes.jsonl` | Monotonic `id`. `ts_iso` from `date` + noon local. `source` defaults `"self"`. | — |
| `protocol.json.thyroid_medication`, `cgm_active` | `protocol.json.clinical.*` | Direct. | — |
| gallbladder_status (new, no v1 field) | `protocol.json.clinical.gallbladder_status = "unknown"` | Default. | `gallbladder = true` |
| `day-patterns/active.json` + `day-patterns/[phase]-NN.json` | `goals.json.defaults` + `goals.json.day_patterns[]` + `goals.json.weekly_schedule` | See range-shape rules below. | — |
| `day-patterns/*.defaults.protein_g` + `protected: true` | `goals.defaults.protein_g.min` = v1 value; `protected = true`; `max = null` | v1 protein was a floor. | — |
| v1 fat rule (65 maintenance / 58 deficit) | `goals.defaults.fat_g.max = 65`; deficit-day pattern override sets `fat_g.max = 58` | Ceiling becomes a max. Protected mirrors v1. | — |
| v1 carbs per day type | `goals.day_patterns[*].carbs_g.min = v1_value, max = null` | Min-only default (less-dangerous shape). | `carbs_shape = true` |
| `cycles/active.json` + `cycles/[cycle]-NN.json` | `mesocycles/{cycle_id}.json` | Cycle fields carry. TDEE and deficit behavior per TDEE/deficit rules below. | — |
| v1 kcal per day type | computed `deficit_kcal` (if TDEE is known) OR stored as `_pending_kcal` hint OR skipped | See rules below. | `deficits = true`, `nominal_deficit = true` |
| `events.json.events[]` | `events.json.events[]` | Re-keyed with `id` + normalized `event_type`. Unknown types map to `"other"` with original string preserved in `notes`. | — |
| `logs/YYYY-MM-DD.json.entries[]` | `log/YYYY-MM-DD.jsonl` food lines | `source: "estimated"` → `"manual"`. | — |
| `logs/YYYY-MM-DD.json.dose_logged: true` | one dose line | `ts_iso` from date + protocol `dose_time` + TZ → UTC. `dose_mg` + `brand` snapshotted from current protocol. Flagged in report. | — |
| `logs/YYYY-MM-DD.json.dose_logged: false` | nothing | No line is a valid state. | — |
| `logs/YYYY-MM-DD.json.water_count` | discarded | Feature removed. Report notes per-day count. | — |
| `logs/YYYY-MM-DD.json.day_notes` | discarded | No v2 home. Report surfaces non-empty values. | — |
| `logs/YYYY-MM-DD.json.running_totals, remaining, targets` | discarded | Recomputable. | — |
| `recipes.json.recipes[]` | `recipes.json.recipes[]` | Schema validation pass. Repair if possible, quarantine to `_quarantine/recipes/` if not. | — |
| `.bak` files | discarded | JSONL append semantics; no .bak. | — |

### TDEE/deficit rules (Phase 1)

1. If v1 `whoop_tdee_kcal` is non-null and > 0, write to active mesocycle `tdee_kcal`. Compute `deficit_kcal = tdee_kcal - v1_scalar_kcal` for each day type. Write as day-pattern overrides. Pick the most common deficit as the cycle's nominal. Set `deficits` and `nominal_deficit` markers anyway — user confirms or adjusts in Phase 2. Do NOT set `tdee` marker.
2. If v1 `whoop_tdee_kcal` is null or zero, leave active mesocycle `tdee_kcal = null`. Do NOT compute deficits. Store v1 scalar kcal values in `_pending_kcal` field on each day_pattern (not part of the canonical model — migration scratch field, cleared in Phase 2). Set `tdee`, `deficits`, and `nominal_deficit` markers.

Historical (non-active) mesocycles always get `tdee_kcal = null` and are flagged in the report. v1 didn't carry enough info to reconstruct historical TDEE.

### Idempotency

Migrator writes `_migration_marker.json` on success: `{source_root, migrated_at_iso, v1_file_count, v2_file_count, counts_per_kind, markers_set}`. Re-runs check the marker and refuse unless `--force`. `--force` rebuilds from scratch; no partial re-run.

### Migration report

`_migration_report_<timestamp>.md` at `NUTRIOS_DATA_ROOT` root after each run:

- Source and destination paths.
- Counts: migrated cleanly, repaired (with rules), quarantined (with reasons).
- Discarded: water counts per day, day_notes content, `.bak` files.
- Markers set: full list with why each was set.
- Warnings: historical dose lines whose snapshots were filled from current protocol; historical mesocycles with null TDEE.
- TDEE/deficit resolution: which rule fired (1 or 2) and the resulting state.

### Part 6.2 — Phase 2: Setup resume

Runs through the normal turn contract after migration. Driven entirely by `_needs_setup.json` markers.

### Marker order (fixed)

Engine's `setup_status` returns markers in this order, one at a time:

1. `gallbladder` — clinical field affecting advisory logic.
2. `tdee` — blocks kcal target rendering; highest leverage.
3. `carbs_shape` — affects range check semantics.
4. `deficits` — per-day-type confirmation.
5. `nominal_deficit` — cycle-level nominal.

Dependency logic: `deficits` cannot be presented before `tdee` is cleared (deficits are computed against TDEE). `nominal_deficit` cannot be presented before `deficits` is cleared. Engine enforces order.

### Marker prompts

Each marker has a canonical prompt rendered by `render_setup_resume_prompt`:

**gallbladder:**
```
Quick setup question: has your gallbladder been removed?
This affects fat-ceiling recommendations.
Reply: removed / present / unknown
```

**tdee:**
```
What's your TDEE (total daily energy expenditure) for this cycle?
This is the kcal baseline before any deficit.
Reply with a number, e.g. 2600.
```

**carbs_shape:** (context: shows current min per day type)
```
Your v1 carbs came over as a minimum. Is that right?
- Training day: min 220g
- Rest day: min 180g

Reply: yes (keep as minimums), max (change to maximums), both (set both ends), or adjust each.
```

**deficits:** (context: shows computed suggestions)
```
With TDEE 2600, here are the deficits from your v1 kcal targets:
- Rest day: deficit 600 (v1 was 2000)
- Training day: deficit 200 (v1 was 2400)
- Post-dose day: deficit 700 (v1 was 1900)

Reply 'yes' to confirm all, or specify changes (e.g. "rest 500").
```

**nominal_deficit:** (context: shows confirmed deficits)
```
Which deficit should be the cycle nominal? Day types not matching it become overrides.
Most common: 600 (rest day).
Reply 'yes' for 600, or specify (e.g. '500').
```

### Write-through discipline

Each setup_resume answer routes through the same gated tools as normal operation:

- `gallbladder` → `nutrios_protocol_edit.py` (ungated field — no confirmation phrase needed for this specific field, documented in the tool).
- `tdee` → direct write to active mesocycle. Not protected by default (can be adjusted anytime).
- `carbs_shape` → `nutrios_write.py` to `goals.json`. If `protected=true` on the carbs range (not set by migration, but user may set later), routes through `protected_gate_range`.
- `deficits` → direct writes to each day-pattern.
- `nominal_deficit` → direct write to active mesocycle.

Every successful write calls `clear_needs_setup_marker`. When the last marker clears, setup_resume returns `render_setup_complete`.

### Interrupted setup

Setup resume is resumable. If the user stops mid-flow and comes back days later, the context pass detects the remaining markers and resumes at the next-in-order marker. No state is lost. Allowed intents (log food, weigh-in, smalltalk) continue to work throughout.

---

## Part 7 — Success criteria (additions to base brief)

- All v1 weigh-ins present in `weigh_ins.jsonl` in original order with monotonic IDs.
- All v1 med_team_notes present in `med_notes.jsonl`.
- Every v1 daily log with `dose_logged: true` produces exactly one dose line in the v2 JSONL.
- Zero v1 `water_count` data written to v2.
- Zero LLM-authored advisory flags or range-status labels in a 7-day sample.
- Zero protected-default bypasses on `protocol.dose_mg`, `protocol.dose_day_of_week`, or any `protected=true` MacroRange in adversarial prompt tests.
- `resolve_day` produces identical kcal targets to v1's hand-authored scalars on migrated data (within ±1 kcal rounding) once TDEE is set — verifies the TDEE/deficit resolution.
- Migration Phase 1 runs end-to-end with zero interactive prompts on fixture data.
- Setup resume correctly blocks disallowed intents and allows the allowed intents at every marker state.
- Setup resume is resumable: stopping and resuming at any marker produces identical final state.
- Re-running migration against an already-migrated tree is a no-op without `--force`.

---

## Part 8 — Build order delta

Numbering matches base brief with decimal inserts.

1. `nutrios_time.py` + tests. (base)
2. `nutrios_store.py` with per-user path resolver, atomic JSONL append, `next_id` counter, `_needs_setup` read/clear. (base, extended)
3. `nutrios_engine.py` pure functions + tests: base brief plus MacroRange logic (`merge_range`, `macro_range_check`, `range_proximity`), `resolve_day`, weight functions, dose/event functions, `advisory_flags`, `protected_gate_protocol`, `protected_gate_range`, `setup_status`.
4. `nutrios_mnemo.py`. (base)
5. `nutrios_render.py` with range-aware macro lines, kcal derivation rendering, setup resume renderers, all new renderers.
6. Port `read/write/log` tools; `log` gains dose-kind awareness; `write` routes protected MacroRange edits through `protected_gate_range`.
6.5. **Migration module** `nutrios_migrate.py` (Phase 1 only) + tests. Headless, deterministic, report. Runs against fixture first.
6.6. New Python tool entrypoints: `nutrios_weigh_in.py`, `nutrios_dose.py`, `nutrios_med_note.py`, `nutrios_event.py`, `nutrios_protocol_edit.py`, `nutrios_setup_resume.py`.
7. Slim `orchestrator.md` + module prompts (log, goals, setup-resume, weigh-in, dose, events, protocol).
8. `scaffold.sh` updated for extended tree.
9. `INSTALL.md` updated: env vars, channels, migration invocation, setup resume expected on first interaction.

Review gates:

- **Step 3 (engine)** — first architectural review. Covers MacroRange logic, `resolve_day` semantics, protected-default extensions, `setup_status` ordering and dependency logic, advisory structure.
- **Step 6.5 (migration)** — second architectural review. Covers idempotency, marker-setting discipline, TDEE/deficit rules, dose-line synthesis, report completeness. Fixture-only; no live cutover until report passes review.
- **Step 7 (prompts)** — third architectural review. Orchestrator byte-stability, setup gate enforcement, setup resume prompt clarity.

---

## Part 9 — Non-negotiables (additions to base brief)

- LLM never authors an advisory flag, dose reminder, range status, event trigger, or setup prompt body. All come from Python as pre-rendered strings.
- LLM never performs weight math, kcal derivation, range resolution, or setup-order determination. All engine functions.
- Protocol edits to `dose_mg` and `dose_day_of_week` route through `protected_gate_protocol`.
- Any MacroRange edit where `protected=true` routes through `protected_gate_range`.
- Historical dose lines synthesized during migration are marked in the report; their `dose_mg` and `brand` are current-protocol values at migration time, not reconstructions.
- Historical mesocycles (non-active) carry null `tdee_kcal` when migrated; not synthesized.
- Water intent is removed. If a user says "water" to the bot, orchestrator classifies as `smalltalk` with a one-line acknowledgment; no state change.
- Mesocycles are always user-scoped by path. No global mesocycle store exists.
- Migration Phase 1 is deterministic and headless. Zero interactive prompts during structural transformation.
- Setup resume operates through the standard turn contract. No side channels, no direct file writes from the LLM.
- Allowed intents during setup (food log, weigh-in, smalltalk) continue to work. Setup does not block core daily usage.
- Setup marker order is fixed in engine. The LLM does not reorder or skip markers.

---

End of extension.
