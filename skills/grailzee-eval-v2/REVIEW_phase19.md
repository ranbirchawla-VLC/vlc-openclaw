# REVIEW_phase19.md — Phase 19: capabilities + query_targets rewrite

**Verdict:** Ships in two commits. `query_targets.py` rewritten against D3+D4 (pure-lookup, two-section spec). Four capability files aligned with D1–D4; `ledger.md` left untouched by design (already D2-compliant from Phase 17).

**Commits:**
- `[phase19] query_targets.py — rewrite against two-section spec`
- `[phase19] four capability files — report deal targets ledger`

**Tests:** 571 baseline → 545 after phase. Movement is planned: 34 Phase 17 cycle-gated tests removed (the behavior they tested no longer exists), 8 new tests added. No unrelated regressions.

---

## What shipped

### Deliverable 1 — `capabilities/report.md`

Replaces the three-step ingest + glob + run_analysis chain with a single invocation of `scripts/report_pipeline.py` (Phase 19.5 wrapper). No flags — wrapper defaults cover all state paths. Name-resolution loop preserved with a new failure-handling clause (skip unresolvable refs and continue rather than stalling the hand-off). Final hand-off message trimmed to the exact D3-compliant wording: `"Cycle {cycle_id} analyzed. Ready to strategize in Chat."`

### Deliverable 2 — `capabilities/deal.md`

Two-branch structure on script status:

- **Branch A (`status: "ok"`):** template surfaces median, MAX BUY, signal, volume, sell-through, momentum, margin, ad budget, confidence, premium status. LLM composes voice-grounded recommendation using business context. Cycle annotation removed per D3.
- **Branch B (`status: "not_found"`):** market context only per D3. Quarantines `comp_search_hint.formula_reminder` and `comp_search_hint.instructions` as pre-D3 (they applied margin math to web comps). No forced recommendation. No margin math. No MAX BUY calculation.

### Deliverable 3 — `capabilities/targets.md`

Thin pass-through around `scripts/query_targets.py`. No flags, no gate handling, no override phrases, no filter table, no momentum emoji, no prose framing. Script stdout goes to Telegram verbatim. Response Format documents the two-section block, the one-tier-empty header-preserved case, and the both-tiers-empty fallback message.

### Deliverable 4 — `capabilities/ledger.md`

**Deliberately untouched.** Per user instruction ("minimize churn; if it's already D2-compliant, leave it"). Re-read against the §9.3 template and against D2 rejection semantics: existing file is fully compliant. Sub-mode A rejection flow at lines 66–72 aborts with `"Trade not logged. Re-send the trade details with corrections when ready."` — matches D2 intent exactly. Template shape is expanded per sub-mode (Trade Logging Workflow + Performance Query Workflow with response formats integrated into each), which the user's instruction explicitly permits for two-sub-mode capabilities. No edits applied.

### Deliverable 5 — `scripts/query_targets.py` rewrite

600 lines → 124 lines (≈70 lines executable code). Pure lookup:

- Reads `analysis_cache.json`.
- Filters references where `signal == "Strong"` and `signal == "Normal"`.
- Sorts each tier by `max_buy_nr` DESC (ties break on dict-insertion order — documented in `build_sections` docstring).
- Emits two-section text block or single-line fallback to stdout.

One OTel span `query_targets.run` mirrors `analyze_brands`/`evaluate_deal` precedent. Attributes: `cache_path`, `strong_count`, `normal_count`, with `record_exception` + `set_status(ERROR)` on error path.

Removed from the Phase 17 version: cycle gate, `cycle_focus.json` read, `--ignore-cycle` flag, `--brand`/`--signal`/`--budget`/`--format`/`--sort` filters, filter validation, confidence enrichment, response-dict envelope, 8 helper functions. CLI surface is now `--cache PATH` only.

---

## Key decisions

### Both-tiers-empty fallback

The prompt asked me to pick behavior when both Strong and Normal are empty, and document the choice. Chose: single-line fallback message `"No references at Strong or Normal signal."` rather than emitting two bare section headers. Rationale: Telegram doesn't benefit from two empty headers; the operator gets the same signal (no targets qualify) with less visual noise. One-tier-empty still emits the header — an empty STRONG section is itself information.

### float-to-int rendering

Cache stores `max_buy_nr` as float (e.g. `1950.0`). Output renders via `int(ref["max_buy_nr"])` → `$1950`. The analyzer rounds MAX BUY to the nearest $10 already, so the fractional component is always `.0` for valid data. Output is pinned by `test_float_max_buy_nr_renders_as_int`.

### Fail-loud on missing `max_buy_nr`, forgive missing text fields

Reviewer advisory accepted. `_format_line` uses `or ""` fallbacks on brand/model/reference (text degrades gracefully — a missing brand renders as a leading space, which is cosmetic) but drops the `or 0` fallback on `max_buy_nr` (a missing price is a cache-integrity bug that should surface via `TypeError: int(None)` rather than silently ship `$0` targets to Telegram). The asymmetry is intentional.

