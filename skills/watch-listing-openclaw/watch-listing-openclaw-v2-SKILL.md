---
name: watch-listing-openclaw
description: >
  Generate multi-platform watch listings for Vardalux Collections via Slack,
  following the mandatory approval workflow with Block Kit interactive buttons.
  Use this skill whenever the user wants to create a watch listing, list a watch
  for sale, build a listing document, write a Grailzee description, or mentions
  listing a specific watch reference. Also trigger when the user says "list this",
  "build a listing", "write the listing", "Grailzee description", "WTA listing",
  "dealer chat", "Reddit listing", "watchexchange", or references any watch
  brand/model in the context of selling or listing. Trigger when a listing folder
  is detected in the pipeline (format: {internalRef}-{modelRef}/). This skill
  handles all platforms: Grailzee, eBay, Chrono24, Facebook (retail and wholesale),
  WTA Dealer Chat, Reddit r/watchexchange, Value Your Watch, and Instagram.
---

# Watch Listing Generator — Vardalux Collections (OpenClaw / Slack v2)

## Purpose

Generate complete, copy-paste-ready watch listings across all sales platforms
following Vardalux brand standards. This is the OpenClaw version of the skill,
designed for Telegram-based interaction using inline buttons for approvals and
selections. Output is a PDF generated via ReportLab, saved into the listing
folder alongside the photos.

A parallel Claude Chat version of this skill exists for use in claude.ai sessions.
Both versions share identical business logic, pricing formulas, voice standards,
and platform rules. Only the interaction model, tool layer, and output format differ.

**Approval platform: Telegram (chat ID: 8712103657).** All step approvals,
button selections, and interactive prompts go to Telegram. Slack (channel
`C0APPJX0FGC`) is used only for completed listing notifications and status
posts — never for approvals or mid-pipeline interaction.

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
| Brand subfolders | `Rolex/` `Tudor/` `Omega/` `Cartier/` `IWC/` `Breitling/` |

Listing folders follow the naming convention `{internalRef}-{modelRef}/`.
Examples: `164WU-IW371446-1/` | `14618-M28500-0003/`

Each listing folder contains:
- Numbered PNG files (photos)
- `_draft.json` (state checkpoint, created and updated by this pipeline)
- `_Listing.pdf` (final output, generated into same folder by `generate_pdf.py`)

### Slack Configuration (Notifications Only)

| Setting | Value |
|---------|-------|
| Channel ID | `C0APPJX0FGC` |
| Workspace ID | `T087DH94JL8` (Rnvi LLC) |
| Slack App ID | `A0APYTD0BDX` |

**Slack is used for completed listing notifications only.** Post to `C0APPJX0FGC`
when a listing is fully generated (Step 4 complete). Do not post approvals,
button prompts, or mid-pipeline updates to Slack.

### Telegram Interaction Model

**All approvals and interactive selections go to Telegram (chat ID: 8712103657).**

Use inline buttons for all structured choices. Never poll for free-text replies
when a button selection is appropriate.

**Button interactions (never free-text):**
- Condition selection: `BNIB` / `Excellent` / `Very Good` / `Good` / `Other`
- Tier selection: `Tier 1` / `Tier 2` / `Tier 3`
- Grailzee format: `No Reserve` / `Reserve` / `Skip`
- Step approvals: `Approve` / `Request Changes`
- WatchTrack confirmation: `Looks Good` / `Correct This`
- Grailzee gate: `Proceed with Current Pricing` / `Adjust Pricing`
- Pipeline start: `▶️ Start Listing` / `⏭ Skip`

**Free-text inputs (pricing only — sent as Telegram messages):**
- `retail_net`, `wholesale_net`, `wta_price`, `wta_comp`, `reddit_price`, `msrp`
- `buffer` (if non-default)

Include a brief context line above each button group explaining what is being
decided. After a button is tapped, send a confirmation message acknowledging
the selection before proceeding to the next step.

### Image Review

To review photos, read the image files from the listing folder using the `read`
tool. Examine each image and evaluate against the photo review criteria in
Step 1. Post the review summary to Telegram (chat ID: 8712103657).

---

## Expected Inputs

Inputs arrive via Slack messages or button selections. Some may arrive across
multiple messages. The pipeline collects inputs progressively across steps.

**From folder name (parsed automatically):**
- `internal_ref` — Internal reference ID (first segment before hyphen)
- `model_ref` — Model reference number (remaining segments)

**From WatchTrack lookup (Step 0, automatic):**
- `brand`, `model`, `reference`, `year`, `case_size`, `case_material`
- `movement`, `cost_basis`, `recent_comps`, `serial`

**From button selections:**
- `condition` — Overall condition rating (BNIB / Excellent / Very Good / Good / Other)
- `tier` — Buyer tier (1, 2, or 3)
- `grailzee_format` — Auction format (NR / Reserve / Skip)

**From free-text Slack messages:**
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

On startup, if a `_draft.json` exists in the target listing folder:

1. Read the checkpoint
2. Post to Telegram (chat ID: 8712103657): "Found an in-progress listing for
   [brand] [model]. Last completed step: [step name]."
3. Send Telegram inline buttons: `Resume from Step [N+1]` / `Start Over`
4. If resume, load all saved inputs and approved outputs, continue from next step
5. If start over, archive the old draft as `_draft.json.bak` and begin fresh

---

## The Pipeline Workflow

```
WATCHTRACK ──confirm──▶ PHOTOS ──approve──▶ PRICING ──approve──▶ DESCRIPTIONS ──approve──▶ GRAILZEE GATE ──confirm──▶ GENERATE PDF ──▶ WATCHTRACK STATUS
     Step 0                Step 1              Step 2               Step 3                  Step 3.5                   Step 4             Step 5
```

Hard approval gates at every step. Never skip steps. Never combine steps.

### Step 0: WATCHTRACK LOOKUP

Runs automatically when a listing folder is detected or the user initiates a
listing by referencing a folder name.

1. Parse the folder name to extract `internal_ref` and `model_ref`
2. Use your native browser tool to navigate to the URL. Do not use Playwright, Puppeteer, or any CLI. Just use the browser tool directly.
   The user is already logged into WatchTrack in that Chrome session. Do not
   attempt to authenticate.
3. Navigate to https://watchtrack.com/store/home and look up the reference number
4. Extract: serial data, cost basis, recent sold comps, condition notes if present.
   Also extract `retail_net` and `wholesale_net` from their dedicated fields.
   **Always capture the Notes field verbatim, regardless of whether price fields
   are populated.** If Notes contains pricing language (e.g. "Retail NET $5,411"
   or "List at $5,850"), surface it alongside the price fields in the summary
   and flag it as "(from Notes field)" so the user can decide which value to use.
   Never silently prefer one source over the other — show both.
5. Save extracted data into `_draft.json` (step: 0)
6. Post a summary of findings to Telegram (chat ID: 8712103657) with buttons:
   `Looks Good` / `Correct This`

If the user taps `Correct This`, prompt for the specific field corrections
via Telegram message, update `_draft.json`, and re-confirm.

**If WatchTrack lookup fails or returns no data:** Post a warning to Telegram
and continue to Step 1. Do not block the pipeline. The user can provide missing
data manually.

After confirmation, save checkpoint and proceed to Step 1.

### Step 1: PHOTOS

Read every image in the listing folder using the `read` tool.

Post to Telegram (chat ID: 8712103657) at least one full paragraph of feedback covering:
- What is working well (composition, lighting, angles covered)
- What is missing or could be improved
- Whether the photos are sufficient to list (yes/no with reasoning)
- Any condition details visible in photos that conflict with WatchTrack data
  or provided condition notes

Then send Telegram inline buttons: `Approve` / `Request Changes`

If `Request Changes`: address the feedback, re-review if new photos are added,
and re-present the buttons.

Do NOT proceed until `Approve` is tapped. If the folder is empty, stop entirely.

After approval, prompt for any missing inputs needed for Step 2 via Telegram:
- Send condition buttons: `BNIB` / `Excellent` / `Very Good` / `Good` / `Other`
- Send tier buttons: `Tier 1` / `Tier 2` / `Tier 3`
- Send Grailzee format buttons: `No Reserve` / `Reserve` / `Skip`
- Request free-text via Telegram message: retail_net (and optionally wholesale_net,
  wta_price/comp, reddit_price, buffer if non-default)

Save checkpoint (step: 1) after photo approval.

### Step 2: PRICING

Calculate platform-specific pricing using the formulas below. Post the pricing
table to Telegram (chat ID: 8712103657).

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

Post the pricing table to Telegram (chat ID: 8712103657):

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

Then send Telegram inline buttons: `Approve` / `Request Changes`

Save checkpoint (step: 2) after pricing approval.

### Step 3: DESCRIPTIONS

Write listing descriptions based on the tier. Post all descriptions to
Telegram (chat ID: 8712103657) for approval. WTA does not require description approval
(structured data only, auto-generated from condition input).

#### Voice and Tone (All Prose, All Platforms)

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

Post all descriptions to Telegram (chat ID: 8712103657), then send inline buttons:
`Approve` / `Request Changes`

Save checkpoint (step: 3) after description approval.

### Step 3.5: GRAILZEE RECOMMENDATION GATE

After descriptions are approved and before generating the full document, run
a Grailzee pricing validation.

1. Call the Grailzee deal evaluator via exec:

```bash
python3 ~/.openclaw/workspace/skills/grailzee-eval/scripts/evaluate_deal.py \
  "[brand]" "[reference]" [purchase_price]
```

   Reads from `GrailzeeData/state/analysis_cache.json`. Sub-second response.
   Returns JSON with fields: `grailzee`, `format`, `reserve_price`, `ad_budget`,
   `rationale`, `metrics`.

2. Parse the JSON response and post to Telegram (chat ID: 8712103657):

