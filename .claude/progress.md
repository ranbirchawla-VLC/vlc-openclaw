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

### Track 2 — Ledger Redo Phase 1 (BLOCKED — extraction contract is hallucinated)

**Next-session entry point — read this first**: Phase 1's transform layer
was built against fabricated data. Operator confirmation 2026-04-29:
previous AI sessions hallucinated the WatchTrack JSONL extraction format
and authored `tey1104_clean.json`, `tey1048_unmatched.json`, etc. as
fictional test fixtures. The implementation, the eight test fixtures
under `skills/grailzee-eval/tests/fixtures/ingest_sales/`, and design v1
§7's "single JSON object with sales/purchases arrays" claim are all
artifacts of that hallucination. Cost: one full day of rework before
the divergence was caught at Gate 3.

**Real production fixture is canonical**:
`skills/grailzee-eval/state_seeds/gate3_fixtures/watchtrack_full_final.jsonl`
(committed at 1f2c140). Use this as the source of truth for the real
WatchTrack extraction shape; don't trust the existing test fixtures or
design v1 §7 wording.

**Salvageable from Phase 1**:
- 1.1 schema scaffolding (LedgerRow, error hierarchy, path resolution) —
  the dataclass shape may need fields revisited but the wrapping is fine
- 1.3 lockfile + atomic_write_csv — operates on LedgerRow, fixture-agnostic
- 1.4 merge_rows (Rule Y) — operates on LedgerRow, fixture-agnostic
- 1.5 prune_by_sell_date — operates on LedgerRow, fixture-agnostic
- 1.6 archive_jsonl — file move, fixture-agnostic
- 1.7 orchestrator composition — calls primitives by interface; transform
  layer is the only piece that needs replacement
- read_ledger_csv (1.7 commit 1) — operates on CSV serialization layer,
  fixture-agnostic

**Not salvageable**:
- 1.2 transform_jsonl + ~60 test cases in test_ingest_sales_transform.py
  built on the hallucinated fixtures
- The eight fixtures themselves under tests/fixtures/ingest_sales/
- Account-derivation logic (NR/RES from Platform fee actual_cost ∈ {49, 99}):
  only 10/95 real Sales carry a Platform fee; values include 352.5, 377.4
  not just 49/99; rule is incomplete or wrong
- Sale↔Purchase 1-to-1 join via stock_id: real Purchases have up to 4
  line_items each, so one Purchase may satisfy buy-side for 4 different
  Sales — hallucinated 1-to-1 model can't represent this
- design v1 §7 wording (single JSON document, sales/purchases arrays,
  one line_item per record, platform as string)

**Tests using hallucinated fixtures**:
- test_ingest_sales_transform.py — entirely (60+ tests on fictional data)
- test_ingest_sales_orchestrator.py — Scenario 2 mid-batch failure
  (tey1092_no_services.json), OTEL halted_schema_shift /
  halted_erp_invalid tests using missing_purchases_key.json /
  tey1092_no_services.json; need re-built against real fixture once the
  new transform layer exists
- test_ingest_sales_integration.py — TestScenario2MidBatchFailureAtomicity
  uses tey1092_no_services.json; Scenario 1 / 4 use inline-constructed
  payloads matching the hallucinated single-doc shape

**The path forward (only viable route)**:
This is now a corrective pass scoped as "Phase 1.2 redo + design v1 §7
amendment + downstream test rebuild." Not a tweak to transform_jsonl.
Concretely:

1. **Read the canonical fixture carefully** before writing any code.
   See "Real format characterization" block below for the audit done
   2026-04-29; verify the audit by re-reading the fixture rather than
   trusting it.
2. **Amend design v1 §7** to specify the JSONL line-delimited format,
   the three record types (Sale / Purchase / Trade), the multi-line_items
   structure, and the real account-derivation rule (whatever it is —
   needs operator input on what NR/RES vs other-platform vs no-Platform-fee
   should map to in the ledger).
