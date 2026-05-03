# evaluate_deal Gate Failure — Supervisor Capture

**Date:** 2026-05-03
**Session:** Mac Studio runtime gate — 1c+1c.5 post-rebase verification
**Branch:** feature/grailzee-eval-v2 at 254b6e7
**Audit session:** 016b53d5-710d-4052-93fc-b6b4bac64bdc.jsonl
**Model:** qwen3.5:latest via ollama

---

## What the audit showed (counts)

| Metric | Value |
|--------|-------|
| Total tool calls | 2 |
| Registered | 2 |
| Forbidden | 0 |
| Exec/Python bypass | 0 |
| Unknown | 0 |

Plugin loaded from the correct path. Gateway restarted clean. Architecture
layer held: the LLM called the registered tool, not exec. That part worked.

---

## What failed: rendering surface

Both turns hit `match_resolution: ambiguous`. Branch B in deal.md has an
explicit verbatim template. Neither response used it.

---

### Turn 1 — Tudor M7941A1A0RU-0003 @ $3,750

**Tool input:** `{"brand": "Tudor", "reference": "M7941A1A0RU-0003", "listing_price": "3750"}`

**Tool returned:** `decision: no`, `match_resolution: ambiguous`,
`match_resolution_label: "Multiple buckets possible. Clarify dial color, auction type, or numerals."`,
`plan_status_label: "Off cycle plan"`,
candidates: black/No Numerals/res (vol 18) and black/No Numerals/nr (vol 9)

**LLM rendered:**

> The script flagged a "Multiple buckets possible" conflict due to the reference number being ambiguous.
> The watch likely has a blue dial (the "Blue Fifty-Eight"), not a black dial as the system may be assuming.

**Failures:**
1. "The script flagged" — exposes implementation layer. Hard rule violation.
2. Hallucination: tool returned two black dial candidates. LLM invented a
   "blue dial" interpretation not present in any tool output field.
3. Branch B template not used at all.

**Correct Branch B output per deal.md:**

```
Tudor M7941A1A0RU-0003: Multiple buckets possible. Clarify dial color, auction type, or numerals.
- black dial, No Numerals numerals, res
- black dial, No Numerals numerals, nr
```

---

### Turn 2 — Tudor 79830RB Black Dial Pepsi @ $2,450

**Tool input:** `{"brand": "Tudor", "reference": "79830RB", "listing_price": "2450", "dial_color": "black"}`

**Note:** The LLM correctly passed `dial_color: "black"` because the operator
named it. This is the right behavior per deal.md Step 1 parsing rules —
suggests deal.md WAS loaded and the parsing instruction was followed.

**Tool returned:** `decision: no`, `match_resolution: ambiguous`,
`plan_status_label: "On cycle plan"`,
`cycle_reason: "...black dial Strong ($2,760 max-buy, vol 11) and white dial Normal ($3,430 max-buy, vol 9)..."`,
candidates: black/No Numerals/res (vol 25) and black/No Numerals/nr (vol 11)

**LLM rendered:**

> On plan. Two buckets in scope: Black dial (Strong) max buy $2,760; White dial (Normal) max buy $3,430.
> Ledger: 2 prior closes, 50% win rate, 9.2% avg ROI.
> **Why no buy:** the system didn't auto-approve due to ambiguity.
> **Recommendation:** if it's the black dial, $2,450 is below the max-buy of $2,760 — this should be a strong buy signal.

**Failures:**
1. "The script flagged it as ambiguous" — same tech leak.
2. Math synthesis: LLM extracted `$2,760` and `$3,430` from cycle_reason
   prose and applied arithmetic to listing_price $2,450. deal.md §"What
   the LLM Does NOT Do" explicitly prohibits: "Override the tool's yes/no"
   and "Calculate or recalculate any number from math." The LLM did both.
3. White dial max-buy ($3,430) is for a completely different bucket than
   what was submitted. LLM applied it to the black dial submission.
4. Tool returned `decision: no` with `match_resolution: ambiguous`.
   Branch B applies: no math rendering, no plan context, just the
   verbatim template. The LLM ran Branch A logic on an ambiguous result.

**Correct Branch B output:**

