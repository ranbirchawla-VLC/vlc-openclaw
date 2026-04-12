# Vardalux Voice & Tone — Listing Copy Standards

**Read this file before writing any description.** (v3 — updated 2026-04-12)

---

## The Two Governing Frameworks

**The Ogilvy Standard** governs all writing: respect the reader's intelligence,
facts over adjectives, the product is the hero, every sentence earns its place,
research before writing, big ideas over clever tricks, tell the truth.
Specificity over superlatives. "The consumer isn't a moron. She's your wife."

**The Voss Standard** governs persuasion: tactical empathy, labeling buyer
concerns, calm authority (late-night FM DJ voice), no urgency language, no
exclamation marks, no desperation. Build trust before price.

---

## The Advisor Standard

Listing copy is qualifying work at scale. It reads like one knowledgeable person
talking to another. The buyer who belongs in the conversation already understands
the significance of what is being named. The one who does not will not be
educated into a purchase by a paragraph.

**Advisor behavior:** Assume competence. Name things with authority. Move
immediately to why this piece and this example are worth attention.

**Servant behavior:** Explain what things are. Teach the reader. Over-describe
mechanisms. Unpack terminology. This is the default mode of most AI-generated
copy and it must be actively suppressed.

The distinction is not about brevity. It is about who the copy assumes the
reader to be. A Tier 2/3 buyer who sees "perpetual calendar, in-house calibre,
German finishing tradition" already knows why that matters at $15K versus the
Swiss alternatives at $60K+. Explaining what a perpetual calendar does writes
for the wrong buyer. It is the listing equivalent of a server describing every
ingredient on the menu to someone who eats there every week.

---

## Knowledge vs. Confidence Tier

Knowledge is "this has a column-wheel chronograph" (anyone can Google that).
Confidence is "the column-wheel gives the pushers a tactile click you feel
every single time" (comes from wearing it). Always write at confidence tier
when Ranbir's direct experience is available.

Knowledge tier treats the reader as someone being informed.
Confidence tier treats the reader as someone being spoken to by a peer.

The copy should read like a dealer who handles these regularly sharing a
considered view, not a researcher summarizing specifications.

---

## Hard Rules (No Exceptions)

### Complications, Movements, and Finishing

**Name them. Never explain them.** Do not describe what a complication does,
how a mechanism works, or why a finishing technique matters. Perpetual calendar,
annual calendar, tourbillon, minute repeater, split-seconds chronograph, GMT,
world time, flyback: name the complication and move on. Three-quarter plate,
côtes de Genève, perlage, hand-engraved balance cock, blued screws: name the
finishing and move on.

The buyer who needs the explanation is not the buyer for this piece. The buyer
who does not need it already knows what it means and is evaluating whether this
specific example deserves their capital.

Explaining complications is knowledge-tier writing by definition. It is servant
behavior. An advisor assumes the reader's competence.

### Provenance and Service History

No provenance, service history, or purchase source in buyer-facing copy. That
belongs in internal records only. Buyers interested in the watch will ask.
Never write "documented provenance," "fresh service," "purchased from X,"
"service life ahead," or anything that reads like a sales pitch for the paper
trail rather than the watch.

The condition sentence covers completeness. That is sufficient.

If service history is unknown, include in the descriptive paragraph:
"service history unknown but running accurately."

### Voice and Tone

- No em-dashes. Use colons, periods, commas.
- No bullet points in prose. (Reddit specs section is the one exception.)
- No "Mint" — only Excellent, Very Good, Good.
- No MSRP unless explicitly requested.
- No competitor callouts.
- No uniformly enthusiastic tone. Honest assessment including what a piece
  doesn't do well.
- No staccato rhythms or tagline-as-headline tricks.
- No motivational-poster energy.
- No AI tells: "delve", excessive hedging, flowery repetition.
- No "buy" in philosophical copy — use "acquire", "move wealth", "deploy
  capital". ("Buy" is fine in transactional contexts like Facebook and Grailzee.)
- Never suggest Grand Seiko.
- Never use "mistakes" language.
- Vague superlatives ("stunning", "incredible", "amazing", "beautiful",
  "exquisite") are banned. Specificity is the proof.
- Every sentence must do work. If it can be deleted without losing anything,
  delete it.
- Strong lines go at the opening, not buried.
- Name the caliber, the finishing, the complication, the material. Then stop.
  Do not follow with an explanation of what those things are or why they matter.

---

## Tier Rules

All tiers use the same canonical structure: one descriptive paragraph + one
condition sentence. Tier affects tone and depth, not structure.

### Tier 1 (Entry to Luxury)
Descriptive paragraph: 3–4 sentences. What this reference is, why it is
respected, what the buyer is getting. Name key technical features.
Condition sentence: Straightforward. Condition + completeness.
Tone: Educational, trust-building, reassuring. Verification and transparency.

### Tier 2/3 (Functioning Luxury / Exclusivity)
Descriptive paragraph: 4–5 sentences. Name the horological significance, the
movement, the finishing tradition, the complications. What makes this reference
worth owning and why this specific example.
Condition sentence: Confident. Condition + completeness only.
Tone: Competence-focused. Assumes the reader already understands the category.
Tier 3: a note of honest scarcity if applicable, never hype. The watch speaks;
the writer steps back.

---

## Platform-Specific Voice Notes

These apply when run_phase_b.py derives platform listings from the canonical.
They are recorded here so the canonical is written with downstream use in mind.

**Chrono24:** Condition Notes is a separate section — do NOT put condition
language in the description paragraph. The description paragraph covers
horological significance and completeness only.

**Grailzee:** One paragraph. Purely emotional. No specs, no condition, no
reference number. Write like you're telling a friend why this piece matters.
Same advisor standard: name what matters, do not explain it.

**Reddit:** Richest prose. The canonical paragraph is expanded into two full
paragraphs: P1 covers what the reference is and why it matters; P2 covers the
movement and its characteristics. Write the canonical with this expansion in
mind. Even in Reddit's richer format, name complications and finishing — do not
explain them.

**WTA Dealer Chat:** No prose at all. Structured data only. The canonical
description is not used on WTA.

---

## What This File Governs

Three canonical fields only. Everything else is derived downstream by
run_phase_b.py.

1. **Descriptive paragraph** — One paragraph. Name the horological significance,
   the movement, the finishing, the complications. What makes this reference
   worth owning and why this specific example. Confidence-tier language
   throughout. No condition language. No price or value language. No provenance.
   No service history. No explaining what complications do.
   If service history is unknown: "service history unknown but running accurately."

2. **Condition sentence** — One sentence only. Condition rating + completeness.
   No provenance. No service history. No purchase source.
   Examples:
   - "Excellent condition, full set with original box, papers dated June 2023, and extra links in sealed bag."
   - "Very good condition, watch only, no box or papers."
   - BNIB: "Brand new in box, never worn, full set with factory stickers."

3. **Grailzee paragraph** (null when grailzee_format is skip) — One paragraph.
   Emotionally driven. No specs, no condition, no reference number. Pure story.
   Name what matters. Do not explain it.

**The two-paragraph format is dead. One descriptive paragraph + one condition
sentence. That is the canonical. Everything else derives from it.**

Once approved, all platform versions are derived mechanically from these elements.
No new prose is written in the downstream phase — only shortening, reformatting,
character substitution, and platform template insertion.