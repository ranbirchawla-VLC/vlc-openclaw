"""Shared constants, formulas, and utilities for Grailzee Eval v2.

All constants, formulas, and reference-matching logic live here. Every
other script in skills/grailzee-eval-v2/scripts/ imports from this module.

Extracted and refactored from skills/grailzee-eval/scripts/
analyze_report.py and evaluate_deal.py. Behavior preserved unless
explicitly noted (see RISK_RESERVE_THRESHOLD comment).
"""

from __future__ import annotations

import csv
import json
import os
import re
import statistics
import sys
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional


# ─── Paths ────────────────────────────────────────────────────────────

GRAILZEE_ROOT = (
    "/Users/ranbirchawla/Library/CloudStorage/"
    "GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/"
    "Vardalux Shared Drive/GrailzeeData"
)
REPORTS_PATH  = f"{GRAILZEE_ROOT}/reports"
CSV_PATH      = f"{GRAILZEE_ROOT}/reports_csv"
OUTPUT_PATH   = f"{GRAILZEE_ROOT}/output"
BRIEFS_PATH   = f"{OUTPUT_PATH}/briefs"
STATE_PATH    = f"{GRAILZEE_ROOT}/state"
BACKUP_PATH   = f"{GRAILZEE_ROOT}/backup"

CACHE_PATH          = f"{STATE_PATH}/analysis_cache.json"
BRIEF_PATH          = f"{STATE_PATH}/sourcing_brief.json"
LEDGER_PATH         = f"{STATE_PATH}/trade_ledger.csv"
NAME_CACHE_PATH     = f"{STATE_PATH}/name_cache.json"
CYCLE_FOCUS_PATH    = f"{STATE_PATH}/cycle_focus.json"
CYCLE_OUTCOME_PATH  = f"{STATE_PATH}/cycle_outcome.json"
MONTHLY_GOALS_PATH  = f"{STATE_PATH}/monthly_goals.json"
QUARTERLY_PATH      = f"{STATE_PATH}/quarterly_allocation.json"
RUN_HISTORY_PATH    = f"{STATE_PATH}/run_history.json"


# ─── Business rules ───────────────────────────────────────────────────

NR_FIXED = 149              # NR account: $49 Grailzee fee + $100 shipping
RES_FIXED = 199             # Reserve account: $99 fee + $100 shipping
TARGET_MARGIN = 0.05        # 5% target margin on every trade

# NOTE: v1 used RISK_RESERVE_THRESHOLD = 20 (percent). v2 uses fraction.
# All downstream consumers must use the fraction (0.40 = 40%).
RISK_RESERVE_THRESHOLD = 0.40

MIN_SALES_FOR_SCORING = 3   # plan Section 7.1: need 3+ sales to score
CACHE_SCHEMA_VERSION = 2    # plan Section 13: v2 cache schema

ACCOUNT_FEES = {"NR": NR_FIXED, "RES": RES_FIXED}

VARDALUX_COLORS = {
    "rich_black": "231F20",
    "warm_gold":  "C9A84C",
    "deep_teal":  "315159",
}

# Extracted from v1 analyze_report.py line 34.
# Plan Section 12.3 showed only 4 items (very good, like new, excellent, unworn);
# v1 is the source of truth with these 4 items. "unworn" is NOT in v1; "new" IS.
QUALITY_CONDITIONS = {"very good", "like new", "new", "excellent"}

# ─── Ledger schema ────────────────────────────────────────────────────

LEDGER_COLUMNS = [
    "date_closed", "cycle_id", "brand", "reference",
    "account", "buy_price", "sell_price",
]
VALID_ACCOUNTS = {"NR", "RES"}


# Ad budget brackets (from v1 evaluate_deal.py lines 39-44)
AD_BUDGETS = [
    (3500, "$37\u201350"),
    (5000, "$50\u2013100"),
    (10000, "$200\u2013250"),
    (float("inf"), "$250 cap"),
]


# ─── Formulas ─────────────────────────────────────────────────────────

def max_buy_nr(median: float) -> float:
    """MAX BUY for No Reserve account.

    Formula: (median - 149) / 1.05, rounded to nearest $10.
    """
    return round((median - NR_FIXED) / (1 + TARGET_MARGIN), -1)


def max_buy_reserve(median: float) -> float:
    """MAX BUY for Reserve account.

    Formula: (median - 199) / 1.05, rounded to nearest $10.
    """
    return round((median - RES_FIXED) / (1 + TARGET_MARGIN), -1)


def breakeven_nr(max_buy: float) -> float:
    """Breakeven sell price for an NR trade at max_buy purchase."""
    return max_buy + NR_FIXED


