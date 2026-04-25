# vlc-openclaw — Infrastructure Summary: Makefile + Test Layout

Prepared: 2026-04-24  
Branch: feature/nutrios-v2  

---

## Files Changed

| File | Action | Lines |
|---|---|---|
| `skills/nutrios/lib/nutrios_store.py` | +5 (non-string guard in resolve_user_id_from_peer) | 324 |
| `skills/nutrios/tests/test_nutrios_store.py` | +7 (one new test) | 295 |
| `pytest.ini` | created — restricts bare pytest to `skills/` | 3 |
| `Makefile` | created — 7 named test targets | 46 |
| `skills/nutrios/lib/*` (5 files) | moved from `nutrios-workspace/skills/nutrios/lib/` | — |
| `skills/nutrios/tests/*` (5 files) | moved from `nutrios-workspace/skills/nutrios/tests/` | — |

---

## Seven-Target Verification

| Target | Result |
|---|---|
| `make help` | prints 6-line target list ✓ |
| `make test` | **138 passed** |
| `make test-nutrios` | **138 passed** |
| `make test-nutrios-time` | **22 passed** |
| `make test-nutrios-store` | **28 passed** |
| `make test-nutrios-engine` | **67 passed** |
| `make test-nutrios-models` | **21 passed** |

Sum of scoped targets: 22 + 28 + 67 + 21 = **138** = `make test`. Exact match.

---

## Commits (this task)

```
refactor: move nutrios v2 lib+tests to skills/nutriOS — 137 tests pass at new location
fix(store): validate resolve_user_id_from_peer returns str — StoreError on non-string index value
build: Makefile + pytest.ini — bare make test collects all skills via testpaths=skills
```

---

## Allowlist targets (Ranbir's step)

After this clears review, add to `.claude/settings.json` `permissions.allow`:

```json
"Bash(make help)",
"Bash(make test)",
"Bash(make test-nutrios)",
"Bash(make test-nutrios-time)",
"Bash(make test-nutrios-store)",
"Bash(make test-nutrios-engine)",
"Bash(make test-nutrios-models)"
```

Branch holds. Step 4 (Mnemo) starts after the gate clears.
