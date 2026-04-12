---
name: title-research
description: >
  Research buyer search behavior on eBay, Chrono24, and Google to produce
  evidence-based keyword recommendations for watch listing titles. Use this
  skill whenever the listing pipeline needs SEO-optimized titles, when
  evaluating retail search demand for a reference before buying, when
  comparing keyword trends across references, or when assessing competitor
  titling strategies. Trigger when the user says "run title research",
  "SEO research", "keyword research", "what are buyers searching for",
  "title optimization", "check search demand", or when the listing pipeline
  reaches Step 1.5 (after WatchTrack extraction, before pricing). Also
  trigger when the user asks "how searchable is this reference", "what
  would buyers type", or "how are competitors titling this".
---

# Title Research — Vardalux Collections (OpenClaw)

## Purpose

Perform live platform research to determine which search terms real buyers
are using for a specific watch on eBay, Chrono24, and Google. Output a
structured Title Research Brief (`title-research.json`) that downstream
skills and tools can consume.

This skill produces keyword intelligence. It does NOT generate titles,
descriptions, pricing, or any listing content. It does NOT know about
Vardalux voice standards, platform templates, or listing workflows. The
content skill reads this skill's output and builds titles from it.

### Why This Exists

Retail buyers do not search by reference number. They search by what they
want: "Tudor automatic watch 41mm steel," "blue dial chronograph men's,"
"Pepsi bezel GMT." Titles that lead with reference numbers self-select
into the most price-sensitive, margin-compressed buyer pool on every
platform.

This skill ensures every listing title is informed by how buyers actually
search, not by what dealers assume buyers search for. The same research
data is also valuable outside of listings: evaluating retail demand before
sourcing, tracking keyword shifts over time, and identifying gaps in
competitor titling.

---

## Inputs

This skill receives basic watch identity data. Source can be:
- `watchtrack.json` in the listing working folder (preferred, auto-read)
- Direct input from the operator via Slack or chat
- Manual JSON provided as a message

### Required Fields (minimum)

At least ONE of these combinations:
- `brand` + `collection` (e.g., "Tudor" + "Black Bay")
- `brand` + `reference` (e.g., "Tudor" + "79830RB")

### Optional Fields (improve research quality)

```json
{
  "brand": "Tudor",
  "collection": "Black Bay",
  "model_name": "Black Bay GMT",
  "reference": "79830RB",
  "case_size_mm": 41,
  "case_material": "Stainless Steel",
  "dial_color": "Black",
  "bezel_material": "Aluminum",
  "bezel_colors": "Blue/Red",
  "movement_type": "Automatic",
  "complication_type": "GMT",
  "gender": "Men's",
  "year": "2023",
  "condition": "Excellent",
  "box_papers": "Full Set"
}
```

**Critical: `dial_color` is the ground truth for this specific watch.**
Research will surface keywords from multiple dial variants of the same
reference. The spec validation step filters out keywords that don't match
the actual dial. Without `dial_color`, this filter cannot run and the
output will include a warning.

### Photo Fallback for Missing dial_color

If `dial_color` is null or absent from the input data AND the skill is
running inside a listing folder (i.e., a working folder path is known),
use the `image` tool to determine the dial color from the listing photos
before proceeding.

**Steps:**

1. List the first `.jpg` or `.png` file in the listing folder
2. Call the `image` tool with that file path and the prompt:
   `"What color is the dial of this watch? Reply with just the color name
   (e.g., Black, White, Silver, Blue, Green, Pink, Salmon, Champagne,
   Opaline, Skeleton). One or two words only."`
3. Use the response as `dial_color` for the spec validation step
4. Record the source of the value in `watch_identity`:
   ```json
   "dial_color": "Black",
   "dial_color_source": "photo_inference"
   ```
   vs. when it comes from watchtrack.json:
   ```json
   "dial_color": "Black",
   "dial_color_source": "watchtrack"
   ```

**Handling:**
- If the image tool returns an ambiguous answer (e.g., "silver or white"),
  use the more specific term and note the ambiguity in `spec_validation`
- If no photos are found in the folder, fall through to the existing
  behavior: skip the dial variant filter and add the warning to output
- Only use one photo — the first one found is sufficient for color ID
- This step runs BEFORE any web research begins, so the correct dial
  color is available for query construction (e.g., Google organic query
  can include the nickname if Pepsi/Batman/etc. is already known)