def breakeven_reserve(max_buy: float) -> float:
    """Breakeven sell price for a Reserve trade at max_buy purchase."""
    return max_buy + RES_FIXED


def adjusted_max_buy(median: float, fixed_cost: float,
                     premium_adjustment_pct: float) -> float:
    """MAX BUY with presentation-premium adjustment applied.

    Used when the ledger has accumulated enough trades to prove a
    presentation premium above +8% average. See Section 5.5 of plan.
    """
    adjusted_median = median * (1 + premium_adjustment_pct / 100)
    return round((adjusted_median - fixed_cost) / (1 + TARGET_MARGIN), -1)


def get_ad_budget(median_price: float) -> str:
    """Return recommended ad budget string based on expected sale price.

    Extracted from v1 evaluate_deal.py get_ad_budget (lines 109-114).
    """
    for threshold, budget in AD_BUDGETS:
        if median_price <= threshold:
            return budget
    return AD_BUDGETS[-1][1]


# ─── Reference matching ───────────────────────────────────────────────

def normalize_ref(s: str) -> str:
    """Normalize a reference string for matching.

    Extracted from v1 analyze_report.py (lines 231-234).
    Strips whitespace, uppercases, removes trailing '.0' (Excel artifact).
    """
    s = str(s).strip().upper()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def strip_ref(s: str) -> str:
    """Strip common prefixes/suffixes for fuzzy matching.

    Extracted from v1 evaluate_deal.py (lines 53-62).
    Normalizes first, then strips Tudor M-prefix, trailing -XXXX suffixes,
    and all separators (hyphens, dots, spaces).
    """
    s = normalize_ref(s)
    # Strip leading M (Tudor convention)
    if s.startswith("M") and len(s) > 5:
        s = s[1:]
    # Strip trailing -XXXX suffixes
    s = re.sub(r"-\d{4}$", "", s)
    # Remove all separators for comparison
    return s.replace("-", "").replace(".", "").replace(" ", "")


def match_reference(sale_ref: str, target: str | list) -> bool:
    """True if sale_ref matches target (exact or pattern list).

    Extracted from v1 analyze_report.py (lines 236-244).
    Matches if either normalized form is a substring of the other,
    or if either separator-stripped form is a substring of the other.
    When target is a list, returns True if any element matches.
    """
    if isinstance(target, list):
        return any(match_reference(sale_ref, t) for t in target)
    norm = normalize_ref(sale_ref)
    np = normalize_ref(target)
    if np in norm or norm in np:
        return True
    cn = norm.replace("-", "").replace(".", "").replace(" ", "")
    cp = np.replace("-", "").replace(".", "").replace(" ", "")
    if cp in cn or cn in cp:
        return True
    return False


# ─── DJ 126300 configuration breakout ─────────────────────────────────
# Same reference, wildly different prices depending on dial/bracelet
# configuration. Keyword matching against auction titles classifies
# sales into config buckets so median pricing is accurate per config.

# Extracted from v1 analyze_report.py (lines 72-82).
# Dict maps config name to (dial_keywords, bracelet_keywords).
# bracelet_keywords=None means bracelet is irrelevant for that config.
DJ_CONFIGS = {
    "Black/Oyster":   (["black"], ["oyster"]),
    "Blue/Jubilee":   (["blue"], ["jubilee"]),
    "Blue/Oyster":    (["blue"], ["oyster"]),
    "Slate/Jubilee":  (["slate"], ["jubilee"]),
    "Slate/Oyster":   (["slate"], ["oyster"]),
    "Green":          (["green"], None),
    "Wimbledon":      (["wimbledon"], None),
    "White/Oyster":   (["white"], ["oyster"]),
    "Silver":         (["silver"], None),
}


def classify_dj_config(title: str) -> Optional[str]:
    """Classify a DJ 41 (126300) auction title into a config bucket.

    Returns config key (e.g. 'Black/Oyster') or None if unclassifiable.
    Extracted from v1 analyze_report.py (lines 246-252).
    v1 returned "Other" for unclassifiable; v2 returns None for cleaner
    downstream filtering (callers can default to "Other" if needed).
    """
    tl = title.lower()
    for cfg, (dial_kw, bracelet_kw) in DJ_CONFIGS.items():
        if any(k in tl for k in dial_kw):
            if bracelet_kw is None:
                return cfg
            if any(k in tl for k in bracelet_kw):
                return cfg
    return None


# ─── Quality filter ───────────────────────────────────────────────────

