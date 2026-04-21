# Grailzee OTEL Coverage Audit — Task 0.1

**Date:** 2026-04-21
**Branch:** `feature/grailzee-eval-v2` (HEAD `73407c0`)
**Scope:** Read-only audit, no changes. Phase 0 gate before schema refactor.

---

## 0. Scope caveats (surface first)

Two prerequisites named in CLAUDE.md and the task spec do not exist on disk as named. Calling this out before findings so the reader can interpret paths correctly:

1. **`skills/grailzee-eval-v2/`** (CLAUDE.md lines 9, 78; task spec "Scope") **does not exist**. The analyzer lives at `skills/grailzee-eval/scripts/` (v2 is the branch name `feature/grailzee-eval-v2`, not a sibling directory — v1 was deleted in Phase 22–23 per progress.md). All paths in this report are relative to `skills/grailzee-eval/`.

2. **`grailzee_schema_design_v1.md`** and **`v1_1.md`** (CLAUDE.md line 10, task spec header) **do not exist** anywhere in the workspace (searched entire tree for `*schema*` / `*design*` — matches are all unrelated JSON schemas under other skills). Audit findings below do not depend on them, but the phrase "canonical Grailzee attribute set" references CLAUDE.md's list (`cycle_id, source_report, references_count`) which may be superseded by these missing docs.

---

## 1. Configuration state

### Exporter

**Wired:** OTLP HTTP exporter, batched, gated on `OTEL_EXPORTER_OTLP_ENDPOINT`.
Single source in `scripts/grailzee_common.py:537-573` (`_init_tracer_provider`):

- If `OTEL_EXPORTER_OTLP_ENDPOINT` unset → no provider installed, `get_tracer()` returns a no-op.
- If set → `TracerProvider` with `Resource({"service.name": $OTEL_SERVICE_NAME})`, `BatchSpanProcessor(OTLPSpanExporter())`.
- Idempotent via module-level `_tracer_provider_initialized` flag.
- `ImportError` → silent no-op. Any other `Exception` → stderr warning, no crash.

**Not wired:** Console exporter. No `ConsoleSpanExporter` in the tree — there is no local-visible tracing path today. Tests and dry runs emit nothing.

### Environment variables

| Var | Default | Read at |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset → no-op | `grailzee_common.py:548` |
| `OTEL_SERVICE_NAME` | `"grailzee-eval"` | `grailzee_common.py:562` |
| `OTEL_EXPORTER_OTLP_HEADERS` | n/a (read by OTLPSpanExporter internally) | documented in comment `grailzee_common.py:528` |

No custom env vars beyond OTLP SDK conventions. No `.env` template in repo.

### Dependencies — `skills/grailzee-eval/requirements.txt`

```
opentelemetry-api>=1.25.0
opentelemetry-sdk>=1.25.0
opentelemetry-exporter-otlp-proto-http>=1.25.0
```

**Installed locally (this machine):** all at `1.41.0`, plus `opentelemetry-exporter-otlp-proto-common 1.41.0`, `opentelemetry-proto 1.41.0`, `opentelemetry-semantic-conventions 0.62b0` (transitive).

**Discrepancy with CLAUDE.md line 68:** CLAUDE.md names `opentelemetry-exporter-otlp` (the meta-package that includes both gRPC and HTTP flavors). `requirements.txt` pins only `opentelemetry-exporter-otlp-proto-http`. The wired exporter is HTTP-only (`grailzee_common.py:558-560`), so HTTP-only is functionally sufficient. Flagged as minor wording drift; no operational gap.

**`requirements-dev.txt`:** `-r requirements.txt` + `pytest-cov>=4.0.0`. No additional OTel packages.

---

## 2. Per-script coverage map

22 `.py` files in `scripts/` (including `__init__.py` empty module + `grailzee_common.py` library).

Legend: ✓ full · ◐ partial (entry only, inner stages bare) · ✗ none. "Top-level" = CLI `main()` or public `run()`. "Inner stages" = sub-operations within a top-level span.

