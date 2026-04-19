# REVIEW_phase21.md — Pre-deletion audit

## 1. Verdict

Audit initially dirty, remediated, now clean for migration.

Step 2 (gitignore hygiene) skipped per decision: the repo-root `.gitignore` already contains all required patterns (`__pycache__/`, `*.py[cod]`, `.DS_Store`). One tracked `.pyc` file exists in the repo — but it lives under `skills/grailzee-eval/scripts/__pycache__/`, i.e. in v1. Touching v1 now would violate the session's v1-untouchable scope guard. Phase 22's `rm -rf skills/grailzee-eval-old` removes it implicitly as part of v1 deletion — git-tracking status becomes irrelevant once the file no longer exists.

## 2. Initial audit findings

| Audit | Real deps | Doc / artifact | Verdict |
|---|---|---|---|
| 1 — `from grailzee-eval` | 0 | 1 (impl-doc self-ref to the grep command) | clean |
| 2 — `import.*analyze_report` | **2** (both test files) | 1 (impl-doc self-ref) | **dirty — blocker** |
| 3 — `CORE_REFERENCES` | 0 | 7 (3 docstrings + 4 .pyc + 1 impl-doc self-ref) | clean |
| 4 — `skills/grailzee-eval/` | 0 | ~25 (REVIEW docs + progress.md + impl-doc + 1 attribution docstring + 2 .pyc) | clean |

The blocker: both `tests/test_analyze_references.py` and `tests/test_analyze_trends.py` contained a `TestV1V2Equivalence` class with a pytest fixture that inserted `skills/grailzee-eval/scripts/` onto `sys.path` at runtime and imported v1's `analyze_report` module to run side-by-side parity checks against v2 equivalents. Post-Phase-22 (v1 deletion) these imports fail with `ImportError`.

## 3. Remediation actions

**TestV1V2Equivalence class deletion (Option A).**

- `tests/test_analyze_references.py` — removed the class (1 fixture `v1_analyze_reference` + 2 tests: `test_field_equivalence`, `test_recommend_reserve_differs_at_boundary`). Also removed the section-header comment block above it. `sys` and `Path` imports retained — still used by `run_cli`.
- `tests/test_analyze_trends.py` — removed the class (1 fixture `v1_compare_periods` + 1 test: `test_field_equivalence`). Also removed the section-header comment block. `sys` and `Path` imports retained.
- Total: **3 tests deleted**, 111 lines removed.
- Committed as `[phase21] remediate — remove TestV1V2Equivalence classes`.

**Step 2 (gitignore) skipped** per user decision (Option i). Rationale: `.gitignore` already correct; the one tracked `.pyc` is in v1 and will be removed by Phase 22's v1 deletion sequence.

## 4. Post-remediation audit output

```
$ grep -rn "from grailzee-eval" skills/grailzee-eval-v2/
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1388:grep -rn "from grailzee-eval" skills/grailzee-eval-v2/
```

```
$ grep -rn "import.*analyze_report" skills/grailzee-eval-v2/
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1389:grep -rn "import.*analyze_report" skills/grailzee-eval-v2/
```

```
$ grep -rn "CORE_REFERENCES" skills/grailzee-eval-v2/
skills/grailzee-eval-v2/scripts/analyze_changes.py:4:against a hardcoded CORE_REFERENCES list; v2 compares any two scored
Binary file skills/grailzee-eval-v2/scripts/__pycache__/analyze_changes.cpython-312.pyc matches
Binary file skills/grailzee-eval-v2/scripts/__pycache__/analyze_references.cpython-312.pyc matches
Binary file skills/grailzee-eval-v2/scripts/__pycache__/analyze_references.cpython-39.pyc matches
Binary file skills/grailzee-eval-v2/scripts/__pycache__/analyze_changes.cpython-39.pyc matches
skills/grailzee-eval-v2/scripts/analyze_references.py:9:v1 matched against CORE_REFERENCES; v2 scores every reference with 3+
skills/grailzee-eval-v2/scripts/analyze_references.py:137:    """Group sales by normalized reference. No CORE_REFERENCES filter."""
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1390:grep -rn "CORE_REFERENCES" skills/grailzee-eval-v2/
```

