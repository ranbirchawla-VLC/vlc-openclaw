---
name: step1-photos
description: >
  Review listing photos, assess quality and condition, collect pricing inputs
  via Telegram. Called by the listing pipeline when _draft.json is at step 0
  (WatchTrack done, photos not yet reviewed). Writes approved.photos and all
  step-1 inputs to _draft.json. Triggered by pipeline.py — do not invoke directly.
---

# Step 1: Photos and Input Collection

## Purpose

Read every image in the listing folder, post a quality assessment to Telegram,
get approval, then collect the inputs required to calculate pricing. Saves
`approved.photos` on photo approval and advances to step 1 after all required
inputs are confirmed.

---

## Step Gate

Read `_draft.json`. Check `step`.

| step value | Action |
|------------|--------|
| 0 | Proceed normally — run photo review |
| 0 AND `approved.photos.status == "approved"` | Photos already approved — skip photo review, go straight to Phase B |
| ≥ 1 | Send "Step 1 already complete" to Telegram and stop |

Note: a schema-valid `_draft.json` always has `step` present. If for any reason
it is absent, treat as step 0.

---

## Empty Folder

Before reviewing photos, scan the listing folder for image files
(`*.jpg`, `*.jpeg`, `*.png` — case-insensitive).

If no images found:
> "No photos found in [folder name]. Add photos and re-trigger this step."

Stop. Do not write `_draft.json`. Do not advance step.

---

## Phase A — Photo Review

Read every image file using the `read` tool. Assess against the criteria below.

### Review criteria

**Angles — check for:**
- Dial: straight-on, well-lit, indices and hands visible without glare
- Case sides: both the crown side and the opposite flank
- Case back: serial number legible; note if engraved, plain, or exhibition
- Bracelet or strap and clasp
- Box and papers (required if `inputs.included` mentions them or `watchtrack.notes` references them)
- Any condition detail areas: scratches, dents, bezel insert wear, crown damage

**Quality:**
- No harsh shadows obscuring dial or case details
- No blown highlights that lose texture on polished surfaces
- Watch fills the frame; backgrounds are clean or neutral

**Condition conflict check:**
Compare what is visibly worn or damaged in photos against `watchtrack.notes`.
If photos show wear that WatchTrack does not mention (or vice versa), flag the
specific discrepancy in the feedback paragraph.

### Feedback format

Post at least one full paragraph to Telegram covering:
1. What is working (composition, lighting, angle coverage)
2. What is missing or could be improved
3. Whether photos are sufficient to list — yes or no with one-line reasoning
4. Any condition conflict with WatchTrack data, stated specifically

Header: `PHOTO REVIEW — [Brand] [Model]`

Then send approval buttons with the review:
```
buttons: [[{text: "✅ Approve", callback_data: "approve"}, {text: "✏️ Change", callback_data: "change"}]]
```

**On Change:** Ask what to correct. If new photos are added, re-read and re-review.
Re-post feedback and buttons. Loop until approved.

**Plain-text approval:** "looks good", "lg", "approve", "yes", "good to go" all
count. Parse intent.

**On Approve:** immediately save Save 1 (see below), then proceed to Phase B.

---

## Save 1 — Photo Approval

Write to `_draft.json` via `draft_save.py` immediately on photo approval:

```json
{
  "approved": {
    "photos": {
      "status": "approved",
      "notes": "<feedback paragraph text>",
      "timestamp": "<ISO 8601>"
    }
  }
}
```

Do not advance `step` yet.

---

## Phase B — Button Inputs

Check `_draft.json` for already-known values before sending any button prompt.
Skip a button set entirely if the value is already present in `inputs.*` or
`inputs_pending.*`.

Send one button set at a time. Wait for a reply before sending the next.

### Condition (skip if `inputs.condition` is already set)

```
buttons: [
  [{text: "BNIB",      callback_data: "BNIB"},
   {text: "Excellent", callback_data: "Excellent"},
   {text: "Very Good", callback_data: "Very Good"}],
  [{text: "Good",      callback_data: "Good"},
   {text: "Other",     callback_data: "Other"}]
]
```

