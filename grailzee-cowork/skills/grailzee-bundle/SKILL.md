---
name: grailzee-bundle
description: Package GrailzeeData state into an outbound .zip for a Chat strategy session, or validate and atomically write an inbound .zip back into state/. Invoke when the operator asks to build a strategy bundle, upload to a Chat session, or apply Chat planning decisions locally.
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
  INBOUND mode.

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
- `trade_ledger_snippet.csv` (current cycle's rows only)
- `sourcing_brief.json`
- `latest_report/grailzee_YYYY-MM-DD.csv` (newest)

## Workflow — INBOUND

1. Confirm the `.zip` path and the GrailzeeData root.
2. Invoke the unpacker:
   ```
   python grailzee-cowork/grailzee_bundle/unpack_bundle.py \
     <path-to-inbound.zip> \
     --grailzee-root <path-to-GrailzeeData>
   ```
3. On success, the script prints a JSON summary
   (`{cycle_id, roles_written, source}`). Relay to the operator.
4. On failure, the stderr message names exactly which validation rule
   failed (symlink, cycle_id mismatch, sha256 mismatch, etc.). Do not
   retry. Return the error to the operator verbatim.

Inbound writes are atomic. If any validation rule fails OR a mid-commit
write fails, no state file is left in a half-written state.

## Response format

- OUTBOUND success: one line with the bundle path, optionally preceded
  by the scope flags if either boundary is True (`[month boundary]` or
  `[quarter boundary]`).
- INBOUND success: the JSON summary from the script, human-readable.
- Either failure: the stderr message, quoted verbatim.

## LLM responsibilities

- Decide OUTBOUND vs. INBOUND from operator intent.
- Choose the `.zip` path (operator names it, or agent reads it from a
  previous turn's context).
- Surface boundary flags (`month_boundary`, `quarter_boundary`) after
  OUTBOUND so the operator knows the bundle spans a planning rollover.

## What the LLM does NOT do

- Does not parse or transform the manifest. The Python scripts own the
  schema.
- Does not compute sha256s, read zip internals, or walk state/ manually.
  Call the scripts; report their output.
- Does not edit state files directly. INBOUND is the only sanctioned
  write path for cycle_focus / monthly_goals / quarterly_allocation in
  this plugin.
- Does not accept a `.zip` from an untrusted source without running
  `unpack_bundle.py` first. The 8-rule validation is the trust boundary.
