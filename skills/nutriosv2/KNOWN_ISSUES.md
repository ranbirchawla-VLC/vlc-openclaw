# KNOWN_ISSUES.md — NutriOS v3

Issues carried forward from code-reviewer subagent. Fix before the sub-step that first exercises the affected code path.

---

## NB-1 — Atomic write has a crash window that leaves the file absent
**File:** `scripts/common.py:39-41` | **Fix by:** any sub-step before live data writes
Between `os.replace(path, bak)` and `os.replace(tmp, path)`, if the process crashes the live path is absent. Both `.bak` and `.tmp` are intact so no data is lost, but `read_json` returns `None` on recovery. Acceptable for single-user bot; document or resolve window before production use.

## NB-2 — `write_json` raises on flat path (no directory component)
**File:** `scripts/common.py:32` | **Fix by:** sub-step 1
`os.makedirs(os.path.dirname("data.json"))` raises `FileNotFoundError: ''`. All current callers are safe. Fix: `if d := os.path.dirname(path): os.makedirs(d, exist_ok=True)`.

## NB-3 — Pydantic v2 silently coerces numeric string user_id
**File:** `scripts/common.py:62` | **Fix by:** sub-step 1 (before first Telegram message handler)
`user_id: int` coerces `"123"` to `123` without error. Add `model_config = ConfigDict(strict=True)` if strict int enforcement is needed, or document that coercion is intentional.

## NB-4 — `read_user` propagates `JSONDecodeError` and `ValidationError` on corrupt data
**File:** `scripts/common.py:70-75` | **Fix by:** sub-step 1 (before first live tool)
Corrupt or schema-mismatched `user.json` raises rather than returning `None`. Add try/except in `read_user` or handle at the message-handler boundary — either is acceptable, but the choice must be explicit before handlers are wired.

## NB-5 — `ok` / `err` have no tests
**File:** `scripts/common.py:52-59` | **Fix by:** sub-step 1 (before first tool script that calls them)
Test with `capsys` + `pytest.raises(SystemExit)`.

## NB-6 — `today_str` has no test
**File:** `scripts/common.py:20-21` | **Fix by:** sub-step 2 (before meal log date partitioning)
Add one test verifying `YYYY-MM-DD` format and timezone-awareness.

## NB-7 — No `pyproject.toml` for the skill
**Project-level** | **Fix by:** sub-step 1
Global CLAUDE.md mandates `pyproject.toml` for dependency management. Pydantic is a runtime dependency with no pinned version constraint.

---
*Generated: 2026-04-25 — code-reviewer subagent, sub-step 0 gate*