3. **Rewrite transform_jsonl** against the new spec. Likely shape:
   parse line by line; bucket by `type`; for each Sale, emit one
   LedgerRow per line_item; join buy-side from any Purchase whose
   line_items contain the matching stock_id; handle Trade records as
   synthetic-Purchase equivalents (or skip them; needs operator decision).
4. **Replace test fixtures** with sliced subsets of the real production
   fixture (one-Sale-one-Purchase clean case, multi-line-item Purchase,
   Trade record, missing-Platform-fee Sale, non-Grailzee Sale, etc.).
   Anonymization may be needed if test fixtures are committed; the
   gate3_fixtures/ copy is the operator-confirmed full file.
5. **Re-run Gate 3** with the canonical fixture against the new transform.

**Open questions for the operator before any code work**:
- Trade records (4 of 184): are these in scope for the ledger? They're
  synthetic Purchase-equivalents derived from prior Sales. Trade-in
  stock_id flows into the buy-side of a future Sale, but the wholesale
  credit is owed not paid in cash. How does this book to NR/RES/UNKNOWN
  account derivation?
- Non-Grailzee platforms (Ebay, Direct, WTA, Chrono24, MODA, empty): the
  hallucinated impl filtered to Grailzee-only via `if "Grailzee" in
  sale.get("platform", "")`. With `platform: list[str]` the membership
  check works for `["Grailzee"]` but the spec needs to confirm: are
  non-Grailzee Sales excluded from the ledger, or do they appear with
  account="UNKNOWN" or some other rule?
- Account derivation when no Platform fee: 85/95 Sales have no Platform
  fee entry at all. Those are mostly non-Grailzee, but there's overlap
  to verify. The hallucinated impl raised ERPBatchInvalid; this won't
  work. Default to UNKNOWN? Skip?
- Platform fee values 352.5 and 377.4: not in {49, 99}. Likely percent-
  of-transaction fees. Needs operator: NR/RES tier rules, or a different
  classification entirely.
- Multi-line_item Purchases: how does merge_rows handle the case where
  a single Purchase row in real data corresponds to N independent
  ledger rows (one per stock_id)? Either transform emits N rows per
  Purchase (likely correct) and merge handles them as siblings, or
  the LedgerRow model needs revisiting.

Working tree clean.

**Branch**: `feature/grailzee-ledger-phase1-v2` (off `feature/grailzee-eval-v2`)
**Tip**: `8d73c35` ([ledger 1.7 commit 2 of 2] integration tests, OTEL outcome
consolidation, CLI surface). Plus pending chore commit for this progress.md.
**Remote**: not pushed yet
**Design spec**: `Downloads/GZ-4-28.v3/Grailzee_Ledger_Redo_Design_v1.md` — not present on disk at last check (2026-04-29). Content referenced from ADRs and session history.
**Tests**: 1342 eval / 71 skipped / 235 cowork / 308 ledger

Skipped-delta note (2026-04-29): baseline 76 skipped recorded on MacStudio; laptop
has 5 additional state-file-conditional tests passing (skipif on installed state files).
71 unconditional skips are fixed; delta is machine-state, not code.

| Sub-step | State | Tip |
|---|---|---|
| 1.1 schema, dataclasses, path resolution | DONE | `3f963af` |
| 1.2 transform_jsonl single-file ingest | DONE | `eb10767` (OTEL corrective) |
| 1.3 lockfile + atomic write | DONE | `43c47d0` (commit A + commit B) |
| 1.4 Rule Y dedup-and-update | DONE | `5d5d47f` |
| 1.5 pruning + ADR-0004 nullability | DONE | `30cfd7f` |
| 1.6 archive move | DONE | `61f6f6a` |
| 1.7 top-level orchestrator | DONE | `8d73c35` (commit 2 of 2) |
| Phase 1 Gate 3 smoke | ATTEMPTED — HALTED | see Gate 3 attempt block below |

---

### Gate 3 — first-attempt outcome (2026-04-29) — BLOCKER