def is_quality_sale(sale: dict) -> bool:
    """True if a sale meets condition + papers quality gates.

    Extracted from v1 analyze_report.py (lines 255-258).
    Requires BOTH:
      1. condition contains one of QUALITY_CONDITIONS (substring match)
      2. papers field is one of: 'yes', 'y', 'true', '1', 'included'
    """
    cond = sale.get("condition", "").lower().strip()
    papers = sale.get("papers", "").lower().strip()
    return (
        any(q in cond for q in QUALITY_CONDITIONS)
        and papers in ("yes", "y", "true", "1", "included")
    )


# ─── Name cache ───────────────────────────────────────────────────────

def load_name_cache(cache_path: Optional[str] = None) -> dict:
    """Load name_cache.json. Returns empty dict if file missing."""
    path = cache_path or NAME_CACHE_PATH
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def save_name_cache(cache: dict, cache_path: Optional[str] = None) -> None:
    """Write name_cache.json (indented, sorted keys)."""
    path = cache_path or NAME_CACHE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(cache, f, indent=2, sort_keys=True)


def append_name_cache_entry(
    reference: str,
    brand: str,
    model: str,
    alt_refs: Optional[list] = None,
    cache_path: Optional[str] = None,
) -> None:
    """Add one entry to name cache. Idempotent on exact reference match.

    If the reference already exists, leaves the existing entry alone.
    Use save_name_cache directly for overwrites.
    """
    cache = load_name_cache(cache_path)
    if reference in cache:
        return
    entry: dict = {"brand": brand, "model": model}
    if alt_refs:
        entry["alt_refs"] = alt_refs
    cache[reference] = entry
    save_name_cache(cache, cache_path)


# ─── Ledger I/O ──────────────────────────────────────────────────────


@dataclass
class LedgerRow:
    """One trade in the ledger. Stored fields only; derived fields live
    in read_ledger.py."""
    date_closed: date
    cycle_id: str
    brand: str
    reference: str
    account: str
    buy_price: float
    sell_price: float


def parse_ledger_csv(ledger_path: Optional[str] = None) -> list[LedgerRow]:
    """Read trade_ledger.csv and return a list of LedgerRow.

    Returns empty list if file is missing or empty (header-only).
    Raises ValueError on malformed rows.
    """
    path = ledger_path or LEDGER_PATH
    if not os.path.exists(path):
        return []
    rows: list[LedgerRow] = []
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for i, raw in enumerate(reader, start=2):
            try:
                y, m, d = raw["date_closed"].split("-")
                rows.append(LedgerRow(
                    date_closed=date(int(y), int(m), int(d)),
                    cycle_id=raw["cycle_id"],
                    brand=raw["brand"],
                    reference=raw["reference"],
                    account=raw["account"],
                    buy_price=float(raw["buy_price"]),
                    sell_price=float(raw["sell_price"]),
                ))
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError(
                    f"Malformed row {i} in {path}: {exc}"
                ) from exc
    return rows


def ensure_ledger_exists(ledger_path: Optional[str] = None) -> str:
    """Create trade_ledger.csv with header row if it doesn't exist.

    Idempotent. Returns the path used.
    """
    path = ledger_path or LEDGER_PATH
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(LEDGER_COLUMNS)
    return path


def append_ledger_row(row: LedgerRow, ledger_path: Optional[str] = None) -> None:
    """Append one trade to trade_ledger.csv. Creates file if missing."""
    path = ensure_ledger_exists(ledger_path)
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            row.date_closed.isoformat(),
            row.cycle_id,
            row.brand,
            row.reference,
            row.account,
            row.buy_price,
            row.sell_price,
        ])


# ─── Cycle helpers ────────────────────────────────────────────────────

def _first_monday_of_year(year: int) -> date:
    """Return the first Monday on or after Jan 1 of the given year."""
    jan1 = date(year, 1, 1)
    days_to_monday = (7 - jan1.weekday()) % 7
    if days_to_monday == 0:
        return jan1
    return date(year, 1, 1 + days_to_monday)


