"""Phase 1 discovery runner. Parses W1+W2 xlsx, emits findings/p[1-6]_*.md.

Discovery only. Deleted after Phase 2 ship. No production code touched.
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from load import load_both, Report

FINDINGS = Path(__file__).parent / "findings"
FINDINGS.mkdir(exist_ok=True)

NR_PREFIX = "No Reserve - "
# Robust prefix regex: tolerates ASCII space, NBSP (U+00A0), and other
# whitespace after the hyphen. Phase 2 implementation must use a similar
# normalization. Literal-string startswith misses ~0.5% of NR rows where
# the source carries NBSP.
NR_PREFIX_RE = re.compile(r"^No Reserve\s*-\s*", re.UNICODE)


def is_nr(desc: Any) -> bool:
    if desc is None:
        return False
    return bool(NR_PREFIX_RE.match(str(desc)))
INCH_RE = re.compile(
    r"\d+(\.\d+)?\s*x\s*\d+(\.\d+)?(\s*x\s*\d+(\.\d+)?)?\s*IN\b",
    re.IGNORECASE,
)

CANONICAL_DIAL = {
    "No Numerals",
    "Arabic Numerals",
    "Roman Numerals",
    "Diamond Numerals",
}


def write(name: str, body: str) -> None:
    (FINDINGS / name).write_text(body)


def money(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("$", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ============================================================================
# PHASE 1: Header canonicalization map
# ============================================================================

def phase1_headers(w1: Report, w2: Report) -> None:
    lines = ["# Phase 1: Header canonicalization map", ""]
    lines.append("## Full column inventory")
    lines.append("")
    lines.append("| Position | W1 header | W2 header |")
    lines.append("|---|---|---|")
    max_cols = max(len(w1.headers), len(w2.headers))
    for i in range(max_cols):
        a = w1.headers[i] if i < len(w1.headers) else "(absent)"
        b = w2.headers[i] if i < len(w2.headers) else "(absent)"
        marker = "" if a == b else " *"
        lines.append(f"| {i+1} | `{a}`{marker} | `{b}`{marker} |")
    lines.append("")
    lines.append("Asterisk marks positions where header text differs between W1 and W2.")
    lines.append("")

    # Identify variations
    lines.append("## Variations detected")
    lines.append("")
    differs = [(i, w1.headers[i], w2.headers[i]) for i in range(max_cols)
               if i < len(w1.headers) and i < len(w2.headers)
               and w1.headers[i] != w2.headers[i]]
    for pos, a, b in differs:
        if a.lower() == b.lower():
            kind = "case-only"
        else:
            kind = "rename"
        lines.append(f"- Position {pos+1}: `{a}` (W1) vs `{b}` (W2); {kind}")
    lines.append("")

    # Proposed canonicalization map
    lines.append("## Proposed canonicalization map")
    lines.append("")
    lines.append("All downstream reads use canonical names. Source-name lookup at ingest.")
    lines.append("")
    canon_map = {
        "Sold at": "sold_at",
        "Sold At": "sold_at",
        "Auction": "auction_descriptor",
        "Make": "brand",
        "Model": "model",
        "Reference Number": "reference",
        "Sold For": "sold_for",
        "Condition": "condition",
        "Year": "year",
        "Papers": "papers",
        "Box": "box",
        "Dial": "dial_numerals",
        "Dial Numbers": "dial_numerals",
        "URL": "url",
    }
    lines.append("| Source name (any observed spelling) | Canonical name |")
    lines.append("|---|---|")
    for src, canon in canon_map.items():
        lines.append(f"| `{src}` | `{canon}` |")
    lines.append("")

    # Planned ingest fields + ordinal confirmation
    lines.append("## Planned ingest fields vs column positions")
    lines.append("")
    planned = [
        ("reference", "Reference Number", 5),
        ("auction_descriptor", "Auction", 2),
        ("brand", "Make", 3),
        ("model", "Model", 4),
        ("sold_for", "Sold For", 6),
        ("condition", "Condition", 7),
        ("year", "Year", 8),
        ("papers", "Papers", 9),
        ("box", "Box", 10),
        ("dial_numerals", "Dial / Dial Numbers", 11),
        ("sold_at", "Sold at / Sold At", 1),
    ]
    lines.append("| Canonical | Source name | Observed position (W1=W2) |")
    lines.append("|---|---|---|")
    for canon, src, pos in planned:
        lines.append(f"| `{canon}` | `{src}` | {pos} |")
    lines.append("")
    lines.append("Asset-class detection runs against `auction_descriptor` (position 2).")
    lines.append("Dial-color parse runs against `auction_descriptor` (position 2).")
    lines.append("All fields the planned ingest needs are within the first 11 columns.")
    lines.append("URL at position 12 is not an ingest field.")
    lines.append("")
    lines.append("**Ordinal-read requirement**: none past column 11. No ordinal reads")
    lines.append("past column 9 as specified by the §5 constraint would require dropping")
    lines.append("dial_numerals (position 11) and box (position 10). This is a drift")
    lines.append("finding against §5; see report Drift section.")

    write("p1_headers.md", "\n".join(lines))


# ============================================================================
# PHASE 2: Auction type parsing
# ============================================================================

def phase2_auction(w1: Report, w2: Report) -> None:
    lines = ["# Phase 2: Auction type parsing", ""]

    def classify(r: Report) -> dict:
        total = len(r.rows)
        nr = 0
        prefix_mid = 0
        blank_auction = 0
        samples_nr: list[str] = []
        samples_res: list[str] = []
        for row in r.rows:
            desc = row.get("Auction")
            if desc is None or str(desc).strip() == "":
                blank_auction += 1
                continue
            s = str(desc)
            if is_nr(s):
                nr += 1
                if len(samples_nr) < 6:
                    samples_nr.append(s)
            else:
                if "No Reserve" in s and NR_PREFIX not in s[: len("No Reserve") + 5]:
                    prefix_mid += 1
                if len(samples_res) < 6:
                    samples_res.append(s)
        return dict(total=total, nr=nr, prefix_mid=prefix_mid,
                    blank_auction=blank_auction,
                    samples_nr=samples_nr, samples_res=samples_res)

    for r in (w1, w2):
        c = classify(r)
        pct = (c["nr"] / c["total"] * 100) if c["total"] else 0
        lines.append(f"## {r.label}")
        lines.append("")
        lines.append(f"- Total rows: {c['total']}")
        lines.append(f"- NR rows (prefix `{NR_PREFIX}` at start): {c['nr']} ({pct:.2f}%)")
        lines.append(f"- RES (non-NR) rows: {c['total'] - c['nr'] - c['blank_auction']}")
        lines.append(f"- Blank auction descriptor: {c['blank_auction']}")
        lines.append(f"- Rows with `No Reserve` appearing mid-string (ambiguous): {c['prefix_mid']}")
        lines.append("")
        lines.append("Sample NR descriptors:")
        for s in c["samples_nr"]:
            lines.append(f"- `{s[:130]}`")
        lines.append("")
        lines.append("Sample RES descriptors:")
        for s in c["samples_res"]:
            lines.append(f"- `{s[:130]}`")
        lines.append("")

    # Cross-check aggregate
    lines.append("## Cross-check against `Sales Auction Type` aggregate sheet")
    lines.append("")
    for r in (w1, w2):
        sheet = r.aggregate_sheets.get("Sales Auction Type")
        lines.append(f"### {r.label}")
        lines.append("")
        if sheet is None:
            lines.append("Sheet absent.")
            lines.append("")
            continue
        for row in sheet[:20]:
            cells = [str(c) if c is not None else "" for c in row]
            lines.append("- " + " | ".join(cells))
        lines.append("")

    # Combined
    total = len(w1.rows) + len(w2.rows)
    nr_w1 = sum(1 for row in w1.rows
                if row.get("Auction") and str(row["Auction"]).startswith(NR_PREFIX))
    nr_w2 = sum(1 for row in w2.rows
                if row.get("Auction") and str(row["Auction"]).startswith(NR_PREFIX))
    lines.append("## Combined W1+W2")
    lines.append("")
    lines.append(f"- Total rows: {total}")
    lines.append(f"- NR rows: {nr_w1 + nr_w2} ({(nr_w1+nr_w2)/total*100:.2f}%)")
    lines.append(f"- NR target per discovery doc: ~22%")
    lines.append("")

    write("p2_auction.md", "\n".join(lines))


# ============================================================================
# PHASE 3: Dial numerals parsing
# ============================================================================

def _canonicalize_dial(raw: Any) -> tuple[str, str]:
    """Returns (canonical_bucket, normalized_raw_for_noise_tail)."""
    if raw is None or str(raw).strip() == "":
        return ("_blank", "")
    s = str(raw).strip().lower()
    # Strip trailing punctuation
    s = s.rstrip(".,;")
    if s in ("no numerals", "no numeral", "none", "no"):
        return ("No Numerals", s)
    if s in ("arabic numerals", "arabic numeral", "arabic"):
        return ("Arabic Numerals", s)
    if s in ("roman numerals", "roman numeral", "roman"):
        return ("Roman Numerals", s)
    if s in ("diamond numerals", "diamond numeral", "diamond", "diamonds",
             "diamond markers"):
        return ("Diamond Numerals", s)
    # slash-combined (e.g., "Arabic Numerals / Roman Numerals")
    if "/" in s:
        parts = [p.strip() for p in s.split("/") if p.strip()]
        buckets = set()
        for p in parts:
            b, _ = _canonicalize_dial(p)
            if b in CANONICAL_DIAL:
                buckets.add(b)
        if len(buckets) == 1:
            return (next(iter(buckets)), s)
        if len(buckets) > 1:
            return ("_slash_combined", s)
    # Typo variants
    if "arabic" in s:
        return ("Arabic Numerals", s)
    if "roman" in s:
        return ("Roman Numerals", s)
    if "diamond" in s:
        return ("Diamond Numerals", s)
    if "no numeral" in s or s == "baton" or s == "batons":
        return ("No Numerals", s)
    return ("_noise", s)


def phase3_dial(w1: Report, w2: Report) -> None:
    lines = ["# Phase 3: Dial numerals parsing", ""]

    def per_report(r: Report, col: str) -> tuple[Counter, Counter, list[tuple[str, int]]]:
        raw_counter: Counter = Counter()
        canon_counter: Counter = Counter()
        for row in r.rows:
            raw = row.get(col)
            raw_key = ("" if raw is None else str(raw).strip())
            raw_counter[raw_key] += 1
            bucket, _ = _canonicalize_dial(raw)
            canon_counter[bucket] += 1
        noise = [(v, c) for v, c in raw_counter.items()
                 if _canonicalize_dial(v)[0] == "_noise" and v != ""]
        noise.sort(key=lambda t: -t[1])
        return raw_counter, canon_counter, noise

    for r, col in ((w1, "Dial"), (w2, "Dial Numbers")):
        raw, canon, noise = per_report(r, col)
        total = len(r.rows)
        lines.append(f"## {r.label} (column: `{col}`)")
        lines.append("")
        lines.append(f"Total rows: {total}")
        lines.append(f"Distinct raw values: {len(raw)}")
        lines.append("")
        lines.append("### Raw value distribution (top 25)")
        lines.append("")
        lines.append("| Count | Raw value |")
        lines.append("|---|---|")
        for val, cnt in raw.most_common(25):
            display = val if val else "(blank)"
            lines.append(f"| {cnt} | `{display}` |")
        lines.append("")
        lines.append("### After canonicalization")
        lines.append("")
        lines.append("| Count | Pct | Canonical bucket |")
        lines.append("|---|---|---|")
        for val, cnt in canon.most_common():
            lines.append(f"| {cnt} | {cnt/total*100:.2f}% | `{val}` |")
        lines.append("")
        lines.append(f"### Noise tail ({len(noise)} distinct values)")
        lines.append("")
        if noise:
            lines.append("| Count | Raw value |")
            lines.append("|---|---|")
            for val, cnt in noise[:40]:
                lines.append(f"| {cnt} | `{val}` |")
        else:
            lines.append("(no noise)")
        lines.append("")

    lines.append("## Canonicalization rules applied")
    lines.append("")
    lines.append("1. Lowercase, strip whitespace, strip trailing `.,;`.")
    lines.append("2. Exact match first against the four canonical singulars and")
    lines.append("   common plural/singular variants.")
    lines.append("3. Slash-combined: split on `/`, canonicalize each part; if all")
    lines.append("   parts map to the same bucket, assign; otherwise mark")
    lines.append("   `_slash_combined` for plan-review.")
    lines.append("4. Keyword fallback: substring match on `arabic`, `roman`,")
    lines.append("   `diamond`, `no numeral`.")
    lines.append("5. Everything else → `_noise`.")
    lines.append("")

    # W1-vs-W2 identity check
    lines.append("## W1-vs-W2 value-identity check")
    lines.append("")
    lines.append("For rows that match on both `Reference Number` AND `Sold at`/`Sold At`")
    lines.append("AND `Sold For`, compare the W1 `Dial` value to the W2 `Dial Numbers` value.")
    lines.append("(Rows overlap only if the same sale appears in both reports; the two")
    lines.append("reports cover different bi-weekly windows, so overlap is expected to be")
    lines.append("small or zero.)")
    lines.append("")
    key_w1 = {(row.get("Reference Number"), row.get("Sold at"),
               money(row.get("Sold For"))): row.get("Dial")
              for row in w1.rows}
    overlap = 0
    identical = 0
    diffs: list[tuple[Any, Any, Any]] = []
    for row in w2.rows:
        k = (row.get("Reference Number"), row.get("Sold At"),
             money(row.get("Sold For")))
        if k in key_w1:
            overlap += 1
            w1val = key_w1[k]
            w2val = row.get("Dial Numbers")
            if (w1val or "") == (w2val or ""):
                identical += 1
            else:
                diffs.append((k, w1val, w2val))
    lines.append(f"- Overlap rows (match on ref + sold_at + sold_for): {overlap}")
    lines.append(f"- Identical dial value: {identical}")
    lines.append(f"- Divergent dial value: {len(diffs)}")
    if diffs:
        lines.append("")
        lines.append("Sample divergences:")
        for k, a, b in diffs[:10]:
            lines.append(f"- `{k}`: W1=`{a}` vs W2=`{b}`")

    write("p3_dial.md", "\n".join(lines))


# ============================================================================
# PHASE 4: Asset class detection
# ============================================================================

def phase4_asset(w1: Report, w2: Report) -> None:
    lines = ["# Phase 4: Asset class detection", ""]
    lines.append(f"Pattern: `{INCH_RE.pattern}` (case-insensitive)")
    lines.append("")
    lines.append("Applied to `Auction` descriptor field.")
    lines.append("")
    for r in (w1, w2):
        matches: list[dict] = []
        for row in r.rows:
            desc = row.get("Auction")
            if desc is None:
                continue
            if INCH_RE.search(str(desc)):
                matches.append(row)
        lines.append(f"## {r.label}")
        lines.append("")
        lines.append(f"Total rows: {len(r.rows)}")
        lines.append(f"Inch-pattern matches: {len(matches)}")
        lines.append("")
        if matches:
            lines.append("| Reference | Make | Auction descriptor (trunc 140) |")
            lines.append("|---|---|---|")
            for row in matches:
                desc = str(row.get("Auction", ""))[:140]
                lines.append(f"| `{row.get('Reference Number','')}` | "
                             f"`{row.get('Make','')}` | `{desc}` |")
        lines.append("")
        # Distribution by make
        brands = Counter(row.get("Make") for row in matches)
        lines.append("Brand distribution of matches:")
        for b, c in brands.most_common():
            lines.append(f"- {b}: {c}")
        lines.append("")

    # False-positive check: look for watch rows that happen to match
    lines.append("## False-positive check")
    lines.append("")
    lines.append("Any matched row whose `Make` is a watch brand (not Louis Vuitton,")
    lines.append("Hermes, Chanel, Gucci, etc.) flags as a false positive.")
    lines.append("")
    HANDBAG_MAKES = {
        "Louis Vuitton", "Hermes", "Hermès", "Chanel", "Gucci", "Prada",
        "Dior", "Fendi", "Saint Laurent", "Bottega Veneta", "Céline",
        "Celine", "Balenciaga", "Loewe", "Goyard",
    }
    for r in (w1, w2):
        fp = []
        for row in r.rows:
            desc = row.get("Auction")
            if desc and INCH_RE.search(str(desc)):
                make = row.get("Make")
                if make and make not in HANDBAG_MAKES:
                    fp.append((make, row.get("Reference Number"),
                               str(desc)[:120]))
        lines.append(f"### {r.label}")
        lines.append(f"False positives: {len(fp)}")
        for m, ref, d in fp[:15]:
            lines.append(f"- `{m}` `{ref}`: `{d}`")
        lines.append("")

    # False-negative: handbag-make rows that did NOT match
    lines.append("## False-negative check")
    lines.append("")
    lines.append("Any row whose `Make` is in the handbag-brand set but whose `Auction`")
    lines.append("descriptor does not match the inch pattern.")
    lines.append("")
    for r in (w1, w2):
        fn = []
        for row in r.rows:
            make = row.get("Make")
            if make in HANDBAG_MAKES:
                desc = row.get("Auction")
                if not (desc and INCH_RE.search(str(desc))):
                    fn.append((make, row.get("Reference Number"),
                               str(desc)[:120] if desc else "(blank)"))
        lines.append(f"### {r.label}")
        lines.append(f"False negatives: {len(fn)}")
        for m, ref, d in fn[:15]:
            lines.append(f"- `{m}` `{ref}`: `{d}`")
        lines.append("")

    lines.append("## Filter behavior")
    lines.append("")
    lines.append("Phase 2 implementation: at ingest, set `asset_class = \"handbag\"`")
    lines.append("for rows matching the inch pattern, else `asset_class = \"watch\"`.")
    lines.append("Scoring pipeline filters on `asset_class == \"watch\"`. Handbag rows")
    lines.append("remain in the report store but are excluded from analyzer scoring,")
    lines.append("bucket construction, confidence calculations, and premium math.")

    write("p4_asset.md", "\n".join(lines))


# ============================================================================
# PHASE 5: Dial color audit (the gated investigation)
# ============================================================================

COLOR_VOCAB_BASE = [
    "black", "white", "silver", "blue", "green", "red", "yellow", "pink",
    "purple", "orange", "brown", "grey", "gray", "gold", "champagne",
    "cream", "ivory", "tan", "slate", "teal", "turquoise", "rhodium",
    "anthracite", "salmon", "copper", "bronze",
]
COMPOUND_NAMES = [
    "mother of pearl", "mother-of-pearl", "mop",
    "skeleton", "skeletonized", "wimbledon", "tiffany", "stella",
    "tapestry", "meteorite", "aventurine", "malachite", "lapis",
    "onyx", "jade", "opal", "panda", "reverse panda", "tropical",
    "linen", "waffle", "pave", "pavé", "gem-set", "diamond pave",
    "diamond dial", "sunburst", "sunray", "celebration",
    "palm", "chromalight",
]
FAMILY_KEYWORDS = {
    "datejust": ["datejust", "date-just", "dj"],
    "sport_rolex": ["submariner", "gmt-master", "gmt master", "daytona",
                    "explorer", "yacht-master", "yachtmaster", "sea-dweller",
                    "seadweller", "deepsea", "air-king", "milgauss"],
    "tudor_sport": ["black bay", "pelagos"],
    "oyster_perpetual": ["oyster perpetual"],
}


def _classify_family(auction_desc: str, model: str) -> str:
    text = (str(auction_desc or "") + " " + str(model or "")).lower()
    for fam, keys in FAMILY_KEYWORDS.items():
        for k in keys:
            if k in text:
                return fam
    return "other"


_color_re = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in COLOR_VOCAB_BASE) + r")\b",
    re.IGNORECASE,
)
_compound_re = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in COMPOUND_NAMES) + r")\b",
    re.IGNORECASE,
)
_dial_anchor_re = re.compile(r"\bdial\b", re.IGNORECASE)


def _parse_color(auction_desc: str) -> dict:
    """Returns dict with: bucket, color (if clean), compound_hits."""
    if not auction_desc:
        return {"bucket": "unparseable", "color": None, "compounds": []}
    s = str(auction_desc)
    if not _dial_anchor_re.search(s):
        return {"bucket": "unparseable", "color": None, "compounds": []}
    # extract a window around "dial" for ranking
    compounds = [m.group(1).lower() for m in _compound_re.finditer(s)]
    # scan colors; prefer colors adjacent (within 4 words) of "dial"
    lower = s.lower()
    words = lower.split()
    dial_idxs = [i for i, w in enumerate(words) if "dial" in w]
    found_colors: list[str] = []
    for i in dial_idxs:
        window = words[max(0, i - 4): i + 1]
        for w in window:
            base = re.sub(r"[^a-z-]", "", w)
            if base in COLOR_VOCAB_BASE:
                found_colors.append(base)
    # de-dup preserving order
    seen = set()
    unique_colors = []
    for c in found_colors:
        if c not in seen:
            seen.add(c)
            unique_colors.append(c)
    if not unique_colors and not compounds:
        return {"bucket": "unparseable", "color": None, "compounds": compounds}
    if compounds and not unique_colors:
        return {"bucket": "ambiguous",
                "color": None, "compounds": compounds,
                "note": "compound name only; no base color"}
    if len(unique_colors) == 1 and not compounds:
        return {"bucket": "clean", "color": unique_colors[0], "compounds": []}
    if len(unique_colors) == 1 and compounds:
        return {"bucket": "ambiguous",
                "color": unique_colors[0], "compounds": compounds,
                "note": "base color plus compound qualifier"}
    if len(unique_colors) > 1:
        return {"bucket": "ambiguous",
                "color": unique_colors[0], "compounds": compounds,
                "note": "multiple base colors"}
    return {"bucket": "unparseable", "color": None, "compounds": []}


def phase5_color(w1: Report, w2: Report) -> None:
    lines = ["# Phase 5: Dial color audit (the gated investigation)", ""]
    lines.append("## Parse rule")
    lines.append("")
    lines.append("1. Require literal `dial` in the Auction descriptor (case-insensitive)")
    lines.append("   as an anchor. No anchor → `unparseable`.")
    lines.append("2. Scan for base-color vocabulary within a 4-word window")
    lines.append("   preceding `dial`.")
    lines.append("3. Scan for compound dial names anywhere in the descriptor")
    lines.append(f"   ({len(COMPOUND_NAMES)} known names).")
    lines.append("4. Classification:")
    lines.append("   - `clean`: exactly one base color, no compound qualifier")
    lines.append("   - `ambiguous`: compound hit, multiple base colors, or base color")
    lines.append("     plus compound qualifier")
    lines.append("   - `unparseable`: no anchor, or anchor with no color vocabulary")
    lines.append("")
    lines.append(f"Base color vocabulary: {COLOR_VOCAB_BASE}")
    lines.append(f"Compound names: {COMPOUND_NAMES}")
    lines.append("")

    all_rows: list[tuple[str, dict, dict]] = []
    for r in (w1, w2):
        for row in r.rows:
            res = _parse_color(row.get("Auction", ""))
            all_rows.append((r.label, row, res))

    bucket_counts = Counter(res["bucket"] for _, _, res in all_rows)
    total = len(all_rows)
    clean = bucket_counts["clean"]
    ambiguous = bucket_counts["ambiguous"]
    unparseable = bucket_counts["unparseable"]
    clean_pct = clean / total * 100
    lines.append("## Headline parse-rate")
    lines.append("")
    lines.append(f"| Bucket | Count | Pct |")
    lines.append(f"|---|---|---|")
    lines.append(f"| Clean unambiguous color | {clean} | {clean_pct:.2f}% |")
    lines.append(f"| Ambiguous | {ambiguous} | {ambiguous/total*100:.2f}% |")
    lines.append(f"| Unparseable | {unparseable} | {unparseable/total*100:.2f}% |")
    lines.append(f"| **Total** | **{total}** | |")
    lines.append("")
    lines.append("### Route decision against pre-locked thresholds")
    lines.append("")
    if clean_pct >= 90:
        route = "≥90% → color joins as fourth keying axis (4-axis schema)"
    elif clean_pct >= 60:
        route = "60-90% → color attaches as bucket metadata only"
    else:
        route = "<60% → color dropped, schema three-axis, color to backlog"
    lines.append(f"**Headline clean parse-rate: {clean_pct:.2f}%**")
    lines.append(f"**Route: {route}**")
    lines.append("")

    # Stratify by family
    lines.append("## Parse rate stratified by reference family")
    lines.append("")
    family_buckets: dict[str, Counter] = defaultdict(Counter)
    for label, row, res in all_rows:
        fam = _classify_family(row.get("Auction", ""), row.get("Model", ""))
        family_buckets[fam][res["bucket"]] += 1
    lines.append("| Family | Total | Clean | Ambiguous | Unparseable | Clean pct |")
    lines.append("|---|---|---|---|---|---|")
    for fam, c in sorted(family_buckets.items(), key=lambda t: -sum(t[1].values())):
        t = sum(c.values())
        lines.append(f"| {fam} | {t} | {c['clean']} | {c['ambiguous']} | "
                     f"{c['unparseable']} | {c['clean']/t*100:.2f}% |")
    lines.append("")

    # Compound case enumeration
    lines.append("## Compound cases enumerated")
    lines.append("")
    compound_counter: Counter = Counter()
    for _, _, res in all_rows:
        for cn in res.get("compounds", []):
            compound_counter[cn] += 1
    lines.append("| Compound name | Row count |")
    lines.append("|---|---|")
    for name, cnt in compound_counter.most_common():
        lines.append(f"| `{name}` | {cnt} |")
    lines.append("")

    # Color distribution among clean
    lines.append("## Base-color distribution among clean rows")
    lines.append("")
    color_counter = Counter(res["color"] for _, _, res in all_rows
                            if res["bucket"] == "clean" and res["color"])
    lines.append("| Color | Count |")
    lines.append("|---|---|")
    for c, n in color_counter.most_common():
        lines.append(f"| {c} | {n} |")
    lines.append("")

    # Samples of unparseable for plan-review
    lines.append("## Samples of unparseable rows (first 15)")
    lines.append("")
    ups = [row for _, row, res in all_rows if res["bucket"] == "unparseable"]
    for row in ups[:15]:
        desc = str(row.get("Auction", ""))[:140]
        lines.append(f"- `{row.get('Make','')}` `{row.get('Reference Number','')}`: "
                     f"`{desc}`")
    lines.append("")

    # Samples of ambiguous
    lines.append("## Samples of ambiguous rows (first 15)")
    lines.append("")
    ambs = [(row, res) for _, row, res in all_rows if res["bucket"] == "ambiguous"]
    for row, res in ambs[:15]:
        desc = str(row.get("Auction", ""))[:140]
        note = res.get("note", "")
        comps = ",".join(res.get("compounds", []))
        lines.append(f"- `{row.get('Make','')}` `{row.get('Reference Number','')}`: "
                     f"note=`{note}`, compounds=`{comps}`, color=`{res.get('color')}`")
        lines.append(f"    desc: `{desc}`")
    lines.append("")

    write("p5_color.md", "\n".join(lines))


# ============================================================================
# PHASE 6: Coverage simulation
# ============================================================================

def phase6_coverage(w1: Report, w2: Report, min_sales: int) -> None:
    lines = ["# Phase 6: Coverage simulation", ""]
    lines.append(f"Keying tuple: `(Reference Number, dial_numerals, auction_type)`")
    lines.append(f"min_sales_for_scoring (from analyzer_config.json): {min_sales}")
    lines.append("")

    # Build combined row set, filter handbags
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    handbag_filtered = 0
    total_rows = 0
    for r, col in ((w1, "Dial"), (w2, "Dial Numbers")):
        for row in r.rows:
            total_rows += 1
            desc = row.get("Auction")
            if desc and INCH_RE.search(str(desc)):
                handbag_filtered += 1
                continue
            ref = row.get("Reference Number")
            if ref is None or str(ref).strip() == "":
                continue
            dial_bucket, _ = _canonicalize_dial(row.get(col))
            at = "NR" if is_nr(desc) else "RES"
            key = (str(ref).strip(), dial_bucket, at)
            price = money(row.get("Sold For"))
            if price is None:
                continue
            buckets[key].append({"price": price, "row": row,
                                 "report": r.label})

    lines.append(f"Total rows scanned: {total_rows}")
    lines.append(f"Handbag-pattern excluded: {handbag_filtered}")
    lines.append(f"Scoring-universe rows: {sum(len(v) for v in buckets.values())}")
    lines.append(f"Total buckets: {len(buckets)}")
    lines.append("")

    # Size distribution
    sizes = [len(v) for v in buckets.values()]
    lines.append("## Bucket size distribution")
    lines.append("")
    size_hist = Counter()
    for s in sizes:
        if s == 1:
            size_hist["1"] += 1
        elif s == 2:
            size_hist["2"] += 1
        elif s < 5:
            size_hist["3-4"] += 1
        elif s < 10:
            size_hist["5-9"] += 1
        elif s < 25:
            size_hist["10-24"] += 1
        elif s < 50:
            size_hist["25-49"] += 1
        elif s < 100:
            size_hist["50-99"] += 1
        else:
            size_hist["100+"] += 1
    order = ["1", "2", "3-4", "5-9", "10-24", "25-49", "50-99", "100+"]
    lines.append("| Bucket sale count | Buckets |")
    lines.append("|---|---|")
    for k in order:
        lines.append(f"| {k} | {size_hist.get(k, 0)} |")
    lines.append("")

    scoring_eligible = sum(1 for s in sizes if s >= min_sales)
    lines.append(f"**Scoring-eligible buckets (>= {min_sales} sales): {scoring_eligible}**")
    lines.append("")
    lines.append("### Comparison to production cycle_2026-06")
    lines.append("")
    lines.append(f"- Production cache (reference-only keying, full historical window):")
    lines.append(f"  1,229 references scored")
    lines.append(f"- New W1+W2 cache (three-axis keying, W1+W2 window only):")
    lines.append(f"  {scoring_eligible} scoring-eligible buckets")
    lines.append(f"- Discovery-doc headline: 1,330 buckets across 13,190 sales")
    lines.append("")

    # Breakdown by axis
    lines.append("## Bucket count broken down by axis")
    lines.append("")
    refs_only = len({k[0] for k in buckets})
    ref_x_dial = len({(k[0], k[1]) for k in buckets})
    ref_x_at = len({(k[0], k[2]) for k in buckets})
    lines.append(f"- Distinct `reference` values: {refs_only}")
    lines.append(f"- Distinct `(reference, dial_numerals)`: {ref_x_dial}")
    lines.append(f"- Distinct `(reference, auction_type)`: {ref_x_at}")
    lines.append(f"- Distinct `(reference, dial_numerals, auction_type)`: {len(buckets)}")
    lines.append("")

    # Datejust sample
    DATEJUST_SAMPLES = ["126200", "126300", "126334", "116234"]
    lines.append("## Datejust-family per-bucket medians")
    lines.append("")
    # Also find the top-volume Datejust refs organically
    dj_refs: Counter = Counter()
    for key, sales in buckets.items():
        for sale in sales:
            m = str(sale["row"].get("Model", "")).lower()
            if "datejust" in m:
                dj_refs[key[0]] += len(sales)
                break
    top_dj = [ref for ref, _ in dj_refs.most_common(10)]
    ref_list = list(dict.fromkeys(DATEJUST_SAMPLES + top_dj))
    for ref in ref_list:
        ref_buckets = {k: v for k, v in buckets.items() if k[0] == ref}
        if not ref_buckets:
            continue
        lines.append(f"### Reference {ref}")
        lines.append("")
        # Aggregate
        all_prices = [s["price"] for sales in ref_buckets.values() for s in sales]
        lines.append(f"Rows: {len(all_prices)}. Blended median: "
                     f"${statistics.median(all_prices):,.0f}")
        lines.append("")
        lines.append("| dial_numerals | auction_type | n | median |")
        lines.append("|---|---|---|---|")
        for key, sales in sorted(ref_buckets.items()):
            n = len(sales)
            med = statistics.median(s["price"] for s in sales) if n else 0
            marker = "" if n >= min_sales else " (<min)"
            lines.append(f"| {key[1]} | {key[2]} | {n}{marker} | "
                         f"${med:,.0f} |")
        lines.append("")

    write("p6_coverage.md", "\n".join(lines))

    # Return a small summary for final report
    return {
        "total_buckets": len(buckets),
        "scoring_eligible": scoring_eligible,
        "handbag_filtered": handbag_filtered,
        "total_rows": total_rows,
        "scoring_universe_rows": sum(len(v) for v in buckets.values()),
    }


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    # Read min_sales from analyzer_config.json
    cfg_path = Path("/Users/ranbirchawla/.openclaw/workspace/state/analyzer_config.json")
    cfg = json.loads(cfg_path.read_text())
    min_sales = cfg["scoring"]["min_sales_for_scoring"]

    print("Loading W1 + W2 xlsx...")
    w1, w2 = load_both()
    print(f"W1: {len(w1.rows)} rows. W2: {len(w2.rows)} rows.")
    print(f"min_sales_for_scoring: {min_sales}")

    print("Phase 1: headers...")
    phase1_headers(w1, w2)
    print("Phase 2: auction type...")
    phase2_auction(w1, w2)
    print("Phase 3: dial numerals...")
    phase3_dial(w1, w2)
    print("Phase 4: asset class...")
    phase4_asset(w1, w2)
    print("Phase 5: dial color...")
    phase5_color(w1, w2)
    print("Phase 6: coverage...")
    summary = phase6_coverage(w1, w2, min_sales)
    print("\nSummary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print("\nFindings written to:", FINDINGS)


if __name__ == "__main__":
    main()
