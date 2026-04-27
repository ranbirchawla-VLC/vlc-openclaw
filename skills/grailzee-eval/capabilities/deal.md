# Deal Evaluation

## Purpose

Answer one question: "I can buy this watch at this price. Should I list
it on Grailzee?" Yes or no, with the math visible. Cycle plan is context
for the LLM, not a gate; math gates the decision.

## Trigger

Message contains a brand + reference + dollar amount. Examples:
"Tudor 79830RB at $2,750"; "Can I buy this Omega 210.30 for 3200?";
"Breitling A17320 $2,400 Black Arabic NR".

## Verbatim Render Rule

Label fields (`match_resolution_label`, `plan_status_label`, `bucket_label`,
`candidate_bucket_labels`) are already human-facing strings computed by the
tool. Render them exactly as returned. Do not paraphrase.

Correct:   `plan_status_label` is "Off cycle plan" → write "Off cycle plan"
Incorrect: "off the active cycle plan" (paraphrase; wrong)

Correct:   `match_resolution_label` is "Reference not in cache" → write "Reference not in cache"
Incorrect: "No match found" or "Unknown reference" (paraphrase; wrong)

Correct:   `candidate_bucket_labels[i]` is "Black dial, No Numerals, nr" → write "Black dial, No Numerals, nr"
Incorrect: "Black No-Reserve" or any reordering (reformatted; wrong)

Em-dashes are banned in all responses without exception. Use a period,
comma, colon, or semicolon instead.

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
  "cycle_context": {on_plan: bool | null, target_match: {...} | null},
  "match_resolution": "single_bucket" | "ambiguous" | "no_match" | "reference_not_found" | "error",
  "candidates": [bucket, ...]   // only on ambiguous
  "match_resolution_label": str,
  "plan_status_label": "On cycle plan" | "Off cycle plan" | "Lookup error" | null,
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
- `adjusted_price` (median x (1 + premium_scalar))
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
and target margin. Never compose math; reuse the verbatim numbers above.
No em-dashes.}
```

### Composition guardrails

Branch A renders math output as one paragraph of operator-facing prose. The paragraph is allowed to surface tradeoffs, characterize cushion or risk, and reference plan context. The paragraph is not allowed to invent facts or make the buy decision.

Three rules govern Branch A composition. All three are hard constraints.

1. **Numbers are verbatim.** Every dollar figure, percentage, count, ratio, and date in Branch A prose must exist in the math output dict or in rendered plan text. The LLM never computes, rounds, restates, or approximates a number. If a number isn't in the input, it doesn't appear in the output.

2. **Framing is decision-helping, not decision-making.** The LLM may surface tradeoffs ("thin cushion vs. clean plan match"), characterize the deal in plan context ("weaker variant on the cycle list"), and suggest sequencing ("take only if the pink is gone"). The LLM may not say "buy this" or "skip this." Yes/no is the math output's decision, never the LLM's. Framing surrounds the decision; framing never overrides it.

3. **Length-bounded.** One paragraph. Three to five sentences. Hard cap. If the framing needs more than five sentences to land, the math output isn't telling the full story. Surface that, don't pad the prose.

Branch C inherits Branch A guardrails. All three rules apply identically to override-match render when that branch ships.

On `decision: "no"` end the response with one line:

    Comp search not yet wired.

No button, no follow-up offer. Step 2 of the implementation sequence
builds comp-search properly.

## Branch B: ambiguous

The reference has multiple buckets and the operator did not name enough
axes to narrow. Use this template exactly:

```
{Brand} {reference}: {match_resolution_label}
- {candidate_bucket_labels[0]}
- {candidate_bucket_labels[1]}
(one item per candidate, each verbatim from candidate_bucket_labels)
```

Do not substitute your own question for `match_resolution_label`. Do not
summarize, reword, or reorder `candidate_bucket_labels` items. Operator
answers and you call `evaluate_deal` again with the named axis.

## Branch C: no_match

Operator named axes that don't match any bucket for this reference. Use
this template exactly:

```
{Brand} {reference}: {match_resolution_label}
Sent: {axes passed to the tool}.
Comp search not yet wired.
```

Do not substitute your own phrasing for `match_resolution_label`. The
cache does not return available-bucket axes on no_match; do not invent them.

## Branch D: reference_not_found

The reference is not in the v3 cache. Use this template exactly:

```
{Brand} {reference}: {match_resolution_label}
Comp search not yet wired.
```

Do not substitute your own phrasing for `match_resolution_label`.

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
  surface verbatim numbers from `math`; deliver framing in operator voice;
  no em-dashes.
- Branch B: use the template exactly; render `match_resolution_label`
  verbatim; render each `candidate_bucket_labels` entry verbatim.
- Branch C / D: use the templates exactly; render `match_resolution_label`
  verbatim; end with "Comp search not yet wired."
- Branch E: surface the error message cleanly.

## What the LLM Does NOT Do

- Calculate or recalculate any number from `math`. Python provides them
  verbatim per AA §2.7.
- Compose or interpret enum codes, booleans, or bucket axes. Render
  `match_resolution_label`, `plan_status_label`, `bucket_label`, and
  `candidate_bucket_labels` verbatim per AA §2.7.1.
- Paraphrase label fields. "Off cycle plan" is not "off the active cycle
  plan". "Reference not in cache" is not "No match found". Render exactly.
- Re-apply the premium scalar; it is already baked into `adjusted_price`
  and `max_buy`.
- Override the tool's yes/no.
- Force a recommendation when match_resolution is anything other than
  single_bucket.
- Invent comp-search results. Comp search is not wired this cycle.
- Use em-dashes anywhere. Period. Use a period, comma, colon, or semicolon
  instead.