```
$ grep -rn "skills/grailzee-eval/" skills/grailzee-eval-v2/
skills/grailzee-eval-v2/REVIEW_phase3.md:79:- No modifications under skills/grailzee-eval/.
skills/grailzee-eval-v2/REVIEW_phase2.md:52:- No changes under skills/grailzee-eval/.
skills/grailzee-eval-v2/progress.md:53:- **Phase 22** — Migration. Rename `skills/grailzee-eval-v2/` → `skills/grailzee-eval/`, delete old contents. Follow §15 migration protocol.
skills/grailzee-eval-v2/scripts/grailzee_common.py:6:Extracted and refactored from skills/grailzee-eval/scripts/
Binary file skills/grailzee-eval-v2/scripts/__pycache__/grailzee_common.cpython-39.pyc matches
Binary file skills/grailzee-eval-v2/scripts/__pycache__/grailzee_common.cpython-312.pyc matches
skills/grailzee-eval-v2/REVIEW_batchB1.md:84:- **v1 `skills/grailzee-eval/` has its own `write_cache.py` with the old timestamp format.** Not touched — v1 is production and out of scope for v2 hygiene work. If v1 ever hits the collision, the fix is the same one-line change.
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:14:**Build location during development:** `skills/grailzee-eval-v2/` (parallel to existing `skills/grailzee-eval/`)
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:15:**Final location after migration:** `skills/grailzee-eval/` (existing directory replaced by v2 contents)
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:48:skills/grailzee-eval/ (one agent, four capabilities)
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:572:skills/grailzee-eval/
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:957:/Users/ranbirchawla/.openclaw/workspace/skills/grailzee-eval/scripts/ledger_manager.py
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1089:Location: `skills/grailzee-eval/scripts/` (final path after migration)
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1116:The existing scripts in `skills/grailzee-eval/scripts/` contain working logic that must be preserved, not rewritten. During Phase 1 extraction, Claude Code reads:
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1304:1. Read all .md files in `skills/grailzee-eval/`: AGENTS.md, SOUL.md, USER.md, IDENTITY.md, TOOLS.md, HEARTBEAT.md, SKILL.md, BOOTSTRAP.md (if present), folder-structure.md
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1351:- `skills/grailzee-eval/scripts/analyze_report.py`
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1352:- `skills/grailzee-eval/scripts/evaluate_deal.py`
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1353:- `skills/grailzee-eval/scripts/query_targets.py`
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1354:- `skills/grailzee-eval/scripts/write_cache.py`
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1357:- `skills/grailzee-eval/AGENTS.md`
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1358:- `skills/grailzee-eval/SOUL.md`
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1359:- `skills/grailzee-eval/USER.md`
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1360:- `skills/grailzee-eval/IDENTITY.md`
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1361:- `skills/grailzee-eval/TOOLS.md`
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1362:- `skills/grailzee-eval/HEARTBEAT.md`
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1365:- `skills/grailzee-eval/references/` directory (if it exists with business-model.md or similar)
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1368:- `skills/grailzee-eval/scripts/analyze_report.py` (replaced by decomposed scripts)
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1369:- `skills/grailzee-eval/scripts/evaluate_deal.py` (replaced by v2)
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1370:- `skills/grailzee-eval/scripts/query_targets.py` (replaced by v2)
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1371:- `skills/grailzee-eval/scripts/write_cache.py` (replaced by v2)
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1372:- `skills/grailzee-eval/scripts/__pycache__/` (Python build artifact)
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1373:- `skills/grailzee-eval/SKILL.md` (old monolith, replaced by intent dispatcher)
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1374:- `skills/grailzee-eval/BOOTSTRAP.md` (if present — AGENTS.md says delete after first run)
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1375:- `skills/grailzee-eval/folder-structure.md` (superseded by this implementation plan)
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1393:grep -rn "skills/grailzee-eval/" skills/grailzee-eval-v2/
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1412:ls -la skills/grailzee-eval/
skills/grailzee-eval-v2/Grailzee_Eval_v2_Implementation.md:1425:ls -la skills/grailzee-eval/
skills/grailzee-eval-v2/REVIEW_phase4.md:83:- No modifications under skills/grailzee-eval/.
```