---

## Output

A `title-research.json` file written to:
- The listing working folder (if running inside the listing pipeline)
- The current working directory (if running standalone)

### Output Schema

```json
{
  "spec_version": "1.1",
  "research_timestamp": "ISO-8601",
  "watch_identity": {
    "brand": "string",
    "collection": "string",
    "reference": "string",
    "dial_color": "string | null",
    "case_size_mm": "number | null",
    "bezel_colors": "string | null"
  },
  "ebay_autocomplete": {
    "queries_tested": ["array of query strings"],
    "suggestions_found": ["array of autocomplete suggestions"]
  },
  "ebay_sold_comps": {
    "search_query": "string",
    "total_results_scanned": "number",
    "results_used": "number",
    "results_excluded": [
      {
        "title": "string",
        "sold_price": "number",
        "reason": "string (Off-reference | Anomalous price | Accessory/parts)"
      }
    ],
    "titles": [
      {
        "title": "string",
        "sold_price": "number",
        "sold_date": "string"
      }
    ],
    "keyword_frequency": { "keyword": "count" },
    "price_correlation": {
      "highest_price_title": "string",
      "highest_price": "number",
      "highest_price_keywords": ["array"],
      "top_3_avg_price": "number",
      "top_3_shared_keywords": ["array"],
      "bottom_3_avg_price": "number",
      "bottom_3_shared_keywords": ["array"],
      "note": "string"
    },
    "common_keywords_in_top_titles": ["array"],
    "keywords_in_highest_priced_titles": ["array"],
    "keywords_absent_from_most_titles": ["array"]
  },
  "chrono24_search": {
    "method": "web_search",
    "query": "string",
    "top_listing_titles": ["array"],
    "common_keywords": ["array"]
  },
  "google_organic": {
    "method": "web_search",
    "query": "string",
    "top_result_titles": ["array"],
    "common_keywords": ["array"]
  },
  "nickname_detection": {
    "detected": "string | null",
    "source": "string",
    "search_validated": "boolean",
    "validation_evidence": ["array of evidence strings"],
    "sources_validated": "number",
    "promoted_to": "priority_1 | priority_2 | priority_3 | null"
  },
  "spec_validation": {
    "dial_variant_filter": {
      "input_dial_color": "string",
      "keywords_found_in_research": ["array"],
      "keywords_removed": ["array"],
      "reason": "string"
    },
    "case_size_validation": {
      "input_case_size_mm": "number",
      "conflicting_values_in_comps": ["array"],
      "resolution": "string"
    },
    "completeness_filter": {
      "input_box_papers": "string | null",
      "keywords_validated": ["array"],
      "note": "string"
    }
  },
  "recommended_title_keywords": {
    "priority_1_must_include": ["array"],
    "priority_2_high_value": ["array"],
    "priority_3_if_space_allows": ["array"],
    "reference_placement": "Item Specifics / structured fields only, not in title"
  },
  "msrp": {
    "value": "number | null",
    "currency": "USD",
    "source": "string (e.g. brand website, retailer, search result)",
    "note": "string | null"
  },
  "competitor_gap": {
    "note": "string"
  },
  "sources_successful": "number",
  "sources_attempted": 5,
  "source_status": {
    "ebay_autocomplete": "string",
    "ebay_sold_comps": "string",
    "chrono24": "string",
    "google_organic": "string",
    "msrp_lookup": "string"
  }
}
```

---

## Research Steps

### Research 1: eBay Autocomplete Mining

**Method:** Browser automation (same pattern as WatchTrack skill)
**URL:** `https://www.ebay.com`
**Auth:** None. Public search interface.

**Steps:**

1. Navigate to `https://www.ebay.com`
2. Locate the search input field
3. Run a progressive query sequence, pausing 1-2 seconds after each to
   capture autocomplete suggestions:

| Query # | Input | Purpose |
|---------|-------|---------|
| 1 | `{brand}` | Broad brand-level search terms |
| 2 | `{brand} {collection}` | Collection-level refinements |
| 3 | `{brand} {complication}` | Complication-level searches |
| 4 | `{brand} {collection} {complication}` | Full specific queries |

