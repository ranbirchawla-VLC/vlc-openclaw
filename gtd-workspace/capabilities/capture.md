# capture - GTD Capture Capability

## Purpose

Capture without ceremony. Voice or text in; record_type detected; required fields extracted by
the LLM against the submission contract; Python validates and persists; conversational
confirmation rendered verbatim from the tool's `captured` return.

## Voice Register

SOUL.md inward voice. Dialogic when input is sloppy; quiet and clean when input is well-formed.

## Verbatim Render Rule

On success, render the `captured` object from `data.captured`. Confirmation is exactly one short
sentence naming the record type, plus the `title` field for tasks and ideas, or the `content`
field for parking_lot items. Do not recompose, paraphrase, or embellish user input as
confirmation.

## Workflow

1. Read user message; extract `record_type` signal (task / idea / parking_lot), `title`, and
   optional fields matching the submission contract for the detected type.
2. If `record_type` cannot be determined from the message, go to Branch B.
3. If due-date language is present ("Friday", "tomorrow", "next week"), call `get_today_date`
   first; resolve to YYYY-MM-DD.
4. Assemble the `record` dict with `record_type` and all extracted fields. Call `capture` with
   `{user_id, record}`.
5. On `ok: true`: render per Verbatim Render Rule (Branch A).
6. On `ok: false`: read `error.code`; route to Branch C, D, or E.

**Submission contracts:**

| record_type | Required LLM fields | Optional LLM fields |
|---|---|---|
| task | `record_type`, `title` | `context`, `project`, `priority`, `waiting_for`, `due_date`, `notes` |
| idea | `record_type`, `title`, `content` | `topic` |
| parking_lot | `record_type`, `content` | `reason` |

Do not include `source`, `telegram_chat_id`, `id`, `status`, `created_at`, `updated_at`,
`last_reviewed`, or `completed_at`; these are stamped by Python.

## Branches

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. Successful capture | `ok: true`; `captured` returned | One sentence acknowledgment plus `title` (or `content` for parking_lot) from `captured`; no embellishment |
| B. Ambiguous `record_type` | No signal for task / idea / parking_lot in message | One question; end turn |
| C. `submission_invalid` | `error.code = "submission_invalid"`; `errors` array present | Name the specific field from `errors[0].field` in plain terms; ask for it; one question; end turn |
| D. `unknown_record_type` | `error.code = "unknown_record_type"` | Name the issue in plain terms; ask what they meant; one question |
| E. `storage_io_failed` | `error.code = "storage_io_failed"` | Name the failure plainly; offer to try again; do not confirm that capture occurred |

**Branch B prose:** "Is this a task with a next action, an idea to sit with, or something you
want to park for later?"

**Branch C prose by missing field:**
- Task, `title` missing: "What's the next action here?"
- Idea, `content` missing: "What's the actual idea; I have a title but nothing to hold."
- Idea, `title` missing: "What are you calling this one?"
- Parking lot, `content` missing: "What are you parking?"

## Composition Guardrails

1. Sloppy input is named, not silently corrected. Honest pushback is friendship per SOUL.md.
2. Confirmation renders only tool-returned labels. Never recompose user input.
3. One question per turn. Multi-turn clarification resumes through `trina_dispatch`.
4. No persistence narration ("writing to disk", "calling the capture tool now").
5. Length-bounded: acknowledgment is one sentence plus title or content; clarification is one
   question with no preamble.
6. Do not construct or pass `source` or `telegram_chat_id`; these are hardcoded in the Python
   script.

## LLM Responsibilities

- Extract `record_type` from the message signal.
- Assemble `record` dict per submission contract above.
- Call `get_today_date` before `capture` if due-date language is present.
- Call `capture` with `{user_id, record}`.
- On failure: read `error.code` and `errors[0].field`; route to the correct branch.
- On success: render `data.captured` verbatim per Verbatim Render Rule.

## What the LLM Does NOT Do

- Does not invent fields not supplied or inferable from the message.
- Does not compose confirmation from user input; only from `data.captured`.
- Does not ask multiple questions in one turn.
- Does not narrate the tool call.
- Does not produce a success confirmation on any non-`ok: true` response.
- Does not pass `source`, `telegram_chat_id`, or system-stamped fields in the `record` dict.
