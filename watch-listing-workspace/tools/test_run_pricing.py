#!/usr/bin/env python3
"""
test_run_pricing.py — Unit and integration tests for run_pricing.py.

Run standalone: python3 test_run_pricing.py
Exits 0 on all pass, 1 if any test fails.

Test structure:
  Section 1 — Rounding helpers (unit)
  Section 2 — Platform calculators (unit)
  Section 3 — Tudor BB GMT 79830RB cross-validation (the key regression test)
  Section 4 — Edge cases (missing optional fields, WTA statuses, buffer override)
"""

import json
import os
import sys
import tempfile

# Import functions directly from run_pricing.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_pricing import (
    round_ebay, round_clean, round_nearest_50,
    calc_ebay, calc_chrono24, calc_facebook_retail,
    calc_facebook_wholesale, calc_wta, calc_reddit, calc_grailzee,
    format_pricing_table, load_draft, validate_draft, save_pricing,
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


def expect_none(name, actual):
    expect(name, actual, None)


def expect_key(name, d, key, expected):
    expect(name, d.get(key), expected)


# ---------------------------------------------------------------------------
# SECTION 1: Rounding helpers
# ---------------------------------------------------------------------------

print("\n--- Section 1: Rounding helpers ---")

# round_ebay: sequence is 49, 99, 149, 199, ...
expect("round_ebay: 3847 → 3849", round_ebay(3847), 3849)
expect("round_ebay: 3875 → 3899", round_ebay(3875), 3899)
expect("round_ebay: 3851 → 3849", round_ebay(3851), 3849)
expect("round_ebay: 3673.52 → 3649", round_ebay(3673.52), 3649)   # Tudor eBay raw
expect("round_ebay: 3579.40 → 3599", round_ebay(3579.40), 3599)   # IWC eBay raw
expect("round_ebay: 5542.50 → 5549", round_ebay(5542.50), 5549)   # High-value tier-3 case
expect("round_ebay: 99 → 99", round_ebay(99), 99)                  # Already on target
expect("round_ebay: 49 → 49", round_ebay(49), 49)                  # Already on target
expect("round_ebay: 100 → 99", round_ebay(100), 99)                # Just over 99, rounds back

# round_clean
expect("round_clean 25: 3730.27 → 3725", round_clean(3730.27, 25), 3725)  # Tudor Chrono24
expect("round_clean 50: 3450.50 → 3450", round_clean(3450.50, 50), 3450)  # Tudor FB retail
expect("round_clean 50: 2900 → 2900",    round_clean(2900, 50), 2900)     # Tudor FB wholesale
expect("round_clean 50: 3360 → 3350",    round_clean(3360, 50), 3350)     # IWC FB retail
expect("round_clean 25: 3632.43 → 3625", round_clean(3632.43, 25), 3625)  # IWC Chrono24

# round_nearest_50
expect("round_nearest_50: 3466.55 → 3450", round_nearest_50(3466.55), 3450)  # Tudor auto_accept
expect("round_nearest_50: 3101.65 → 3100", round_nearest_50(3101.65), 3100)  # Tudor auto_decline
expect("round_nearest_50: 3419.05 → 3400", round_nearest_50(3419.05), 3400)  # IWC auto_accept
expect("round_nearest_50: 3059.15 → 3050", round_nearest_50(3059.15), 3050)  # IWC auto_decline


# ---------------------------------------------------------------------------
# SECTION 2: Platform calculators (IWC Portugieser: retail_net=3200, buffer=5)
# ---------------------------------------------------------------------------

print("\n--- Section 2: Platform calculators (IWC Portugieser, retail_net=3200, buffer=5) ---")

# buffered = 3200 × 1.05 = 3360
# eBay fees: 125.00 + (2360 × 0.04)=94.40 + 0 = 219.40 → raw = 3579.40 → 3599
iwc_ebay = calc_ebay(3200, 5)
expect("IWC eBay list_price",    iwc_ebay["list_price"],   3599)
expect("IWC eBay auto_accept",   iwc_ebay["auto_accept"],  3400)
expect("IWC eBay auto_decline",  iwc_ebay["auto_decline"], 3050)

# Chrono24: 3360 / 0.925 = 3632.43 → round_clean(3632.43, 25) = 3625
iwc_c24 = calc_chrono24(3200, 5)
expect("IWC Chrono24 list_price", iwc_c24["list_price"], 3625)

