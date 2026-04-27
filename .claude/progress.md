# progress.md — Grailzee Eval v2 / Rational Sequence

**Working root**: `/Users/ranbirchawla/ai-code/vlc-openclaw` (not `.openclaw/workspace`)
**Branch**: `feature/grailzee-eval-v2`
**Remote**: in sync at `4d65a4e` (pushed 2026-04-26); Step 2 pending push
**Canonical state doc**: `GRAILZEE_SYSTEM_STATE.md` at repo root. Read that first.

Session-open protocol: read `GRAILZEE_SYSTEM_STATE.md`, then this file.

---

## Status at a glance

| Item | State |
|---|---|
| Schema version | v3 (cache `schema_version: 3` since 2b) |
| Tests | `make test-grailzee-eval`: 987 passed, 54 skipped |
| Cowork suite | `make test-grailzee-cowork`: 235 passed, 0 failed |
| Step 0 (schema lock) | DONE; `bfc68cd` pushed |
| Step 1 (`evaluate_deal.py` + bot wiring) | DONE; `c8b8494` pushed |
| Step 1 patch (margin-floor rounding) | DONE; `2ec21e5` pushed |
| Step 1.3 (human-facing label fields + deal.md) | DONE; `4d65a4e` pushed; release check passed |
| Step 2 (producer chain + bundle validation) | DONE; commit pending push |
| Step 3 (strategy skill update) | NOT STARTED; next up |
| State doc Section 4 | Pending operator draft; entries: ae253aa, 2a852cb, c7f90d5, bfc68cd, c8b8494, 2ec21e5, 4d65a4e + Step 2 commit |
| §5.5 spot-check | Rides next live Grailzee cycle |
| 2a ingest_and_archive live rehearsal | Open; closes with §5.5 |
| Telegram release check (Step 2) | PASS; Branch D: "Reference not in cache" + comp-search; Branch E: "Deal evaluation failed: {message}"; em-dashes: 0 |
| Bundle assembly check (Step 2) | PASS; 12 roles (10+2 conditional), sha256 all OK, shortlist validates |

---

## Rational sequence (current)

From `Grailzee_Implementation_Sequence_2026-04-26.md` and `Grailzee_Architecture_Lock_2026-04-26.md`.

**Step 0** — Lock schemas — **DONE** (`bfc68cd`)
**Step 1** — Wire bot end-to-end against mock — **DONE** (`c8b8494` + `2ec21e5` patch)
**Step 2** — Wire producer chain forward — **DONE** (commit this session)
**Step 3** — Wire strategy session — Sonnet; next up
**Step 4** — Sale folder json ingest — design outstanding
**Step 5** — Verify report pipeline — verification only

Architecture lock: three surfaces (Telegram bot, cowork, chat strategy skill). Wide CSV is strategy input. Yes/no only on deal eval. Premium scalar uniform. No inter-cycle tracking in this stack.

---

## Session 2026-04-26 (third): Step 1 bot end-to-end + floor-round patch

### What landed (`c8b8494`, `2ec21e5`)

**`evaluate_deal.py`** (full rewrite). Reads v3 bucket cache; matcher narrows by 0–3 optional axes (`dial_numerals`, `auction_type`, `dial_color`); ambiguous returns candidates so the LLM asks one clarifying question. New return shape: `decision`, `bucket`, `math`, `cycle_context`, `match_resolution`, `candidates` (when ambiguous). Yes/no only; no MAYBE. `_on_demand_analysis` deleted; cache miss → `reference_not_found` / no. Premium scalar applied uniformly from `analyzer_config.scoring.premium_scalar_fraction` (default 0.10). Dual entry (argparse + stdin-JSON) for OpenClaw + tests.

**`scripts/grailzee_common.py`**: added `premium_scalar_fraction: 0.10` to `ANALYZER_CONFIG_FACTORY_DEFAULTS["scoring"]`. `state/analyzer_config.json` regenerated via installer.

**Per-agent `openclaw.json`** at `skills/grailzee-eval/openclaw.json`. Two tools: `evaluate_deal` (with optional axes) and `report_pipeline`. Absolute repo paths in `command`. NutriOS-style stdin-JSON inputSchema. `accountId` not `default`. Operator handles root `~/.openclaw/openclaw.json` repoint.

**`SKILL.md` cuts**: Path 1 (ledger), Path 4 (performance query), Path 5 (targets) removed. Paths 2 (deal eval), 2a (priceless), 3 (report) retained. Capability list reduced to `deal.md` + `report.md`.

**`capabilities/deal.md`** (full rewrite). Single yes/no narration from verbatim `math` numbers per AA §2.7. Branches A–E mapped to `match_resolution`. On `decision: "no"` ends with single line `Comp search not yet wired.` (§4.6 cut; Step 2 builds backend). Em-dash–free.