def cycle_id_from_date(d: date) -> str:
    """Return cycle_id (cycle_YYYY-NN) for a given date.

    Cycles are biweekly. Cycle 01 starts the first Monday of the year.
    Dates before that first Monday fall in the prior year's last cycle.
    """
    first_monday = _first_monday_of_year(d.year)
    if d < first_monday:
        # Recurse into prior year's last cycle
        return cycle_id_from_date(date(d.year - 1, 12, 31))
    delta_days = (d - first_monday).days
    cycle_num = 1 + (delta_days // 14)
    return f"cycle_{d.year}-{cycle_num:02d}"


def cycle_date_range(cycle_id: str) -> tuple[date, date]:
    """Return (start_date, end_date) inclusive for a cycle_id."""
    year_str, num_str = cycle_id.replace("cycle_", "").split("-")
    year, num = int(year_str), int(num_str)
    first_monday = _first_monday_of_year(year)
    start = date.fromordinal(first_monday.toordinal() + (num - 1) * 14)
    end = date.fromordinal(start.toordinal() + 13)
    return start, end


def prev_cycle(cycle_id: str) -> str:
    """Return the cycle_id preceding the given cycle.

    For cycle_YYYY-01, returns the last cycle of YYYY-1.
    """
    year_str, num_str = cycle_id.replace("cycle_", "").split("-")
    year, num = int(year_str), int(num_str)
    if num > 1:
        return f"cycle_{year}-{num - 1:02d}"
    return cycle_id_from_date(date(year - 1, 12, 31))


def load_cycle_focus(path: Optional[str] = None) -> Optional[dict]:
    """Load cycle_focus.json. Returns None if file missing."""
    path = path or CYCLE_FOCUS_PATH
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def is_cycle_focus_current(
    current_cycle_id: str,
    focus: Optional[dict] = None,
) -> bool:
    """True if cycle_focus.json's cycle_id matches the current cycle."""
    focus = focus if focus is not None else load_cycle_focus()
    if focus is None:
        return False
    return focus.get("cycle_id") == current_cycle_id


# ─── Presentation premium ─────────────────────────────────────────────

def calculate_presentation_premium(ledger_rows: list) -> dict:
    """Compute presentation premium stats from ledger rows.

    Expects rows with premium_vs_median and median_at_trade attributes
    (or dict equivalent). See plan Section 5.5.

    Threshold: 10 trades at +8% average or greater triggers automatic
    MAX BUY adjustment. Adjustment = half the average premium.
    """
    def get_premium(row):
        if hasattr(row, "premium_vs_median"):
            return row.premium_vs_median, row.median_at_trade
        return row.get("premium_vs_median"), row.get("median_at_trade")

    premiums = []
    for row in ledger_rows:
        premium, median = get_premium(row)
        if median is not None and premium is not None:
            premiums.append(premium)

    if not premiums:
        return {
            "avg_premium": 0,
            "trade_count": 0,
            "threshold_met": False,
            "adjustment": 0,
        }

    avg = statistics.mean(premiums)
    count = len(premiums)
    threshold_met = count >= 10 and avg >= 8.0
    adjustment = round(avg / 2, 1) if threshold_met else 0

    return {
        "avg_premium": round(avg, 1),
        "trade_count": count,
        "threshold_met": threshold_met,
        "adjustment": adjustment,
    }


# ─── Observability ────────────────────────────────────────────────────
# Lazy tracer factory. Returns a no-op tracer unless OpenTelemetry is
# configured via environment variables. This means tests, local dev,
# and CI run quietly without needing a collector.
#
# To activate tracing, set these env vars before running scripts:
#   OTEL_EXPORTER_OTLP_ENDPOINT=<collector URL>
#   OTEL_SERVICE_NAME=grailzee-eval
#   OTEL_EXPORTER_OTLP_HEADERS=<headers if needed, e.g. honeycomb team>
#
# Usage in scripts:
#   from grailzee_common import get_tracer
#   tracer = get_tracer(__name__)
#   with tracer.start_as_current_span("operation_name") as span:
#       span.set_attribute("key", "value")
#       ... work ...

_tracer_provider_initialized = False


def _init_tracer_provider() -> None:
    """One-time OTel setup. Idempotent. Only configures exporters if
    OTEL_EXPORTER_OTLP_ENDPOINT is set."""
    global _tracer_provider_initialized
    if _tracer_provider_initialized:
        return
    _tracer_provider_initialized = True

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        # No endpoint configured; leave default no-op provider in place
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        service_name = os.environ.get("OTEL_SERVICE_NAME", "grailzee-eval")
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter()  # reads env vars for endpoint + headers
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
    except ImportError:
        # opentelemetry not installed; silent no-op
        pass
    except Exception as exc:
        # Never let observability setup crash the application
        print(f"[grailzee_common] OTel init failed: {exc}", file=sys.stderr)


def get_tracer(name: str) -> Any:
    """Return an OTel tracer for the given module name.

    Returns a real tracer if OTEL_EXPORTER_OTLP_ENDPOINT is set and
    opentelemetry packages are importable. Otherwise returns a no-op
    tracer that satisfies the Tracer interface without emitting spans.
    """
    _init_tracer_provider()
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoOpTracer()


class _NoOpTracer:
    """Fallback tracer when opentelemetry is not installed at all.

    Implements the minimum interface needed so scripts can use
    `with tracer.start_as_current_span(...)` unconditionally."""

    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()


class _NoOpSpan:
    """No-op span satisfying the context-manager + attribute interface."""

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> bool:
        return False

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        pass

    def record_exception(self, *args: Any, **kwargs: Any) -> None:
        pass
