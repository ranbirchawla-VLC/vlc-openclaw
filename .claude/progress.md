# progress.md — Grailzee Eval v2 / Ledger Redo Phase 1

**Working root**: `/Users/ranbirchawla/ai-code/vlc-openclaw` (not `.openclaw/workspace`)
**Canonical state doc**: `GRAILZEE_SYSTEM_STATE.md` at repo root. Read that first.

Session-open protocol: read `GRAILZEE_SYSTEM_STATE.md`, then this file.

---

## Active tracks

### Track 1 — Shape K (ACTIVE — 2026-05-04)

**Branch**: `feature/grailzee-eval-v2`
**Tip**: `0c3d78b` (pushed to origin; session 2026-05-04 uncommitted work above this)

#### Session 2026-05-04 — what happened

**Commits landed this session (all pushed):**
- `7ff23e9` G — report_pipeline plugin dispatch layer
- `0d73691` H — ingest_sales plugin dispatch layer + tool registration
- `2852144` E — capabilities/ledger.md rewrite
- `ce4be04` A — AGENTS.md rewrite (design §7)
- `70b1164` B.1 — SKILL.md rewrite (design §6)
- `25be64b` B.2 — remove cross-cutting rule duplication from ledger.md
- `0c3d78b` fix — ingest_sales sys.path.insert for spawnArgv invocation

**Model switch**: grailzee-eval agent switched from `ollama/qwen3.5:latest`
to `mnemo/claude-sonnet-4-6` (edit to `~/.openclaw/openclaw.json` only; not
in repo). qwen3.5 was not following plugin tool dispatch instructions.

#### Session 2026-05-05 — what happened

**turn_state dispatch tool built and /ledger gate CLEARED**

Root cause of prior gate failure: AGENTS.md said "Read one file: SKILL.md"
but no `read` tool in tools.allow. SKILL.md never landed in context.

Fix: `turn_state.py` (stdin-dispatched) classifies message, reads matching
capability file from disk, returns `{intent, capability_prompt}`. AGENTS.md
PREFLIGHT forces it before every response.

Second failure: `GRAILZEE_ROOT` not in gateway environment. Fix: injected
as `SPAWN_ENV` constant in `index.js` with production Drive path as fallback.

**Uncommitted work (ready to stage):**
- `skills/grailzee-eval/scripts/turn_state.py` (new)
- `skills/grailzee-eval/tests/test_turn_state.py` (new, 50 tests)
- `plugins/grailzee-eval-tools/index.js` — turn_state registration + SPAWN_ENV
- `skills/grailzee-eval/AGENTS.md` — PREFLIGHT replaces "Read one file"
- `skills/grailzee-eval/tests/test_plugin_shape.py` — turn_state assertions
- `Makefile` — test-grailzee-eval-turn-state target
- `update_openclaw_config.py` — one-time config script (already run; idempotent)

**Test baseline**: 1441 passed / 71 skipped (all green; 1 skip-guarded config
test passes after `update_openclaw_config.py` was run)

**Operator gate: CLEARED — /ledger worked on Telegram 2026-05-05**

**Remaining commit chain:**
- Commit: turn_state + AGENTS.md + SPAWN_ENV + tests (ready now)
- C — capabilities/eval.md (replaces capabilities/deal.md)
- D — capabilities/report.md rewrite
- F — tools.allow lockdown + audit gate

**Resume doc**: `~/Downloads/aBuilds-5-2/Grailzee_ShapeK_Resume_2026-05-02.md` (supersedes 04-28 doc)

#### Session 2026-05-03 — what happened

**evaluate_deal runtime gate (1c+1c.5 post-rebase): NOT CLEARED**

Gateway restart: clean (PID 11285 post-probe restart). Plugin `grailzee-eval-tools` loaded from
`~/ai-code/vlc-openclaw/plugins/grailzee-eval-tools/index.js`. Correct path. Load pattern confirmed
as `openclaw.json plugins.load.paths` (not plugins install).

Audit counts (session `016b53d5`): 2 total / 2 registered / 0 forbidden / 0 exec bypass. Architecture
held at the tool invocation layer.

Gate not cleared because rendering surface failed on both turns:
- Turn 1 (M7941A1A0RU-0003, ambiguous, off plan): LLM said "the script flagged..." (tech leak);
  hallucinated blue dial not in tool output; did not use Branch B verbatim template.
