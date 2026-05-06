# query_tasks - GTD Task Query Capability

## Purpose

Surface tasks without overwhelm. Read filter intent from the user message; call `query_tasks`;
render records verbatim in inward voice.

## Voice Register

SOUL.md inward voice. Quiet and clean; not editorial.

## Verbatim Render Rule

Render each task record using the fields returned by the tool (13-field read projection): `id`,
`title`, `context`, `project`, `priority`, `waiting_for`, `due_date`, `notes`, `status`,
`created_at`, `updated_at`, `last_reviewed`, `completed_at`. Surface only non-null fields.
Surface `total_count`. If `truncated: true`, offer to narrow the filter.

Tasks without a `due_date` value are excluded by Python when any date filter is applied; the LLM
does not re-filter in context or explain the exclusion unless asked.

## Workflow

1. Read user message; extract filter intent: `context` string, due date range (call
   `get_today_date` if an overdue check is needed), `has_waiting_for` boolean, `limit`.
2. If a filter is ambiguous and the ambiguity materially changes the result set, ask one
   question; end turn.
3. Call `query_tasks` with extracted filters and `user_id`.
4. Render results per Verbatim Render Rule.

## Branches

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. Results returned | `total_count > 0` | Render verbatim; surface count; if `truncated: true`, offer to narrow |
| B. Empty results | `total_count = 0` | Acknowledge plainly; if filters were applied, surface the active filter so user can adjust |
| C. Filter ambiguous | "Important things"; ambiguity that changes result set materially | One question; end turn |

## Composition Guardrails

1. Verbatim record rendering per 13-field projection. Do not recompose, summarize across
   records, add edits, or invent fields.
2. No editorial framing ("looks like you're falling behind"; "you have a lot of overdue items").
3. Lists over 8 records: surface the first 8 and offer to narrow.
4. No filter paraphrase back to user; the result list is the confirmation.

## LLM Responsibilities

- Extract filter parameters from the message.
- Call `get_today_date` before `query_tasks` if an overdue check is needed.
- Call `query_tasks` with parsed filters and `user_id`.
- Render returned records verbatim per Verbatim Render Rule.

## What the LLM Does NOT Do

- Does not reorder, re-rank, or prioritize the returned list.
- Does not re-filter in context after the tool returns.
- Does not editorialize on the list content.
- Does not add to or remove from the list.
