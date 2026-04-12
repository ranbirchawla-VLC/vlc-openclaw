---
name: step0-watchtrack
description: >
  Look up a watch on WatchTrack, extract inventory and pricing data, confirm
  via Telegram, and write to _draft.json. Called by the listing pipeline when
  a new listing folder is detected. Writes all step-0 fields and advances to
  step 0. Triggered by pipeline.py — do not invoke directly.
---

# Step 0: WatchTrack Lookup

## Purpose

Parse the listing folder name to identify the watch, look it up on WatchTrack,
extract all available data, confirm with Ranbir via Telegram, and write the
result to `_draft.json`. This is the first step in the pipeline.

---

## Step Gate

If `_draft.json` exists and `step >= 0`, send to Telegram:
> "Step 0 already complete for [folder name]. Nothing to do."

Stop.

If `_draft.json` does not exist, proceed normally.

---

## Phase A — Folder Parsing

Parse the listing folder name. Convention: `{internal_ref}-{model_ref}`.

Split on the first hyphen only:
- `internal_ref` — everything before the first hyphen (e.g., `164WU`)
- `model_ref` — everything after the first hyphen (e.g., `IW371446-1`)

If the folder name contains no hyphen:
- `internal_ref` = full folder name
- `model_ref` = `""`

---

## Phase B — WatchTrack Lookup

Navigate to `https://watchtrack.com/store/home` using the native browser tool.
The user is already authenticated in Chrome. Do not attempt to log in.

Search for the watch using `internal_ref`. Locate the inventory record.

### Fields to Extract

**Into `inputs.*`:**

| Field | WatchTrack source |
|-------|-------------------|
| `brand` | Brand field |
| `model` | Model field |
| `reference` | Reference number field |
| `year` | Year / production year |
| `case_size` | Case size |
| `case_material` | Case material |
| `movement` | Movement / caliber |

**Into `watchtrack.*`:**

| Field | WatchTrack source |
|-------|-------------------|
| `cost_basis` | Cost / purchase price |
| `serial` | Serial number |
| `notes` | Notes field — always capture verbatim |
| `recent_comps` | Recent sold comps — array of prices or structured object as returned |
| `retail_price_wt` | Retail price if shown as a dedicated field |
| `wholesale_price_wt` | Wholesale price if shown as a dedicated field |

**Notes field handling:** Always capture verbatim into `watchtrack.notes`. If
the Notes field contains pricing language (retail, wholesale, floor, comp,
asking, etc.), extract those figures and surface them alongside any dedicated
price fields. Flag each extracted figure as "from Notes field" in the Telegram
confirmation message. Never silently prefer one source over another — show
both and let Ranbir decide.

**Condition handling:** If WatchTrack shows condition as "Brand New", write
`inputs.condition = "BNIB"` now. For any other condition string, do not write
`inputs.condition` — leave the field absent and let step 1 collect it via
Telegram buttons.

### Lookup Failure

If the watch is not found on WatchTrack:

Send to Telegram:
> "WatchTrack lookup failed for [internal_ref] — watch not found. Continuing
> to step 1 with folder name only. Fill in details manually."

Write a minimal `_draft.json` with only `internal_ref`, `model_ref`, and
proceed to Save below (step will be set to 0).

---

## Phase C — Telegram Confirmation

Format the extracted data as a confirmation message:

```
WATCHTRACK — [Brand] [Model] [Reference]

Internal ref:  [internal_ref]
Cost basis:    $[cost_basis]
Serial:        [serial]
Condition:     [condition or "not set"]
Year:          [year or "—"]
Case:          [case_size] [case_material]
Movement:      [movement]
Included:      (not set — collected at step 1)

PRICING
Retail (WatchTrack):    $[retail_price_wt or "—"]
Wholesale (WatchTrack): $[wholesale_price_wt or "—"]
[If pricing extracted from Notes: "Retail (Notes field): $X"]
[If pricing extracted from Notes: "Wholesale (Notes field): $X"]

Comps: [recent_comps summary]

NOTES
[watchtrack.notes verbatim, or "—" if empty]
```

Send approval buttons:
```
buttons: [[{text: "✅ Looks Good", callback_data: "approve"}, {text: "✏️ Correct This", callback_data: "change"}]]
```

**On Change:** Ask what to correct. Accept free-text. Apply corrections, re-post
the summary and buttons. Loop until approved.

**On Approve:** Proceed to Save.

**Plain-text approval:** "looks good", "lg", "approve", "yes", "good to go" all
count. Parse intent.

---

## Save — Step 0 Complete

Write to `_draft.json` via `draft_save.py`:

```json
{
  "step": 0,
  "timestamp": "<ISO 8601>",
  "inputs": {
    "internal_ref": "<string>",
    "model_ref":    "<string>",
    "brand":        "<string>",
    "model":        "<string>",
    "reference":    "<string>",
    "year":         "<string or omit if absent>",
    "case_size":    "<string or omit if absent>",
    "case_material":"<string or omit if absent>",
    "movement":     "<string or omit if absent>",
    "condition":    "BNIB"
  },
  "watchtrack": {
    "cost_basis":          <number>,
    "serial":              "<string>",
    "notes":               "<verbatim string>",
    "recent_comps":        <array or object>,
    "retail_price_wt":     <number or omit if absent>,
    "wholesale_price_wt":  <number or omit if absent>
  }
}
```

Omit optional fields (`year`, `case_size`, `case_material`, `movement`,
`condition`, `retail_price_wt`, `wholesale_price_wt`) if not found.
Do not write `null` for missing optional fields — omit the key entirely.
`draft_save.py` deep-merge will leave existing values untouched.

Always use `draft_save.py`. Never write `_draft.json` directly:
```
python3 /Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/draft_save.py "<folder>" '<json_patch>'
```

If `draft_save.py` returns `{"ok": false, ...}`: stop and report the error to
Telegram.

After a successful save, confirm:
> "Step 0 complete — [Brand] [Model] ready for photo review."

---

## What This Skill Does NOT Do

- Does not load pricing formulas, run_pricing.py, or any pricing calculation
- Does not load voice-tone.md, platform-templates.md, character-substitutions.md,
  or posting-checklist.md
- Does not review photos or assess condition in images
- Does not write listing copy or descriptions
- Does not collect `condition` from Ranbir (except mapping "Brand New" to BNIB)
- Does not collect `tier`, `retail_net`, `included`, or any step-1 inputs
- Does not access Grailzee or evaluate listing eligibility
- Does not write `inputs_pending` — any pricing data from WatchTrack goes into
  `watchtrack.*` only; step 1 reads those fields and promotes them to `inputs`