- Turn 2 (79830RB, ambiguous, on plan): same "script" tech leak; synthesized own math from
  cycle_reason prose; concluded "should be a strong buy signal" directly overriding tool's `decision: no`.

Full analysis in `skills/grailzee-eval/evaluate_deal_gate_failure_2026-05-03.md`.

Root cause candidates: (A) `capabilities/deal.md` not in LLM context (no file-read tool in
tools.allow; OpenClaw may not auto-inject capability files); (B) qwen3.5:latest instruction-following
fidelity breaks on strict negative constraints ("do not override tool decision"). Evidence slightly
favors B: Turn 2 LLM passed `dial_color: "black"` per deal.md Step 1 parsing rule, suggesting
deal.md IS partially in context. Both A and B may be true together.

**Capability injection probe: INCONCLUSIVE — capabilities rebuild in separate session**

Probe did not produce a usable result. Sentinel reverted from deal.md (never committed).
Supervisor decision: rebuild capabilities surface in a dedicated session. deal.md is clean (no sentinel).

**AGENT_ARCHITECTURE.md update**

Root copy (`AGENT_ARCHITECTURE.md`, 760 lines) and new `docs/AGENT_ARCHITECTURE.md` (712 lines)
copied from `~/Downloads/` and `~/Downloads/docs/`. Not yet committed (pending operator confirm).

**Pending commit (staged when operator confirms)**

Files to commit together (not deal.md):
- `AGENT_ARCHITECTURE.md` (root, updated)
- `docs/AGENT_ARCHITECTURE.md` (new file)
- `skills/grailzee-eval/evaluate_deal_gate_failure_2026-05-03.md` (new gate capture doc)

**Next actions (in order)**

1. Capabilities rebuild session (separate) — supervisor and operator redesign the surface.
2. 1c.7 commit (AGENTS.md + SKILL.md hard rules hardening) once capabilities direction is locked.
3. Re-run evaluate_deal gate after 1c.7 + capabilities rebuild.
4. Continue Shape K commit chain (1d, 1e, 1e.5) per ShapeK Resume 2026-05-02 §5.

---

### Track 2 — Ledger Redo Phase 1 (SHIPPED 2026-04-29)

**Status**: Phase 1 complete and in production. Production `trade_ledger.csv`
is the 13-column WatchTrack-derived canonical artifact. Strategy skill reads
against it from the next cycle onward.

**Branch**: `feature/grailzee-ledger-phase1-v2` (off `feature/grailzee-eval-v2`)
**Tip**: `1256dfd` (Phase 1 durability artifacts). Pushed.
**Tests**: ledger 332 / eval 1366 / 71 skipped / cowork 235

**Production ledger**: `$GRAILZEE_ROOT/state/trade_ledger.csv`
- 16 rows, 13-column Phase 1 schema
- NR=11, RES=5, UNKNOWN=0
- Pre-cutover 9-column ledger archived to `.pre-redo-2026-04-29.bak` (882 bytes)

**Gate 3 result (2026-04-29)**: PASSED
- files_processed=1, rows_added=19, rows_pruned=3
- rows_skipped=[TEY1104 pending, TEY1092 pending]
- Unmatched: 2 (TEY1048 stock 297Z8, TEY1029 stock I7411V5)
- Idempotency confirmed (files_found=0 on second run)

**ADRs landed**: ADR-0001 through ADR-0007
- ADR-0005: extraction-agent JSONL contract
- ADR-0006: real-data sample-records rule
- ADR-0007: why-this-matters rule

**Durability artifacts landed (2026-04-29)**: `1256dfd`
- `docs/Grailzee_Ledger_Phase1_Closeout_2026-04-29.md` — permanent closeout record
- `docs/decisions/ADR-0006` + `ADR-0007` — methodology rules, binding
- `SUPERVISOR_ROLE.md` v2 — pre-emit audit, code prompt shape, methodology rules section
- `watchtrack_full_final.jsonl` — canonical Gate 3 fixture with NR/RES Platform fee relabels

**Supervisor-side remaining** (Drive / project knowledge, not repo):
- `Grailzee_Ledger_Redo_Design_v1_1.md` — twelve amendments
- `Grailzee_ShapeK_Resume_2026-04-28.md` §7 update

