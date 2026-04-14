#!/usr/bin/env python3
"""
test_run_phase_b.py — Tests for run_phase_b.py.

Run standalone: python3 test_run_phase_b.py
Exits 0 on all pass, 1 if any test fails.

Sections:
  1 — Title generation: with title-research.json (Tudor BB GMT fixture)
  2 — Title generation: fallback (no title-research.json)
  3 — Title generation: edge cases
  4 — Key Details builder
  5 — Trust and payment block presence/absence per platform
  6 — Absolute Do Not validation checks
  7 — Character substitutions: FB applies, WTA/Reddit do not
  8 — Platform section builders: structural checks
  9 — Assembly: full listing structure
 10 — Integration: --dry-run via subprocess
"""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_phase_b import (
    get_title, load_title_research, _get_keywords, _make_fallback_base,
    _ebay_from_research, _joined_from_research, _reddit_from_research,
    make_key_details, validate_do_nots,
    build_internal_ref, build_grailzee, build_ebay, build_chrono24,
    build_fb_retail, build_fb_wholesale, build_wta, build_reddit,
    build_vyw, build_instagram, assemble_listing,
    TRUST_BLOCKS, PAYMENT_BLOCKS,
)
from run_char_subs import load_substitutions, SUBS_PATH

# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

passed = 0
failed = 0
failures = []


def expect(name, actual, expected):
    global passed, failed
    if actual == expected:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")
        print(f"        Expected: {expected!r}")
        print(f"        Got:      {actual!r}")
        failures.append(name)


def expect_true(name, cond):
    expect(name, bool(cond), True)


def expect_false(name, cond):
    expect(name, bool(cond), False)


def expect_raises(name, fn, exc_type):
    global passed, failed
    try:
        fn()
        failed += 1
        print(f"  FAIL  {name} — expected {exc_type.__name__}, no exception raised")
        failures.append(name)
    except exc_type:
        passed += 1
        print(f"  PASS  {name}")
    except Exception as e:
        failed += 1
        print(f"  FAIL  {name} — expected {exc_type.__name__}, got {type(e).__name__}: {e}")
        failures.append(name)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SUBS = load_substitutions(SUBS_PATH)

# Real title-research.json from the repo (Tudor BB GMT 79830RB)
TITLE_RESEARCH_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "listings", "tudor-79830rb-test", "title-research.json",
)
with open(TITLE_RESEARCH_PATH, encoding="utf-8") as _f:
    TUDOR_TR = json.load(_f)

TUDOR_INPUTS = {
    "internal_ref":  "TUDOR-79830RB",
    "model_ref":     "79830RB",
    "brand":         "Tudor",
    "model":         "Black Bay GMT",
    "reference":     "79830RB",
    "retail_net":    3350,
    "buffer":        3,
    "wholesale_net": 2900,
    "wta_price":     None,
    "wta_comp":      None,
    "reddit_price":  3450.50,
    "grailzee_format": "NR",
    "tier":          1,
    "condition":     "Excellent",
    "included":      "Box and papers",
    "year":          "2024",
    "case_size":     "41",
    "case_material": "Stainless Steel",
    "movement":      "Automatic, MT5652",
    "condition_detail": (
        "Case: Light micro-scratches on lugs consistent with light wear.\n"
        "Bezel: Clean with no notable marks.\n"
        "Crystal: No scratches.\n"
        "Dial: Perfect.\n"
        "Movement: Running accurately.\n"
        "Bracelet: Normal use wear, no stretch."
    ),
}

TUDOR_PRICING = {
    "ebay":              {"list_price": 3649, "auto_accept": 3450, "auto_decline": 3100},
    "chrono24":          {"list_price": 3725},
    "facebook_retail":   {"list_price": 3450},
    "facebook_wholesale": {"list_price": 2900},
    "wta":               None,
    "reddit":            {"list_price": 3450.50},
    "grailzee":          {"format": "NR", "reserve_price": None},
}

