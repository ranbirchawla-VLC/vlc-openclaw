# REVIEW_batchB1.md — Batch B1 Hygiene Fixes

**Verdict:** 4 flags shipped across 2 bisect-friendly commits. 567 tests pass (562 baseline + 5 new).

**Commits:**
- `9a84d86` — `[hygiene] ingest_report.py — mtime warning, datetime.now() removal, required --output-dir` (Flags #1, #2, #3)
- `06ea683` — `[hygiene] write_cache.py — microsecond precision on backup timestamps` (Flag #6)

Flags #4 (dial column preservation) and #5 (schema-change alerts) deferred to Batch B2 per original scope.

---

## Flags Shipped

| Flag | File | Before | After |
|------|------|--------|-------|
| #1 | `ingest_report.py` `_determine_output_name()` | mtime fallback silently named the output CSV from file mtime when sale-date extraction failed | Emits `WARNING: no usable sale dates in workbook {path!r}; falling back to file mtime as report date: YYYY-MM-DD.` to stderr |
| #2 | `ingest_report.py` `_determine_output_name()` | `except OSError: pass` then `datetime.now()` last resort — could produce today's date for an unrelated workbook on any future run | `except OSError as exc: raise ValueError(...) from exc` with chained cause |
| #3 | `ingest_report.py` CLI + `ingest()` signature | `--output-dir` optional with `CSV_PATH` default fallback | `required=True`; `ingest(output_dir: str)` signature; `CSV_PATH` import removed; `capabilities/report.md` Step 2 updated to pass `--output-dir reports_csv/` |
| #6 | `write_cache.py` `_backup_existing()` | Backup filename format `%Y%m%d_%H%M%S` — same-second collisions silently overwrote earlier backups via `shutil.copy2` | `%Y%m%d_%H%M%S_%f` (microsecond) |

---

## Tests Added

| # | Test | Flag | What it proves |
|---|------|------|----------------|
| 1 | `TestMtimeFallback.test_mtime_fallback_warns_to_stderr` | #1 | stderr contains WARNING + "mtime" + input path; protects against message regression |
| 2 | `TestMtimeFallback.test_mtime_fallback_filename_format` | #1 | Returned name matches `grailzee_YYYY-MM-DD.csv` with a parseable date |
| 3 | `TestMtimeFallback.test_mtime_unavailable_raises` | #2 | `OSError` on `getmtime` → `ValueError`; asserts `__cause__` is the OSError (chained exception contract) |
| 4 | `TestRequiredOutputDir.test_missing_output_dir_fails` | #3 | CLI without `--output-dir` exits non-zero; stderr names the flag |
| 5 | `TestBackupTimestampCollision.test_distinct_filenames_within_same_second` | #6 | Monkey-patches `wc.datetime` with a `datetime` subclass whose `.now()` returns two timestamps with identical seconds but different microseconds; asserts 2 distinct backup files |

Also updated: `test_nonexistent_file_fails` now passes `--output-dir` so it still exercises the "nonexistent input → error" check rather than tripping on argparse's new `required=True` (intent-preserving change, not a new test).

---

## Code Review Findings

### Commit 1 (ingest_report.py)

Two blocking issues surfaced by `/agent code-reviewer`. Both resolved before commit:

| Issue | Severity | Resolution |
|-------|----------|------------|
| Error messages said "filename date parse failed" but `_determine_output_name` never parses the filename — primary path reads `sales[].date_sold`. The "rename to grailzee_YYYY-MM-DD.xlsx to suppress" hint was actively misleading | **Blocking** | Reworded to "no usable sale dates in workbook"; dropped the rename hint |
| `capabilities/report.md` Step 2 documented the wrong JSON output shape (`{"status": "ok", "csv_path": ..., "rows": N}` vs actual `{"output_csv": ..., "rows_written": ..., "sheets": ..., "warnings": ...}`). Pre-existing bug, but in-scope since I was editing this file for Flag #3 | **Blocking** | Corrected to match the actual payload |
| `test_mtime_fallback_warns_to_stderr` didn't assert the filename appears in stderr — reword regressions would pass silently | Advisory | Added `assert str(f) in captured.err` |
| `test_mtime_unavailable_raises` didn't verify `raise … from exc` chaining | Advisory | Added `assert isinstance(excinfo.value.__cause__, OSError)` |
| `os.path.*` usage not migrated to `pathlib` | Advisory | Out of scope for this batch; pre-existing mixed style in both files |

### Commit 2 (write_cache.py)

No blocking issues. Reviewer confirmed:

- Sort-order preserved: after the shared `YYYYMMDD_HHMMSS` prefix, old-format files have `.` (ASCII 46) and new-format have `_` (95). Pre-existing old-format backups sort before same-second new-format backups. Rotation `sorted(...)[:-MAX_BACKUPS]` stays correct.
- `TestBackupRotation.test_keeps_last_10` still passes — its pre-created fixtures use date `20260101`; the new backup uses today's date, so it sorts last and the 11→10 trim picks the correct file.
- No other parsers of the backup filename format anywhere in the repo (grep confirmed).
- `tz=None` on the fake `_FixedDT.now` correctly mirrors the real signature.

---

## Key Decisions

**Flag #2 — raise, don't fall back to `datetime.now()`.**
The previous code had a defensive three-tier fallback: sales dates → mtime → `datetime.now()`. The third tier returned the wrong date on any future run. The operator never saw the failure; the output CSV was just named with today's date and silently joined the pipeline. Converting the third tier to a raise is a root-cause fix — the caller now knows the workbook is unusable and can act (provide a date, fix the file, etc.). `mtime` is kept as a best-effort fallback because it's still *correct* information (when the file was last written) and emits a stderr warning.

**Flag #3 — `required=True` over a named env var.**
Considered using an env var or config-file default instead of breaking CLI compatibility. Rejected because the only existing caller (`capabilities/report.md` Step 2) is trivially updatable and the cost of a silent default (output goes to the wrong directory in production) outweighs the one-line migration cost. Breaking-change is acceptable for a tool still in v2 development.

**Flag #6 — `%f` over a monotonic counter.**
Considered an in-process monotonic counter (e.g., `itertools.count`) for absolute collision-freedom. Rejected because:
1. `_backup_existing` is called once per `write_cache.run` invocation — no within-process burst, so microsecond resolution is sufficient.
2. Microsecond timestamps are human-readable; a counter is not.
3. Counter state doesn't survive process restarts; microseconds do (to the limit of clock resolution).

The realistic failure mode is two pipeline runs triggered by two near-simultaneous operator commands, not a tight in-process loop. Microsecond precision handles that cleanly.

---

## Anomalies

- **mtime fallback is effectively dead code through the normal `ingest()` call path.** `parse_auctions_sold` skips any row without a `Sold at` value; `ingest()` raises if `sales` is empty before `_determine_output_name` is ever called. So `sales` is never `[]` at the callsite via the normal path. The mtime branch is only reachable by calling `_determine_output_name` directly (tests) or by a hypothetical future caller that passes pre-filtered empty sales. Keeping the fallback + warning is defensible defensive-programming; the flag improves its observability without expanding its reach.
- **v1 `skills/grailzee-eval/` has its own `write_cache.py` with the old timestamp format.** Not touched — v1 is production and out of scope for v2 hygiene work. If v1 ever hits the collision, the fix is the same one-line change.

---

## Scope Creep Flags

| What | Why not done | Future target |
|------|-------------|---------------|
| `os.path` → `pathlib` migration in `ingest_report.py` and `write_cache.py` | Pre-existing mixed style; out of scope for hygiene batch | Separate cleanup pass if/when touched for other reasons |
| Flag #4 (dial column preservation in `ingest_report.py`) | Deferred to Batch B2 per original plan | Batch B2, post-Phase 22 |
| Flag #5 (schema-change alerts in `ingest_report.py`) | Deferred to Batch B2 per original plan | Batch B2, post-Phase 22 |
| Phase 18 MNEMO seeding (memory population) | Out of scope per progress notes; separate phase | Phase 18 session |
| Phase 19 capability-file expansion (beyond the one-line Step 2 fix for Flag #3) | Out of scope | Phase 19 session |
| Request/agent/capability-level tracing (Goal 2) | Out of scope — OTel Goal 2 runs after pipeline-stage instrumentation stabilizes | Separate session |