### 34-test removal audit

Phase 17's `tests/test_query_targets.py` had 34 tests across 8 categories (A: cycle gate behavior, B: filtered list / gate passes, C: override mode, D: filters + validation, E: premium status, F: error paths, G: path isolation, H: CLI). Every one of those categories tests behavior that D3+D4 removed. The rewrite deletes all 34 and replaces them with 8 tests covering the actual new contract (5 per-deliverable + 3 advisory-accepted: float render, missing cache, stale schema). Net: `571 − 34 + 8 = 545`.

This is planned removal of tests for removed behavior, not a regression. Documented here so future sessions reading git history understand the count drop.

### `ledger.md` carried forward with no edits

User's explicit instruction: minimize churn; leave if D2-compliant. Compliance verified; file carried forward unchanged. Phase 19 credit for ledger capability sits with the Phase 17 author. The REVIEW table below shows zero lines touched.

### `report.md` Step 2 "inline glob" reconciliation

Code-reviewer flagged that Step 2's `ls -t reports/*.xlsx | head -1` contradicts the "Does NOT inline glob logic" rule in the same file. Resolved by tightening the "Does NOT" wording to distinguish **pipeline state glob** (the CSV trend window — forbidden) from **operator input-acquisition** (selecting which workbook to process — permitted). The one file path the capability knows about is the workbook the operator just dropped; everything else defaults.

---

## D1–D5 contracts honored

| Decision | Binding on | How honored |
|----------|-----------|-------------|
| **D1** — report.md invokes wrapper, not raw scripts; no state paths | `capabilities/report.md` | Single call `python3 scripts/report_pipeline.py <input.xlsx>`. No `--output-folder` flag. No `ingest_report.py` / `run_analysis.py` invocations anywhere in the file. Wrapper defaults for CSV dir, ledger, cache, backup, name cache, output folder all resolve from `grailzee_common` constants. |
| **D2** — ledger.md abort-on-no with re-send message | `capabilities/ledger.md` | Already compliant from Phase 17. No edits. |
| **D3** — no cycle gate on targets/deal; deal Branch B is market-context-only | `capabilities/targets.md`, `capabilities/deal.md`, `scripts/query_targets.py` | targets.md: no gate, no override, no `cycle_focus.json` read. deal.md: `cycle_focus` fields ignored in both branches; Branch B surfaces Chrono24/eBay market data only, no MAX BUY, no margin math, no recommendation. query_targets.py: removed the entire cycle-gate code path (`_check_cycle_gate`, `--ignore-cycle`, gate response dicts). |
| **D4** — two-section Strong/Normal, MAX BUY DESC | `scripts/query_targets.py`, `capabilities/targets.md` | Script filters `signal == "Strong"` and `signal == "Normal"`, sorts each by `max_buy_nr` DESC, emits `STRONG\n...lines...\n\nNORMAL\n...lines...` or fallback. targets.md documents this output shape verbatim. |
| **D5** — config-driven analyzer thresholds | Out of scope for Phase 19 | The cache already emits `signal` with the correct tier strings from `analyze_references.py` — verified during planning (F3). No pull-forward of config-file infrastructure needed. Config-file work lives in its own phase. |

---

## Test results

| Category | Baseline | After phase | Delta |
|----------|----------|-------------|-------|
| test_query_targets.py | 34 | 8 | −26 |
| All other test files | 537 | 537 | 0 |
| **Total** | **571** | **545** | **−26** |

New tests in `tests/test_query_targets.py`:

| # | Test | Proves |
|---|------|--------|
| 1 | `test_happy_path_mix_of_tiers` | Strong/Normal appear in their sections; Reserve/Careful/Pass excluded; DESC sort within each tier; exact output shape |
| 2 | `test_empty_strong_header_present_with_no_entries` | Only-Normal cache emits `STRONG\n\nNORMAL\n<entries>` |
| 3 | `test_empty_normal_header_present_with_no_entries` | Only-Strong cache emits `STRONG\n<entries>\n\nNORMAL` |
| 4 | `test_both_tiers_empty_falls_back_to_message` | Only Reserve/Careful/Pass refs collapse to `EMPTY_MESSAGE` |
| 5 | `test_sort_correctness_desc_within_tier` | Distinct `max_buy_nr` values sort DESC (5000, 4000, 3000, 2000, 1000) |
| 6 | `test_float_max_buy_nr_renders_as_int` | Cache `1950.0` → output `$1950`, not `$1950.0` |
| 7 | `test_missing_cache_raises_file_not_found` | Missing path → `FileNotFoundError` with path in message |
| 8 | `test_stale_schema_raises_value_error` | `schema_version < CACHE_SCHEMA_VERSION` → `ValueError("schema version ...")` |

---

## Code review findings

### Commit 1 — `query_targets.py` + `test_query_targets.py`

Reviewer surfaced no blocking issues. Seven advisories; four accepted, three declined:

| Advisory | Resolution |
|----------|-----------|
| 🟡 Two-pass iteration in `build_sections` (filter Strong, filter Normal separately) | **Declined.** At 22-ref cache scale, irrelevant. Single-pass with match/case would be clearer but not measurably faster. |
| 🟡 Sort ties on `max_buy_nr` fall back to dict-insertion order, not documented | **Accepted (doc only).** Added tie-break note to `build_sections` docstring. Not adding a secondary sort key — that commits a second contract without being asked. |
| 🟡 `_format_line` defensive fallbacks — `or 0` on `max_buy_nr` is forgiving a cache-integrity bug | **Accepted.** Dropped `or 0` on `max_buy_nr`; kept `or ""` on text fields. Forgive text, fail loud on numbers. |
| 🟡 No test for float-to-int render contract | **Accepted.** Added `test_float_max_buy_nr_renders_as_int` (1950.0 in, $1950 out). |
| 🟡 No test for `FileNotFoundError` / `ValueError` paths | **Accepted.** Added `test_missing_cache_raises_file_not_found` and `test_stale_schema_raises_value_error`. |
| 🟢 `lambda` assigned to `key` (ruff E731) | **Accepted.** Inlined lambdas into the two `sorted()` calls. |
| 🟢 `dict[str, Any]` generics on type hints | **Declined.** Matches in-project convention (grep shows bare `dict` is the norm across other analyzer modules). |
| 🟢 Line count | **Declined.** 124 lines total (~70 executable) is justified; inlining `_format_line` into `format_output` would lose the one place that names the render contract. |
| 🟢 Docstring/comment quality | **No action needed.** All four docstrings pull weight; no deletions. |

### Commit 2 — capability files

No blocking issues. Four advisories; three accepted, one declined:

| Advisory | Resolution |
|----------|-----------|
| 🟡 `report.md` Step 2's `ls -t reports/*.xlsx \| head -1` contradicts the "Does NOT inline glob" rule in the same file | **Accepted.** Reworded the `What the LLM Does NOT Do` section to distinguish pipeline-state glob (forbidden) from operator input-acquisition (permitted). Step 2 comment added inline clarifying which category it sits in. |
| 🟡 `report.md` Step 5 web-search loop has no failure-handling clause | **Accepted.** Added: "If a search fails or yields no confident match, skip the reference and continue. Do not stall the hand-off. At the end of the loop, include a one-line note listing any references that could not be resolved." |
| 🟡 `deal.md` Branch A margin line should handle null/negative margin | **Declined (verified non-null).** Inspected `evaluate_deal.py` line 538: on `status: "ok"`, `metrics.margin_pct` is always `round(decision["margin_pct"], 1)` where `decision` is always populated in the ok branch. Null is not possible. Negative values are valid operator-facing information (a −15% margin is a meaningful NO). Template unchanged. |
| 🟡 `deal.md` Branch B "Market spread suggests ${range} current value" skates close to a valuation | **Accepted.** Tightened to `"Observed spread: ${range}."` Market context, not valuation. |

---

## Anomalies

- None worth flagging. All surfacing was clean; test deltas matched plan; reviewer findings were symmetric to my own read.

---

## Scope creep flags

| What | Why deferred | Future target |
|------|-------------|---------------|
| `append_name_cache_entry` one-liner in `report.md` Step 5 | Reviewer nit; cleaner as a dedicated CLI script | Phase 20 or a hygiene batch |
| Dispatch hole: single-reference lookup without price ("Should I buy the Tudor 79830RB?" with no $ amount) | Reviewer flagged as an across-capability gap; not in D1–D5 | Phase 20 SKILL.md top-level dispatch logic |
| `ledger.md` cycle-rollup output still references `cycle_focus` data for historical hit/miss reporting | Not a D3 violation (D3 removed cycle *gating*, not cycle *reporting*); historical rollups are archival | No action needed unless D3's scope later broadens |
| Config-file infrastructure (D5) | Deferred to its dedicated phase | Future phase — `analyze_references.py` already emits `signal` with the correct tier strings, so Phase 19 doesn't depend on D5 |
| Span-attribute path-leak (absolute paths in `query_targets.run` `cache_path` attr) | Same decision as Phase 19.5 — local-dev only, traces don't ship off-box | OTel Goal 2 if off-box export is added |

---

## Files changed

| File | Lines before | Lines after | Delta |
|------|-------------|------------|-------|
| `scripts/query_targets.py` | 600 | 124 | −476 |
| `tests/test_query_targets.py` | 960 | 141 | −819 |
| `capabilities/report.md` | 111 | 124 | +13 |
| `capabilities/deal.md` | 139 | 175 | +36 |
| `capabilities/targets.md` | 158 | 84 | −74 |
| `capabilities/ledger.md` | 184 | 184 | 0 |
| `REVIEW_phase19.md` | 47 (stale Phase 17 review) | ≈270 | +223 (overwrite) |

Net: substantial deletion of superseded code and tests, modest additions to capability prompts, one deliberately untouched file.
