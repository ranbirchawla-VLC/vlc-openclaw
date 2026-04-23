"""Phase 2a v3 ingest: canonical row layer over Grailzee Pro CSVs.

Produces CanonicalRow instances from one or more Grailzee Pro CSV reports.
Reads CSVs only; transforms (NBSP normalization, asset-class filter,
dial-numerals canonicalization, dial-color parsing, auction-type detection,
dedup) live in pipeline order. Pure analytical layer; downstream is the v3
scorer (lands in Phase 2b). Operational mode is single-report; the
ingest_and_archive wrapper handles the post-pipeline source-file move.

Schema v3 keying tuple per Decision Lock 2026-04-24: (reference,
dial_numerals, auction_type, dial_color). Cache schema bump lands in
Phase 2b; this module produces the row layer the bump consumes.

Critical pipeline invariant: NBSP normalization (U+00A0 to U+0020)
runs at step 3, before any regex match or dedup hash. Future maintainers
must not move it: the NR-prefix regex and the dedup key both depend on
it. See _normalize_nbsp docstring.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import get_tracer

tracer = get_tracer(__name__)


# ─── Vocabulary constants ─────────────────────────────────────────────


NBSP = " "

# Canonical CSV column names produced by the f7ecab8 ingest_report.py
# patch. Read-by-name via DictReader; ordinal reads are forbidden.
EXPECTED_CSV_COLUMNS: frozenset[str] = frozenset({
    "date_sold", "make", "reference", "title", "condition",
    "papers", "sold_price", "sell_through_pct",
    "model", "year", "box", "dial_numerals_raw", "url",
})

# Dial-numerals exact-match table. Keys are lowercase + stripped + trailing
# punctuation removed before lookup. Operator plan-review 2026-04-24 added
# "no numbers" (typo of "No Numerals", 10 rows in W1+W2 live data) and
# "abaric numerals"/"abaric numeral" (typo of "Arabic", 2 rows).
NUMERALS_CANONICAL: dict[str, str] = {
    "arabic numerals": "Arabic",
    "arabic numeral": "Arabic",
    "arabic": "Arabic",
    "roman numerals": "Roman",
    "roman numeral": "Roman",
    "roman": "Roman",
    "diamond numerals": "Diamond",
    "diamond numeral": "Diamond",
    "diamond": "Diamond",
    "no numerals": "No Numerals",
    "no numeral": "No Numerals",
    "no numbers": "No Numerals",
    "abaric numerals": "Arabic",
    "abaric numeral": "Arabic",
}

# Substring keyword fallback for the cascade. Order does not matter; each
# keyword is checked in turn.
NUMERALS_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("arabic", "Arabic"),
    ("roman", "Roman"),
    ("diamond", "Diamond"),
    ("no numeral", "No Numerals"),
)

# Decision 4 base-color vocabulary. Lowercase singletons; parser scans a
# 4-word window before the literal "dial" anchor in the auction descriptor.
BASE_COLOR_VOCABULARY: frozenset[str] = frozenset({
    "black", "white", "silver", "blue", "green", "red", "yellow",
    "pink", "purple", "orange", "brown", "grey", "gray", "gold",
    "champagne", "cream", "ivory", "tan", "slate", "teal",
    "turquoise", "rhodium", "anthracite", "salmon", "copper", "bronze",
})

# Decision 3 named-compound slug vocabulary (13 values, locked).
NAMED_SPECIAL_VOCABULARY: frozenset[str] = frozenset({
    "skeleton", "wimbledon", "panda", "mother_of_pearl",
    "meteorite", "tiffany", "aventurine", "reverse_panda",
    "tapestry", "pave", "linen", "celebration", "tropical",
})

# Source-text patterns mapping to slugs. Multiple source spellings may
# point to the same slug (e.g., "Mother of Pearl"/"MOP"/"mother-of-pearl").
# Detection uses longest-match-wins to handle compound substrings safely
# (e.g., "Reverse Panda" must not silently parse to "panda"). Tests pin
# the longest-match behavior at TestNamedSpecial.test_reverse_panda_*.
NAMED_SPECIAL_SOURCE_PATTERNS: dict[str, str] = {
    "skeletonized": "skeleton",
    "skeleton": "skeleton",
    "wimbledon": "wimbledon",
    "reverse panda": "reverse_panda",
    "panda": "panda",
    "mother of pearl": "mother_of_pearl",
    "mother-of-pearl": "mother_of_pearl",
    "mop": "mother_of_pearl",
    "meteorite": "meteorite",
    "tiffany": "tiffany",
    "aventurine": "aventurine",
    "tapestry": "tapestry",
    "pavé": "pave",
    "pave": "pave",
    "linen": "linen",
    "celebration": "celebration",
    "tropical": "tropical",
}


# ─── Pre-compiled regexes ─────────────────────────────────────────────


# NBSP-tolerant NR-prefix detector. Per Phase 2 Spec Input 4 with
# re.UNICODE. Python 3 str patterns are Unicode by default; the flag is
# kept explicit per spec for documentation clarity.
NR_PREFIX_RE = re.compile(r"^No Reserve\s*-\s*", re.UNICODE)

# Asset-class filter. Multi-dimension inch pattern, uppercase IN
# (handbag descriptor convention). Watch descriptors use uppercase MM
# for size and never the multi-dimension pattern; structural exclusion.
INCH_PATTERN_RE = re.compile(
    r"\b\d+(?:\.\d+)?(?:\s*x\s*\d+(?:\.\d+)?)+\s*IN\b"
)

# Dial-color anchor and word tokenizer.
DIAL_ANCHOR_RE = re.compile(r"\bdial\b", re.IGNORECASE)
WORD_TOKEN_RE = re.compile(r"[\w'-]+")

# Whitespace cleanup (used for trailing punctuation strip in numerals
# cascade: lowercase -> strip -> rstrip(".,;") -> strip).
NUMERALS_TRAILING_PUNCT = ".,;"


# ─── CanonicalRow + IngestSummary ─────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CanonicalRow:
    """A single fully-canonicalized sale, ready for v3 bucket construction.

    Identity and market facts come first; the four keying axes per
    Decision 1 follow; named_special carries Decision 3 metadata
    (separate from dial_color); analyzer-support fields preserve what
    the v2 scorer reads today; provenance trails.

    Frozen + slotted: hashable (handy for set membership in 2b);
    memory-tight across ~10k rows.
    """

    # Identity and market
    reference: str
    sold_at: date
    sold_for: float
    # Four keying axes
    auction_type: Literal["NR", "RES"]
    auction_descriptor: str
    dial_numerals: Literal["Arabic", "Roman", "Diamond", "No Numerals"]
    dial_color: str
    # Decision 3 metadata
    named_special: str | None
    # Analyzer/display support (preserved for 2b scorer)
    brand: str
    model: str
    condition: str
    papers: str
    year: str
    box: str
    sell_through_pct: float | None
    url: str
    # Provenance
    source_report: str
    source_row_index: int


@dataclass
class IngestSummary:
    """Per-pipeline counters for telemetry and spot-check arithmetic.

    Arithmetic invariant: canonical_rows_emitted ==
        source_rows_total
        - asset_class_filtered
        - numerals_blank_dropped
        - fallthrough_drops
        - within_report_duplicates
        - cross_report_duplicates
    """

    source_reports: list[str] = field(default_factory=list)
    # Pre-pipeline
    source_rows_total: int = 0
    # Drops (each reduces emitted count)
    asset_class_filtered: int = 0
    numerals_blank_dropped: int = 0           # Decision 5
    fallthrough_drops: int = 0                # operator plan-review 2026-04-24
    within_report_duplicates: int = 0         # I.4 finding
    cross_report_duplicates: int = 0          # validation path; 0 in single-report ops
    # Transforms (no row drop)
    numerals_slash_canonicalized: int = 0     # Decision 6
    nbsp_normalized_nr_rows: int = 0          # I.2 telemetry
    dial_color_unknown: int = 0               # Decision 4
    named_special_detected: int = 0
    # Advisory (no drop, no transform)
    within_report_near_collisions: int = 0    # I.4; 2b observation flag
    # Post-pipeline
    canonical_rows_emitted: int = 0


# ─── Pipeline transforms ──────────────────────────────────────────────


def _normalize_nbsp(value: str) -> str:
    """Replace U+00A0 with U+0020 in a single string.

    LOAD-BEARING: must run before NR-prefix regex matching and before
    dedup-key construction. Live W1+W2 data carries 106 rows where the
    NR-prefix uses NBSP after the hyphen; without normalization those
    rows misclassify as RES.
    """
    return value.replace(NBSP, " ")


def is_handbag(descriptor: str) -> bool:
    """Decision: filter row from scoring as a non-watch asset.

    Discovery I.3 confirmed zero false positives, zero genuine false
    negatives on W1+W2 (3 LV handbag rows in W2; 0 in W1).
    """
    return bool(INCH_PATTERN_RE.search(descriptor))


def canonicalize_dial_numerals(raw: str | None) -> tuple[str | None, str]:
    """Apply the cascade per Decisions 5/6 plus operator plan-review.

    Returns (canonical_value, status) where status is one of:
      "ok"                   - canonicalized via exact match or keyword
      "slash_canonicalized"  - took first segment of slash-combined value
      "blank_drop"           - blank/None per Decision 5; row drops
      "fallthrough_drop"     - non-canonical-non-blank per operator
                               plan-review 2026-04-24; row drops
    """
    if raw is None:
        return None, "blank_drop"
    s_initial = str(raw).strip()
    if not s_initial:
        return None, "blank_drop"
    s = s_initial.lower().rstrip(NUMERALS_TRAILING_PUNCT).strip()
    if not s:
        return None, "blank_drop"

    if "/" in s:
        first = s.split("/", 1)[0].strip()
        if first in NUMERALS_CANONICAL:
            return NUMERALS_CANONICAL[first], "slash_canonicalized"
        for kw, canon in NUMERALS_KEYWORDS:
            if kw in first:
                return canon, "slash_canonicalized"
        # First segment untranslatable; fall through to whole-string attempts

    if s in NUMERALS_CANONICAL:
        return NUMERALS_CANONICAL[s], "ok"
    for kw, canon in NUMERALS_KEYWORDS:
        if kw in s:
            return canon, "ok"
    return None, "fallthrough_drop"


def parse_dial_color(descriptor: str) -> str:
    """Return a base color from BASE_COLOR_VOCABULARY or "unknown".

    Anchors on the first occurrence of the literal "dial" word; scans
    the four words preceding for base-vocabulary hits. Exactly one hit
    in the window returns that color; zero, multiple, or no anchor
    returns "unknown" (Decision 4).
    """
    desc_lower = descriptor.lower()
    m = DIAL_ANCHOR_RE.search(desc_lower)
    if not m:
        return "unknown"
    before = desc_lower[: m.start()]
    words = WORD_TOKEN_RE.findall(before)
    window = words[-4:]
    found = [w for w in window if w in BASE_COLOR_VOCABULARY]
    # Dedupe order-preserving (e.g., "Black Black Dial" reads as one base)
    seen: set[str] = set()
    deduped: list[str] = []
    for w in found:
        if w not in seen:
            seen.add(w)
            deduped.append(w)
    if len(deduped) == 1:
        return deduped[0]
    return "unknown"


def detect_named_special(descriptor: str) -> str | None:
    """Decision 3 compound detection with longest-match-wins.

    Operator plan-review 2026-04-24: longest-match (not first-match by
    vocabulary order). A "Reverse Panda" descriptor returns
    "reverse_panda", not "panda". Tie broken by source-pattern
    alphabetical order for determinism (extremely unlikely tie).
    """
    desc_lower = descriptor.lower()
    best_length = -1
    best_pattern = ""
    best_slug: str | None = None
    for src, slug in NAMED_SPECIAL_SOURCE_PATTERNS.items():
        if src in desc_lower:
            length = len(src)
            if length > best_length or (length == best_length and src < best_pattern):
                best_length = length
                best_pattern = src
                best_slug = slug
    return best_slug


def detect_auction_type(descriptor: str) -> Literal["NR", "RES"]:
    """Per Phase 2 Spec Input 4. Descriptor must already be NBSP-normalized."""
    return "NR" if NR_PREFIX_RE.match(descriptor) else "RES"


# ─── Source CSV reader ────────────────────────────────────────────────


def _parse_iso_date(raw: str) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _parse_float(raw: str) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _load_csv(path: Path) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Empty CSV (no header): {path}")
        missing = EXPECTED_CSV_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(
                f"CSV {path} missing expected columns: {sorted(missing)}. "
                f"Run ingest_report.py against the source xlsx to "
                f"regenerate the canonical CSV (commit f7ecab8 added the "
                f"five appended fields)."
            )
        return list(reader)


# ─── Pipeline driver ──────────────────────────────────────────────────


def _process_row(
    raw: dict[str, str],
    source_report: str,
    source_row_index: int,
    summary: IngestSummary,
) -> CanonicalRow | None:
    """Apply pipeline steps 3-8 to a single source row.

    Returns the CanonicalRow or None when the row is dropped. Drops
    increment the appropriate summary counter.
    """
    # Step 3: NBSP normalization on string fields. We normalize at read
    # time so dedup keys and regex matches see clean whitespace.
    string_field_names = ("title", "make", "reference", "condition",
                          "papers", "model", "year", "box",
                          "dial_numerals_raw", "url")
    normalized: dict[str, str] = dict(raw)
    for fname in string_field_names:
        v = normalized.get(fname, "") or ""
        if NBSP in v:
            normalized[fname] = _normalize_nbsp(v)

    title = normalized.get("title", "") or ""

    # Step 4: asset-class filter
    if is_handbag(title):
        summary.asset_class_filtered += 1
        return None

    # Step 5: dial-numerals canonicalization
    numerals, num_status = canonicalize_dial_numerals(
        normalized.get("dial_numerals_raw", "")
    )
    if num_status == "blank_drop":
        summary.numerals_blank_dropped += 1
        return None
    if num_status == "fallthrough_drop":
        summary.fallthrough_drops += 1
        return None
    if num_status == "slash_canonicalized":
        summary.numerals_slash_canonicalized += 1

    # Step 6: dial-color parsing + named_special detection
    color = parse_dial_color(title)
    if color == "unknown":
        summary.dial_color_unknown += 1
    named = detect_named_special(title)
    if named is not None:
        summary.named_special_detected += 1

    # Step 7: auction-type detection
    auction_type = detect_auction_type(title)
    # NBSP NR telemetry: did this row need NBSP-tolerance to classify as NR?
    # Test: original raw title (pre-normalization) starts with literal-space
    # pattern? If not but normalized does, it relied on NBSP normalization.
    if auction_type == "NR":
        original_title = raw.get("title", "") or ""
        if not original_title.startswith("No Reserve - "):
            summary.nbsp_normalized_nr_rows += 1

    # Step 8: row construction
    sold_at = _parse_iso_date(normalized.get("date_sold", ""))
    sold_for = _parse_float(normalized.get("sold_price", ""))
    if sold_at is None or sold_for is None:
        # Source CSV from ingest_report.py guarantees these are populated;
        # treat malformed as a hard surface error so we do not silently
        # absorb upstream regressions.
        raise ValueError(
            f"Malformed source row at {source_report}#{source_row_index}: "
            f"date_sold={normalized.get('date_sold')!r}, "
            f"sold_price={normalized.get('sold_price')!r}"
        )

    return CanonicalRow(
        reference=normalized.get("reference", ""),
        sold_at=sold_at,
        sold_for=sold_for,
        auction_type=auction_type,
        auction_descriptor=title,
        dial_numerals=numerals,  # type: ignore[arg-type]
        dial_color=color,
        named_special=named,
        brand=normalized.get("make", ""),
        model=normalized.get("model", ""),
        condition=normalized.get("condition", ""),
        papers=normalized.get("papers", ""),
        year=normalized.get("year", ""),
        box=normalized.get("box", ""),
        sell_through_pct=_parse_float(normalized.get("sell_through_pct", "")),
        url=normalized.get("url", ""),
        source_report=source_report,
        source_row_index=source_row_index,
    )


def _dedup_key(row: CanonicalRow) -> tuple[str, str, str, str]:
    """4-tuple key per Decision 1's keying surface plus descriptor.

    Stringifies sold_for to two decimals to avoid float-equality
    fragility in dict lookups.
    """
    return (
        row.reference,
        row.sold_at.isoformat(),
        f"{row.sold_for:.2f}",
        row.auction_descriptor,
    )


def _dedup(
    rows: list[CanonicalRow],
    summary: IngestSummary,
) -> list[CanonicalRow]:
    """4-tuple dedup per Phase 2 Spec Input 5.

    Within-report tiebreak: first-seen-wins.
    Cross-report tiebreak: prefer most recent report by filename
    lexicographic sort (Decision 7 generalized; ISO-date filenames
    sort in chronological order).
    """
    keyed: dict[tuple[str, str, str, str], CanonicalRow] = {}
    for r in rows:
        key = _dedup_key(r)
        existing = keyed.get(key)
        if existing is None:
            keyed[key] = r
            continue
        if existing.source_report == r.source_report:
            summary.within_report_duplicates += 1
            # first-seen-wins: keep existing
        else:
            summary.cross_report_duplicates += 1
            if r.source_report > existing.source_report:
                keyed[key] = r
            # else keep existing
    # Stable output order per plan: (source_report, source_row_index)
    return sorted(keyed.values(), key=lambda x: (x.source_report, x.source_row_index))


def _count_near_collisions(rows: list[CanonicalRow]) -> int:
    """Count within-report 3-tuple groupings with differing 4th field.

    Per discovery I.4 definition: groupings, not row count. Operator
    plan-review 2026-04-24: log this count, do not drop. 4-axis keying
    in Phase 2b resolves dial-color and NR-vs-RES variants; year and
    bracelet variants stay in-bucket as observable signal.
    """
    grouped: dict[tuple[str, str, str, str], set[str]] = {}
    for r in rows:
        key = (r.source_report, r.reference, r.sold_at.isoformat(),
               f"{r.sold_for:.2f}")
        grouped.setdefault(key, set()).add(r.auction_descriptor)
    return sum(1 for descriptors in grouped.values() if len(descriptors) > 1)


# ─── Public API ───────────────────────────────────────────────────────


def load_and_canonicalize(
    report_paths: list[Path],
) -> tuple[list[CanonicalRow], IngestSummary]:
    """Pure function: read CSVs, emit canonical rows.

    Reads the input CSVs only. No writes, moves, creates. Production
    operational use takes a single-element list (and is best wrapped by
    ingest_and_archive); validation use takes multiple paths to exercise
    the cross-report dedup.
    """
    if not report_paths:
        raise ValueError("report_paths is empty; supply at least one CSV path")

    with tracer.start_as_current_span("ingest.load_and_canonicalize") as span:
        span.set_attribute("report_count", len(report_paths))
        summary = IngestSummary(source_reports=[p.name for p in report_paths])

        pre_dedup: list[CanonicalRow] = []
        for path in report_paths:
            raw_rows = _load_csv(path)
            summary.source_rows_total += len(raw_rows)
            for idx, raw in enumerate(raw_rows):
                row = _process_row(raw, path.name, idx, summary)
                if row is not None:
                    pre_dedup.append(row)

        deduped = _dedup(pre_dedup, summary)
        summary.within_report_near_collisions = _count_near_collisions(deduped)
        summary.canonical_rows_emitted = len(deduped)

        span.set_attribute("source_rows_total", summary.source_rows_total)
        span.set_attribute("canonical_rows_emitted", summary.canonical_rows_emitted)
        span.set_attribute("asset_class_filtered", summary.asset_class_filtered)
        span.set_attribute("numerals_blank_dropped", summary.numerals_blank_dropped)
        span.set_attribute("fallthrough_drops", summary.fallthrough_drops)
        span.set_attribute("within_report_duplicates", summary.within_report_duplicates)
        span.set_attribute("cross_report_duplicates", summary.cross_report_duplicates)
        span.set_attribute("nbsp_normalized_nr_rows", summary.nbsp_normalized_nr_rows)
        span.set_attribute("dial_color_unknown", summary.dial_color_unknown)
        span.set_attribute("named_special_detected", summary.named_special_detected)
        span.set_attribute("within_report_near_collisions",
                           summary.within_report_near_collisions)
        span.set_attribute("outcome", "ok")

        return deduped, summary


def ingest_and_archive(
    report_path: Path,
    archive_dir: Path | None = None,
) -> tuple[list[CanonicalRow], IngestSummary, Path]:
    """Production wrapper: canonicalize one report, archive the source.

    1. Calls load_and_canonicalize([report_path]).
    2. On success, moves report_path to archive_dir/report_path.name.
       Default archive_dir is report_path.parent / "archive".
    3. Returns (rows, summary, final_archived_path).

    Raises FileExistsError on destination collision (idempotency block;
    operator manually unblocks). Archival failure does not invalidate
    the canonical rows; the caller observes the failure via exception.
    """
    if archive_dir is None:
        archive_dir = report_path.parent / "archive"

    with tracer.start_as_current_span("ingest.ingest_and_archive") as span:
        span.set_attribute("report_path", str(report_path))
        span.set_attribute("archive_dir", str(archive_dir))

        rows, summary = load_and_canonicalize([report_path])

        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / report_path.name
        if dest.exists():
            span.set_attribute("outcome", "archive_destination_exists")
            raise FileExistsError(
                f"Archive destination already exists: {dest}. Refusing to "
                f"overwrite. Inspect both files; if intentional re-ingest, "
                f"manually remove the destination then retry."
            )
        shutil.move(str(report_path), str(dest))

        span.set_attribute("archived_path", str(dest))
        span.set_attribute("canonical_rows_emitted", summary.canonical_rows_emitted)
        span.set_attribute("outcome", "ok")
        return rows, summary, dest


# ─── CLI ──────────────────────────────────────────────────────────────


def _summary_to_dict(s: IngestSummary) -> dict:
    return {
        "source_reports": s.source_reports,
        "source_rows_total": s.source_rows_total,
        "canonical_rows_emitted": s.canonical_rows_emitted,
        "asset_class_filtered": s.asset_class_filtered,
        "numerals_blank_dropped": s.numerals_blank_dropped,
        "fallthrough_drops": s.fallthrough_drops,
        "within_report_duplicates": s.within_report_duplicates,
        "cross_report_duplicates": s.cross_report_duplicates,
        "numerals_slash_canonicalized": s.numerals_slash_canonicalized,
        "nbsp_normalized_nr_rows": s.nbsp_normalized_nr_rows,
        "dial_color_unknown": s.dial_color_unknown,
        "named_special_detected": s.named_special_detected,
        "within_report_near_collisions": s.within_report_near_collisions,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI for spot-check use. Production wiring (Phase 2b) calls the
    Python API directly. Two modes:
      --validate <csv> [<csv> ...]   -> load_and_canonicalize, no archival
      --ingest <csv> [--archive-dir DIR] -> ingest_and_archive
    """
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    p_val = sub.add_parser("validate",
                           help="Pure load_and_canonicalize on one or more CSVs")
    p_val.add_argument("csvs", nargs="+")

    p_ing = sub.add_parser("ingest",
                           help="ingest_and_archive on a single CSV")
    p_ing.add_argument("csv")
    p_ing.add_argument("--archive-dir", default=None)

    args = parser.parse_args(argv)

    if args.mode == "validate":
        paths = [Path(p) for p in args.csvs]
        _, summary = load_and_canonicalize(paths)
        print(json.dumps(_summary_to_dict(summary), indent=2))
        return 0

    if args.mode == "ingest":
        path = Path(args.csv)
        archive = Path(args.archive_dir) if args.archive_dir else None
        _, summary, dest = ingest_and_archive(path, archive)
        out = _summary_to_dict(summary)
        out["archived_path"] = str(dest)
        print(json.dumps(out, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
