#!/usr/bin/env python3
"""
test_run_checklist.py — Tests for run_checklist.py.

Run standalone: python3 test_run_checklist.py
Exits 0 on all pass, 1 if any test fails.

Sections:
  1 — Spec-required test cases (Tudor $3,200 → 7, Omega Speedmaster $4,500 → 9)
  2 — Rolex $12,000 with all optionals → 13, correct FB group selection
  3 — Price boundary cases ($5,000 / $5,050 / $9,950 / $10,000)
  4 — Brand routing (Omega non-Speedmaster, Breitling, Panerai, Hublot, unknown)
  5 — Speedmaster detection (brand+model check)
  6 — Optional platform activation (Grailzee/WTA/Reddit/Wholesale flags)
  7 — Wholesale Moda tier selection (<$10K vs ≥$10K)
  8 — Edge cases (missing pricing, no brand, Reserve grailzee)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_checklist import generate_checklist, get_price_groups, get_brand_groups, get_wholesale_groups

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


def count_platforms(checklist_str):
    """Count all checklist items (- [ ] lines, including indented sub-items)."""
    return sum(1 for line in checklist_str.splitlines() if "- [ ]" in line)


def make_pricing(fb_price, ebay=None, c24=None, fbw=None, wta_p=None, reddit_p=None, gz_format=None):
    """Build a minimal pricing dict for testing."""
    p = {
        "facebook_retail": {"list_price": fb_price},
        "ebay":            {"list_price": ebay or fb_price + 200},
        "chrono24":        {"list_price": c24  or fb_price + 150},
    }
    if fbw is not None:
        p["facebook_wholesale"] = {"list_price": fbw}
    if wta_p is not None:
        p["wta"] = {"price": wta_p, "comp": 5000, "max_allowed": 4500, "sweet_spot": 4000, "status": "OK"}
    if reddit_p is not None:
        p["reddit"] = {"list_price": reddit_p}
    if gz_format == "NR":
        p["grailzee"] = {"format": "NR", "reserve_price": None}
    elif gz_format == "Reserve":
        p["grailzee"] = {"format": "Reserve", "reserve_price": 3500}
    return p


def make_inputs(brand, model="", fb_price=None, grailzee_format=None,
                wta_price=None, reddit_price=None, wholesale_net=None, reference=""):
    i = {"brand": brand, "model": model, "reference": reference}
    if grailzee_format is not None:
        i["grailzee_format"] = grailzee_format
    if wta_price is not None:
        i["wta_price"] = wta_price
    if reddit_price is not None:
        i["reddit_price"] = reddit_price
    if wholesale_net is not None:
        i["wholesale_net"] = wholesale_net
    return i


# ---------------------------------------------------------------------------
# SECTION 1: Spec-required test cases
# ---------------------------------------------------------------------------

print("\n--- Section 1: Spec-required test cases ---")

# Tudor Black Bay at $3,200 FB retail — no optional platforms except Instagram
tudor_inputs  = make_inputs("Tudor", "Black Bay GMT", reference="79830RB")
tudor_pricing = make_pricing(3200)
tudor_cl      = generate_checklist(tudor_inputs, tudor_pricing)

expect("Tudor $3,200 → total 7 platforms", count_platforms(tudor_cl), 7)
expect_true("Tudor: eBay in checklist",                          "eBay" in tudor_cl)
expect_true("Tudor: Chrono24 in checklist",                      "Chrono24" in tudor_cl)
expect_true("Tudor: Value Your Watch in checklist",              "Value Your Watch" in tudor_cl)
expect_true("Tudor: Watch Trader Community in checklist",        "Watch Trader Community" in tudor_cl)
expect_true("Tudor $3,200: TWAT (5K or less)",                   "TWAT (5K or less)" in tudor_cl)
expect_true("Tudor $3,200: Bay Watch Under 10K",                 "Bay Watch Under 10K" in tudor_cl)
expect_false("Tudor: no TWAT Over $5K (wrong tier)",             "TWAT (Over $5K)" in tudor_cl)
expect_false("Tudor: no brand-specific section",                 "BRAND-SPECIFIC" in tudor_cl)
expect_true("Tudor: Instagram always present",                   "Instagram" in tudor_cl)
expect_false("Tudor: no Grailzee (not requested)",               "Grailzee" in tudor_cl)
expect_true("Tudor: Total platforms: 7 in output",               "Total platforms: 7" in tudor_cl)

# Omega Speedmaster at $4,500 FB retail — Instagram only (no other optionals)
omega_sp_inputs  = make_inputs("Omega", "Speedmaster Professional", reference="311.30.42.30.01.005")
omega_sp_pricing = make_pricing(4500)
omega_sp_cl      = generate_checklist(omega_sp_inputs, omega_sp_pricing)

expect("Omega Speedmaster $4,500 → total 9 platforms", count_platforms(omega_sp_cl), 9)
expect_true("Omega Speedmaster: BRAND-SPECIFIC section present",          "BRAND-SPECIFIC" in omega_sp_cl)
expect_true("Omega Speedmaster: Omega Watches Buy and Sell",              "Omega Watches Buy and Sell" in omega_sp_cl)
expect_true("Omega Speedmaster: Omega Speedmaster Buy and Sell",          "Omega Speedmaster Buy and Sell" in omega_sp_cl)
expect_true("Omega Speedmaster $4,500: TWAT (5K or less)",                "TWAT (5K or less)" in omega_sp_cl)
expect_true("Omega Speedmaster $4,500: Bay Watch Under 10K",              "Bay Watch Under 10K" in omega_sp_cl)
expect_false("Omega Speedmaster: no TWAT Over $5K (wrong tier)",          "TWAT (Over $5K)" in omega_sp_cl)
expect_true("Omega Speedmaster: Instagram always present",                "Instagram" in omega_sp_cl)
expect_true("Omega Speedmaster: Total platforms: 9 in output",            "Total platforms: 9" in omega_sp_cl)
expect_true("Omega Speedmaster: spec satisfied (count >= 9)",             count_platforms(omega_sp_cl) >= 9)


# ---------------------------------------------------------------------------
# SECTION 2: Rolex $12,000 with all optional platforms active
# ---------------------------------------------------------------------------

print("\n--- Section 2: Rolex $12,000 with all optionals → 13 platforms ---")

rolex_inputs = make_inputs(
    brand="Rolex", model="Submariner Date", reference="126610LN",
    grailzee_format="NR",
    wta_price=10500,
    reddit_price=11500,
    wholesale_net=9500,
)
rolex_pricing = make_pricing(
    fb_price=12000,
    ebay=12999,
    c24=12975,
    fbw=9500,
    wta_p=10500,
    reddit_p=11500,
    gz_format="NR",
)
rolex_cl = generate_checklist(rolex_inputs, rolex_pricing)

expect("Rolex $12,000 all optionals → total 13 platforms", count_platforms(rolex_cl), 13)

# Correct FB price tier: ≥$10K
expect_true("Rolex $12K: TWAT (Over $5K) present",                 "TWAT (Over $5K)" in rolex_cl)
expect_true("Rolex $12K: Bay Watch Club (Over $10K) present",      "Bay Watch Club (Over $10K)" in rolex_cl)
expect_false("Rolex $12K: Bay Watch Under 10K absent",             "Bay Watch Under 10K" in rolex_cl)
expect_false("Rolex $12K: TWAT (5K or less) absent",               "TWAT (5K or less)" in rolex_cl)

# No brand-specific groups for Rolex
expect_false("Rolex: no BRAND-SPECIFIC section", "BRAND-SPECIFIC" in rolex_cl)

# All optionals present
expect_true("Rolex: Grailzee (NR) in optional",               "Grailzee — No Reserve" in rolex_cl)
expect_true("Rolex: WTA Dealer Chat in optional",              "WTA Dealer Chat" in rolex_cl)
expect_true("Rolex: Reddit r/watchexchange in optional",       "Reddit r/watchexchange" in rolex_cl)
expect_true("Rolex: Facebook Wholesale in optional",           "Facebook Wholesale" in rolex_cl)
expect_true("Rolex: Watch Trading Academy sub-item",           "Watch Trading Academy" in rolex_cl)
# $12K ≥ $10K → Moda Watch Club regular (not 10k & Under)
expect_true("Rolex $12K: Moda Watch Club (regular) present",   "Moda Watch Club" in rolex_cl)
expect_false("Rolex $12K: Moda 10k & Under absent",            "10k & Under" in rolex_cl)
expect_true("Rolex: Instagram always present",                 "Instagram" in rolex_cl)
expect_true("Rolex: Total platforms: 13 in output",            "Total platforms: 13" in rolex_cl)


# ---------------------------------------------------------------------------
# SECTION 3: Price boundary cases
# ---------------------------------------------------------------------------

print("\n--- Section 3: Price boundary cases ---")

def twat_group(fb_price):
    return generate_checklist(make_inputs("Tudor", "Test"), make_pricing(fb_price))

# $5,000 — on the boundary, should be ≤5K tier
cl_5000 = twat_group(5000)
expect_true("$5,000: TWAT (5K or less)",     "TWAT (5K or less)" in cl_5000)
expect_true("$5,000: Bay Watch Under 10K",   "Bay Watch Under 10K" in cl_5000)
expect_false("$5,000: no TWAT Over $5K",     "TWAT (Over $5K)" in cl_5000)

# $5,050 — just over $5K, should be middle tier
cl_5050 = twat_group(5050)
expect_true("$5,050: TWAT (Over $5K)",       "TWAT (Over $5K)" in cl_5050)
expect_true("$5,050: Bay Watch Under 10K",   "Bay Watch Under 10K" in cl_5050)
expect_false("$5,050: no Bay Watch Club",    "Bay Watch Club" in cl_5050)

# $9,950 — just under $10K, still middle tier
cl_9950 = twat_group(9950)
expect_true("$9,950: TWAT (Over $5K)",       "TWAT (Over $5K)" in cl_9950)
expect_true("$9,950: Bay Watch Under 10K",   "Bay Watch Under 10K" in cl_9950)
expect_false("$9,950: no Bay Watch Club",    "Bay Watch Club" in cl_9950)

# $10,000 — on the ≥$10K boundary
cl_10000 = twat_group(10000)
expect_true("$10,000: TWAT (Over $5K)",             "TWAT (Over $5K)" in cl_10000)
expect_true("$10,000: Bay Watch Club (Over $10K)",  "Bay Watch Club (Over $10K)" in cl_10000)
expect_false("$10,000: no Bay Watch Under 10K",     "Bay Watch Under 10K" in cl_10000)

# Verify Tier 2 always contributes exactly 2 items at every price point
for price, label in [(3000, "$3K"), (5000, "$5K"), (5050, "$5.05K"), (10000, "$10K"), (15000, "$15K")]:
    cl = twat_group(price)
    groups = [l for l in cl.splitlines() if "TWAT" in l or "Bay Watch" in l]
    expect(f"Price-based always exactly 2 groups at {label}", len(groups), 2)


# ---------------------------------------------------------------------------
# SECTION 4: Brand routing
# ---------------------------------------------------------------------------

print("\n--- Section 4: Brand routing ---")

def brand_cl(brand, model="", fb_price=4000):
    return generate_checklist(make_inputs(brand, model), make_pricing(fb_price))

# Omega (non-Speedmaster) → 1 brand group
omega_sea_cl = brand_cl("Omega", "Seamaster 300")
expect("Omega non-Speedmaster: 1 brand group", len(get_brand_groups("Omega", "Seamaster 300")), 1)
expect_true("Omega Seamaster: Omega Buy/Sell present",          "Omega Watches Buy and Sell" in omega_sea_cl)
expect_false("Omega Seamaster: no Speedmaster group",           "Speedmaster Buy and Sell" in omega_sea_cl)
expect("Omega Seamaster total platforms", count_platforms(omega_sea_cl), 8)  # 4+2+1+1

# Breitling → 1 brand group
breitling_cl = brand_cl("Breitling", "Navitimer B01")
expect("Breitling: 1 brand group", len(get_brand_groups("Breitling", "Navitimer B01")), 1)
expect_true("Breitling: Owners and Enthusiasts present", "Breitling Owners and Enthusiasts" in breitling_cl)
expect("Breitling total platforms", count_platforms(breitling_cl), 8)  # 4+2+1+1

# Panerai → 3 brand groups
panerai_cl = brand_cl("Panerai", "Luminor Marina")
expect("Panerai: 3 brand groups", len(get_brand_groups("Panerai", "Luminor Marina")), 3)
expect_true("Panerai: Buy/Sell/Trade present",   "Panerai Watches: Buy, Sell, Trade" in panerai_cl)
expect_true("Panerai: For Sale present",         "Panerai Watches For Sale" in panerai_cl)
expect_true("Panerai: Paneristi present",        "Paneristi.com Sellers" in panerai_cl)
expect("Panerai total platforms", count_platforms(panerai_cl), 10)  # 4+2+3+1

# Hublot → 2 brand groups
hublot_cl = brand_cl("Hublot", "Big Bang")
expect("Hublot: 2 brand groups", len(get_brand_groups("Hublot", "Big Bang")), 2)
expect_true("Hublot: Buy/Sell present",    "HUBLOT Watches Buy and Sell" in hublot_cl)
expect_true("Hublot: Discussion present",  "Discuss All Things Hublot" in hublot_cl)
expect("Hublot total platforms", count_platforms(hublot_cl), 9)  # 4+2+2+1

# Rolex → 0 brand groups
expect("Rolex: 0 brand groups", len(get_brand_groups("Rolex", "Submariner")), 0)

# IWC → 0 brand groups (unknown brand)
expect("IWC: 0 brand groups", len(get_brand_groups("IWC", "Portugieser")), 0)
iwc_cl = brand_cl("IWC", "Portugieser Chronograph")
expect_false("IWC: no BRAND-SPECIFIC section", "BRAND-SPECIFIC" in iwc_cl)
expect("IWC total platforms (no brand groups)", count_platforms(iwc_cl), 7)  # 4+2+0+1


# ---------------------------------------------------------------------------
# SECTION 5: Speedmaster detection
# ---------------------------------------------------------------------------

print("\n--- Section 5: Speedmaster detection ---")

# Exact "Speedmaster" in model name
expect("Omega + 'Speedmaster Professional' → 2 groups",
       len(get_brand_groups("Omega", "Speedmaster Professional")), 2)

expect("Omega + 'Speedmaster Moonwatch' → 2 groups",
       len(get_brand_groups("Omega", "Speedmaster Moonwatch")), 2)

# Non-Speedmaster Omega models → 1 group
expect("Omega + 'Seamaster' → 1 group",
       len(get_brand_groups("Omega", "Seamaster")), 1)

expect("Omega + 'Constellation' → 1 group",
       len(get_brand_groups("Omega", "Constellation")), 1)

expect("Omega + 'De Ville' → 1 group",
       len(get_brand_groups("Omega", "De Ville")), 1)

# Non-Omega brand with "Speedmaster" in model → 0 (safety check)
expect("Tudor + 'Speedmaster-replica' → 0 (not Omega)",
       len(get_brand_groups("Tudor", "Speedmaster-replica")), 0)


# ---------------------------------------------------------------------------
# SECTION 6: Optional platform activation
# ---------------------------------------------------------------------------

print("\n--- Section 6: Optional platform activation ---")

base_inputs  = make_inputs("IWC", "Portugieser")
base_pricing = make_pricing(3200)
base_cl      = generate_checklist(base_inputs, base_pricing)
expect("No optionals: only Instagram (count=7)", count_platforms(base_cl), 7)
expect_false("No optionals: no Grailzee",   "Grailzee" in base_cl)
expect_false("No optionals: no WTA",        "WTA" in base_cl)
expect_false("No optionals: no Reddit",     "Reddit" in base_cl)
expect_false("No optionals: no Wholesale",  "Wholesale" in base_cl)
expect_true("No optionals: Instagram always present", "Instagram" in base_cl)

# Grailzee NR only
gz_inputs  = make_inputs("IWC", "Portugieser", grailzee_format="NR")
gz_pricing = make_pricing(3200, gz_format="NR")
gz_cl      = generate_checklist(gz_inputs, gz_pricing)
expect("Grailzee NR adds 1 → count 8",         count_platforms(gz_cl), 8)
expect_true("Grailzee NR: 'No Reserve' label",  "No Reserve" in gz_cl)

# Grailzee skip → not included
gz_skip_inputs  = make_inputs("IWC", "Portugieser", grailzee_format="skip")
gz_skip_pricing = make_pricing(3200)
gz_skip_cl      = generate_checklist(gz_skip_inputs, gz_skip_pricing)
expect("Grailzee skip: count unchanged (7)",  count_platforms(gz_skip_cl), 7)
expect_false("Grailzee skip: not in output",  "Grailzee" in gz_skip_cl)

# WTA only
wta_inputs  = make_inputs("IWC", "Portugieser", wta_price=2900)
wta_pricing = make_pricing(3200, wta_p=2900)
wta_cl      = generate_checklist(wta_inputs, wta_pricing)
expect("WTA adds 1 → count 8",              count_platforms(wta_cl), 8)
expect_true("WTA: Dealer Chat in output",   "WTA Dealer Chat" in wta_cl)

# Reddit only
reddit_inputs  = make_inputs("IWC", "Portugieser", reddit_price=3100)
reddit_pricing = make_pricing(3200, reddit_p=3100)
reddit_cl      = generate_checklist(reddit_inputs, reddit_pricing)
expect("Reddit adds 1 → count 8",                   count_platforms(reddit_cl), 8)
expect_true("Reddit: r/watchexchange in output",     "Reddit r/watchexchange" in reddit_cl)

# Wholesale only (under $10K) → adds 3 (header + Watch Trading Academy + Moda 10k & Under)
ws_inputs  = make_inputs("IWC", "Portugieser", wholesale_net=2700)
ws_pricing = make_pricing(3200, fbw=2700)
ws_cl      = generate_checklist(ws_inputs, ws_pricing)
expect("Wholesale adds 3 → count 10",                        count_platforms(ws_cl), 10)
expect_true("Wholesale: FB Wholesale header",                 "Facebook Wholesale" in ws_cl)
expect_true("Wholesale: Watch Trading Academy",               "Watch Trading Academy" in ws_cl)
expect_true("Wholesale <$10K: Moda 10k & Under",             "Moda Watch Club — 10k & Under" in ws_cl)


# ---------------------------------------------------------------------------
# SECTION 7: Wholesale Moda tier selection
# ---------------------------------------------------------------------------

print("\n--- Section 7: Wholesale Moda tier selection ---")

def wholesale_cl(fb_price):
    inputs  = make_inputs("IWC", "Portugieser", wholesale_net=fb_price * 0.85)
    pricing = make_pricing(fb_price, fbw=int(fb_price * 0.85))
    return generate_checklist(inputs, pricing)

# Under $10K → Moda 10k & Under
ws_5k  = wholesale_cl(5000)
ws_9k  = wholesale_cl(9950)
expect_true("$5,000 wholesale: Moda 10k & Under",    "Moda Watch Club — 10k & Under" in ws_5k)
expect_false("$5,000 wholesale: no regular Moda",    ws_5k.count("Moda Watch Club") > 1 or "10k & Under" not in ws_5k)
expect_true("$9,950 wholesale: Moda 10k & Under",    "Moda Watch Club — 10k & Under" in ws_9k)

# At and above $10K → Moda Watch Club (regular)
ws_10k = wholesale_cl(10000)
ws_15k = wholesale_cl(15000)
expect_false("$10,000 wholesale: no 10k & Under",    "10k & Under" in ws_10k)
expect_true("$10,000 wholesale: Moda Watch Club",    "Moda Watch Club" in ws_10k)
expect_false("$15,000 wholesale: no 10k & Under",    "10k & Under" in ws_15k)
expect_true("$15,000 wholesale: Moda Watch Club",    "Moda Watch Club" in ws_15k)

# Verify get_wholesale_groups directly
expect("get_wholesale_groups($4,500): Moda 10k & Under",
       get_wholesale_groups(4500)[1][0], "Moda Watch Club — 10k & Under")
expect("get_wholesale_groups($10,000): Moda regular",
       get_wholesale_groups(10000)[1][0], "Moda Watch Club")
expect("get_wholesale_groups always: Watch Trading Academy first",
       get_wholesale_groups(5000)[0][0], "Watch Trading Academy Buy/Sell/Trade Group")


# ---------------------------------------------------------------------------
# SECTION 8: Edge cases
# ---------------------------------------------------------------------------

print("\n--- Section 8: Edge cases ---")

# Missing pricing → ValueError
try:
    generate_checklist(make_inputs("Tudor", "Test"), {})
    expect("Missing pricing raises ValueError", False, True)
except ValueError as e:
    expect_true("Missing pricing raises ValueError", "facebook_retail" in str(e))

# Grailzee Reserve with reserve_price set
reserve_inputs  = make_inputs("IWC", "Portugieser", grailzee_format="Reserve")
reserve_pricing = make_pricing(3200, gz_format="Reserve")
reserve_cl      = generate_checklist(reserve_inputs, reserve_pricing)
expect_true("Grailzee Reserve: 'Reserve' label in output",  "Reserve" in reserve_cl)
expect_false("Grailzee Reserve: 'No Reserve' absent",       "No Reserve" in reserve_cl)

# Grailzee Reserve without reserve_price (TBD at gate)
reserve_no_price_inputs  = make_inputs("IWC", "Portugieser", grailzee_format="Reserve")
reserve_no_price_pricing = make_pricing(3200)  # no gz_format → no reserve_price
reserve_no_price_pricing["grailzee"] = {"format": "Reserve", "reserve_price": None}
reserve_no_price_cl = generate_checklist(reserve_no_price_inputs, reserve_no_price_pricing)
expect_true("Grailzee Reserve no price: 'TBD at gate'", "TBD at gate" in reserve_no_price_cl)

# Omega with empty model string → falls back to 1 brand group (not Speedmaster path)
omega_no_model = generate_checklist(make_inputs("Omega", ""), make_pricing(4000))
expect("Omega empty model → 1 brand group (8 total)", count_platforms(omega_no_model), 8)

# Panerai at $12,000 with all optionals → 10 base + Grailzee + WTA + Reddit + wholesale(3) = 16
panerai_all_inputs = make_inputs(
    "Panerai", "Luminor Marina",
    grailzee_format="NR", wta_price=10000, reddit_price=11000, wholesale_net=9000,
)
panerai_all_pricing = make_pricing(12000, fbw=9000, wta_p=10000, reddit_p=11000, gz_format="NR")
panerai_all_cl = generate_checklist(panerai_all_inputs, panerai_all_pricing)
# 4 universal + 2 price-based + 3 brand + 1 Instagram + 1 Grailzee + 1 WTA + 1 Reddit + 3 wholesale = 16
expect("Panerai $12K all optionals → 16 platforms", count_platforms(panerai_all_cl), 16)

# Output always ends with "Total platforms: N"
for label, cl in [("Tudor", tudor_cl), ("Omega SP", omega_sp_cl), ("Rolex all", rolex_cl)]:
    last_line = [l for l in cl.splitlines() if l.strip()][-1]
    expect_true(f"{label}: last line is 'Total platforms: N'", last_line.startswith("Total platforms:"))


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
