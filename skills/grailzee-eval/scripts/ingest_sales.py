"""Grailzee ledger ingest pipeline: schema, dataclasses, path resolution.

Phase 1 of the ledger redo per Grailzee_Ledger_Redo_Design_v1.md.
Sub-step 1.1: schema, error hierarchy, path resolution. No I/O yet.

Design note: the spec uses $GRAILZEE_DATA_ROOT; the existing codebase uses
GRAILZEE_ROOT. They are the same path. This module uses GRAILZEE_ROOT to
match the code convention (grailzee_common.GRAILZEE_ROOT). Recorded in
design v1 §14 open item 1.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


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