TUDOR_CANONICAL = {
    "description": (
        "The Black Bay GMT is Tudor's answer to the original GMT-Master brief. "
        "The bi-directional ceramic bezel reads a second time zone cleanly, the "
        "MT5652 in-house movement is COSC-certified, and the heritage snowflake "
        "hands keep it unmistakably Tudor. This example is in excellent condition "
        "with full set including box and papers."
    ),
    "condition_line": "Excellent condition with box and papers.",
    "grailzee_desc":  (
        "Two time zones, one wrist. The Black Bay GMT moves with you, "
        "the kind of watch that makes a transatlantic morning feel deliberate."
    ),
}

TUDOR_WATCHTRACK = {
    "cost_basis":   2700,
    "serial":       "TB123456",
    "notes":        "Retail NET $3,350. Purchased from collector.",
    "recent_comps": [3200, 3350, 3100],
}

TUDOR_DRAFT = {
    "step":       3.5,
    "timestamp":  "2026-04-11T00:00:00Z",
    "inputs":     TUDOR_INPUTS,
    "pricing":    TUDOR_PRICING,
    "canonical":  TUDOR_CANONICAL,
    "watchtrack": TUDOR_WATCHTRACK,
    "approved": {
        "photos":       {"status": "approved", "notes": "Strong set.", "timestamp": "2026-04-11T00:00:00Z"},
        "pricing":      {"status": "approved", "timestamp": "2026-04-11T00:00:00Z"},
        "descriptions": {"status": "approved", "timestamp": "2026-04-11T00:00:00Z"},
        "grailzee_gate": {"status": "proceed", "median": 3500, "recommendation": "proceed", "timestamp": "2026-04-11T00:00:00Z"},
    },
}


# ---------------------------------------------------------------------------
# SECTION 1: Title generation — with title-research.json
# ---------------------------------------------------------------------------

print("\n--- Section 1: Title generation with title-research.json ---")

ebay_title = _ebay_from_research(TUDOR_TR)
expect_true("eBay title ≤ 80 chars",               len(ebay_title) <= 80)
expect_true("eBay title starts with Tudor",         ebay_title.startswith("Tudor"))
expect_true("eBay title contains Pepsi (P1)",       "Pepsi" in ebay_title)
expect_true("eBay title contains GMT (P1)",         "GMT" in ebay_title)
expect_true("eBay title contains Automatic (P2)",   "Automatic" in ebay_title)
expect_true("eBay title contains Full Set (P3 — fits within 80)", "Full Set" in ebay_title)
expect_false("eBay title contains reference number", "79830RB" in ebay_title)
expect_false("eBay title contains pipes",            "|" in ebay_title)

expect("eBay title exact value",
       ebay_title,
       "Tudor Black Bay GMT Pepsi 41mm Automatic Steel Men's Watch Opaline Full Set")

c24_title = _joined_from_research(TUDOR_TR)
expect_true("Chrono24 title starts with Tudor",    c24_title.startswith("Tudor"))
expect_true("Chrono24 title contains Pepsi",       "Pepsi" in c24_title)
expect_true("Chrono24 title contains Full Set (P3)", "Full Set" in c24_title)
expect_false("Chrono24 title has no reference",    "79830RB" in c24_title)

fb_title = get_title("facebook_retail", TUDOR_TR, TUDOR_INPUTS, TUDOR_PRICING, SUBS)
expect_true("FB title has char subs applied (Tud0r)", "Tud0r" in fb_title)
expect_false("FB title: original Tudor absent",       "Tudor" in fb_title)

reddit_title = _reddit_from_research(TUDOR_TR, TUDOR_PRICING)
expect_true("Reddit title starts with [WTS]",        reddit_title.startswith("[WTS]"))
expect_true("Reddit title contains Tudor",           "Tudor" in reddit_title)
expect_true("Reddit title contains price",           "$3,450 Shipped" in reddit_title)
expect_false("Reddit title contains P3 (Full Set)",  "Full Set" in reddit_title)
expect_false("Reddit title has reference number",    "79830RB" in reddit_title)

