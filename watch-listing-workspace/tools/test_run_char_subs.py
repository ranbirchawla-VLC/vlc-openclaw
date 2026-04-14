#!/usr/bin/env python3
"""
test_run_char_subs.py — Tests for run_char_subs.py.

Run standalone: python3 test_run_char_subs.py
Exits 0 on all pass, 1 if any test fails.

Sections:
  1 — Table loading and ordering
  2 — needs_substitution() platform check
  3 — Spec-required sample: Omega Speedmaster + automatic + Wire/Zelle + warranty + Papers
  4 — No substitutions on WTA and Reddit
  5 — Brand substitutions (single and compound)
  6 — Case sensitivity
  7 — Edge cases
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_char_subs import (
    load_substitutions, apply_substitutions, needs_substitution,
    SUBS_PATH,
)

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
    expect(name, cond, True)


def expect_false(name, cond):
    expect(name, cond, False)


# Load table once for all tests
SUBS = load_substitutions(SUBS_PATH)
SUBS_DICT = dict(SUBS)  # for spot-checking individual entries


# ---------------------------------------------------------------------------
# SECTION 1: Table loading and ordering
# ---------------------------------------------------------------------------

print("\n--- Section 1: Table loading and ordering ---")

# 35 entries expected (USDT skipped — "No substitution needed")
expect("Entry count is 35 (USDT excluded)", len(SUBS), 35)

# Longest entry must come first
expect("First entry is Jaeger-LeCoultre (len 16)", SUBS[0][0], "Jaeger-LeCoultre")
expect("First entry substitution",                 SUBS[0][1], "Ja3ger-LeC0ultre")

# Second longest
expect("Second entry is Audemars Piguet (len 15)", SUBS[1][0], "Audemars Piguet")

# Third longest
expect("Third entry is Patek Philippe (len 14)",   SUBS[2][0], "Patek Philippe")

# Shortest entries are last (IWC and fee, both len 3)
last_keys = {SUBS[-1][0], SUBS[-2][0]}
expect_true("Last two entries are IWC and fee (len 3)", last_keys == {"IWC", "fee"})

# USDT must not be in the table
expect_false("USDT is not in substitution table", "USDT" in SUBS_DICT)

# Spot-check individual entries from each section of the markdown
expect("Omega → Om3ga",              SUBS_DICT.get("Omega"),      "Om3ga")
expect("Rolex → R0lex",              SUBS_DICT.get("Rolex"),      "R0lex")
expect("IWC → !WC",                  SUBS_DICT.get("IWC"),        "!WC")
expect("automatic → @utomatic",      SUBS_DICT.get("automatic"),  "@utomatic")
expect("warranty → w@rranty",        SUBS_DICT.get("warranty"),   "w@rranty")
expect("Wire → W!re",                SUBS_DICT.get("Wire"),       "W!re")
expect("Zelle → Z3lle",              SUBS_DICT.get("Zelle"),      "Z3lle")
expect("fee → f33",                  SUBS_DICT.get("fee"),        "f33")
expect("Papers → P@pers",            SUBS_DICT.get("Papers"),     "P@pers")
expect("Speedmaster → Sp33dmaster",  SUBS_DICT.get("Speedmaster"), "Sp33dmaster")
expect("Royal Oak → R0yal 0ak",      SUBS_DICT.get("Royal Oak"),  "R0yal 0ak")

# Verify descending length order throughout (no entry longer than its predecessor)
lengths = [len(k) for k, _ in SUBS]
expect_true("All entries sorted descending by key length",
            all(lengths[i] >= lengths[i + 1] for i in range(len(lengths) - 1)))


# ---------------------------------------------------------------------------
# SECTION 2: needs_substitution() platform check
# ---------------------------------------------------------------------------

print("\n--- Section 2: needs_substitution() ---")

expect_true("facebook_retail → True",     needs_substitution("facebook_retail"))
expect_true("facebook_wholesale → True",  needs_substitution("facebook_wholesale"))
expect_false("wta → False",               needs_substitution("wta"))
expect_false("reddit → False",            needs_substitution("reddit"))
expect_false("ebay → False",              needs_substitution("ebay"))
expect_false("chrono24 → False",          needs_substitution("chrono24"))
expect_false("grailzee → False",          needs_substitution("grailzee"))
expect_false("value_your_watch → False",  needs_substitution("value_your_watch"))
expect_false("instagram → False",         needs_substitution("instagram"))


# ---------------------------------------------------------------------------
# SECTION 3: Spec-required sample
#
# Input contains: "Omega Speedmaster" + "automatic" + "Wire or Zelle"
#                 + "warranty" + "Papers"
# Every one of these must be substituted on a Facebook platform.
# ---------------------------------------------------------------------------

print("\n--- Section 3: Spec-required sample (all 8 substitutions) ---")

SAMPLE_INPUT = (
    "The Omega Speedmaster is an automatic chronograph with a lifetime warranty. "
    "Wire or Zelle preferred. Papers included."
)

SAMPLE_EXPECTED = (
    "The Om3ga Sp33dmaster is an @utomatic chr0nograph with a lifetime w@rranty. "
    "W!re or Z3lle preferred. P@pers included."
)

result = apply_substitutions(SAMPLE_INPUT, SUBS)

expect("Full sample substitution matches expected", result, SAMPLE_EXPECTED)

# Verify each substitution individually in the output
expect_true("Omega → Om3ga in output",           "Om3ga" in result)
expect_true("Speedmaster → Sp33dmaster in output", "Sp33dmaster" in result)
expect_true("automatic → @utomatic in output",   "@utomatic" in result)
expect_true("chronograph → chr0nograph in output", "chr0nograph" in result)
expect_true("warranty → w@rranty in output",     "w@rranty" in result)
expect_true("Wire → W!re in output",             "W!re" in result)
expect_true("Zelle → Z3lle in output",           "Z3lle" in result)
expect_true("Papers → P@pers in output",         "P@pers" in result)

# None of the originals should remain
expect_false("'Omega' (unsubstituted) absent from output",      "Omega" in result)
expect_false("'Speedmaster' absent from output",                "Speedmaster" in result)
expect_false("'automatic' absent from output",                  "automatic" in result)
expect_false("'chronograph' absent from output",                "chronograph" in result)
expect_false("'warranty' absent from output",                   "warranty" in result)
expect_false("'Wire' absent from output",                       "Wire" in result)
expect_false("'Zelle' absent from output",                      "Zelle" in result)
expect_false("'Papers' absent from output",                     "Papers" in result)


# ---------------------------------------------------------------------------
# SECTION 4: No substitutions on WTA and Reddit
# ---------------------------------------------------------------------------

print("\n--- Section 4: No substitutions on WTA / Reddit ---")

# needs_substitution returns False → caller skips apply_substitutions entirely.
# We also verify apply_substitutions with an empty subs list gives the original
# (simulates what happens when the caller respects needs_substitution).

for platform in ("wta", "reddit", "ebay", "chrono24"):
    expect_false(
        f"{platform}: needs_substitution is False",
        needs_substitution(platform),
    )

# Simulate the caller pattern: only apply if needs_substitution is True
def maybe_substitute(text, platform):
    if needs_substitution(platform):
        return apply_substitutions(text, SUBS)
    return text

wta_result    = maybe_substitute(SAMPLE_INPUT, "wta")
reddit_result = maybe_substitute(SAMPLE_INPUT, "reddit")
ebay_result   = maybe_substitute(SAMPLE_INPUT, "ebay")

expect("WTA: text unchanged",    wta_result,    SAMPLE_INPUT)
expect("Reddit: text unchanged", reddit_result, SAMPLE_INPUT)
expect("eBay: text unchanged",   ebay_result,   SAMPLE_INPUT)

# Facebook still substitutes through the same helper
fb_result = maybe_substitute(SAMPLE_INPUT, "facebook_retail")
expect_true("facebook_retail: Om3ga present", "Om3ga" in fb_result)


# ---------------------------------------------------------------------------
# SECTION 5: Brand substitutions — single and compound
# ---------------------------------------------------------------------------

print("\n--- Section 5: Brand substitutions ---")

# Single-word brands
for clean, sub in [
    ("Rolex",     "R0lex"),
    ("Tudor",     "Tud0r"),
    ("Omega",     "Om3ga"),
    ("Breitling", "Br3itling"),
    ("IWC",       "!WC"),
    ("Panerai",   "Pan3rai"),
    ("Hublot",    "Hubl0t"),
    ("Cartier",   "Cart!er"),
]:
    expect(f"{clean} → {sub}", apply_substitutions(clean, SUBS), sub)

# Multi-word / compound brands (longest-first ordering protects these)
expect("Jaeger-LeCoultre → Ja3ger-LeC0ultre",
       apply_substitutions("Jaeger-LeCoultre", SUBS), "Ja3ger-LeC0ultre")

expect("Audemars Piguet → Aud3mars P!guet",
       apply_substitutions("Audemars Piguet", SUBS), "Aud3mars P!guet")

expect("Patek Philippe → Pat3k Phil!ppe",
       apply_substitutions("Patek Philippe", SUBS), "Pat3k Phil!ppe")

expect("TAG Heuer → T@G Heuer",
       apply_substitutions("TAG Heuer", SUBS), "T@G Heuer")

expect("Royal Oak → R0yal 0ak",
       apply_substitutions("Royal Oak", SUBS), "R0yal 0ak")

# Multi-brand in one string
expect("Rolex Tudor Omega → R0lex Tud0r Om3ga",
       apply_substitutions("Rolex Tudor Omega", SUBS), "R0lex Tud0r Om3ga")

# Model-specific
for clean, sub in [
    ("Speedmaster", "Sp33dmaster"),
    ("Seamaster",   "S3amaster"),
    ("Submariner",  "Submar!ner"),
    ("Daytona",     "Dayt0na"),
    ("Datejust",    "Dat3just"),
    ("Navitimer",   "Nav!timer"),
    ("Superocean",  "Sup3rocean"),
    ("Aquanaut",    "Aqu@naut"),
    ("Nautilus",    "N@utilus"),
    ("Royal Oak",   "R0yal 0ak"),
    ("Pilot's",     "P!lot's"),
    ("Prince",      "Pr!nce"),
]:
    expect(f"{clean} → {sub}", apply_substitutions(clean, SUBS), sub)

# Technical terms
for clean, sub in [
    ("automatic",   "@utomatic"),
    ("chronograph", "chr0nograph"),
    ("calibre",     "c@libre"),
    ("caliber",     "c@liber"),
    ("warranty",    "w@rranty"),
]:
    expect(f"{clean} → {sub}", apply_substitutions(clean, SUBS), sub)

# Payment block (the exact format used in listings)
PAYMENT_BLOCK = "Wire or Zelle preferred (under $5K). USDT (crypto) and CC (+4.5% fee) available."
PAYMENT_EXPECTED = "W!re or Z3lle preferred (under $5K). USDT (crypto) and CC (+4.5% f33) available."
expect("Full payment block substitution", apply_substitutions(PAYMENT_BLOCK, SUBS), PAYMENT_EXPECTED)

expect_true("USDT unchanged in payment block (no sub)",
            "USDT" in apply_substitutions(PAYMENT_BLOCK, SUBS))


# ---------------------------------------------------------------------------
# SECTION 6: Case sensitivity
# ---------------------------------------------------------------------------

print("\n--- Section 6: Case sensitivity ---")

# Key is lowercase "automatic" — only lowercase matches
expect("'automatic' (lower) → '@utomatic'",
       apply_substitutions("automatic movement", SUBS), "@utomatic movement")
expect("'Automatic' (capital) unchanged",
       apply_substitutions("Automatic movement", SUBS), "Automatic movement")
expect("'AUTOMATIC' (upper) unchanged",
       apply_substitutions("AUTOMATIC movement", SUBS), "AUTOMATIC movement")

# Key is "warranty" (lowercase) — only lowercase matches
expect("'warranty' (lower) → 'w@rranty'",
       apply_substitutions("warranty included", SUBS), "w@rranty included")
expect("'Warranty' (capital) unchanged",
       apply_substitutions("Warranty included", SUBS), "Warranty included")

# Key is "Papers" (capital P) — matches, lowercase does not
expect("'Papers' (capital P) → 'P@pers'",
       apply_substitutions("Papers included", SUBS), "P@pers included")
expect("'papers' (lower) unchanged",
       apply_substitutions("papers included", SUBS), "papers included")

# Key is "Wire" (capital W) — matches
expect("'Wire' (capital W) → 'W!re'",
       apply_substitutions("Wire transfer", SUBS), "W!re transfer")
expect("'wire' (lower) unchanged",
       apply_substitutions("wire transfer", SUBS), "wire transfer")

# Key is "Omega" (capital O) — matches, lowercase does not
expect("'Omega' → 'Om3ga'",
       apply_substitutions("Omega watch", SUBS), "Om3ga watch")
expect("'omega' (lower) unchanged",
       apply_substitutions("omega watch", SUBS), "omega watch")

# IWC: all caps key
expect("'IWC' → '!WC'",
       apply_substitutions("IWC Pilot's Watch", SUBS), "!WC P!lot's Watch")
expect("'iwc' (lower) unchanged",
       apply_substitutions("iwc pilot's watch", SUBS), "iwc pilot's watch")


# ---------------------------------------------------------------------------
# SECTION 7: Edge cases
# ---------------------------------------------------------------------------

print("\n--- Section 7: Edge cases ---")

# Empty string
expect("Empty string → empty string", apply_substitutions("", SUBS), "")

# No matches — text returned unchanged
no_match = "This listing has no substitutable terms."
expect("No matches → original unchanged", apply_substitutions(no_match, SUBS), no_match)

# 'fee' is substring risk — appears in "coffee" but word-boundary is not enforced
# per spec ("case-sensitive string replacement, not regex")
# Document the actual behaviour: "coffee" → "coff33"
coffee_result = apply_substitutions("coffee", SUBS)
expect("'fee' sub applies inside 'coffee' (known behaviour, no word boundaries)",
       coffee_result, "coff33")

# Substitution is idempotent when applied twice (no chain-substitution)
# e.g. "W!re" after first pass — if applied again, "W!re" has no key match
once  = apply_substitutions(SAMPLE_INPUT, SUBS)
twice = apply_substitutions(once, SUBS)
expect("apply_substitutions is idempotent (second pass changes nothing)", once, twice)

# Valve substitution (Document / Accessory section)
expect("Valve → V@lve", apply_substitutions("helium escape Valve", SUBS),
       "helium escape V@lve")

# Omega Speedmaster together — both subs apply regardless of order
# (they don't overlap so result is the same either way)
omega_speed = apply_substitutions("Omega Speedmaster Professional", SUBS)
expect("Omega Speedmaster → Om3ga Sp33dmaster Professional", omega_speed,
       "Om3ga Sp33dmaster Professional")


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