| Script | Top-level | Inner stages | Notes |
|---|---|---|---|
| `__init__.py` | n/a | n/a | Empty package marker. |
| `grailzee_common.py` | n/a | n/a | Provides tracer factory; pure library, no operational spans (correct). |
| `analyze_brands.py` | ✓ `analyze_brands.run` | — | `main()`-level; pure in-memory rollup, inner stages not warranted. Attrs: `csv_count`, `brand_count`. |
| `analyze_breakouts.py` | ✓ `analyze_breakouts.run` | — | Attrs: `curr_csv`, `has_prev`, `breakout_count`. |
| `analyze_changes.py` | ✓ `analyze_changes.run` | — | Attrs: `curr_csv`, `has_prev`, `emerged_count`, `shifted_count`, `faded_count`, `unnamed_count`. |
| `analyze_references.py` | ✓ `analyze_references.run` | — | Attrs: `csv_count`, `references_scored`, `unnamed_count`, `total_sales`. Scoring loop inside is CPU-bound pure-compute; finer spans would be noise. |
| `analyze_trends.py` | ✓ `analyze_trends.run` | — | Attrs: `csv_count`, `period_count`, `trend_count`, `momentum_refs`. |
| `analyze_watchlist.py` | ✓ `analyze_watchlist.run` | — | Attrs: `curr_csv`, `has_prev`, `watchlist_count`. |
| `backfill_ledger.py` | ✗ | ✗ | **GAP.** No tracer import. `main()` (line 523) performs atomic CSV rewrite with `read_input`, `validate_all`, `filter_duplicates`, `write_ledger_atomic`, `post_write_hooks` — all untraced. Only standalone CLI of the 22. |
| `build_brief.py` | ✓ `build_brief.run` | — | Attrs: `json_path`. Thin; other useful attrs (ref_count, brand_count, cycle_id) not set. |
| `build_spreadsheet.py` | ✓ `build_spreadsheet.run` | — | Attrs: `output_path`. Thin; xlsx has 3 sheets, no stage breakdown. |
| `build_summary.py` | ✓ `build_summary.run` | — | Attrs: `output_path`. Thin. |
| `evaluate_deal.py` | ✓ `evaluate_deal` | — | Rich: `brand`, `reference`, `purchase_price`, `status` (branches: `error`, `not_found`, `ok`), `grailzee` (decision), `data_source`. Best attribute coverage in the tree. |
| `ingest_report.py` | ✓ `ingest_report.run` | — | Attrs: `input_path`, `output_path`, `rows_written`, `rows_skipped`, `sell_through_joined`, `sell_through_missing`, `warning_count`. Inner stages (Excel parse, CSV write, sell-through join) are one span; arguably worth splitting. |
| `ledger_manager.py` | ✓ four spans (`ledger_log`, `ledger_summary`, `ledger_premium`, `ledger_cycle_rollup`) | ✓ by CLI subcommand | Most granular span taxonomy in tree. Attrs: `brand`, `reference`, `account`, `cycle_id`, `buy_price`, `sell_price`, `filter.brand`, `filter.reference`, `filter.cycle_id`, `trade_count`, `threshold_met`. |
| `query_targets.py` | ✓ `query_targets.run` | — | Attrs: `cache_path`, `strong_count`, `normal_count`. Uses `record_exception` + `set_status(StatusCode.ERROR)`. |
| `read_ledger.py` | ◐ (library-only; no CLI) | ✗ | No tracer module-level. Consumers `run_analysis.py:147`, `ledger_manager.py`, `evaluate_deal.py`, `roll_cycle.py` all call under their own spans, so calls are parent-traced. Three public functions (`run`, `reference_confidence`, `cycle_rollup`) never originate a span. Acceptable since the module has no standalone entry. Flagged for completeness. |
| `report_pipeline.py` | ✓ two spans (`report_pipeline.ingest_glob`, `report_pipeline.run`) | ✓ | Attrs: `input_report`, `csv_dir`, `trend_window`, `output_csv`, `rows_written`, `csv_count`, `csv_newest`, `csv_oldest`, `cycle_id`, `unnamed_count`. Uses `record_exception` + `set_status`. |
| `roll_cycle.py` | ✓ `roll_cycle.run` | — | Attrs: `cycle_id`, `total_trades`. |
| `run_analysis.py` | ✓ `run_analysis` + 12 inner spans | ✓ | Orchestrator. Inner spans: `analyze_references.run`, `analyze_trends.run`, `analyze_changes.run`, `analyze_breakouts.run`, `analyze_watchlist.run`, `analyze_brands.run`, `read_ledger.run`, `roll_cycle.run`, `build_spreadsheet.run`, `build_summary.run`, `build_brief.run`, `write_cache.run`. Every inner block uses `try/except` + `record_exception` + `set_status(StatusCode.ERROR)`. **Span name collision risk noted**: inner span names are identical to the child scripts' CLI-level span names (e.g. `analyze_references.run`). Since the child scripts put their spans in `main()`, not the library `run()`, only one fires per invocation (the orchestrator's). Not a bug; just worth noting for future refactor — if a child script moves its span into its library `run`, traces will double-span. |
| `seed_name_cache.py` | ✓ `seed_name_cache` | — | Attrs: `target`, `dry_run`, `force`, `seed_count`, `drive_reachable`, `existing_count`, `added_count`. |
| `write_cache.py` | ✓ `write_cache.run` | — | Attrs: `cache_path` only. Thin — doesn't emit `cycle_id`, `references_count`, or backup-rotation outcome despite handling both. |

