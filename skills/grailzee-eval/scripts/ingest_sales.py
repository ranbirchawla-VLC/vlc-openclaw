"""Grailzee ledger ingest pipeline: schema, dataclasses, path resolution.

Phase 1 of the ledger redo per Grailzee_Ledger_Redo_Design_v1.md.
Sub-step 1.1: schema, error hierarchy, path resolution. No I/O yet.

Design note: the spec uses $GRAILZEE_DATA_ROOT; the existing codebase uses
GRAILZEE_ROOT. They are the same path. This module uses GRAILZEE_ROOT to
match the code convention (grailzee_common.GRAILZEE_ROOT). Recorded in
design v1 §14 open item 1.
"""

from __future__ import annotations

import csv
import fcntl
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import IO, Any, Generator

from scripts.grailzee_common import cycle_id_from_date, get_tracer

tracer = get_tracer(__name__)


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

    # Required positional fields. sell_date is nullable: legacy rows that
    # predate sell_date tracking are represented with sell_date=None and
    # must not be pruned (design v1 §10, ADR-0004).
    stock_id: str
    sell_date: date | None
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


@dataclass(frozen=True)
class MergeCounts:
    """Outcome counts from a single merge_rows call (design v1 §8)."""

    added: int = 0
    updated: int = 0
    unchanged: int = 0


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


# Local-filesystem default for the advisory lockfile. Must not resolve to
# Google Drive or any other FUSE mount — flock() is unreliable on FUSE.
# Override via GRAILZEE_LOCK_PATH env var. ~/.grailzee/ is unambiguously
# local on macOS. Env var naming follows the GRAILZEE_ prefix convention
# from grailzee_common.GRAILZEE_ROOT.
LEDGER_LOCK_DEFAULT: Path = Path.home() / ".grailzee" / "trade_ledger.lock"


def _resolve_lock_path(override: Path | None = None) -> Path:
    """Resolve trade_ledger.lock. Precedence: explicit arg > GRAILZEE_LOCK_PATH > local default.

    Unlike the data-path resolvers, this function never raises on a missing env
    var: the lockfile does not need to colocate with the ledger data and has a
    sensible local default. The default is always on a real local filesystem.
    """
    if override is not None:
        return override
    env_val = os.environ.get("GRAILZEE_LOCK_PATH", "").strip()
    if env_val:
        return Path(env_val)
    return LEDGER_LOCK_DEFAULT


# ─── CSV column order (design v1 §6) ─────────────────────────────────

# Canonical CSV column order for trade_ledger.csv. Matches
# grailzee_common.LEDGER_COLUMNS for the first 9 fields (backward
# compatibility with consumers that read by column index), then appends
# the four new columns introduced in Phase 1. Downstream Python
# consumers access by name and ignore unknown columns.
LEDGER_CSV_COLUMNS: list[str] = [
    "buy_date", "sell_date", "buy_cycle_id", "sell_cycle_id",
    "brand", "reference", "account", "buy_price", "sell_price",
    "stock_id", "buy_received_date", "sell_delivered_date", "buy_paid_date",
]


def _row_to_csv_dict(row: LedgerRow) -> dict:
    """Serialize a LedgerRow to a flat dict suitable for csv.DictWriter.

    date fields → ISO string; None → empty string; floats pass through.
    """
    return {
        "stock_id": row.stock_id,
        "buy_date": row.buy_date.isoformat() if row.buy_date else "",
        "sell_date": row.sell_date.isoformat() if row.sell_date else "",
        "buy_cycle_id": row.buy_cycle_id or "",
        "sell_cycle_id": row.sell_cycle_id,
        "brand": row.brand,
        "reference": row.reference,
        "account": row.account,
        "buy_price": f"{row.buy_price:.2f}",
        "sell_price": f"{row.sell_price:.2f}",
        "buy_received_date": (
            row.buy_received_date.isoformat() if row.buy_received_date else ""
        ),
        "sell_delivered_date": (
            row.sell_delivered_date.isoformat() if row.sell_delivered_date else ""
        ),
        "buy_paid_date": row.buy_paid_date.isoformat() if row.buy_paid_date else "",
    }