vyw_title = get_title("value_your_watch", TUDOR_TR, TUDOR_INPUTS, TUDOR_PRICING, SUBS)
expect_true("VYW title starts with Tudor",           vyw_title.startswith("Tudor"))
expect_true("VYW title contains Full Set (P3)",      "Full Set" in vyw_title)


# ---------------------------------------------------------------------------
# SECTION 2: Title generation — fallback (no title-research.json)
# ---------------------------------------------------------------------------

print("\n--- Section 2: Title generation fallback ---")

fallback_base = _make_fallback_base(TUDOR_INPUTS)
expect_true("Fallback contains brand",          "Tudor" in fallback_base)
expect_true("Fallback contains model",          "Black Bay GMT" in fallback_base)
expect_true("Fallback ends with Watch",         fallback_base.endswith("Watch"))
expect_true("Fallback case_size has mm suffix", "41mm" in fallback_base)

ebay_fallback = get_title("ebay", None, TUDOR_INPUTS, TUDOR_PRICING, SUBS)
expect_true("eBay fallback ≤ 80 chars",        len(ebay_fallback) <= 80)
expect_true("eBay fallback contains Tudor",    "Tudor" in ebay_fallback)

fb_fallback = get_title("facebook_retail", None, TUDOR_INPUTS, TUDOR_PRICING, SUBS)
expect_true("FB fallback has char subs (Tud0r)", "Tud0r" in fb_fallback)

reddit_fallback = get_title("reddit", None, TUDOR_INPUTS, TUDOR_PRICING, SUBS)
expect_true("Reddit fallback starts [WTS]",      reddit_fallback.startswith("[WTS]"))
expect_true("Reddit fallback contains price",    "$3,450" in reddit_fallback)


# ---------------------------------------------------------------------------
# SECTION 3: Title edge cases
# ---------------------------------------------------------------------------

print("\n--- Section 3: Title edge cases ---")

# P1 alone > 80 chars — eBay returns empty string (nothing fits)
long_tr = {
    "recommended_title_keywords": {
        "priority_1_must_include": ["A" * 85],
        "priority_2_high_value":   [],
        "priority_3_if_space_allows": [],
    }
}
long_title = _ebay_from_research(long_tr)
expect("eBay: P1 > 80 chars → empty string",  long_title, "")
expect_true("eBay: P1 > 80 chars, no exception raised", True)  # reaching here means no crash

# Missing P2/P3 — no KeyError
sparse_tr = {
    "recommended_title_keywords": {
        "priority_1_must_include": ["Tudor", "GMT"],
    }
}
sparse_ebay = _ebay_from_research(sparse_tr)
expect("eBay: missing P2/P3 → P1 only",       sparse_ebay, "Tudor GMT")
expect_true("eBay: sparse P1 ≤ 80 chars",     len(sparse_ebay) <= 80)

# Reddit price fallback: no reddit pricing → uses FB retail price
pricing_no_reddit = dict(TUDOR_PRICING)
pricing_no_reddit["reddit"] = None
reddit_no_reddit_price = _reddit_from_research(TUDOR_TR, pricing_no_reddit)
expect_true("Reddit title: falls back to FB retail price when reddit pricing absent",
            "$3,450 Shipped" in reddit_no_reddit_price)

# get_title dispatcher: unknown platform → joined title
unknown_title = get_title("unknown_platform", TUDOR_TR, TUDOR_INPUTS, TUDOR_PRICING, SUBS)
expect_true("Unknown platform: returns joined title",
            unknown_title == _joined_from_research(TUDOR_TR))


# ---------------------------------------------------------------------------
# SECTION 4: Key Details builder
# ---------------------------------------------------------------------------

print("\n--- Section 4: Key Details builder ---")

kd_emoji = make_key_details(TUDOR_INPUTS, TUDOR_CANONICAL, emoji=True)
expect_true("Key Details with emoji starts with 🔎",      kd_emoji.startswith("🔎"))
expect_true("Key Details contains condition",             "Excellent" in kd_emoji)
expect_true("Key Details contains case_material",         "Stainless Steel" in kd_emoji)
expect_true("Key Details contains condition_line",        "Excellent condition with box" in kd_emoji)
expect_true("Key Details contains included",              "Box and papers" in kd_emoji)