# Facebook retail: round_clean(3360, 50) = 3350
iwc_fb = calc_facebook_retail(3200, 5)
expect("IWC Facebook retail list_price", iwc_fb["list_price"], 3350)

# Facebook wholesale
expect("FB wholesale None when missing", calc_facebook_wholesale(None), None)
expect("FB wholesale rounds to $50",     calc_facebook_wholesale(2900)["list_price"], 2900)
expect("FB wholesale 2750 → 2750",       calc_facebook_wholesale(2750)["list_price"], 2750)
expect("FB wholesale 2780 → 2800",       calc_facebook_wholesale(2780)["list_price"], 2800)

# Reddit pass-through
expect("Reddit None when missing",        calc_reddit(None), None)
expect("Reddit pass-through int",         calc_reddit(3100)["list_price"], 3100)
expect("Reddit pass-through float",       calc_reddit(3450.50)["list_price"], 3450.50)

# Grailzee
expect("Grailzee NR format",             calc_grailzee("NR")["format"], "NR")
expect("Grailzee NR reserve_price None", calc_grailzee("NR")["reserve_price"], None)
expect("Grailzee Reserve format",        calc_grailzee("Reserve")["format"], "Reserve")
expect("Grailzee Reserve price None",    calc_grailzee("Reserve")["reserve_price"], None)
expect("Grailzee skip → None",           calc_grailzee("skip"), None)
expect("Grailzee None → None",           calc_grailzee(None), None)


# ---------------------------------------------------------------------------
# SECTION 3: Tudor BB GMT 79830RB cross-validation
#
# Inputs from P&L tracker:
#   retail_net = 3350, buffer = 3%, wholesale_net = 2900,
#   wta = None, reddit = retail + buffer (3450.50), grailzee = NR
#
# These expected values were pre-computed from the formula and must match
# what the monolith would produce for this listing.
# ---------------------------------------------------------------------------

print("\n--- Section 3: Tudor BB GMT 79830RB cross-validation ---")

tudor_ebay = calc_ebay(3350, 3)
expect("Tudor eBay list_price",   tudor_ebay["list_price"],   3649)
expect("Tudor eBay auto_accept",  tudor_ebay["auto_accept"],  3450)
expect("Tudor eBay auto_decline", tudor_ebay["auto_decline"], 3100)

tudor_c24 = calc_chrono24(3350, 3)
expect("Tudor Chrono24 list_price", tudor_c24["list_price"], 3725)

tudor_fb = calc_facebook_retail(3350, 3)
expect("Tudor Facebook retail list_price", tudor_fb["list_price"], 3450)

tudor_fbw = calc_facebook_wholesale(2900)
expect("Tudor Facebook wholesale list_price", tudor_fbw["list_price"], 2900)

expect("Tudor WTA is None (not provided)", calc_wta(None, None), None)

tudor_reddit = calc_reddit(3350 * 1.03)  # retail + buffer
expect("Tudor Reddit list_price", tudor_reddit["list_price"], 3450.50)

tudor_grailzee = calc_grailzee("NR")
expect("Tudor Grailzee format",        tudor_grailzee["format"], "NR")
expect("Tudor Grailzee reserve_price", tudor_grailzee["reserve_price"], None)


# ---------------------------------------------------------------------------
# SECTION 4: Edge cases
# ---------------------------------------------------------------------------

print("\n--- Section 4: Edge cases ---")

# Buffer override (buffer=8 instead of default 5) — result must differ from default
# buffered = 3200 × 1.08 = 3456
# eBay fees: 125 + (2456×0.04=98.24) + 0 = 223.24 → raw = 3679.24 → round_ebay → 3699
ebay_buf8 = calc_ebay(3200, 8)
expect("Buffer override: eBay list differs from buffer=5", ebay_buf8["list_price"] != iwc_ebay["list_price"], True)
expect("Buffer override: eBay list_price with buffer=8", ebay_buf8["list_price"], 3699)

# High-value watch: eBay tier-3 kicks in (buffered > $5,000)
# retail_net=5000, buffer=5 → buffered=5250
# fees: 125 + 160 + (250×0.03=7.50) = 292.50 → raw=5542.50 → round_ebay → 5549
hv_ebay = calc_ebay(5000, 5)
expect("High-value eBay tier-3: list_price", hv_ebay["list_price"], 5549)

# WTA status OK (price ≤ sweet_spot)
# wta_comp=3350, sweet_spot=2680, max_allowed=3015
wta_ok = calc_wta(2600, 3350)
expect("WTA status OK",          wta_ok["status"],      "OK")
expect("WTA max_allowed (×0.90)", wta_ok["max_allowed"], 3015)
expect("WTA sweet_spot (×0.80)",  wta_ok["sweet_spot"],  2680)

