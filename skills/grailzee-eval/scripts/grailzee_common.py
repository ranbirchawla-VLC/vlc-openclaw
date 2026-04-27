"""Shared constants, formulas, and utilities for Grailzee Eval v2.

All constants, formulas, and reference-matching logic live here. Every
other script in skills/grailzee-eval/scripts/ imports from this module.

Extracted and refactored from the original v1 analyze_report.py and
evaluate_deal.py. Behavior preserved unless explicitly noted (see
RISK_RESERVE_THRESHOLD comment).
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import statistics
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
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
STATE_PATH    = f"{GRAILZEE_ROOT}/state"
BACKUP_PATH   = f"{GRAILZEE_ROOT}/backup"

# Phase A.2: config files (analyzer_config, brand_floors, sourcing_rules,
# cycle_focus, monthly_goals, quarterly_allocation, capacity_context)
# live in the repo's ``state/`` directory rather than on Drive. They
# ship with the code, unlike data files (cache, ledger, outcomes)
# which are generated at runtime and live on Drive via STATE_PATH.
# ``config_path(name)`` resolves against WORKSPACE_STATE_PATH.
WORKSPACE_STATE_PATH = str(
    (Path(__file__).resolve().parent.parent.parent.parent / "state")
)

CACHE_PATH          = f"{STATE_PATH}/analysis_cache.json"
LEDGER_PATH         = f"{STATE_PATH}/trade_ledger.csv"
NAME_CACHE_PATH     = f"{STATE_PATH}/name_cache.json"
CYCLE_FOCUS_PATH    = f"{STATE_PATH}/cycle_focus.json"
MONTHLY_GOALS_PATH  = f"{STATE_PATH}/monthly_goals.json"
QUARTERLY_PATH      = f"{STATE_PATH}/quarterly_allocation.json"
RUN_HISTORY_PATH    = f"{STATE_PATH}/run_history.json"


# ─── Business rules ───────────────────────────────────────────────────

NR_FIXED = 149              # NR account: $49 Grailzee fee + $100 shipping
RES_FIXED = 199             # Reserve account: $99 fee + $100 shipping

# B.5: platform-fee-only decomposition. Used for capital_required_* and
# expected_net_at_median_* per schema §3.1 (post-B.5 shipped shape).
# Analyzer ships gross-of-shipping/cost-of-capital; strategist layers
# those as separate inputs. Distinct from NR_FIXED/RES_FIXED above,
# which roll in the $100 shipping component and feed profit_nr /
# breakeven_nr. Platform fees are Grailzee-dictated, not a
# Vardalux-tunable parameter; kept as module constants rather than in
# analyzer_config.json.
PLATFORM_FEE_NR = 49
PLATFORM_FEE_RES = 99

# Fallback defaults for values now sourced from analyzer_config.json
# (v1.1 §2, Phase A.2 migration). The live value is read via
# load_analyzer_config(); these constants remain as the in-process
# fallback when the config file is missing or unreadable, and as the
# documented "factory default" matching the bootstrapped config.
TARGET_MARGIN = 0.05        # fallback default; live value in analyzer_config.json

# NOTE: v1 used RISK_RESERVE_THRESHOLD = 20 (percent). v2 uses fraction.
# All downstream consumers must use the fraction (0.40 = 40%).
RISK_RESERVE_THRESHOLD = 0.40  # fallback default; live value in analyzer_config.json

MIN_SALES_FOR_SCORING = 3   # fallback default; live value in analyzer_config.json
CACHE_SCHEMA_VERSION = 3    # v3 schema: market fields per-bucket (2b)

# Phase A.2: analyzer_config.json name + schema version + factory defaults.
# Factory defaults mirror the values bootstrapped by
# scripts/install_analyzer_config.py — they are the ground truth that
# load_analyzer_config() falls back to when the file is missing or
# malformed. After changing anything below, rerun the installer with
# --force to regenerate state/analyzer_config.json; the
# ``test_values_match_factory_defaults`` test in test_analyzer_config.py
# catches drift.
ANALYZER_CONFIG_NAME = "analyzer_config.json"
ANALYZER_CONFIG_SCHEMA_VERSION = 1
ANALYZER_CONFIG_FACTORY_DEFAULTS: dict = {
    "schema_version": ANALYZER_CONFIG_SCHEMA_VERSION,
    "windows": {
        "pricing_reports": 2,
        "trend_reports": 6,
    },
    "margin": {
        "per_trade_target_margin_fraction": 0.05,
        "monthly_return_target_fraction": 0.10,
    },
    "labor": {
        "hours_per_piece": 1.5,
    },
    "premium_model": {
        "lookback_days": 30,
        "close_count_floor": 5,
        "recent_weighted": True,
    },
    "scoring": {
        "min_sales_for_scoring": 3,
        "risk_reserve_threshold_fraction": 0.40,
        "premium_scalar_fraction": 0.10,
        "signal_thresholds": {
            "strong_max_risk_pct": 10,
            "normal_max_risk_pct": 20,
            "reserve_max_risk_pct": 30,
            "careful_max_risk_pct": 50,
        },
    },
}

# Phase A.4: sourcing_rules.json name + schema version + factory defaults.
# Factory defaults mirror the strategy-tunable fields lifted from
# build_brief.SOURCING_RULES — they are the ground truth that
# load_sourcing_rules() falls back to when the file is missing or
# malformed. After changing anything below, rerun the installer with
# --force to regenerate state/sourcing_rules.json; the
# ``test_values_match_factory_defaults`` test in test_sourcing_rules.py
# catches drift.
#
# Scope: strategy-tunable fields only. build_brief.py keeps
# platform_priority, us_inventory_only, never_exceed_max_buy as
# internal hardcoded fields per schema v1 S2.
SOURCING_RULES_NAME = "sourcing_rules.json"
SOURCING_RULES_SCHEMA_VERSION = 1
SOURCING_RULES_FACTORY_DEFAULTS: dict = {
    "schema_version": SOURCING_RULES_SCHEMA_VERSION,
    "condition_minimum": "Very Good",
    "papers_required": True,
    "keyword_filters": {
        "include": [
            "full set", "complete set", "box papers", "BNIB", "like new",
            "excellent", "very good", "AD", "authorized",
        ],
        "exclude": [
            "watch only", "no papers", "head only", "international",
            "damaged", "for parts", "aftermarket", "rep", "homage",
        ],
    },
}

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
    "buy_date", "sell_date", "buy_cycle_id", "sell_cycle_id",
    "brand", "reference", "account", "buy_price", "sell_price",
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

def _target_margin() -> float:
    """Live target-margin fraction, sourced from analyzer_config.json.

    Reads via the memoized loader; falls back to TARGET_MARGIN constant
    when the config file is missing. Exists so max_buy formulas stay
    one-liners at the call site.
    """
    cfg = load_analyzer_config()
    return cfg["margin"]["per_trade_target_margin_fraction"]


def max_buy_nr(median: float) -> float:
    """MAX BUY for No Reserve account.

    Formula: (median - 149) / (1 + target_margin), floored to nearest $10.
    Target margin is sourced from analyzer_config.json (Phase A.2).
    Floor-round ensures every dollar at or below max_buy clears the 5% floor.
    """
    return math.floor((median - NR_FIXED) / (1 + _target_margin()) / 10) * 10


def max_buy_reserve(median: float) -> float:
    """MAX BUY for Reserve account.

    Formula: (median - 199) / (1 + target_margin), floored to nearest $10.
    Target margin is sourced from analyzer_config.json (Phase A.2).
    Floor-round ensures every dollar at or below max_buy clears the 5% floor.
    """
    return math.floor((median - RES_FIXED) / (1 + _target_margin()) / 10) * 10


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
    Target margin is sourced from analyzer_config.json (Phase A.2).
    """
    adjusted_median = median * (1 + premium_adjustment_pct / 100)
    return math.floor((adjusted_median - fixed_cost) / (1 + _target_margin()) / 10) * 10


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

    Use this for FUZZY matching only (e.g. evaluate_deal's user-input
    lookup). For strict canonical-form joins (ledger-to-cache matching),
    use ``canonical_reference`` instead — it preserves separators so
    canonical Pro-report refs like ``5500V/110A-B148`` stay intact.
    """
    s = normalize_ref(s)
    # Strip leading M (Tudor convention)
    if s.startswith("M") and len(s) > 5:
        s = s[1:]
    # Strip trailing -XXXX suffixes
    s = re.sub(r"-\d{4}$", "", s)
    # Remove all separators for comparison
    return s.replace("-", "").replace(".", "").replace(" ", "")


def canonical_reference(s: str) -> str:
    """Strip the per-piece inventory suffix from a reference.

    Tudor per-piece inventory IDs append a ``-NNNN`` sequence to the
    canonical reference (e.g. ``M28500-0005``, ``79470-0001``). This
    helper strips that suffix only. The leading ``M`` is preserved
    because the Grailzee Pro report legitimately carries distinct
    canonical references with and without M-prefix as DIFFERENT
    watches (observed live: ``79360N`` and ``M79360N`` are two
    separate scored entries with different medians).

    Rules, applied in order:
      1. ``normalize_ref`` (upper, trim, strip trailing ``.0``)
      2. Strip trailing ``-NNNN`` (exactly 4 digits; inventory sequence)

    Separators elsewhere are preserved so Pro-report references like
    ``5500V/110A-B148`` and ``26238CE.OO.1300CE.01`` pass through
    unchanged. Idempotent on already-canonical inputs.

    For the full ledger-to-cache join (suffix-strip PLUS M-prefix
    fallback when the suffix-stripped form has no cache entry), see
    ``resolve_to_cache_ref``. This helper is the string-shape layer;
    the resolver is the cache-context layer.

    Distinct from ``strip_ref``, which additionally removes all
    separators for fuzzy substring matching.
    """
    s = normalize_ref(s)
    s = re.sub(r"-\d{4}$", "", s)
    return s


def resolve_to_cache_ref(cache_keys: Any, ledger_ref: str) -> Optional[str]:
    """Map a ledger reference to the matching cache key, if any.

    Two-tier resolution avoids the false-positive collision when the
    Pro-report data has both ``79360N`` and ``M79360N`` as distinct
    canonical references:

      1. Apply ``canonical_reference`` (suffix strip only). If the
         result is a key in ``cache_keys``, return it.
      2. Else, if the result starts with ``M`` followed by a digit,
         strip the leading ``M`` and try again. Handles Tudor
         per-piece inventory IDs like ``M28500-0005`` where the
         canonical Pro-report reference is ``28500`` (no M-prefix
         variant exists in cache).

    Returns ``None`` if neither form is present in ``cache_keys``.

    ``cache_keys`` can be any container supporting the ``in``
    operator — typically ``set[str]`` or a ``dict`` with reference
    keys.
    """
    canon = canonical_reference(ledger_ref)
    if canon in cache_keys:
        return canon
    if len(canon) >= 2 and canon[0] == "M" and canon[1].isdigit():
        stripped = canon[1:]
        if stripped in cache_keys:
            return stripped
    return None


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
    in read_ledger.py.

    Phase A.6 / schema v1 §4: buy_date/sell_date split (from the old
    single ``date_closed``) and both cycle ids stored explicitly. Legacy
    rows migrated at A.6 cutover carry buy_date=None, buy_cycle_id=None.
    """
    sell_date: date
    sell_cycle_id: str
    brand: str
    reference: str
    account: str
    buy_price: float
    sell_price: float
    buy_date: Optional[date] = None
    buy_cycle_id: Optional[str] = None


