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
| `watchtrack.notes` | If present | Primary source for provenance and service history |

**Do not read:** `inputs.retail_net`, `pricing.*`, `approved.grailzee_gate`, or
any pricing data. This skill has no knowledge of what the watch costs.

---

## Writing Instructions

### Descriptive paragraph

Apply the tier rules from `voice-tone.md`:

- **Tier 1:** 3–4 sentences. Why this reference is respected, key technical
  features, what the buyer is getting. Educational, trust-building tone.
- **Tier 2/3:** 4–5 sentences. Horological significance, technical detail,
  what makes it special, why this specific example. Competence-focused tone.
  Tier 3: note of rarity or exclusivity — never hype, honest scarcity.

**Source priority:**
1. `watchtrack.notes` — extract any provenance, service history, or context not
   on the spec sheet. This is the differentiator. Use it.
2. Standard knowledge about the brand, model, caliber, complications.
   Apply confidence-tier language (from wearing it), not knowledge-tier (spec sheet).

**Hard rules for the paragraph:**
- One paragraph, full stop
- No em-dashes
- No condition language — condition lives in the condition sentence
- No pricing, value, or cost-of-ownership language
- If service history is unknown: include "service history unknown but running
  accurately" — use `watchtrack.notes` to confirm this before including it

### Condition sentence

One sentence. State: condition rating + completeness + provenance if notable.

Format: `[Condition], [completeness], [provenance note if applicable].`

Examples:
- "Excellent condition, full set with original box and papers dated June 2023."
- "Very good condition, watch only, no box or papers."
- "Excellent condition, full set, extra links and hang tags in sealed bag."

Use `inputs.condition` for the rating. Use `inputs.included` for completeness.
Use `inputs.condition_detail` if component notes merit mention (e.g., "Light
surface marks on case flanks" when condition is Very Good).

One sentence only. Do not turn this into a paragraph.

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
the affected field(s), but re-post all three fields for review. Loop until
approved. Do not save until approval is received.

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
