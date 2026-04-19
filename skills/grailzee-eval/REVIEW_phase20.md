# REVIEW_phase20.md — Phase 20: SKILL.md top-level intent dispatcher

**Verdict:** Ships in one commit. New `SKILL.md` at the skill root (93 lines, under 100-line target). Implements name-gate ("Grailzee" word-boundary) and five ordered dispatch paths with an in-line fallback. No code, no tests, no metric changes.

**Commit:**
- `[phase20] SKILL.md — top-level intent dispatcher`

**Tests:** 545 unchanged (no code changes).

---

## What shipped

### Deliverable — `SKILL.md`

Root-level entry point for the Grailzee Eval agent. Structure:

- **Identity** — one paragraph framing (sourcing co-pilot; voice per SOUL.md; business context per MNEMO.md).
- **When to Respond (Name-Gate)** — word-boundary match on "Grailzee", case-insensitive, anywhere in message, punctuation-tolerant. Absent name → silence.
- **Intent Dispatch** — five ordered paths, first match wins.
- **Global Behavior** — Python owns math; LLM owns voice; cycle does not gate deal/targets per D3.
- **Capability Files** — pointer list to the four `capabilities/*.md` files.

Design replaces the Phase 9 implementation-plan @mention gate. Rationale: Wispr Flow dictation drops the `@` glyph in shared-chat contexts, making @mention unreliable as a trigger.

---

## Key decisions

### Path ordering (trade-log before deal)

Path 1 (ledger trade-log) matches on **two or more** dollar amounts plus a trade verb. Path 2 (deal) matches on **one** dollar amount plus brand + reference. Trade-log is the more specific signal, so it must be evaluated first or a message like *"closed Tudor 79830 at $2900, bought at $2750"* would misroute to `deal.md`.

### Sub-path 2a is stateless

A priceless deal query ("Grailzee, what's the move on a Breitling A17320?") does not have enough data to invoke `evaluate_deal.py` (the script requires a purchase price). Two options considered:

1. **SKILL.md replies in-line asking for the price.** Operator re-sends the full deal next turn. Stateless.
2. SKILL.md stores the brand/reference and splices in when the operator replies with a bare dollar amount.

Chose **option 1**. Option 2 introduces conversational state that this skill currently has no infrastructure for. The D2 pattern across ledger-rejection and name-cache resolution is already "abort with clean instruction; operator re-sends" — Path 2a follows the same shape. Documented in SKILL.md body.

### Fallback wording

The fallback reply lists the five capability classes without inline signal hints (no parenthetical `(brand + ref + $)`). Hints in a fallback read as scolding; a plain menu reads as a help message.

### Name-gate word-boundary rule

Gate matches `\bgrailzee\b` in effect — case-insensitive. Substring matches inside other words (e.g. `grailzeebot`) do not fire. Trailing punctuation (`,`, `.`, `!`, `?`, `:`) is permitted because it follows the word boundary.

---

## Contract table — Phase 20 vs. D1–D5

| Contract | Source | Honored by SKILL.md |
|---|---|---|
| Report via `report_pipeline.py` wrapper | D1 | ✓ Path 3 routes to `capabilities/report.md` only |
| Ledger rejection is abort + re-send | D2 | ✓ Path 1 routes to `capabilities/ledger.md` (which implements D2) |
| No cycle gate on deal or targets | D3 | ✓ Global Behavior states this explicitly |
| Targets = Strong/Normal, MAX BUY DESC | D4 | ✓ Path 5 routes to `capabilities/targets.md` (which implements D4) |
| Config-driven thresholds deferred | D5 | ✓ No thresholds introduced |

---

## Dry-run routing table

Twelve sample messages. For each: expected path, rationale.