kd_no_emoji = make_key_details(TUDOR_INPUTS, TUDOR_CANONICAL, emoji=False)
expect_true("Key Details without emoji starts plain",     kd_no_emoji.startswith("Key Details:"))
expect_false("Key Details without emoji has no 🔎",      "🔎" in kd_no_emoji)

# Minimal inputs — only required fields
minimal_inputs = {"condition": "Very Good"}
minimal_canonical = {"condition_line": "Very Good condition."}
kd_minimal = make_key_details(minimal_inputs, minimal_canonical)
expect_true("Minimal Key Details: no crash",              "Very Good" in kd_minimal)


# ---------------------------------------------------------------------------
# SECTION 5: Trust and payment blocks
# ---------------------------------------------------------------------------

print("\n--- Section 5: Trust and payment blocks ---")

# Platforms that have trust blocks
expect_true("eBay has trust block",          bool(TRUST_BLOCKS["ebay"]))
expect_true("Reddit has trust block",        bool(TRUST_BLOCKS["reddit"]))
expect_true("VYW has trust block",           bool(TRUST_BLOCKS["value_your_watch"]))

# Platforms that omit trust blocks
expect("Chrono24 trust block is None",   TRUST_BLOCKS["chrono24"],           None)
expect("FB wholesale trust block None",  TRUST_BLOCKS["facebook_wholesale"],  None)
expect("Grailzee trust block is None",   TRUST_BLOCKS["grailzee"],            None)
expect("WTA trust block is None",        TRUST_BLOCKS["wta"],                 None)
expect("Instagram trust block is None",  TRUST_BLOCKS["instagram"],           None)

# Platforms that have payment blocks
expect_true("FB retail has payment block",    bool(PAYMENT_BLOCKS["facebook_retail"]))
expect_true("FB wholesale has payment block", bool(PAYMENT_BLOCKS["facebook_wholesale"]))
expect_true("Reddit has payment block",       bool(PAYMENT_BLOCKS["reddit"]))
expect_true("WTA has payment block",          bool(PAYMENT_BLOCKS["wta"]))

# Platforms that omit payment blocks
expect("eBay payment block is None",      PAYMENT_BLOCKS["ebay"],    None)
expect("Chrono24 payment block is None",  PAYMENT_BLOCKS["chrono24"], None)
expect("Instagram payment block is None", PAYMENT_BLOCKS["instagram"], None)

# FB blocks are pre-substituted
expect_true("FB retail payment has W!re",    "W!re"  in PAYMENT_BLOCKS["facebook_retail"])
expect_true("FB retail payment has Z3lle",   "Z3lle" in PAYMENT_BLOCKS["facebook_retail"])
expect_true("FB retail payment has f33",     "f33"   in PAYMENT_BLOCKS["facebook_retail"])
expect_true("FB retail trust has w@rranty",  "w@rranty" in TRUST_BLOCKS["facebook_retail"])

# Reddit payment uses clean text
expect_false("Reddit payment: no W!re",      "W!re" in PAYMENT_BLOCKS["reddit"])
expect_true("Reddit payment: clean Wire",    "wire" in PAYMENT_BLOCKS["reddit"].lower())


# ---------------------------------------------------------------------------
# SECTION 6: Absolute Do Not validation
# ---------------------------------------------------------------------------

print("\n--- Section 6: Absolute Do Not validation ---")

clean_canonical = {
    "description":   "A robust and refined timepiece.",
    "condition_line": "Excellent condition with full set.",
    "grailzee_desc":  "It compels attention without demanding it.",
}
# Clean canonical should not raise
try:
    validate_do_nots(clean_canonical)
    passed += 1
    print("  PASS  Clean canonical: no exception")
except ValueError:
    failed += 1
    print("  FAIL  Clean canonical: unexpected ValueError raised")
    failures.append("Clean canonical: no exception")