# ─── Lock primitives (design v1 §9) ──────────────────────────────────

_POLL_INTERVAL = 0.05  # seconds between flock() retries


def _acquire_flock(fd: IO[Any], mode: int, timeout: float, path: Path) -> None:
    """Poll flock(LOCK_NB) until success or timeout. Raises LockAcquisitionFailed."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, mode | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LockAcquisitionFailed(
                    f"Could not acquire lock on {path} within {timeout:.1f}s."
                )
            time.sleep(min(_POLL_INTERVAL, remaining))


def _open_and_lock(path: Path, mode: int, deadline: float) -> IO[Any]:
    """Open the lockfile and acquire flock, retrying on inode change (B2).

    Guards against the split-brain race where another process deletes and
    recreates the lockfile between this process's open() and flock(): after
    flock() succeeds, compare the fd's inode (os.fstat) to the current inode
    at path (os.stat). If they differ, the lock was acquired on a stale inode;
    release and retry from open() with the remaining budget.

    Returns the locked fd. Caller is responsible for LOCK_UN and close() on
    all exit paths.

    Raises:
        LockAcquisitionFailed: if the deadline elapses across all attempts.
    """
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LockAcquisitionFailed(
                f"Could not acquire lock on {path}: deadline elapsed."
            )
        fd = open(path, "a")
        try:
            _acquire_flock(fd, mode, remaining, path)
        except LockAcquisitionFailed:
            fd.close()
            raise
        # Inode re-check: confirm fd still points to the file currently at path.
        try:
            fd_ino = os.fstat(fd.fileno()).st_ino
            try:
                path_ino = os.stat(path).st_ino
            except FileNotFoundError:
                path_ino = None
            if path_ino is not None and fd_ino == path_ino:
                return fd
            # Stale inode: release lock, fall through to retry.
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError as exc:
            fd.close()
            raise LockAcquisitionFailed(
                f"OSError during inode re-check on {path}: {exc}"
            ) from exc
        try:
            fd.close()
        except OSError as exc:
            raise LockAcquisitionFailed(
                f"OSError closing stale lockfile {path}: {exc}"
            ) from exc


@contextmanager
def with_exclusive_lock(
    path: Path, timeout: float = 30
) -> Generator[None, None, None]:
    """Acquire a POSIX advisory exclusive lock (LOCK_EX) on path.

    Creates the lockfile parent directory and the lockfile itself on first
    use. Applies the inode re-check after flock() acquisition (see
    _open_and_lock). The lock is released when the context exits, whether
    by normal return or exception.

    Raises:
        LockAcquisitionFailed: if the exclusive lock cannot be acquired
            within timeout seconds.
    """
    with tracer.start_as_current_span("ingest_sales.with_exclusive_lock") as span:
        span.set_attribute("lock_path", str(path))
        span.set_attribute("timeout", timeout)
        path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout
        fd = _open_and_lock(path, fcntl.LOCK_EX, deadline)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()


@contextmanager
def with_shared_lock(
    path: Path, timeout: float = 30
) -> Generator[None, None, None]:
    """Acquire a POSIX advisory shared lock (LOCK_SH) on path.

    Multiple processes may hold LOCK_SH simultaneously. LOCK_SH is
    incompatible with LOCK_EX: each blocks the other's acquisition.
    Applies the inode re-check after flock() acquisition.

    Used by cowork bundle assembly (Phase 2) to read trade_ledger.csv
    safely while the ingest generator may be writing.

    Raises:
        LockAcquisitionFailed: if the shared lock cannot be acquired
            within timeout seconds.
    """
    with tracer.start_as_current_span("ingest_sales.with_shared_lock") as span:
        span.set_attribute("lock_path", str(path))
        span.set_attribute("timeout", timeout)
        path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout
        fd = _open_and_lock(path, fcntl.LOCK_SH, deadline)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()


# ─── Atomic CSV write (design v1 §9) ─────────────────────────────────


def atomic_write_csv(
    path: Path,
    rows: list[LedgerRow],
    header: list[str] | None = None,
) -> None:
    """Write rows to path atomically via tmp-file-and-rename.

    Always writes the full file: header + all rows. There is no append
    path; the ledger is read-modify-write under exclusive lock per §8.
    Calls fsync before rename so a crash or power loss after rename cannot
    surface an empty or truncated ledger.

    The tmp file is path + ".tmp" (e.g., trade_ledger.csv.tmp). On rename
    failure the tmp file may remain; cleanup is a separate concern.

    Args:
        path: target CSV path.
        rows: LedgerRow instances to write, in the order supplied.
        header: column names in write order. Defaults to LEDGER_CSV_COLUMNS.

    Raises:
        LedgerWriteFailed: on any OSError during write, fsync, or rename.
    """
    with tracer.start_as_current_span("ingest_sales.atomic_write_csv") as span:
        span.set_attribute("target_path", str(path))
        span.set_attribute("row_count", len(rows))
        custom_header = header is not None
        effective_header = header if custom_header else LEDGER_CSV_COLUMNS
        # extrasaction="raise" enforces the schema contract when using the
        # default header — a key in _row_to_csv_dict that isn't in
        # LEDGER_CSV_COLUMNS indicates a programmer error. Callers that
        # pass an explicit header are electing a subset write and opt into
        # "ignore" (their responsibility).
        extrasaction = "ignore" if custom_header else "raise"
        tmp = Path(str(path) + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=effective_header,
                    extrasaction=extrasaction,
                )
                writer.writeheader()
                for row in rows:
                    writer.writerow(_row_to_csv_dict(row))
                f.flush()
                os.fsync(f.fileno())
            os.rename(tmp, path)
        except (OSError, ValueError) as exc:
            raise LedgerWriteFailed(str(exc)) from exc


# ─── Merge — Rule Y (design v1 §8) ───────────────────────────────────


def merge_rows(
    existing: list[LedgerRow],
    new: list[LedgerRow],
) -> tuple[list[LedgerRow], MergeCounts]:
    """Merge new rows into existing per Rule Y (design v1 §8).

    Three-way classification per stock_id:
    - stock_id absent from existing → append new row. counts.added += 1.
    - stock_id present, LedgerRow.__eq__ matches → skip. counts.unchanged += 1.
    - stock_id present, any field differs → replace in place at existing
      position. counts.updated += 1.

    Position 1 (equality semantics): dataclass __eq__ compares field-by-field
    with ==. Float fields (buy_price, sell_price) serialized via f"{v:.2f}"
    through the CSV round-trip produce stable IEEE 754 values for valid price
    inputs. Direct LedgerRow construction uses the same float literals; callers
    must not introduce precision drift between the existing and new rows.

    If `new` contains two rows with the same stock_id, raises ERPBatchInvalid
    identifying the colliding stock_id before any work is done. This is an
    extraction-agent contract violation; the agent must emit at most one row
    per stock_id per batch.

    Corrupt-existing posture: if `existing` itself contains duplicate stock_id
    values (pre-existing ledger corruption), the index is built last-occurrence-
    wins (Python dict iteration order). The merge updates the last-occurrence
    slot and leaves the first-occurrence row untouched, producing a result that
    still has two rows for the same stock_id. This is deterministic but
    unspecified by the design. Corrupt ledger repair is a separate concern;
    see ADR-0001.

    Returns a new list; existing and new inputs are not mutated.
    """
    with tracer.start_as_current_span("ingest_sales.merge_rows") as span:
        span.set_attribute("existing_count", len(existing))
        span.set_attribute("new_count", len(new))
        result, counts = _merge_rows_inner(existing, new)
        span.set_attribute("added", counts.added)
        span.set_attribute("updated", counts.updated)
        span.set_attribute("unchanged", counts.unchanged)
        return result, counts


def _merge_rows_inner(
    existing: list[LedgerRow],
    new: list[LedgerRow],
) -> tuple[list[LedgerRow], MergeCounts]:
    """Private implementation of merge_rows. The OTEL span lives on the
    public wrapper; this function contains only business logic. Implements
    Rule Y three-way classification (add / update-in-place / skip-unchanged)
    and the duplicate-in-new-batch pre-check per design v1 §8."""
    seen_new: set[str] = set()
    for row in new:
        if row.stock_id in seen_new:
            raise ERPBatchInvalid(
                f"Duplicate stock_id '{row.stock_id}' in new batch: "
                "extraction-agent contract violation."
            )
        seen_new.add(row.stock_id)

    result: list[LedgerRow] = list(existing)
    existing_index: dict[str, int] = {
        row.stock_id: i for i, row in enumerate(existing)
    }
    added = 0
    updated = 0
    unchanged = 0

    for row in new:
        if row.stock_id not in existing_index:
            result.append(row)
            added += 1
        else:
            idx = existing_index[row.stock_id]
            if result[idx] == row:
                unchanged += 1
            else:
                result[idx] = row
                updated += 1

    return result, MergeCounts(added=added, updated=updated, unchanged=unchanged)


# ─── Prune — rolling window (design v1 §10) ──────────────────────────


def prune_by_sell_date(
    rows: list[LedgerRow],
    today: date,
    window_days: int = 180,
) -> tuple[list[LedgerRow], int]:
    """Return (kept_rows, pruned_count) applying the rolling-window rule (§10).

    A row is kept if its sell_date is >= (today - window_days). The boundary
    is inclusive. Rows where sell_date is None are always kept: they represent
    pre-A.6 legacy rows without a sell date and must not be silently discarded.
    Input order is preserved in the returned list.

    Args:
        rows: current ledger contents.
        today: reference date for the window calculation.
        window_days: rolling window length in days (default 180).

    Returns:
        Tuple of (kept_rows, pruned_count).
    """
    with tracer.start_as_current_span("ingest_sales.prune_by_sell_date") as span:
        span.set_attribute("input_count", len(rows))
        span.set_attribute("today", today.isoformat())
        span.set_attribute("window_days", window_days)
        kept, pruned_count = _prune_by_sell_date_inner(rows, today, window_days)
        span.set_attribute("kept_count", len(kept))
        span.set_attribute("pruned_count", pruned_count)
        return kept, pruned_count


def _prune_by_sell_date_inner(
    rows: list[LedgerRow],
    today: date,
    window_days: int,
) -> tuple[list[LedgerRow], int]:
    """Private implementation of prune_by_sell_date. OTEL span lives on the
    public wrapper; this function contains only business logic. Iterates rows
    once, classifying each as kept (sell_date >= boundary or None) or pruned
    (sell_date < boundary). Boundary = today - timedelta(days=window_days)."""
    boundary = today - timedelta(days=window_days)
    kept: list[LedgerRow] = []
    pruned = 0
    for row in rows:
        if row.sell_date is None or row.sell_date >= boundary:
            kept.append(row)
        else:
            pruned += 1
    return kept, pruned


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
    with tracer.start_as_current_span("ingest_sales.transform_jsonl") as span:
        span.set_attribute("source_file", path.name)
        return _transform_jsonl_inner(path, span)


def _transform_jsonl_inner(path: Path, span: object) -> list[LedgerRow]:
    """Inner implementation; span is the ambient OTel span from the caller."""
    raw = json.loads(path.read_text())

    # Set sales_total before any raise so the attribute is present even on
    # SchemaShiftDetected (missing-key path). Uses .get() because the key
    # being absent is exactly the error we're about to check.
    span.set_attribute("sales_total", len(raw.get("sales", [])))

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

    try:
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
    finally:
        span.set_attribute("rows_emitted", len(rows))

    return rows
