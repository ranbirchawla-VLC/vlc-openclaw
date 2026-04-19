# REVIEW — Phase 24b Cowork Deliverable

**Branch:** `feature/grailzee-eval-v2`
**Commits reviewed:** `b5b0995` → `fe651d2` (6 commits, ~1,900 lines)
**Reviewer:** `code-reviewer` subagent (Claude Opus 4.7)
**Date:** 2026-04-19
**Status:** PASSED with targeted fixes applied in-branch

## Scope

Phase 24b extends the existing Phase 24a cowork plugin to accept a new
INBOUND input format (`strategy_output.json`) alongside the existing
`.zip` bundle, validates it against a hand-rolled JSON Schema 2020-12
validator, atomically writes each non-null decision section into
`state/`, and archives three operator-facing artifacts (JSON / XLSX /
MD) to `output/briefs/`.

Commits in scope:

| SHA | Summary |
|---|---|
| `b5b0995` | strategy_output_v1 schema + validator + 33 tests |
| `e7e507f` | INBOUND dual-input dispatch + JSON apply pipeline + 24 tests |
| `0d26be1` | build_strategy_xlsx + 5-sheet builder + 14 tests |
| `242d9c0` | archive writes to output/briefs/ + 11 tests |
| `ecebdd2` | grailzee-bundle SKILL.md dual-input contract |
| `fe651d2` | round-trip integration tests for .json path (+2 tests) |

## Summary

No critical findings. The trust boundary between `.zip` (Phase 24a, 3
roles) and `.json` (Phase 24b, 9 roles) holds: `_validate_manifest`
enforces the narrower `ZIP_WHITELIST` for zip inputs, and
`validate_strategy_output` runs before any state write on the json
path. The atomic two-phase commit in `_atomic_write_targets` is
exception-safe and its crash-atomicity caveat is documented.
Archive-write isolation from state-write atomicity is explicitly
tested (`test_apply_archive_failure_does_not_block_state_commit`).

All recommendations and nits were addressed in a follow-up commit on
this same branch before this review was finalized.

## Findings and resolutions

### Critical

None.

### Recommended (fixed)

1. **Full-file slurp for a 4-byte magic probe** — `_detect_input_type`
   previously used `path.read_bytes()[:4]`, loading the entire file
   (up to `MAX_TOTAL_DECOMPRESSED_BYTES = 16 MB`) to check a 4-byte
   signature. Replaced with `open(path, "rb") as f: f.read(4)` /
   `f.read(64)` so only the needed prefix is read. Also rewrote the
   dispatch as `match/case` per CLAUDE.md convention for known-value
   branching.

2. **XLSX archive catch was `except Exception`** — global Python
   standards require specific exceptions. Narrowed to
   `(OSError, ValueError, KeyError, TypeError)` with a comment
   documenting which openpyxl failure classes each arm covers.

3. **`match/case` not used in `main()` dispatch** — the `if kind ==
   "zip": ... else: # "json"` chain was rewritten as `match kind`
   with an explicit `case _` defensive arm. CLAUDE.md calls out
   match/case for exactly this kind of known-value dispatch.

4. **Missing test: `target_margin_fraction == 1.0` rejection** — the
   constraint is exclusive on both ends; the lower bound had coverage
   but the upper bound did not. Added
   `test_target_margin_fraction_one_rejected`.

5. **Missing test: XLSX-only archive failure isolation** — the XLSX
   write path has the broadest exception catch, but no test
   specifically induced an XLSX write failure to confirm JSON + MD
   still write. Added
   `test_xlsx_failure_alone_does_not_block_json_or_md`.

### Nits (fixed)

1. **Dead `import copy`** in `tests/test_strategy_output_schema.py` —
   removed.

2. **Implausible `cycle_2026-15` literal** in the schema-test minimal
   fixture — replaced with the realistic `cycle_2026-04` used
   elsewhere.

3. **Missing explicit `encoding="utf-8"`** on two
   `json.loads(path.read_text())` call sites — added for cross-
   platform robustness and consistency with the archive writer.

## Verified clean

- Trust boundary: `ZIP_WHITELIST` ≠ `JSON_WHITELIST`; hostile `.zip`
  with a `signal_thresholds` role is rejected at
  `_validate_manifest` (`unpack_bundle.py:183`).
- `_atomic_write_targets` pre-checks leftover pid-tagged siblings
  across every target, writes tmps, hardlinks snapshots, replaces,
  rolls back on any phase-3 exception.
- Hand-rolled validator guards `bool`-as-`int` / `bool`-as-number
  coercion (explicitly tested).
- Archive isolation: state commits before archive writes; archive
  failures return `archive_errors: [{file, error}]` without raising.
- `VARDALUX_COLORS` duplication is documented with rationale and
  canonical-source pointer. Justified for a plugin that must run
  from any checkout path without a cross-module sys.path hack.
- Round-trip integration test covers state + archive + non-
  interference with unrelated files (analysis_cache, trade_ledger,
  sourcing_brief).
- All 156 tests pass on `feature/grailzee-eval-v2` after fixes.

## False flags considered and dismissed

- `os.link()` cross-filesystem failure — snapshots live in the same
  directory as the target, so same-FS is guaranteed.
- `ZipInfo.file_size` trust — checked against the post-read
  `len(data)` AND the manifest's declared `size_bytes`, so a lying
  zip header gets caught twice.
- Duplicate arcname collision with `zf.getinfo(entry["path"])` —
  dedup runs before `getinfo`, so resolution is unambiguous.
- `_is_unsafe_arcname` missing UTF-8 normalization tricks (NFC/NFD,
  zero-width joiners) — out of scope for a trusted-operator-delivered
  bundle.
- Returning the full payload in `apply_strategy_output`'s summary
  dict — `main()` strips it at the CLI boundary; library callers
  explicitly requested it (documented).

## Test inventory

| File | Tests | Purpose |
|---|---|---|
| `test_strategy_output_schema.py` | 34 | Validator happy paths + all shape errors |
| `test_inbound_dispatch.py` | 11 | `.zip` / `.json` magic-byte probe + `main()` |
| `test_json_apply_pipeline.py` | 13 | `apply_strategy_output` state writes + cycle_id gate |
| `test_build_strategy_xlsx.py` | 14 | XLSX sheet order, brand palette, percent rendering |
| `test_archive_writes.py` | 12 | Best-effort archive + failure isolation |
| `test_round_trip.py` | 5 | OUTBOUND→INBOUND + Phase 24b full JSON handoff |
| **Total** | **89 new** | +62 inherited from Phase 24a = **156 tests** |

## Sign-off

Phase 24b cowork deliverable is ready for the supervisor gate. No
open issues. All reviewer findings resolved in-branch with targeted
fixes preserving the existing design.
