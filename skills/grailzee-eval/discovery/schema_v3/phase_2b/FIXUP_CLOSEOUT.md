# Phase 2b Fixup Close-out Report

**Date**: 2026-04-24
**Branch**: `feature/grailzee-eval-v2`
**Scope**: judgment-creep removal from 2b pre-commit; three bug fixes
**Status**: ready for review; no commit yet per repo CLAUDE.md

---

## Files changed

| File | Line count (after) | Change |
|------|--------------------|--------|
| `scripts/write_cache.py` | 323 | Rip: `_dominant_median`, `_best_signal`, `_SIGNAL_RANK`, `_premium_vs_market_from_trades`, `_realized_premium_from_trades`, all call sites. Strip premium fields from reference entry. Strip 4 signal counts from summary. Strip premium-coverage OTel span attrs. Trend defaults null (not `"No prior data"` / 0) on both main ref path and DJ config path. Drop `get_current_span` import (now unused). Docstring updated. |
| `scripts/analyze_buckets.py` | 397 | Bug 1: `bucket_key` serializer lowercases all three axes. Docstring updated. Body fields (bucket dict entries) keep canonical case. |
| `scripts/evaluate_deal.py` | 737 | Bug 3: add pending_2c_restore return after stale-schema check; v3 cache fails clean with explicit message instead of silently KeyError-ing on flat field reads. |
| `grailzee_schema_design_v2_0.md` | 210 | Reference entry + summary + DJ config shape updated; ledger-vs-market moved to strategy-session scope; `_dominant_median` interim section replaced with strategy-session narrative. |
| `tests/test_write_cache.py` | 610 | Delete `TestPremiumVsMarket` (12 tests) and `TestRealizedPremium` (15 tests). Rewrite `TestPerReferenceShape` against v3 post-fixup shape (new tests: `expected_keys_present`, `ripped_fields_absent`, `identity_values`, `trend_threaded`, `buckets_passed_through`, `buckets_default_empty`, `confidence_from_ledger`). New `TestDJConfigShape` class (3 tests) for null trend/confidence + ripped-field regression. Update `TestNullDefaults::test_no_trend` to assert null. Update `TestSummaryAggregation::test_summary_counts` for the new summary shape + new `test_per_signal_counts_absent` regression. Replace `test_schema_version_is_2` with `test_schema_version_is_3`. |
| `tests/test_analyze_buckets.py` | 475 | `TestBucketKey` updates: all 5 existing tests assert lowercase keys; 1 new `test_body_case_preserved_key_lowered` regression. `TestBuildBuckets` key assertions switched to lowercase. `test_bucket_inside_reference` switched to lowercase key. |
| `tests/test_run_analysis.py` | 423 | Delete `TestPremiumVsMarketIntegration` (3 tests), `TestRealizedPremiumIntegration` (3 tests), `test_max_buy_stays_at_plain_median`, `TestSentinelValues` (both tests). New `TestReferenceShape` class: `test_reference_has_v3_keys` and `test_no_ripped_fields_in_cache` end-to-end regression. Update `test_trends_empty` to null assertion (bug 2). Drop orphaned imports (`csv`, `statistics`, `date`, `timedelta`) and `_premium_ledger` helper. |
| `tests/test_evaluate_deal.py` | 1,218 | Per-class `@pytest.mark.skip(_PENDING_2C)` on 9 classes that go through `evaluate()` against v3 cache (`TestCacheHitDecisions`, `TestOnDemandFallback`, `TestNotFound`, `TestCycleFocusAlignment`, `TestConfidenceEnrichment`, `TestPremiumStatus`, `TestPathIsolation`, `TestCLI`, `TestAdBudget`). Two test-level skips in `TestErrorPaths` for the two cycle-focus tests that do go through `evaluate()`. New `TestSchemaGuardPending2c` class (2 tests) covering bug 3: v3 cache returns pending_2c_restore, v2 cache still returns stale_schema. |

### New discovery artifacts

| File | Purpose |
|------|---------|
| `discovery/schema_v3/phase_2b/fixup_part_a.py` + `fixup_part_a_findings.md` | Part A verification (W1+W2 union logic). Zero drift vs Phase 2b I.4. |
| `discovery/schema_v3/phase_2b/fixup_part_b.py` + `fixup_part_b_findings.md` + `fixup_part_b_raw.txt` | Part B verification (W2-only end-to-end rehearsal). All checks passed. |
| `discovery/schema_v3/phase_2b/fixup_benchmark_1_7.py` + `fixup_benchmark_1_7.md` | §1.7 analytical-quality benchmark. 10 references side-by-side v2 vs v3. Operator read pending. |

---

## Two-sentence summary

The fixup removes three judgment-creep fields (`_dominant_median` proxy, `_best_signal` cross-bucket aggregation, `premium_vs_market` / `realized_premium` ledger comparisons) from the v3 cache build so the scorer emits facts-per-bucket plus own-ledger-summary only. Three supporting bug fixes land in the same pass: lowercase bucket_key serialization, null trend defaults (not sentinel strings), and a loud `pending_2c_restore` error on `evaluate_deal` when the v3 cache would otherwise be silently read with v2 flat-field expectations.

---

## Verification