```
📊 Grailzee Recommendation — [Brand] [Reference]

Decision: [YES — No Reserve / YES — Reserve at $X,XXX / NO]
Ad budget: [ad_budget]
[rationale]

Median: $X,XXX | Max buy: $X,XXX | Signal: [signal]
```

3. Send Telegram inline buttons: `Proceed with Current Pricing` / `Adjust Pricing`

If `Adjust Pricing`: return to Step 2 with Grailzee data pre-loaded as context.
Re-run pricing calculations and re-approve.

If `Proceed with Current Pricing`: continue to Step 4.

**If the evaluator returns `grailzee: "NO"`:** Make this clear in the Telegram
post. The listing can still proceed — Grailzee simply won't be included.
Send buttons: `Proceed Without Grailzee` / `Override — List Anyway`

**If the script errors or cache is missing:** Post a note to Telegram explaining
the cache may be stale or the analyzer hasn't been run yet. Send buttons:
`Proceed Anyway` / `I'll Check Manually`

If `I'll Check Manually`: wait for the user to send updated info via Telegram
or tap `Proceed Anyway` when ready.

Save checkpoint (step: 3.5) after gate resolution.

### Step 4: GENERATE PDF

Once all prior steps are approved and the Grailzee gate is resolved, generate
the complete listing document.

Read these reference files before generating:
- `references/platform-templates.md` for exact copy-paste template structures
- `references/posting-checklist.md` for platform posting checklist logic
- `references/character-substitutions.md` for the complete Facebook substitution table

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

1. Assemble all approved content into a structured data object
2. Save the final object as `_draft.json` in the listing folder (step: 4,
   overwriting the previous draft with complete approved content)
3. Call `generate_pdf.py` (ReportLab-based script located in the listing folder)
   via `exec` tool
4. The script generates `_Listing.pdf` in the same listing folder
5. **Delete `generate_pdf.py` from the listing folder** immediately after PDF
   is confirmed generated. Do not skip this step. The script must not remain
   in the listing folder after use.
6. Post confirmation to Telegram (chat ID: 8712103657):
   *"✅ Listing PDF generated: [brand] [model] — ready for the team to execute."*
7. Post notification to Slack (`C0APPJX0FGC`):
   *"✅ Listing complete: [brand] [model] ([internal_ref]) — PDF ready."*

**If `generate_pdf.py` is not found in the listing folder:** Post an error to
Telegram and save the `_draft.json` so the PDF can be generated manually.
Do not fail silently.

### Step 5: WATCHTRACK SUB STATUS UPDATE

⚠️ **This step is handled by the main OpenClaw agent — NOT by Claude Code.**

Claude Code does not have access to the OpenClaw browser tool. When Step 4 is
complete, post to Telegram (chat ID: 8712103657):

*"✅ PDF complete: [brand] [model] ([internal_ref]) — ready for WatchTrack update."*

The main OpenClaw agent will handle the WatchTrack sub-status update using the
`openclaw browser` CLI and the watchtrack skill. Do not attempt browser
navigation from this session.

---

## Key Details Format

The pipe-separated Key Details line appears on multiple platforms:

```
| [Completeness] | [Condition] | [Case Material] | [Bezel] | [Dial] |
[Movement/Caliber] | [Complications] | [Power Reserve] | [Strap/Bracelet] |
[Special Features] | [Condition note] |
```

Only include fields that are known. Do not pad with generic filler.

---

## Vardalux Trust Block (per platform)

**eBay:** "VARDALUX: We verify condition and functionality before listing. Every watch includes our 1-year movement warranty. Established 2021. Questions? Message us anytime."

**Chrono24:** Omit. Trust block lives in the seller profile.

**Facebook:** "We verify condition and functionality. Please review the photos. Includes our 1-year movement warranty."

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
- Title max 80 characters: `[Brand] [Model] [Key Feature] | Ref [Reference] | [Size]mm`
- List price rounds to $49 or $99 ending
- Include Item Specifics section
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
- No emojis, no storytelling, no Key Details pipe format
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

- `references/platform-templates.md` — Exact copy-paste template structures for
  every platform, condition language reference, and complete examples
- `references/posting-checklist.md` — Platform posting checklist auto-generation
  logic (universal, price-based, brand-specific, and optional platform routing)
- `references/character-substitutions.md` — Complete Facebook character substitution
  table covering brand names, model names, technical terms, payment terms, and
  document terms

These reference files are aligned to The Vardalux Way v1.3 (March 2026). If any
conflict exists between these files and The Way, The Way takes precedence.

---

## OpenClaw Configuration Notes

These are operational notes for maintaining the OpenClaw installation. Not part
of the listing logic, but critical for the skill to function.

**Channel ID:** All Slack API calls must use `C0APPJX0FGC`, never a channel name
string. This includes `chat.postMessage`, `chat.update`, and `block_actions`
event listeners.

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

**generate_pdf.py:** Uses ReportLab. Must be present in each listing folder
before Step 4 runs. If missing, Step 4 will save `_draft.json` but cannot
produce the PDF. The team must copy the script into the folder and run manually,
or install it globally and symlink.