**Summary:** 20 of 22 files instrumented at top-level. 1 gap (`backfill_ledger.py`). 1 deliberate library module (`read_ledger.py`) with no standalone entry — always parent-traced.

---

## 3. Attribute consistency

### What's actually used (unioned across tree)

Identifiers: `brand`, `reference`, `account`, `purchase_price`, `target`, `cycle_id`, `previous_cycle_id`, `buy_price`, `sell_price`

Paths/inputs: `input_path`, `input_report`, `curr_csv`, `csv_path`, `csv_dir`, `csv_newest`, `csv_oldest`, `cache_path`, `output_path`, `output_csv`, `json_path`

Counts: `csv_count`, `refs_count`, `references_scored`, `total_sales`, `trade_count`, `period_count`, `trend_count`, `momentum_refs`, `breakout_count`, `watchlist_count`, `brand_count`, `emerged_count`, `shifted_count`, `faded_count`, `unnamed_count`, `strong_count`, `normal_count`, `seed_count`, `existing_count`, `added_count`, `rows_written`, `rows_skipped`, `warning_count`, `total_trades`

Flags/state: `has_prev`, `dry_run`, `force`, `drive_reachable`, `threshold_met`, `sell_through_joined`, `sell_through_missing`, `status` (values: `error`, `not_found`, `ok`), `grailzee`, `data_source`

Filters: `filter.brand`, `filter.reference`, `filter.cycle_id`

Other: `trend_window`

### Inconsistencies

1. **Same concept, two names** — references count:
   - `analyze_references.py:328` emits `references_scored`
   - `run_analysis.py:84,137,197,223` emits `refs_count`
   - Task spec / CLAUDE.md canonical candidate: `references_count`
2. **Same concept, two names** — input path:
   - `ingest_report.py:399` emits `input_path`
   - `report_pipeline.py:63,117` emits `input_report`
3. **Same concept, two names** — output path:
   - Most scripts use `output_path`
   - `ingest_report.py:423` and `report_pipeline.py:70` also use `output_csv` (for a different but overlapping semantic)
4. **CLAUDE.md canonical `source_report` is never emitted.** The variable is computed in `run_analysis.py:76` but not set as a span attribute anywhere.
5. **`cycle_id` emission is patchy.** Emitted in: `ledger_manager.py` (2×), `roll_cycle.py`, `run_analysis.py` (3×), `report_pipeline.py`. Not emitted where the script knows or can derive cycle_id: `analyze_references`, `analyze_trends`, `analyze_changes`, `analyze_breakouts`, `analyze_watchlist`, `analyze_brands`, `build_brief`, `build_spreadsheet`, `build_summary`, `write_cache`, `query_targets`, `seed_name_cache`, `ingest_report`, `evaluate_deal`.
6. **Trade count naming** — `ledger_manager.py:175` and `run_analysis.py:150` emit `trade_count`; `roll_cycle.py:92` emits `total_trades`. Probably different semantics (one is per-cycle rollup total, the other is ledger-scan count) but the naming doesn't disambiguate.
7. **Status handling is inconsistent.** 3 scripts (`run_analysis`, `report_pipeline`, `query_targets`) use explicit `try/except` + `record_exception` + `set_status(StatusCode.ERROR)` inside every span. The other 17 let exceptions propagate and rely on SDK default behavior (which since opentelemetry-sdk 1.15+ does record exceptions automatically on abnormal span exit). Functionally equivalent, but the explicit pattern produces clearer traces and uniform error status. Worth standardising or deliberately picking one.

### Recommended canonical attribute set (for remediation phases, if/when run)

From CLAUDE.md's candidates plus what the code already uses, in priority order:

