# vlc-openclaw — Infrastructure Review: Makefile + Test Layout

Prepared: 2026-04-24  
Reviewer: Claude (self-review)  
Branch: feature/nutrios-v2  
Scope: Piece 0 (piggyback fix), Piece 1 (test layout move), Piece 2 (Makefile)

---

## 1. What Was Changed

### Piece 0 — Piggyback fix: `resolve_user_id_from_peer` non-string guard

**File:** `skills/nutriOS/lib/nutrios_store.py`  
**Change (5 lines added):** After looking up the peer in the index, added a type check:
```python
if not isinstance(resolved, str):
    raise StoreError(
        f"Index entry for {channel_peer!r} must be a str user_id, "
        f"got {type(resolved).__name__!r}"
    )
```
**Test file:** `skills/nutriOS/tests/test_nutrios_store.py` — one test added (`test_resolve_user_id_value_not_string_raises`). Writes `{"telegram:12345": 12345}` (int value) and asserts `StoreError` is raised with the peer key in the message. Test count: 28 (was 27 after corrective pass).

### Piece 1 — Test layout move

**Source:** `nutrios-workspace/skills/nutrios/{lib,tests}/`  
**Destination:** `skills/nutrios/{lib,tests}/` (git tracks as `skills/nutriOS/` due to `git mv` casing; macOS filesystem merges both into `skills/nutrios/` since APFS is case-insensitive)

**Files moved (10 total):**

| File | From | To |
|---|---|---|
| `__init__.py` (lib) | `nutrios-workspace/skills/nutrios/lib/` | `skills/nutriOS/lib/` |
| `nutrios_engine.py` | same | `skills/nutriOS/lib/` |
| `nutrios_models.py` | same | `skills/nutriOS/lib/` |
| `nutrios_store.py` | same | `skills/nutriOS/lib/` |
| `nutrios_time.py` | same | `skills/nutriOS/lib/` |
| `__init__.py` (tests) | `nutrios-workspace/skills/nutrios/tests/` | `skills/nutriOS/tests/` |
| `test_nutrios_engine.py` | same | `skills/nutriOS/tests/` |
| `test_nutrios_models.py` | same | `skills/nutriOS/tests/` |
| `test_nutrios_store.py` | same | `skills/nutriOS/tests/` |
| `test_nutrios_time.py` | same | `skills/nutriOS/tests/` |

**Import mechanism unchanged:** Every test file uses:
```python
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
```
This resolves relative to `__file__`, so `tests/../lib` = `skills/nutrios/lib/` at the new location. No `conftest.py` changes were needed.

**Pre-move test count:** 137  
**Post-move test count:** 137 (verified via `python3.12 -m pytest skills/nutriOS/tests -q`)  
**Post-piggyback test count:** 138

### Piece 2 — Makefile

**File:** `Makefile` (new at repo root)  
**Lines:** 47  
**Targets:** 7 (`.PHONY`: `help`, `test`, `test-nutrios`, `test-nutrios-time`, `test-nutrios-store`, `test-nutrios-engine`, `test-nutrios-models`)  
**Recipe indentation:** Confirmed literal tabs via `cat -e Makefile`.

---

## 2. Verification

### `make help`
```
Available targets:
  make test                   - run full test suite (all skills)
  make test-nutrios           - run all NutriOS tests
  make test-nutrios-time      - run nutrios_time tests
  make test-nutrios-store     - run nutrios_store tests
  make test-nutrios-engine    - run nutrios_engine tests
  make test-nutrios-models    - run nutrios_models tests
```

### `make test` (full suite)
```
138 passed in 0.15s
```

### `make test-nutrios`
```
138 passed in 0.11s
```

### `make test-nutrios-time`
```
22 passed in 0.02s
```

### `make test-nutrios-store`
```
28 passed in 0.10s
```

### `make test-nutrios-engine`
```
67 passed in 0.06s
```

### `make test-nutrios-models`
```
21 passed in 0.05s
```

**Sum check:** 22 + 28 + 67 + 21 = **138**. Matches `make test`. No double-collection, no missed files.

---

## 3. `resolve_day` Caller Audit

Grep of `resolve_day(` across `skills/nutriOS/lib/` and `skills/nutriOS/tests/`:

| Location | Line | Call | `tz` passed? |
|---|---|---|---|
| `nutrios_engine.py` | 70 | `def resolve_day(now, tz, goals, mesocycle)` | definition |
| `test_nutrios_engine.py` | 157 | `engine.resolve_day(_NOW, "UTC", goals, meso)` | ✓ |
| `test_nutrios_engine.py` | 163 | `engine.resolve_day(_NOW, "UTC", goals, meso)` | ✓ |
| `test_nutrios_engine.py` | 169 | `engine.resolve_day(_NOW, "UTC", goals, meso)` | ✓ |
| `test_nutrios_engine.py` | 175 | `engine.resolve_day(_NOW, "UTC", goals, meso)` | ✓ |
| `test_nutrios_engine.py` | 189 | `engine.resolve_day(now_utc, "America/Denver", goals, meso)` | ✓ |
| `test_nutrios_engine.py` | 201 | `engine.resolve_day(now_utc, "America/Denver", goals, meso)` | ✓ |

**No tool entrypoints exist yet** (steps 4–6 are future work). The only caller is the test suite. All six test call sites pass `tz`. No corrective regression.

---

## 4. Judgment Calls

### J1: Future-skill pattern documented in Makefile comment block, not CONTRIBUTING.md

**Decision:** The pattern is in a comment block at the top of `Makefile`, not a separate `CONTRIBUTING.md`.  
**Why:** The pattern is directly adjacent to the thing it describes. A developer opening `Makefile` sees the pattern immediately without context-switching to another file. A `CONTRIBUTING.md` would need to be kept in sync; the Makefile comment stays in sync by definition.  
**Risk:** If the repo grows enough to warrant a `CONTRIBUTING.md` covering multiple workflows, the Makefile comment would be one of several locations. Low risk at current scale.

### J2: macOS case-insensitivity — `nutriOS` vs `nutrios` in git vs filesystem

**Situation:** The spec calls for `skills/nutriOS/` (capital N and O). The existing `skills/nutrios/` v1 skill directory exists. macOS APFS is case-insensitive, so `git mv ... skills/nutriOS/...` merged into `skills/nutrios/`. Git tracks the files with the capital `nutriOS` casing; the filesystem serves them from `nutrios/`.  
**Decision:** Left as-is. The Makefile uses lowercase `skills/nutrios/tests` which is what the filesystem requires. Tests pass. Git history preserves the `nutriOS` tracking path. On a case-sensitive Linux filesystem, this would be a real `skills/nutriOS/` distinct from `skills/nutrios/`.  
**Risk:** If this repo is ever cloned on a case-sensitive filesystem, the `lib/` and `tests/` directories would appear under `skills/nutriOS/` (separate from the v1 `skills/nutrios/`). The Makefile would break — it points at `skills/nutrios/tests`. **Recommend:** On a future Linux deployment, update Makefile paths to `skills/nutriOS/tests` consistently.

### J3: `make test` and `make test-nutrios` are identical

**Decision:** Both run `$(PYTEST) skills/nutrios/tests`. Today they produce the same output because NutriOS is the only Python skill.  
**Why:** The intent is deliberate. `make test` is "run everything" and will expand as more skills are added (by appending additional pytest invocations). `make test-nutrios` is "run this skill only" and stays scoped. They happen to be equivalent now; they won't be once a second skill lands.  
**Alternative considered:** `make test` could recurse over `skills/*/tests/`. Rejected: named literal targets are the design constraint.

### J4: `scripts/runtests` left in place

**Decision:** The `scripts/runtests` wrapper added in the `fewer-permission-prompts` session was not removed. It still works and is independently useful for one-off invocations. The Makefile is additive.

---

## 5. Pattern Propagation

When the next skill lands (`grailzee`, `vardalux`, or similar), the author:

1. Creates `skills/<skill-name>/lib/` and `skills/<skill-name>/tests/` with the same `sys.path.insert(...)` pattern in test files.
2. Opens `Makefile` and copies the nutriOS block verbatim, substituting `<skill-name>` and `<module>` throughout.
3. Adds the new target names to the `.PHONY` line.
4. Adds a `help` echo line for each new target.
5. Appends a `$(PYTEST) skills/<skill-name>/tests` line to `make test` (so the full suite stays complete).

The comment block at the top of the Makefile spells this out. The pattern is clear enough that a developer joining cold can follow it without additional documentation — the existing nutriOS block is the working example.

One potential confusion: step 5 (updating `make test`) requires editing an existing recipe, not just appending a new target. Make sure to change:
```makefile
test:
	$(PYTEST) skills/nutrios/tests
```
to:
```makefile
test:
	$(PYTEST) skills/nutrios/tests
	$(PYTEST) skills/<new-skill>/tests
```
This should be called out explicitly in the Makefile comment or a `CONTRIBUTING.md` once a second skill exists. Adding it now would be speculative.

---

*End of review. Three judgment calls flagged for awareness: the macOS casing ambiguity (J2) is the only one with a future deployment risk. Everything else is self-consistent and low-risk.*
