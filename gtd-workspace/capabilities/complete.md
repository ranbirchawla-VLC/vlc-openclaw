# complete - GTD Complete Capability

## Purpose

Mark a task or idea as done. Finds the record by ID, stamps it completed, and
confirms with the title from the returned `completed` object.

## Workflow

1. If the user names a specific item ("mark the Chris call done"), call `query_tasks`
   (or `query_ideas`) first to surface the matching record and its `id`.
2. Identify the correct record from the query result by matching the user's description
   to the `title` field. If multiple records could match, ask which one (Branch B).
3. Call `complete` with `{user_id, record_id, record_type}`.
4. On `ok: true`: render per Verbatim Render Rule (Branch A).
5. On `ok: false`: read `error.code`; route to Branch C, D, or E.

**Tool parameters:**

| Parameter | Value |
|---|---|
| `user_id` | `sender_id` from conversation metadata (untrusted) |
| `record_id` | `id` field from the prior query result |
| `record_type` | `"task"` or `"idea"` — match the type you queried |

## Verbatim Render Rule

On success, render the `completed` object from `data.completed`. Confirmation is
exactly one short sentence: "Done — [title]." Do not recompose or embellish.

## Branches

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. Successful completion | `ok: true`; `completed` returned | "Done — [title from data.completed.title]." One sentence. |
| B. Ambiguous match | Query returns multiple plausible matches | Name the options briefly; ask which one; end turn |
| C. `record_not_found` | `error.code = "record_not_found"` | "I couldn't find that one — want to check what's on the list?" |
| D. `already_completed` | `error.code = "already_completed"` | "That one's already marked done." |
| E. `unsupported_record_type` | `error.code = "unsupported_record_type"` | "I can only complete tasks and ideas right now." |
| F. `storage_io_failed` | `error.code = "storage_io_failed"` | Name the failure; offer to try again; do not confirm completion |

## Composition Guardrails

1. Always query first to get the `record_id`. Never guess or fabricate an ID.
2. Confirmation renders only from `data.completed.title`. Never recompose user input.
3. One question per turn if clarification is needed.
4. No persistence narration.
5. Do not attempt to complete a parking_lot item; that is not supported.

## LLM Responsibilities

- Call `query_tasks` or `query_ideas` to find the `record_id`.
- Identify the correct record by matching user description to `title`.
- Call `complete` with `{user_id, record_id, record_type}`.
- On success: render `data.completed.title` per Verbatim Render Rule.
- On failure: read `error.code` and route to the correct branch.

## What the LLM Does NOT Do

- Does not fabricate a `record_id` from user input.
- Does not confirm completion on any non-`ok: true` response.
- Does not attempt to complete a `parking_lot` record.
- Does not ask multiple questions in one turn.
