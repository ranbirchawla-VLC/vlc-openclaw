# MNEMO Integration — GTD Agent

MNEMO is the transparent HTTP proxy that gives the GTD agent persistent memory. It sits between OpenClaw and the LLM API. Python tools own all file I/O; MNEMO owns compact context injection when the LLM is actually called.

---

## Operating mode

**Passive observation:** MNEMO observes all sessions and builds its memory store from captured inputs, written records, and review results. No explicit write calls are needed from the agent — MNEMO infers state from observed tool outputs.

**Selective injection:** MNEMO only injects context when the LLM is actually invoked (i.e., when `needs_llm: true` or a narrative skill is requested). On zero-LLM paths — capture, retrieval, structured review, delegation — MNEMO does nothing.

---

## What MNEMO injects (compact, not raw files)

### User profile context

Injected on every LLM call for this user.

```json
{
  "mnemo_key": "gtd:user:{user_id}:profile",
  "schema": {
    "display_name": "string",
    "status": "active|inactive",
    "telegram_chat_id": "string",
    "alexa_linked": false
  }
}
```

### Recent capture history

Last 5–10 captures for conversational continuity. Allows the LLM to understand what the user has been working on without re-reading JSONL files.

```json
{
  "mnemo_key": "gtd:user:{user_id}:recent_captures",
  "schema": {
    "items": [
      { "title": "string", "record_type": "task|idea|parking_lot", "captured_at": "iso8601" }
    ],
    "max_items": 10
  }
}
```

### Personal taxonomy extensions

Contexts, areas, and domains the user has added beyond the starter set in `references/taxonomy.json`.

```json
{
  "mnemo_key": "gtd:user:{user_id}:taxonomy_extensions",
  "schema": {
    "contexts": ["@custom-context"],
    "areas": ["custom-area"],
    "domains": ["custom-domain"]
  }
}
```

### Review state

Last review date, flagged item count, and per-section counts. Injected when the LLM is invoked for `llm_review_narrative`. Only include sections with count > 0 — skip zero-count sections to keep injection minimal.

```json
{
  "mnemo_key": "gtd:user:{user_id}:review_state",
  "schema": {
    "last_reviewed_at": "iso8601",
    "total_items_flagged": 4,
    "section_counts": {
      "stale_active_tasks": 3,
      "waiting_for_followup": 1
    }
  }
}
```

---

## What MNEMO must NOT inject

- Raw JSONL file contents — Python tools handle all file reads
- Full task or idea lists — pass only recent captures (last 5–10), not the whole store
- Profile JSON verbatim — summarise to the keys listed above
- Anything on zero-LLM paths — no injection overhead on clean captures, retrieval, or structured review

---

## Injection trigger map

| Branch | LLM called? | MNEMO injects? |
|---|---|---|
| Capture (clean, `needs_llm: false`) | No | No |
| Capture (ambiguous, `needs_llm: true`) | Yes | Profile + recent captures + taxonomy extensions |
| Retrieval (`/next`, `/waiting`) | No | No |
| Review (structured output) | No | No |
| Review (narrative requested) | Yes | Profile + review state |
| Delegation | No | No |

---

## Memory update events

MNEMO should update its store when:

| Event | Keys updated |
|---|---|
| `gtd_write` succeeds with a new record | `recent_captures` (prepend, trim to 10) |
| `gtd_review` is called | `review_state` |
| User adds a new context, area, or domain | `taxonomy_extensions` |
| Profile is created or updated | `profile` |

---

## Scope and isolation

Each memory key is namespaced by `user_id`. MNEMO must never inject one user's context into another user's LLM call. The `gtd:user:{user_id}:` prefix enforces this at the key level.