| Sub-step | State | Tip |
|---|---|---|
| 1.1 schema, dataclasses, path resolution | DONE | `3f963af` |
| 1.2 transform_jsonl (corrective pass) | DONE | `66fe0ec` |
| 1.3 lockfile + atomic write | DONE | `43c47d0` |
| 1.4 Rule Y dedup-and-update | DONE | `5d5d47f` |
| 1.5 pruning + ADR-0004 nullability | DONE | `30cfd7f` |
| 1.6 archive move | DONE | `61f6f6a` |
| 1.7 top-level orchestrator | DONE | `8d73c35` |
| Phase 1 Gate 3 + cutover | DONE | `ae80d3a` |
| Phase 1 durability + closeout | DONE | `1256dfd` |

---

## Sub-step closeouts

**Phase 1 cutover (2026-04-29)**: `ae80d3a`. Archived 14-row 9-column pre-redo
ledger to `.pre-redo-2026-04-29.bak`. Ran `ingest_sales()` against production
fixture. Post-cutover: 16 rows, NR=11, RES=5, UNKNOWN=0. Idempotency confirmed.

**1.2 corrective pass (2026-04-29)**: `e003427` (parser rebuild) + `66fe0ec`
(integration cascade). Fixed both bugs: JSONL line-by-line parse + `line_items`
plural list. 8 old synthetic fixtures deleted; 7 real-derived JSONL fixtures
added. ADR-0005 landed. Tests: 308 → 332 ledger / 1342 → 1366 eval. Gate 2:
all 5 subagent confirmations passed on both commits.

**1.7 closeout (2026-04-29)**:
- Branch tip: commit 1 `42f4514`; commit 2 lands on top
- test-grailzee-ledger: 276 → 308 (+32 = 5 in-lock OTEL tests + 27 integration tests)
- test-grailzee-eval: 1310 → 1342 / 71 skipped (unchanged skips)
- test-grailzee-cowork: 235 unchanged
- Commit 1 (substantive): read_ledger_csv + ingest_sales orchestrator + four-inheritance unit tests; lock posture single-acquisition spanning read+merge+prune+write; baseline correction landed (1234 → 1235)
- Commit 2 (substantive): OTEL outcome consolidation (`_OUTCOME_BY_CLASS` mapping + try/except IngestError around with-block); CLI `__main__` (zero arguments, exit 0/1, manifest summary on stdout, error class on stderr); 6 integration scenarios; Gate 2 round 1: 0 blocker / 0 major / 4 minor (sys/contextmanager imports hoisted, sleep bumped to 1.05s for coarse-resolution filesystems, in-lock atomicity assertion added to TestScenario6); standing pattern triage applied, no supervisor in loop
- Carry-forwards to spec v1.1: ArchiveMoveFailed → outcome string for partial-success path (ledger written, archive failed); file-order ISO-dash chronology rule documented but not enforced; defensive-guard test coupling for sell_cycle_id blank validation
- Phase 1 sub-steps complete; Phase 1 Gate 3 REPL smoke is the next gate (operator-supplied fixture)

**1.6 closeout (2026-04-29)**:
- Branch tip: `61f6f6a`
- test-grailzee-ledger-archive: 25 passed / 0 skipped (new)
- test-grailzee-ledger: 201 passed / 0 skipped (+25 from 1.5)
- test-grailzee-eval: 1234 passed / 71 skipped (unchanged skips)
- test-grailzee-cowork: 235 passed / 0 skipped (not re-run; no changes)
- Gate 2 round 1: 0 blocker / 0 major / 1 minor (coverage gap on size-mismatch collision else-branch; fixed before commit with `test_creates_suffixed_path_when_size_differs`)
- Gate 2 round 2: post-fix rerun: 25/25 archive, 201/201 ledger aggregate — clean
- Three drifts corrected: (1) `shutil.move` → `os.rename` / EXDEV not absorbed; (2) idempotency via size+sha256 / `"idempotent_skip"`; (3) `_N`-suffix collision / `"collision_suffixed"`
- Skip-count anomaly resolved: 71 unconditional marker-based skips at both 8eecfe2 and HEAD; +24 archive tests; delta timing artifact (aggregate ran before final test added)
- Carry-forward for spec v1.1 §14 item 7: compact-date filenames (`YYYYMMDD`) would trigger `_TRAILING_N` falsely; ISO-dash format is safe; documented in `_next_archive_path` docstring
- New files: `test_ingest_sales_archive.py` (25 tests)

