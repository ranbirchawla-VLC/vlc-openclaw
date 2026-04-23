# Phase 2a Close-out Report

**Date**: 2026-04-24
**Branch**: `feature/grailzee-eval-v2`
**Commit**: `9777199` (preceded by prerequisite patch `f7ecab8`)
**Both unpushed.**

---

## Files changed

| File | Lines | Purpose |
|------|-------|---------|
| `skills/grailzee-eval/scripts/ingest.py` | 685 | Phase 2a v3 canonical row layer: `CanonicalRow`, `IngestSummary`, `load_and_canonicalize`, `ingest_and_archive`, all transforms, OTel spans, CLI. |
| `skills/grailzee-eval/tests/test_ingest.py` | 649 | 86 tests across 14 test classes covering vocabulary, every transform, pipeline integration, dedup, archival, summary arithmetic. |
| `skills/grailzee-eval/discovery/schema_v3/phase_2a/` | 591 (8 files) | Five investigation findings + Part A and Part B spot-check reports + discovery script + this close-out. |

All files are net-new; nothing existing modified by `9777199`.

---

## What it does

New module that reads canonical CSVs from `reports_csv/` (post-`f7ecab8` patch) and emits `CanonicalRow` instances per the locked four-axis schema. Pipeline runs in v2-prompt-locked order: load -> header validation -> NBSP normalization -> asset-class filter -> dial-numerals canonicalization -> dial-color parsing + named_special detection -> auction-type detection -> row construction -> 4-tuple dedup -> near-collision counting. Pure function `load_and_canonicalize` for validation and tests; wrapper `ingest_and_archive` for production single-report ops with idempotent archival to `reports_csv/archive/`. Schema v2 cache untouched.

---

## Verification

