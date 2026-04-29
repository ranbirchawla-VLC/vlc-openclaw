# progress.md — Grailzee Eval v2 / Ledger Redo Phase 1

**Working root**: `/Users/ranbirchawla/ai-code/vlc-openclaw` (not `.openclaw/workspace`)
**Canonical state doc**: `GRAILZEE_SYSTEM_STATE.md` at repo root. Read that first.

Session-open protocol: read `GRAILZEE_SYSTEM_STATE.md`, then this file.

---

## Active tracks

### Track 1 — Shape K (PAUSED)

**Branch**: `feature/grailzee-eval-v2`
**Remote**: pushed `994cda3` (2026-04-28; rebase onto origin/main complete)
**Rebase note**: 2026-04-28 laptop rebase completed. Conflicts in `pytest.ini` (×2), `claude.md` (delete-accept), `CLAUDE.md` (rebase artifact — restored from ORIG_HEAD), `.claude/settings.json`, `Makefile` (×2). All resolved. Post-rebase counts: 1117/76/235.

**Carry-forward**: `PYTEST = python3.12 -m pytest` was applied in the working tree to fix missing `opentelemetry`/`openpyxl` on the laptop venv, but not committed before the branch was paused. One-line Makefile fix needed on next open.

**Next up on resume**: Shape K 1b.5 (stdin dispatch for report_pipeline + ledger_manager). See full scope below.

---

### Track 2 — Ledger Redo Phase 1 (ACTIVE)

**Branch**: `feature/grailzee-ledger-phase1-v2` (off `feature/grailzee-eval-v2`)
**Remote**: not pushed yet
**Design spec**: `Downloads/GZ-4-28.v3/Grailzee_Ledger_Redo_Design_v1.md`
**Tests**: 1152 eval / 76 skipped / 235 cowork / 123 ledger

| Sub-step | State | Tip |
|---|---|---|
| 1.1 schema, dataclasses, path resolution | DONE | `3f963af` |
| 1.2 transform_jsonl single-file ingest | DONE | `eb10767` (OTEL corrective) |
| 1.3 lockfile + atomic write | DONE | `43c47d0` (commit A + commit B) |
| 1.4 Rule Y dedup-and-update | NEXT UP | — |
| 1.5 pruning | NOT STARTED | — |
| 1.6 archive move | NOT STARTED | — |
| 1.7 top-level orchestrator | NOT STARTED | — |
| Phase 1 Gate 3 smoke | NOT STARTED | — |

---

## Ledger redo key decisions (2026-04-28/29)

**LEDGER_LOCK_DEFAULT**: `~/.grailzee/trade_ledger.lock`
Override via `GRAILZEE_LOCK_PATH` env var. Lock file must be on local filesystem — flock() unreliable on Google Drive FUSE mount. Default is unambiguously local.

**Lockfile env var naming**: `GRAILZEE_LOCK_PATH` follows `GRAILZEE_` prefix convention from `grailzee_common.GRAILZEE_ROOT`. Unlike the data-path resolvers, `_resolve_lock_path()` never raises on missing env — it has a local default.

**`atomic_write_csv` header contract**: Always writes the full file every time including header. No append path. `extrasaction="raise"` for the default-header path (schema contract); `"ignore"` for the explicit-header path (caller elects subset write).

**Float serialization**: `buy_price` and `sell_price` use `f"{v:.2f}"` in `_row_to_csv_dict`. Only two float fields in `LedgerRow`. IEEE 754 precision concern for sub-cent inputs deferred to Phase 2 schema discussion.

**`atomic_write_csv` error contract**: Both `OSError` and `ValueError` (extrasaction violation) are caught and wrapped in `LedgerWriteFailed`.

**Inode re-check (B2)**: `_open_and_lock()` compares `os.fstat(fd.fileno()).st_ino` to `os.stat(path).st_ino` after acquiring flock. Mismatch triggers retry from `open()` with remaining deadline budget. `OSError` from the check block is wrapped in `LockAcquisitionFailed`.

**`§14 surface**: `grailzee_common.append_ledger_row` is an existing append-write path that `atomic_write_csv` supersedes. The two coexist during Phase 1 (different branches, different call sites).

**m3 carry-forward**: `_wait_for_acquired()` in tests blocks indefinitely if subprocess crashes before writing `"acquired\n"`. Timeout on `readline()` requires `select`; deferred.

**__main__ deferred**: `ingest_sales.py` has no `__main__` block. The 1.7 orchestrator owns the CLI surface; primitives don't need it.

---

## Ledger redo sub-step 1.3 fixture inventory

7 fixture files under `skills/grailzee-eval/tests/fixtures/ingest_sales/`:
- `tey1104_clean.json` — fully matched Sale + Purchase
- `tey1048_unmatched.json` — Sale with no matching Purchase (RES account)
- `tey1080_multi_payment.json` — Purchase with 3 payment dates (min = 2026-03-29)
- `tey1081_auction_fee.json` — ERPBatchInvalid: "Auction Fee" service name
- `tey1091_cc_fee_only.json` — ERPBatchInvalid: CC FEE only
- `tey1092_no_services.json` — ERPBatchInvalid: empty services[]
- `missing_purchases_key.json` — SchemaShiftDetected: no "purchases" top-level key
- `non_grailzee.json` — eBay platform, filtered out

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

### ledger_manager — Mechanically broken (deferred to Phase D / ledger redo)
Argparse-only. The ledger redo (Track 2) supersedes the Telegram log path entirely. `ledger_manager` will be removed from `tools.allow` when the redo ships. Operator gate for Shape K should proceed without it; re-evaluate at Shape K 1b.5.

### report_pipeline — Mechanically broken (fix in 1b.5)
Argparse-only. report.md Steps 2 and 5 reference dead `exec` paths.

---

## Pointers

- State truth: `GRAILZEE_SYSTEM_STATE.md` (repo root)
- Decision locks: `docs/decisions/`
- Architecture lock: `docs/decisions/Grailzee_Architecture_Lock_2026-04-26.md`
- Ledger redo design: `Downloads/GZ-4-28.v3/Grailzee_Ledger_Redo_Design_v1.md`
- Ledger audit: `skills/grailzee-eval/docs/Ledger_Audit_2026-04-28.md` (untracked)
- Plugin API spec: `Grailzee_Plugin_API_Spec_v1.md` — absent from working tree (see §15 of design v1)
- Root OpenClaw config: `~/.openclaw/openclaw.json` (outside repo; env object removed 2026-04-28)
- Step 1 mock fixture: `grailzee-cowork/tests/fixtures/mock_strategy_output.json`
- INBOUND apply bundle path: `GrailzeeData/bundles/` (NOT `output/`)
- Full prior build log: `.claude/progress-v0.md`