| Attribute | Applies to | Current state |
|---|---|---|
| `cycle_id` | Every span whose script can resolve it (analyzer, ingest, cache, brief, summary, spreadsheet, deal eval, etc.) | Partial — 6 of 20 instrumented scripts emit it |
| `source_report` | Every span whose script knows the originating report filename | Zero emission today |
| `references_count` | Every span that touches the ref universe | Emitted as `refs_count` / `references_scored` — needs one name |
| `trades_processed` | Every span that reads the ledger | Emitted as `trade_count` and `total_trades` — needs clarification |
| `brand_count` | Brand-rollup-producing spans | Already canonical (`analyze_brands`, `run_analysis`) |

Additional, per-script stable attrs already in use that should be preserved:
`has_prev` (two-period analyzers), `status` (evaluate_deal's error-path branches), `threshold_met` (premium), `filter.*` namespace (ledger_manager queries).

---

## 4. Shared instrumentation module — status

**Present and canonical.** `scripts/grailzee_common.py:540-617`:

- `get_tracer(name)` — factory used by every instrumented script (13 imports). Returns real tracer when SDK installed + endpoint configured, else `_NoOpTracer`.
- `_init_tracer_provider()` — one-time idempotent setup.
- `_NoOpTracer` + `_NoOpSpan` — minimum viable context-manager interface: `__enter__`/`__exit__`, `set_attribute`, `set_status`, `record_exception`. No `add_event` stub, but no script calls `add_event` today.

Import pattern is uniform across all 13 consumer scripts:

```python
from scripts.grailzee_common import get_tracer  # or similar
tracer = get_tracer(__name__)
```

No script sets up its own `TracerProvider`, its own exporter, or its own semantic-conventions imports. Single source of truth.

**Minor completeness gaps in the shared module:**

- Resource attributes set: only `service.name`. Could add `service.version`, `deployment.environment` (dev/prod), `service.namespace` ("vardalux"). Not required by anything today.
- No helper for the common "wrap a function call, set cycle_id + source_report, record exceptions" pattern that's duplicated 12 times in `run_analysis.py`. Candidate for a small decorator or `@contextmanager` if the pattern spreads.

---

## 5. Gaps list

Discrete items, in priority order for the refactor:

1. **`backfill_ledger.py` is fully untraced.** Historical trade import — the only CLI-surface script with zero observability. `write_ledger_atomic` is the most consequential operation (single atomic rewrite of the authoritative ledger file); invocations today are invisible to any collector.
2. **`source_report` is never emitted as a span attribute**, despite being named as canonical and computed in `run_analysis.py`. Zero spans would tell you which report filename drove the run.
3. **`cycle_id` emission is patchy.** 14 of 20 instrumented scripts can resolve cycle_id (directly or from CSV filename) but don't set it. Traces can't be filtered/grouped by cycle today except on the spans that do.
4. **`references_count` vs `refs_count` vs `references_scored`** — three names, one concept. Whichever single canonical name is picked for v1.1, remediation would rename both existing variants.
5. **Error handling is inconsistent** between scripts that wrap spans in `try/except` + explicit status and scripts that don't. Pick one; SDK default is acceptable, but make the choice deliberate.
6. **`write_cache.py` emits only `cache_path`** despite having `cycle_id`, `references_count`, and backup-rotation outcome all in scope. Thin instrumentation on the one span that writes the authoritative agent state.
7. **`ingest_report.py` has one span covering three distinct stages** (Excel parse, normalize/CSV write, sell-through join). Failure modes differ per stage; separate spans would make trace-time debugging cleaner. Lower priority — not a coverage gap per CLAUDE.md's "top-level spans" rule, which is satisfied.
8. **No console exporter wired.** Local dev and test runs emit nothing. Adding a `ConsoleSpanExporter` toggled by `GRAILZEE_OTEL_CONSOLE=1` (or similar) would make instrumentation visible during iteration without a collector. Not a correctness gap — just a dev-experience gap.
9. **`opentelemetry-exporter-otlp` wording in CLAUDE.md line 68** vs `opentelemetry-exporter-otlp-proto-http` in requirements.txt. Wording drift only; either update CLAUDE.md to match the HTTP-specific pin, or broaden the pin to the meta-package. No runtime impact.

---

## 6. Recommended remediation tasks

Proposed numbering continues from 0.1. Each is independently commissionable, scoped narrowly, and verifiable from the commit diff alone. Run before A.1 only the tasks marked **[blocks A.1]**; the rest can slot anywhere in the refactor.

### **0.2** — Instrument `backfill_ledger.py` at top level **[blocks A.1]**

**Scope:** Add `tracer = get_tracer(__name__)` and wrap `main()` in a `backfill_ledger.main` span. Emit `input_path`, `dry_run`, `force`, `rows_read`, `rows_valid`, `rows_written`, `rows_skipped_duplicate`, `warning_count`. If the canonical attribute set from 0.5 is agreed first, also emit `cycle_id` (derived in the script).

**Files touched:** `skills/grailzee-eval/scripts/backfill_ledger.py` (one).

**Verification:** pytest `tests/test_backfill_ledger.py` green; span emission observable via `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` + a local collector or by stubbing the tracer in tests.

### **0.3** — Add `source_report` and `cycle_id` to every span that can resolve them **[blocks A.1]**

**Scope:** Threading two attributes through the 14 scripts that know them:
- `source_report`: derived from `Path(csv_path).name` in analyzer + ingest contexts
- `cycle_id`: derived via `cycle_id_from_csv()` (already in `grailzee_common.py`) or read from the analysis cache

Scripts affected: `analyze_references`, `analyze_trends`, `analyze_changes`, `analyze_breakouts`, `analyze_watchlist`, `analyze_brands`, `build_brief`, `build_spreadsheet`, `build_summary`, `write_cache`, `query_targets`, `ingest_report`, `evaluate_deal`, `run_analysis` (orchestrator spans that currently skip it).

**Files touched:** up to 14 scripts, each one-to-three-line additions inside existing span blocks.

**Verification:** pytest suite green; manual trace inspection confirms both attributes present on every span.

### **0.4** — Unify references-count attribute name

**Scope:** Decide on canonical name (recommend `references_count` per CLAUDE.md), replace `refs_count` (5 sites in `run_analysis.py`) and `references_scored` (1 site in `analyze_references.py`) with it. Same operation for `trade_count` vs `total_trades` if the semantics allow unification.

**Files touched:** `analyze_references.py`, `run_analysis.py`, possibly `ledger_manager.py`, `roll_cycle.py`.

**Verification:** grep confirms no remaining occurrences of the retired names; test suite green.

### **0.5** — Standardise span error handling

**Scope:** Pick one of (a) explicit `try/except` + `record_exception` + `set_status(StatusCode.ERROR)` around every span body (current pattern in `run_analysis`, `report_pipeline`, `query_targets`) or (b) rely on SDK default (current pattern in 17 other scripts). Apply uniformly. Recommendation: (b) is less noise, SDK handles it, and scripts don't currently need to distinguish handled-vs-unhandled failures.

**Files touched:** 3 scripts if going (b); 17 if going (a).

**Verification:** grep for `StatusCode` / `record_exception` matches expected set; span status visible in traces for a deliberately-failed invocation.

### **0.6** — Thicken `write_cache.py` attributes

**Scope:** Add `cycle_id`, `references_count`, `backup_rotated` (bool), `backup_count` to the `write_cache.run` span. These are all already in scope at call time.

**Files touched:** `write_cache.py` (one).

**Verification:** pytest suite green; trace shows all four attributes on `write_cache.run`.

### **0.7** — Split `ingest_report.run` into stage spans (optional, lower priority)

**Scope:** Inner spans for `parse_excel`, `normalize_rows`, `write_csv`, `join_sell_through`. Emit stage-specific row counts.

**Files touched:** `ingest_report.py` (one).

**Verification:** pytest suite green; trace shows 4 nested spans under `ingest_report.run`.

### **0.8** — Add console exporter toggle (optional, dev experience)

**Scope:** In `grailzee_common._init_tracer_provider()`, additionally install a `ConsoleSpanExporter` with `SimpleSpanProcessor` when `GRAILZEE_OTEL_CONSOLE=1`. Does not conflict with OTLP exporter.

**Files touched:** `grailzee_common.py` (one).

**Verification:** `GRAILZEE_OTEL_CONSOLE=1 python scripts/analyze_references.py ...` prints spans to stderr; unset: no output change.

### **0.9** — Resolve `requirements.txt` vs CLAUDE.md wording (optional, docs-only)

**Scope:** Either amend CLAUDE.md line 68 to `opentelemetry-exporter-otlp-proto-http` (match pin), or broaden `requirements.txt` to `opentelemetry-exporter-otlp` (the meta-package, at the cost of pulling in gRPC deps unused today).

**Files touched:** `CLAUDE.md` **or** `skills/grailzee-eval/requirements.txt` — pick one.

**Verification:** grep matches; install resolves cleanly.

---

## 7. Final recommendation

**Run 0.2 and 0.3 before A.1. Defer 0.4–0.9 to in-line with the refactor or a dedicated cleanup sweep.**

Reasoning:

- **0.2 (backfill_ledger)** — only fully untraced CLI in the tree, and the one that modifies authoritative ledger state atomically. Leaving it blind through the schema refactor means A-series invocations that include historical backfills will have observability holes exactly where schema migrations are most likely to surface bugs.
- **0.3 (`source_report` + `cycle_id` everywhere)** — CLAUDE.md names these as canonical. Adding them after the A-series introduces more rename churn in already-changed files. Easier to set the canonical baseline first.
- **0.4 (attribute rename)** — desirable but non-blocking; `refs_count` / `references_scored` drift doesn't hide failures, just makes dashboards uglier.
- **0.5 (error handling)** — tolerable as-is thanks to SDK default behavior; deliberate choice can be made any time.
- **0.6–0.9** — nice-to-have, orthogonal to the schema work.

Net state today is "clean coverage at top level with one real gap (backfill) plus one canonical-attribute gap that matters for observability queries." Not "significant gaps" in the sense of broken or missing infrastructure — the shared module is well-designed, the no-op fallback is correct, and the trace skeleton is consistent. The refactor does not need to stop and build instrumentation from scratch; it needs two small pre-tasks to close the two gaps that will otherwise bite during A.x migrations.

---

## 8. Close-out notes

**Report path:** `state/grailzee_otel_audit.md` (created `state/` directory — was an empty workspace-root dir that existed but was unused).

**Top-level finding:** **minor gaps**. Instrumentation infrastructure is well-built; 19 of 20 instrumented scripts hit the CLAUDE.md top-level standard. Two discrete pre-tasks close the remaining surface (0.2 + 0.3). Not "clean" because `backfill_ledger.py` and `source_report` are both real gaps CLAUDE.md implicitly requires; not "significant" because nothing is broken, just incomplete.

**Read outside audit scope (and why):**

- `CLAUDE.md` (project) — task spec references "standing per-task standard" and "CLAUDE.md"; needed to verify the OTEL Standard section (lines 36–41), the canonical attribute list, and the dependency carve-out (line 67–68).
- `~/.claude/CLAUDE.md` (global) — OTEL observability policy (line 64–68) provides the "instrument at transaction boundary with rich attributes" framing that informed the canonical-set recommendations.
- `.claude/progress.md` — to confirm v2 is a branch rather than a directory (progress.md entry for Phase 22–23 confirms v1 was deleted, v2 lives at `skills/grailzee-eval/`).

**Anything in existing code that surprised me:**

1. **The no-op path is genuinely zero-cost.** `_NoOpSpan.__enter__` returns self, `__exit__` returns False (no suppression), `set_attribute` is pass. When the endpoint env var is unset, the tracer factory returns `trace.get_tracer()` from the default OTel API which itself yields a no-op tracer; `_NoOpTracer` is a second fallback for when `opentelemetry` is not even importable. Belt and suspenders, but correct.
2. **Span name collision between `run_analysis` inner spans and child scripts' CLI-level spans is avoided only because the child spans live in `main()`, not the library `run()`.** If any child script is later refactored to put its span inside the library `run()` (reasonable thing to want), `run_analysis` invocations will produce doubled-up identically-named nested spans. Worth documenting somewhere visible so it doesn't get done casually.
3. **`read_ledger.py` has no tracer and it's actually fine.** Every public entry is called from a parent-spanned context. The current design doesn't need `read_ledger` to originate a span, which is the right call — the library is used, not invoked, and always inherits caller context. If it ever grows a CLI, add a tracer then.
4. **`ledger_manager.py` has the most granular span taxonomy in the tree** (four distinct span names, one per CLI subcommand), and uses a `filter.*` attribute namespace that no other script uses. Cleanest instrumentation pattern in the repo — worth citing as the positive model when 0.2–0.3 go out.
5. **`evaluate_deal.py` uses `status` as a branch marker** (`error`, `not_found`, `ok`) emitted as a span attribute. This is exactly the kind of "enables arbitrary queries downstream" pattern the global CLAUDE.md asks for. No other script does this. Good candidate for extension to other multi-path scripts (`query_targets` could emit `status` for `ok` / `gate` / `ok_override` / `bad_filter`).

**Stopped per instruction. No commits. No code changes.**
