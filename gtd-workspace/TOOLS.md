# Tools — GTD Workspace

Python tools are deterministic and always available. LLM skills are invoked only when a Python tool explicitly signals `needs_llm: true`, or when the user requests a narrative summary.

---

## Python Tools

All six tools are standalone-runnable and independently testable.

| Tool | Purpose | CLI invocation |
|------|---------|----------------|
| `common.py` | Shared path resolution, user-scoped JSONL I/O, enums, `parse_iso` | Imported by other tools |
| `gtd_normalize.py` | Classify raw text into task/idea/parking_lot with confidence scoring | `python3 tools/gtd_normalize.py '<raw_input>'` |
| `gtd_validate.py` | Validate a candidate record against JSON schema and business rules | `python3 tools/gtd_validate.py <type> <file.json>` |
| `gtd_write.py` | Persist a validated record to user-scoped JSONL storage | `python3 tools/gtd_write.py <record_type> <file.json>` |
| `gtd_query.py` | Filter and rank tasks by context, priority, energy, duration | `python3 tools/gtd_query.py <user_id> [--context @computer] [--priority high] [--limit 5]` |
| `gtd_review.py` | Structured scan: missing metadata, stale tasks, overdue ideas, waiting follow-ups, parking lot | `python3 tools/gtd_review.py <user_id>` |
| `gtd_delegation.py` | Group waiting-for and delegated tasks by person, sorted by oldest untouched | `python3 tools/gtd_delegation.py <user_id>` |

### Key contracts

- Every tool reads from and writes to user-scoped paths via `common.user_path(user_id)`.
- No tool calls the LLM or reads another user's data.
- `gtd_write` always runs `gtd_validate` before persisting.
- `gtd_query` never returns idea or parking-lot records — tasks only.

---

## LLM Skills

Defined in `skills/gtd/`. See `skills/gtd/SKILL.md` for full invocation rules.

| Skill | Invoked when | Returns |
|-------|-------------|---------|
| `llm_ambiguous_classifier` | `gtd_normalize` returns `needs_llm: true` (confidence < 0.60) | `{ record_type, rationale }` |
| `llm_title_rewriter` | Voice transcription is garbled, overly long, or unclear | Clean title string |
| `llm_domain_inferrer` | Idea has no domain and no keyword match above threshold | `{ suggested_domain, is_new_domain, rationale }` |
| `llm_clarification_generator` | A required field is still missing after classify + validate | `{ status, question, missing_field, options }` |
| `llm_review_narrative` | User explicitly requests a conversational review summary | 3–5 sentence plain text |

### Invocation rule

```
needs_llm == true from a Python tool  →  invoke the appropriate skill
Otherwise                              →  no LLM call
```

LLM skills never write to storage, read files directly, or call each other.

---

## Paths

```
storage_root:  $GTD_STORAGE_ROOT or gtd-workspace/storage/
user_data:     {storage_root}/gtd-agent/users/{user_id}/
schemas:       references/schemas/
taxonomy:      references/taxonomy.json
skills:        skills/gtd/
memory:        memory/
```
