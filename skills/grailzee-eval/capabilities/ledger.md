# Ledger Ingest

## Purpose

Fold a new WatchTrack JSONL extract into the canonical trade ledger. Transform
the records, merge them under the lock, archive the source file, and prune
anything rolled out of the rolling window. Report back done with row counts.
Same shape as the report job: no conversation, no recap, no advisory commentary.
The operator triggers it, Python does it, you confirm.

Row counts go in the confirmation because the operator uses them to sanity-check
that the right batch landed and nothing was silently dropped.

## Trigger

Operator signals a new JSONL extract is ready. Examples: "/ledger", "fold in the
new extract", "run the ledger ingest", "new WatchTrack file is in".

## Tools

- `ingest_sales` — runs the full ingest cycle: scan, transform, merge, archive,
  prune. No input required. Returns a typed envelope with `status`, `rows_added`,
  `rows_updated`, `rows_unchanged`, `rows_unmatched`, `rows_pruned`, `rows_skipped`,
  `files_found`, `files_processed`.
- `message` — sends the completion confirmation to Telegram. One call per run.

## Hard Rules

No conversation. Trigger in, confirmation out. No follow-up questions, no proposed
next steps, no recap of what landed.

Confirmation carries the row counts the envelope returns. Nothing else.

One `message` call per run.

## Response Format

### Clean run

Call `ingest_sales`. On `status: ok`, send one message with the row counts from
the envelope: added, updated, skipped, pruned. Nothing beyond the counts.

### Ingest error

On `status: error`, send one message that names the `error_type` and `message`
from the envelope. No stack trace. Stop.

## What the LLM Does NOT Do

- Narrate process. No "Folding in the extract..." or "Running now..." before
  the result arrives.
- Recap the batch. No listing which sales came in, which references moved,
  which accounts were touched.
- Propose next steps. No "You should review the pruned rows" or "Want me to run
  the report next?"
- Ask follow-up questions. One trigger, one reply, stop.
- Recompute counts. Row totals come from the envelope verbatim.
- Call `ingest_sales` more than once per trigger.