def _parse_iso_date(raw: str) -> date:
    y, m, d = raw.split("-")
    return date(int(y), int(m), int(d))


def parse_ledger_csv(ledger_path: Optional[str] = None) -> list[LedgerRow]:
    """Read trade_ledger.csv and return a list of LedgerRow (v2 schema).

    Returns empty list if file is missing or empty (header-only).
    Raises ValueError on malformed rows OR when the file header does
    not match LEDGER_COLUMNS — hard cutover means a v1-shape file feeds
    through this function as an error, not a silent misread.
    """
    path = ledger_path or LEDGER_PATH
    if not os.path.exists(path):
        return []
    rows: list[LedgerRow] = []
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        required = {"sell_date", "sell_cycle_id"}
        missing = required - set(header)
        if missing:
            raise ValueError(
                f"Ledger {path} missing required v2 columns {sorted(missing)}; "
                f"header was {header}. Phase A.6 migrated the schema — "
                f"run migrate_ledger_v2.py on any v1 file before reading."
            )
        for i, raw in enumerate(reader, start=2):
            try:
                sell_date = _parse_iso_date(raw["sell_date"])
                buy_raw = (raw.get("buy_date") or "").strip()
                buy_date: Optional[date] = (
                    _parse_iso_date(buy_raw) if buy_raw else None
                )
                buy_cycle_raw = (raw.get("buy_cycle_id") or "").strip()
                buy_cycle_id: Optional[str] = buy_cycle_raw or None
                rows.append(LedgerRow(
                    sell_date=sell_date,
                    sell_cycle_id=raw["sell_cycle_id"],
                    brand=raw["brand"],
                    reference=raw["reference"],
                    account=raw["account"],
                    buy_price=float(raw["buy_price"]),
                    sell_price=float(raw["sell_price"]),
                    buy_date=buy_date,
                    buy_cycle_id=buy_cycle_id,
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
    """Append one trade to trade_ledger.csv. Creates file if missing.

    Writes the v2 column order defined in LEDGER_COLUMNS:
    buy_date, sell_date, buy_cycle_id, sell_cycle_id, brand, reference,
    account, buy_price, sell_price. buy_date / buy_cycle_id render as
    empty strings when None (legacy-row convention from A.6 migration).
    """
    path = ensure_ledger_exists(ledger_path)
    buy_date_str = row.buy_date.isoformat() if row.buy_date else ""
    buy_cycle_str = row.buy_cycle_id or ""
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            buy_date_str,
            row.sell_date.isoformat(),
            buy_cycle_str,
            row.sell_cycle_id,
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


def cycle_outcome_path(cycle_id: str) -> str:
    """Per-cycle outcome file path (Phase A.5).

    Each cycle rollup writes to its own file so a loop of rollups does not
    overwrite prior results. Replaces the prior single-file CYCLE_OUTCOME_PATH
    constant. Consumers computing 'previous cycle outcome' resolve the
    previous cycle_id first, then pass it here.
    """
    return f"{STATE_PATH}/cycle_outcome_{cycle_id}.json"


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


def cycle_id_from_csv(csv_path: str) -> str:
    """Extract date from CSV filename (grailzee_YYYY-MM-DD.csv), return cycle_id.

    Falls back to cycle_id_from_date(today) if filename doesn't match pattern.
    """
    import re
    basename = os.path.basename(csv_path)
    m = re.search(r"(\d{4}-\d{2}-\d{2})", basename)
    if m:
        y, mo, d = m.group(1).split("-")
        return cycle_id_from_date(date(int(y), int(mo), int(d)))
    return cycle_id_from_date(date.today())


# ─── Config file resolution + analyzer_config cache ──────────────────


def config_path(name: str) -> str:
    """Resolve a config file name to its absolute path under the
    workspace ``state/`` directory.

    Single source of truth for locating the strategy-writable config
    files introduced in Phase A (analyzer_config.json, brand_floors.json,
    sourcing_rules.json, cycle_focus.json, monthly_goals.json,
    quarterly_allocation.json, capacity_context.json). These files ship
    with the repo (unlike data files on Drive) so they resolve against
    WORKSPACE_STATE_PATH, not the Drive-backed STATE_PATH. Callers that
    need a custom root (tests, dry-runs) should not use this helper and
    should pass their paths explicitly.

    Strips leading/trailing slashes from ``name`` to protect against
    accidental absolute paths. Raises ValueError on empty name.
    """
    if not isinstance(name, str):
        raise ValueError(
            f"config_path: name must be str, got {type(name).__name__}"
        )
    stripped = name.strip().strip("/")
    if not stripped:
        raise ValueError("config_path: name must be a non-empty string")
    if ".." in stripped.split("/"):
        raise ValueError(
            f"config_path: name {name!r} contains '..' "
            f"(would escape the state directory)"
        )
    return f"{WORKSPACE_STATE_PATH}/{stripped}"


# Module-level cache for analyzer_config. First call reads from disk;
# subsequent calls return the cached dict. A process is expected to
# live no longer than a single analyzer run, so a cached read matches
# the cycle-boundary change-propagation rule from schema design v1
# Section 5: config edits apply on the next analyzer run. Tests that
# need fresh reads call ``_reset_analyzer_config_cache()``.
_analyzer_config_cache: dict | None = None
_analyzer_config_source: str = "uninitialized"


def _reset_analyzer_config_cache() -> None:
    """Test helper: clear the memoized analyzer_config.

    Production code must not call this; it exists so tests can switch
    between file-present and file-absent conditions in a single process.
    """
    global _analyzer_config_cache, _analyzer_config_source
    _analyzer_config_cache = None
    _analyzer_config_source = "uninitialized"


def analyzer_config_source() -> str:
    """Return where the last load_analyzer_config() call got its data.

    One of: 'uninitialized' (never loaded), 'file' (read from disk),
    'fallback' (file missing or malformed; factory defaults used).
    Exposed for span attribution.
    """
    return _analyzer_config_source


def load_analyzer_config(path: Optional[str] = None) -> dict:
    """Return the live analyzer_config dict, memoized for the process.

    Read-once semantics are intentional. The cache-once-per-process
    pattern matches the change-propagation rule from grailzee schema
    design v1 Section 5: analyzer_config edits take effect at the next
    cycle boundary (i.e. the next analyzer run), not mid-run. A single
    process represents one cycle's evaluation, so caching the first
    read is correct — re-reading mid-run would let a concurrent
    strategy edit flip thresholds underneath the scoring loop.

    Tests that need to exercise both file-present and file-absent
    paths in one process call ``_reset_analyzer_config_cache()``
    between scenarios.

    Args:
        path: Override the default ``STATE_PATH/analyzer_config.json``.
              First call after a reset wins; subsequent calls return
              the cached dict regardless of their ``path`` argument.

    Returns:
        The parsed config dict with the full §2.1 shape. Always returns
        a complete dict: missing keys are backfilled from
        ``ANALYZER_CONFIG_FACTORY_DEFAULTS`` so consumers can safely
        access nested paths without guards. A fallback read (file
        absent or malformed) returns a deep copy of the factory
        defaults, matching today's hardcoded constants exactly.

    Fallback behavior:
        A missing file, unreadable JSON, or schema_version > 1 is
        logged to stderr once and falls back to factory defaults. The
        analyzer proceeds with identical behavior to the pre-A.2 code.
        Downstream phases may tighten this to fail-loud once A.2-A.5
        are stable.
    """
    global _analyzer_config_cache, _analyzer_config_source
    if _analyzer_config_cache is not None:
        return _analyzer_config_cache

    resolved = path or config_path(ANALYZER_CONFIG_NAME)
    fallback = _deep_copy(ANALYZER_CONFIG_FACTORY_DEFAULTS)

    if not os.path.exists(resolved):
        _analyzer_config_cache = fallback
        _analyzer_config_source = "fallback"
        return _analyzer_config_cache

    # Local import: config_helper imports grailzee_common for
    # get_tracer, so a top-level import would be circular.
    from scripts.config_helper import (
        SchemaVersionError,
        read_config,
        schema_version_or_fail,
    )
    try:
        parsed = read_config(resolved)
        schema_version_or_fail(parsed, ANALYZER_CONFIG_SCHEMA_VERSION)
    except (OSError, json.JSONDecodeError, SchemaVersionError, ValueError) as exc:
        print(
            f"[grailzee_common] analyzer_config read failed ({exc}); "
            f"falling back to factory defaults",
            file=sys.stderr,
        )
        _analyzer_config_cache = fallback
        _analyzer_config_source = "fallback"
        return _analyzer_config_cache

    _analyzer_config_cache = _merge_onto_defaults(parsed, fallback)
    _analyzer_config_source = "file"
    return _analyzer_config_cache


def _deep_copy(source: dict) -> dict:
    """Return a fresh deep copy of ``source`` via JSON round-trip.

    Generic helper shared across Phase A loaders (analyzer_config,
    sourcing_rules, …). JSON round-trip also guarantees the shape is
    serializable, which is a reasonable safety check for config-shaped
    dicts.
    """
    return json.loads(json.dumps(source))


def _merge_onto_defaults(overlay: dict, base: dict) -> dict:
    """Deep-merge ``overlay`` onto ``base``. Overlay values win.

    Used so a config file that omits a section inherits the factory
    default for that section rather than crashing a consumer. Only
    dicts recurse; other types replace wholesale.
    """
    merged = json.loads(json.dumps(base))
    for key, value in overlay.items():
        if (
            isinstance(value, dict)
            and isinstance(merged.get(key), dict)
        ):
            merged[key] = _merge_onto_defaults(value, merged[key])
        else:
            merged[key] = value
    return merged


# ─── sourcing_rules cache (Phase A.4) ────────────────────────────────

# Module-level cache mirroring the analyzer_config pattern. First call
# reads from disk; subsequent calls return the cached dict. A process
# is expected to live no longer than a single analyzer run, so a cached
# read matches the cycle-boundary change-propagation rule from schema
# design v1 Section 5: sourcing_rules edits apply on the next analyzer
# run. Tests that need fresh reads call ``_reset_sourcing_rules_cache()``.
_sourcing_rules_cache: dict | None = None
_sourcing_rules_source: str = "uninitialized"


def _reset_sourcing_rules_cache() -> None:
    """Test helper: clear the memoized sourcing_rules.

    Production code must not call this; it exists so tests can switch
    between file-present and file-absent conditions in a single process.
    """
    global _sourcing_rules_cache, _sourcing_rules_source
    _sourcing_rules_cache = None
    _sourcing_rules_source = "uninitialized"


def sourcing_rules_source() -> str:
    """Return where the last load_sourcing_rules() call got its data.

    One of: 'uninitialized' (never loaded), 'file' (read from disk),
    'fallback' (file missing or malformed; factory defaults used).
    Exposed for span attribution.
    """
    return _sourcing_rules_source


def load_sourcing_rules(path: Optional[str] = None) -> dict:
    """Return the live sourcing_rules dict, memoized for the process.

    Read-once semantics are intentional. The cache-once-per-process
    pattern matches the change-propagation rule from grailzee schema
    design v1 Section 5: sourcing_rules edits take effect at the next
    cycle boundary (i.e. the next analyzer run), not mid-run. A single
    process represents one cycle's evaluation, so caching the first
    read is correct — re-reading mid-run would let a concurrent
    strategy edit change sourcing rules between the JSON brief write
    and the markdown brief write.

    Tests that need to exercise both file-present and file-absent
    paths in one process call ``_reset_sourcing_rules_cache()``
    between scenarios.

    Args:
        path: Override the default ``WORKSPACE_STATE_PATH/sourcing_rules.json``.
              First call after a reset wins; subsequent calls return
              the cached dict regardless of their ``path`` argument.

    Returns:
        The parsed config dict with the full §2.3 shape. Always returns
        a complete dict: missing keys are backfilled from
        ``SOURCING_RULES_FACTORY_DEFAULTS`` so consumers can safely
        access nested paths without guards. A fallback read (file
        absent or malformed) returns a deep copy of the factory
        defaults, matching the historical build_brief.SOURCING_RULES
        values exactly.

    Fallback behavior:
        A missing file, unreadable JSON, or schema_version > 1 is
        logged to stderr once and falls back to factory defaults. The
        analyzer proceeds with identical behavior to the pre-A.4 code.
        Downstream phases may tighten this to fail-loud once A.2-A.5
        are stable.
    """
    global _sourcing_rules_cache, _sourcing_rules_source
    if _sourcing_rules_cache is not None:
        return _sourcing_rules_cache

    resolved = path or config_path(SOURCING_RULES_NAME)
    fallback = _deep_copy(SOURCING_RULES_FACTORY_DEFAULTS)

    if not os.path.exists(resolved):
        _sourcing_rules_cache = fallback
        _sourcing_rules_source = "fallback"
        return _sourcing_rules_cache

    # Local import avoids circular dependency (config_helper
    # imports grailzee_common for get_tracer).
    from scripts.config_helper import (
        SchemaVersionError,
        read_config,
        schema_version_or_fail,
    )
    try:
        parsed = read_config(resolved)
        schema_version_or_fail(parsed, SOURCING_RULES_SCHEMA_VERSION)
    except (OSError, json.JSONDecodeError, SchemaVersionError, ValueError) as exc:
        print(
            f"[grailzee_common] sourcing_rules read failed ({exc}); "
            f"falling back to factory defaults",
            file=sys.stderr,
        )
        _sourcing_rules_cache = fallback
        _sourcing_rules_source = "fallback"
        return _sourcing_rules_cache

    _sourcing_rules_cache = _merge_onto_defaults(parsed, fallback)
    _sourcing_rules_source = "file"
    return _sourcing_rules_cache


# ─── Premium adjustment (read by run_analysis) ────────────────────────


def apply_premium_adjustment(all_results: dict, adjustment_pct: float) -> None:
    """Mutate all_results references: recalculate max_buy with premium.

    Called when ledger has 10+ trades at >= 8% avg presentation premium.
    Uses adjusted_max_buy() to recompute max_buy_nr and max_buy_res.
    """
    for ref, rd in all_results.get("references", {}).items():
        median = rd.get("median")
        if median is None:
            continue
        rd["max_buy_nr"] = adjusted_max_buy(median, NR_FIXED, adjustment_pct)
        rd["max_buy_res"] = adjusted_max_buy(median, RES_FIXED, adjustment_pct)


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

    Post-B.1: the returned ``adjustment`` field is observational only.
    ``apply_premium_adjustment`` is no longer called by ``run_analysis``
    (schema v1 §7/§3.1). Do not remove this function as dead code
    without checking callers — two non-pipeline callers remain and
    surface the stats block to the user:

      * ``ledger_manager.cmd_premium``  — the `premium` CLI subcommand
      * ``write_cache._build_premium_status`` — populates the cache's
        ``premium_status`` block

    Thresholds (count >= 10, avg >= 8.0) are hardcoded here and are
    NOT sourced from ``analyzer_config.premium_model.*`` (backlog #4).
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

    def add_event(
        self,
        name: str,
        attributes: Any = None,
        timestamp: Any = None,
    ) -> None:
        pass
