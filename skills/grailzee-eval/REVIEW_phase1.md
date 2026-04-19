# Phase 1 Review (deferred to Phase 2)
Date: 2026-04-16

## Summary
- Blockers found and fixed: 0
- Majors found and fixed: 0
- Minors found and fixed: 1 (dead imports in test file)
- Nits: 1 fixed (added get_ad_budget tests), 0 deferred
- Scope creep flagged: 0

## Extraction fidelity audit

- **normalize_ref:** Verbatim match. v1 (analyze_report.py:231-234) logic: `str(s).strip().upper()`, strip trailing `.0`. v2 identical.
- **strip_ref:** Verbatim match. v1 (evaluate_deal.py:53-62) logic: normalize, strip M-prefix if len>5, strip -XXXX suffix, remove separators. v2 identical.
- **match_reference:** Behavioral match with extension. v1 (analyze_report.py:236-244) takes list only, iterates. v2 accepts `str | list`, recurses for list. Core matching logic (normalized substring, separator-stripped substring) identical. Extension is additive; no regression.
- **classify_dj_config:** Logic match; intentional return-type change. v1 returns `"Other"` for unclassifiable; v2 returns `None`. Documented in docstring. Callers in later phases use `None` check.
- **is_quality_sale:** Verbatim match. v1 (analyze_report.py:255-258) logic: condition substring vs QUALITY_CONDITIONS AND papers in allowed set. v2 identical.
- **QUALITY_CONDITIONS:** Verbatim match. v1: `{'very good', 'like new', 'new', 'excellent'}`. v2 identical. Plan's 4-item set incorrectly included "unworn" and omitted "new"; v1 was used as source of truth per Phase 1 spec.
- **DJ_CONFIGS:** Verbatim match. All 9 entries with identical keyword lists and None-bracelet configs.
- **NR_FIXED:** v1=149, v2=149. Match.
- **RES_FIXED:** v1=199, v2=199. Match.
- **TARGET_MARGIN:** v1=0.05, v2=0.05. Match.
- **AD_BUDGETS:** Match. v1 uses en-dash characters, v2 uses `\u2013` unicode escapes. Render identically.

## Changes made during review

1. **tests/test_grailzee_common.py imports:** Removed dead imports `AD_BUDGETS`, `QUALITY_CONDITIONS` (imported but never referenced in any assertion). Kept `get_ad_budget` import and added tests for it.
2. **tests/test_grailzee_common.py TestAdBudget:** Added 2 tests (`test_below_first_threshold`, `test_highest_bracket`) for the `get_ad_budget` public function which had no test coverage.

## Out of scope (NOT fixed, for human decision)

None identified. All Phase 1 deliverables are within spec.

## Checklist results

1.1 Extraction fidelity: **PASS** - All 6 functions verbatim or behavioral match. One intentional change (classify_dj_config return type) documented.
1.2 Unit correctness: **PASS** - RISK_RESERVE_THRESHOLD=0.40 with comment. No bare `20` in risk context (only in the explanatory comment). Hand-verified max_buy_nr(3000)=2720, max_buy_reserve(3000)=2670.
1.3 Test quality: **PASS** - 54 tests (over 25-35 target but all substantive). V1-behavioral tests document behavior in docstrings. No tautologies. No skips.
1.4 Code hygiene: **PASS** after fix - Dead imports removed. All public functions have docstrings and type hints. Hardcoded paths in Paths block only. Magic numbers in Business Rules block only.
1.5 Plan alignment: **PASS** - 5.4 fee structure, 5.5 presentation premium, 7.7 name cache, 12.3 common module all implemented per spec.
1.6 Structural correctness: **PASS** - Directory tree matches spec. pytest.ini works. __init__.py files are 0 bytes. No Python files outside scripts/ and tests/.
1.7 Not-in-scope verification: **PASS** - No ingest, analyze, ledger scripts. No Google Drive writes. No v1 modifications. No OTel plumbing.
1.8 Tripwires: **PASS** - `load_name_cache` with corrupt JSON would raise `json.JSONDecodeError` (correct; loud failure beats silent corruption). No silent fallbacks. No v1-existence assumptions. Machine paths limited to documented Google Drive root.

## Recommendation

READY TO PROCEED TO PHASE 2 STEP 2.
