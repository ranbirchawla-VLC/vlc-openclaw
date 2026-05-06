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

Open with one line:

```
Cycle {cycle_id} buying list — ${capital_target:,} capital, {volume_target} pieces, {brand_emphasis joined with " + "}.
```

Render each target as a compact two-line block, blank line between each.
Do NOT use tables, pipes, dashes-as-separators, or code blocks:

```
*{reference}* — {model} — max ${max_buy:,}
{One sentence from cycle_reason. Preserve every number and signal name exactly.}
```

If `max_buy_override` is not null, replace the max buy figure:

```
*{reference}* — {model} — max ${max_buy_override:,} (operator override)
{One sentence from cycle_reason.}
```

Example of correct rendering (use actual data, not these values):

```
*79830RB* — BB GMT Pepsi — max $2,850
NR-Strong signal; wide sell-through; buy under $2,850 NR only.

*25600TB* — Pelagos FXD — max $3,090
Normal signal; strong Tudor dive volume; no Reserve stretch.
```

After all targets, if `notes` contains skip or pullback references:

```
Hard passes: {references and one-line reasons as a single prose sentence.}
```

Close with one line from `notes`:

```
{Capital target, unit count, and any NR discipline or margin guidance. Numbers verbatim.}
```

Omit hard passes if no skips in notes.
Omit closing line if notes is empty.

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
- No em-dashes anywhere. No emoji. No bullet points. No pipe-separated fields. No markdown tables. No code blocks in the response body.

## What the LLM Does NOT Do

- Invent or infer max_buy values not present in the data.
- Add commentary, ranking, or opinions beyond what is in cycle_reason or notes.
- Reorder or filter targets.
- Use emoji section headers or structural chrome (arrows, pipes, →).
- Group targets into sections or categories not present in the data.
- Use markdown tables or pipe characters to align columns.