**Status**: attempted; HALTED on stop condition #1 (Step 2 raised). Awaiting
supervisor triage before retry. Atomicity contract held under unplanned failure
(production state byte-identical to pre-run); the architecture is not the
problem.

**Fixture used**: `$GRAILZEE_ROOT/sales_data/watchtrack_full_final.jsonl`
(operator-supplied; original prompt name `watchtrack_full_final__1_.jsonl`
without the download-dedup tail).

**Fixture archived in repo for reuse**:
`skills/grailzee-eval/state_seeds/gate3_fixtures/watchtrack_full_final.jsonl`
(372337 bytes, 184 lines, sha256
`108dd5575edf173b328b7e09ab453f274a051f5a82b6112b2a582b92b216fece`).
Byte-identical to the production fixture as of 2026-04-29. To re-run
Gate 3, copy this file into `$GRAILZEE_ROOT/sales_data/` rather than
re-downloading from the extraction agent — guarantees the same fixture
content the failure was characterized against.

**Failure**: `json.decoder.JSONDecodeError: Extra data: line 2 column 1
(char 4388)` from `_transform_jsonl_inner` line 709 on the first file.

**Two contract gaps surfaced (not one)**:

1. **Parse strategy**. `_transform_jsonl_inner` calls `json.loads(path.read_text())`
   expecting a single JSON document. Production fixture is true JSONL
   (line-delimited, one JSON object per line). Function name `transform_jsonl`
   matches conventional `.jsonl` semantics but implementation matches design
   v1 §7's "single JSON object" claim.

2. **Schema shape**. Each line of the production fixture is a flat transaction
   record discriminated by a `type` field:
   ```
   {"transaction_id": "TEYPA1088", "type": "Purchase", ...}    (line 1, 4388 chars)
   {"transaction_id": "TEY1104",   "type": "Sale",     ...}    (line 2)
   ```
   Implementation expects nested arrays:
   ```
   {"sales": [{...}, {...}], "purchases": [{...}, {...}]}
   ```
   Even with a JSONL reader bolted on, transform would still fail on the
   `for key in ("sales", "purchases"): if key not in raw` guard — neither
   key exists in the flat schema.

**Atomicity ✅**. Pre-lock raise meant: lock never acquired, archive loop
never entered, no partial CSV writes. Post-state is byte-identical to
pre-state (sales_data/ still has the fixture, archive/ still doesn't exist,
ledger still 15 lines = 1 header + 14 rows). Gate 3 verified the
atomicity contract under an unplanned failure mode — a real win for
commit 1's architecture even though the run failed.

**OTEL silence**. `JSONDecodeError` is a `ValueError` subclass, not an
`IngestError`. The pre-lock `try/except IngestError` did NOT catch it; the
orchestrator span closed without an `outcome` attribute (consistent with
`TestBareExceptionInLock`). The Phase 2 bot route would surface this as an
unhandled traceback rather than a structured halt — small wrap-into-
SchemaShiftDetected follow-up regardless of which triage route is chosen.

**Triage outcome (2026-04-29 supervisor confirmation)**: there is no
"Route A — spec correct, fixture wrong" — that framing in this file's
earlier draft was wrong. Design v1 §7 and the existing test fixtures
were both authored by previous AI sessions against hallucinated data,
not real WatchTrack output. The corrective-pass scope (full Phase 1.2
redo + spec amendment + test rebuild) is documented in the
"Next-session entry point" block at the top of Track 2. Estimated
session size: large.

**Real format characterization (2026-04-29 audit of canonical fixture)**:

Audit method: parsed `state_seeds/gate3_fixtures/watchtrack_full_final.jsonl`
line by line; counted record types, status values, top-level keys,
platform values, line_items multiplicity, service-name distribution,
Platform-fee actual_cost distribution. 184 records total.

- **Document shape**: JSONL (one JSON object per line). Not a single
  document with nested arrays.