**1.5 closeout (2026-04-29)**:
- Branch tip: `30cfd7f` (corrective) / `6e81e34` (main commit)
- test-grailzee-ledger: 176 passed / 0 skipped (+17 from 1.4)
- test-grailzee-eval: 1210 passed / 71 skipped (+17 from 1.4)
- test-grailzee-cowork: 235 passed / 0 skipped
- Gate 2 round 1: 0 blocker / 1 major / 3 minor (all addressed: M1 `_row_to_csv_dict` None guard, m1 docstring typo, m2 `window_days=0` test, m3 inner docstring)
- Gate 2 round 2 (post-commit): 0 blocker / 0 major / 2 minor (corrective `30cfd7f`: `is not None` sweep across 5 date fields, `LEDGER_CSV_COLUMNS` module-level import)
- ADR-0004 landed: `sell_date: date` → `date | None`; 13-field nullability audit; `sell_cycle_id` non-optional with 1.7 raise-on-blank obligation
- Data verification: live ledger (14 rows, 2026-04-29) — all `sell_date` populated, all `account` ∈ {NR, RES}; design v1 UNKNOWN-account row evidence not verifiable (design doc not on disk)
- New files: `test_ingest_sales_prune.py` (14 tests), `docs/decisions/ADR-0004-ledger-row-nullability.md`

**1.4 closeout (2026-04-29)**:
- Branch tip: `5d5d47f`
- test-grailzee-ledger: 159 passed / 0 skipped
- test-grailzee-eval: 1193 passed / 71 skipped
- test-grailzee-cowork: 235 passed / 0 skipped
- Gate 2 round 1: 4 major / 5 minor (all addressed before commit)
- Gate 2 round 2: 0 blocker / 0 major / 2 minor (both addressed before commit)
- ADRs landed: ADR-0001 (Rule Y), ADR-0002 (concurrency), ADR-0003 (schema versioning)
- span_exporter fixture: 26 lines in conftest.py (session-scoped provider + function-scoped clear)
- 1.2 OTEL carry-forward closed: rows_emitted-on-exception test in test_ingest_sales_transform.py

---

## Ledger redo key decisions (2026-04-28/29)

**`LedgerRow.sell_date` nullability (ADR-0004)**: `date | None`. Legacy rows that
predate sell_date tracking are represented with `sell_date=None`; they serialize to
empty string in CSV (`_row_to_csv_dict`) and are never pruned. `sell_cycle_id` stays
non-optional — the 1.7 read path must raise on a blank `sell_cycle_id` rather than
silently accept it. All five nullable date fields in `_row_to_csv_dict` use
`if x is not None` guards (not truthiness checks).

**LEDGER_LOCK_DEFAULT**: `~/.grailzee/trade_ledger.lock`
Override via `GRAILZEE_LOCK_PATH` env var. Lock file must be on local filesystem — flock() unreliable on Google Drive FUSE mount. Default is unambiguously local.

**Lockfile env var naming**: `GRAILZEE_LOCK_PATH` follows `GRAILZEE_` prefix convention from `grailzee_common.GRAILZEE_ROOT`. Unlike the data-path resolvers, `_resolve_lock_path()` never raises on missing env — it has a local default.

**`atomic_write_csv` header contract**: Always writes the full file every time including header. No append path. `extrasaction="raise"` for the default-header path (schema contract); `"ignore"` for the explicit-header path (caller elects subset write).

**Float serialization**: `buy_price` and `sell_price` use `f"{v:.2f}"` in `_row_to_csv_dict`. Only two float fields in `LedgerRow`. IEEE 754 precision concern for sub-cent inputs deferred to Phase 2 schema discussion.

**`atomic_write_csv` error contract**: Both `OSError` and `ValueError` (extrasaction violation) are caught and wrapped in `LedgerWriteFailed`.

**Inode re-check (B2)**: `_open_and_lock()` compares `os.fstat(fd.fileno()).st_ino` to `os.stat(path).st_ino` after acquiring flock. Mismatch triggers retry from `open()` with remaining deadline budget. `OSError` from the check block is wrapped in `LockAcquisitionFailed`.

**`§14 surface`**: `grailzee_common.append_ledger_row` is an existing append-write path that `atomic_write_csv` supersedes. The two coexist during Phase 1 (different branches, different call sites).

