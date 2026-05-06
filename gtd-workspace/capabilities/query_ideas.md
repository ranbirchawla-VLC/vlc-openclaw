# query_ideas - GTD Idea Query Capability

## Purpose

Surface ideas without overwhelm. Call `query_ideas`; render records verbatim in inward voice.

## Voice Register

SOUL.md inward voice. Quiet and clean.

## Verbatim Render Rule

Render each idea record using the fields returned by the tool (9-field read projection): `id`,
`title`, `topic`, `content`, `status`, `created_at`, `updated_at`, `last_reviewed`,
`completed_at`. Surface only non-null fields. Surface `total_count`. If `truncated: true`, offer
to narrow.

## Workflow

1. Read user message; extract `limit` if stated.
2. Call `query_ideas` with `user_id` and optional `limit`.
3. Render results per Verbatim Render Rule.

## Branches

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. Results returned | `total_count > 0` | Render verbatim; surface count; if truncated, offer to narrow |
| B. Empty results | `total_count = 0` | Acknowledge plainly |
| C. Filter requested | User asks to filter by topic, domain, or status | State plainly that filtering by those fields is not available yet; render all; let user scan |

## Composition Guardrails

1. Verbatim record rendering per 9-field projection.
2. No editorial framing.
3. Do not fabricate a filter; do not claim to filter when the tool does not support it.

## LLM Responsibilities

- Call `query_ideas` with `user_id` and optional `limit`.
- Render returned records verbatim per Verbatim Render Rule.

## What the LLM Does NOT Do

- Does not filter in context after the tool returns.
- Does not summarize across idea records.
- Does not claim filtering capability that does not exist in the schema.
