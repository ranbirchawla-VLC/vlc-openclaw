# Report Processing

## Purpose

Process a new Grailzee Pro biweekly report. Invokes the single-command
pipeline wrapper (ingest + CSV glob + full analysis), resolves unnamed
references via web search, posts the summary to Telegram, and hands off
to the strategy skill in Chat.

## Trigger

Message mentions a new report, file ready, or time to process. Examples:
"new report", "report is in", "process the new file", "new Grailzee Pro".

## Workflow

### Step 1: Acknowledge

Reply: "Running the analyzer now..."

### Step 2: Locate the input workbook

If the operator provided a specific file path, use that. Otherwise find
the newest workbook in the reports directory:

```
ls -t reports/*.xlsx | head -1
```

This is input-acquisition — selecting which workbook the operator just
dropped. It is not state-threading (the pipeline's CSV trend window, ledger,
cache, and output paths all resolve inside the wrapper from defaults).

### Step 3: Run the pipeline

```
python3 scripts/report_pipeline.py <input.xlsx>
```

The wrapper handles ingest, CSV glob, and full analysis in one call. It
reads all state paths (CSV dir, ledger, cache, backup, name cache, output
folder) from grailzee_common constants — no flags needed.

On success, stdout is JSON:

```json
{"summary_path": "<path>", "unnamed": ["<ref>", ...], "cycle_id": "<cycle_id>"}
```

On failure, non-zero exit; stderr carries `{"status": "error", "error": "..."}`.

### Step 4: Post the summary

Read the markdown at `summary_path`. Post to Telegram, chunking at 4000
characters max per message.

### Step 5: Resolve unnamed references

For each reference in `unnamed`:

1. Web search: `"{brand} {reference} watch"` (brand from cache entry).
2. Parse results for the official model name.
3. Append to name_cache:

```
python3 -c "from scripts.grailzee_common import append_name_cache_entry; append_name_cache_entry('<ref>', '<brand>', '<model>')"
```

If a search fails or yields no confident match, skip the reference and
continue. Do not stall the hand-off. At the end of the loop, include a
one-line note listing any references that could not be resolved.

### Step 6: Post the hand-off message

Post verbatim (substituting `cycle_id`):

```
Cycle {cycle_id} analyzed. Ready to strategize in Chat.
```

## Response Format

### Success

The markdown summary (chunked at 4000 chars) followed by the hand-off
message above.

### Error

```
Report processing failed: {error message}
Check the report file and try again. If the issue persists, check the logs.
```

## LLM Responsibilities

- Acknowledge the incoming report.
- Invoke the wrapper; capture the returned dict.
- Web-search unnamed references and resolve to model names.
- Present the summary conversationally; highlight notable items (strong
  emergers, premium threshold reached, high-volume momentum flips).
- Chunk Telegram messages at 4000 characters max.
- Route errors cleanly; no raw stack traces.

## What the LLM Does NOT Do

- Invoke `ingest_report.py`, `run_analysis.py`, or any other raw script
  directly — the pipeline wrapper is the single entry point.
- Thread state file paths through the pipeline — defaults in the wrapper
  cover all state locations (CSV trend window, ledger, cache, backup, name
  cache, output folder).
- Inline glob logic for pipeline state (e.g. constructing the CSV trend
  window from `reports_csv/`). Newest-workbook selection in Step 2 is
  operator input-acquisition, not state-threading.
- Calculate any metrics (Python does all math).
- Parse Excel files.
- Write CSV or JSON directly (except `name_cache` append via helper).
- Restate fee structures or margin targets (MNEMO provides business context).

Voice and tone follow Vardalux conventions per SOUL.md.