**m3 carry-forward**: `_wait_for_acquired()` in tests blocks indefinitely if subprocess crashes before writing `"acquired\n"`. Timeout on `readline()` requires `select`; deferred.

**__main__ deferred**: `ingest_sales.py` has no `__main__` block. The 1.7 orchestrator owns the CLI surface; primitives don't need it.

---

## Shape K — status at pause (2026-04-28)

| Item | State |
|---|---|
| Shape K 1a (GRAILZEE_ROOT env-var) | DONE; `a790f5d` + `1e38de7` pushed |
| Shape K 1b (agent surface lockdown) | DONE; `8c9cc8f` + `2ce167f` pushed |
| env object revert (gateway blowup fix) | DONE; `~/.openclaw/openclaw.json` edited directly |
| Rebase onto origin/main | DONE; `994cda3` pushed 2026-04-28 |
| Shape K 1c (plugin scaffold + register evaluate_deal) | DONE; in `994cda3` |
| Shape K 1c.5 (spec-drift fixup) | DONE; in `994cda3` |
| Shape K 1b.5 (stdin dispatch: report_pipeline + ledger_manager) | NEXT on resume |
| Shape K 1d (report_pipeline plugin registration) | NOT STARTED |
| Shape K 1e (update_name_cache plugin registration) | NOT STARTED |
| Shape K 1f (AGENTS.md final pass + SKILL.md hard rules) | NOT STARTED |
| Shape K commit 2 (override wiring + deal.md branch) | NOT STARTED |
| Operator gate (gateway restart + Telegram test) | BLOCKED on 1b.5 + GRAILZEE_ROOT resolution |

**Shape K 1b.5 scope (expanded)**:
1. `report_pipeline.py`: stdin dispatch + error routing to stdout
2. `ledger_manager.py`: stdin dispatch + error routing to stdout
3. `report.md`: fix Steps 2 (dead ls path) and 5 (dead exec path)
4. Confirm `ledger_manager` surface decision (capability file or remove from tools.allow)
5. Confirm GRAILZEE_ROOT injection mechanism

**Shape K commit 2 carry-forwards**:
- Wire `_override_math` into `evaluate()`: new branch on `no_match` + `on_plan` + `max_buy_override`
- New `deal.md` Branch C for `override_match`
- OTEL spans for `_override_math` + `_decision_math`
- Update deal.md math shape (`headroom_pct`) and `match_resolution` enum

---

## Shape K: capability contract review notes (2026-04-28)

### evaluate_deal — Honored
Works correctly post-1c.5. Dual entry: JSON argv → `_run_from_argv`; stdin → `json.loads(sys.stdin.read())`. All errors routed stdout as shaped JSON.

### ledger_manager — Mechanically broken (deferred to Phase D)
Argparse-only. The ledger redo (Track 2) shipped. `ledger_manager` will be removed from `tools.allow` when Shape K closes. Re-evaluate at Shape K 1b.5.

### report_pipeline — Mechanically broken (fix in 1b.5)
Argparse-only. report.md Steps 2 and 5 reference dead `exec` paths.

---

## Pointers

- State truth: `GRAILZEE_SYSTEM_STATE.md` (repo root)
- Decision locks: `docs/decisions/`
- Architecture lock: `docs/decisions/Grailzee_Architecture_Lock_2026-04-26.md`
- Ledger redo design: `Downloads/GZ-4-28.v3/Grailzee_Ledger_Redo_Design_v1.md` (not on disk)
- Plugin API spec: `Grailzee_Plugin_API_Spec_v1.md` — absent from working tree
- Root OpenClaw config: `~/.openclaw/openclaw.json` (outside repo; env object removed 2026-04-28)
- Step 1 mock fixture: `grailzee-cowork/tests/fixtures/mock_strategy_output.json`
- INBOUND apply bundle path: `GrailzeeData/bundles/` (NOT `output/`)
- Full prior build log: `.claude/progress-v0.md`
- WatchTrack fixture (canonical, post-edit): `skills/grailzee-eval/state_seeds/gate3_fixtures/watchtrack_full_final.jsonl` (sha256 `029238eb...`)
- ADRs: `docs/decisions/ADR-0001` through `ADR-0005`
- Production ledger backup: `$GRAILZEE_ROOT/state/trade_ledger.csv.pre-redo-2026-04-29.bak`