## 5. False-positive allowlist

Matches that remain in the post-remediation audits are not dependencies on v1. Documented here so future audit runs don't re-surface them as open questions.

**Implementation-doc self-references.** The grep commands themselves live literally inside `Grailzee_Eval_v2_Implementation.md` §15.2 (lines 1388–1390, 1393). Matching a command's own text in the document that specifies the command is unavoidable. Acceptable.

**REVIEW docs and progress notes.** Multiple `REVIEW_phase*.md` files and `progress.md` reference v1's path (`skills/grailzee-eval/`) in "what this replaces" context — phase narratives describing the v1→v2 migration. Prose, not code. These will stay with the skill directory after Phase 22's rename; their content is historical.

**Module docstrings — design-difference narrative.**
- `scripts/analyze_changes.py:4`
- `scripts/analyze_references.py:9`
- `scripts/analyze_references.py:137`

Three docstrings explain v1's `CORE_REFERENCES`-based approach vs v2's universal-scoring approach. Reader documentation for future maintainers; removing them costs clarity for zero dependency gain. No `CORE_REFERENCES` symbol is defined, imported, or referenced as code anywhere in v2.

**Module docstring — attribution.**
- `scripts/grailzee_common.py:6` — "Extracted and refactored from skills/grailzee-eval/scripts/"

Provenance note in a module docstring. Not a live path — no file I/O reads this string.

**Bytecode (.pyc) — build artifacts.** Bytecode in `skills/grailzee-eval-v2/scripts/__pycache__/` inherits docstring text from `.py` sources when compiled. Not tracked by git (covered by repo `.gitignore`); regenerates automatically on next `pytest` or `python` invocation.

**Tracked `.pyc` in v1 (out-of-scope).** `skills/grailzee-eval/scripts/__pycache__/write_cache.cpython-311.pyc` is tracked in git. Not remediated in Phase 21 per the session's v1-untouchable guard. Phase 22's `rm -rf skills/grailzee-eval-old` removes it implicitly as part of v1 deletion.

## 6. Option A rationale — delete vs archive

`TestV1V2Equivalence` was scaffolding for the v1→v2 cutover. Its contract ("prove v2 produces identical output to v1 on shared inputs") is satisfied by shipping v2. Post-migration, v1 cannot be imported — the fixtures cannot resolve their module load — the tests become impossible to run. Leaving non-runnable tests in the tree signals false ongoing validation against v1 and invites future confusion.

Git history (commits `a62a05f` and earlier) preserves the deleted code. Archival preserves nothing history doesn't already. Option A is the clean exit.

**Precedent:** Phase 19 removed 34 Phase-17 cycle-gate tests when decisions D3/D4 superseded the behavior those tests exercised. Same pattern, same rationale — test deletions for behavior that no longer exists in the codebase are not regressions.

## 7. Test count movement

- Baseline (pre-remediation): **545 passing**
- After Step 1 remediation: **542 passing**
- Delta: **−3** (2 from `test_analyze_references.py` + 1 from `test_analyze_trends.py`)

## 8. Close

Phase 22 migration unblocked. All four audits clean of live v1 dependencies. False-positive allowlist documented for future audit runs. One tracked v1 artifact (`write_cache.cpython-311.pyc`) handled implicitly by Phase 22's v1 deletion.