**Capability deletes**: `capabilities/ledger.md`, `capabilities/targets.md`. No standalone test modules referenced them.

**Mock + INBOUND + e2e**: `grailzee-cowork/tests/fixtures/mock_strategy_output.json` (12 targets across Tudor / Breitling / Cartier / Omega; capital_target 60000; target_margin_fraction 0.05; monthly_return_pct 0.12; cycle_id `cycle_2026-15`). `tests/test_step1_mock_inbound.py` exercises `unpack_bundle.apply_strategy_output` and asserts atomic state writes. `skills/grailzee-eval/tests/test_step1_e2e_bot.py` runs mock → unpack → `evaluate()` end-to-end (3 tests: yes on plan, no on plan math fails, off plan reference_not_found).

**Floor-round patch (`2ec21e5`)**. Architecture lock §1: 5% margin floor non-negotiable. `max_buy = round(unrounded, -1)` could let a deal land 1–4 dollars below the floor with `decision: yes`. Switched to `math.floor(unrounded/10)*10` so every dollar at or below `max_buy` clears the floor. Boundary test added (`test_max_buy_floor_rounds_below_5pct_unrounded`): median=2768 → unrounded=2757.90 → floor=2750 (margin 5.30%); old nearest-round=2760 (margin 4.92%, the bug).

**Tests**: 1047 grailzee-eval pass (was 1033; +14 net after replacing v2 contract; +1 boundary test). 234 grailzee-cowork pass (was 230; +4 INBOUND-against-mock).

**Code review** (subagent, fresh context, two passes):
- Step 1: SHIP-WITH-FIXES, no BLOCKERS. Two MAJORs carry-forward (fee constants externalization, margin-floor rounding). Eight architecture-lock decisions all PASS.
- Patch: SHIP, no BLOCKERS. Reviewer's 100k random sweep (NR/RES, premium 0–30%, median 50–50k) confirmed zero floor violations under floor-round.

**Two-commit pattern applied per gate; Step 1 squashed to single commit; patch is its own commit per §5 directive.**

### State of tree

- `2ec21e5` (patch) → `c8b8494` (Step 1) → `bfc68cd` (Step 0) → `c7f90d5`. All pushed to `origin/feature/grailzee-eval-v2`.
- `state/analyzer_config.json` regenerated to include `scoring.premium_scalar_fraction`.
- New per-agent `openclaw.json` at `skills/grailzee-eval/openclaw.json`; root config repoint operator-handled at gateway restart.
- `Makefile` adds `test-grailzee-eval-evaluate-deal` target.

### Architecture-lock §1 floor leak (carry-forward, MAJOR)

Same nearest-rounding gap exists in `grailzee_common.max_buy_nr()` and `max_buy_reserve()` (both use `round(_, -1)`). Feeds:
- `scripts/query_targets.py` → Telegram targets list (Surface 1).
- `scripts/build_brief.py`, `build_summary.py`, `build_spreadsheet.py` → strategy bundle outputs (Surface 3).
- `scripts/analyze_references.py` → bucket-cached `max_buy_nr` / `max_buy_res`.
- `scripts/grailzee_common.py::adjusted_max_buy()` → premium-applied cache writes.
- `scripts/read_ledger.py` → ledger-derived `max_buy_at_trade`.

Floor applies to every operator-facing buy ceiling. Land as Step 1.1 patch or roll into Step 2 producer-chain work; either is defensible since strategy-bundle outputs (Surface 3) get rebuilt in Step 2.

### Other carry-forwards (MINOR; out of Step 1 scope)

- `_bucket_fees` reads hardcoded `NR_FIXED=149` / `RES_FIXED=199`; should externalize to `analyzer_config.fees`.
- `_decide_yes_no` precondition order vs. non-null-median Low data buckets.
- `_run_from_dict` accepts `cache_path` / `cycle_focus_path` not declared in `inputSchema`.
- Symmetric span attributes on error path.
- `report_pipeline` tool description duplicates intent triggers from SKILL.md.
- `test_apply_blocks_cycle_id_mismatch` final assertion polish.
- `test_step1_e2e_bot.py` `sys.path` edit → conftest plug.
- `skills/grailzee-eval/scripts.zip` and `tests.zip` artifacts untracked; `.gitignore` candidates.

---

## Session 2026-04-26 (second): Step 0 schema lock

### What landed (`bfc68cd`)

**`cycle_shortlist_v1.json`** (new): 30-column bucket-row CSV contract.
- Canonical at `grailzee-cowork/schema/`, byte-identical mirror at `grailzee-strategy/schema/`.
- Column inventory captured from `build_shortlist.py` output (authoritative).
- Three spec-checklist drifts surfaced and accepted: `generated_at`, `cycle_id`, `condition_mix` absent from script output. Script is canonical.
- `check_schema_mirror.py` extended to check both schema pairs; both green.