- **All 1,046 tests pass** in 29.33s on Python 3.12.10 (960 baseline + 86 new).
- **Part A (W1+W2 logic validation)**: 19,335 source rows -> 10,440 canonical. Cross-report dedup overlap 8,801 (vs Phase 1's 8,837-8,839; delta -36 to -38, explained by pre-filter ordering), 108 NBSP-normalized NR rows, 3 asset-class drops, 71 blank-numerals drops, 10 fallthrough drops, 10 within-report duplicates. Arithmetic invariant holds.
- **Part B (W2-only operational rehearsal in tmp tree)**: 9,895 -> 9,846; archival happy path works (source moved, original filename preserved, byte-fidelity intact); idempotency block raises `FileExistsError` and leaves source in place. Live `reports_csv/` untouched.

---

## OTel

Two spans:
- `ingest.load_and_canonicalize`: attributes for `report_count, source_rows_total, canonical_rows_emitted` plus all 9 drop/transform counters plus `outcome=ok`.
- `ingest.ingest_and_archive`: attributes for `report_path, archive_dir, archived_path, canonical_rows_emitted, outcome` (`ok` or `archive_destination_exists`).

Both spans wrap the public function bodies; counters surface for Honeycomb when Z.1 wires up.

---

## Things to eyeball

**1. Test count delta is +86, above the +35-to-+55 prompt band.** Per kill-condition wording, flagged. Reasoning: heavy parametrization (15-case named_special vocab sweep, 9-case numerals exact-match, 4-case fallthrough drop, 5 NBSP/color/auction edge methods each). Each parametrized case is a distinct test instance. No test is wasted; each exercises a discrete vocabulary entry or transform variant. Operator accepted the +86 over consolidating to lists-in-loops which would lose pytest's per-case failure granularity.

**2. Cross-report overlap count -36 vs Phase 1.** Filter-aware semantics; pre-filter drops (asset_class, blank, fallthrough) on one report's side prevent the cross-report counter from incrementing for the matching key. Spot-check Part A explains. Not a regression, not a kill (delta is 0.47% < 10%). Worth understanding before 2b builds on the counter.

**3. `dial_color_unknown=1,116` exceeds Phase 1's 392 unparseable.** Expected: v2 prompt's parsed-vs-unknown simplification collapses Phase 1's 1,286 ambiguous bucket into unknown (multi-color-in-window cases). 2b should treat `unknown` as a real keying bucket value with substantial population, not a small leftover.

**4. Color-in-model-name ambiguity.** "Tudor Black Bay 41MM Blue Dial" returns `dial_color="unknown"` because both `black` and `blue` fall in the 4-word window. Conservative; matches Phase 1's tudor_sport 88% family parse rate. `test_color_in_model_name_creates_window_ambiguity` pins this. Not a defect; family-stratified evidence supports the conservative choice.

**5. `within_report_near_collisions=19` (post-dedup) vs discovery I.4's 33 (pre-dedup).** Pipeline-ordering difference; counter is advisory only per operator plan-review. Documented in spot-check Part A.

---

## Plan-review divergences (operator-confirmed)

1. **`sold_at` typed as `datetime.date` not `datetime`** (v2 prompt §5 specified `datetime`). CSV has day-precision; `date` is semantically cleaner. Approved.
2. **`dial_color` as `str` with `frozenset` allowlist** rather than `Literal[40+ values]`. Vocabulary is large; `Literal` would be rigid. Approved.
3. **CanonicalRow carries 8 analyzer-support fields** (`brand, model, condition, papers, year, box, sell_through_pct, url`) beyond v2 prompt's "minimum" set. Avoids 2b having to join back to source CSV. Approved.
4. **named_special tiebreak: longest-match-wins, NOT first-match-wins.** Operator-tightened during plan-review after the original first-match-wins proposal. Reason: vocabulary contains both `panda` and `reverse_panda`; first-match returns `panda` on a "Reverse Panda" descriptor, silently wrong. Pinned by `TestNamedSpecial::test_reverse_panda_not_panda`.
5. **Operator-adjusted cascade extensions for I.5 fall-through**: `no numbers` -> `No Numerals`, `abaric` -> `Arabic`. Drop the rest as Decision-5-equivalent.

---

## Implied but not done

- **State doc Section 4 entry**: written and committed separately (post-commit, citing hash `9777199`).
- **Live `reports_csv/` archival**: Part B ran in tmp tree; live CSVs untouched. Operator decides whether to run live `ingest_and_archive` on W2 now or let Phase 2b drive its own first ingest. Verification item added to STATE §7.
- **Phase 2b scoper**: 2a does not wire `CanonicalRow` into the v2 scorer. v2 scorer continues to read `analyze_references.load_sales_csv`. Wiring lands in 2b per non-goal §2.2.

---

## Pre-commit verification done

- `wc -l skills/grailzee-eval/scripts/ingest.py` -> 685 lines (parity with `evaluate_deal.py` 725-line precedent for module size).
- `git diff --stat` showed three new tracked items: `scripts/ingest.py`, `tests/test_ingest.py`, `discovery/schema_v3/phase_2a/`.
- `discovery/schema_v3/` Phase 1 artifacts (`load.py`, `discover.py`, `findings/`) deliberately left untracked per default-delete-at-Phase-2-close convention.
- Em-dash sweep before commit: 8 in markdown findings + 6 in `discover_2a.py` -> all replaced with semicolons. Code (`ingest.py`, `test_ingest.py`) was always clean.
- Subject line of commit `9777199` confirmed clean (`[build] Phase 2a; v3 canonical row layer (ingest module)`).

---

## Operator-pinned guarantees

1. **Implementation is longest-match-wins**, not first-match-wins by vocabulary order. Verified at `scripts/ingest.py:detect_named_special` (tracks `best_length`, replaces only when `length > best_length`, alphabetical-on-source-pattern tiebreak).
2. **Test pinned for "Reverse Panda" -> `reverse_panda`**: `tests/test_ingest.py:271 TestNamedSpecial::test_reverse_panda_not_panda`. Plus `test_reverse_panda_lowercased_input` and `test_panda_alone_still_panda` covering the inverse case. All three pass.

---

*End of close-out.*
