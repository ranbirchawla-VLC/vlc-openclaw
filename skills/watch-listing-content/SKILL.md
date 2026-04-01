---
name: watch-listing-content
description: >
  Single source of truth for Vardalux Collections watch listing content: voice
  standards, description rules by tier, pricing formulas for all platforms,
  platform-specific templates, character substitutions, trust blocks, payment
  blocks, condition language, and posting checklist logic. This skill contains
  NO workflow, orchestration, or interaction logic. It is a pure content
  knowledge base referenced by orchestrators (OpenClaw pipeline, Claude Chat)
  when generating listings. Trigger this skill whenever generating listing
  descriptions, calculating platform pricing, applying character substitutions,
  building posting checklists, or reviewing listing copy against Vardalux
  standards. Also trigger for "what's the eBay pricing formula", "write a
  Grailzee description", "what platforms does this go to", "check the voice
  rules", or any question about how listings should read, look, or be priced.
---

# Watch Listing Content — Vardalux Collections

## Purpose

This is the content engine for Vardalux watch listings. It contains every
rule, formula, template, and standard needed to produce copy-paste-ready
listings across all 9 sales platforms. It does NOT contain workflow steps,
approval gates, Slack configuration, checkpoint systems, or PDF generation.
Those belong to the orchestrator that calls this skill.

Both the OpenClaw pipeline and the Claude Chat listing workflow reference
this skill for identical content output. One source of truth, two delivery
mechanisms.

---

## Identity Anchor

Vardalux are **dealers who transact with purpose**. Not commodity flippers or
margin grinders. Every transaction reflects the client's broader interests:
portfolio positioning, strategic access, and generational wealth building. The
thinking behind each deal is the differentiator, not the absence of deals.

**Profit for Acquisition:** Platform trading (Grailzee, eBay, Chrono24) serves
two purposes simultaneously: it generates margin and turns capital, and it is a
client acquisition channel. Every platform sale earns while introducing Vardalux
to someone who may become a long-term client. Listings are the first impression.
Presentation quality serves both purposes.

---

## Named Frameworks

**The Ogilvy Standard** governs all listing copy. "The consumer isn't a moron.
She's your wife." Respect the reader's intelligence. Facts persuade more than
adjectives. The product is the hero, not the writer. Every sentence earns its
place. Thoughts connect and build into each other. Never staccato rhythms, never
tagline-as-headline tricks, never motivational-poster energy. Specificity over
superlatives. The writing should read like someone explaining how they think
about a watch, not performing expertise or selling. Research before writing. Big
ideas over clever tricks. Tell the truth.

**The Voss Standard** shapes how listings address buyer psychology. Label the
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

---

## Voice Rules

- No stacking short punchy lines that read like ad copy
- Write like a real person talking to a smart friend over coffee
- Avoid "buy" in philosophical copy (use "acquire," "move wealth," "deploy capital").
  "Buy" is fine in transactional contexts like Facebook listings and Grailzee
- Specificity is the proof: name the caliber, describe the finishing, reference the function
- Vague superlatives ("stunning," "incredible," "amazing") are banned
- Strong lines go at the opening as hooks, not buried at the end
- Every sentence should do work. If it could be deleted without losing anything, delete it
- No em-dashes anywhere. Use colons, periods, commas
- No bullet points in prose descriptions (Reddit specs section is the one
  exception: bullet points are standard and expected there)
- No competitor callouts in descriptions
- No "Mint" condition language. Only Excellent, Very Good, Good
- No MSRP unless the user explicitly requests it (Reddit is the exception: MSRP is standard there)
- No condition language in Grailzee descriptions
- Include "service history unknown but running accurately" when service history is not known
- Never be uniformly enthusiastic. The server says everything is amazing.
  The advisor offers genuine comparables and lets the buyer decide

**P/S/V checkpoint:** Every description must map to at least one:
- **Product** (how good is it, honest comparables)
- **Safety** (transaction trust, process confidence)
- **Value** (cost of ownership, depreciation reality)

If it maps to none, it is filler. Delete it.

---

## Description Rules by Tier

### Tier 1 (Entry to Luxury)

3-4 sentences total. Two paragraphs:
- Paragraph 1: Why this reference is respected + key technical features
- Paragraph 2: This specific example's condition and completeness

Tone: Educational, trust-building, reassuring. Emphasize verification,
warranty, and transparency.

### Tier 2/3 (Functioning Luxury / Exclusivity)

