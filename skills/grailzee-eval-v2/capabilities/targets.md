# Target Queries

## Purpose

Return the active hunting list. Strict cycle discipline enforced: no filtered list until a strategy session has set the cycle focus. When cycle focus is current, returns only the focused targets sorted by momentum, enriched with ledger confidence data.

## Trigger

Message asks about targets, priorities, what to buy, what's hot. Examples: "what should I be buying?", "targets", "priorities", "what's hot?", "buy list".

## Workflow

### Step 1: Call the target query

Default invocation (gated by cycle focus):

```
python3 scripts/query_targets.py
```

If the operator requests filters, add flags:

```
python3 scripts/query_targets.py --brand Tudor --signal Strong --budget 3000
```

If the operator explicitly requests override mode (see Override Phrases below), add --ignore-cycle:

```
python3 scripts/query_targets.py --ignore-cycle
```

Override mode also honors additional filter flags.

### Step 2: Format the response based on status

**status: "gate"** — Cycle discipline blocked the query. Post the gate message.

**status: "ok"** — Cycle-filtered list returned. Format using the target list template.

**status: "ok_override"** — Full universe returned with warning. Format with override template.

**status: "error"** — Script failure. Surface the error message.

## Response Format

### Gate (no active cycle focus)

Post verbatim (substituting cycle_id from the response):

```
No active cycle focus for {cycle_id_current}.
Strategy session required before targets are set.

Run grailzee-strategy in Chat to plan this cycle.
```

If the gate state is "stale_focus", adjust:

```
Cycle focus is for {cycle_id_focus}, but current cycle is {cycle_id_current}.
Strategy session required to set targets for this cycle.

Run grailzee-strategy in Chat.
```

If the gate state is "error", surface the parse error:

```
Cannot read cycle focus: {message}
Resolve the issue and retry, or ask for the unfiltered view.
```

### Filtered target list (status: "ok")

```
Cycle {cycle_id} Focus (set {cycle_focus_set_at})
{target_count} active targets

{For each target, sorted by momentum:}
{momentum_emoji} {brand} {model} ({reference}) -- {momentum.label} ({momentum.score:+d})
   MAX BUY: ${max_buy} | Signal: {signal} | {format}
   {confidence line if trades > 0, else "No trade history"}
   Cycle reason: {cycle_reason}
```

Momentum emoji: score >= 2 use a fire indicator, score <= -2 use a down indicator, otherwise a neutral dot.

If `targets_not_in_cache_count` > 0, append:

```
Note: {count} focus target(s) not found in current data ({references}). These references may have faded below the 3-sale threshold.
```

Premium status, if approaching threshold:

```
Premium: {avg_premium}% across {trade_count} trades, {trades_to_threshold} to threshold.
```

### Override mode (status: "ok_override")

```
Operating outside cycle focus. Targets not filtered by strategic intent.
Full market view, sorted by momentum:

{Same target format as filtered list, cycle_reason omitted}
```

### Error

```
Target query failed: {message}
```

## Override Phrases

The LLM passes `--ignore-cycle` ONLY when the operator's message matches one of these phrases (case-insensitive):

- "ignore cycle" / "ignore the cycle"
- "unfiltered"
- "show me everything"
- "full universe" / "full market"
- "off-cycle view"
- "override"

Any other phrasing: default to gated behavior. If uncertain whether the operator wants override, ask: "Do you want me to bypass the cycle focus and show the full market?"

The LLM must NEVER pass --ignore-cycle based on perceived intent or inferred frustration. Only explicit operator language triggers it.

## Available Filters

These flags narrow results in both gated and override modes:

| Flag | Purpose | Example |
|------|---------|---------|
| --brand | Filter by brand | --brand Tudor |
| --signal | Filter by signal strength | --signal Strong |
| --budget | Max buy ceiling | --budget 3000 |
| --format | NR or Reserve | --format NR |
| --sort | Sort field (momentum, volume, signal, max_buy) | --sort volume |

## LLM Responsibilities

- Parse filter intent from natural language and map to CLI flags
- Enforce override phrase allowlist strictly
- Format target list conversationally; highlight top momentum movers
- Surface premium status when approaching threshold
- Post gate messages verbatim when cycle discipline blocks

## What the LLM Does NOT Do

- Pass --ignore-cycle on its own initiative
- Calculate momentum, signal, or any metrics (script returns them)
- Decide which targets belong in the focus list (strategy skill sets focus)
- Restate fee structures or margin targets (MNEMO provides business context)

Voice and tone follow Vardalux conventions per SOUL.md.
