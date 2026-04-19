# llm_review_narrative

**This skill runs on Sonnet. Switch model before proceeding:**
```
/model claude-sonnet-4-6
```

Convert structured review output into a brief conversational summary. Return plain text only.

Write 3–5 sentences. Lead with the most urgent or actionable finding. Be direct and dry — not chatty. Skip sections with count 0.

## Section name mapping

- `active_tasks_missing_metadata` → "tasks missing metadata"
- `stale_active_tasks` → "stale tasks"
- `ideas_overdue_for_review` → "ideas overdue for review"
- `waiting_for_followup` → "waiting follow-ups"
- `parking_lot_unclassified` → "unclassified captures"

## Input

Pass counts only — not the full items arrays.

```json
{
  "total_items_flagged": 7,
  "reviewed_at": "iso8601",
  "sections": [
    { "name": "active_tasks_missing_metadata", "count": 0 },
    { "name": "stale_active_tasks", "count": 3 },
    { "name": "ideas_overdue_for_review", "count": 1 },
    { "name": "waiting_for_followup", "count": 2 },
    { "name": "parking_lot_unclassified", "count": 1 }
  ]
}
```

## Examples

**Input:** total_items_flagged=7, stale_active_tasks=3, waiting_for_followup=2, ideas_overdue_for_review=1, parking_lot_unclassified=1

**Output:**
Three stale tasks haven't moved in over two weeks — worth deciding if they're still real. Two waiting follow-ups are overdue for a nudge. One idea is past its review cadence and one capture is still unclassified. Seven items total need attention.

---

**Input:** total_items_flagged=1, active_tasks_missing_metadata=1, all others=0

**Output:**
One task is missing a context, so it won't show up in next-action queries. Everything else is clean.
