# GTD Agent — Vardalux Collections OpenClaw

A personal GTD system built on native Python tools and a minimal LLM footprint. Captures tasks, ideas, and delegation reminders from Telegram. Retrieval, review, and delegation grouping are entirely Python — no LLM cost on the daily hot path.

---

## Architecture

```
Telegram message
       │
       ▼
gtd_router.py          ← single entry point; routes normaliser output to correct branch
       │
       ├── capture branch ──────────────────────────────────────────────────────────────────┐
       │   gtd_normalize → [LLM fallback if needs_llm] → gtd_write (calls validate inside) │
       │                                                                                     │
       ├── retrieval branch (/next)                                                          │
       │   gtd_query                                                                         │
       │                                                                                     │
       ├── review branch (/review)                                                           │
       │   gtd_review → [optional llm_review_narrative]                                     │
       │                                                                                     │
       ├── delegation branch (/waiting)                                                      │
       │   gtd_delegation                                                                    │
       │                                                                                     │
       └── system commands (/start /help /settings /privacy)                                │
                                                                                             │
MNEMO ─────────────────────────────────────────── compact context injection on LLM calls ──┘
```

### Design principles

| Principle | What it means here |
|-----------|--------------------|
| Python-first | All deterministic work runs in Python. LLM is called only when `needs_llm: true`. |
| Telegram-first identity | Each user is anchored by their `telegram_chat_id`. All other channels (Alexa, future) map into this same identity. |
| User isolation | `user_path(user_id)` scopes all reads and writes. No tool can access another user's data. Path traversal is rejected at the API level. |
| MNEMO for memory | Compact context injection on LLM calls only. No LLM reads raw storage files. |
| Near-zero LLM cost | Clean captures, all retrievals, structured review, and delegation listing: zero LLM calls. |

---

## Workspace structure

```
gtd-workspace/
  tools/                   ← Python tools (the core)
    common.py              ← shared utilities, enums, storage I/O
    gtd_normalize.py       ← intent classification and field extraction
    gtd_validate.py        ← schema + business rule validation
    gtd_write.py           ← validated persistence
    gtd_query.py           ← task retrieval and ranking
    gtd_review.py          ← structured review scan (5 sections)
    gtd_delegation.py      ← delegation/waiting-for grouping
    gtd_router.py          ← orchestrator — routes to correct tool branch
  tests/                   ← 144 tests, all passing
    conftest.py            ← shared fixtures (storage, user_a/b, make_task/idea)
    test_common.py         ← 25 tests
    test_normalize.py      ← 25 tests
    test_validate.py       ← 20 tests
    test_write.py          ← 10 tests
    test_query.py          ← 10 tests
    test_review.py         ← 11 tests
    test_delegation.py     ← 8 tests
    test_router.py         ← 17 tests
    test_e2e_single_user.py ← 10 e2e tests
    test_e2e_isolation.py  ← 9 isolation tests
  skills/gtd/              ← LLM skill prompt files (invoked only on needs_llm: true)
    SKILL.md               ← skill index and invocation rules
    llm_ambiguous_classifier.md
    llm_title_rewriter.md
    llm_domain_inferrer.md
    llm_clarification_generator.md
    llm_review_narrative.md
  memory/
    MNEMO.md               ← MNEMO integration config and injection trigger map
  references/
    taxonomy.json          ← starter contexts, areas, and idea domains
    schemas/               ← JSON Schema draft-07 files (documentation)
  pipeline.md              ← routing table and branch definitions
  openclaw.json            ← tool registry (update CLI signatures before production)
  AGENTS.md                ← agent identity and rules
  TOOLS.md                 ← tool reference: CLI signatures, contracts, paths
```

---

## Current build status

### Implemented (144/144 tests passing)

| Component | Status |
|-----------|--------|
| `gtd_normalize` — intent classification, field extraction, confidence scoring | Done |
| `gtd_validate` — schema + business rules, no external deps | Done |
| `gtd_write` — user-isolated JSONL persistence | Done |
| `gtd_query` — filtering, sorting, limit | Done |
| `gtd_review` — 5-section structured scan | Done |
| `gtd_delegation` — grouped by person, sorted by oldest untouched | Done |
| `gtd_router` — deterministic orchestrator, needs_llm signal | Done |
| LLM skills (5) — ambiguous classifier, title rewriter, domain inferrer, clarification generator, review narrative | Done |
| MNEMO integration config | Done |
| End-to-end single-user flows | Done |
| Multi-user isolation + path traversal protection | Done |

### Deferred

| Component | Status |
|-----------|--------|
| User onboarding flow (profile creation via `/start`) | Not yet built |
| `openclaw.json` update with correct CLI signatures | Needs update before production |
| MNEMO passive observation runtime (Rust side) | Config documented; runtime not yet wired |
| Telegram voice note transcription adapter | Not yet built |
| Alexa identity linking | Not yet scoped |

---

## Reference documents

| Document | Purpose |
|----------|---------|
| `gtd-claude-implementation-packet-v2.md` | Authoritative build spec — read this first |
| `SETUP.md` | End-to-end deployment: bot, storage, OpenClaw, MNEMO, onboarding |
| `TESTING.md` | Running tests, test coverage map, pre-production checklist |
| `VOICE-INTEGRATION.md` | Telegram voice notes, Wispr Flow, Alexa (future) |
| `TOOLS.md` | CLI signatures, output contracts, storage paths |
| `pipeline.md` | Routing table and branch-level behaviour |
| `memory/MNEMO.md` | MNEMO memory keys, injection triggers, scope rules |
| `skills/gtd/SKILL.md` | LLM skill index and invocation rules |

---

## Quick start

```bash
cd gtd-workspace/

# Run all tests
python -m pytest tests/ -v

# Try the normaliser
python3 tools/gtd_normalize.py "/task call the customs broker @phone"

# Route a message end-to-end (dev storage)
GTD_STORAGE_ROOT=/tmp/gtd-dev python3 tools/gtd_router.py "/task call the customs broker @phone" user_123 chat_456
```

For deployment, start with `SETUP.md`.
