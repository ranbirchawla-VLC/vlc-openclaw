# ADR-0001: Rule Y dedup-and-update semantics

**Status:** Accepted  
**Decided:** 2026-04-29  
**Sub-step:** 1.4  
**Implemented in:** `scripts/ingest_sales.py` — `merge_rows`, `_merge_rows_inner`

---

## Context

The ledger redo (Phase 1) processes one JSONL batch file per ingest run. The
trade ledger is a full rewrite on each run: existing rows are loaded into memory,
new rows from the batch are merged in, and the result is written atomically. Rule Y
defines the merge classification: each incoming row is checked against the existing
set by `stock_id` (the dedup key per design v1 §6) and is either added, updated,
or skipped.

Four positions were decided before implementation and are recorded here for
contributors who hit edge cases and need to understand the reasoning.

---

## Decision

### Position 1 — Equality semantics

`merge_rows` uses `LedgerRow.__eq__` for the skip-unchanged check. `LedgerRow` is a
`frozen=True` dataclass; Python generates field-by-field `==` automatically. No
custom comparator is defined.

Float fields (`buy_price`, `sell_price`) are stable across the CSV round-trip because
`atomic_write_csv` serializes them via `f"{v:.2f}"` (sub-step 1.3). A row constructed
from a CSV parse and a row constructed directly from the same float literals compare
equal. Callers must not introduce precision drift (e.g., from arithmetic on price
values) between the `existing` and `new` arguments to `merge_rows`.

### Position 2 — Legacy collision

The live trade ledger contains eight rows with `account="UNKNOWN"` that predate
account-code derivation. When a new batch yields a row whose `stock_id` matches one
of those legacy rows, Rule Y's standard classification applies: if any field differs
(as it will, because the new row will have a real account code), the existing row is
replaced in place. No special case for `UNKNOWN` account rows.

Forward-only posture means the system does not reprocess historical batches. It does
not mean legacy rows are frozen. When WatchTrack reports new truth for a stock ID,
the ledger updates to reflect it.

### Position 3 — Duplicate stock_id within new batch

If the `new` list contains two or more rows with the same `stock_id`,
`merge_rows` raises `ERPBatchInvalid` before any modification to the result list.
The error message identifies the colliding `stock_id`. This is treated as an
extraction-agent contract violation: the extraction agent is required to emit at most
one row per `stock_id` per batch, because WatchTrack models each stock ID as a unique
sale event.

### Position 4 — Order and mutation

`merge_rows` preserves the order of `existing`: updates land at the original position
of the replaced row; new rows append at the end of the result in the order they appear
in `new`. The function returns a new list and does not mutate either input argument.
This enables safe accumulation across multiple batch files in the Phase 1 orchestrator
(sub-step 1.7) without defensive copying at each call site.

---

## Corrupt-existing posture (docstring-only)

If the `existing` list contains duplicate `stock_id` values (pre-existing ledger
corruption), `_merge_rows_inner` builds the `existing_index` with last-occurrence-wins
semantics because the dict comprehension iterates forward and later entries overwrite
earlier ones. This behavior is undefined by the spec and deterministic only because of
Python dict semantics. Corruption repair is outside the scope of Phase 1; if it
becomes necessary, a dedicated repair tool should be built rather than adding a guard
to the hot path. The position is noted in the `merge_rows` docstring.

---

## Alternatives considered

**Custom float comparator with epsilon tolerance.** Rejected. Epsilon arithmetic
introduces a new class of decision: what epsilon is correct? The `f"{v:.2f}"`
serialization contract from sub-step 1.3 is the simpler and more auditable guarantee.
If the serialization contract changes, the equality posture should be revisited.

**Raise on legacy collision.** Rejected. The eight UNKNOWN-account rows are known
data quality debt. Treating collision as an error would block every future ingest that
touches one of those eight stock IDs, requiring manual intervention before each run.
The forward-only posture already handles this correctly.
