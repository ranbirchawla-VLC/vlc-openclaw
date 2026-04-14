#!/usr/bin/env python3
"""
run_pricing.py — Platform pricing calculator for the Vardalux listing pipeline.

Usage:
  python3 run_pricing.py /path/to/listing_folder
  python3 run_pricing.py /path/to/listing_folder --dry-run

Reads inputs from _draft.json, calculates all platform prices, writes the
pricing object back to _draft.json via draft_save.py, and prints the pricing
summary table to stdout (for the skill to post to Telegram).

Validates _draft.json against schema/draft_schema.json before operating.

Inputs consumed from _draft.json:
  inputs.retail_net       — required
  inputs.buffer           — default 5 if absent
  inputs.wholesale_net    — optional; omit pricing.facebook_wholesale if absent
  inputs.wta_price        — optional; omit pricing.wta if absent
  inputs.wta_comp         — required if wta_price is present
  inputs.reddit_price     — optional; pass-through, no calculation
  inputs.grailzee_format  — optional; "NR", "Reserve", or "skip"
  inputs.msrp             — optional; shown in Reddit row of table

Outputs written to _draft.json:
  pricing.ebay            — list_price, auto_accept, auto_decline
  pricing.chrono24        — list_price
  pricing.facebook_retail — list_price
  pricing.facebook_wholesale — list_price | null
  pricing.wta             — price, comp, max_allowed, sweet_spot, status | null
  pricing.reddit          — list_price | null
  pricing.grailzee        — format, reserve_price | null
  step                    — set to 2

TODO (pipeline.py): Cross-check wta_price against other platform prices.
  WTA compliance rule: cannot be listed lower anywhere else on the internet.
  This is a cross-platform check; run_pricing.py calculates each platform
  in isolation and does not enforce it.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(TOOLS_DIR, "..", "schema", "draft_schema.json")
DRAFT_SAVE = os.path.join(TOOLS_DIR, "draft_save.py")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def fail(msg):
    """Print error JSON to stdout and exit non-zero."""
    print(json.dumps({"ok": False, "error": msg}))
    sys.exit(1)


# ---------------------------------------------------------------------------
# Rounding helpers
# ---------------------------------------------------------------------------

def round_ebay(price):
    """
    Round to the nearest price ending in 49 or 99.

    Valid eBay prices form the sequence 49, 99, 149, 199, ... (i.e., 49 + 50k).
    Formula maps any price to the nearest element of that sequence.

    Examples:
      3847.00 → 3849   (72.49 rounds to 72)
      3875.00 → 3899   (76.52 rounds to 77)
      3924.00 → 3949   (77.50 → banker's rounds to 78)
    """
    n = round((price - 49) / 50)
    return int(49 + n * 50)


def round_clean(price, step=25):
    """
    Round to the nearest multiple of step.

    Used for:
      Chrono24:           step=25  ($X,X00 / $X,X25 / $X,X50 / $X,X75)
      Facebook retail:    step=50  (cleaner round numbers for posts)
      Facebook wholesale: step=50
      WTA max/sweet:      step=1   (plain round())
      eBay auto_accept/decline: step=50 (via round_nearest_50)
    """
    return int(round(price / step) * step)


def round_nearest_50(price):
    """Round to nearest $50. Used for eBay auto_accept and auto_decline."""
    return round_clean(price, 50)


# ---------------------------------------------------------------------------
# Platform calculators
# ---------------------------------------------------------------------------

def calc_ebay(retail_net, buffer_pct):
    """
    eBay fee structure (tiered on buffered price):
      First $1,000:         12.5%
      Next $4,000 ($1K-$5K): 4.0%
      Above $5,000:          3.0%

    list_price = buffered + total_fees, rounded to nearest $X,X49 or $X,X99
    auto_accept  = list_price × 0.95, rounded to nearest $50
    auto_decline = list_price × 0.85, rounded to nearest $50
    """
    buffered = retail_net * (1 + buffer_pct / 100)
    first_1000 = min(buffered, 1000) * 0.125
    next_4000 = min(max(buffered - 1000, 0), 4000) * 0.04
    remainder = max(buffered - 5000, 0) * 0.03
    total_fees = first_1000 + next_4000 + remainder
    list_price = round_ebay(buffered + total_fees)
    return {
        "list_price": list_price,
        "auto_accept": round_nearest_50(list_price * 0.95),
        "auto_decline": round_nearest_50(list_price * 0.85),
    }


def calc_chrono24(retail_net, buffer_pct):
    """
    Chrono24 takes 7.5% of sale price.
    Solve: buffered = list_price × (1 - 0.075)
    → list_price = buffered / 0.925, rounded to nearest $25.
    """
    buffered = retail_net * (1 + buffer_pct / 100)
    return {"list_price": round_clean(buffered / (1 - 0.075), 25)}


def calc_facebook_retail(retail_net, buffer_pct):
    """
    Facebook retail: no platform fee. list_price = buffered, rounded to $50.
    """
    buffered = retail_net * (1 + buffer_pct / 100)
    return {"list_price": round_clean(buffered, 50)}


def calc_facebook_wholesale(wholesale_net):
    """Returns None if wholesale_net is absent or null."""
    if wholesale_net is None:
        return None
    return {"list_price": round_clean(wholesale_net, 50)}


def calc_wta(wta_price, wta_comp):
    """
    WTA Dealer Chat compliance check.

    max_allowed = wta_comp × 0.90  (absolute ceiling — 10% below comp)
    sweet_spot  = wta_comp × 0.80  (recommended — 20% below comp)

    status:
      OK   — price ≤ sweet_spot
      NOTE — price > sweet_spot but ≤ max_allowed (compliant, may sit)
      OVER — price > max_allowed (admin will remove listing)

    Returns None if wta_price is absent. Fails if wta_comp is missing.
    """
    if wta_price is None:
        return None
    if wta_comp is None:
        fail("wta_price provided but wta_comp is missing — cannot calculate max_allowed or sweet_spot")
    max_allowed = round(wta_comp * 0.90)
    sweet_spot = round(wta_comp * 0.80)
    if wta_price > max_allowed:
        status = "OVER"
    elif wta_price > sweet_spot:
        status = "NOTE"
    else:
        status = "OK"
    return {
        "price": wta_price,
        "comp": wta_comp,
        "max_allowed": max_allowed,
        "sweet_spot": sweet_spot,
        "status": status,
    }


def calc_reddit(reddit_price):
    """
    Reddit r/watchexchange: pass-through. No buffer, no fees, no rounding.
    Returns None if reddit_price is absent.
    """
    if reddit_price is None:
        return None
    return {"list_price": reddit_price}


def calc_grailzee(grailzee_format):
    """
    Grailzee pricing:
      NR      → $1 start, no reserve
      Reserve → reserve_price is None here; set by user at step 3.5 gate
      skip    → None (excluded from listing)
    """
    match grailzee_format:
        case None | "skip":
            return None
        case "NR":
            return {"format": "NR", "reserve_price": None}
        case "Reserve":
            return {"format": "Reserve", "reserve_price": None}
        case _:
            fail(f"Unknown grailzee_format: {grailzee_format!r} — must be NR, Reserve, or skip")


# ---------------------------------------------------------------------------
# Pricing summary table (Telegram-ready text)
# ---------------------------------------------------------------------------

def fmt_price(price):
    """Format a number as $X,XXX with commas."""
    return f"${price:,.0f}" if isinstance(price, (int, float)) else str(price)


def format_pricing_table(pricing, inputs):
    brand = inputs.get("brand", "")
    model = inputs.get("model", "")
    header = f"PRICING SUMMARY — {brand} {model}".strip()

    rows = []

    gz = pricing.get("grailzee")
    if gz:
        note = "No-reserve, $1 start" if gz["format"] == "NR" else f"Reserve: {fmt_price(gz['reserve_price']) if gz['reserve_price'] else 'TBD at gate'}"
        rows.append(("Grailzee", "$1 start" if gz["format"] == "NR" else fmt_price(gz.get("reserve_price") or 0), note))

    eb = pricing.get("ebay", {})
    rows.append((
        "eBay",
        fmt_price(eb["list_price"]),
        f"Accept: {fmt_price(eb['auto_accept'])} / Decline: {fmt_price(eb['auto_decline'])}",
    ))

    c24 = pricing.get("chrono24", {})
    rows.append(("Chrono24", fmt_price(c24["list_price"]), ""))

    fb = pricing.get("facebook_retail", {})
    rows.append(("Facebook Retail", fmt_price(fb["list_price"]), "+4.5% CC fee"))

    fbw = pricing.get("facebook_wholesale")
    if fbw:
        rows.append(("Facebook Wholesale", fmt_price(fbw["list_price"]), "Dealer only"))

    wta = pricing.get("wta")
    if wta:
        status_icons = {"OK": "✅", "NOTE": "ℹ️", "OVER": "⚠️"}
        icon = status_icons.get(wta["status"], "")
        note = (
            f"{icon} Comp: {fmt_price(wta['comp'])} | "
            f"Max: {fmt_price(wta['max_allowed'])} | "
            f"Sweet spot: {fmt_price(wta['sweet_spot'])}"
        )
        if wta["status"] == "OVER":
            note += f" — OVER by {fmt_price(wta['price'] - wta['max_allowed'])}"
        rows.append(("WTA Dealer Chat", fmt_price(wta["price"]), note))

    reddit = pricing.get("reddit")
    if reddit:
        msrp = inputs.get("msrp")
        note = f"MSRP: {fmt_price(msrp)}" if msrp else ""
        rows.append(("Reddit", fmt_price(reddit["list_price"]), note))

    # Build table
    col_w = [max(len(r[i]) for r in rows) for i in range(3)]
    col_w[0] = max(col_w[0], len("Platform"))
    col_w[1] = max(col_w[1], len("List Price"))
    col_w[2] = max(col_w[2], len("Notes"))

    sep = f"+-{'-' * col_w[0]}-+-{'-' * col_w[1]}-+-{'-' * col_w[2]}-+"
    hdr = f"| {'Platform':<{col_w[0]}} | {'List Price':<{col_w[1]}} | {'Notes':<{col_w[2]}} |"

    lines = [header, sep, hdr, sep]
    for platform, price, note in rows:
        lines.append(f"| {platform:<{col_w[0]}} | {price:<{col_w[1]}} | {note:<{col_w[2]}} |")
    lines.append(sep)

    # WTA warning block
    if wta:
        match wta["status"]:
            case "OVER":
                lines.append("")
                lines.append(f"⚠️  WTA COMPLIANCE FAILURE")
                lines.append(f"   Your price {fmt_price(wta['price'])} exceeds the 10%-below-comp ceiling of {fmt_price(wta['max_allowed'])}.")
                lines.append(f"   Admin will remove the listing. Correct before posting.")
            case "NOTE":
                lines.append("")
                lines.append(f"ℹ️  WTA NOTE: Price is compliant but {fmt_price(wta['price'] - wta['sweet_spot'])} above sweet spot. Listing is valid but may sit.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Draft I/O
# ---------------------------------------------------------------------------

def load_draft(folder):
    path = os.path.join(folder, "_draft.json")
    if not os.path.exists(path):
        fail(f"No _draft.json found in: {folder}")
    with open(path, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            fail(f"_draft.json is not valid JSON: {e}")


def validate_draft(draft):
    """Validate draft against schema/draft_schema.json. Fails on violation."""
    if not os.path.exists(SCHEMA_PATH):
        print("WARNING: Schema not found, skipping validation.", file=sys.stderr)
        return
    try:
        import jsonschema
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.validate(instance=draft, schema=schema)
    except ImportError:
        print("WARNING: jsonschema not installed, skipping schema validation.", file=sys.stderr)
    except jsonschema.ValidationError as e:
        fail(f"_draft.json schema validation failed: {e.message}")


def save_pricing(folder, pricing):
    """Write pricing to _draft.json via draft_save.py (atomic write)."""
    if not os.path.exists(DRAFT_SAVE):
        fail(f"draft_save.py not found at: {DRAFT_SAVE}")
    patch = json.dumps({
        "step": 2,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pricing": pricing,
    })
    result = subprocess.run(
        [sys.executable, DRAFT_SAVE, folder, patch],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"draft_save.py exited with code {result.returncode}: {result.stderr.strip()}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        fail(f"draft_save.py returned non-JSON output: {result.stdout!r}")
    if not data.get("ok"):
        fail(f"draft_save.py failed: {data.get('error', 'unknown error')}")
    return data["path"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        fail("Usage: run_pricing.py /path/to/listing_folder [--dry-run]")

    folder = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    if not os.path.isdir(folder):
        fail(f"Not a directory: {folder}")

    draft = load_draft(folder)
    validate_draft(draft)

    inputs = draft.get("inputs", {})

    retail_net = inputs.get("retail_net")
    if retail_net is None:
        fail("inputs.retail_net is required — run step 1 (photos) first to collect pricing inputs")

    buffer_pct = inputs.get("buffer", 5)
    wholesale_net = inputs.get("wholesale_net")
    wta_price = inputs.get("wta_price")
    wta_comp = inputs.get("wta_comp")
    reddit_price = inputs.get("reddit_price")
    grailzee_format = inputs.get("grailzee_format")

    pricing = {
        "ebay": calc_ebay(retail_net, buffer_pct),
        "chrono24": calc_chrono24(retail_net, buffer_pct),
        "facebook_retail": calc_facebook_retail(retail_net, buffer_pct),
        "facebook_wholesale": calc_facebook_wholesale(wholesale_net),
        "wta": calc_wta(wta_price, wta_comp),
        "reddit": calc_reddit(reddit_price),
        "grailzee": calc_grailzee(grailzee_format),
    }

    table = format_pricing_table(pricing, inputs)
    print(table)

    if dry_run:
        print("\n[dry-run: _draft.json not modified]")
        sys.exit(0)

    saved_path = save_pricing(folder, pricing)
    print(f"\nDraft saved: {saved_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
