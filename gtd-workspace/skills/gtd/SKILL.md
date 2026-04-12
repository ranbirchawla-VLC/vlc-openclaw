# GTD Agent — LLM Skills Index

LLM skills are invoked **rarely** and only when a Python tool explicitly signals it. The hot capture path, all retrieval queries, and the structured review scan are handled entirely by Python. No LLM call occurs unless a tool returns `needs_llm: true` or the user explicitly requests a narrative.

---

## Invocation rule

```
Python tool result.needs_llm == true  →  invoke the appropriate skill
Otherwise                              →  Python handles it, no LLM call
```

Never call these skills proactively, on a hunch, or to improve output that Python already produced.

---

## Skills

### `llm_ambiguous_classifier`

**File:** `llm_ambiguous_classifier.md`

**When:** `gtd_normalize` returns `needs_llm: true` because the input did not match any known intent pattern with sufficient confidence (confidence < 0.60).

**Receives:**
- `raw_input` — the original user text
- `candidate` — partial fields extracted by the normalizer (`title`, `context_hint`, `priority_hint`, `area_hint`, `missing_fields`)
- `contexts` — the user's known context list from taxonomy

**Returns:**
```json
{ "record_type": "task|idea|delegation|parking_lot", "rationale": "one sentence" }
```

**After this call:** pass `record_type` back to the capture branch. If `parking_lot`, write a parking-lot record immediately. Otherwise, proceed to `gtd_validate` on the candidate.

---

### `llm_title_rewriter`

**File:** `llm_title_rewriter.md`

**When:** Input text (transcribed or typed) is garbled, overly long, or unclear. Checked after normalizer, before `gtd_validate`.

**Receives:**
- `raw_text` — the original transcription
- `record_type` — `task` or `idea`

**Returns:** A single clean title string — plain text, no JSON, no quotes, max 100 characters, no newlines. Tasks must start with a verb. Ideas should be a noun phrase or question.

---

### `llm_domain_inferrer`

**File:** `llm_domain_inferrer.md`

**When:** An idea record has no `domain` and none of the normalizer's keyword matches are above threshold for any known domain.

**Receives:**
- `title` — the idea title
- `spark_note` — optional spark note or `null`
- `domains` — the user's current domain list from taxonomy

**Returns:**
```json
{ "suggested_domain": "slug", "is_new_domain": false, "rationale": "one sentence" }
```

If `is_new_domain` is `true`, prompt the user to confirm before adding it to their taxonomy.

---

### `llm_clarification_generator`

**File:** `llm_clarification_generator.md`

**When:** A required field is still missing after normalizer + classifier have both run, and `gtd_validate` returns an error for that field.

**Receives:**
- `record_type` — `task` or `idea`
- `missing_field` — the specific field name that failed validation
- `candidate` — current partial record fields
- `taxonomy` — contexts and domains relevant to the record type

**Returns:**
```json
{ "status": "clarify", "question": "...", "missing_field": "...", "options": [...] }
```

**Clarification order:** See `llm_clarification_generator.md` for the sequence and skip-populated-fields rule (task: context → title → intent; idea: domain → context → review_cadence).

---

### `llm_review_narrative` *(optional)*

**File:** `llm_review_narrative.md`

**When:** User explicitly asks for a conversational review summary (e.g. "summarise my review", "give me the short version"). Not called on `/review` by default — the structured output from `gtd_review` is returned as-is unless requested.

**Receives:** The full structured review object from `gtd_review`.

**Returns:** 3–5 sentences of plain text. No JSON.

---

## What these skills must not do

- Write to storage directly (all writes go through `gtd_write`)
- Read from storage directly (all reads go through Python tools)
- Call each other
- Be invoked on zero-LLM paths (capture, retrieval, structured review)
- Make routing decisions — they return structured data; the orchestrator decides what to do with it
