---
name: step3a-canonical
description: >
  Write canonical descriptions for a Vardalux watch listing. Called by the
  listing pipeline when _draft.json is at step 2 (pricing approved, descriptions
  not yet written). Writes canonical.description, canonical.condition_line, and
  canonical.grailzee_desc to _draft.json. Triggered by pipeline.py — do not
  invoke directly.
---

# Step 3a: Canonical Descriptions

## Purpose

Read the approved watch data from `_draft.json`, write three canonical text
fields, get Telegram approval, and save the result. Advances pipeline to step 3.

**This is the only step that writes listing copy.** All platform formatting,
character substitution, and template insertion is handled downstream by
`run_phase_b.py`. Do not write platform-specific text here.

---

## Setup

Load at the start of this skill:

```
references/voice-tone.md
```

Read every rule in that file before writing a single word.

---

## Step Gate

Read `_draft.json` from the listing folder. Verify `step == 2`.

If `step != 2`, send to Telegram:
> "Cannot write descriptions: pipeline is at step [N], not step 2. Check the
> current state and retry."

Do not proceed.

---

## Inputs

Read from `_draft.json`:

| Field | Required | Notes |
|-------|----------|-------|
| `inputs.brand` | Yes | |
| `inputs.model` | Yes | |
| `inputs.reference` | Yes | |
| `inputs.tier` | Yes | 1, 2, or 3 — governs length and tone |
| `inputs.condition` | Yes | BNIB, Excellent, Very Good, Good, Other |
| `inputs.condition_detail` | If present | Component-level notes |
| `inputs.included` | Yes | What ships with the watch |
| `inputs.year` | If present | |
| `inputs.case_size` | If present | |
| `inputs.case_material` | If present | |
| `inputs.movement` | If present | |
| `inputs.grailzee_format` | If present | If "skip" or absent: grailzee_desc = null |
| `watchtrack.notes` | If present | See Source Priority below for filtering rules |

**Do not read:** `inputs.retail_net`, `pricing.*`, `approved.grailzee_gate`, or
any pricing data. This skill has no knowledge of what the watch costs.

---

## Source Priority

1. **`watchtrack.notes` (filtered):** This field may contain provenance, service
   history, purchase source, and ownership details alongside useful information
   about the watch's behavior and characteristics.

   **Use:** Any information about how the watch runs, wears, or behaves. Movement
   accuracy observations, winding feel, bracelet comfort, lume performance, bezel
   action, anything that supports confidence-tier language about the physical
   experience of the watch.

   **Filter out completely:** Where, when, or from whom the watch was purchased.
   Any service events, service dates, or service providers. Any phrase that
   functions as a sales pitch for the paper trail rather than the watch itself.
   These details belong in internal records only. Do not reference them, allude
   to them, or rephrase them in any buyer-facing field.

   If `watchtrack.notes` contains only provenance and service data with no
   behavioral observations, treat it as empty for writing purposes. Do not
   invent behavioral details to compensate.

2. **Standard knowledge** about the brand, model, caliber, complications, and
   finishing tradition. Apply confidence-tier language throughout (see Writing
   Rules below).

---

## Writing Rules — The Advisor Standard

These rules govern every word this skill writes. They exist because the
listing copy is doing qualifying work at scale. It reads like one knowledgeable
person talking to another. The buyer who belongs in this conversation already
understands the significance of what is being named.

### Name complications. Never explain them.

Do not describe what a complication does or how its mechanism works. A perpetual
calendar, annual calendar, tourbillon, minute repeater, split-seconds
chronograph, GMT function: name it with authority and move on. The buyer who
needs the explanation is not the buyer for this piece. The one who does not
need the explanation already knows why the complication matters at this price
point versus the alternatives.

Explaining complications is knowledge-tier writing by definition. It treats
the reader as someone who needs to be taught. That is servant behavior, not
advisor behavior. An advisor assumes competence.

This applies to movements, finishing techniques, and materials with equal force.
"Three-quarter plate in German silver, hand-engraved balance cock, blued screws"
lands with the right reader. Do not follow it with a sentence explaining what
three-quarter plate construction is or why German silver matters.

### Confidence tier, not knowledge tier

Knowledge tier: reciting what anyone can find on a spec sheet or brand website.
Confidence tier: speaking from the experience of handling, wearing, and
transacting the piece.

Knowledge: "This has a column-wheel chronograph."
Confidence: "The column-wheel gives the pushers a tactile click you feel every
single time."

If Ranbir's direct experience is available in `watchtrack.notes`, use it. If
not, write with the authority of a dealer who handles these regularly, not a
researcher summarizing specifications.

### Every sentence does specific work

If a sentence can be deleted without losing anything concrete, delete it. No
warm-up sentences, no throat-clearing, no transitional filler. Strong lines
open the paragraph.

### No provenance in buyer-facing copy

No purchase source. No service history. No service dates. No "documented
provenance." No "fresh service life ahead." No "purchased from [dealer]." The
buyer is interested in the watch. If they want the paper trail, they will ask.
The condition sentence covers completeness. That is sufficient.

If service history is unknown: include "service history unknown but running
accurately" in the descriptive paragraph. Use `watchtrack.notes` to confirm
the watch is running accurately before including this line.

### Specificity is the proof

Name the caliber. Name the finishing. Name the complication. Name the material.
Vague superlatives ("stunning," "incredible," "amazing") are banned. "40mm
steel case" is a fact. "Beautiful timepiece" is filler.

---

