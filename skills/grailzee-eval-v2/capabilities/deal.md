# Deal Evaluation

## Purpose

Answer one question: "I can buy this watch at this price. Should I list
it on Grailzee?"

Always available — cycle discipline does not gate deal evaluation.
Two branches on script response:

- **Grailzee data exists** — LLM reads the data and delivers a voice-grounded
  recommendation using business context (fees, margin target, Profit for
  Acquisition model, operator goals).
- **No Grailzee data** — LLM delivers market context only from web research.
  No forced recommendation. The absence of Grailzee data is itself the
  answer.

## Trigger

Message contains a brand + reference + dollar amount. Examples:
"Tudor 79830RB at $2,750", "Can I buy this Omega 210.30 for 3200?",
"Breitling A17320 $2,400".

## Workflow

### Step 1: Parse the input

Extract brand, reference, and purchase price. Strip dollar signs and commas.

### Step 2: Call the evaluator

```
python3 scripts/evaluate_deal.py <brand> <reference> <purchase_price>
```

### Step 3: Dispatch on status

The script returns JSON with one of three statuses:

- **`status: "ok"`** — Grailzee data present. Go to Branch A.
- **`status: "not_found"`** — No Grailzee data. Go to Branch B.
- **`status: "error"`** — Script-level failure. Surface the error message cleanly.

Ignore `cycle_focus` fields in either branch. Cycle annotation is not
part of the deal-evaluation output.

## Branch A — Grailzee data exists (`status: "ok"`)

Surface the following data points from the response:

- `metrics.median`
- `metrics.max_buy` (MAX BUY — NR by default; Reserve when `format == "Reserve"`)
- `reserve_price` (when present)
- `metrics.signal`
- `metrics.volume`
- `metrics.sell_through`
- `metrics.momentum.label` + `metrics.momentum.score`
- `metrics.margin_pct` + `metrics.margin_dollars`
- `ad_budget`
- `confidence` (trades, win rate, avg ROI, avg premium — when non-null)
- `premium_status` (when approaching or past threshold)

Deliver a recommendation grounded in business context — fees, margin
target, Profit for Acquisition model, operator goals. Use the operator's
voice per SOUL.md. Do not reduce the response to a template. The Python
`rationale` field is a reasonable starting point but not a script for
the LLM to recite verbatim.

Example shape (not a rigid template):

```
{Brand Model} ({reference}) @ ${purchase_price}

Grailzee: {YES/NO/MAYBE}
Format: {NR/Reserve}
Median ${median} | MAX BUY ${max_buy} | Margin {margin_pct}% (${margin_dollars})
Signal {signal} | {volume} sales | {sell_through} sell-through | {momentum.label} ({momentum.score:+d})
{Reserve Price line when reserve_price present}
Ad Budget: {ad_budget}

{LLM rationale paragraph — operator voice, grounded in business context}

{Trade History line from confidence when non-null}
{Premium status line when at or approaching threshold}
```

## Branch B — No Grailzee data (`status: "not_found"`)

**Market context only.** No forced recommendation. No margin math. No
ad budget. No MAX BUY calculation.

### Step B1: Web research

Run web searches from `comp_search_hint.search_queries` (Chrono24, eBay,
WatchRecon). Gather:

- Chrono24 asking-price range and listing count.
- eBay 30-day sold comps (prices + count).

Ignore `comp_search_hint.formula_reminder` and `comp_search_hint.instructions`
— they predate D3 and apply the margin formula, which is out of scope
for this branch.

### Step B2: Deliver market context

Format:

```
{Brand Model} ({reference}) @ ${asking}

No Grailzee data. This reference hasn't been in our window.

Chrono24 asks: ${range} across {N} listings
eBay sold (30 days): ${comps}, {N} comps

Observed spread: ${range}.
Your call on whether Grailzee traffic warrants the try.
```

If comps are thin (< 3 sold), note that explicitly — do not fabricate
a range.

## Response Format

### Branch A (ok)

Composed per template above. Verbatim data lines; LLM voice on framing
and rationale.

### Branch B (not_found)

Market-context block per Step B2.

### Error

```
Deal evaluation failed: {message}
```

No raw stack traces.

## LLM Responsibilities

- Parse brand, reference, price from natural language.
- Call `evaluate_deal.py` with parsed arguments.
- Branch A: surface the data per template, deliver voice-grounded
  recommendation using business context from MNEMO.
- Branch B: run web research, deliver market context only.
- Surface `premium_status` when at or approaching threshold.

## What the LLM Does NOT Do

- Calculate median, margin, risk, MAX BUY, or any metrics (Python
  provides them in Branch A; explicitly not computed in Branch B).
- Re-apply the presentation premium adjustment (baked into cache).
- Override the script's YES/NO/MAYBE in Branch A.
- Force a recommendation in Branch B — the absence of Grailzee data is
  the answer.
- Apply the margin formula to web comps (Branch B is market context only).
- Annotate cycle alignment (cycle state is not part of deal output).
- Restate fee structures or account rules (MNEMO provides business context).

Voice and tone follow Vardalux conventions per SOUL.md.