4-6 sentences total. Two paragraphs:
- Paragraph 1: Horological significance, technical detail, what makes it special
- Paragraph 2: This example's condition, provenance, completeness

Tone: Competence-focused. For Tier 3, add mystery and intrigue.

### Chrono24 Description Adjustment

Chrono24 has a dedicated "Condition Notes" section. The description's second
paragraph should focus ONLY on completeness, provenance, and service history.
Do NOT put condition language in the description paragraph.

### Grailzee Description (All Tiers)

One paragraph. Emotionally driven. No specs, no condition, no reference number.
Pure story and pull. Write it like telling a friend why this piece matters.

### WTA Dealer Chat (No Description)

Structured data only: year, reference, completeness, condition notes, diameter,
payment methods. No prose, no storytelling, no marketing copy.

### Reddit r/watchexchange Description

Richest prose of any platform: two full paragraphs weaving technical detail
into story. Paragraph 1: What this reference is and why it matters. Paragraph 2:
The movement and its characteristics. After the prose, include structured Specs
section (bullet points standard on Reddit), Condition and Completeness, Price,
About Us, and photo/timestamp links.

---

## Pricing Formulas

### eBay

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

### Chrono24

```
buffered = retail_net × (1 + buffer/100)
list_price = buffered / (1 - 0.075)
Round to clean number (nearest $25 or $50)
```

### Facebook Retail

```
buffered = retail_net × (1 + buffer/100)
list_price = buffered
Round to clean number
```

### Facebook Wholesale (only if wholesale_net provided)

```
list_price = wholesale_net
Round to clean number
```

### WTA Dealer Chat (only if wta_price provided)

```
wta_comp = lowest US dealer comp from Chrono24 or eBay (whichever is lower)
max_allowed = wta_comp × 0.90   (absolute ceiling)
sweet_spot  = wta_comp × 0.80   (recommended range)

wta_price must be ≤ max_allowed

If wta_price > max_allowed:
  FLAG: Price exceeds WTA 10% below comp rule.
  Show: "WTA comp: $X,XXX → Max: $X,XXX → Your price: $X,XXX (OVER by $XXX)"
  Do NOT proceed with WTA listing.

If wta_price ≤ max_allowed but > sweet_spot:
  NOTE: Price is compliant but above the sweet spot.

If wta_price ≤ sweet_spot:
  Price is in the sweet spot for WTA.
```

**WTA Compliance Rule:** The watch cannot be listed for a lower price ANYWHERE
else on the internet or any other dealer chat.

### Reddit r/watchexchange (only if reddit_price provided)

```
list_price = reddit_price
No platform fees. No buffer calculation.
```

### Grailzee (if not skipped)

No pricing calculation needed for NR auctions (start at $1).
For Reserve: reserve_price is provided by user or set at Grailzee median +10-15%.

### Pricing Table Format

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

---

## Key Details Format

The pipe-separated Key Details line appears on eBay, Chrono24, Facebook
(retail and wholesale):

```
| [Completeness] | [Condition] | [Case Material] | [Bezel] | [Dial] |
[Movement/Caliber] | [Complications] | [Power Reserve] | [Strap/Bracelet] |
[Special Features] | [Condition note] |
```

Only include fields that are known. Do not pad with generic filler.

---

## Trust Blocks (per platform)

**eBay:** "VARDALUX: We verify condition and functionality before listing. Every
watch includes our 1-year movement warranty. Established 2021. Questions?
Message us anytime."

**Facebook:** "We verify condition and functionality. Please review the photos.
Includes our 1-year movement w@rranty." (with character substitutions)

**Value Your Watch:** "Established 2021. Based in Colorado. Fast, insured
shipping."

**Reddit:** "Vardalux Collections is a luxury timepiece dealer based in Colorado.
We verify condition and functionality before listing and include a 1-year
movement warranty on every watch. Established 2021. Positive references on eBay,
Chrono24, Google, and across the watch community. Happy to connect via phone or
video call."

**Chrono24, Grailzee, WTA, Instagram:** Omit.

---

## Payment Blocks (per platform)

**Facebook (retail and wholesale):**
```
W!re or Z3lle preferred (under $5K). USDT (crypto) and CC (+4.5% f33) available.
Ships fast from Colorado.
```

**Reddit:**
```
Payment via wire or Zelle. CC available (+4.5% fee).
```

