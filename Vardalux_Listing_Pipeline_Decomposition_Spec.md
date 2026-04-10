# Vardalux Listing Pipeline — Decomposition Spec

## For Claude Code Build Session
**April 10, 2026**

---

## The Problem

`watch-listing-openclaw/SKILL.md` is 775 lines / 31K. The three reference files add another 25K. Every invocation loads ~56K of context regardless of which step is running. OpenClaw times out because the LLM is processing platform templates when it only needs to review photos, or recalculating pricing formulas when it only needs to write one paragraph.

## The Principle

**LLM = synthesis + human judgment. Python = everything deterministic.**

Of the 7 pipeline steps, only 2 genuinely need an LLM (photo review and canonical description writing). WatchTrack browser nav is borderline — it's automation, not synthesis. Everything else is math, string formatting, or template slotting.

## Design Rule Going Forward

Every new skill follows this pattern:
- One job per skill, 50–100 lines max
- If the work is deterministic (math, formatting, templating, substitutions, checklist generation), it's Python
- If the work is synthesis or judgment (writing, visual assessment, strategic decisions), it's a micro-skill
- Shared data travels through `_draft.json`, not through context

---

## Current Architecture (Monolith)

```
watch-listing-openclaw/
  SKILL.md                        ← 775 lines, 31K — THE WHOLE PIPELINE
  references/
    platform-templates.md          ← 495 lines, 15K
    character-substitutions.md     ← 111 lines, 4K
    posting-checklist.md           ← 199 lines, 5.5K
```

Total context per invocation: ~56K

## Target Architecture (Decomposed)

```
watch-listing-workspace/
  pipeline.py                      ← Orchestrator: reads _draft.json, calls next step
  schema/
    draft_schema.json              ← _draft.json validation schema
  tools/
    run_pricing.py                 ← Pure math: all platform pricing formulas
    run_phase_b.py                 ← Template assembly: canonical → all platforms
    run_grailzee_gate.py           ← Web fetch + price comparison
    run_checklist.py               ← Posting checklist generation from price + brand
    run_char_subs.py               ← Character substitution engine (regex)
    generate_listing_pdf.py        ← ReportLab PDF generation (already exists)
    draft_save.py                  ← Draft read/write/validate (already exists)
  skills/
    step0-watchtrack/SKILL.md      ← LLM: browser nav, data extraction → draft
    step1-photos/SKILL.md          ← LLM: visual assessment, condition notes → draft
    step3a-canonical/SKILL.md      ← LLM: write one paragraph + one condition sentence → draft
  references/
    voice-tone.md                  ← Trimmed voice rules (30-40 lines, not 200)
    platform-templates.md          ← Kept as-is (only loaded by run_phase_b.py, not LLM)
    character-substitutions.md     ← Kept as-is (only loaded by run_char_subs.py, not LLM)
    posting-checklist.md           ← Kept as-is (only loaded by run_checklist.py, not LLM)
    trust-blocks.md                ← Per-platform trust blocks (extracted from SKILL.md lines 580-596)
    payment-blocks.md              ← Per-platform payment methods (extracted from SKILL.md lines 613-632)
```

Context per LLM invocation at each step:
- step0-watchtrack: ~3K (just browser nav instructions + draft schema)
- step1-photos: ~4K (photo review criteria + draft schema)
- step3a-canonical: ~5K (voice-tone.md + tier rules + draft schema)
- pipeline.py orchestrator: 0K LLM (pure Python)

vs. current: ~56K for every step.

---

## Existing Assets (Do Not Rebuild)

These already exist and work. Copy them into the new structure:

| File | Current Location | Status |
|------|-----------------|--------|
| `generate_listing_pdf.py` | Referenced in SKILL.md line 771; lives in listing folders | Working, uses ReportLab |
| `draft_save.py` | Referenced in conversation; built in prior session | Working |
| `platform-templates.md` | `references/platform-templates.md` | Complete, 495 lines |
| `character-substitutions.md` | `references/character-substitutions.md` | Complete, 111 lines |
| `posting-checklist.md` | `references/posting-checklist.md` | Complete, 199 lines |
| `_draft.json` schema | SKILL.md lines 176-209 | Defined, needs formal JSON Schema |

---

## Extraction Map

### File 1: `schema/draft_schema.json`

**Source:** SKILL.md lines 176–209 (the _draft.json example)

**Action:** Formalize into a JSON Schema that every tool validates against. Fields:

```
step              → integer (0-4), which step was last completed
timestamp         → ISO 8601 string
inputs            → object
  internal_ref    → string (parsed from folder name)
  model_ref       → string (parsed from folder name)
  brand           → string
  model           → string
  reference       → string
  retail_net      → number
  wholesale_net   → number | null
  wta_price       → number | null
  wta_comp        → number | null
  reddit_price    → number | null
  msrp            → number | null
  tier            → integer (1, 2, or 3)
  condition       → string (BNIB | Excellent | Very Good | Good | Other)
  condition_detail → string (component-level notes)
  grailzee_format → string (NR | Reserve | skip)
  buffer          → number (default 5)
  included        → string (what ships with the watch)
  year            → string
  case_size       → string
  case_material   → string
  movement        → string
watchtrack        → object
  cost_basis      → number
  recent_comps    → array of numbers
  serial          → string
  notes           → string
pricing           → object (populated by run_pricing.py)
  ebay            → object { list_price, auto_accept, auto_decline }
  chrono24        → object { list_price }
  facebook_retail → object { list_price }
  facebook_wholesale → object { list_price } | null
  wta             → object { price, comp, max_allowed, sweet_spot, status } | null
  reddit          → object { list_price } | null
  grailzee        → object { format, reserve_price } | null
canonical         → object (populated by step3a-canonical)
  description     → string (one paragraph, tier-appropriate)
  condition_line  → string (one sentence, condition + completeness)
  grailzee_desc   → string (emotional paragraph, no specs)
approved          → object
  photos          → object { status, notes, timestamp }
  pricing         → object { status, table, timestamp }
  descriptions    → object { status, timestamp }
  grailzee_gate   → object { status, median, recommendation, timestamp }
```

### File 2: `tools/run_pricing.py`

**Source:** SKILL.md lines 288–390

**Extracts:**
- eBay pricing formula (lines 290-306): buffered → tiered fees → list price → round to $X49/$X99 → auto_accept (×0.95) → auto_decline (×0.85)
- Chrono24 formula (lines 310-314): buffered / (1 - 0.075) → round to nearest $25/$50
- Facebook retail formula (lines 318-322): buffered → round to clean number
- Facebook wholesale formula (lines 326-329): wholesale_net → round
- WTA validation (lines 333-356): comp × 0.90 max, comp × 0.80 sweet spot, compliance checks
- Reddit (lines 360-362): pass-through, no calculation
- Grailzee (lines 368-371): NR = $1 start, Reserve = user-provided or median +10-15%

**Interface:**
```
Input:  _draft.json (reads inputs.retail_net, inputs.buffer, inputs.wholesale_net, etc.)
Output: writes pricing object back to _draft.json via draft_save.py
Returns: pricing summary table (for Slack display)
```

**Rounding helpers to implement:**
- `round_ebay(price)` → nearest $X,X49 or $X,X99
- `round_clean(price, step=25)` → nearest $25 or $50
- `round_nearest_50(price)` → for auto_accept/decline

**Test criteria:** Run against the Tudor BB GMT 79830RB numbers from the P&L tracker. Verify eBay, Chrono24, Facebook prices match what the monolith would produce.

### File 3: `tools/run_char_subs.py`

**Source:** `references/character-substitutions.md` (the complete substitution table)

