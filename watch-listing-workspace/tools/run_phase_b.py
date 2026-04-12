#!/usr/bin/env python3
"""
run_phase_b.py — Platform listing assembler.

Reads _draft.json (step 3.5) + title-research.json (optional) and assembles
the complete multi-platform listing document (_Listing.md).

Usage:
  python3 run_phase_b.py /path/to/listing_folder
  python3 run_phase_b.py /path/to/listing_folder --dry-run

Output:
  _Listing.md written to the listing folder
  _draft.json step updated to 4 (via draft_save.py)

Requires: step 3.5 (Grailzee gate resolved, canonical descriptions written).

Imports run_char_subs and run_checklist directly — no reimplementation.
Trust/payment blocks for Facebook are stored pre-substituted (fixed strings).
Only LLM-written canonical fields run through apply_substitutions().
"""

import json
import os
import subprocess
import sys

TOOLS_DIR   = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(TOOLS_DIR, "..", "schema", "draft_schema.json")

sys.path.insert(0, TOOLS_DIR)
from run_char_subs import apply_substitutions, load_substitutions, SUBS_PATH
from run_checklist import generate_checklist

_SUBS = None


def _get_subs() -> list:
    global _SUBS
    if _SUBS is None:
        _SUBS = load_substitutions(SUBS_PATH)
    return _SUBS


# ---------------------------------------------------------------------------
# Trust blocks (per platform)
# FB text is pre-substituted — it is a fixed string, not LLM-generated.
# ---------------------------------------------------------------------------

TRUST_BLOCKS: dict[str, str | None] = {
    "ebay": (
        "VARDALUX: We verify condition and functionality before listing. "
        "Every watch includes our 1-year movement warranty. "
        "Established 2021. Questions? Message us anytime."
    ),
    "chrono24":           None,   # lives in seller profile
    "facebook_retail":    "We verify condition and functionality. Please review the photos. Includes our 1-year movement w@rranty.",
    "facebook_wholesale": None,
    "value_your_watch":   "Established 2021. Based in Colorado. Fast, insured shipping.",
    "instagram":          None,
    "grailzee":           None,
    "wta":                None,
    "reddit": (
        "Vardalux Collections is a luxury timepiece dealer based in Colorado. "
        "We verify condition and functionality before listing and include a "
        "1-year movement warranty on every watch. Established 2021. Positive "
        "references on eBay, Chrono24, Google, and across the watch community. "
        "Happy to connect via phone or video call."
    ),
}

# ---------------------------------------------------------------------------
# Payment blocks (per platform)
# FB blocks are pre-substituted fixed strings.
# ---------------------------------------------------------------------------

PAYMENT_BLOCKS: dict[str, str | None] = {
    "facebook_retail":    "W!re or Z3lle preferred (under $5K). USDT (crypto) and CC (+4.5% f33) available.\nShips fast from Colorado.",
    "facebook_wholesale": "W!re or Z3lle preferred (under $5K). USDT (crypto) and CC (+4.5% f33) available.\nShips fast from Colorado.",
    "reddit":             "Payment via wire or Zelle. CC available (+4.5% fee).",
    "wta":                "Wire, Zelle, USDT, CC (+4.5% fee)",
    "ebay":               None,
    "chrono24":           None,
    "value_your_watch":   None,
    "instagram":          None,
    "grailzee":           None,
}

# ---------------------------------------------------------------------------
# Absolute Do Not checks
# Applied only to LLM-written canonical fields, not to hardcoded template text.
# ---------------------------------------------------------------------------