**WTA Dealer Chat:**
```
Wire, Zelle, USDT, CC (+4.5% fee)
```

**eBay, Chrono24, Value Your Watch, Instagram:** No payment methods.

**The CC fee is 4.5%. This is final.**

---

## Platform-Specific Notes

**eBay:** Title max 80 chars. List price rounds to $49/$99 ending. Include Item
Specifics. Use "Key Details" emoji prefix only on eBay.

**Chrono24:** Clean, professional, no emojis. "Scope of Delivery" not "What's
Included." Separate "Condition Notes" section. No trust block in body.

**Facebook Retail:** "Offered at: $[price]" format. Character substitutions
mandatory. CTA: "DM if you're interested."

**Facebook Wholesale:** Ultra-lean. Key Details + payment block only. No
description paragraphs. Character substitutions mandatory.

**WTA Dealer Chat:** Structured data only. No emojis, no storytelling. No
character substitutions. Price must be at or below 10% below lowest US C24/eBay
dealer comp. Cannot be listed for lower anywhere else.

**Reddit r/watchexchange:** Title: `[WTS] Brand Model Feature – Size Material –
Ref Number`. Richest prose. Specs use bullet points. Include MSRP. "Dealer"
positioning in About Us. "Trades considered" ONLY when user requests. Timestamp
photo required. No character substitutions.

**Value Your Watch:** Short Catchy Description (2-3 sentences, appears in search
results). Full specs section. "Why Vardalux" section.

**Instagram:** No pricing. Ever. Status: AVAILABLE / PENDING SALE / SOLD. 1-2
sentences max. CTA: "Tell Me More to inquire." No trust block, no payment.

**Grailzee:** One emotional paragraph. Branded account = NR only. No pricing in
description. No specs, no condition. No trust block.

---

## Document Assembly Order

When the orchestrator requests the full listing document, assemble sections in
this order:

1. Internal Reference (DO NOT POST) — condition, specs, selling points, cost basis
2. Pricing Summary table
3. Grailzee Listing (if not skipped)
4. eBay Listing (title, pricing, condition field, description, What's Included,
   trust block, condition detail, Item Specifics)
5. Chrono24 Listing (title, reference, key details, description, scope of
   delivery, condition notes)
6. Facebook Retail Listing (with character substitutions applied)
7. Facebook Wholesale Listing (if applicable)
8. WTA Dealer Chat Listing (if applicable)
9. Reddit r/watchexchange Listing (if applicable)
10. Value Your Watch Listing
11. Instagram Post
12. Platform Posting Checklist

---

## Reference Files

These files live in `references/` within this skill folder. Read them
before generating the full listing document:

- `references/platform-templates.md` — Exact copy-paste template structures for
  every platform, condition language reference, and complete examples
- `references/posting-checklist.md` — Platform posting checklist auto-generation
  logic (universal, price-based, brand-specific, and optional platform routing)
- `references/character-substitutions.md` — Complete Facebook character substitution
  table covering all brand names, model names, technical terms, payment terms, and
  document terms

**Full paths (OpenClaw):**
```
~/.openclaw/workspace/skills/watch-listing-content/references/platform-templates.md
~/.openclaw/workspace/skills/watch-listing-content/references/character-substitutions.md
~/.openclaw/workspace/skills/watch-listing-content/references/posting-checklist.md
```

---

## Absolute Do Nots

**Brand:** Never suggest Grand Seiko. Never use "Mint." Never use em-dashes.
Never use "mistakes" language.

**Positioning:** Never position as a commodity flipper or margin grinder. Never
let trading activity stand alone without the strategic thinking behind it. Never
be transactional ("Buy now!" / "Limited time!" / "DM for price!"). Never use
servant language. Never chase.

**Voice:** Never be uniformly enthusiastic about every product. Never write
knowledge-tier content when confidence-tier is available. Never use staccato
rhythms, tagline-as-headline, or motivational-poster energy. Never restyle
Ranbir's own rewrites: tighten and preserve.

**Content:** Never use bullet points in prose descriptions (Reddit specs is the
one exception). Never mention MSRP unless explicitly requested (Reddit is the
exception). Never assume gender. No AI tells: "delve," excessive hedging,
flowery repetition.

**Listings:** Never generate without photo review first. Never combine pricing
and description approval steps.

---

*Aligned to The Vardalux Way v1.3 | March 2026*
*CC fee: 4.5% | Location: Colorado | Identity: Dealers who transact with purpose*