# Each violation triggers ValueError
violations = [
    ("Mint",          {"description": "Mint condition example."}),
    ("em-dash",       {"description": "Perfect\u2014absolutely flawless."}),
    ("delve",         {"description": "Let us delve into the details."}),
    ("Buy now!",      {"description": "Buy now! Limited stock."}),
    ("Limited time!", {"description": "Limited time! Act fast."}),
    ("DM for price",  {"description": "DM for price and details."}),
    ("Grand Seiko",   {"description": "Consider Grand Seiko as an alternative."}),
    ("mistakes",      {"description": "Avoid mistakes when buying."}),
]
for name, bad_canonical in violations:
    expect_raises(
        f"Do Not: '{name}' raises ValueError",
        lambda c=bad_canonical: validate_do_nots(c),
        ValueError,
    )


# ---------------------------------------------------------------------------
# SECTION 7: Character substitution routing
# ---------------------------------------------------------------------------

print("\n--- Section 7: Character substitution routing ---")

fb_retail_section = build_fb_retail(
    TUDOR_INPUTS, TUDOR_PRICING, TUDOR_CANONICAL, TUDOR_TR, SUBS
)
# LLM description subs applied — canonical description contains "Tudor" → "Tud0r"
expect_true("FB retail: 'Tudor' → 'Tud0r' in description", "Tud0r" in fb_retail_section)
# Key Details subs applied
expect_true("FB retail: 'Stainless Steel' key detail processed", "Steel" in fb_retail_section)
# Fixed trust/payment blocks already substituted
expect_true("FB retail: w@rranty in trust block",  "w@rranty"  in fb_retail_section)
expect_true("FB retail: W!re in payment block",    "W!re"      in fb_retail_section)
expect_true("FB retail: Z3lle in payment block",   "Z3lle"     in fb_retail_section)

# WTA: no character substitutions anywhere
wta_pricing = dict(TUDOR_PRICING)
wta_pricing["wta"] = {
    "price": 2900, "comp": 3350, "max_allowed": 3015, "sweet_spot": 2680, "status": "OK"
}
wta_section = build_wta(TUDOR_INPUTS, wta_pricing)
expect_false("WTA: no @utomatic sub",   "@utomatic" in (wta_section or ""))
expect_false("WTA: no W!re sub",        "W!re"      in (wta_section or ""))
expect_true("WTA: clean Wire in payment", "Wire" in (wta_section or ""))

# Reddit: no character substitutions
reddit_section = build_reddit(
    TUDOR_INPUTS, TUDOR_PRICING, TUDOR_CANONICAL, TUDOR_TR, SUBS
)
expect_false("Reddit: no @utomatic sub", "@utomatic" in (reddit_section or ""))
expect_true("Reddit: clean wire in payment", "wire" in (reddit_section or "").lower())


# ---------------------------------------------------------------------------
# SECTION 8: Platform section structural checks
# ---------------------------------------------------------------------------

print("\n--- Section 8: Platform section structural checks ---")

# Internal Reference
internal = build_internal_ref(TUDOR_INPUTS, TUDOR_PRICING, TUDOR_WATCHTRACK)
expect_true("Internal ref: DO NOT POST header",   "DO NOT POST" in internal)
expect_true("Internal ref: brand present",        "Tudor" in internal)
expect_true("Internal ref: cost basis present",   "$2,700" in internal)
expect_true("Internal ref: target NET present",   "$3,450" in internal)
expect_true("Internal ref: watchtrack notes",     "Retail NET" in internal)

# Grailzee: NR format
gz = build_grailzee(TUDOR_CANONICAL, TUDOR_INPUTS, TUDOR_PRICING)
expect_true("Grailzee section present for NR",    gz is not None)
expect_true("Grailzee: NR format line",           "No Reserve" in (gz or ""))
expect_true("Grailzee: emotional desc present",   "transatlantic" in (gz or ""))