```
Tudor 79830RB: Multiple buckets possible. Clarify dial color, auction type, or numerals.
- black dial, No Numerals numerals, res
- black dial, No Numerals numerals, nr
```

---

## Root cause

deal.md is well-written. The verbatim render rule is clear, Branch B
template is explicit, "What the LLM Does NOT Do" directly names the
violation that occurred. The rules were not followed.

Two possible explanations, not mutually exclusive:

**A. deal.md not in context.**
SKILL.md routes to `capabilities/deal.md`. Whether the LLM can actually
read that file depends on whether OpenClaw injects it into the system
prompt or whether the LLM calls a tool to read it. With `tools.allow:
["evaluate_deal", "message"]` there is no file-read tool. If OpenClaw
does not auto-inject capability files, the LLM is working from AGENTS.md
and whatever SKILL.md says at the routing level only — no Branch B
template, no verbatim render rule.

Evidence against A: Turn 2's LLM correctly passed `dial_color: "black"`
from the operator's message — exactly the behavior deal.md Step 1
specifies. If deal.md were absent, this parsing precision would be
surprising. Something from deal.md appears to be reaching the model.

**B. qwen3.5:latest instruction-following fidelity under strict templates.**
The model followed deal.md's parsing instructions (input handling) but
broke from the rendering constraint (output handling). This is a known
failure mode for smaller local models: instruction-following degrades
when the instruction is a hard negative constraint ("do not do X") rather
than a positive instruction ("do Y"). Both "do not say script" and "do
not override the tool's decision" are negative constraints.

Claude's instruction-following on strict template adherence is materially
stronger than qwen3. If the capability files are in context, this is a
model selection problem, not a capability file writing problem. Rewriting
deal.md will improve behavior but may not eliminate it on qwen3.5.

**Most likely: both A and B together.**
Capability file may be partially injected (SKILL.md yes, deal.md maybe),
and qwen3.5 fidelity drops precisely on the negative constraints and
strict branch templates that Branch B depends on.

---

## Additional gap surfaced: AGENTS.md stale tool list

AGENTS.md Tools Available still lists `ledger_manager`. That tool was
de-registered in commit 1b.5. Stale entry in the authoritative hard-rules
file — may contribute to model confusion about what tools actually exist.
This is one of the three fixes scoped to commit 1c.7.

---

## Gate status

NOT CLEARED.

Audit counts are clean. The architecture held at the tool-invocation
layer. The rendering surface failed on both turns. A real Grailzee deal
surfaced to the operator group in this state would:
- Expose implementation language ("the script")
- Potentially override a tool decision with synthesized math
- Surface hallucinated facts (blue dial, wrong-bucket max-buy)

---

## What needs to happen before the gate re-runs

1. **Confirm whether deal.md is actually in LLM context.** Ask OpenClaw
   team or check gateway logs for system prompt assembly. If capability
   files are NOT auto-injected, the routing instruction in SKILL.md is a
   dead letter and deal.md content needs to move into SKILL.md directly
   or into AGENTS.md.

2. **1c.7 commit lands:** AGENTS.md hard rules update (no-process-narration,
   no-tool-announcements, act-silently, stale ledger_manager removed),
   SKILL.md Hard Rules block at top. This closes the identified gaps but
   does not resolve the Branch B template adherence issue.

3. **Re-run this gate after 1c.7.** Check specifically whether:
   - "script" / "system" / tech language appears in any response
   - Branch B renders verbatim template vs LLM synthesis
   - Turn 2 ambiguous+on-plan does not produce override math

4. **Model selection decision.** If Branch B violations persist after
   1c.7, the supervisor needs to decide: accept weaker template fidelity
   on qwen3.5 and write deal.md more coercively, or move grailzee-eval
   to Claude (haiku or sonnet) for this agent. This is a product decision,
   not a capability file writing problem.

---

## What worked (do not lose sight of)

The plugin architecture worked exactly as designed. evaluate_deal was
called via the registered tool. The envelope shape is correct (decision,
match_resolution, candidates, plan_status_label). Forbidden call count:
zero. This is the substantive win from 1c+1c.5. The failure is purely
in the rendering layer, not in the tool invocation or data layer.

---

*Captured by Claude Code post gate run, 2026-05-03. For supervisor review.*