## Writing Instructions

### Descriptive paragraph

Apply the tier rules from `voice-tone.md`:

- **Tier 1:** 3–4 sentences. What this reference is, why it is respected, what
  the buyer is getting. Name the key technical features. Educational,
  trust-building tone.
- **Tier 2/3:** 4–5 sentences. Name the horological significance, the movement,
  the finishing tradition, the complications. What makes this reference worth
  owning and why this specific example. Competence-focused tone. Tier 3: a note
  of honest scarcity if applicable, never hype.

**Hard rules for the paragraph:**
- One paragraph, full stop
- No em-dashes
- No condition language — condition lives in the condition sentence
- No pricing, value, or cost-of-ownership language
- No provenance, service history, or purchase source (see Writing Rules above)
- No explaining what complications do or how mechanisms work (see Writing Rules above)
- If service history is unknown: include "service history unknown but running
  accurately" — use `watchtrack.notes` to confirm this before including it

### Condition sentence

One sentence. State: condition rating + completeness.

Format: `[Condition], [completeness].`

Examples:
- "Excellent condition, full set with original box and papers dated June 2023."
- "Very good condition, watch only, no box or papers."
- "Excellent condition, full set, extra links and hang tags in sealed bag."
- BNIB: "Brand new in box, never worn, full set with factory stickers."

Use `inputs.condition` for the rating. Use `inputs.included` for completeness.
Use `inputs.condition_detail` if component notes merit mention (e.g., "Light
surface marks on case flanks" when condition is Very Good).

One sentence only. Do not turn this into a paragraph. No provenance. No service
history. No purchase source. Completeness and condition only.

### Grailzee description

**If `inputs.grailzee_format` is `"skip"` or absent:** set `grailzee_desc` to
`null`. Do not write a paragraph. Done.

**Otherwise:** One paragraph. Rules from `voice-tone.md` apply strictly:
- No specs
- No condition language
- No reference number
- No em-dashes
- Pure story and pull — why this piece matters, what it means to own it
- Write like telling a friend, not closing a sale
- Same advisor standard: name what matters, do not explain it

---

## Self-Check Before Sending to Telegram

Run this checklist against every field before posting for approval. If any
check fails, rewrite the affected field before sending.

**Descriptive paragraph:**
- [ ] Does any sentence explain what a complication does or how a mechanism works?
      → Rewrite: name it, delete the explanation.
- [ ] Does any sentence reference purchase source, service history, service
      dates, or provenance? → Delete the sentence.
- [ ] Does any sentence use a vague superlative (stunning, incredible, amazing,
      beautiful, exquisite)? → Replace with a specific fact.
- [ ] Is any sentence knowledge-tier (spec sheet recitation) when confidence-tier
      language is possible? → Rewrite from wearing experience.
- [ ] Can any sentence be deleted without losing concrete information?
      → Delete it.
- [ ] Does the strongest line open the paragraph? → Reorder if not.

**Condition sentence:**
- [ ] Is it exactly one sentence? → Trim if not.
- [ ] Does it contain provenance, service history, or purchase source?
      → Remove. Condition and completeness only.

**Grailzee paragraph (when applicable):**
- [ ] Does it contain specs, condition language, or reference numbers?
      → Rewrite.
- [ ] Does it explain what a complication does? → Rewrite: name it, move on.

---

## Telegram Approval Flow

Post all three fields in this format:

```
CANONICAL DESCRIPTIONS — [Brand] [Model]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DESCRIPTION:
[paragraph]

CONDITION:
[sentence]

GRAILZEE:
[paragraph]
← or "SKIP — not applicable" when grailzee_format is skip
```

Send approval buttons with the post:

```
buttons: [[{"text": "✅ Approve", "callback_data": "approve"}, {"text": "✏️ Change", "callback_data": "change"}]]
```

**On Approve:**
Save to `_draft.json` (see Output below). Then confirm to Telegram:
> "Descriptions saved. Step 3 complete — ready for Grailzee gate."

**On Request Changes:**
Ask: "What would you like to change?" Accept free-text feedback. Rewrite only
the affected field(s), but re-post all three fields for review. Run the
self-check again before re-posting. Loop until approved. Do not save until
approval is received.

**Plain-text approval fallback:** "looks good", "lg", "approve", "yes",
"good to go", "proceed" all count as approval. Parse intent, not exact strings.

---

## Output

After approval, write to `_draft.json` via `draft_save.py`:

```json
{
  "canonical": {
    "description": "<paragraph>",
    "condition_line": "<sentence>",
    "grailzee_desc": "<paragraph | null>"
  },
  "step": 3,
  "timestamp": "<ISO 8601>"
}
```

**Always use `draft_save.py`. Never write `_draft.json` directly.**

```
python3 /Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/draft_save.py "<folder>" '<json_patch>'
```

If `draft_save.py` returns `{"ok": false, ...}`: stop and report the error to
Telegram. Do not mark the step complete.

---

## What This Skill Does NOT Do

- Does not access `inputs.retail_net` or any field under `pricing.*`
- Does not load `platform-templates.md`, `character-substitutions.md`, or
  `posting-checklist.md`
- Does not write eBay titles, Facebook posts, or any platform-specific text
- Does not run character substitutions
- Does not access WatchTrack
- Does not read or act on `approved.grailzee_gate`
- Does not generate the Key Details pipeline line (run_phase_b.py does this)
- Does not write the eBay title (title-research skill does this)
- Does not explain complications, mechanisms, or finishing techniques
