#!/usr/bin/env python3
"""
run_checklist.py — Platform posting checklist generator.

Reads _draft.json, determines which platforms are active based on pricing,
brand, and optional flags, and outputs the formatted posting checklist.

Usage:
  python3 run_checklist.py /path/to/listing_folder

Output is printed to stdout. This tool reads from _draft.json but does NOT
write back to it — the checklist string is consumed by run_phase_b.py when
assembling the listing document.

Requires: pricing must already be calculated (step 2 complete).

Platform routing:
  Tier 1 — Universal (always):       eBay, Chrono24, Value Your Watch, Watch Trader Community
  Tier 2 — Price-based (always 2):   Two FB groups based on FB retail price
  Tier 3 — Brand-specific (0–3):     FB groups for Omega/Speedmaster/Breitling/Panerai/Hublot
  Tier 4 — Optional:                 Grailzee, WTA, Reddit, Wholesale (if active)
  Always:                            Instagram
"""

import json
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(TOOLS_DIR, "..", "schema", "draft_schema.json")


# ---------------------------------------------------------------------------
# Platform data
# ---------------------------------------------------------------------------

# Tier 2: price-based FB groups
# Each entry: (max_price_inclusive, twat_name, twat_url, baywatch_name, baywatch_url)
# None = $10K+ tier (no max)
_PRICE_TIERS = [
    (5_000,  "TWAT (5K or less)", "https://www.facebook.com/groups/388782265512153/",
              "Bay Watch Under 10K", "https://www.facebook.com/groups/911491502379901"),
    (9_999,  "TWAT (Over $5K)", "https://www.facebook.com/groups/645732992585010/",
              "Bay Watch Under 10K", "https://www.facebook.com/groups/911491502379901"),
    (None,   "TWAT (Over $5K)", "https://www.facebook.com/groups/645732992585010/",
              "Bay Watch Club (Over $10K)", "https://www.facebook.com/groups/omarbay"),
]

# Tier 3: brand-specific FB groups
# Key "Omega Speedmaster" is a sub-case of Omega — checked first.
_BRAND_GROUPS = {
    "Omega Speedmaster": [
        ("Omega Watches Buy and Sell",     "https://www.facebook.com/groups/967376425025667"),
        ("Omega Speedmaster Buy and Sell", "https://www.facebook.com/groups/317784437216258"),
    ],
    "Omega": [
        ("Omega Watches Buy and Sell", "https://www.facebook.com/groups/967376425025667"),
    ],
    "Breitling": [
        ("Breitling Owners and Enthusiasts", None),
    ],
    "Panerai": [
        ("Panerai Watches: Buy, Sell, Trade", "https://www.facebook.com/groups/1000482317936935"),
        ("Panerai Watches For Sale",          None),
        ("Paneristi.com Sellers",             None),
    ],
    "Hublot": [
        ("HUBLOT Watches Buy and Sell",                              "https://www.facebook.com/groups/6536262816386227"),
        ("Hublot Watches: Buy, Sell, Trade and Discuss All Things Hublot", None),
    ],
}

# Tier 4 wholesale: always includes Watch Trading Academy; Moda Club tier by FB price
_WHOLESALE_ALWAYS = ("Watch Trading Academy Buy/Sell/Trade Group", None)
_MODA_UNDER_10K   = ("Moda Watch Club — 10k & Under", None)
_MODA_OVER_10K    = ("Moda Watch Club", None)


# ---------------------------------------------------------------------------
# Routing helpers
# ---------------------------------------------------------------------------

def get_price_groups(fb_price):
    """Return list of (name, url) for the two price-based FB groups."""
    for max_price, twat_name, twat_url, bay_name, bay_url in _PRICE_TIERS:
        if max_price is None or fb_price <= max_price:
            return [(twat_name, twat_url), (bay_name, bay_url)]
    # Unreachable, but satisfies type checkers
    return []


def get_brand_groups(brand, model):
    """
    Return list of (name, url) for brand-specific FB groups.

    Omega Speedmaster detection: brand == "Omega" AND "Speedmaster" in model.
    Speedmasters go to BOTH the general Omega group and the Speedmaster group.
    """
    if brand == "Omega" and "Speedmaster" in (model or ""):
        return _BRAND_GROUPS["Omega Speedmaster"]
    return _BRAND_GROUPS.get(brand, [])


def get_wholesale_groups(fb_price):
    """Return list of (name, url) for wholesale FB sub-groups."""
    moda = _MODA_UNDER_10K if fb_price < 10_000 else _MODA_OVER_10K
    return [_WHOLESALE_ALWAYS, moda]


# ---------------------------------------------------------------------------
# Checklist generator
# ---------------------------------------------------------------------------

def _fmt(price):
    """Format a number as $X,XXX."""
    if price is None:
        return "TBD"
    return f"${price:,.0f}" if isinstance(price, (int, float)) else str(price)


def _item(text, url=None):
    """Format a top-level checklist item."""
    suffix = f"  ({url})" if url else ""
    return f"- [ ] {text}{suffix}"


def _sub_item(text, url=None):
    """Format an indented sub-item (e.g. wholesale FB groups)."""
    suffix = f"  ({url})" if url else ""
    return f"  - [ ] {text}{suffix}"


