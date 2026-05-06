# query_parking_lot - GTD Parking Lot Query Capability

## Purpose

Surface parking lot items without overwhelm. Call `query_parking_lot`; render records verbatim
in inward voice.

## Voice Register

SOUL.md inward voice. Quiet and clean.

## Verbatim Render Rule

Render each parking lot record using the fields returned by the tool (8-field read projection):
`id`, `content`, `reason`, `status`, `created_at`, `updated_at`, `last_reviewed`,
`completed_at`. Surface only non-null fields. `status` is always `"open"` in the current
version. Surface `total_count`. If `truncated: true`, offer to narrow.

## Workflow

1. Read user message; extract `limit` if stated.
2. Call `query_parking_lot` with `user_id` and optional `limit`.
3. Render results per Verbatim Render Rule.

## Branches

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. Results returned | `total_count > 0` | Render verbatim; surface count; if truncated, offer to narrow |
| B. Empty results | `total_count = 0` | Acknowledge plainly |
| C. Completed items requested | User asks for done or completed parking lot items | State plainly that the status field is only `"open"` in the current version; completed parking lot tracking is not yet available |

## Composition Guardrails

1. Verbatim record rendering per 8-field projection.
2. No editorial framing.
3. Do not invent a completed status filter; it does not exist in the current scope.

## LLM Responsibilities

- Call `query_parking_lot` with `user_id` and optional `limit`.
- Render returned records verbatim per Verbatim Render Rule.

## What the LLM Does NOT Do

- Does not filter in context after the tool returns.
- Does not summarize across records.
- Does not claim completed-status capability that does not exist.
