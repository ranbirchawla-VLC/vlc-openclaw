# Vardalux Voice & Tone — Listing Copy Standards

**Read this file before writing any description.**

---

## The Two Governing Frameworks

**The Ogilvy Standard** governs all writing: respect the reader's intelligence,
facts over adjectives, the product is the hero, every sentence earns its place,
research before writing, big ideas over clever tricks, tell the truth.
Specificity over superlatives. "The consumer isn't a moron. She's your wife."

**The Voss Standard** governs persuasion: tactical empathy, labeling buyer
concerns, calm authority (late-night FM DJ voice), no urgency language, no
exclamation marks, no desperation. Build trust before price.

**Knowledge vs. Confidence tier:** Knowledge is "this has a column-wheel
chronograph" (anyone can Google that). Confidence is "the column-wheel gives
the pushers a tactile click you feel every single time" (comes from wearing it).
Always write at confidence tier when Ranbir's direct experience is available.

---

## Hard Rules (No Exceptions)

- No em-dashes. Use colons, periods, commas.
- No bullet points in prose. (Reddit specs section is the one exception.)
- No "Mint" — only Excellent, Very Good, Good.
- No MSRP unless explicitly requested.
- No competitor callouts.
- No uniformly enthusiastic tone. Honest assessment including what a piece doesn't do well.
- No staccato rhythms or tagline-as-headline tricks.
- No motivational-poster energy.
- No AI tells: "delve", excessive hedging, flowery repetition.
- No "buy" in philosophical copy — use "acquire", "move wealth", "deploy capital".
  ("Buy" is fine in transactional contexts like Facebook and Grailzee.)
- Never suggest Grand Seiko.
- Never use "mistakes" language.
- Every sentence must do work. If it can be deleted without losing anything, delete it.
- Strong lines go at the opening, not buried.
- Specificity is the proof: name the caliber, describe the finishing, reference the function.
- Vague superlatives ("stunning", "incredible", "amazing") are banned.

---

## Tier Rules

All tiers use the same canonical structure: one descriptive paragraph + one
condition sentence. Tier affects tone and depth, not structure.

### Tier 1 (Entry to Luxury)
Descriptive paragraph: 3–4 sentences. Why this reference is respected, key
technical features, what the buyer is getting.
Condition sentence: Straightforward. Condition + completeness.
Tone: Educational, trust-building, reassuring. Verification and transparency.

### Tier 2/3 (Functioning Luxury / Exclusivity)
Descriptive paragraph: 4–5 sentences. Horological significance, technical
detail, what makes it special, why this example specifically.
Condition sentence: Confident. Condition + completeness + provenance if notable.
Tone: Competence-focused. Tier 3: note of rarity or exclusivity — never
hype, just honest scarcity. The watch speaks; the writer steps back.

---

## Platform-Specific Voice Notes

These apply when run_phase_b.py derives platform listings from the canonical.
They are recorded here so the canonical is written with downstream use in mind.

**Chrono24:** Condition Notes is a separate section — do NOT put condition
language in the description paragraph. The description paragraph covers
horological significance and completeness only.

**Grailzee:** One paragraph. Purely emotional. No specs, no condition, no
reference number. Write like you're telling a friend why this piece matters.

**Reddit:** Richest prose. The canonical paragraph is expanded into two full
paragraphs: P1 covers what the reference is and why it matters; P2 covers the
movement and its characteristics. Write the canonical with this expansion in mind.

**WTA Dealer Chat:** No prose at all. Structured data only. The canonical
description is not used on WTA.

---

## What This Skill Writes

Three fields only. Everything else is derived downstream by run_phase_b.py.

1. **Descriptive paragraph** — One paragraph. Horological significance, technical
   detail, what makes this reference worth owning, and why this specific example
   is the right one. Confidence-tier language throughout. No condition language.
   No price or value language. If service history is unknown, include:
   "service history unknown but running accurately."

2. **Condition sentence** — One sentence only. Condition rating + completeness
   + provenance if notable. Example: "Excellent condition, full set with original
   box, papers dated June 2023, and extra links in sealed bag."
   - BNIB: "Brand new in box, never worn, full set with factory stickers."
   - Other: write what inputs.condition_detail says, verbatim rating from detail notes.

3. **Grailzee paragraph** (null when grailzee_format is skip) — One paragraph.
   Emotionally driven. No specs, no condition, no reference number. Pure story.

**The two-paragraph format is dead. One descriptive paragraph + one condition
sentence. That is the canonical. Everything else derives from it.**

Once approved, all platform versions are derived mechanically from these elements.
No new prose is written in the downstream phase — only shortening, reformatting,
character substitution, and platform template insertion.