- **Record type distribution**: Sale (95), Purchase (85), Trade (4).
  Trade is a synthetic Purchase-equivalent: `type: "Trade"`,
  `source: "synthetic_trade_in"`, `derived_from_transaction: <sale_id>`.
- **Status distribution**: Received (88), Fulfilled (88), Pending (8).
- **Top-level keys (union across all records)**: additional_purchase_fees,
  agreement_state, balance_due, client (dict), completed_at, created_at,
  credit_owed_on_trade_in, data_quality (Sales only), derived_from_transaction
  (Trades only), extracted_at, line_items, merchant_fee, payments,
  payments_made_count, payments_made_total, platform, sales_associate,
  services, shipping_charge, source (Trades only), source_url, status,
  transaction_id, transaction_notes, transaction_sales_tax,
  transaction_sales_tax_rate, transaction_total, type.
- **`platform`**: list[str], not string. 7 distinct values across Sales:
  Grailzee (21), Direct (22), WTA (19), Ebay (8), Chrono24 (4), MODA (2),
  empty list (19).
- **`line_items`**: plural list, not singular `line_item`. Counts:
  Purchases — 1×80, 2×1, 3×3, 4×1; Sales — 1×89, 2×6; Trades — 1×4.
  Each line_item has 28 keys including: brand, condition, cost_of_item,
  delivered_date, delivery_status, fulfillment_date, in_transit_date,
  included_items, is_consignment, is_trade_in, item_uuid, line_state,
  model, production_month, production_year, reference_number,
  retail_price, sales_tax, serial_number, shipping_method, sold_date,
  stock_id, tracking_added_date, tracking_link, tracking_number,
  unit_price, watch_name, wholesale_price.
- **Services on Sales** (top names): Platform fee (10), Shipping (4),
  CC FEE (2), Auction Fee (2), and one-offs: Credit Card Fee, shipping
  (lower-case), Shipping Overnight, CC Fee, Chrono Fee, Commission.
- **Platform fee actual_cost distribution**: 49 (×6), 99 (×2), 352.5 (×1),
  377.4 (×1). Only 10/95 Sales carry a Platform fee at all; the
  hallucinated NR/RES dichotomy on {49, 99} covers 8/95 Sales.

**Reproduction note for retry session**:
- `GRAILZEE_ROOT` is NOT set in fresh login shells; export it explicitly:
  `export GRAILZEE_ROOT="/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Shared Drive/GrailzeeData"`
- `LEDGER_LOCK_DEFAULT` resolves to `~/.grailzee/trade_ledger.lock` (local FS,
  per ADR-0002); no override needed.
- Gate 3 invocation (post-cd):
  `cd skills/grailzee-eval && python3.12 -c "from scripts.ingest_sales import ingest_sales; m = ingest_sales(); print(m)"`

---

## Sub-step closeouts

**Gate 3 attempt (2026-04-29)**: HALTED on JSONDecodeError; see Gate 3 block
above for full triage. No state changes; no commits beyond this progress.md
chore. Atomicity contract verified under unplanned failure.

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
- Ledger redo design: `Downloads/GZ-4-28.v3/Grailzee_Ledger_Redo_Design_v1.md` (not on disk)
- Ledger audit: `skills/grailzee-eval/docs/Ledger_Audit_2026-04-28.md` (untracked)
- Plugin API spec: `Grailzee_Plugin_API_Spec_v1.md` — absent from working tree (see §15 of design v1)
- Root OpenClaw config: `~/.openclaw/openclaw.json` (outside repo; env object removed 2026-04-28)
- Step 1 mock fixture: `grailzee-cowork/tests/fixtures/mock_strategy_output.json`
- INBOUND apply bundle path: `GrailzeeData/bundles/` (NOT `output/`)
- Full prior build log: `.claude/progress-v0.md`
- Gate 3 production fixture (archived for reuse): `skills/grailzee-eval/state_seeds/gate3_fixtures/watchtrack_full_final.jsonl`
