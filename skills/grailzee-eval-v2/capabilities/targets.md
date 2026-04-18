# Target Queries

## Purpose

Return the active hunting list: references at Strong or Normal signal,
sorted by MAX BUY (NR) descending, in two sections. Always available.
No cycle gate. No filters. No override flags.

Reserve, Careful, and Pass tiers are deliberately excluded from this
output — tactical sourcing uses NR pricing and the top two signal tiers.
Full detail for all tiers lives in the Excel output on disk.

## Trigger

Message asks about targets, priorities, what to buy, what's hot. Examples:
"what should I be buying?", "targets", "priorities", "what's hot?", "buy list".

## Workflow

### Step 1: Run the query

```
python3 scripts/query_targets.py
```

Defaults to `analysis_cache.json` at the state path. No flags.

### Step 2: Post the output verbatim

The script prints the formatted two-section block directly. Pass it to
Telegram as-is. No prose framing, no momentum emoji, no brand highlights,
no commentary.

## Response Format

### Two-section block (normal case)

```
STRONG
{brand} {model} — {reference} — ${max_buy_nr}
...sorted by max_buy_nr DESC

NORMAL
{brand} {model} — {reference} — ${max_buy_nr}
...sorted by max_buy_nr DESC
```

One-tier-empty preserves the header with no entries — that absence is
itself information.

### Both tiers empty (fallback)

When no references are at Strong or Normal signal:

```
No references at Strong or Normal signal.
```

### Error

If the script exits non-zero, surface the stderr message cleanly:

```
Target query failed: {message}
```

## LLM Responsibilities

- Invoke `query_targets.py`.
- Post the stdout output verbatim to Telegram.
- Surface errors cleanly; no raw stack traces.

## What the LLM Does NOT Do

- Pass flags, filters, or sort overrides to the script.
- Add prose framing, commentary, or operator-facing narration around
  the script output.
- Annotate momentum labels, signal text, or cycle state.
- Block or gate the query on cycle focus (no cycle gate per D3).
- Calculate or re-derive any metric (the script is the authority).
- Restate fee structures or margin targets (MNEMO provides business context).

Voice and tone follow Vardalux conventions per SOUL.md.