| # | Message | Expected path | Notes |
|---|---|---|---|
| 1 | `Grailzee, closed Tudor at $2900, bought at $2750` | Path 1 | 2 $ amounts + "closed/bought" verbs |
| 2 | `Grailzee sold Omega 210.30 for $3800, booked $3200` | Path 1 | 2 $ amounts + "sold/booked" verbs |
| 3 | `Tudor 79830RB at $2,750 Grailzee` | Path 2 | brand + ref + single $ |
| 4 | `Grailzee, can I buy this Omega 210.30 for 3200?` | Path 2 | brand + ref + single $ (bare number is price) |
| 5 | `Grailzee what's the move on a Breitling A17320?` | Path 2a | brand + ref, no $ |
| 6 | `Grailzee, just picked up a Breitling A17320 — what can I sell it for?` | Path 2a | brand + ref, no $; **see scope-creep flag below** |
| 7 | `Grailzee new report is in` | Path 3 | "new report" signal |
| 8 | `Grailzee how are we doing this cycle?` | Path 4 | "how are we doing" + "cycle" performance signal |
| 9 | `Grailzee what should I be buying?` | Path 5 | "what should I buy" signal |
| 10 | `Grailzee targets` | Path 5 | "targets" keyword |
| 11 | `Grailzee, hi` | Fallback | name present, no dispatch signals |
| 12 | `what should I be buying?` | **silence** | no name-gate match |

All twelve route to their intended handlers. No ambiguous cases under the first-match-wins rule.

---

## Scope-creep flags for future phases

### Flag A — Path 2a state-carrying

Path 2a is stateless by design. If operator friction accumulates ("I send ref then price repeatedly; it's annoying"), a future phase could teach SKILL.md to hold the brand/reference until a bare price arrives in the next turn. Not scoped here. Documented in SKILL.md under Path 2a.

### Flag B — Sell-side "what can I sell it for?" queries

Sample 6 in the dry-run table is a sell-side question, not a purchase-decision question. Path 2a's priceless-reply handles it by asking for the ask price, which is acceptable but partial — a genuine sell-side capability would invoke comp research without asking for a purchase price. Future capability candidate. Not scoped here.

---

## Code review notes

Staff-engineer review pass surfaced five findings; four applied.

| # | Finding | Status |
|---|---|---|
| 1 | Path 4 performance-query signals can collide with Path 2 deal-eval signals when brand + ref + $ is present in a performance-phrased message. First-match-wins saves it, but the interaction is fragile. | **Applied** — Path 4 section ends with an explicit tie-break note: deal-eval wins on conflict. |
| 2 | Path 2a location — keep the in-line reply in SKILL.md rather than routing to `deal.md` just to bounce back out. | **No change** — reviewer confirmed in-line handling is correct. |
| 3 | Name-gate wording was abstract; an LLM could mis-classify edges like `Grailzee's`, `"Grailzee"`, `(Grailzee)`. | **Applied** — added explicit regex-intent line (`\bGrailzee\b` with `re.IGNORECASE`) and the trailing-punctuation set `,.!?:'")]`. |
| 4 | Fallback was too terse — five nouns with no shape for the operator to re-phrase. | **Applied** — appended one concrete example: `Try: "Grailzee, Tudor 79830RB $8900"`. |
| 5 | No statement about whether targets are mutable from this surface. | **Applied** — Capability Files section now states targets are read-only; trade logging records the purchase but does not mutate the target list. |

Final line count: 104 (vs. 100-line target). The four reviewer-driven additions address substantive routing and gate clarity; the 4-line overrun is deliberate.

Other self-review checks (all clean):

- **Template shape:** matches §9.2 of the implementation plan modulo the name-gate substitution (intended per prompt).
- **Voice check:** `capabilities/*.md` defer voice to SOUL.md; SKILL.md does the same via Identity and Global Behavior. No voice drift.
- **Cross-references:** four capability files listed; all four files exist in `capabilities/` (confirmed in Phase 19 shipping).
- **D3 gate statement:** present in Global Behavior; matches deal.md and targets.md language.
- **Path 2a reply wording:** verbatim match with the wording approved in session dialogue.

---

## What did NOT ship (deferred, out of scope)

- Conversational state for Path 2a.
- Dedicated sell-side capability for "what can I sell X for" queries.
- Telemetry for dispatch decisions (SKILL.md is LLM-interpreted; OTel is on the Python side only).
- Any capability-file edits (deal/report/targets/ledger are unchanged from Phase 19).
- Any script edits.

---

## End-state

- Branch: `feature/grailzee-eval-v2`
- Tests: 545 passing, unchanged.
- New files: `SKILL.md`, `REVIEW_phase20.md`.
- Ready to merge after the final phase(s) land on this branch.