**`strategy_output_v1.json`** (amended in both copies):
- `monthly_return_pct` added to `monthly_goals.properties`: oneOf null or number in (0,1) exclusive. Optional; NOT in required. `strategy_output_version` stays 1.
- Pre-existing em-dash in top-level description replaced with semicolon (code-review blocker, caught and fixed).

**`cycle_shortlist_schema.py`** (new): stdlib-only hand-rolled CSV validator mirroring `strategy_schema.py` pattern. `validate_schema_file` + `validate_csv(path, schema_path)` with dotted-path errors.

**`strategy_schema.py`** (amended): `_validate_monthly_goals` replaced `_require_exact_keys` with inline required/optional split. `monthly_return_pct` validated when present; null or absent passes.

**Tests**: +37 new cowork tests (230 total). `test_cycle_shortlist_schema.py`: schema-level + CSV-level coverage. `test_strategy_output_schema.py`: 7 `monthly_return_pct` range-bound tests. `_fixtures.py`: `_monthly_goals_with_return_pct` helper.

**Code review** (subagent, fresh context): one BLOCKER (em-dash), fixed before squash. All other checks PASS. Verdict: SHIP.

**Two-commit pattern applied; squashed to single Step 0 commit.**

---

## Session 2026-04-26 (first): Wave 1.1 + audit + planning

### What landed (pushed to remote)

**Wave 1.1 `build_shortlist.py`**: `ae253aa` (tests), `2a852cb` (impl), `c7f90d5` (Makefile).
- 30-column bucket-row CSV; `_flatten_row(ref_entry, bucket_key, bucket)`; deterministic sort with tiebreaks; Decisions 8/9/10/11 PASS; run_analysis.py 2c-restore try/except removed.
- Makefile targets added: `test-grailzee-eval`, `test-grailzee-eval-build-shortlist`, `test-grailzee-eval-run-analysis`, `test-grailzee-cowork`.
- **Standing rule**: always `make test-*`; never raw pytest.

**Wave 1 audit** (`discovery/schema_v3/phase_2c/audit_findings.md`): cowork bundle roles mapped; strategy skill v2-era reads documented; skip-marker gap in `analyze_brands.py` surfaced.

**State docs added** to `state/`: Decision Lock Addendum (Decisions 8-11 + Opus process decision); 2b close-out.

---

## Open items into Step 2

1. **State doc Section 4**: six commit entries pending — ae253aa, 2a852cb, c7f90d5, bfc68cd, c8b8494, 2ec21e5.
2. **Telegram release check** (Step 1 §5 third gate): operator-driven; bot answers a deal eval against mocked state with yes/no + math; off-plan / math-failing deal returns no with `Comp search not yet wired.`
3. **Operator action**: repoint root `~/.openclaw/openclaw.json` workspace path (or symlink) before gateway restart so OpenClaw discovers the per-agent `openclaw.json` at `skills/grailzee-eval/`.
4. **`grailzee_common.max_buy_*` floor leak**: Step 1.1 patch or Step 2 producer-chain absorption.
5. **Step 2 prompt drafting**: `build_shortlist.py` schema-validation OUTBOUND; cowork OUTBOUND wide-CSV validation; bundle assembly with state + sale-folder JSONs; KNOWN_ISSUES #1 / #3 fixes.
6. **`analyze_brands.py` skip-marker gap**: determine pass/fail before Step 2 sequencing.
7. **§5.5 spot-check**: generate v3 cache from branch against live W2 CSV; closes 2a ingest_and_archive rehearsal.

---

## Pointers

- State truth: `GRAILZEE_SYSTEM_STATE.md` (repo root)
- Architecture lock: `Downloads/GZ-4-25/GZ-4-26/files/Grailzee_Architecture_Lock_2026-04-26.md`
- Rational sequence: `Downloads/GZ-4-25/GZ-4-26/files/Grailzee_Implementation_Sequence_2026-04-26.md`
- Step 0 spec: `Downloads/GZ-4-25/GZ-4-26/Grailzee_Step0_Schema_Specification_2026-04-26.md`
- Decision locks: `state/Grailzee_Schema_v3_Decision_Lock_2026-04-24_v1.md` + `state/Grailzee_Schema_v3_Decision_Lock_Addendum_2026-04-26_v1.md`
- 2c audit findings: `discovery/schema_v3/phase_2c/audit_findings.md`
- Strategy skill: `grailzee-strategy/` (repo root)
- Cowork plugin: `grailzee-cowork/` (repo root)
- Step 1 mock fixture: `grailzee-cowork/tests/fixtures/mock_strategy_output.json`
- Per-agent OpenClaw config: `skills/grailzee-eval/openclaw.json`
- Full prior build log: `.claude/progress-v0.md`