**Action:** Parse the markdown tables into a Python dict. Apply substitutions via case-sensitive string replacement (not regex — the substitutions are literal). Order matters: longer strings first to avoid partial matches (e.g., "Speedmaster" before "master").

**Interface:**
```
Input:  clean text string
Output: substituted text string
```

Also include a `needs_substitution(platform)` check: returns True only for facebook_retail and facebook_wholesale.

**Test criteria:** Feed in a sample eBay description mentioning "Omega Speedmaster" + "automatic" + "Wire or Zelle" + "warranty" + "Papers". Verify all substitutions apply correctly. Verify no substitutions on WTA or Reddit input.

### File 4: `tools/run_phase_b.py`

**Source:** SKILL.md lines 392-696 (description rules, platform-specific notes, trust blocks, payment blocks) + `references/platform-templates.md`

This is the biggest Python tool. It assembles the complete multi-platform listing document from the canonical description + pricing data in `_draft.json`.

**What it does:**
1. Reads `_draft.json` (canonical description, condition line, pricing, inputs)
2. Reads `references/platform-templates.md` for template structures
3. For each platform, slots the canonical content into the template:
   - Internal Reference: specs + condition + selling points (from draft)
   - Grailzee: canonical.grailzee_desc (if not skipped)
   - eBay: title (80 char max) + pricing + canonical.description + canonical.condition_line + What's Included + trust block + Item Specifics
   - Chrono24: title + reference + canonical.description + Scope of Delivery + Condition Notes (component breakdown, NOT in description)
   - Facebook Retail: runs through `run_char_subs.py` + Key Details + canonical.description + canonical.condition_line + payment block + CTA
   - Facebook Wholesale: Key Details + payment block only (no description)
   - WTA Dealer Chat: structured data only (year, ref, completeness, condition notes, diameter, payment). NO prose
   - Reddit: richest prose (may need a separate canonical.reddit_desc or the canonical gets expanded here) + Specs + Condition + Price + About Us
   - Value Your Watch: short catchy desc + full specs + Why Vardalux
   - Instagram: 1-2 sentences, no pricing, "Tell Me More" CTA
4. Calls `run_checklist.py` to generate the posting checklist
5. Assembles everything into `_Listing.md`
6. Updates `_draft.json` with step: 4

**Key extraction points from SKILL.md:**
- Key Details pipe format: lines 566-576
- Trust blocks per platform: lines 580-596
- Payment blocks per platform: lines 613-632
- Platform-specific rules: lines 636-696
- Absolute Do Nots: lines 699-726 (embed as validation checks, not as LLM context)

**Title generation rules (deterministic, no LLM needed):**
- eBay: `[Brand] [Model] [Key Feature] | Ref [Reference] | [Size]mm` (max 80 chars)
- Chrono24: clean, professional format
- Facebook: with character substitutions applied
- Reddit: `[WTS] Brand Model Key Feature – Size Material – Ref Number`

**Test criteria:** Take a completed `_draft.json` from a real listing (with canonical description already written) and run it. Compare output to a known-good listing document.

### File 5: `tools/run_grailzee_gate.py`

**Source:** SKILL.md lines 498-522

**Action:** Fetch Grailzee median data for the reference, compare to current pricing.

**Interface:**
```
Input:  _draft.json (reads inputs.reference, pricing.grailzee)
Output: gate result object { median, recommendation, comparison }
```

**Note:** The "web fetch" part depends on how Grailzee data is accessed. Options:
- Grailzee Pro report data (if cached from analyzer)
- Web scrape (if accessible)
- Manual input fallback (post to Slack, wait for user)

If data unavailable, return a "manual check needed" status rather than blocking.

**Test criteria:** Run against a reference with known Grailzee data. Verify comparison logic.

### File 6: `tools/run_checklist.py`

**Source:** `references/posting-checklist.md` (complete logic)

**Action:** Pure Python. Takes final Facebook retail price + brand + which optional platforms are active. Generates the formatted checklist.

