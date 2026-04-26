# Deal Evaluation

## Purpose

Answer one question: "I can buy this watch at this price. Should I list
it on Grailzee?" Yes or no, with the math visible. Cycle plan is context
for the LLM, not a gate; math gates the decision.

## Trigger

Message contains a brand + reference + dollar amount. Examples:
"Tudor 79830RB at $2,750"; "Can I buy this Omega 210.30 for 3200?";
"Breitling A17320 $2,400 Black Arabic NR".

## Workflow

### Step 1: Parse the input

Extract brand, reference, and listing_price (strip `$` and commas).
Optionally extract any of the three keying axes when the operator
names them in the message:
- `dial_numerals`: Arabic, Roman, Stick, etc.
- `auction_type`: NR (No Reserve) or RES (Reserve).
- `dial_color`: Black, Blue, Slate, Green, White, Silver, etc.

Pass an axis only when the operator names it. Do not guess.

### Step 2: Call evaluate_deal

Call the `evaluate_deal` tool with parsed values. The tool returns
this shape:

```
{
  "decision": "yes" | "no",
  "reference": "...",
  "bucket": {dial_numerals, auction_type, dial_color, named_special, signal, volume} | null,
  "math": {listing_price, premium_scalar, adjusted_price, max_buy, margin_pct} | null,
  "cycle_context": {on_plan: bool, target_match: {...} | null},
  "match_resolution": "single_bucket" | "ambiguous" | "no_match" | "reference_not_found" | "error",
  "candidates": [bucket, ...]   // only on ambiguous
  "match_resolution_label": str,
  "plan_status_label": "On cycle plan" | "Off cycle plan" | null,
  "bucket_label": str | null,
  "candidate_bucket_labels": [str, ...]   // only on ambiguous
}
```

### Step 3: Dispatch on `match_resolution`

- `single_bucket` → Branch A.
- `ambiguous` → Branch B.
- `no_match` → Branch C.
- `reference_not_found` → Branch D.
- `error` → Branch E.

## Branch A: single_bucket

Decision is `yes` or `no` from the tool. Surface the verbatim numbers
from `math`:

- `listing_price`
- `adjusted_price` (median × (1 + premium_scalar))
- `max_buy`
- `margin_pct`

And from `bucket`:

- `bucket_label` (verbatim)
- `named_special` (when set)
- `signal`, `volume`

And the cycle context:

- `plan_status_label` (verbatim)
- `cycle_context.target_match.cycle_reason` (when on plan)

Example shape (not a rigid template; voice in operator's authority
register per SOUL.md):

```
{Brand} {reference} ({bucket_label}) @ ${listing_price}

Decision: YES (or NO)
Adjusted median ${adjusted_price} | MAX BUY ${max_buy} | Margin {margin_pct}%
Signal {signal} | {volume} sales

{plan_status_label}{; cycle_reason when on plan.}

{One-paragraph framing in operator voice; grounded in fees, premium scalar,
and target margin. Never compose math; reuse the verbatim numbers above.}
```

On `decision: "no"` end the response with one line:

    Comp search not yet wired.

No button, no follow-up offer. Step 2 of the implementation sequence
builds comp-search properly.

## Branch B: ambiguous

The reference has multiple buckets and the operator did not name
enough axes to narrow. Tool returns `candidates`. Ask one clarifying
question that surfaces the differentiating axis. Do not guess; do not
return a decision.

Example:

```
{Brand} {reference}: which one are you looking at?
- {candidate_bucket_labels[0]}
- {candidate_bucket_labels[1]}
(one entry per candidate)
```

Render each `candidate_bucket_labels` entry verbatim as a list item.
Operator answers and you call `evaluate_deal` again with the named axis.

## Branch C: no_match

Operator named axes that don't match any bucket for this reference.
Surface what's available so they can correct.

```
{Brand} {reference} doesn't have a bucket matching {axes you sent}.
Available: {list bucket axes the reference does have}.
```

End with: `Comp search not yet wired.`

## Branch D: reference_not_found

The reference is not in the v3 cache.

```
No Grailzee data for {brand} {reference}; not in the current cycle's window.
Comp search not yet wired.
```

## Branch E: error

The cache is missing or out-of-date.

```
Deal evaluation failed: {message}
```

No raw stack traces.

## LLM Responsibilities

- Parse brand, reference, listing_price, and optionally
  dial_numerals / auction_type / dial_color from the operator's message.
- Call `evaluate_deal` with parsed values; pass an axis only when named.
- Branch A: render `bucket_label` and `plan_status_label` verbatim;
  surface verbatim numbers from `math`; deliver framing in operator voice.
- Branch B: render each `candidate_bucket_labels` entry verbatim; ask one
  clarifying question grounded in the candidate list.
- Branch C / D / E: surface the resolution cleanly.

## What the LLM Does NOT Do

- Calculate or recalculate any number from `math`. Python provides them
  verbatim per AA §2.7.
- Compose or interpret enum codes, booleans, or bucket axes. Render
  `match_resolution_label`, `plan_status_label`, `bucket_label`, and
  `candidate_bucket_labels` verbatim per AA §2.7.1.
- Re-apply the premium scalar; it is already baked into `adjusted_price`
  and `max_buy`.
- Override the tool's yes/no.
- Force a recommendation when match_resolution is anything other than
  single_bucket.
- Invent comp-search results. Comp search is not wired this cycle.
- Use em-dashes anywhere; semicolons in their place per CLAUDE.md voice
  rules.