For each query:
- Type into search field
- Wait 1-2 seconds for autocomplete dropdown
- Read all suggestions from the dropdown
- Clear the field before the next query

**Extract:** All unique autocomplete suggestions across all queries, deduplicated.

**Handling:**
- If autocomplete dropdown does not appear within 3 seconds, record empty
  and move to next query
- Suggestions are the literal strings shown in the dropdown
- If `complication_type` is not provided, skip queries 3 and 4 and
  substitute query: `{brand} {collection} watch`

### Research 2: eBay Sold Listing Title Analysis

**Method:** Browser automation
**URL:** `https://www.ebay.com/sch/i.html?_nkw={query}&_sacat=0&LH_Sold=1&LH_Complete=1&_sop=13`

Where `{query}` is URL-encoded: `{brand}+{collection}+{complication}+{reference}`
The `_sop=13` parameter sorts by price descending.

**Auth:** None. Sold listings are public.

**Steps:**

1. Navigate to the sold listings URL
2. Wait for results to load
3. Read the first 10 result titles from the search results page
4. For each result, extract:
   - Full listing title text
   - Sold price (green text amount)
   - Sold date (if visible)
5. Do NOT click into individual listings

**Anomaly Detection (apply before keyword analysis):**

Exclude any result if:

| Condition | Flag Reason |
|-----------|-------------|
| Title contains a different reference or model | Off-reference |
| Sold price is >40% below the median of the other results | Anomalous price |
| Title indicates parts, straps, bezels, or accessories | Accessory/parts listing |

Excluded results stay in the output under `results_excluded` with the flag
reason. They do NOT contribute to keyword frequency or price correlation.

**Keyword Frequency:** After exclusions, count how many of the remaining
titles contain each distinct keyword. Record as `keyword_frequency` object.

**Price Correlation:** Compute top 3 vs. bottom 3 analysis (see Keyword
Analysis Logic section below).

**Broadening logic:**
- If fewer than 5 usable results after exclusions, retry without reference:
  `{brand}+{collection}+{complication}`
- If still fewer than 5, retry with: `{brand}+{collection}+watch`
- Log which query was ultimately used in `search_query`

### Research 3: Chrono24 Title Analysis

**Method: Web search.** Do NOT navigate directly to chrono24.com.
Chrono24 returns 403 on automated browser requests. Confirmed in testing.

**Query:** `{brand} {collection} {complication} {reference} site:chrono24.com`

Example: `Tudor Black Bay GMT 79830RB site:chrono24.com`

**Steps:**

1. Perform a web search using the query above
2. Read the titles of the first 7-10 results from chrono24.com domains
3. Record each listing title as it appears in search results

**Extract:**
- Array of listing titles (up to 10)
- Frequency analysis of keywords across titles

**Handling:**
- If fewer than 3 Chrono24 results, retry without reference:
  `{brand} {collection} {complication} site:chrono24.com`
- Some titles may be truncated by the search engine. Record what is visible.
- Strip any pricing or seller info appended by the search engine.

### Research 4: Google Organic Search

**Method: Web search.** Do NOT navigate to Google Shopping directly.
The Shopping tab is JavaScript-rendered and returns empty on automated fetch.
Confirmed in testing.

**Query construction:**

If a nickname has been detected by this point (from nickname lookup table):
`buy {brand} {collection} {complication} {nickname} watch`
Example: `buy Tudor Black Bay GMT Pepsi watch`

If no nickname detected:
`buy {brand} {collection} {complication} watch`
Example: `buy Tudor Royal Date watch`

**Steps:**

1. Perform a web search using the constructed query
2. Read the first 5-8 result titles (includes organic results, Shopping
   carousel snippets, and indexed dealer listings)
3. Record each title

**Extract:**
- Array of product/listing titles from results
- Keywords that appear in 3+ of the top results

**Handling:**
- If results are dominated by editorial content (reviews, comparisons),
  retry with: `{brand} {collection} {reference} for sale`
- Ignore non-listing results (forum posts, Wikipedia, etc.)

---

### Research 5: MSRP Lookup

**Method: Web search.** Quick lookup only — 30 seconds max, do not block on failure.

**Query:**
`{brand} {model} {reference} retail price MSRP`

