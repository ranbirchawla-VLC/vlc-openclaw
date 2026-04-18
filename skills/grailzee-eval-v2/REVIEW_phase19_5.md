# REVIEW_phase19_5.md — Phase 19.5: `report_pipeline.py`

**Verdict:** Ships 1 wrapper module + 4 tests in one commit. 571 tests pass (567 baseline + 4 new).

**Commit:** `[phase19_5] report_pipeline.py — ingest + glob + analyze wrapper`

---

## What Shipped

`scripts/report_pipeline.py` (~130 lines): collapses the three-step `ingest_report → glob → run_analysis` chain into one callable, `run_pipeline(input_report, output_folder, *, csv_dir, ledger_path, cache_path, backup_path, name_cache_path, cycle_focus_path, trend_window)`. Returns `run_analysis`'s dict unchanged — `{summary_path, unnamed, cycle_id}`.

The `capabilities/report.md` step 2/3/4 chain can now be one invocation.

### Flow

1. Open span `report_pipeline.ingest_glob` (attrs: input_report, csv_dir, trend_window).
2. Call `ingest_report.ingest(input_report, output_dir=csv_dir or CSV_PATH)`. Record `output_csv` + `rows_written` span attrs.
3. Glob `{csv_dir}/grailzee_*.csv`, sort descending (ISO date suffix makes lexical-desc == chronological-desc), slice to `trend_window`.
4. Raise `ValueError` with directory + pattern if the glob is empty.
5. Close span.
6. Call `run_analysis.run_analysis(csv_paths, ...)` and return its dict unchanged. `run_analysis`'s 12 existing per-stage spans cover the rest.

### CLI

`python3 scripts/report_pipeline.py <input.xlsx> --output-folder DIR [--csv-dir PATH] [--ledger PATH] [--cache PATH] [--backup PATH] [--name-cache PATH] [--cycle-focus PATH] [--trend-window N]`. Wraps `run_pipeline` in a root span `report_pipeline.run` and prints the result dict as JSON.

---

## Tests

`tests/test_report_pipeline.py`:

| # | Test | Proves |
|---|------|--------|
| 1 | `TestHappyPath.test_ingest_glob_analyze_end_to_end` | Real xlsx (built via `_fixture_builders.build_minimal_report` with pinned 2026-04-20 date) + 3 seeded fixture CSVs → returns well-formed dict; summary file exists; csv_dir has exactly 4 CSVs post-ingest |
| 2 | `TestEmptyGlob.test_raises_with_dir_and_pattern` | Monkeypatch `ingest_report.ingest` to a no-op; empty csv_dir → `ValueError` containing both the directory path and `grailzee_*.csv` pattern |
| 3 | `TestIngestFailurePropagates.test_non_xlsx_input_raises` | `.txt` input → openpyxl `InvalidFileException` propagates through the wrapper unwrapped |
| 4 | `TestTrendWindow.test_slice_respects_trend_window` | Monkeypatch both ingest and run_analysis; `trend_window=2` → `run_analysis` receives exactly the 2 newest CSVs in newest-first order |

Span-emission is not unit-tested — matches precedent in `test_run_analysis.py`, which does not assert on its 12 orchestrator spans either. This was an explicit plan decision (option C), not an oversight.

---

## Code Review Findings

Reviewer surfaced no blocking issues. Four advisories; three accepted, one declined:

| Advisory | Resolution |
|----------|-----------|
| `pytest.raises(Exception)` too broad — would mask `KeyError`-from-kwarg-typo regressions | **Accepted.** Tightened to `pytest.raises(InvalidFileException)` with docstring explaining the exact type. |
| Docstring should pin the "ISO date suffix makes lex == chron" contract so a maintainer doesn't reach for `os.path.getmtime` | **Accepted.** Added 3-line docstring note. |
| Happy-path asserted `len >= 4` instead of `== 4`; reviewer correctly pointed out the real risk is ingest-date collision with a seeded fixture, not ingest-side bugs | **Accepted.** Switched to `== 4` and pinned an explicit 2026-04-20 sale date in the test (distinct from 03-09/03-23/04-06 seeds) + added `assert (csv_dir / "grailzee_2026-04-20.csv").exists()` |
| Span attrs include full filesystem paths (`input_report`, `csv_dir`, `output_csv`). If traces ever ship off-box they leak home-dir layout. | **Declined.** This workspace is local-dev; traces don't ship off-box. Stripping to `Path(...).name` would cost debug usefulness (you can't tell *which* `reports_csv/` directory from a bare name). Revisit if OTel Goal 2 adds off-box export. |
| Double exception-record pattern in `run_pipeline` span + `main()` root span (both record + set ERROR + re-raise) | **Declined, matches precedent.** `run_analysis.py` does exactly the same pattern (inner spans record + re-raise, outer `main` span also records). Worth revisiting cross-module as a separate cleanup if it bothers the trace viewer; not in-scope for this phase. |

---

## Key Decisions

**Single span, ingest + glob only.** Per D1 from session kickoff: the wrapper's one span covers the two stages `run_analysis` doesn't already instrument. Wrapping `run_analysis` in another span would duplicate every one of its 12 per-stage spans under a redundant parent. Future observers can group by `trace_id` to see the whole pipeline without the redundancy.

**`trend_window` defaulted to 6 per guide §6.2.** Exposed as a keyword arg + CLI flag so integration tests and one-off investigations can narrow the window without monkeypatching.

**No changes to `capabilities/report.md` in this commit.** Phase 19 (next task) rewrites the four capability files against D2/D3/D4; the `report.md` update belongs there.

**Empty-glob test uses monkeypatch, not a carefully-constructed Excel file.** Considered: build a workbook whose ingest succeeds but produces a file outside `csv_dir`. Rejected: the wrapper uses one `csv_dir` for both ingest output *and* glob input, so they can't diverge through real inputs. Monkeypatching `ingest_report.ingest` to a no-op is the only honest way to exercise the empty-glob code path without fighting the design.

---

## Anomalies

- None worth flagging. Wrapper is pure composition; no new domain logic.

---

## Scope Creep Flags

| What | Why not done | Future target |
|------|-------------|---------------|
| Update `capabilities/report.md` to call `report_pipeline.py` instead of the 3-step chain | Out of scope for 19.5; that's exactly Phase 19's job | Phase 19 (next task) |
| Strip filesystem paths from span attrs | Declined per reviewer advisory discussion above | OTel Goal 2 session if/when off-box export is introduced |
| Unify double-record pattern between inner stage spans and outer root span | Matches `run_analysis.py` precedent; cross-module change belongs in its own cleanup | Separate session |
