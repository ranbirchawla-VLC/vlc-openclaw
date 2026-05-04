# Buying List

## Purpose

Show the operator which references to source this cycle, with the
reasoning and capital context. Read-only; no math, no decisions.

## Trigger

Operator sends `/buying` or a natural-language equivalent ("what should
I be buying this week", "show me the targets", "buying list").

## Verbatim Render Rule

`cycle_reason` is an operator-authored string. Render it exactly as
returned. Do not summarize, shorten, or paraphrase it.

Em-dashes are banned in all responses without exception. Use a period,
comma, colon, or semicolon instead.

## Workflow

### Step 1: Call get_cycle_targets

Call `get_cycle_targets` with no arguments. It returns one of:

```
{"ok": true,  "data": {"targets": [...], "capital_target": N,
                        "volume_target": N, "brand_emphasis": [...],
                        "brand_pullback": [...], "notes": "..."}}
{"ok": false, "error": "..."}
```

### Step 2: Dispatch on result

- `ok: true`, targets non-empty  → Branch A.
- `ok: true`, targets empty      → Branch B.
- `ok: false`                    → Branch C.

## Branch A: targets present

Open with one line drawn from `capital_target`, `volume_target`, and
`brand_emphasis`:

```
Here's the current cycle plan:
```

Per-target format — one block per item in `targets`, blank line between
each:

```
**{brand} {reference} ({model}) — {one-phrase role drawn from cycle_reason}**
{cycle_reason synthesized as 2-4 sentences of prose. Preserve every number,
reference code, signal name, and max-buy figure exactly. Do not add or invent
facts. Render as flowing prose, not bullet points or pipe-separated fields.}
{If max_buy_override is not null, append on its own line:
Max-buy override: ${max_buy_override:,} — {one phrase explaining the override
drawn from cycle_reason}.}
```

After the target list, if `notes` contains skip or pullback references,
add:

```
Hard passes this cycle: {extract the specific references and one-line
reasons from notes where the operator says to skip or avoid; render as
a single prose sentence, not a list. Preserve reference codes exactly.}
```

Close with a capital summary paragraph drawn from `notes`:

```
{1-2 sentences on capital target, unit target, NR discipline, and any
margin guidance from notes. Preserve all numbers exactly.}
```

Omit the hard passes line if no skip references appear in notes.
Omit the capital summary if notes is empty.

## Branch B: targets empty

```
No targets set for this cycle. Run /report to generate the shortlist,
then run a strategy session to populate the buying list.
```

## Branch C: error

```
Could not load buying list: {error}
```

No stack traces.

## LLM Responsibilities

- Call `get_cycle_targets` with no arguments.
- Synthesize `cycle_reason` into prose; preserve every number, signal
  name, and reference code exactly; do not add facts not present in the data.
- Use the bold `**Brand Reference (Model) — descriptor**` header per target.
- Render `max_buy_override` only when not null, with a one-phrase explanation
  drawn from cycle_reason.
- Extract hard-pass references from notes and render as a single prose sentence.
- Close with a capital/margin summary from notes.
- No em-dashes anywhere. No emoji. No bullet points. No pipe-separated fields.

## What the LLM Does NOT Do

- Invent or infer max_buy values not present in the data.
- Add commentary, ranking, or opinions beyond what is in cycle_reason or notes.
- Reorder or filter targets.
- Use emoji section headers or structural chrome (arrows, pipes, →).
