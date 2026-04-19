# REVIEW_otel_retrofit.md — OTel Retrofit on run_analysis.py

**Verdict:** OTel retrofit complete. 12 spans added to run_analysis.py. 562 tests pass.

---

## Pre-Retrofit State

One span existed, in `main()` only:

| Span | Location | Attributes |
|------|----------|------------|
| `"run_analysis"` | `main()` CLI entry | `csv_count`, `cycle_id` (post), `unnamed_count` (post) |

Exception handling: `record_exception` + `set_status(ERROR)` present, but `StatusCode`
imported inline inside the `except` block (deferred import pattern).

The `run_analysis()` function body had zero spans. All 8 analyzer-stage calls, the 4
file-write boundary calls, and the cycle rollup call were uninstrumented.

---

## Spans Added

All 12 spans are in `run_analysis()` function body, sequential call-site wrappers.

| # | Span name | Stage | Pre-call attributes | Post-call attributes |
|---|-----------|-------|--------------------|--------------------|
| 1 | `analyze_references.run` | Step 6 | `csv_count` | `refs_count` |
| 2 | `analyze_trends.run` | Step 7 | `csv_count` | `trend_count` |
| 3 | `analyze_changes.run` | Step 8 | `has_prev` | `emerged_count`, `faded_count` |
| 4 | `analyze_breakouts.run` | Step 8 | `has_prev` | `breakout_count` |
| 5 | `analyze_watchlist.run` | Step 8 | `has_prev` | `watchlist_count` |
| 6 | `analyze_brands.run` | Step 9 | `refs_count` | `brand_count` |
| 7 | `read_ledger.run` | Step 10 | — | `trade_count` |
| 8 | `roll_cycle.run` | Step 12 | `previous_cycle_id` | — |
| 9 | `build_spreadsheet.run` | Step 14 | `refs_count` | — |
| 10 | `build_summary.run` | Step 14 | `cycle_id` | `output_path` |
| 11 | `build_brief.run` | Step 14 | `refs_count` | — |
| 12 | `write_cache.run` | Step 15 | `cycle_id`, `cache_path` | — |

Exception handling per span: `record_exception(exc)` + `set_status(StatusCode.ERROR, str(exc))` + `raise`.

`StatusCode` import hoisted to module level (between sys.path block and local imports) — same
symbol, avoids 12 repeated inline imports.

---

## Span Tree (3-CSV fixture run against real data)

When invoked via CLI, the `"run_analysis"` span in `main()` is the root and all 12 are children.
When `run_analysis()` is called as a library function (tests, capability layer), the 12 spans
fire as roots with no parent — correct, since no trace context is propagated from outside.

```
run_analysis  [csv_count=3, cycle_id=cycle_2026-07, unnamed_count=1207]  ← main() CLI span
  analyze_references.run  [csv_count=2, refs_count=1229]
  analyze_trends.run      [csv_count=3, trend_count=598]
  analyze_changes.run     [has_prev=True, emerged_count=48, faded_count=29]
  analyze_breakouts.run   [has_prev=True, breakout_count=18]
  analyze_watchlist.run   [has_prev=True, watchlist_count=2949]
  analyze_brands.run      [refs_count=1229, brand_count=33]
  read_ledger.run         [trade_count=0]
  roll_cycle.run          [previous_cycle_id='cycle_2026-06']
  build_spreadsheet.run   [refs_count=1229]
  build_summary.run       [cycle_id='cycle_2026-07', output_path='.../Vardalux_Grailzee_Analysis_April2026.md']
  build_brief.run         [refs_count=1229]
  write_cache.run         [cycle_id='cycle_2026-07', cache_path='.../state/analysis_cache.json']
```

All 12 spans emitted with status `UNSET` (success) on a clean run. Verified with
`InMemorySpanExporter` + `SimpleSpanProcessor` against fixture CSVs
(grailzee_2026-04-06.csv, grailzee_2026-03-23.csv, grailzee_2026-03-09.csv,
empty ledger).

---

## Test Results

562 passed / 0 failed. No test changes required — `test_run_analysis.py` has no span
count assertions and calls `run_analysis()` as a library function. Spans fire via no-op
tracer during the test run.

Note: 3.12.10 pyenv environment was not active at session start; `openpyxl` and
`opentelemetry` packages had to be installed into it. These are pre-existing env gaps,
not introduced by this block.

---

## Code Review Summary

Five issues surfaced by `/agent code-reviewer`. All resolved:

| Issue | Severity | Resolution |
|-------|----------|------------|
| `StatusCode` import before `sys.path` block | Advisory | Moved to after path manipulation, before local imports |
| `os.path.basename` / `os.path.dirname` used instead of `Path` | Advisory | Replaced with `Path(...).name` and `Path(...).parent`; `import os` removed |
| `roll_cycle` comment overstated "no legitimate failure path" | **Blocking** | Narrowed to: missing-file inputs handled gracefully; remaining exceptions are real failures |
| `os.path.dirname(cache_path)` unsafe on bare filename (no dir component) | **Blocking** | Replaced with `Path(cache_path).parent / "cycle_outcome.json"` |
| `references_scored` attribute always logged 0 (`"references"` not in return shape) | **Blocking** | Attribute and vacuous `isinstance` guard removed |

---

## roll_cycle Non-Fatal → Fatal: Confirmed Decision

The pre-existing `except Exception: pass` was a **defensive hack**, not an intentional design
decision. Evidence:

- `load_cycle_focus()` returns `None` for a missing file (explicit docstring: "Returns None if file missing")
- `parse_ledger_csv()` returns `[]` for a missing or empty ledger
- `prev_cycle()` always returns a valid cycle string
- The comment was `pass  # cycle rollup failure is non-fatal` — no documentation of *why*

Any real exception from `roll_cycle.run()` means `cycle_outcome.json` was not written. Making
it fatal is correct. The span records the exception and re-raises; the outer `"run_analysis"`
CLI span also records it and exits with code 1.

---

## Scope Creep Flags

| What | Why not done | Future target |
|------|-------------|---------------|
| `ingest_report.convert_latest()` span | Not called in `run_analysis.py`; orchestrator receives already-normalized CSVs. Ingest is upstream. | Belongs on whatever caller feeds run_analysis with the ingest step. Block 2 or later. |
| `calculate_presentation_premium` / `apply_premium_adjustment` spans | Pure in-process calculation with no I/O boundary. Not in scope per amended rule. | Not required. |
| Request-level / agent-level / capability-level tracing (Goal 2) | Out of scope for this block per Section 1. Capability files don't exist yet (Phase 19). | Scoped separately in a later session. |
| Spans inside analyzer modules (`run()` functions) | All analyzer spans are in `main()` CLI entries, not in `run()`. Adding spans to `run()` would be analyzer-internal work, not orchestrator work. | Separate pass if intra-module spans are needed. |

---

## Anomalies

- **No REVIEW_phase15.md** — Phase 15 REVIEW doc does not exist in the branch. Pre-retrofit
  state confirmed by reading `run_analysis.py` source directly.
- **Analyzer spans are in `main()`, not `run()`** — All 8 analyzer scripts have their spans
  in the CLI entry function. When called as library functions from the orchestrator, those
  child spans do not fire. The orchestrator's new call-site spans are the only spans for
  these stages when running through the pipeline. Nested span structure only applies if the
  CLI path and library path are both exercised simultaneously (they are not).
- **`load_name_cache` imported but unused** — Pre-existing in the original file, not introduced
  by this block. Left as-is.