| Step | Status | Location |
|------|--------|----------|
| Full pytest run on canonical Python 3.12 | 973 passed, 96 skipped, 0 failed | 44s runtime |
| Part A (W1+W2 union, logic validation) | PASS; zero drift vs Phase 2b I.4 | `fixup_part_a_findings.md` |
| Part B (W2-only, end-to-end) | PASS all 10 checks | `fixup_part_b_findings.md` + `fixup_part_b_raw.txt` |
| §1.7 analytical-quality benchmark | PREPARED; operator read pending | `fixup_benchmark_1_7.md` |
| Em-dash sweep | Clean across all modified scripts, tests, and findings | ripgrep for U+2014 returns nothing |
| Rip hygiene: `rg "_dominant_median|_best_signal|_premium_vs_market_from_trades|_realized_premium_from_trades"` | 0 hits in scripts/ and tests/ | Pre-existing-only references in `build_shortlist.py` (2c-restore scope, unchanged per spec) and `test_config_helper.py` (unrelated brand-config test keys). |

---

## OTel spans touched

- `scripts/write_cache.py`: **removed** two ambient-span attributes (`premium_vs_market_pct_nonzero_count`, `realized_premium_pct_populated_count`) because they point to ripped fields. The underlying `get_current_span()` import was dropped. No new attributes invented (escalation trigger 2 respected).
- `scripts/analyze_buckets.py` span (`analyze_buckets.score_all_references`): unchanged. Carries `reference_count`, `total_bucket_count`, `scored_bucket_count`, `below_threshold_bucket_count`, `dj_config_count`, `outcome`.
- `scripts/evaluate_deal.py`: unchanged; outer `evaluate_deal` span still emits `brand`, `reference`, `purchase_price`, `outcome`. New pending_2c_restore return path sets `outcome="error"` the same way stale_schema does.

---

## Things noticed, worth eyeballing

1. **Spec ambiguity on evaluate_deal guard**. The fixup instructions say "If not 3, raise a clean error." Read literally, that lets a v3 cache pass the guard and then break on flat-field reads (the exact silent-failure the fix was meant to stop). Implemented as intent-aligned: v3 cache raises `pending_2c_restore`, v2 and older still raise `stale_schema`. Reviewer should confirm this reading. If the literal reading was intended, the change is a one-line flip of the condition.

2. **Summary schema shrunk, not just patched**. Ripping `_best_signal` and every call site took four summary fields with it: `strong_count`, `normal_count`, `reserve_count`, `caution_count`. These fields would require cross-bucket aggregation at reference level (synthesis); rebuilding them under different semantics (e.g., counting buckets instead of references) would be a new judgment, so none was invented. Flagged because it is a surface change to the cache schema.

3. **240 buckets with n>=3 get signal=Low data**. Part A signal distribution shows 482 scored buckets vs 722 n>=3 buckets. The 240-bucket gap is pre-existing v2 `analyze_reference` behavior (a VG+-filter inside the scorer can push a bucket back to Low data). Unchanged by fixup. Worth a future look but out of scope.

4. **Finding 01 is now historically stale**. `discovery/schema_v3/phase_2b/findings/01_scorer_call_graph.md` references the ripped helpers in its write_cache field map. Not updated in this pass (discovery findings are snapshots, not live docs). If 01 is cited outside this session, readers should know the write_cache surface it describes predates the fixup.

5. **`RUN_HISTORY_PATH` and `canonical_reference` imports in write_cache.py are unused**. Pre-existing dead imports per STATE backlog. Not touched in this scope-shrink pass.

6. **Benchmark ledger mismatch**. The §1.7 doc compares Drive's live v2 cache (with real ledger; shows `confidence`, `realized_premium_pct` etc. populated) against a fresh v3 cache run in a tmp tree with an empty ledger (so `confidence=null`). Operator should read for **shape**, not values. Written into the doc's header note.

---

## Things implied but not done, with reasoning

- **Cowork-side cache consumer adaptation**. Not touched. Per spec: "2c consumer restoration ... stay broken per 2b plan."
- **STATE Section 4 entry for fixup**. Supervisor scope per spec: "GRAILZEE_SYSTEM_STATE.md (supervisor updates Section 4 at close-out)."
- **Regenerate v2 cache on current W1+W2**. Would require checkout to parent commit, re-run, switch back. The existing Drive v2 cache (W1.5 source) is sufficient for the shape comparison §1.7 calls for.
- **Remove finding 01 stale references**. Historical doc; leaving as-is until a broader findings sweep.

---

## Specific things to verify before commit

1. **Re-read the evaluate_deal guard**. Is "if not 3, raise error" the literal-read behavior you want (evaluator only trusts v3), or the intent-read behavior I implemented (v3 returns pending_2c_restore until 2c restores the consumer)? If literal, the fix is one line: change `if schema_version < CACHE_SCHEMA_VERSION` to `if schema_version != CACHE_SCHEMA_VERSION` and delete the added return block.

2. **Confirm summary-shape shrinkage**. Are you OK dropping `strong_count` / `normal_count` / `reserve_count` / `caution_count` from the summary block? Alternative is to redefine as "buckets with signal X" (changes semantic); I did not do that because it is a new judgment not in the rip list.

3. **Confirm bucket body case convention**. Body fields keep canonical case (`"dial_numerals": "Arabic"`); only the dict key is lowercase (`"arabic|nr|black"`). If you want the body lowered too, the change is ~5 lines in `score_bucket` and a few test asserts.

4. **Commit approval**. Per repo CLAUDE.md: operator commits after review. Proposed single-commit scope: everything listed above, under a subject like `[fixup] 2b judgment-creep rip + three bug fixes`.

---

## Standing rules (confirmed)

- Branch `feature/grailzee-eval-v2`, single long-lived.
- No em-dashes across any edited file or new artifact.
- Scorer reads `CanonicalRow` only; no raw CSV reads (unchanged).
- No judgment encoded in the scorer: facts per-bucket; own-ledger summary at reference. Cache contract holds.