# WTA status NOTE (compliant but above sweet spot)
wta_note = calc_wta(2900, 3350)
expect("WTA status NOTE", wta_note["status"], "NOTE")

# WTA status OVER (exceeds max_allowed)
wta_over = calc_wta(3200, 3350)
expect("WTA status OVER", wta_over["status"], "OVER")

# WTA rounding: comp=3333, max=round(3333×0.90)=round(2999.70)=3000, sweet=round(3333×0.80)=round(2666.40)=2666
wta_round = calc_wta(2500, 3333)
expect("WTA max_allowed rounds correctly", wta_round["max_allowed"], 3000)
expect("WTA sweet_spot rounds correctly",  wta_round["sweet_spot"],  2666)

# Grailzee skip → None
expect("Grailzee skip excluded from pricing", calc_grailzee("skip"), None)

# All optional platforms absent → all None
expect("All optionals None: wholesale", calc_facebook_wholesale(None), None)
expect("All optionals None: wta",       calc_wta(None, None), None)
expect("All optionals None: reddit",    calc_reddit(None), None)
expect("All optionals None: grailzee",  calc_grailzee(None), None)


# ---------------------------------------------------------------------------
# SECTION 5: Integration — full pipeline via temp _draft.json
# ---------------------------------------------------------------------------

print("\n--- Section 5: Integration (temp folder with _draft.json) ---")

TUDOR_DRAFT = {
    "step": 1,
    "timestamp": "2026-04-11T00:00:00Z",
    "inputs": {
        "internal_ref": "79830RB-TEST",
        "model_ref": "79830RB",
        "brand": "Tudor",
        "model": "Black Bay GMT",
        "reference": "79830RB",
        "retail_net": 3350,
        "buffer": 3,
        "wholesale_net": 2900,
        "wta_price": None,
        "wta_comp": None,
        "reddit_price": 3450.50,
        "grailzee_format": "NR",
        "tier": 1,
        "condition": "Excellent",
        "included": "Box and papers",
        "year": "2024",
        "case_size": "41mm",
        "case_material": "Stainless Steel",
        "movement": "MT5652",
    },
    "watchtrack": {
        "cost_basis": 2700,
        "recent_comps": [3200, 3350, 3100],
        "serial": "TB123456",
        "notes": "Retail NET $3,350",
    },
    "approved": {
        "photos": {
            "status": "approved",
            "notes": "Strong set.",
            "timestamp": "2026-04-11T00:00:00Z",
        }
    },
}

with tempfile.TemporaryDirectory() as tmpdir:
    draft_path = os.path.join(tmpdir, "_draft.json")
    with open(draft_path, "w") as f:
        json.dump(TUDOR_DRAFT, f, indent=2)

    # Run the tool (--dry-run so it doesn't call draft_save.py subprocess)
    import subprocess as sp
    tool_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_pricing.py")
    result = sp.run(
        [sys.executable, tool_path, tmpdir, "--dry-run"],
        capture_output=True, text=True,
    )

    int_ok = result.returncode == 0
    if int_ok:
        passed += 1
        print(f"  PASS  Integration: --dry-run exits 0")
    else:
        failed += 1
        print(f"  FAIL  Integration: --dry-run exited {result.returncode}")
        print(f"        stdout: {result.stdout[:300]}")
        print(f"        stderr: {result.stderr[:300]}")
        failures.append("Integration: --dry-run exits 0")

    # Check that the table output contains key prices
    output = result.stdout
    checks = [
        ("Tudor eBay price in table",          "$3,649" in output),
        ("Tudor Chrono24 price in table",       "$3,725" in output),
        ("Tudor FB retail price in table",      "$3,450" in output),
        ("Tudor FB wholesale price in table",   "$2,900" in output),
        ("Tudor Reddit price in table",         "$3,450" in output),
        ("Dry-run message in output",           "dry-run" in output),
        ("No WTA row when wta=None",            "WTA" not in output),
    ]
    for name, cond in checks:
        if cond:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            print(f"  FAIL  {name}")
            failures.append(name)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

print(f"\nResults: {passed} passed, {failed} failed out of {passed + failed} tests")

if failures:
    print("\nFailed tests:")
    for f_name in failures:
        print(f"  - {f_name}")
    sys.exit(1)
else:
    print("All tests passed.")
    sys.exit(0)