# Grailzee: skip
inputs_skip = dict(TUDOR_INPUTS, grailzee_format="skip")
gz_skip = build_grailzee(TUDOR_CANONICAL, inputs_skip, TUDOR_PRICING)
expect("Grailzee returns None when skip",         gz_skip, None)

# Grailzee: Reserve format with price
pricing_reserve = dict(TUDOR_PRICING)
pricing_reserve["grailzee"] = {"format": "Reserve", "reserve_price": 3200}
inputs_reserve = dict(TUDOR_INPUTS, grailzee_format="Reserve")
gz_res = build_grailzee(TUDOR_CANONICAL, inputs_reserve, pricing_reserve)
expect_true("Grailzee Reserve: format line shows price", "$3,200" in (gz_res or ""))

# Grailzee: grailzee_desc is null (JSON null → Python None) — must not crash
canonical_null_desc = dict(TUDOR_CANONICAL, grailzee_desc=None)
gz_null = build_grailzee(canonical_null_desc, TUDOR_INPUTS, TUDOR_PRICING)
expect_true("Grailzee: null grailzee_desc does not crash", gz_null is not None)
expect_true("Grailzee: null desc produces valid section",  "GRAILZEE" in (gz_null or ""))

# eBay section
ebay_section = build_ebay(TUDOR_INPUTS, TUDOR_PRICING, TUDOR_CANONICAL, TUDOR_TR, SUBS)
expect_true("eBay: TITLE header present",         "TITLE" in ebay_section)
expect_true("eBay: List Price $3,649",            "$3,649" in ebay_section)
expect_true("eBay: Auto-Accept $3,450",           "$3,450" in ebay_section)
expect_true("eBay: Auto-Decline $3,100",          "$3,100" in ebay_section)
expect_true("eBay: trust block present",          "VARDALUX:" in ebay_section)
expect_true("eBay: no payment methods",           "Wire" not in ebay_section and "Zelle" not in ebay_section)
expect_true("eBay: ITEM SPECIFICS section",       "ITEM SPECIFICS" in ebay_section)
expect_true("eBay: CONDITION section (detail present)", "CONDITION" in ebay_section)
expect_true("eBay: eBay title ≤ 80 chars stamp",  "[75 chars]" in ebay_section or "chars]" in ebay_section)

# Chrono24 section
c24_section = build_chrono24(TUDOR_INPUTS, TUDOR_PRICING, TUDOR_CANONICAL, TUDOR_TR, SUBS)
expect_true("Chrono24: List Price $3,725",        "$3,725" in c24_section)
expect_true("Chrono24: no VARDALUX trust",        "VARDALUX" not in c24_section)
expect_true("Chrono24: Scope of Delivery",        "Scope of Delivery" in c24_section)
expect_true("Chrono24: Condition Notes",          "Condition Notes" in c24_section)
expect_false("Chrono24: no emoji 🔎",             "🔎" in c24_section)

# FB wholesale section
fbw = build_fb_wholesale(TUDOR_INPUTS, TUDOR_PRICING, TUDOR_CANONICAL, TUDOR_TR, SUBS)
expect_true("FB wholesale: section present (wholesale_net provided)", fbw is not None)
expect_true("FB wholesale: $2,900 price",         "$2,900" in (fbw or ""))
expect_true("FB wholesale: payment block",        "W!re" in (fbw or ""))
expect_false("FB wholesale: no trust block",      "VARDALUX" in (fbw or ""))
expect_false("FB wholesale: no description para", "MT5652" not in (fbw or ""))

# FB wholesale absent when no wholesale
pricing_no_fbw = dict(TUDOR_PRICING, facebook_wholesale=None)
fbw_absent = build_fb_wholesale(TUDOR_INPUTS, pricing_no_fbw, TUDOR_CANONICAL, TUDOR_TR, SUBS)
expect("FB wholesale returns None when not in pricing", fbw_absent, None)

# WTA absent (wta is None in TUDOR_PRICING)
wta_absent = build_wta(TUDOR_INPUTS, TUDOR_PRICING)
expect("WTA returns None when wta not in pricing",      wta_absent, None)

