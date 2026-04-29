"""Grailzee ledger ingest pipeline: schema, dataclasses, path resolution.

Phase 1 of the ledger redo per Grailzee_Ledger_Redo_Design_v1.md.
Sub-step 1.1: schema, error hierarchy, path resolution. No I/O yet.

Design note: the spec uses $GRAILZEE_DATA_ROOT; the existing codebase uses
GRAILZEE_ROOT. They are the same path. This module uses GRAILZEE_ROOT to
match the code convention (grailzee_common.GRAILZEE_ROOT). Recorded in
design v1 §14 open item 1.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from scripts.grailzee_common import cycle_id_from_date


LEDGER_SCHEMA_VERSION = 1


# ─── Error hierarchy (§12.3) ─────────────────────────────────────────


class IngestError(Exception):
    """Base class for all ingest pipeline errors."""


class ERPBatchInvalid(IngestError):
    """Extraction agent halted; batch file absent or structurally invalid.

    The ingest tool sees no new file in sales_data/ when the extraction
    agent halts. When a file is present but structurally wrong, this error
    is raised before any ledger write.
    """


class LedgerWriteFailed(IngestError):
    """Atomic rewrite of trade_ledger.csv failed.

    Covers: rename failure, fsync failure, permission denied, disk full.
    The ledger is unchanged when this is raised (temp file was not renamed).
    """


class LockAcquisitionFailed(IngestError):
    """Exclusive lock on trade_ledger.lock not acquired within timeout.

    Raised after the configured timeout (default 30 seconds). The caller
    surfaces this to the bot as a transient failure; the operator retries.
    """


class SchemaShiftDetected(IngestError):
    """JSONL shape diverges from the extraction contract.

    Raised when a top-level key expected by the transformation logic is
    absent, or when a field's type has changed. Ingest halts before any
    write. Operator sees the failure and the design chat reopens.
    """


# ─── Schema (design v1 §6) ───────────────────────────────────────────


@dataclass(frozen=True)
class LedgerRow:
    """One Grailzee trade, sourced from WatchTrack ERP extract.

    Thirteen fields per design v1 §6. Immutable: downstream merge and
    prune operations produce new instances rather than mutating in place.

    CSV column order on cutover: existing columns first (sell_date,
    buy_date, sell_cycle_id, buy_cycle_id, brand, reference, account,
    buy_price, sell_price) for backward compatibility, then the four new
    columns appended (stock_id, buy_received_date, sell_delivered_date,
    buy_paid_date) per §6 CSV ordering note. Downstream Python consumers
    access fields by name; column order is a CSV-serialization concern.
    """

    # Required fields -- always populated on a valid Grailzee Sale
    stock_id: str
    sell_date: date
    sell_cycle_id: str
    brand: str
    reference: str
    account: str           # "NR" or "RES"; derived from Platform fee actual_cost
    buy_price: float       # Sale line_item.cost_of_item
    sell_price: float      # Sale line_item.unit_price (gross of platform fees)

    # Optional fields -- empty when matching Purchase not found or dates absent
    buy_date: date | None = None
    buy_cycle_id: str | None = None
    buy_received_date: date | None = None   # Purchase line_item.delivered_date
    sell_delivered_date: date | None = None  # Sale line_item.delivered_date
    buy_paid_date: date | None = None       # min(payment_date) across Purchase.payments


# ─── Manifest (design v1 §12.2) ──────────────────────────────────────


@dataclass
class IngestManifest:
    """Outcome of one ingest_sales invocation.

    Intentionally mutable (not frozen). The orchestrator (sub-step 1.7)
    builds the manifest incrementally as each file is processed -- it
    updates rows_added, rows_updated, etc. after each file and at the end
    of the prune step. Freezing would require building a complete dict up
    front and constructing once, which forces the orchestrator to carry
    accumulation state separately. The current shape is the cleaner design.
    """

    files_found: int               # all .jsonl files in sales_data/ (excluding archive/)
    files_processed: int           # files successfully ingested this run
    files_skipped: list[str] = field(default_factory=list)  # filenames not processed
    last_processed: str | None = None  # filename of the most recently processed file
    rows_added: int = 0
    rows_updated: int = 0
    rows_unchanged: int = 0
    rows_unmatched: int = 0        # rows with empty buy-side dates (no Purchase match)
    rows_pruned: int = 0
    error: IngestError | None = None  # None on success


# ─── Path resolution (design v1 §5, §12.1) ───────────────────────────


def _get_data_root() -> Path:
    """Return GRAILZEE_ROOT from the environment.

    Raises EnvironmentError if the variable is not set or is empty.
    Design §5 names this variable $GRAILZEE_DATA_ROOT; the code uses
    GRAILZEE_ROOT -- same path, different document names.
    """
    root = os.environ.get("GRAILZEE_ROOT", "").strip()
    if not root:
        raise EnvironmentError(
            "GRAILZEE_ROOT environment variable is not set or is empty. "
            "Set it to the GrailzeeData root directory path, or pass "
            "an explicit path argument to ingest_sales()."
        )
    return Path(root)


def _resolve_ledger_path(override: Path | None = None) -> Path:
    """Resolve trade_ledger.csv. Precedence: explicit arg > env > error."""
    if override is not None:
        return override
    return _get_data_root() / "state" / "trade_ledger.csv"


def _resolve_sales_data_dir(override: Path | None = None) -> Path:
    """Resolve sales_data/ directory. Precedence: explicit arg > env > error."""
    if override is not None:
        return override
    return _get_data_root() / "sales_data"


def _resolve_archive_dir(override: Path | None = None) -> Path:
    """Resolve sales_data/archive/. Precedence: explicit arg > env > error."""
    if override is not None:
        return override
    return _get_data_root() / "sales_data" / "archive"


def _resolve_lock_path(override: Path | None = None) -> Path:
    """Resolve trade_ledger.lock. Precedence: explicit arg > env > error."""
    if override is not None:
        return override
    return _get_data_root() / "state" / "trade_ledger.lock"


# ─── Date helpers ────────────────────────────────────────────────────


def _parse_date(s: str) -> date:
    """Parse an ISO date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS...)."""
    return date.fromisoformat(s.split("T")[0])


def _parse_date_opt(s: str | None) -> date | None:
    """Parse an optional ISO date string; None for None or empty string."""
    if not s:
        return None
    return _parse_date(s)


# ─── Transformation (design v1 §7) ───────────────────────────────────

# Platform fee → account code mapping per §7 step 4.
_PLATFORM_FEE_TO_ACCOUNT: dict[int, str] = {49: "NR", 99: "RES"}


def transform_jsonl(path: Path) -> list[LedgerRow]:
    """Read one watchtrack_*.jsonl batch file; return LedgerRow list.

    The file contains a single JSON object with top-level "sales" and
    "purchases" arrays (the extraction agent's atomic batch contract).
    Only Sales where "Grailzee" in platform are emitted. Each emitted
    row represents one line item; the Sale's stock_id is the dedup key.

    Raises:
        SchemaShiftDetected: missing top-level "sales" or "purchases"
            key; missing line_item.stock_id on a Grailzee Sale; missing
            line_item.cost_of_item on a Purchase that matches a Sale.
        ERPBatchInvalid: empty services[], no "Platform fee" entry,
            actual_cost is None, or actual_cost maps to neither NR nor
            RES. These are extraction-agent contract violations per §11.
    """
    raw = json.loads(path.read_text())

    for key in ("sales", "purchases"):
        if key not in raw:
            raise SchemaShiftDetected(
                f"Missing required top-level key '{key}' in {path.name}."
            )

    # Index Purchases by line_item.stock_id for O(1) join.
    purchase_by_sid: dict[str, dict] = {}
    for purchase in raw["purchases"]:
        sid = (purchase.get("line_item") or {}).get("stock_id")
        if sid:
            purchase_by_sid[sid] = purchase

    rows: list[LedgerRow] = []

    for sale in raw["sales"]:
        if "Grailzee" not in sale.get("platform", ""):
            continue

        raw_li = sale.get("line_item")
        if not raw_li:
            raise SchemaShiftDetected(
                f"Missing or empty line_item on a Grailzee Sale in {path.name}."
            )
        li = raw_li
        stock_id = li.get("stock_id")
        if not stock_id:
            raise SchemaShiftDetected(
                f"Missing line_item.stock_id on Grailzee Sale in {path.name}."
            )

        # §11 validity: services block must be non-empty and contain
        # a "Platform fee" entry with a non-null actual_cost.
        services = sale.get("services") or []
        if not services:
            raise ERPBatchInvalid(
                f"Sale {stock_id}: empty services[] — "
                "extraction agent must halt batches with missing services."
            )

        platform_fee = next(
            (s for s in services if s.get("name") == "Platform fee"), None
        )
        if platform_fee is None:
            names = [s.get("name", "") for s in services]
            raise ERPBatchInvalid(
                f"Sale {stock_id}: no 'Platform fee' service entry "
                f"(found: {names}) — extraction-agent contract violation."
            )

        actual_cost = platform_fee.get("actual_cost")
        if actual_cost is None:
            raise ERPBatchInvalid(
                f"Sale {stock_id}: Platform fee actual_cost is null."
            )

        cost_key = round(float(actual_cost))
        account = _PLATFORM_FEE_TO_ACCOUNT.get(cost_key)
        if account is None:
            raise ERPBatchInvalid(
                f"Sale {stock_id}: Platform fee actual_cost={actual_cost} "
                "does not map to NR ($49) or RES ($99)."
            )

        if "created_at" not in sale:
            raise SchemaShiftDetected(
                f"Missing created_at on Grailzee Sale {stock_id} in {path.name}."
            )
        if "cost_of_item" not in li:
            raise SchemaShiftDetected(
                f"Missing line_item.cost_of_item on Grailzee Sale {stock_id}."
            )
        if "unit_price" not in li:
            raise SchemaShiftDetected(
                f"Missing line_item.unit_price on Grailzee Sale {stock_id}."
            )
        sell_date = _parse_date(sale["created_at"])
        sell_cycle_id = cycle_id_from_date(sell_date)
        sell_delivered_date = _parse_date_opt(li.get("delivered_date"))

        purchase = purchase_by_sid.get(stock_id)
        if purchase is not None:
            p_li = purchase.get("line_item") or {}
            if "cost_of_item" not in p_li:
                raise SchemaShiftDetected(
                    f"Missing line_item.cost_of_item on Purchase "
                    f"matching {stock_id}."
                )
            buy_date = _parse_date_opt(purchase.get("created_at"))
            buy_cycle_id = cycle_id_from_date(buy_date) if buy_date else None
            buy_received_date = _parse_date_opt(p_li.get("delivered_date"))
            payments = purchase.get("payments") or []
            if payments:
                pdates = [
                    _parse_date(p["payment_date"])
                    for p in payments
                    if p.get("payment_date")
                ]
                buy_paid_date = min(pdates) if pdates else None
            else:
                buy_paid_date = None
        else:
            buy_date = None
            buy_cycle_id = None
            buy_received_date = None
            buy_paid_date = None

        rows.append(LedgerRow(
            stock_id=stock_id,
            sell_date=sell_date,
            sell_cycle_id=sell_cycle_id,
            brand=li.get("brand", ""),
            reference=li.get("reference_number", ""),
            account=account,
            buy_price=float(li["cost_of_item"]),
            sell_price=float(li["unit_price"]),
            buy_date=buy_date,
            buy_cycle_id=buy_cycle_id,
            buy_received_date=buy_received_date,
            sell_delivered_date=sell_delivered_date,
            buy_paid_date=buy_paid_date,
        ))

    return rows