def generate_checklist(inputs, pricing):
    """
    Build the platform posting checklist string.

    Args:
        inputs:  dict — from _draft.json["inputs"]
        pricing: dict — from _draft.json["pricing"]

    Returns:
        Formatted checklist string (multi-line).

    Raises:
        ValueError if pricing.facebook_retail.list_price is absent.
    """
    brand           = inputs.get("brand", "")
    model           = inputs.get("model", "")
    reference       = inputs.get("reference", "")
    grailzee_format = inputs.get("grailzee_format")
    wta_price       = inputs.get("wta_price")
    reddit_price    = inputs.get("reddit_price")
    wholesale_net   = inputs.get("wholesale_net")

    fb_retail  = pricing.get("facebook_retail") or {}
    fb_price   = fb_retail.get("list_price")
    if fb_price is None:
        raise ValueError(
            "pricing.facebook_retail.list_price is required — "
            "run run_pricing.py first (step 2)"
        )

    ebay_price   = (pricing.get("ebay")               or {}).get("list_price")
    c24_price    = (pricing.get("chrono24")            or {}).get("list_price")
    fbw_price    = (pricing.get("facebook_wholesale")  or {}).get("list_price")
    wta_p        = (pricing.get("wta")                 or {}).get("price")
    reddit_p     = (pricing.get("reddit")              or {}).get("list_price")
    gz_data      = pricing.get("grailzee")             or {}
    gz_format    = gz_data.get("format", grailzee_format)
    gz_reserve   = gz_data.get("reserve_price")

    lines  = []
    count  = 0

    # --- Header ---
    parts = [p for p in [brand, model, reference] if p]
    lines.append(f"PLATFORM POSTING CHECKLIST — {' '.join(parts)}")
    lines.append("")

    # --- Tier 1: Universal ---
    lines.append("UNIVERSAL:")
    for name, price in [
        ("eBay",                       ebay_price),
        ("Chrono24",                   c24_price),
        ("Value Your Watch",           fb_price),
        ("Watch Trader Community (FB)", fb_price),
    ]:
        lines.append(_item(f"{name} — {_fmt(price)}"))
        count += 1
    lines.append("")

    # --- Tier 2: Price-based ---
    lines.append("PRICE-BASED (FB):")
    for name, url in get_price_groups(fb_price):
        lines.append(_item(f"{name} — {_fmt(fb_price)}", url))
        count += 1
    lines.append("")

    # --- Tier 3: Brand-specific ---
    brand_groups = get_brand_groups(brand, model)
    if brand_groups:
        lines.append("BRAND-SPECIFIC (FB):")
        for name, url in brand_groups:
            lines.append(_item(name, url))
            count += 1
        lines.append("")

    # --- Tier 4: Optional ---
    optional_lines = []

    grailzee_active = grailzee_format and grailzee_format != "skip"
    if grailzee_active:
        match gz_format:
            case "NR":
                optional_lines.append(_item("Grailzee — No Reserve ($1 start)"))
            case _:
                reserve_str = f" at {_fmt(gz_reserve)}" if gz_reserve else " (reserve TBD at gate)"
                optional_lines.append(_item(f"Grailzee — Reserve{reserve_str}"))
        count += 1

    if wta_price is not None:
        optional_lines.append(_item(f"WTA Dealer Chat — {_fmt(wta_p or wta_price)}"))
        count += 1

    if reddit_price is not None:
        optional_lines.append(_item(f"Reddit r/watchexchange — {_fmt(reddit_p or reddit_price)}"))
        count += 1

    if wholesale_net is not None:
        optional_lines.append(_item(f"Facebook Wholesale — {_fmt(fbw_price or wholesale_net)}"))
        count += 1
        for name, url in get_wholesale_groups(fb_price):
            optional_lines.append(_sub_item(name, url))
            count += 1

    if optional_lines:
        lines.append("OPTIONAL:")
        lines.extend(optional_lines)
        lines.append("")

    # --- Always: Instagram ---
    lines.append("ALWAYS:")
    lines.append(_item('Instagram (no pricing, "Tell Me More" CTA)'))
    count += 1
    lines.append("")

    lines.append(f"Total platforms: {count}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Draft I/O
# ---------------------------------------------------------------------------

def load_draft(folder):
    path = os.path.join(folder, "_draft.json")
    if not os.path.exists(path):
        print(json.dumps({"ok": False, "error": f"No _draft.json found in: {folder}"}))
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            print(json.dumps({"ok": False, "error": f"_draft.json is not valid JSON: {e}"}))
            sys.exit(1)


def validate_draft(draft):
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
        print(json.dumps({"ok": False, "error": f"_draft.json schema validation failed: {e.message}"}))
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: run_checklist.py /path/to/listing_folder"}))
        sys.exit(1)

    folder = sys.argv[1]
    if not os.path.isdir(folder):
        print(json.dumps({"ok": False, "error": f"Not a directory: {folder}"}))
        sys.exit(1)

    draft = load_draft(folder)
    validate_draft(draft)

    inputs  = draft.get("inputs",  {})
    pricing = draft.get("pricing", {})

    try:
        checklist = generate_checklist(inputs, pricing)
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)

    print(checklist)
    sys.exit(0)


if __name__ == "__main__":
    main()
