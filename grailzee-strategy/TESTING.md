# Testing — grailzee-strategy

Manual test playbook. The skill runs in Chat against real operator
uploads; the automated coverage lives on the cowork side (schema
validator, archive writer, round-trip). This doc is the manual
checklist for verifying the skill end-to-end before cutting a
release.

## Prerequisites

- Working `grailzee-cowork` checkout with Phase 24b applied (inbound
  accepts both `.zip` and `strategy_output.json`).
- A GrailzeeData tree to point at (real or a fixture clone).
- Python 3.10+ with `openpyxl` available for the cowork archive leg.

## Test 1 — schema mirror

Confirm the Chat skill's schema is byte-identical to cowork's:

```
python grailzee-strategy/tools/check_schema_mirror.py
```

Expected: exits 0 with `OK: strategy_output_v1.json byte-identical
across both plugins.` Non-zero exit means drift — fix before anything
else; both copies must move in lockstep. Wire this into CI when CI
exists; run it manually before every commit that touches either
schema file in the meantime.

For manual inspection of the diff:

```
diff \
  grailzee-strategy/schema/strategy_output_v1.json \
  grailzee-cowork/schema/strategy_output_v1.json
```

## Test 2 — fixtures validate

Every fixture under `references/mode_fixtures/` must pass cowork's
validator:

```
cd grailzee-cowork
for f in ../grailzee-strategy/references/mode_fixtures/*.json; do
  python -c "
import json, sys
from pathlib import Path
sys.path.insert(0, 'grailzee_bundle')
from strategy_schema import validate_strategy_output, StrategyOutputValidationError
payload = json.loads(Path('$f').read_text(encoding='utf-8'))
try:
    validate_strategy_output(payload)
    print('$f OK')
except StrategyOutputValidationError as e:
    print('$f FAIL', e)
"
done
```

Expected: each line prints `... OK` (validator returns None on success,
raises `StrategyOutputValidationError` on failure).

## Test 3 — cycle_planning session (golden path)

1. Build an outbound bundle with `scope.month_boundary: false` and
   `scope.quarter_boundary: false`.
2. Upload `.zip` to Chat with prompt: *"New cycle — plan it."*
3. Expected skill behavior:
   - Activates `grailzee-strategy`.
   - Reads `manifest.json`, `cycle_shortlist.csv`, `analysis_cache.json`,
     and `cycle_focus.json` before writing anything.
   - Produces `strategy_output.json` with:
     - `session_mode: "cycle_planning"`
     - `decisions.cycle_focus` populated; other three decisions null
     - `cycle_focus.targets` has 3–6 entries, each with a
       `cycle_reason` grounded in bundle data
     - `target_margin_fraction: 0.05` unless operator overrode
     - `session_artifacts.cycle_brief_md` present and non-empty
   - Hands over a one-paragraph summary and the unpack_bundle.py
     command.
4. Save the JSON, run cowork unpack_bundle.py. Expected:
   - `state/cycle_focus.json` updated atomically
   - Three files under `output/briefs/`:
     `<cycle_id>_strategy_output.json`,
     `<cycle_id>_strategy_brief.md`,
     `<cycle_id>_strategy_brief.xlsx`

## Test 4 — monthly_review session

1. Build bundle with `scope.month_boundary: true`.
2. Upload with prompt: *"Wrap up April and give me the May plan."*
3. Expected:
   - `session_mode: "monthly_review"`
   - `decisions.monthly_goals` populated with `month: "2026-05"` (new
     month, not closed month), `review_notes` recapping the prior
     month in absolute-date terms, `focus_notes` forward-looking
   - `cycle_focus` null unless operator also asked for a refresh
   - Platform mix sums to ~100 if non-empty
4. Apply via cowork. Expected: `state/monthly_goals.json` updated;
   other state files untouched.

## Test 5 — quarterly_allocation session