**Interface:**
```
Input:  _draft.json (reads pricing.facebook_retail.list_price, inputs.brand, inputs.grailzee_format, etc.)
Output: formatted checklist string
```

**Logic (from posting-checklist.md):**
1. Universal: always eBay, Chrono24, Value Your Watch, Watch Trader Community
2. Price-based: two Facebook groups selected by price threshold (≤$5K, $5K-$10K, $10K+)
3. Brand-specific: Omega, Speedmaster, Breitling, Panerai, Hublot groups
4. Optional: Grailzee (if not skip), WTA (if wta_price provided), Reddit (if reddit_price provided), Wholesale (if wholesale_net provided), Instagram (always)

**Test criteria:** Run for an Omega Speedmaster at $4,500 — should get 9+ platforms. Run for a Tudor at $3,200 — should get 7 platforms (no brand-specific group).

---

## Micro-Skills (LLM)

### Skill A: `skills/step0-watchtrack/SKILL.md`

**Source:** SKILL.md lines 234-256

**Scope:** Browser navigation to WatchTrack, data extraction, save to draft. That's it.

**Context needed:** (~50 lines)
- WatchTrack URL and navigation pattern
- What fields to extract (serial, cost basis, comps, condition notes)
- How to save to `_draft.json` via draft_save.py
- Slack channel ID for confirmation message
- Button spec: `Looks Good` / `Correct This`

**Context NOT needed:** Pricing formulas, platform templates, voice rules, character substitutions, posting checklist, description rules.

### Skill B: `skills/step1-photos/SKILL.md`

**Source:** SKILL.md lines 258-283

**Scope:** Read images from listing folder, assess quality and completeness, post review to Slack, collect condition/tier/format inputs. Save to draft.

**Context needed:** (~60 lines)
- Photo review criteria (composition, lighting, angles, condition conflicts)
- The "at least one full paragraph of feedback" requirement
- Button specs: Approve/Request Changes, then Condition/Tier/Grailzee format buttons
- Free-text input prompts (retail_net, optional prices)
- How to save to `_draft.json`
- Slack channel ID

**Context NOT needed:** Everything else.

### Skill C: `skills/step3a-canonical/SKILL.md`

**Source:** SKILL.md lines 392-496 (voice, tone, tier rules, description rules)

**Scope:** Read the draft, write one canonical description paragraph + one condition sentence + one Grailzee emotional paragraph. Save to draft.

**This is the only skill that needs voice rules.** Extract a trimmed `references/voice-tone.md`:

**voice-tone.md content (extract from SKILL.md lines 398-448):**
- Ogilvy Standard summary (5 lines)
- Voss Standard summary for listings (3 lines)
- Knowledge vs. Confidence distinction (3 lines)
- Core writing rules (lines 421-429, ~10 lines)
- Tier 1 rules (lines 449-456, ~8 lines)
- Tier 2/3 rules (lines 458-464, ~7 lines)
- Grailzee rules (lines 472-476, ~5 lines)
- Chrono24 adjustment note (lines 467-470, ~3 lines)
- Reddit note: richest prose, two full paragraphs (lines 485-488, ~4 lines)

Total: ~50 lines. Compare to the current 200+ lines of voice content embedded in the monolith.

**Interface:**
```
Input:  _draft.json (reads inputs.tier, inputs.condition, inputs.condition_detail, inputs.brand, inputs.model, watchtrack data)
        voice-tone.md (read at start of skill)
Output: writes canonical.description, canonical.condition_line, canonical.grailzee_desc to _draft.json
```

**Slack interaction:** Post descriptions to channel, then buttons: `Approve` / `Request Changes`

---

## The Orchestrator: `pipeline.py`

**Source:** SKILL.md lines 226-230 (pipeline flow diagram) + lines 212-222 (resume logic)