**Steps:**
1. Perform one web search
2. Scan the top 3-5 results for a current retail/MSRP price from:
   - Brand's official website
   - Authorized dealer (Jomashop, Watches of Switzerland, etc.)
   - Trusted retailer listing with clear price display
3. Record the value in USD. If price is in another currency, convert at
   approximate current rate and note the original currency.

**Handling:**
- If MSRP is clearly discontinued or unavailable (pre-owned only market):
  write `null` with note "Discontinued — no current MSRP"
- If multiple prices found, use the lowest authorized dealer price
- Do not use grey market or secondary market prices as MSRP
- If no result found in 30 seconds: write `null`, set `msrp_lookup: "no_result"`

**Write to `title-research.json`:**
```json
"msrp": {
  "value": 12500,
  "currency": "USD",
  "source": "Watches of Switzerland listing",
  "note": null
}
```

Also write `msrp` value to `_draft.json` via `draft_save.py`:
```
python3 /Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/draft_save.py "<folder>" '{"inputs": {"msrp": <value>}}'
```
Only write if value is not null. Skip the draft write if MSRP not found.

---

## Keyword Analysis Logic

After all research steps, produce the keyword analysis in this order:

### Step A: Spec Validation

**Must run BEFORE priority assignment.** Three checks:

**A1. Dial Variant Filter**

Compare every keyword candidate against `dial_color` from input.
If a keyword describes a dial variant that does NOT match the input,
remove it from all keyword lists.

Dial-variant keywords to check: Opaline, Sunburst, MOP, Mother of Pearl,
Salmon, Meteorite, Ice Blue, Wimbledon, Champagne, Rhodium, Slate,
Anthracite, White (when used as synonym for Opaline/MOP), Blue (when
input dial is Black and "Blue" refers to a blue-dial variant, not the
bezel).

Log every removal under `spec_validation.dial_variant_filter`.

If `dial_color` is not provided in input, skip this filter and add a
warning to the output: "Dial variant filter skipped. Input missing
dial_color. Keywords may include terms from other variants."

**A2. Case Size Validation**

If input includes `case_size_mm`, check whether competitor titles use a
different size for the same reference. If conflicts exist, always use the
input value. Log under `spec_validation.case_size_validation`.

**A3. Completeness Filter**

Keywords like "Full Set," "Box Papers," "BNIB," "Unworn" describe this
specific example, not the reference. Cross-check against input:

| Keyword | Requires |
|---------|----------|
| Full Set / Box Papers / Box & Papers | `box_papers` confirms completeness |
| BNIB / Unworn / New / Stickered | `condition` confirms new/unworn |

- If input confirms: keyword is valid for Priority 3
- If input contradicts: remove the keyword
- If input field is missing: move to Priority 3 with note "verify before use"

### Step B: Priority Assignment

**Priority 1 (Must Include):**
Keywords that appear in at least TWO of these three sources:
- eBay autocomplete suggestions
- Top 3 highest-priced eBay sold comp titles (after anomaly exclusion)
- Chrono24 top titles

AND pass Step A validation.

**Priority 2 (High Value):**
Keywords that appear in ONE of the three Priority 1 sources AND also
appear in Google organic results. OR keywords that appear in eBay
autocomplete only but match a core spec of the watch (e.g., "Automatic"
for an automatic watch, "Black Dial" for a black dial watch).

Must pass Step A validation.

**Priority 3 (If Space Allows):**
Keywords from only one source that are factually accurate for this
specific watch. Also the holding zone for completeness keywords pending
verification.

### Step C: Nickname Detection

Check bezel/dial combinations against the lookup table:

| Bezel/Dial | Nickname | Brand Context |
|------------|----------|---------------|
| Blue/Red bezel | Pepsi | Rolex GMT, Tudor GMT |
| Black/Blue bezel | Batman | Rolex GMT |
| Black/Brown or Root Beer bezel | Root Beer | Rolex GMT, Tudor GMT |
| Black/Red bezel | Coke | Rolex GMT, Tudor GMT |
| Green bezel + black dial | Kermit | Rolex Submariner (specific refs) |
| Green bezel + green dial | Hulk | Rolex Submariner 116610LV |
| White/Black dial + chronograph | Panda | Rolex Daytona, Tudor Chrono |
| Black/White dial + chronograph | Reverse Panda | Rolex Daytona, Tudor Chrono |
| Blue dial + steel (no bezel color) | — | No universal nickname, skip |