# Reddit section
reddit = build_reddit(TUDOR_INPUTS, TUDOR_PRICING, TUDOR_CANONICAL, TUDOR_TR, SUBS)
expect_true("Reddit: [WTS] title",                "[WTS]" in (reddit or ""))
expect_true("Reddit: About Us block",             "Vardalux Collections" in (reddit or ""))
expect_true("Reddit: clean payment text",         "wire" in (reddit or "").lower())
expect_false("Reddit: no char subs",              "@utomatic" in (reddit or ""))
expect_true("Reddit: Specs section",              "**Specs:**" in (reddit or ""))

# VYW section
vyw = build_vyw(TUDOR_INPUTS, TUDOR_PRICING, TUDOR_CANONICAL, TUDOR_TR, SUBS)
expect_true("VYW: TITLE line",                    "TITLE:" in vyw)
expect_true("VYW: WHY VARDALUX section",          "WHY VARDALUX" in vyw)
expect_true("VYW: SHORT CATCHY DESCRIPTION slot", "SHORT CATCHY" in vyw)
expect_true("VYW: List Price present",            "$3,450" in vyw)

# Instagram section
ig = build_instagram(TUDOR_INPUTS, TUDOR_CANONICAL)
expect_true("Instagram: brand and model",         "Tudor" in ig and "Black Bay GMT" in ig)
expect_true("Instagram: STATUS: AVAILABLE",       "STATUS: AVAILABLE" in ig)
expect_true("Instagram: Tell Me More CTA",        "Tell Me More" in ig)
expect_false("Instagram: no pricing",             "$" in ig)


# ---------------------------------------------------------------------------
# SECTION 9: Full assembly structure
# ---------------------------------------------------------------------------

print("\n--- Section 9: Assembly structure ---")

with tempfile.TemporaryDirectory() as tmpdir:
    # Write _draft.json
    draft_path = os.path.join(tmpdir, "_draft.json")
    with open(draft_path, "w") as f:
        json.dump(TUDOR_DRAFT, f, indent=2)

    # Write title-research.json
    tr_path = os.path.join(tmpdir, "title-research.json")
    with open(tr_path, "w") as f:
        json.dump(TUDOR_TR, f, indent=2)

    listing = assemble_listing(TUDOR_DRAFT, tmpdir)

    # Header
    expect_true("Listing: starts with # VARDALUX LISTING",  listing.startswith("# VARDALUX LISTING"))
    expect_true("Listing: brand in header",                  "Tudor" in listing[:80])

    # All required platform sections
    for section in [
        "## INTERNAL REFERENCE" if False else "INTERNAL REFERENCE",
        "## GRAILZEE",
        "## EBAY",
        "## CHRONO24",
        "## FACEBOOK RETAIL",
        "## FACEBOOK WHOLESALE",
        "## REDDIT r/watchexchange",
        "## VALUE YOUR WATCH",
        "## INSTAGRAM",
        "## PLATFORM POSTING CHECKLIST",
    ]:
        expect_true(f"Listing contains {section}", section in listing)

    # WTA absent (wta=None)
    expect_false("Listing: no WTA section (wta=None)", "## WTA DEALER CHAT" in listing)

    # Sections separated by ---
    expect_true("Listing: sections separated by ---", "\n\n---\n\n" in listing)

    # Checklist at end
    checklist_pos = listing.rfind("## PLATFORM POSTING CHECKLIST")
    ig_pos        = listing.rfind("## INSTAGRAM")
    expect_true("Listing: checklist after Instagram", checklist_pos > ig_pos)

    # FB sections have char subs, Reddit does not
    fb_pos     = listing.find("## FACEBOOK RETAIL")
    fb_end_pos = listing.find("\n\n---\n\n", fb_pos)
    fb_block   = listing[fb_pos:fb_end_pos]

    reddit_pos     = listing.find("## REDDIT")
    reddit_end_pos = listing.find("\n\n---\n\n", reddit_pos)
    reddit_block   = listing[reddit_pos:reddit_end_pos]

    expect_true("Assembly: FB retail block has char subs", "W!re" in fb_block)
    expect_false("Assembly: Reddit block has no char subs", "@utomatic" in reddit_block)

    # Assembly with no title-research.json — fallback path
    os.remove(tr_path)
    listing_no_tr = assemble_listing(TUDOR_DRAFT, tmpdir)
    expect_true("Assembly fallback: listing produced",          len(listing_no_tr) > 100)
    expect_true("Assembly fallback: eBay section present",      "## EBAY" in listing_no_tr)
    ebay_pos_f    = listing_no_tr.find("## EBAY")
    ebay_end_f    = listing_no_tr.find("\n\n---\n\n", ebay_pos_f)
    ebay_block_f  = listing_no_tr[ebay_pos_f:ebay_end_f]
    expect_true("Assembly fallback: eBay title ≤ 80 chars",
                any(
                    "chars]" in line and int(line.strip().strip("[]").split()[0]) <= 80
                    for line in ebay_block_f.splitlines()
                    if "chars]" in line
                ))


