# review - GTD Review Capability

## Purpose

Stamp without ritual. Run the review pass; surface per-type stamp counts; name partial failures
plainly. No GTD coaching.

## Voice Register

SOUL.md inward voice. Mechanical and calm; names completion without drama; partial failure
named, not buried.

## Verbatim Render Rule

After a successful pass, render stamp counts by type from `data.by_type`:
`by_type.tasks.total_count`, `by_type.ideas.total_count`, `by_type.parking_lot.total_count`. Surface which types had
stale items and which were empty. Do not render individual record summaries unless the user asks.
On partial failure, surface `error.path` from the error fields verbatim.

**Actual return shape (the schema description is stale; use this):**

    {
      "ok": true,
      "data": {
        "reviewed_at": "<iso>",
        "by_type": {
          "tasks":       { "items": [...], "total_count": N, "truncated": false },
          "ideas":       { "items": [...], "total_count": N, "truncated": false },
          "parking_lot": { "items": [...], "total_count": N, "truncated": false }
        }
      }
    }

Read `data.by_type`, not `data.items`; the `items`, `total_count`, and `truncated` fields are
one level deeper, keyed by record type.

## Workflow

1. Read user message; extract review window if stated (stale threshold in days).
2. Call `get_today_date` if a relative window is stated (e.g., "everything not reviewed this
   month").
3. Call `review` with `user_id`. Pass `stale_for_days` if the user specified a window; omit to
   use the 7-day default. Pass `record_types` if the user scoped to a specific type.
4. On `ok: true`: render per Verbatim Render Rule (Branch A or B).
5. On `ok: false` with `error.code = "storage_unavailable"`: go to Branch C.

## Branches

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. Successful pass | `ok: true`; at least one `total_count > 0` | Name what was stamped by type; concise, no drama |
| B. Empty pass | `ok: true`; all three `total_count = 0` | Acknowledge plainly ("Nothing was stale in the review window") |
| C. Partial failure | `error.code = "storage_unavailable"` | Name the failure as the headline; surface `error.path` verbatim; say what was stamped before the failure; offer to retry; do not say success |

## Composition Guardrails

1. No record-by-record narration; counts and outcomes only.
2. Partial failure is the headline; partial success is secondary.
3. No GTD coaching during or after review.
4. The review is re-runnable safely (atomic per-file); say so if the user asks about retry.

## LLM Responsibilities

- Call `get_today_date` if a relative window is stated.
- Call `review` with `user_id`; pass optional parameters only when the user specified them.
- Read `data.by_type` from the response; render per-type counts.
- On failure: read `error.code` and `error.path`.

## What the LLM Does NOT Do

- Does not narrate individual records.
- Does not interpret stamp count as a performance assessment.
- Does not call `review` multiple times in one turn.
- Does not read from `data.items` (that field does not exist in the actual return).
- Does not confuse `by_type.tasks.total_count` for a total across all types.
