# Report Processing

## Purpose

Process a new Grailzee Pro biweekly report. Converts the Excel workbook to CSV, runs the full analysis pipeline (scoring, trends, changes, breakouts, watchlist, brand rollups, ledger stats, premium adjustment, cycle rollup, output generation, cache write), resolves unnamed references via web search, and posts the summary to Telegram.

## Trigger

Message mentions a new report, file ready, or time to process. Examples: "new report", "report is in", "process the new file", "new Grailzee Pro".

## Workflow

### Step 1: Acknowledge

Reply: "Running the analyzer now..."

### Step 2: Convert Excel to CSV

Find the newest report in the reports directory:

```
ls -t reports/*.xlsx | head -1
```

If the operator provided a specific file path, use that instead.

Convert to CSV:

```
python3 scripts/ingest_report.py <report.xlsx> --output-dir reports_csv/
```

The script prints JSON on stdout on success: `{"output_csv": "<path>", "rows_written": N, "sheets": {...}, "warnings": [...]}`. On failure it exits non-zero with `{"status": "error", "error": "..."}` on stderr. Capture `output_csv` from the success payload.

### Step 3: Build the trend window

List available CSVs, newest first (up to 6 per Section 6.2):

```
ls -t reports_csv/grailzee_*.csv | head -6
```

The newest CSV (from Step 2) should be first. Pass all CSVs to the orchestrator.

### Step 4: Run the analysis pipeline

```
python3 scripts/run_analysis.py <csv_newest> [<csv_older> ...] --output-dir output/
```

Returns JSON: `{"summary_path": "<path>", "unnamed": ["<ref>", ...], "cycle_id": "<cycle_id>"}`

### Step 5: Read and post the summary

Read the markdown file at `summary_path`. Post to Telegram, chunking at 4000 characters max per message.

### Step 6: Resolve unnamed references

For each reference in the `unnamed` list:
1. Web search: `"{brand} {reference} watch"` (brand from cache entry)
2. Parse results for official model name
3. Append to name_cache.json: `python3 -c "from scripts.grailzee_common import append_name_cache_entry; append_name_cache_entry('<ref>', '<brand>', '<model>')"`

### Step 7: Post the hand-off message

Post verbatim (substituting values):

```
Cycle {cycle_id} analyzed.
{N} references scored, {N} emerged, {N} breakouts, {N} momentum signals.
Premium: {X}% across {N} trades ({threshold status}).
Previous cycle outcome: {N} trades, {X}% avg ROI, {hits}/{total} in focus.

Ready to strategize in Chat.
Open grailzee-strategy to set this cycle's focus. Targets will not filter until strategy runs.
```

## Response Format

### Success

The markdown summary (chunked) followed by the hand-off message above.

### Error

If any script returns an error:

```
Report processing failed: {error message}
Check the report file and try again. If the issue persists, check the logs.
```

## LLM Responsibilities

- Acknowledge the incoming report
- Execute the multi-step pipeline in order
- Web-search unnamed references and resolve to model names
- Present the summary conversationally; highlight notable items (strong emergers, premium threshold reached, high-volume momentum flips)
- Chunk Telegram messages at 4000 characters max
- Route errors cleanly; no raw stack traces

## What the LLM Does NOT Do

- Calculate any metrics (Python does all math)
- Parse Excel files (ingest_report.py handles conversion)
- Write CSV or JSON directly (except name_cache append via helper)
- Decide which references matter (data determines priority)
- Restate fee structures or margin targets (MNEMO provides business context)

Voice and tone follow Vardalux conventions per SOUL.md.