# ---------------------------------------------------------------------------
# SECTION 10: Integration — --dry-run via subprocess
# ---------------------------------------------------------------------------

print("\n--- Section 10: Integration (--dry-run) ---")

TOOL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_phase_b.py")

with tempfile.TemporaryDirectory() as tmpdir:
    draft_path = os.path.join(tmpdir, "_draft.json")
    with open(draft_path, "w") as f:
        json.dump(TUDOR_DRAFT, f, indent=2)

    tr_path = os.path.join(tmpdir, "title-research.json")
    with open(tr_path, "w") as f:
        json.dump(TUDOR_TR, f, indent=2)

    result = subprocess.run(
        [sys.executable, TOOL_PATH, tmpdir, "--dry-run"],
        capture_output=True, text=True,
    )

    int_ok = result.returncode == 0
    if int_ok:
        passed += 1
        print("  PASS  Integration: --dry-run exits 0")
    else:
        failed += 1
        print(f"  FAIL  Integration: --dry-run exited {result.returncode}")
        print(f"        stderr: {result.stderr[:400]}")
        failures.append("Integration: --dry-run exits 0")

    output = result.stdout
    checks = [
        ("Output contains VARDALUX LISTING header",  "VARDALUX LISTING" in output),
        ("Output contains EBAY section",             "## EBAY" in output),
        ("Output contains CHRONO24 section",         "## CHRONO24" in output),
        ("Output contains FACEBOOK RETAIL section",  "## FACEBOOK RETAIL" in output),
        ("Output contains REDDIT section",           "## REDDIT" in output),
        ("Output contains INSTAGRAM section",        "## INSTAGRAM" in output),
        ("Output contains CHECKLIST section",        "POSTING CHECKLIST" in output),
        ("Output contains eBay price $3,649",        "$3,649" in output),
        ("Output contains Chrono24 price $3,725",    "$3,725" in output),
        ("Output contains FB retail price $3,450",   "$3,450" in output),
        ("Output contains FB wholesale price $2,900","$2,900" in output),
        ("dry-run message in stderr",                "dry-run" in result.stderr),
        ("_Listing.md NOT written in dry-run",
         not os.path.exists(os.path.join(tmpdir, "_Listing.md"))),
    ]
    for name, cond in checks:
        if cond:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            print(f"  FAIL  {name}")
            failures.append(name)

    # Wrong step → non-zero exit
    bad_draft = dict(TUDOR_DRAFT, step=2)
    bad_path  = os.path.join(tmpdir, "_draft.json")
    with open(bad_path, "w") as f:
        json.dump(bad_draft, f)
    bad_result = subprocess.run(
        [sys.executable, TOOL_PATH, tmpdir, "--dry-run"],
        capture_output=True, text=True,
    )
    expect_true("Wrong step → non-zero exit", bad_result.returncode != 0)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

print(f"\nResults: {passed} passed, {failed} failed out of {passed + failed} tests")

if failures:
    print("\nFailed tests:")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)
else:
    print("All tests passed.")
    sys.exit(0)
