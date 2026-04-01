# Watch Listing Pipeline — Orchestration Brief for OpenClaw

## What This Document Is

This is an interface specification for OpenClaw to build a watch listing
orchestration pipeline. It describes two skills that exist as independent
modules, their inputs/outputs, and the workflow sequence that connects them.
OpenClaw should use its own messaging setup (Telegram, Slack, or whatever
channel is configured) for approvals and interaction.

---

## Available Skills

### Skill 1: `watchtrack`

**Purpose:** Browser automation for WatchTrack inventory lookups and status
updates via Claude in Chrome.

**Capability A: Item Details**

| | |
|---|---|
| Trigger | "Look up SKU {sku}" or at the start of any listing pipeline |
| Inputs | `sku` (string), `working_folder` (absolute path) |
| Action | Navigates to WatchTrack inventory, searches by SKU, extracts all item data |
| Output | Writes `watchtrack.json` to `working_folder` |
| Error states | No Chrome connection, not authenticated, SKU not found, ambiguous results |

**Output schema (`watchtrack.json`):**
```json
{
  "sku": "9971Z",
  "extracted_at": "2026-03-31T22:35:00Z",
  "source_url": "https://watchtrack.com/store/item/{uuid}",
  "item": {
    "stock_id": "string",
    "brand": "string",
    "model": "string",
    "serial": "string|null",
    "reference": "string",
    "sub_status": "string",
    "list_in_elite": "string|null",
    "sale_channel": "string",
    "owner": "string",
    "condition": "string",
    "included": "string",
    "month": "string|null",
    "year": "string|null",
    "dial_color": "string",
    "bracelet_type": "string|null",
    "case_diameter": "string"
  },
  "pricing": {
    "retail_price": "number",
    "wholesale_price": "number",
    "item_cost": "number"
  },
  "specs": {
    "movement": "string|null",
    "caliber": "string|null",
    "base_caliber": "string|null",
    "frequency": "string|null",
    "power_reserve": "string|null",
    "number_of_jewels": "string|null",
    "case_material": "string|null",
    "bezel_material": "string|null",
    "bezel_type": "string|null",
    "thickness": "string|null",
    "crystal": "string|null",
    "water_resistance": "string|null",
    "dial_numerals": "string|null",
    "bracelet_material": "string|null",
    "bracelet_color": "string|null",
    "clasp_type": "string|null",
    "clasp_material": "string|null"
  },
  "item_notes": "string|null"
}
```

**Capability B: Change Substatus**

| | |
|---|---|
| Trigger | "Set substatus for {sku} to {value}" |
| Inputs | `sku` (string), `new_substatus` (string) |
| Valid substatus values | Intake, Needs Service, Needs Photos, Needs Video, Listing Prep, Ready for listing, On Chrono24, Grailzee First, Fully Listed, Sold |
| Action | Navigates to WatchTrack, opens edit modal, selects new value, saves |
| Output | Confirmation message with old → new value |
| Error states | Invalid value, SKU not found, modal didn't open, save failed |

---

### Skill 2: `watch-listing-content`

**Purpose:** Single source of truth for all listing content: voice rules,
pricing formulas, description standards, platform templates.

This skill is a knowledge base, not an executable. The orchestrator reads
it to know HOW to generate content. It contains:

| Section | What it provides |
|---------|-----------------|
| Voice Rules | Ogilvy Standard, Voss Standard, Knowledge vs. Confidence |
| Description Rules by Tier | Tier 1 (3-4 sentences), Tier 2/3 (4-6 sentences), Grailzee (emotional), WTA (structured), Reddit (richest prose) |
| Pricing Formulas | eBay (tiered fees + rounding), Chrono24 (7.5% commission), Facebook, WTA (comp validation), Reddit, Grailzee |
| Platform Templates | Exact copy-paste structures for all 9 platforms (in `references/platform-templates.md`) |
| Character Substitutions | Facebook algorithm avoidance table (in `references/character-substitutions.md`) |
| Posting Checklist Logic | Universal + price-based + brand-specific routing (in `references/posting-checklist.md`) |
| Trust/Payment Blocks | Per-platform trust language and payment methods |
| Do Nots | Absolute rules that apply to every listing |

**Reference files (read before generating full document):**
- `references/platform-templates.md` — copy-paste template structures
- `references/character-substitutions.md` — Facebook substitution table
- `references/posting-checklist.md` — checklist auto-generation logic

---

## Pipeline Workflow

The orchestrator owns the workflow sequence and approval gates. The skills
provide data and content knowledge. Here is the recommended sequence:

```
STEP 0: WATCHTRACK LOOKUP
│  Call: watchtrack skill, Capability A (Item Details)
│  Input: sku, working_folder
│  Output: watchtrack.json in working_folder
│  Gate: Present extracted data to user → Confirm / Correct
│
STEP 1: PHOTO REVIEW
│  Action: Review photos in listing folder
│  Gate: Approve / Request Changes
│  After approval, collect from user:
│    - Condition (BNIB / Excellent / Very Good / Good / Other)
│    - Tier (1 / 2 / 3)
│    - Grailzee format (No Reserve / Reserve / Skip)
│
STEP 2: PRICING
│  Read: watch-listing-content pricing formulas
│  Input: retail_net, buffer (default 5%), optional wholesale/WTA/Reddit prices
│  Calculate: All platform prices using formulas from content skill
│  Gate: Present pricing table → Approve / Request Changes
│
STEP 3: DESCRIPTIONS
│  Read: watch-listing-content voice rules + description rules by tier
│  Read: watch-listing-content platform-specific notes
│  Generate: Descriptions for each platform following tier rules
│  Gate: Present descriptions → Approve / Request Changes
│  Note: WTA does not need description approval (structured data only)
│
STEP 3.5: GRAILZEE RECOMMENDATION GATE (optional)
│  Action: Look up Grailzee median data for this reference
│  Gate: Proceed with Current Pricing / Adjust Pricing
│  If adjust: return to Step 2 with Grailzee data loaded
│
STEP 4: GENERATE DOCUMENT
│  Read: watch-listing-content document assembly order
│  Read: references/platform-templates.md for exact structures
│  Read: references/character-substitutions.md for Facebook text
│  Read: references/posting-checklist.md for checklist generation
│  Assemble: Complete multi-platform listing document
│  Output: Final document (PDF, markdown, or format of choice)
│
STEP 5: UPDATE WATCHTRACK (post-listing)
│  Call: watchtrack skill, Capability B (Change Substatus)
│  Set substatus based on what was listed:
│    - "Fully Listed" if all platforms done
│    - "On Chrono24" or "Grailzee First" if partial
```

---

## Approval Gate Design

The orchestrator should implement these gates using whatever interaction
model it has configured (Telegram buttons, Slack Block Kit, etc.):

| Gate | Options | Triggers |
|------|---------|----------|
| WatchTrack data confirmation | Confirm / Correct | After Step 0 |
| Condition selection | BNIB / Excellent / Very Good / Good / Other | After Step 1 |
| Tier selection | Tier 1 / Tier 2 / Tier 3 | After Step 1 |
| Grailzee format | No Reserve / Reserve / Skip | After Step 1 |
| Pricing approval | Approve / Request Changes | After Step 2 |
| Description approval | Approve / Request Changes | After Step 3 |
| Grailzee gate | Proceed / Adjust Pricing | After Step 3.5 |

**Free-text inputs (collect from user):**
- `retail_net` — Target NET price after all fees and negotiation
- `wholesale_net` — Optional wholesale NET
- `wta_price` — Optional WTA Dealer Chat asking price
- `wta_comp` — Required if wta_price provided (lowest US dealer comp)
- `reddit_price` — Optional Reddit asking price
- `msrp` — Optional (search if unknown)
- `buffer` — Negotiation buffer percentage (default: 5)
- `condition_detail` — Component-level condition notes

---

## Checkpoint System (Recommended)

Save state after each approved step so the pipeline can resume if
interrupted. Suggested checkpoint structure:

```json
{
  "step": 2,
  "timestamp": "ISO-8601",
  "sku": "9971Z",
  "inputs": { "collected inputs so far" },
  "watchtrack": { "data from watchtrack.json" },
  "approved": {
    "photos": { "status": "approved", "timestamp": "..." },
    "pricing": { "status": "approved", "table": { "..." }, "timestamp": "..." }
  }
}
```

On startup, if a checkpoint exists for a given SKU, offer to resume from
the last completed step.

---

## Listing Folder Convention

Listing folders follow the naming pattern `{internalRef}-{modelRef}/` and
contain:
- Numbered image files (photos)
- `watchtrack.json` (written by Step 0)
- Checkpoint file (written by orchestrator after each approved step)
- Final listing document (written by Step 4)

The pipeline root and folder structure depend on the orchestrator's
environment configuration.

---

## Key Rules the Orchestrator Must Enforce

1. **Photos before everything.** Never proceed to pricing or descriptions
   without photo review and approval.
2. **Pricing and descriptions are separate gates.** Never combine them into
   a single approval.
3. **WTA compliance.** If WTA price exceeds 10% below comp, block the WTA
   listing. If any other platform price is lower than WTA price, flag the
   conflict.
4. **Character substitutions on Facebook only.** Never apply to eBay,
   Chrono24, Reddit, WTA, Value Your Watch, Instagram, or Grailzee.
5. **CC fee is 4.5%.** Non-negotiable. Applies to all platforms that show
   payment methods.
6. **Update WatchTrack after listing.** Use the watchtrack skill to set
   substatus once platforms are posted.

---

## What the Orchestrator Does NOT Need to Know

The orchestrator does not need to know voice rules, pricing math, or
template structures in detail. It delegates those to the content skill.
The orchestrator's job is:

- Collect inputs from the user
- Enforce the step sequence and approval gates
- Call the watchtrack skill for data and status updates
- Read the content skill for formulas, rules, and templates
- Assemble the final document
- Save checkpoints
- Deliver the output

---

*Version 1.0 | March 31, 2026*
*Skills referenced: watchtrack v1.1, watch-listing-content v1.0*
