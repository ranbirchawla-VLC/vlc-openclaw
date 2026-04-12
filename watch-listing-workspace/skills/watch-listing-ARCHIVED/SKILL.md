---
name: watch-listing-openclaw
description: >
  Generate multi-platform watch listings for Vardalux Collections via Telegram,
  following the mandatory approval workflow with plain-text replies. Use this
  skill whenever the user wants to create a watch listing, list a watch for
  sale, build a listing document, write a Grailzee description, or mentions
  listing a specific watch reference. Also trigger when the user says "list this",
  "build a listing", "write the listing", "Grailzee description", "WTA listing",
  "dealer chat", "Reddit listing", "watchexchange", or references any watch
  brand/model in the context of selling or listing. Trigger when a listing folder
  is detected in the pipeline (format: {internalRef}-{modelRef}/). This skill
  handles all platforms: Grailzee, eBay, Chrono24, Facebook (retail and wholesale),
  WTA Dealer Chat, Reddit r/watchexchange, Value Your Watch, and Instagram.
---

# Watch Listing Generator — Vardalux Collections (OpenClaw / Telegram v3)

## Session Model — Read This First

**One step per session. Always.**

Every time this skill is triggered:
1. Read `_draft.json` from the listing folder
2. Identify the next incomplete step
3. Do ONLY that step
4. Save `_draft.json`
5. Send result to Telegram
6. Stop

Do not attempt to run multiple steps in one session. Do not continue to the
next step after completing one. The user will trigger the next session when
ready. This keeps each session short, the skill in context, and mnemo cache
hits maximised.

**Phase B (platform derivations) exception:** Each platform is one micro-step.
Write one platform to the .md file, save draft, then immediately do the next
platform in the same session. Stop after all platforms are written. The .md
file should be complete (all platforms) before the session ends.

## Purpose

Generate complete, copy-paste-ready watch listings across all sales platforms
following Vardalux brand standards. This is the OpenClaw version of the skill,
designed for Telegram-based interaction with plain-text approvals. Output is a
Markdown file converted to PDF via the centralized `generate_listing_pdf.py`
tool, saved into the listing folder alongside the photos.

A parallel Claude Chat version of this skill exists for use in claude.ai sessions.
Both versions share identical business logic, pricing formulas, voice standards,
and platform rules. Only the interaction model, tool layer, and output format differ.

### Identity Anchor

Vardalux are **dealers who transact with purpose**. Not commodity flippers or
margin grinders. Every transaction reflects the client's broader interests:
portfolio positioning, strategic access, and generational wealth building. The
thinking behind each deal is the differentiator, not the absence of deals.

**Profit for Acquisition:** Platform trading (Grailzee, eBay, Chrono24) serves
two purposes simultaneously: it generates margin and turns capital, and it is a
client acquisition channel. Every platform sale earns while introducing Vardalux
to someone who may become a long-term client. Listings are not just inventory
management. They are the first impression of a relationship that nurture builds
deeper over time. Presentation quality matters because it serves both purposes.

### Named Frameworks

Two named frameworks govern all Vardalux communication:

**The Ogilvy Standard** (David Ogilvy's advertising principles) governs writing:
respect the reader's intelligence, facts over adjectives, the product is the hero,
every sentence earns its place, research before writing, big ideas over clever
tricks, tell the truth. Specificity over superlatives.

**The Voss Standard** (Chris Voss' negotiation principles) governs persuasion and
conversation design: tactical empathy, labeling, no-oriented questions, calibrated
questions, "that's right" moments, accusation audits, mirroring, late-night FM DJ
voice. In listings, the Voss Standard manifests as: addressing buyer fears directly
(labeling), building trust before price (tactical empathy), and writing that signals
calm authority rather than urgency (DJ voice).

---

## Environment

### Paths

| Path | Value |
|------|-------|
| Pipeline root | `/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Photo Pipeline` |
| OpenClaw symlink | `~/.openclaw/workspace/pipeline` (points to pipeline root) |
| PDF tool | `/Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/generate_listing_pdf.py` |

### Brand Folder Scanning

Brand folders are **dynamically discovered**. Do not hardcode a brand list.

On pipeline scan:
1. List all subdirectories under the pipeline root
2. Skip `Archive/` and any hidden directories (prefixed with `.`)
3. Treat every remaining subdirectory as a brand folder
4. Scan each brand folder for listing folders matching `{internalRef}-{modelRef}/`

This ensures new brands added to the pipeline are automatically picked up
without skill updates.

### Listing Folder Contents

Listing folders follow the naming convention `{internalRef}-{modelRef}/`.
Examples: `164WU-IW371446-1/` | `14618-M28500-0003/`

Each listing folder contains:
- Numbered PNG files (photos)
- `_draft.json` (state checkpoint, created and updated by this pipeline)
- `_Listing.md` (assembled Markdown, input to PDF generation)
- `_Listing.pdf` (final output, generated by the PDF tool)

### Telegram Interaction Model

All approvals, selections, and messages go to Telegram. Ranbir replies with
plain text. There are no interactive buttons, no Block Kit, no structured
payloads. The agent sends messages and waits for Ranbir's text reply.

**Approval prompts:** Send a summary of what needs approval, then send an
inline button row using the `message` tool with `action: send` and a `buttons`
array. Always use buttons for binary or small-choice gates.

Button layouts per gate:

- **Photos / Pricing / Canonical description:**
  ```
  buttons: [[{text: "✅ Approve", callback_data: "approve"}, {text: "✏️ Change", callback_data: "change"}]]
  ```
- **WatchTrack confirmation:**
  ```
  buttons: [[{text: "✅ Looks Good", callback_data: "approve"}, {text: "✏️ Correct", callback_data: "change"}]]
  ```
- **Grailzee gate:**
  ```
  buttons: [[{text: "▶️ Proceed", callback_data: "proceed"}, {text: "🔧 Adjust", callback_data: "adjust"}]]
  ```
- **Grailzee format:**
  ```
  buttons: [[{text: "NR", callback_data: "NR"}, {text: "Reserve", callback_data: "Reserve"}, {text: "Skip", callback_data: "Skip"}]]
  ```
- **Condition:**
  ```
  buttons: [[{text: "BNIB", callback_data: "BNIB"}, {text: "Excellent", callback_data: "Excellent"}, {text: "Very Good", callback_data: "Very Good"}], [{text: "Good", callback_data: "Good"}, {text: "Other", callback_data: "Other"}]]
  ```
- **Tier:**
  ```
  buttons: [[{text: "Tier 1", callback_data: "1"}, {text: "Tier 2", callback_data: "2"}, {text: "Tier 3", callback_data: "3"}]]
  ```

**How to send buttons** — use the `message` tool:
```
action: send
channel: telegram
message: "[your summary text here]"
buttons: [[{"text": "✅ Approve", "callback_data": "approve"}, {"text": "✏️ Change", "callback_data": "change"}]]
```
Always send the summary text in `message` and the buttons in `buttons`. Do not
send two separate messages (one for text, one for buttons).

**Also accept plain text fallback.** "Looks good", "lg", "approve", "yes",
"good to go", "proceed" all mean approval. Parse intent, not exact strings.
If a reply is ambiguous, ask for clarification.

**Free-text inputs:** Same as before: retail_net, wholesale_net, wta_price,
wta_comp, reddit_price, msrp, buffer. These arrive as plain Telegram messages.

### Browser Tool (WatchTrack Access)

WatchTrack is accessed via the **OpenClaw native browser tool**. Never use
Peekaboo.

```
action: navigate
profile: openclaw
```

The user is already logged into WatchTrack in the browser session. Do not
attempt to authenticate. Start at https://watchtrack.com/store and search
for the reference number.

### Image Review

To review photos, read the image files from the listing folder using the `read`
tool. Examine each image and evaluate against the photo review criteria in
Step 1. Send the review summary to Telegram.

---

## Expected Inputs

Inputs arrive via Telegram messages. Some may arrive across multiple messages.
The pipeline collects inputs progressively across steps.

**From folder name (parsed automatically):**
- `internal_ref` — Internal reference ID (first segment before hyphen)
- `model_ref` — Model reference number (remaining segments)

**From WatchTrack lookup (Step 0, automatic):**
- `brand`, `model`, `reference`, `year`, `case_size`, `case_material`
- `movement`, `cost_basis`, `recent_comps`, `serial`

**From Telegram replies:**
- `condition` — Overall condition rating (BNIB / Excellent / Very Good / Good / Other)
- `tier` — Buyer tier (1, 2, or 3)
- `grailzee_format` — Auction format (NR / Reserve / Skip)
- `retail_net` — Target NET price after all fees and negotiation
- `wholesale_net` — Target wholesale NET (optional)
- `wta_price` — WTA Dealer Chat asking price (optional)
- `wta_comp` — Lowest US dealer comp from C24 or eBay (required if wta_price provided)
- `reddit_price` — Reddit r/watchexchange asking price (optional)
- `msrp` — MSRP (optional, search if unknown)
- `buffer` — Negotiation buffer percentage (default: 5)

**From user (prompted when needed):**
- `included` — What ships with the watch
- `condition_detail` — Component-level condition notes (if "Other" selected or detail needed)

### Condition Detail Format (when prompted)

```
Overall: Excellent condition with minimal wear
Case: Light surface marks on polished surfaces from desk wear. Brushed surfaces crisp.
Bezel: Aluminum bezel insert excellent, no fading or dings
Crystal: Sapphire crystal clear, no marks
Dial: Pristine, no moisture marks or blemishes
Movement: Running accurately, all functions working correctly
Bracelet: Light desk wear on clasp. Sized for 7" wrist, 2 extra links included
Crown: Screw-down, functions properly
```

If any component is not provided, ask before proceeding.

---

## _draft.json Checkpoint System

After every approved step, save a `_draft.json` checkpoint to the listing folder.
This enables re-entrant recovery if the pipeline stalls mid-flow.

**Never write `_draft.json` directly.** Always use `draft_save.py`:

```
python3 /Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/draft_save.py "{folder_path}" '{"key": "value"}'
```

The tool handles reading, deep-merging, validating, and atomic writing.
Pass only the fields that changed — existing fields are preserved.
If the result is `{"ok": false, ...}`, stop and report the error to Telegram.
Never write JSON by hand. Never use exec to write files directly.

### Structure

```json
{
  "step": 2,
  "timestamp": "2026-03-29T14:32:00Z",
  "inputs": {
    "internal_ref": "164WU",
    "model_ref": "IW371446-1",
    "brand": "IWC",
    "model": "Portugieser Chronograph",
    "reference": "IW371446",
    "retail_net": 3200,
    "tier": 1,
    "condition": "Excellent",
    "grailzee_format": "NR"
  },
  "watchtrack": {
    "cost_basis": 2650,
    "recent_comps": [3100, 3250, 2975],
    "serial": "ABC12345",
    "notes": "any extracted notes"
  },
  "approved": {
    "photos": {
      "status": "approved",
      "notes": "photo review feedback text",
      "timestamp": "2026-03-29T14:10:00Z"
    },
    "pricing": {
      "status": "approved",
      "table": { "ebay": 3649, "chrono24": 3625 },
      "timestamp": "2026-03-29T14:32:00Z"
    }
  }
}
```

### Resume Logic

On startup, read `_draft.json` from the listing folder:

1. **If `pipeline_status == "COMPLETE"` or `step == "done"`:** Send to Telegram:
   "[Brand] [Model] ([SKU]) is already complete. PDF exists. Nothing to do." Stop.

2. **If no `_draft.json` exists:** Start from Step 0.

3. **Otherwise:** Do not ask RESUME or START OVER. Just silently resume from the
   next incomplete step. The draft is the source of truth. Load it, find the
   next step, do it, save, stop.

   Exception: if `step == "start_over_requested"` in the draft, archive the
   old draft as `_draft.json.bak` and begin fresh from Step 0.

---

## The Pipeline Workflow

```
WATCHTRACK ──confirm──▶ PHOTOS ──approve──▶ PRICING ──approve──▶ DESCRIPTIONS ──approve──▶ GRAILZEE GATE ──confirm──▶ GENERATE PDF
     Step 0                Step 1              Step 2               Step 3                  Step 3.5                   Step 4
```

Hard approval gates at every step. Never skip steps. Never combine steps.

### Step 0: WATCHTRACK LOOKUP

Runs automatically when a listing folder is detected or the user initiates a
listing by referencing a folder name.

1. Parse the folder name to extract `internal_ref` and `model_ref`
2. Use the OpenClaw browser tool to open WatchTrack:
   ```
   action: navigate
   profile: openclaw
   ```
   The user is already logged into WatchTrack. Do not attempt to authenticate.
   Navigate to: https://watchtrack.com/store
3. Look up the reference number
4. Extract: serial data, cost basis, recent sold comps, condition notes if present
5. Save extracted data into `_draft.json` (step: 0)
6. Send a summary of findings to Telegram:
   "WatchTrack data for [brand] [model]: [summary]. Reply LOOKS GOOD or tell
   me what to correct."

If Ranbir replies with corrections, update `_draft.json` with the corrected
fields and re-confirm.

**If WatchTrack lookup fails or returns no data:** Send a warning to Telegram
and continue to Step 1. Do not block the pipeline. The user can provide missing
data manually.

After confirmation, save checkpoint and proceed to Step 1.

### Step 1: PHOTOS

Read every image in the listing folder using the `read` tool.

Send to Telegram at least one full paragraph of feedback covering:
- What is working well (composition, lighting, angles covered)
- What is missing or could be improved
- Whether the photos are sufficient to list (yes/no with reasoning)
- Any condition details visible in photos that conflict with WatchTrack data
  or provided condition notes

Then: "Reply APPROVE or tell me what to change."

If Ranbir requests changes: address the feedback, re-review if new photos are
added, and re-prompt for approval.

Do NOT proceed until approval is received. If the folder is empty, stop entirely.

After approval, check `_draft.json` for already-known inputs. Only ask for
what is genuinely missing. Do NOT ask for inputs already present in the draft.

Inputs that may already be in the draft from WatchTrack (Step 0):
- `condition` — from watchtrack notes or photo review
- `retail_net` — use `watchtrack.retail_price_wt` if present
- `wholesale_net` — use `watchtrack.wholesale_price_wt` if present
- `cost_basis` — from `watchtrack.cost_basis`

Only ask for inputs that are null or missing. If retail_net and wholesale_net
are already known from WatchTrack, do not ask for them again. If condition
was already provided, do not ask again.

Send a single consolidated message asking ONLY for what is missing:

```
Photos approved. I need the following to calculate pricing:

[Only include lines for inputs that are genuinely missing]
Condition: BNIB, Excellent, Very Good, Good, or Other  ← only if unknown
Tier: 1, 2, or 3
Grailzee format: NR, Reserve, or Skip
Retail NET: $___  ← only if not in WatchTrack data
Wholesale NET (optional): $___  ← only if not in WatchTrack data
WTA price + comp (optional): $___
Reddit price (optional): $___
Buffer (default 5%): ___%
```

If ALL required inputs are already known (condition, tier, grailzee_format,
retail_net), skip this prompt entirely and proceed directly to Step 2.

Ranbir may reply with all inputs in one message or across multiple messages.
Collect progressively. When all required inputs are received, proceed.

Save checkpoint (step: 1) after photo approval.

### Step 2: PRICING

Calculate platform-specific pricing using the formulas below. Send the pricing
table to Telegram.

#### eBay Pricing

```
buffered = retail_net × (1 + buffer/100)

ebay_fees:
  first_1000 = min(buffered, 1000) × 0.125
  next_4000  = min(max(buffered - 1000, 0), 4000) × 0.04
  remainder  = max(buffered - 5000, 0) × 0.03
  total_fees = first_1000 + next_4000 + remainder

list_price = buffered + total_fees
Round to nearest $X,X49 or $X,X99 (whichever is closer)

auto_accept  = list_price × 0.95 (round to nearest $50)
auto_decline = list_price × 0.85 (round to nearest $50)
```

#### Chrono24 Pricing

```
buffered = retail_net × (1 + buffer/100)
list_price = buffered / (1 - 0.075)
Round to clean number (nearest $25 or $50)
```

#### Facebook Retail Pricing

```
buffered = retail_net × (1 + buffer/100)
list_price = buffered
Round to clean number
```

#### Facebook Wholesale Pricing (only if wholesale_net provided)

```
list_price = wholesale_net
Round to clean number
```

#### WTA Dealer Chat Pricing (only if wta_price provided)

```
wta_comp = lowest US dealer comp from Chrono24 or eBay (whichever is lower)
max_allowed = wta_comp × 0.90   (absolute ceiling)
sweet_spot  = wta_comp × 0.80   (recommended range)

wta_price must be ≤ max_allowed

If wta_price > max_allowed:
  ⚠️ FLAG: Price exceeds WTA 10% below comp rule. Admin will remove listing.
  Show: "WTA comp: $X,XXX → Max allowed: $X,XXX → Your price: $X,XXX (OVER by $XXX)"
  Do NOT proceed with WTA listing until price is corrected.

If wta_price ≤ max_allowed but > sweet_spot:
  ℹ️ NOTE: Price is compliant but above the sweet spot.
  Show: "Sweet spot: ≤$X,XXX — you're $XXX above. Listing is valid but may sit."

If wta_price ≤ sweet_spot:
  ✅ Price is in the sweet spot for WTA.
```

**WTA Compliance Rule:** The watch cannot be listed for a lower price ANYWHERE
else on the internet or any other dealer chat. If any other platform price is
lower than `wta_price`, flag the conflict immediately.

#### Reddit r/watchexchange Pricing (only if reddit_price provided)

```
list_price = reddit_price
No platform fees. No buffer calculation.
```

If `msrp` is known, include it in the specs section. If not provided and the
reference is recognizable, search for it before generating the listing.

#### Grailzee Pricing (if grailzee_format is not "skip")

No pricing calculation needed for NR auctions (start at $1).
For Reserve: reserve_price is provided by user or set at Grailzee median +10-15%.

Send the pricing table to Telegram:

```
PRICING SUMMARY

| Platform           | List Price | Notes                    |
|--------------------|------------|--------------------------|
| Grailzee           | $1 start   | No-reserve, 5-day        |
| eBay               | $X,XXX     | Accept: $X,XXX / Decline: $X,XXX |
| Chrono24           | $X,XXX     |                          |
| Facebook Retail    | $X,XXX     | +4.5% CC fee             |
| Facebook Wholesale | $X,XXX     | (if applicable)          |
| WTA Dealer Chat    | $X,XXX     | Comp / Max / Sweet spot  |
| Reddit             | $X,XXX     | MSRP: $X,XXX             |
```

Then: "Reply APPROVE or tell me what to change."

Save checkpoint (step: 2) after pricing approval.

### Step 3: DESCRIPTIONS

Step 3 has two phases. **Do not combine them.**

#### Phase A: Canonical Description (one approval gate)

**Before writing anything:** Read `references/voice-tone.md` in full.
Do NOT read any other reference files at this stage. Only voice-tone.md.

Generate a single canonical description for the watch. This is the full,
Tier-appropriate prose that all platforms derive from. It is NOT platform-specific
yet — no character substitutions, no platform formatting, no titles.

The canonical description contains:
- **Title line**: SEO-optimized, 80 chars max, no reference number
- **Descriptive paragraph**: ONE paragraph. Horological significance, technical
  detail, why this reference and why this example. Confidence-tier language.
  This is the only prose paragraph.
- **Condition sentence**: ONE sentence only. Condition + completeness + provenance.
  Example: "Excellent condition, full set with original box and papers dated June 2023."
- **Key Details line**: pipe-separated spec summary
- **Grailzee paragraph** (if not skipped): one emotional paragraph, no specs

Send to Telegram:
```
CANONICAL DESCRIPTION

Title: [title]

[one descriptive paragraph]

[one condition sentence]

Key Details: [Watch + Papers | Excellent | 41mm Steel | ...]

Grailzee: [one emotional paragraph]

Reply APPROVE or tell me what to change.
```

Save checkpoint immediately after approval. The checkpoint MUST include the
full approved canonical text in the draft so Phase B can reference it without
regenerating. Save as:
```json
{
  "step": 3,
  "phase": "A_complete",
  "canonical": {
    "title": "[approved title]",
    "paragraph_1": "[approved paragraph 1]",
    "paragraph_2": "[approved paragraph 2]",
    "key_details": "[pipe-separated key details line]",
    "grailzee": "[approved grailzee paragraph or null]"
  }
}
```
Do not proceed to Phase B until this checkpoint is saved and validated.

#### Phase B: Platform Derivations (one platform per turn)

Once the canonical description is approved, derive platform versions one at a
time. Each derivation is ONE turn: derive → append to .md file → update
`_draft.json` → move to next. No approval gates. No buffering.

**Critical: write to the .md file after EACH platform, do not buffer.**

Platform order and derivation rules:
1. **eBay**: Full canonical paragraphs + What's Included + Vardalux block + Item Specifics → write to .md → save draft
2. **Chrono24**: Paragraph 1 only (condition moves to Condition Notes section) → write to .md → save draft
3. **Facebook Retail**: Full paragraphs with character substitutions applied + payment block → write to .md → save draft
4. **Facebook Wholesale**: Key Details only + payment block (no paragraphs) → write to .md → save draft
5. **Value Your Watch**: 1-2 sentences from P1 + full paragraphs + specs → write to .md → save draft
6. **Instagram**: 1-2 sentences from P1 only, no price, "Tell Me More" CTA → write to .md → save draft
7. **Reddit** (if applicable): Expand P1+P2 to full Reddit format with specs bullets → write to .md → save draft
8. **WTA Dealer Chat** (if applicable): Structured data only, no prose → write to .md → save draft
9. **Grailzee** (if not skipped): Grailzee paragraph only → write to .md → save draft

After each platform is written to the .md and saved to `_draft.json`, immediately
move to the next platform in the same session if context allows. If context is
running long, stop after saving and resume in the next turn.

**Resume logic:** If `_draft.json` has `step: 3`:
- If `phase` is `A` or missing, or `canonical` is absent from the draft: run Phase A
- If `phase` is `A_complete` or `B`, AND `canonical` is present in the draft:
  - Skip Phase A entirely — do NOT regenerate the canonical
  - Read `draft.canonical` for the approved text
  - Check `platforms_done` list and resume from the first platform NOT in it
  - The .md file will already have completed platforms — append only

#### Voice and Tone (All Prose, All Platforms)

**All voice, tone, tier, and hard rules are in `references/voice-tone.md`.**
Read that file at the start of Phase A. Do not skip it.

<!-- Summary only below — full rules in references/voice-tone.md -->

**The Ogilvy Standard governs all listing copy.** "The consumer isn't a moron.
She's your wife." Respect the reader's intelligence. Facts persuade more than
adjectives. The product is the hero, not the writer. Every sentence earns its
place. Thoughts connect and build into each other. Never staccato rhythms, never
tagline-as-headline tricks, never motivational-poster energy. Specificity over
superlatives. The writing should read like someone explaining how they think
about a watch, not performing expertise or selling.

**The Voss Standard shapes how listings address buyer psychology.** Label the
buyer's likely concerns rather than ignoring them. Build trust before price.
Write with calm authority (the late-night FM DJ voice in written form): no
urgency language, no exclamation marks, no desperation. "Let me know if this
works" reads differently than "Don't miss this!"

**Knowledge vs. Confidence:** Every description should sound like it comes from
someone who has handled the watch, not someone who read the spec sheet. Knowledge
tier is "this has a column-wheel chronograph" (anyone can Google that). Confidence
tier is "the column-wheel gives the pushers a tactile click you feel every single
time" (comes from wearing the watch). Buyers hear the difference instantly. Always
prefer confidence-tier language when Ranbir's direct experience is available.

Rules:
- No stacking short punchy lines that read like ad copy
- Write like a real person talking to a smart friend over coffee
- Avoid "buy" in philosophical copy (use "acquire," "move wealth," "deploy capital")
- Specificity is the proof: name the caliber, describe the finishing, reference the function
- Vague superlatives ("stunning," "incredible," "amazing") are banned
- Strong lines go at the opening, not buried at the end
- Every sentence should do work. If it could be deleted without losing anything, delete it

#### Description Rules (All Tiers)

- Lead with function and beauty, not specs
- No em-dashes (use colons, periods, commas)
- No bullet points in prose
- No competitor callouts
- No "Mint" condition language. Only Excellent, Very Good, Good
- No MSRP unless the user explicitly requests it
- No condition language in Grailzee descriptions
- Grailzee descriptions are purely emotional/story-driven, one paragraph
- Include "service history unknown but running accurately" when service history is not known
- Never be uniformly enthusiastic. Honest assessment, including what a piece does
  not do well or who it is not for, is the advisor voice. The server says everything
  is amazing. The advisor offers genuine comparables and lets the buyer decide
- Every description should map to at least one Product Knowledge metric:
  **Product** (how good is it, honest comparables), **Safety** (transaction trust,
  process confidence), or **Value** (cost of ownership, depreciation reality).
  If it maps to none, it is filler

#### Tier 1 Description (Entry to Luxury)

3-4 sentences total. Two paragraphs:
- Paragraph 1: Why this reference is respected + key technical features
- Paragraph 2: This specific example's condition and completeness

Tone: Educational, trust-building, reassuring. Emphasize verification, warranty,
and transparency.

#### Tier 2/3 Description (Functioning Luxury / Exclusivity)

4-6 sentences total. Two paragraphs:
- Paragraph 1: Horological significance, technical detail, what makes it special
- Paragraph 2: This example's condition, provenance, completeness

Tone: Competence-focused. For Tier 3, add mystery and intrigue.

#### Chrono24 Description Adjustment

Chrono24 has a dedicated "Condition Notes" section. The description's second
paragraph should focus ONLY on completeness, provenance, and service history.
Do NOT put condition language in the description paragraph.

#### Grailzee Description (All Tiers)

One paragraph. Emotionally driven. No specs, no condition, no reference number.
Pure story and pull. Write it like you're telling a friend why this piece matters.

#### WTA Dealer Chat (No Description)

Structured data only: year, reference, completeness, condition notes, diameter,
payment methods. No prose, no storytelling, no marketing copy.

#### Reddit r/watchexchange Description

Richest prose of any platform: two full paragraphs weaving technical detail
into story. Paragraph 1: What this reference is and why it matters. Paragraph 2:
The movement and its characteristics. After the prose, include structured Specs
section (bullet points are standard on Reddit), Condition and Completeness,
Price, About Us, and photo/timestamp links.

Include MSRP in specs when known. Include "Trades considered" ONLY when user
explicitly requests it.

All platform copy derives from the canonical description approved in Phase A.
Do not rewrite prose for individual platforms — shorten and reformat only.

### Step 3.5: GRAILZEE RECOMMENDATION GATE

After descriptions are approved and before generating the full document, run
a Grailzee pricing validation.

1. Pull Grailzee pricing recommendation or median data for the reference
   (via web search or the OpenClaw browser tool)
2. Send recommendation summary to Telegram showing:
   - Grailzee median for this reference
   - Suggested reserve or NR recommendation based on the data
   - How the current pricing compares to the median
3. "Reply PROCEED to continue with current pricing, or ADJUST to change."

If Ranbir replies ADJUST: return to Step 2 with Grailzee data pre-loaded as
context. Re-run pricing calculations and re-approve.

If Ranbir replies PROCEED: continue to Step 4.

**If Grailzee data is unavailable:** Send a note explaining the data could not
be retrieved. "Reply PROCEED ANYWAY or I'LL CHECK MANUALLY."

If Ranbir replies I'll check manually: wait for updated pricing info or a
proceed signal.

Save checkpoint (step: 3.5) after gate resolution.

### Step 4: GENERATE PDF

Once all prior steps are approved and the Grailzee gate is resolved, generate
the complete listing document.

Read reference files lazily — only when needed for that platform:
- `references/character-substitutions.md` — only when writing Facebook platforms
- `references/platform-templates.md` — only at Step 4 final assembly
- `references/posting-checklist.md` — only at Step 4 checklist generation
Do NOT read all reference files upfront.

The document contains these sections in order:

1. **Internal Reference** (condition summary, key specs, selling points) marked "DO NOT POST"
2. **Pricing Summary** table
3. **Grailzee Listing** (if not skipped)
4. **eBay Listing** (title, pricing, condition field, full description, What's Included, Vardalux block, Item Specifics)
5. **Chrono24 Listing** (title, reference, key details, description, scope of delivery, condition notes)
6. **Facebook Retail Listing** (with character substitutions applied)
7. **Facebook Wholesale Listing** (ultra-lean, key details only, if applicable)
8. **WTA Dealer Chat Listing** (structured data only, if applicable)
9. **Reddit r/watchexchange Listing** (rich prose + specs + condition, if applicable)
10. **Value Your Watch Listing** (title, short catchy description, full description, specs, condition)
11. **Instagram Post** (no pricing, "Tell Me More" CTA)
12. **Platform Posting Checklist** (auto-generated from price + brand)

**Output process:**

Note: By the time Step 4 runs, the `_Listing.md` file already exists and is
complete (written incrementally during Phase B). Step 4 only needs to:

1. Verify `_Listing.md` exists and all platforms are written
2. Update `_draft.json` (step: 4, pipeline_status: COMPLETE)
3. Generate the PDF via `exec`:
   ```
   python3 /Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/generate_listing_pdf.py "{absolute_path_to_listing_md}"
   ```
   Never use `cd &&`. Never call a local `generate_pdf.py`.
   Always use the full absolute path to both the script and the .md file.
4. Send confirmation to Telegram:
   "Done. PDF at: [full path to _Listing.pdf]"
5. Stop.

**If PDF generation fails:** Send an error to Telegram with the error output.
The `_Listing.md` and `_draft.json` are already saved, so the PDF can be
regenerated manually. Do not fail silently.

---

## Key Details Format

Key Details appear on eBay, Chrono24, Facebook (retail and wholesale).
One detail per line for clean rendering and easy copy-paste across platforms:

```
[Completeness]
[Condition]
[Case Material]
[Bezel]
[Dial]
[Movement/Caliber]
[Complications]
[Power Reserve]
[Strap/Bracelet]
[Special Features]
[Condition note]
```

Only include fields that are known. Do not pad with generic filler.
Each line should be a self-contained detail (e.g., "Watch + Papers",
"Excellent", "41mm Stainless Steel", "Blue Aluminum Unidirectional Bezel").

---

## Vardalux Trust Block (per platform)

**eBay:** "VARDALUX: We verify condition and functionality before listing. Every watch includes our 1-year movement warranty. Established 2021. Questions? Message us anytime."

**Chrono24:** Omit. Trust block lives in the seller profile.

**Facebook:** "We verify condition and functionality. Please review the photos. Includes our 1-year movement w@rranty." (with character substitutions)

**Value Your Watch:** "Established 2021. Based in Colorado. Fast, insured shipping."

**Instagram:** Omit.

**Grailzee:** Omit.

**WTA Dealer Chat:** Omit.

**Reddit:** "Vardalux Collections is a luxury timepiece dealer based in Colorado. We verify condition and functionality before listing and include a 1-year movement warranty on every watch. Established 2021. Positive references on eBay, Chrono24, Google, and across the watch community. Happy to connect via phone or video call."

---

## Facebook Character Substitutions

Apply to ALL Facebook listings (retail and wholesale). Purpose is algorithm
avoidance. Every brand name, payment term, and flagged word gets substituted.

Read `references/character-substitutions.md` for the complete substitution table
covering all brand names, model names, technical terms, payment terms, and
document terms. Apply substitutions to Key Details, description, and payment block.

**WTA Dealer Chat and Reddit do NOT use character substitutions.**

---

## Payment Block (Facebook Only)

```
W!re or Z3lle preferred (under $5K). USDT (crypto) and CC (+4.5% f33) available.
Ships fast from Colorado.
```

The CC fee is 4.5%. This is final.

No payment methods on eBay, Chrono24, Value Your Watch, or Instagram.

**Reddit payment methods** (clean text):
```
Payment via wire or Zelle. CC available (+4.5% fee).
```

**WTA Dealer Chat payment methods** (clean text):
```
Wire, Zelle, USDT, CC (+4.5% fee)
```

---

## Platform-Specific Notes

**eBay:**
- Title per SEO-optimized construction rules (80 char max, no reference in title)
- List price rounds to $49 or $99 ending
- Include Item Specifics section (reference number goes here)
- 🔎 emoji before "Key Details" (eBay only, not Chrono24)

**Chrono24:**
- Clean, professional, no emojis
- "Scope of Delivery" (not "What's Included")
- "Condition Notes" section with component breakdown
- No "About Vardalux" in listing body

**Facebook Retail:**
- "Offered at: $[price]" format
- 🔎 emoji before "Key Details"
- Character substitutions mandatory
- CTA: "DM if you're interested"

**Facebook Wholesale:**
- Ultra-lean: Key Details + photos + payment block only
- No description paragraphs
- CTA: "DM if you're interested"

**WTA Dealer Chat:**
- Structured data only: Year, Reference, Completeness, Condition Notes, Diameter, Payment
- No emojis, no storytelling, no Key Details format
- No character substitutions
- Price must be ≤ 10% below lowest US C24/eBay dealer comp
- Cannot be listed for lower anywhere else
- No "About Vardalux" or trust blocks

**Reddit r/watchexchange:**
- Title format: `[WTS] Brand Model Key Feature – Size Material – Ref Number`
- Richest prose of any platform
- Specs section uses bullet points (standard on Reddit)
- Include MSRP in specs when known
- "About Us" block uses "dealer" positioning
- Include "Trades considered" ONLY when user specifies
- Timestamp photo required (added at time of posting)
- No character substitutions, no emojis in prose
- Payment: wire, Zelle, CC (+4.5% fee)
- "Shipped, fully insured" included with price

**Value Your Watch:**
- Short Catchy Description (2-3 sentences) appears in search results
- Full specifications section required
- "Why Vardalux" section

**Instagram:**
- No pricing. Ever.
- Status: AVAILABLE / PENDING SALE / SOLD
- 1-2 sentences max on design and significance
- CTA: "Tell Me More to inquire"

**Grailzee:**
- One emotional paragraph. No specs. No condition.
- Branded account = no-reserve format only
- No pricing in the description

---

## Absolute Do Nots

These rules apply to every listing, every platform, every tier. No exceptions.

**Brand:** Never suggest Grand Seiko. Never use "Mint." Never use em-dashes.
Never use "mistakes" language.

**Positioning:** Never position as a commodity flipper or margin grinder. Never
let trading activity stand alone without the strategic thinking behind it. Never
be transactional ("Buy now!" / "Limited time!" / "DM for price!"). Never use
servant language ("Let me find that for you" / "What can I help you with?").
Never chase.

**Voice:** Never be uniformly enthusiastic about every product. Never write
knowledge-tier content when confidence-tier is available. Never use staccato
rhythms, tagline-as-headline tricks, or motivational-poster energy. Never
restyle Ranbir's own rewrites: tighten and preserve. In philosophical copy,
never use "buy": use "acquire," "move wealth," "deploy capital." ("Buy" is
fine in transactional contexts like Facebook listings and Grailzee descriptions.)

**Content:** Never use bullet points in prose descriptions (Reddit specs section
is the one exception: bullet points are standard and expected there). Never
mention MSRP unless explicitly requested. Never assume gender. No AI tells:
"delve," excessive hedging, flowery repetition.

**Listing workflow:** Never generate without photo review first. Never combine
pricing and description approval steps. They are separate gates.

---

## Reference Files

Read these before generating the full document in Step 4:

- `references/voice-tone.md` — Read at start of Phase A only
- `references/character-substitutions.md` — Read only when writing Facebook platforms
- `references/platform-templates.md` — Read only at Step 4 final assembly
- `references/posting-checklist.md` — Read only at Step 4 checklist generation

Read lazily. Never load all reference files at once.

These reference files are aligned to The Vardalux Way v1.3 (March 2026). If any
conflict exists between these files and The Way, The Way takes precedence.

---

## OpenClaw Configuration Notes

These are operational notes for maintaining the OpenClaw installation. Not part
of the listing logic, but critical for the skill to function.

**Telegram:** All messages and approvals go to Telegram. No Slack integration.
No Block Kit. Ranbir replies with plain text and the agent parses intent.

**Bot token:** Must be present in `~/.openclaw/openclaw.json`. Verify on startup.
If the token is missing or invalid, post a diagnostic error and halt.

**After any `openclaw.json` edit:** Run `openclaw gateway restart` then
`openclaw tui` to apply changes. The gateway does not hot-reload config.

**Never edit `openclaw.json` with TextEdit.** TextEdit saves as RTF and breaks
JSON parsing. Use `nano`, `vim`, or `code` (VS Code) only.

**Pipeline symlink:** `~/.openclaw/workspace/pipeline` must point to the Google
Drive path: `/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Photo Pipeline`. If the symlink is broken
(Google Drive not mounted, path changed), the pipeline cannot find listing folders.

**Boot skill:** `~/.openclaw/workspace/boot.md` is loaded on every OpenClaw
startup. Any global instructions or personality directives go there.

**PDF tool:** The centralized PDF generation script lives at:
```
/Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/generate_listing_pdf.py
```
Uses ReportLab. Called via `exec` with the absolute path to both the script and
the input Markdown file. Never `cd` into the listing folder. Never call a local
copy. If the script is missing or the path is wrong, Step 4 will save
`_draft.json` and `_Listing.md` but cannot produce the PDF. Send the error to
Telegram so it can be resolved.

**Browser tool:** WatchTrack access uses the OpenClaw native browser tool
(`action: navigate`, `profile: openclaw`). Never use Peekaboo. The browser
session persists authentication, so no login is needed.