**What it does:**
1. Receives a folder path (from Slack message or `/process` command)
2. Checks for existing `_draft.json` in the folder
3. If found: reads step number, offers Resume/Start Over
4. If not found: creates initial draft from folder name parsing
5. Based on current step, calls the next action:

```
step = None → Create draft, call step0-watchtrack skill
step = 0    → Call step1-photos skill
step = 1    → Call run_pricing.py (pure Python, no LLM)
step = 2    → Call step3a-canonical skill
step = 3    → Call run_grailzee_gate.py (pure Python)
step = 3.5  → Call run_phase_b.py (pure Python, assembles everything)
step = 4    → Call generate_listing_pdf.py (pure Python)
```

**Key behavior:** The orchestrator never loads voice rules, platform templates, or character substitutions. It only reads the draft to determine state, then dispatches.

**For OpenClaw:** The orchestrator is what the user talks to. It posts status to Slack and delegates. The micro-skills are called by the orchestrator, not directly by the user.

---

## Build Order

Each step: build → test against real data → confirm → move to next.

| Order | File | Type | Test |
|-------|------|------|------|
| 1 | `schema/draft_schema.json` | JSON Schema | Validate against existing _draft.json from a real listing |
| 2 | `tools/run_pricing.py` | Python | Run against Tudor BB GMT numbers, verify all platform prices |
| 3 | `tools/run_char_subs.py` | Python | Feed Omega Speedmaster description, verify all subs apply |
| 4 | `tools/run_checklist.py` | Python | Run for Omega Speedmaster at $4,500, verify platform count |
| 5 | `tools/run_phase_b.py` | Python | Feed completed draft, compare to known-good listing doc |
| 6 | `tools/run_grailzee_gate.py` | Python | Run against reference with known median |
| 7 | `skills/step3a-canonical/SKILL.md` + `voice-tone.md` | LLM Skill | Write a description, verify voice compliance |
| 8 | `skills/step1-photos/SKILL.md` | LLM Skill | Review real listing photos |
| 9 | `skills/step0-watchtrack/SKILL.md` | LLM Skill | Navigate WatchTrack, extract data |
| 10 | `pipeline.py` | Python | End-to-end: folder → PDF |

Python tools first (2-6) because they're testable without OpenClaw running. Micro-skills next (7-9) because they're small and focused. Orchestrator last (10) because it needs everything else working.

---

## Migration Strategy

**Do not delete the monolith until the decomposed version is validated end-to-end.**

1. Build all tools and skills in `watch-listing-workspace/` (new directory)
2. Test each tool independently against real listing data
3. Test the orchestrator end-to-end with a real listing
4. Run both the monolith and the decomposed version on the same listing, compare outputs
5. Once outputs match: archive the monolith, switch OpenClaw to the new workspace
6. Delete the monolith only after 2-3 successful listings through the new pipeline

---

## What the Claude Chat Skill Gets

The regular `watch-listing/SKILL.md` (the Claude Chat version, 481 lines) has the same bloat problem, just less severe because Chat has a larger context window. Once the Python tools are validated, the Chat skill can also call them instead of re-implementing pricing math and template assembly inline. That's a follow-on task, not part of this build.

---

## Notes for Claude Code Session

- The git repo is `vardalux-skills`. All new files go there.
- Python 3.10+ assumed. No external dependencies beyond `requests` (for Grailzee gate) and `reportlab` (already installed for PDF gen).
- Every Python tool should be runnable standalone: `python run_pricing.py /path/to/_draft.json`
- Every tool validates `_draft.json` against the schema before operating.
- Error messages go to stdout (for OpenClaw to capture and post to Slack).
- The `references/` folder is read-only at runtime. Tools read from it, never write to it.
- Character substitutions: sort by string length descending before applying (prevents partial matches like "Omega" matching inside "Omega Speedmaster" before the full model name is substituted).

---

*Decomposition spec for Claude Code build | April 10, 2026*