If "Other": follow up immediately:
> "Describe the condition in detail — case, bezel, crystal, dial, movement,
> bracelet, crown."

Collect the free-text reply and store as `inputs.condition_detail`.

### Tier (skip if `inputs.tier` is already set — WatchTrack never sets this)

```
buttons: [[{text: "Tier 1", callback_data: "1"},
           {text: "Tier 2", callback_data: "2"},
           {text: "Tier 3", callback_data: "3"}]]
```

Note on `grailzee_format`: this skill does not collect it. The Grailzee gate
at step 3.5 evaluates actual market data and sets the format. No button or
prompt for NR/Reserve/Skip is shown here.

---

## Phase C — Free-Text Inputs

After button inputs are resolved, check which free-text inputs are still missing.

**Pre-populated from WatchTrack — check these fields before prompting:**
- `retail_net` ← `watchtrack.retail_price_wt` (if present)
- `wholesale_net` ← `watchtrack.wholesale_price_wt` (if present)
- Also check `inputs_pending.*` for values staged during the WatchTrack step

**Merge precedence:** Values confirmed in Phase B or typed in Phase C override
anything in `inputs_pending`. Phase C replies win on conflict.

If ALL required inputs (condition, tier, retail_net) are already known from any
of the above sources, skip this phase entirely and go straight to Save 2.

Otherwise send one consolidated message. Include only the lines for inputs that
are genuinely missing:

```
A few more details:

Retail NET: $___               ← required; omit line if already known
What's included: ___           ← always ask (box/papers/extra links/hang tags/etc.)
Wholesale NET (optional): $___
WTA price + comp (optional): $price / $comp  (your price / lowest dealer comp)
Reddit price (optional): $___
MSRP (optional): $___
Buffer % (default 5): ___      ← only include if user needs to override default
```

Ranbir may reply with all values in one message or across several. Collect
progressively. Parse dollar amounts: strip `$` and `,`. When all required
inputs are present, proceed to Save 2.

If `wta_price` is provided but `wta_comp` is absent: ask before saving:
> "WTA comp needed — what's the lowest US dealer price on Chrono24 or eBay?"

---

## Save 2 — Step 1 Complete

Write to `_draft.json` via `draft_save.py` after all required inputs are confirmed.

Merge rules for this patch:
- `inputs_pending` values are folded into `inputs` and the field is nulled
- Phase C replies take precedence over `inputs_pending` on any conflict
- Omit optional fields (wholesale_net, wta_price, etc.) from the patch if the
  user did not provide them — `draft_save.py` deep-merge will leave existing
  values untouched. Write `null` only when the user explicitly said they do not apply.

```json
{
  "step": 1,
  "timestamp": "<ISO 8601>",
  "inputs": {
    "condition":        "<BNIB|Excellent|Very Good|Good|Other>",
    "condition_detail": "<string or empty>",
    "tier":             2,
    "retail_net":       3800,
    "buffer":           5,
    "included":         "Box and papers",
    "wholesale_net":    null,
    "wta_price":        null,
    "wta_comp":         null,
    "reddit_price":     null,
    "msrp":             null
  },
  "inputs_pending": null
}
```

Always use `draft_save.py`. Never write `_draft.json` directly:
```
python3 /Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/draft_save.py "<folder>" '<json_patch>'
```

If `draft_save.py` returns `{"ok": false, ...}`: stop and report the error to Telegram.

After a successful save, confirm:
> "Step 1 complete — [Brand] [Model] ready for pricing."

---

## What This Skill Does NOT Do

- Does not calculate pricing — run_pricing.py handles all formulas
- Does not collect `grailzee_format` — the gate at step 3.5 evaluates market
  data and determines NR vs. Reserve; no user guess is collected here
- Does not write any listing copy or descriptions
- Does not load voice-tone.md, platform-templates.md, character-substitutions.md,
  or posting-checklist.md
- Does not access WatchTrack — step0-watchtrack skill owns that
- Does not read or write `canonical.*` or `pricing.*`
- Does not evaluate Grailzee eligibility