_DO_NOT_CHECKS: list[tuple[str, object, str]] = [
    ("Mint",          lambda t: "Mint" in t,            '"Mint" is forbidden — use Excellent / Very Good / Good'),
    ("em-dash",       lambda t: "\u2014" in t,          'Em-dash \u201c\u2014\u201d is forbidden — use a hyphen or rewrite'),
    ("delve",         lambda t: "delve" in t.lower(),   '"delve" is an AI tell — remove it'),
    ("Buy now!",      lambda t: "Buy now!" in t,        '"Buy now!" is forbidden'),
    ("Limited time!", lambda t: "Limited time!" in t,   '"Limited time!" is forbidden'),
    ("DM for price",  lambda t: "DM for price" in t,    '"DM for price" is forbidden'),
    ("Grand Seiko",   lambda t: "Grand Seiko" in t,     '"Grand Seiko" must never be suggested'),
    ("mistakes",      lambda t: "mistake" in t.lower(), 'Forbidden framing: "mistakes" language'),
]


def validate_do_nots(canonical: dict) -> None:
    """Raise ValueError if any LLM-written canonical field violates an Absolute Do Not."""
    combined = " ".join(
        canonical.get(k, "") or ""
        for k in ("description", "condition_line", "grailzee_desc")
    )
    for _name, check_fn, msg in _DO_NOT_CHECKS:
        if check_fn(combined):
            raise ValueError(f"Absolute Do Not violation — {msg}")


# ---------------------------------------------------------------------------
# Title generation
# ---------------------------------------------------------------------------

