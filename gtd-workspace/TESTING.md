# Testing — GTD Agent

---

## Running the test suite

From `gtd-workspace/`:

```bash
python -m pytest tests/ -v
```

All 144 tests should pass in under one second. No network calls, no external dependencies, no LLM calls.

Run a single test file:

```bash
python -m pytest tests/test_router.py -v
python -m pytest tests/test_e2e_isolation.py -v
```

Run a single test by name:

```bash
python -m pytest tests/test_router.py::test_task_with_context_captures_ok -v
```

---

## Storage isolation in tests

`conftest.py` sets `GTD_STORAGE_ROOT` to a fresh `tmp_path` for every test that uses the `storage` fixture. No test reads or writes to the real storage root. No cleanup is required.

Tests that use `tmp_path` and `monkeypatch` directly (the older pattern in `test_write.py`, `test_query.py`, etc.) work the same way.

**You do not need to set `GTD_STORAGE_ROOT` to run tests.** The fixtures handle it automatically.

---

## Test file coverage

| File | Module under test | Tests | What it covers |
|------|------------------|-------|----------------|
| `test_common.py` | `common.py` | 25 | Enums, `user_path`, `assert_user_match`, `read_jsonl`, `append_jsonl`, `new_id`, `now_iso` |
| `test_normalize.py` | `gtd_normalize.py` | 25 | Explicit commands, NL classification, field extraction, confidence scoring, output contract shape |
| `test_validate.py` | `gtd_validate.py` | 20 | Schema validation, business rules (active task context, delegated/waiting constraints, completed_at) |
| `test_write.py` | `gtd_write.py` | 10 | Round-trip write, ID/timestamp generation, isolation mismatch rejection, unsupported record type |
| `test_query.py` | `gtd_query.py` | 10 | Status filtering, context/priority/energy filters, duration threshold, sort order, limit, isolation |
| `test_review.py` | `gtd_review.py` | 11 | All five review sections, cadence-aware idea staleness, stale task detection, correct section ordering |
| `test_delegation.py` | `gtd_delegation.py` | 8 | Group-by-person, sort by oldest_untouched, items within group, total count |
| `test_router.py` | `gtd_router.py` | 17 | System commands, retrieval routing, task/idea capture (ok and clarification), delegation capture, LLM fallback |
| `test_e2e_single_user.py` | Full pipeline | 10 | Capture→persist→retrieve round-trips, review flags, delegation listing, NL capture |
| `test_e2e_isolation.py` | Cross-user isolation | 9 | Read isolation, write isolation, path traversal rejection, empty user_id rejection |

Stub files (`test_gtd_{normalize,validate,write,delegation,query,review}.py`) are empty — superseded by the full test files above.

---

## Shared fixtures (conftest.py)

All integration and e2e tests use fixtures from `tests/conftest.py`:

| Fixture | Returns | Notes |
|---------|---------|-------|
| `storage` | `Path` (tmp dir) | Sets `GTD_STORAGE_ROOT`; required by `user_a`, `user_b` |
| `user_a` | `"user_alpha"` | Depends on `storage` |
| `user_b` | `"user_beta"` | Depends on `storage` |
| `chat_a` | `"chat_alpha_001"` | Stable Telegram chat ID string |
| `chat_b` | `"chat_beta_002"` | Stable Telegram chat ID string |
| `make_task` | factory `(user_id, chat_id, **kwargs) → dict` | Builds pre-stamped valid task records |
| `make_idea` | factory `(user_id, chat_id, **kwargs) → dict` | Builds pre-stamped valid idea records |

---

## Adding tests for new features

### New tool

1. Create `tests/test_<tool_name>.py`.
2. Import the tool function at the top.
3. Use `tmp_path` + `monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))`, or use the `storage` fixture from conftest.
4. Write tests for: happy path, edge cases, isolation (tool must not read another user's data).

### New route or branch in `gtd_router.py`

1. Add unit tests in `test_router.py` verifying the branch is set correctly.
2. Add e2e tests in `test_e2e_single_user.py` for the full round-trip.
3. If the feature has cross-user implications, add to `test_e2e_isolation.py`.

### New validation rule in `gtd_validate.py`

1. Add a test in `test_validate.py` that triggers the rule and asserts the correct error field.
2. Add a test that confirms a valid record passes the rule.

### Bug fixes

Write a test that reproduces the bug **before** fixing it. The test should fail on the current code and pass after the fix. Commit both together.

---

## Running tools standalone (manual testing)

Each tool is independently runnable from `gtd-workspace/`:

```bash
# Normalise a raw input
python3 tools/gtd_normalize.py "I need to call the customs broker @phone"

# Route a message end-to-end
python3 tools/gtd_router.py "I need to call the customs broker @phone" user_123 chat_456

# Query tasks for a user
GTD_STORAGE_ROOT=/tmp/gtd-dev python3 tools/gtd_query.py user_123 --context @phone --limit 3

# Run a review
GTD_STORAGE_ROOT=/tmp/gtd-dev python3 tools/gtd_review.py user_123

# List delegation items
GTD_STORAGE_ROOT=/tmp/gtd-dev python3 tools/gtd_delegation.py user_123
```

`gtd_router.py` exits with code `0` on deterministic success, `2` when `needs_llm: true`.

---

## Pre-production checklist

Run this before handling any real user data:

```
[ ] All 144 tests pass: python -m pytest tests/ -v
[ ] Isolation tests pass: python -m pytest tests/test_e2e_isolation.py -v
[ ] GTD_STORAGE_ROOT is set to the production path (not /tmp)
[ ] Separate Telegram bot token confirmed (not the watch-listing bot)
[ ] OpenClaw agent family is separate from watch-listing
[ ] No regressions in watch-listing pipeline tests
[ ] First user onboarded manually: /start → profile.json exists → /next returns []
[ ] Second user onboarded: each user's /next returns only their own tasks
```
