# vlc-openclaw — Infrastructure Review: Makefile + Test Layout

Prepared: 2026-04-24  
Reviewer: Claude (self-review)  
Branch: feature/nutrios-v2  
Scope: Piece 0 (piggyback fix), Piece 1 (test layout move), Piece 2 (Makefile + pytest.ini)

---

## 1. What Was Changed

### Piece 0 — Piggyback fix: `resolve_user_id_from_peer` non-string guard

**File:** `skills/nutrios/lib/nutrios_store.py`  
**Change (5 lines added):** After the index lookup, added:
```python
if not isinstance(resolved, str):
    raise StoreError(
        f"Index entry for {channel_peer!r} must be a str user_id, "
        f"got {type(resolved).__name__!r}"
    )
```
**Test:** `test_resolve_user_id_value_not_string_raises` in `test_nutrios_store.py`. Writes `{"telegram:12345": 12345}` (int value), asserts `StoreError` with peer key in the message.  
**Test count delta:** +1 (27 → 28 in the store module).

### Piece 1 — Test layout move

**Source:** `nutrios-workspace/skills/nutrios/{lib,tests}/`  
**Destination:** `skills/nutrios/{lib,tests}/`

**macOS case-insensitivity note:** The spec uses `skills/nutriOS/` (capital N and O). On macOS APFS the filesystem is case-insensitive, so `git mv ... skills/nutriOS/...` merged into the existing `skills/nutrios/` directory rather than creating a distinct `nutriOS/` directory. Git tracks the files under the `nutriOS` casing in its index; the filesystem and all tools see `nutrios`. This means `python3.12 -m pytest skills/nutriOS/tests` returns "not found" (pytest's path walker is case-sensitive), while `skills/nutrios/tests` works. All Makefile targets use the lowercase form that actually resolves.

**Files moved (10 total via `git mv`):**

| File | From | To |
|---|---|---|
| `__init__.py` (lib) | `nutrios-workspace/skills/nutrios/lib/` | `skills/nutrios/lib/` |
| `nutrios_engine.py` | same | `skills/nutrios/lib/` |
| `nutrios_models.py` | same | `skills/nutrios/lib/` |
| `nutrios_store.py` | same | `skills/nutrios/lib/` |
| `nutrios_time.py` | same | `skills/nutrios/lib/` |
| `__init__.py` (tests) | `nutrios-workspace/skills/nutrios/tests/` | `skills/nutrios/tests/` |
| `test_nutrios_engine.py` | same | `skills/nutrios/tests/` |
| `test_nutrios_models.py` | same | `skills/nutrios/tests/` |
| `test_nutrios_store.py` | same | `skills/nutrios/tests/` |
| `test_nutrios_time.py` | same | `skills/nutrios/tests/` |

**Import mechanism unchanged.** All test files use:
```python
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
```
This resolves to `skills/nutrios/lib/` at the new location. No `conftest.py` changes needed.

**Pre-move test count:** 137  
**Post-move test count (after piece 0):** 138

### Piece 2 — `pytest.ini` + Makefile

**`pytest.ini` (new, 3 lines):**
```ini
[pytest]
testpaths = skills
```
Required because bare `python3.12 -m pytest` from the repo root discovers 282 tests (including `watch-listing-workspace/schema/test_draft_schema.py` and others). With `testpaths = skills`, bare pytest collects exactly 138 — the NutriOS tests — matching the four scoped targets.

**`Makefile` (new, 46 lines):** Seven `.PHONY` targets, literal tab indentation. `make test` uses bare `$(PYTEST)` (relies on `pytest.ini`). All scoped targets use `skills/nutrios/tests` (lowercase, what resolves on macOS).

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

### `make test` (full suite, bare pytest scoped by pytest.ini)
```
138 passed in 0.16s
```

### `make test-nutrios`
```
138 passed in 0.14s
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

**Sum check:** 22 + 28 + 67 + 21 = **138** = `make test`. No double-collection, no missed files.

---

## 3. `resolve_day` Caller Audit

Grep: `grep -rn "resolve_day(" skills/nutrios/lib/ skills/nutrios/tests/`

| Location | Line | Call | `tz` passed? |
|---|---|---|---|
| `nutrios_engine.py` | 70 | `def resolve_day(now, tz, goals, mesocycle)` | definition |
| `test_nutrios_engine.py` | 157 | `engine.resolve_day(_NOW, "UTC", goals, meso)` | ✓ |
| `test_nutrios_engine.py` | 163 | `engine.resolve_day(_NOW, "UTC", goals, meso)` | ✓ |
| `test_nutrios_engine.py` | 169 | `engine.resolve_day(_NOW, "UTC", goals, meso)` | ✓ |
| `test_nutrios_engine.py` | 175 | `engine.resolve_day(_NOW, "UTC", goals, meso)` | ✓ |
| `test_nutrios_engine.py` | 189 | `engine.resolve_day(now_utc, "America/Denver", goals, meso)` | ✓ |
| `test_nutrios_engine.py` | 201 | `engine.resolve_day(now_utc, "America/Denver", goals, meso)` | ✓ |

No tool entrypoints exist yet (steps 4–6 are future). All six test call sites pass `tz`. No corrective regression.

---

## 4. Judgment Calls

### J1: `pytest.ini` added to scope `make test`

**Decision:** Added `pytest.ini` with `testpaths = skills` so bare `$(PYTEST)` in `make test` collects exactly the skill test suites and ignores scratch test files elsewhere in the repo.  
**Why:** The spec says `make test: $(PYTEST)` (bare) and requires the count to match the sum of four scoped targets. Without `pytest.ini`, bare pytest collects 282 tests (from `watch-listing-workspace/` and other locations). With `pytest.ini`, bare pytest collects exactly 138.  
**Alternative:** Use `$(PYTEST) skills/` for `make test`. Rejected: the spec explicitly shows bare `$(PYTEST)`. The `pytest.ini` is the correct mechanism to scope discovery.  
**Future effect:** When a second skill lands in `skills/<name>/tests/`, its tests are automatically included in `make test` with no Makefile change — only the per-skill targets need to be added.

### J2: Makefile uses `skills/nutrios/tests` (lowercase), not `skills/nutriOS/tests`

**Decision:** All scoped Makefile targets use `skills/nutrios/tests` — the path that pytest can actually find on this macOS filesystem.  
**Why:** macOS APFS is case-insensitive at the filesystem level, but pytest's directory walker is not. `python3.12 -m pytest skills/nutriOS/tests` returns "not found" while `skills/nutrios/tests` works. The spec uses `skills/nutriOS/tests`, but that path is unreachable by the tools.  
**Linux deployment risk:** On a case-sensitive filesystem, git's tracked path `skills/nutriOS/lib/` would be a distinct directory from `skills/nutrios/`. The Makefile would break. If this repo is ever deployed on Linux, the `lib/` and `tests/` directories need to be moved to the correct case, and the Makefile updated to match.

### J3: Future-skill pattern documented in Makefile comment block

**Decision:** Pattern lives in a comment block at the top of the Makefile, not in a separate `CONTRIBUTING.md`.  
**Why:** The pattern is directly adjacent to the working example (nutriOS block). A developer opening the Makefile sees both the pattern and the example in one file without context-switching.  
**Risk:** If a `CONTRIBUTING.md` is added later for other workflows, the test pattern would be in two places. Low risk at current scale.

---

## 5. Pattern Propagation

When the next skill lands, the author opens `Makefile`, reads the comment block at the top, and copies the nutriOS block verbatim — substituting the skill name and module names. They add the new target names to the `.PHONY` line and to the `help` echo list. The `make test` target requires no change: `pytest.ini`'s `testpaths = skills` automatically picks up the new skill's tests as long as they live under `skills/<name>/tests/`. The only mandatory Makefile edit is adding the per-skill named targets. This is explicit in the comment block and should be clear to a developer joining cold, because the existing nutriOS block is a working example of exactly the pattern described.

---

*End of review. J2 (macOS casing) is the only risk item with a future deployment implication.*
