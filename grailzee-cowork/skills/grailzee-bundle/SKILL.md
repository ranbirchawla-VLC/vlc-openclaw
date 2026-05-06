---
name: grailzee-bundle
description: Package GrailzeeData state into an outbound .zip for a Chat strategy session, or validate and atomically write an inbound handoff (.zip OR strategy_output.json) back into state/. Invoke when the operator asks to build a strategy bundle, upload to a Chat session, or apply Chat planning decisions locally.
---

# grailzee-bundle

Bridges the Grailzee agent (local, Python-driven auction analysis) with an
interactive Chat strategy session. Two modes, one skill.

## Purpose

Moves planning artifacts across the agent/Chat boundary without ad-hoc
copy-paste. OUTBOUND hands the Chat session a validated snapshot of what
the agent currently knows. INBOUND commits the Chat session's planning
decisions back into local state atomically, or rejects the bundle.

## Trigger

- Operator asks for "the bundle" / "a strategy bundle" / "outbound zip" /
  "package for Chat" → OUTBOUND mode.
- Operator hands over a `.zip` file they received from a Chat session →
  INBOUND mode (zip path, Phase 24a contract).
- Operator hands over a `strategy_output.json` produced by the
  `grailzee-strategy` Chat skill → INBOUND mode (json path, Phase 24b
  contract). The dispatch detects this automatically from the file
  extension + magic bytes.

## Workflow — OUTBOUND

1. Confirm the GrailzeeData root with the operator if not already known.
2. Invoke the builder:
   ```
   python grailzee-cowork/grailzee_bundle/build_bundle.py \
     --grailzee-root <path-to-GrailzeeData>
   ```
3. Report the output path to the operator (printed on stdout).
4. If the builder exits non-zero, surface the stderr message verbatim —
   it names the missing or malformed input.

The bundle is written to `<GRAILZEE_ROOT>/bundles/` as
`grailzee_outbound_<cycle_id>_<YYYYMMDD_HHMMSS_ffffff>.zip` and contains:

- `manifest.json` (schema v1: cycle_id, scope.month_boundary,
  scope.quarter_boundary, file list with sha256 + size per member)
- `analysis_cache.json` (role: analysis_cache)
- `cycle_focus_current.json` (role: cycle_focus_current — what's current
  on the agent; the Chat session's response renames this to `cycle_focus`)
- `monthly_goals.json`
- `quarterly_allocation.json`
- `trade_ledger.csv` (the full trade ledger — all historical Grailzee
  trades, one row per closed position)
- `cycle_shortlist.csv` (per-cycle shortlist CSV from the analyzer)
- `latest_report/grailzee_YYYY-MM-DD.csv` (newest)

## Workflow — INBOUND

1. Confirm the handoff path (either `.zip` or `.json`) and the
   GrailzeeData root.
2. Invoke the unpacker — same entry point for both input types; the
   script auto-detects from the file extension and magic bytes:
   ```
   python grailzee-cowork/grailzee_bundle/unpack_bundle.py \
     <path-to-inbound.zip OR strategy_output.json> \
     --grailzee-root <path-to-GrailzeeData>
   ```
3. On success, the script prints a JSON summary. Relay to the operator.
4. On failure, the stderr message names exactly which validation rule
   failed (symlink, cycle_id mismatch, sha256 mismatch, schema
   violation, etc.). Do not retry. Return the error to the operator
   verbatim.

Both input types commit state writes atomically via the same two-phase
snapshot-and-replace path. If any validation rule fails OR a mid-commit
write fails, no state file is left in a half-written state.

### INBOUND — `.zip` (Phase 24a)

- Whitelisted roles: `cycle_focus`, `monthly_goals`,
  `quarterly_allocation` (3 roles).
- Summary shape: `{cycle_id, roles_written, source}`.
- No archive leg. `.zip` bundles do not carry a markdown brief or the
  Phase 24b session artifacts.

### INBOUND — `strategy_output.json` (Phase 24b)

- Whitelisted roles: the three above PLUS six D5 config files
  (`signal_thresholds`, `scoring_thresholds`, `momentum_thresholds`,
  `window_config`, `premium_config`, `margin_config`). Only the
  non-null decision sections (and within `config_updates`, the
  non-null sub-configs) produce writes.
- Validation is schema-driven (`schema/strategy_output_v1.json`, v1).
  Unknown fields, bad cycle_id patterns, or a `target_margin_fraction`
  outside (0, 1) exclusive are rejected before any write.
- After the atomic state commit, three operator-facing artifacts are
  archived to `<GRAILZEE_ROOT>/output/briefs/`:
  - `<cycle_id>_strategy_output.json` (the validated payload)
  - `<cycle_id>_strategy_brief.xlsx` (multi-sheet Vardalux-branded)
  - `<cycle_id>_strategy_brief.md` (the session's markdown brief)
- Archive writes are best-effort. A failure to write any archive file
  does NOT roll back the state commit — state is the source of truth.
  Failures are surfaced in the summary as `archive_errors: [{file,
  error}, …]`.
- Summary shape: `{cycle_id, session_mode, roles_written, source,
  archive_files_written, archive_errors}`.

## Response format

- OUTBOUND success: one line with the bundle path, optionally preceded
  by the scope flags if either boundary is True (`[month boundary]` or
  `[quarter boundary]`).
- INBOUND success: the JSON summary from the script, human-readable.
  For the `.json` path, explicitly call out any `archive_errors` so
  the operator can retry archival even though the state commit
  landed.
- Either failure: the stderr message, quoted verbatim.

## LLM responsibilities

- Decide OUTBOUND vs. INBOUND from operator intent.
- Choose the handoff path (`.zip` or `.json`) from what the operator
  names or from a previous turn's context. Do not try to convert one
  into the other; the script handles both.
- Surface boundary flags (`month_boundary`, `quarter_boundary`) after
  OUTBOUND so the operator knows the bundle spans a planning rollover.
- On INBOUND `.json` success with non-empty `archive_errors`, tell the
  operator the state commit succeeded AND call out which archive
  file(s) failed — they will want to fix and retry archival without
  re-applying state.

## What the LLM does NOT do

- Does not parse or transform the manifest. The Python scripts own the
  schema.
- Does not compute sha256s, read zip internals, or walk state/ manually.
  Call the scripts; report their output.
- Does not edit state files directly. INBOUND is the only sanctioned
  write path for cycle_focus / monthly_goals / quarterly_allocation in
  this plugin.
- Does not accept a `.zip` or `.json` from an untrusted source without
  running `unpack_bundle.py` first. The 8-rule zip validation and the
  strategy_output schema validator are the trust boundary. The two
  whitelists are kept disjoint: a hostile `.zip` cannot smuggle a
  config-update payload through the Phase 24a trust boundary.
