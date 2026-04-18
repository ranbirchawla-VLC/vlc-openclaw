# Deal Evaluation

## Purpose

Answer one question: "I can buy this watch at this price. Should I list it on Grailzee?" Returns a structured YES/NO/MAYBE recommendation with margin analysis, confidence data from the trade ledger, and cycle alignment annotation.

Always available. Cycle discipline does not block deal evaluation.

## Trigger

Message contains a brand + reference + dollar amount. Examples: "Tudor 79830RB at $2,750", "Can I buy this Omega 210.30 for 3200?", "Breitling A17320 $2,400".

## Workflow

### Step 1: Parse the input

Extract brand, reference, and purchase price from the message. Strip dollar signs and commas from the price.

### Step 2: Call the evaluator

```
python3 scripts/evaluate_deal.py <brand> <reference> <purchase_price>
```

### Step 3: Format the response based on status

The script returns JSON with one of four statuses. Handle each:

**status: "ok"** — Reference found. Format using the response template below.

**status: "not_found"** — Not in cache or raw report. The response includes a `comp_search_hint` payload. Proceed to Step 4 (web research).

**status: "error"** — Script-level failure (no cache, stale schema, bad price). Surface the error message to Telegram cleanly.

### Step 4: Web research (not_found only)

When status is "not_found", the response includes:

```json
"comp_search_hint": {
  "search_queries": ["<brand> <ref> site:chrono24.com", ...],
  "instructions": "Find 5+ recent sold prices...",
  "formula_reminder": "MAX BUY NR = (Median - $149) / 1.05"
}
```

Execute the search queries. Find 5+ recent sold prices in VG+ condition with papers. Take the median. Apply the formula from `formula_reminder`. Deliver the recommendation with the caveat:

```
No Grailzee data. Based on {N} Chrono24/eBay comps.
```

Always deliver a recommendation. Never punt to the user.

## Response Format

### Reference found, in-cycle

```
{brand} {model} ({reference}) @ ${purchase_price}

Grailzee: {YES/NO/MAYBE}
Format: {NR/Reserve}
Margin: {margin_pct}% (${margin_dollars} at median)
Ad Budget: {ad_budget}
Momentum: {momentum.label} ({momentum.score:+d})

{rationale}

Trade History: {confidence.trades} trades, {confidence.win_rate}% profitable, avg ROI {confidence.avg_roi}%, avg premium {confidence.avg_premium:+}%
Cycle Focus: In current hunting list ({cycle_focus.cycle_id_current})
```

If `confidence` is null, omit the Trade History line.
If `reserve_price` is not null, add: `Reserve Price: ${reserve_price}`

### Reference found, off-cycle

Same structure as in-cycle, but replace the Cycle Focus line:

```
Cycle Focus: Not in current hunting list ({cycle_focus.cycle_id_current})
Off-cycle buy; proceed on your judgment.
```

If cycle_focus.state is "no_focus" or "stale_focus":

```
Cycle Focus: No active cycle focus. Strategy session pending.
```

If cycle_focus.state is "error":

```
Cycle Focus: cycle_focus.json error ({note}). Strategy state unknown.
```

### Not found (after web research)

```
{brand} {reference} @ ${purchase_price}

No Grailzee data. Based on {N} Chrono24/eBay comps.

Grailzee: {YES/NO/MAYBE}
Format: NR (assumed)
Estimated Median: ${median}
MAX BUY: ${max_buy}
Margin: {margin_pct}% (${margin_dollars} at median)

{rationale with comp source notes}
```

### Error

```
Deal evaluation failed: {message}
```

No raw stack traces. Surface the error message and suggest corrective action (re-run analyzer, check cache, verify input format).

## LLM Responsibilities

- Parse brand, reference, price from natural language messages
- Call evaluate_deal.py with parsed arguments
- Format response per templates above (verbatim data lines, composed framing)
- Execute web research for not_found references using comp_search_hint
- Apply the MAX BUY formula to web research results (formula provided in hint)
- Surface premium_status from the response when relevant (threshold approaching, or met)

## What the LLM Does NOT Do

- Calculate margin, risk, or any metrics (the script returns them)
- Re-apply or recompute the presentation premium adjustment (already baked into cache)
- Override the script's YES/NO/MAYBE decision
- Block evaluation based on cycle focus state (always available)
- Restate fee structures or account rules (MNEMO provides business context)

Voice and tone follow Vardalux conventions per SOUL.md.