def load_title_research(folder: str) -> dict | None:
    path = os.path.join(folder, "title-research.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_keywords(title_research: dict) -> tuple[list, list, list]:
    rec = title_research.get("recommended_title_keywords", {})
    return (
        rec.get("priority_1_must_include",    []),
        rec.get("priority_2_high_value",      []),
        rec.get("priority_3_if_space_allows", []),
    )


# Fallback slot order when title-research.json is absent.
# Tuple: (inputs_key, suffix_to_append_if_missing_from_value)
# Fallback title slots — movement excluded (caliber details don't belong in titles)
_FALLBACK_SLOTS: list[tuple[str, str | None]] = [
    ("brand",         None),
    ("model",         None),
    ("complications", None),
    ("nickname",      None),
    ("reference",     None),
    ("case_size",     "mm"),
    ("case_material", None),
    ("dial_color",    None),
    ("gender",        None),
]

# Completeness shorthand for titles
_COMPLETENESS_MAP = {
    "box and papers": "Box Papers",
    "box & papers":   "Box Papers",
    "b&p":            "Box Papers",
    "full set":       "Full Set",
    "watch only":     "",
}


def _completeness_suffix(included: str) -> str:
    """Return a short completeness tag for fallback titles."""
    s = included.lower() if included else ""
    for key, tag in _COMPLETENESS_MAP.items():
        if key in s:
            return tag
    if "paper" in s and "box" in s:
        return "Box Papers"
    if "paper" in s:
        return "Papers"
    if "box" in s:
        return "Box"
    return ""


def _make_fallback_base(inputs: dict) -> str:
    parts = []
    for key, suffix in _FALLBACK_SLOTS:
        val = inputs.get(key)
        if not val:
            continue
        val = str(val)
        if suffix and not val.endswith(suffix):
            val = val + suffix
        parts.append(val)
    comp = _completeness_suffix(inputs.get("included", ""))
    if comp:
        parts.append(comp)
    parts.append("Watch")
    # Trim to 80 chars from the right (drop trailing slots if needed)
    title = " ".join(parts)
    while len(title) > 80 and len(parts) > 3:
        parts.pop(-2)  # remove just before "Watch"
        title = " ".join(parts)
    return title[:80]


def _ebay_from_research(title_research: dict) -> str:
    """Greedy P1→P2→P3 pack, stop before exceeding 80 chars."""
    p1, p2, p3 = _get_keywords(title_research)
    result = ""
    for kw in p1 + p2 + p3:
        candidate = (result + " " + kw).strip()
        if len(candidate) <= 80:
            result = candidate
        else:
            break
    return result


def _joined_from_research(title_research: dict) -> str:
    """All P1+P2+P3 joined — used for Chrono24, VYW, and as base for Facebook."""
    p1, p2, p3 = _get_keywords(title_research)
    return " ".join(p1 + p2 + p3)


def _reddit_from_research(title_research: dict, pricing: dict) -> str:
    """[WTS] + P1+P2 (no P3) + price + Shipped."""
    p1, p2, _ = _get_keywords(title_research)
    kw_str = " ".join(p1 + p2)
    price = (
        ((pricing.get("reddit") or {}).get("list_price")) or
        ((pricing.get("facebook_retail") or {}).get("list_price"))
    )
    price_str = f"${price:,.0f}" if price is not None else "TBD"
    return f"[WTS] {kw_str} {price_str} Shipped"


def get_title(
    platform: str,
    title_research: dict | None,
    inputs: dict,
    pricing: dict | None = None,
    subs: list | None = None,
) -> str:
    """Return the correct title string for the given platform."""
    pricing = pricing or {}
    subs    = subs    or []

    if title_research is None:
        base = _make_fallback_base(inputs)
        match platform:
            case "ebay":
                return base[:80]
            case "facebook_retail" | "facebook_wholesale":
                return apply_substitutions(base, subs)
            case "reddit":
                price = (
                    ((pricing.get("reddit") or {}).get("list_price")) or
                    ((pricing.get("facebook_retail") or {}).get("list_price"))
                )
                price_str = f"${price:,.0f}" if price is not None else "TBD"
                return f"[WTS] {base} {price_str} Shipped"
            case _:
                return base

    match platform:
        case "ebay":
            return _ebay_from_research(title_research)
        case "chrono24" | "value_your_watch":
            return _joined_from_research(title_research)
        case "facebook_retail" | "facebook_wholesale":
            return apply_substitutions(_joined_from_research(title_research), subs)
        case "reddit":
            return _reddit_from_research(title_research, pricing)
        case _:
            return _joined_from_research(title_research)


# ---------------------------------------------------------------------------
# Key Details builder
# ---------------------------------------------------------------------------

_KEY_DETAIL_FIELDS: list[str] = [
    "included",
    "condition",
    "case_material",
    "bezel",
    "dial",
    "movement",
    "complications",
    "power_reserve",
    "bracelet_strap",
    "special_features",
]


def make_key_details(inputs: dict, canonical: dict, emoji: bool = True) -> str:
    """
    Return the Key Details block.
    emoji=True  → 🔎 prefix (eBay, Facebook)
    emoji=False → plain prefix (Chrono24)

    Tries dedicated inputs fields first; falls back to condition_detail dict
    for bezel, dial, crystal, and power_reserve when the fields are absent.
    """
    # Pull condition_detail as a dict for fallback lookups
    cd_raw = inputs.get("condition_detail")
    cd = cd_raw if isinstance(cd_raw, dict) else {}

    def _get(field: str, cd_key: str | None = None) -> str | None:
        v = inputs.get(field)
        if v and not isinstance(v, dict):
            return str(v)
        if cd_key and cd.get(cd_key):
            return str(cd[cd_key])
        return None

    parts: list[str] = []
    for field in _KEY_DETAIL_FIELDS:
        val = inputs.get(field)
        if val and not isinstance(val, dict):
            parts.append(str(val))

    # Fill missing bezel / dial from condition_detail dict
    if not inputs.get("bezel") and cd.get("bezel"):
        parts.append(f"Bezel: {cd['bezel']}")
    if not inputs.get("dial") and cd.get("dial"):
        parts.append(f"Dial: {cd['dial']}")
    if not inputs.get("power_reserve"):
        # Try to find it in movement field (e.g. '70-hour power reserve')
        movement = inputs.get("movement", "")
        import re
        m = re.search(r"(\d+)[- ]hour", movement, re.IGNORECASE)
        if m:
            parts.append(f"{m.group(1)}-hour power reserve")

    condition_line = canonical.get("condition_line", "")
    if condition_line:
        parts.append(condition_line)

    prefix = "🔎 Key Details:" if emoji else "Key Details:"
    return "\n".join([prefix] + parts)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt(price: int | float | None) -> str:
    if price is None:
        return "TBD"
    return f"${price:,.0f}"


def _bar(char: str = "━", width: int = 36) -> str:
    return char * width


def _section(title: str, char: str = "━", width: int = 36) -> str:
    b = char * width
    return f"{b}\n{title}\n{b}"


# ---------------------------------------------------------------------------
# Platform section builders
# ---------------------------------------------------------------------------

def build_internal_ref(inputs: dict, pricing: dict, watchtrack: dict) -> str:
    brand    = inputs.get("brand", "")
    model    = inputs.get("model", "")
    ref      = inputs.get("reference", "")
    year     = inputs.get("year", "")
    size     = inputs.get("case_size", "")
    material = inputs.get("case_material", "")
    movement = inputs.get("movement", "")
    included = inputs.get("included", "")

    fb_price = (pricing.get("facebook_retail") or {}).get("list_price")
    wt       = watchtrack or {}
    cost     = wt.get("cost_basis")
    serial   = wt.get("serial", "")
    notes    = wt.get("notes", "")

    rows = [
        "═══════════════════════════════════",
        "INTERNAL REFERENCE — DO NOT POST",
        "═══════════════════════════════════",
        "",
        f"Brand: {brand}",
        f"Model: {model}",
        f"Reference: {ref}",
        f"Year: {year}",
        f"Case Size: {size}mm" if size else "Case Size: —",
        f"Case Material: {material}",
        f"Movement: {movement}",
        f"Completeness: {included}",
        f"Serial: {serial}",
        "",
        f"Cost Basis: {_fmt(cost)}",
        f"Target NET: {_fmt(fb_price)}",
    ]
    if notes:
        rows += ["", f"WatchTrack Notes: {notes}"]
    return "\n".join(rows)


def build_grailzee(canonical: dict, inputs: dict, pricing: dict) -> str | None:
    grailzee_format = inputs.get("grailzee_format")
    if not grailzee_format or grailzee_format == "skip":
        return None

    gz_data = pricing.get("grailzee") or {}
    gz_fmt  = gz_data.get("format", grailzee_format)
    gz_res  = gz_data.get("reserve_price")
    desc    = canonical.get("grailzee_desc") or ""

    match gz_fmt:
        case "NR":
            format_line = "Format: No Reserve ($1 start)"
        case "Reserve":
            res_str = _fmt(gz_res) if gz_res else "TBD at gate"
            format_line = f"Format: Reserve at {res_str}"
        case _:
            format_line = f"Format: {gz_fmt}"

    return "\n".join([
        "## GRAILZEE",
        "",
        format_line,
        "",
        desc,
    ])


def build_ebay(
    inputs: dict,
    pricing: dict,
    canonical: dict,
    title_research: dict | None,
    subs: list,
) -> str:
    title   = get_title("ebay", title_research, inputs, pricing, subs)
    ebay    = pricing.get("ebay") or {}
    list_p  = ebay.get("list_price")
    accept  = ebay.get("auto_accept")
    decline = ebay.get("auto_decline")
    desc    = canonical.get("description", "")
    trust   = TRUST_BLOCKS["ebay"]

    brand    = inputs.get("brand", "")
    model    = inputs.get("model", "")
    ref      = inputs.get("reference", "")
    year     = inputs.get("year", "")
    size     = inputs.get("case_size", "")
    material = inputs.get("case_material", "")
    movement = inputs.get("movement", "")
    included = inputs.get("included", "")
    condition_detail = inputs.get("condition_detail", "")

    kd = make_key_details(inputs, canonical, emoji=True)

    has_box    = bool(included and "box" in included.lower())
    has_papers = bool(included and "paper" in included.lower())

    inc_lines = [f"✓ {brand} {model} watch (Ref: {ref})"]
    if has_box:
        inc_lines.append("✓ Original box")
    if has_papers:
        inc_lines.append("✓ Papers / warranty card")

    spec_fields = [
        f"Brand: {brand}",
        f"Model: {model}",
        f"Reference Number: {ref}",
        f"Year of Manufacture: {year}",
        f"Case Size: {size}mm" if size else "",
        f"Case Material: {material}",
        f"Movement: {movement}",
        f"With Original Box: {'Yes' if has_box else 'No'}",
        f"With Papers: {'Yes' if has_papers else 'No'}",
    ]

    rows = [
        "## EBAY",
        "",
        _section("TITLE (80 characters max):"),
        title,
        f"[{len(title)} chars]",
        "",
        _section("PRICING:"),
        f"List Price:   {_fmt(list_p)}",
        f"Auto-Accept:  {_fmt(accept)}",
        f"Auto-Decline: {_fmt(decline)}",
        "",
        _section("CONDITION FIELD:"),
        "Pre-owned",
        "",
        _section("DESCRIPTION:"),
        f"{year} {brand} {model}" if year else f"{brand} {model}",
        f"Ref: {ref}",
        "",
        kd,
        "",
        _section("WHAT'S INCLUDED"),
        "\n".join(inc_lines),
        "",
        _section("WHY THIS WATCH"),
        desc,
        "",
        _section("ABOUT VARDALUX"),
        trust,
    ]

    if condition_detail:
        rows += [
            "",
            _section("CONDITION"),
            f"Overall: {inputs.get('condition', '')}",
            "",
            condition_detail,
        ]

    rows += [
        "",
        _section("ITEM SPECIFICS"),
        "\n".join(f for f in spec_fields if f),
        "",
        "Questions? Message us anytime.",
    ]

    return "\n".join(rows)


def build_chrono24(
    inputs: dict,
    pricing: dict,
    canonical: dict,
    title_research: dict | None,
    subs: list,
) -> str:
    title    = get_title("chrono24", title_research, inputs, pricing, subs)
    c24      = pricing.get("chrono24") or {}
    list_p   = c24.get("list_price")
    desc     = canonical.get("description", "")

    brand    = inputs.get("brand", "")
    model    = inputs.get("model", "")
    ref      = inputs.get("reference", "")
    year     = inputs.get("year", "")
    included = inputs.get("included", "")
    condition_detail = inputs.get("condition_detail", "")

    kd = make_key_details(inputs, canonical, emoji=False)

    inc_items = [f"- {brand} {model} watch (Ref: {ref})"]
    for item in included.replace(" and ", ", ").split(","):
        item = item.strip()
        if item:
            inc_items.append(f"- {item}")

    rows = [
        "## CHRONO24",
        "",
        f"List Price: {_fmt(list_p)}",
        "",
        f"{year} {brand} {model}" if year else f"{brand} {model}",
        f"Reference: {ref}",
        "",
        f"Title: {title}",
        "",
        kd,
        "",
        "Description:",
        desc,
        "",
        "Scope of Delivery:",
        "\n".join(inc_items),
        "",
        "Condition Notes:",
        condition_detail if condition_detail else f"Overall: {inputs.get('condition', '')}",
    ]
    return "\n".join(rows)


def build_fb_retail(
    inputs: dict,
    pricing: dict,
    canonical: dict,
    title_research: dict | None,
    subs: list,
) -> str:
    title  = get_title("facebook_retail", title_research, inputs, pricing, subs)
    fb     = pricing.get("facebook_retail") or {}
    price  = fb.get("list_price")

    brand  = inputs.get("brand", "")
    model  = inputs.get("model", "")
    ref    = inputs.get("reference", "")
    year   = inputs.get("year", "")

    # LLM-written fields — apply substitutions here
    desc   = apply_substitutions(canonical.get("description", ""), subs)
    kd_raw = make_key_details(inputs, canonical, emoji=True)
    kd     = apply_substitutions(kd_raw, subs)

    # Pre-substituted fixed strings
    trust   = TRUST_BLOCKS["facebook_retail"]
    payment = PAYMENT_BLOCKS["facebook_retail"]

    header  = apply_substitutions(f"{year} {brand} {model}" if year else f"{brand} {model}", subs)
    ref_sub = apply_substitutions(f"Ref: {ref}", subs)

    rows = [
        "## FACEBOOK RETAIL",
        "",
        f"Title: {title}",
        "",
        header,
        ref_sub,
        f"Offered at: {_fmt(price)}",
        "",
        kd,
        "",
        desc,
        "",
        "DM if you're interested.",
        "",
        trust,
        "",
        payment,
    ]
    return "\n".join(rows)


def build_fb_wholesale(
    inputs: dict,
    pricing: dict,
    canonical: dict,
    title_research: dict | None,
    subs: list,
) -> str | None:
    fbw = pricing.get("facebook_wholesale")
    if not fbw:
        return None

    price  = fbw.get("list_price")
    brand  = inputs.get("brand", "")
    model  = inputs.get("model", "")
    ref    = inputs.get("reference", "")
    year   = inputs.get("year", "")

    kd_raw  = make_key_details(inputs, canonical, emoji=True)
    kd      = apply_substitutions(kd_raw, subs)
    payment = PAYMENT_BLOCKS["facebook_wholesale"]

    header  = apply_substitutions(f"{year} {brand} {model}" if year else f"{brand} {model}", subs)
    ref_sub = apply_substitutions(f"Ref: {ref}", subs)

    rows = [
        "## FACEBOOK WHOLESALE",
        "",
        f"Title: {get_title('facebook_wholesale', title_research, inputs, pricing, subs)}",
        "",
        header,
        ref_sub,
        _fmt(price),
        "",
        kd,
        "",
        "DM if you're interested.",
        "",
        payment,
    ]
    return "\n".join(rows)


def build_wta(inputs: dict, pricing: dict) -> str | None:
    wta = pricing.get("wta")
    if not wta:
        return None

    year     = inputs.get("year", "")
    ref      = inputs.get("reference", "")
    included = inputs.get("included", "")
    size     = inputs.get("case_size", "")
    condition_detail = inputs.get("condition_detail", "")
    price    = wta.get("price")
    status   = wta.get("status", "")
    payment  = PAYMENT_BLOCKS["wta"]

    match status:
        case "OK":
            status_note = "(at or below sweet spot)"
        case "NOTE":
            status_note = "(compliant but above sweet spot — may slow close)"
        case "OVER":
            status_note = "WARNING: OVER max allowed — reprice before posting"
        case _:
            status_note = ""

    rows = [
        "## WTA DEALER CHAT",
        "",
        f"Price: {_fmt(price)} {status_note}".strip(),
        "",
        f"Year: {year}",
        f"Reference: {ref}",
        f"Completeness: {included}",
        "Condition Notes:",
        f"  {condition_detail}" if condition_detail else "  [see photos]",
        f"Diameter: {size}mm" if size else "",
        f"Payment: {payment}",
    ]
    return "\n".join(r for r in rows if r is not None)


def build_reddit(
    inputs: dict,
    pricing: dict,
    canonical: dict,
    title_research: dict | None,
    subs: list,
) -> str | None:
    if not pricing.get("reddit"):
        return None

    title    = get_title("reddit", title_research, inputs, pricing, subs)
    price    = (pricing.get("reddit") or {}).get("list_price")

    brand    = inputs.get("brand", "")
    model    = inputs.get("model", "")
    ref      = inputs.get("reference", "")
    year     = inputs.get("year", "")
    size     = inputs.get("case_size", "")
    material = inputs.get("case_material", "")
    movement = inputs.get("movement", "")
    included = inputs.get("included", "")
    msrp     = inputs.get("msrp")
    condition_detail = inputs.get("condition_detail", "")

    desc  = canonical.get("description", "")
    trust = TRUST_BLOCKS["reddit"]
    payment = PAYMENT_BLOCKS["reddit"]

    spec_rows = [
        f"- Reference: {ref}",
        f"- Year: {year}",
        f"- Case: {size}mm {material}",
        f"- Movement: {movement}",
        f"- Completeness: {included}",
    ]
    if msrp:
        spec_rows.append(f"- MSRP: {_fmt(msrp)} + tax")

    rows = [
        "## REDDIT r/watchexchange",
        "",
        f"TITLE: {title}",
        "",
        desc,
        "",
        "**Specs:**",
        "\n".join(spec_rows),
        "",
        "**Condition:**",
        condition_detail if condition_detail else inputs.get("condition", ""),
        "",
        "**Completeness:**",
        included,
        "",
        f"**Price:** {_fmt(price)}, shipped and fully insured.",
        payment,
        "",
        "**About Us:**",
        trust,
        "",
        "[Photo album link]",
        "[Timestamp photo link]",
    ]
    return "\n".join(rows)


def build_vyw(
    inputs: dict,
    pricing: dict,
    canonical: dict,
    title_research: dict | None,
    subs: list,
) -> str:
    title    = get_title("value_your_watch", title_research, inputs, pricing, subs)
    fb       = pricing.get("facebook_retail") or {}
    price    = fb.get("list_price")
    desc     = canonical.get("description", "")
    trust    = TRUST_BLOCKS["value_your_watch"]

    brand    = inputs.get("brand", "")
    model    = inputs.get("model", "")
    ref      = inputs.get("reference", "")
    year     = inputs.get("year", "")
    size     = inputs.get("case_size", "")
    material = inputs.get("case_material", "")
    movement = inputs.get("movement", "")
    included = inputs.get("included", "")
    condition_detail = inputs.get("condition_detail", "")

    has_box    = bool(included and "box" in included.lower())
    has_papers = bool(included and "paper" in included.lower())

    spec_fields = [
        f"Brand: {brand}",
        f"Model: {model}",
        f"Reference: {ref}",
        f"Year: {year}",
        f"Case Size: {size}mm" if size else "",
        f"Case Material: {material}",
        f"Movement: {movement}",
        f"Box: {'Yes' if has_box else 'No'}",
        f"Papers: {'Yes' if has_papers else 'No'}",
    ]

    # Short catchy hook: first 2 sentences of grailzee_desc if present
    # (emotional, no specs) else first 2 sentences of description
    gz_desc  = canonical.get("grailzee_desc") or ""
    hook_src = gz_desc if gz_desc else desc
    import re
    hook_sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', hook_src) if s.strip()]
    hook = " ".join(hook_sentences[:2])
    if hook and not hook.endswith((".", "!", "?")):
        hook += "."

    rows = [
        "## VALUE YOUR WATCH",
        "",
        f"TITLE: {title}",
        f"List Price: {_fmt(price)}",
        "",
        "SHORT CATCHY DESCRIPTION:",
        hook or "[2-3 hook sentences for search results]",
        "",
        "FULL DESCRIPTION:",
        desc,
        "",
        "SPECIFICATIONS:",
        "\n".join(f for f in spec_fields if f),
        "",
        "CONDITION:",
        condition_detail if condition_detail else inputs.get("condition", ""),
        "",
        "WHY VARDALUX:",
        trust,
    ]
    return "\n".join(rows)


def build_instagram(inputs: dict, canonical: dict) -> str:
    brand = inputs.get("brand", "")
    model = inputs.get("model", "")
    ref   = inputs.get("reference", "")

    # Instagram caption: use grailzee_desc (emotional, no specs) trimmed to
    # 1 sentence. Falls back to first sentence of description if grailzee absent.
    gz   = canonical.get("grailzee_desc") or ""
    desc = canonical.get("description", "")
    source = gz if gz else desc

    import re
    # Split on sentence-ending punctuation followed by space or end-of-string
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', source) if s.strip()]
    caption = sentences[0] if sentences else ""
    if caption and not caption.endswith((".", "!", "?")):
        caption += "."

    rows = [
        "## INSTAGRAM",
        "",
        f"{brand} {model}",
        ref,
        "",
        caption or "[1-sentence caption — story and pull, no specs]",
        "",
        "STATUS: AVAILABLE",
        "",
        "Tell Me More to inquire.",
    ]
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def assemble_listing(draft: dict, folder: str) -> str:
    inputs     = draft.get("inputs",     {})
    pricing    = draft.get("pricing",    {})
    canonical  = draft.get("canonical",  {})
    watchtrack = draft.get("watchtrack", {})

    # Normalise condition_detail: if it's a dict, flatten to a readable string
    cd = inputs.get("condition_detail")
    if isinstance(cd, dict):
        lines = []
        for k, v in cd.items():
            if k != "overall" and v:
                lines.append(f"{k.capitalize()}: {v}")
        inputs = dict(inputs)  # shallow copy so we don't mutate the draft
        inputs["condition_detail"] = "\n".join(lines)

    title_research = load_title_research(folder)
    subs           = _get_subs()

    validate_do_nots(canonical)

    parts = []

    parts.append(build_internal_ref(inputs, pricing, watchtrack))

    gz = build_grailzee(canonical, inputs, pricing)
    if gz:
        parts.append(gz)

    parts.append(build_ebay(inputs, pricing, canonical, title_research, subs))
    parts.append(build_chrono24(inputs, pricing, canonical, title_research, subs))
    parts.append(build_fb_retail(inputs, pricing, canonical, title_research, subs))

    fbw = build_fb_wholesale(inputs, pricing, canonical, title_research, subs)
    if fbw:
        parts.append(fbw)

    wta = build_wta(inputs, pricing)
    if wta:
        parts.append(wta)

    reddit = build_reddit(inputs, pricing, canonical, title_research, subs)
    if reddit:
        parts.append(reddit)

    parts.append(build_vyw(inputs, pricing, canonical, title_research, subs))
    parts.append(build_instagram(inputs, canonical))

    checklist = generate_checklist(inputs, pricing)
    parts.append(f"## PLATFORM POSTING CHECKLIST\n\n{checklist}")

    brand  = inputs.get("brand", "")
    model  = inputs.get("model", "")
    ref    = inputs.get("reference", "")
    header = "# VARDALUX LISTING — " + " ".join(p for p in [brand, model, ref] if p)

    return header + "\n\n---\n\n" + "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Draft I/O
# ---------------------------------------------------------------------------

def load_draft(folder: str) -> dict:
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


def validate_draft(draft: dict) -> None:
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
        print(json.dumps({"ok": False, "error": f"Schema validation failed: {e.message}"}))
        sys.exit(1)


def validate_step(draft: dict) -> None:
    step = draft.get("step")
    if step != 3.5:
        print(json.dumps({
            "ok": False,
            "error": f"Expected step 3.5, got {step}. Run run_grailzee_gate.py first.",
        }))
        sys.exit(1)


def save_listing(folder: str, content: str) -> str:
    path = os.path.join(folder, "_Listing.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def save_draft_step(folder: str) -> None:
    draft_save = os.path.join(TOOLS_DIR, "draft_save.py")
    payload    = json.dumps({"step": 4})
    result     = subprocess.run(
        [sys.executable, draft_save, folder, payload],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(json.dumps({"ok": False, "error": f"draft_save.py failed: {result.stderr}"}))
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Assemble multi-platform listing document from _draft.json"
    )
    parser.add_argument("folder",    help="Listing folder containing _draft.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print listing to stdout; do not write files or update step")
    args = parser.parse_args()

    folder = args.folder
    if not os.path.isdir(folder):
        print(json.dumps({"ok": False, "error": f"Not a directory: {folder}"}))
        sys.exit(1)

    draft = load_draft(folder)
    validate_draft(draft)
    validate_step(draft)

    try:
        listing = assemble_listing(draft, folder)
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)

    if args.dry_run:
        print(listing)
        print("\n[dry-run: no files written]", file=sys.stderr)
        sys.exit(0)

    path = save_listing(folder, listing)
    save_draft_step(folder)

    brand = draft.get("inputs", {}).get("brand", "")
    model = draft.get("inputs", {}).get("model", "")
    print(json.dumps({"ok": True, "listing_path": path, "watch": f"{brand} {model}"}))
    sys.exit(0)


if __name__ == "__main__":
    main()