1. Build bundle with `scope.quarter_boundary: true`.
2. Upload with prompt: *"Q3 rebalance."*
3. Expected:
   - `session_mode: "quarterly_allocation"`
   - `decisions.quarterly_allocation` populated with
     `quarter: "2026-QN"` in that format
   - `capital_allocation` has an `other` bucket (framework convention
     — not a validator rule, but flag missing `other` as a judgment
     miss)
   - `inventory_mix_target` sums to ~100
   - `review_notes` anchors each brand delta to a quantified Q-over-Q
     number
4. Apply. Expected: `state/quarterly_allocation.json` updated.

## Test 6 — config_tuning session

1. Build bundle (scope flags irrelevant — config_tuning is operator
   request only, never inferred).
2. Upload with prompt: *"Retune the signal floor — Strong is drifting."*
3. Expected:
   - `session_mode: "config_tuning"`
   - `decisions.config_updates` populated
   - At most **two** sub-configs non-null (guardrail)
   - Each non-null sub carries the envelope: `version` (incremented),
     `updated_at` (matches `generated_at`), `updated_by: "strategy_session"`,
     `notes`
   - Untouched sub-configs are explicitly `null`, not carried forward
   - `change_notes` summarizes what changed
   - `cycle_focus`, `monthly_goals`, `quarterly_allocation` all null
4. Apply. Expected: only the named config state files updated.

## Test 7 — validation failures surface cleanly

Feed malformed JSON to cowork and confirm the skill's self-check
would catch the same issues:

- `target_margin_fraction: 5` (instead of `0.05`) → rejected
- `strategy_output_version: 2` → rejected (current schema is v1)
- `cycle_id: "cycle_2026-15"` (month > 12 still matches regex, so this
  passes the regex but caller should catch semantically; confirm
  regex-only enforcement is the documented contract)
- All four decisions null → rejected (need at least one)
- `config_updates` non-null but all six subs null → rejected
- Missing `session_artifacts.cycle_brief_md` → rejected
- `additionalProperties` violation (stray top-level key) → rejected

## Test 8 — archive failure does not block state

Simulate an archive-leg failure (e.g. briefs directory not writable)
while running the inbound JSON flow:

1. Apply a valid `strategy_output.json`.
2. With `output/briefs/` read-only.
3. Expected:
   - cowork still writes state atomically (state is the contract)
   - The return summary surfaces `archive_errors` listing what failed
   - Exit code is 0 (or whatever cowork's success code is)

This is covered by cowork's automated tests
(`test_archive_writes.py::test_apply_archive_failure_does_not_block_state_commit`)
but worth spot-checking manually on first release.

## Test 9 — double-apply idempotence

Apply the same `strategy_output.json` twice in a row. Expected: second
apply is a no-op or clean overwrite; no corruption, state snapshots
stay consistent, archive writes overwrite cleanly.

## Test 10 — round-trip

1. Export state from a GrailzeeData tree as an outbound `.zip`.
2. Run a cycle_planning session against it.
3. Apply the output.
4. Re-export as a new outbound `.zip`.
5. Confirm: the new bundle's `cycle_focus.json` reflects the
   session's decisions.

Covered for the JSON leg by
`test_round_trip.py::test_strategy_output_full_round_trip` on the
cowork side. The manual test above exercises the full operator loop
including Chat.

## What's intentionally not tested here

- **Schema contents in the abstract** — that's the cowork validator's
  job, covered by `test_strategy_output_schema.py` (34 tests).
- **Archive file formats** — covered by
  `test_build_strategy_xlsx.py` (14 tests) and
  `test_archive_writes.py` (12 tests).
- **Atomic commit semantics** — inherited from Phase 24a, covered by
  `test_zip_apply.py` and existing round-trip tests.

This doc focuses on what only a human operator with a real Chat session
can exercise: the skill's judgment behavior, the conversational
handoff, and the end-to-end operator loop.