After detecting a nickname, validate it against search results:

| Found in N sources | Action |
|-------------------|--------|
| 2+ sources | Promote to Priority 1 |
| 1 source | Priority 2 |
| 0 sources | Priority 3 (collector jargon, may not drive retail search) |

Record validation evidence with specific source citations.

### Step D: Price Correlation

From eBay sold comps (after anomaly exclusion):

1. **Highest single sale:** title, price, keywords in that title
2. **Top 3 average price:** mean of 3 highest, shared keywords
3. **Bottom 3 average price:** mean of 3 lowest, shared keywords
4. **Correlation note:** One-sentence observation about keyword density
   vs. price. This is INFORMATIONAL for the content skill. The content
   skill should always optimize for discoverability unless data strongly
   suggests otherwise.

### Step E: Reference Number Rule

The reference number is NEVER placed in recommended keywords. It belongs
in platform structured fields:

| Platform | Where Reference Goes |
|----------|---------------------|
| eBay | Item Specifics → Reference Number |
| Chrono24 | Reference Number field |
| Facebook | Body text, first line after title |
| Value Your Watch | Separate reference field |
| Reddit | Body text, not post title |
| Grailzee | Auto-populated from database |

---

## Timing and Integration

### In the listing pipeline (Step 1.5)

Runs after WatchTrack extraction (Step 1), before pricing (Step 2).
Reads `watchtrack.json` from the listing folder for input data.
Writes `title-research.json` to the same folder.

### Standalone (outside the pipeline)

Accepts input directly from the operator. Writes `title-research.json`
to the current working directory.

### Execution time

Expected: 60-90 seconds for all four steps.
Maximum: 120 seconds. Skip any step exceeding 30 seconds.

### Failure handling

If the skill fails entirely, the listing pipeline does NOT block. The
content skill falls back to static keyword mapping.

Partial failure:
- 3 of 4 sources succeed → proceed normally
- 2 of 4 sources → proceed with caution flag; Priority 1 threshold drops
  to "appears in both available sources"
- 1 or 0 sources → write minimal output noting failures; content skill
  falls back to static keywords

---

## Standalone Use Cases (Outside Listing Pipeline)

### Sourcing Intelligence

Run title research on a reference you're considering buying. If eBay
autocomplete returns strong suggestions and sold comps show 7+ recent
sales with keyword-rich titles, retail search demand is healthy. If
autocomplete is thin and sold comps return fewer than 5 results after
broadening, the reference has limited retail discoverability.

**Invoke:** "Run title research on Tudor Royal 28600"
**Output:** `title-research.json` with demand signals, no listing generated

### Competitor Analysis

Run on a competitor's reference or a reference you want to understand.
The competitor gap analysis shows what keywords competitors are using
vs. missing. If most competitors lead with reference numbers and skip
retail descriptors, there's an SEO opportunity.

**Invoke:** "Check search demand for Cartier Santos WSSA0030"
**Output:** Keyword landscape, competitor title patterns, nickname status

### Keyword Trend Tracking

Run periodically on core target references to see if buyer search
behavior is shifting. If "Tudor GMT Pepsi" starts dropping out of
autocomplete and "Tudor GMT 58" starts appearing, buyer interest is
migrating to the newer model.

**Invoke:** "Run title research on all Tudor GMT references"
**Output:** Multiple `title-research.json` files for comparison

---

## What This Skill Does NOT Do

- Does not generate titles, descriptions, or any listing content
- Does not know about pricing, voice standards, or platform templates
- Does not log into any platform (all searches are public)
- Does not click into individual listings (all data from results pages)
- Does not interact with Grailzee (not a retail discovery platform)
- Does not modify any existing files (only creates `title-research.json`)
- Does not require API keys, tokens, or authentication
- Does not navigate directly to Chrono24 or Google Shopping (both block
  automated access; uses web search for indexed data instead)

---

## Reference Files

- `references/title-research-config.json` — Nickname lookup table,
  dial variant keyword list, platform structured field mapping, and
  anomaly detection thresholds. Edit this file when adding new nicknames,
  new dial variant keywords, or adjusting thresholds.

---

*Skill Version 1.1 | April 1, 2026*
*Author: Vardalux Collections*

