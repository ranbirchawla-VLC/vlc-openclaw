# ADR-0003: Schema versioning posture for trade_ledger.csv

**Status:** Accepted  
**Decided:** 2026-04-29  
**Sub-step:** 1.1 (MINOR 2)  
**Implemented in:** `scripts/ingest_sales.py` — `LEDGER_SCHEMA_VERSION = 1`

---

## Context

The ledger redo adds four columns to `trade_ledger.csv` (`stock_id`,
`buy_received_date`, `sell_delivered_date`, `buy_paid_date`). Design v1 §6 appends
these after the nine legacy columns to preserve backward compatibility with any
downstream consumer that reads by column index. The question at sub-step 1.1 was
how to version the schema so that consumers can detect and handle format changes.

---

## Decision

`LEDGER_SCHEMA_VERSION` is a Python-side module constant. It does not appear in the
CSV file in any form — not as a dedicated column, not as a header comment, not in a
sidecar file.

Schema versioning is enforced by coordinating three things:
1. The `LedgerRow` dataclass definition.
2. `LEDGER_CSV_COLUMNS` — the canonical column list used by `atomic_write_csv`.
3. Downstream consumers (`_read_full_ledger`, cowork, reporting) that access fields
   by name via `csv.DictReader`.

When the schema changes, all three change together in the same commit. `MINOR 2` at
sub-step 1.1 is a marker that this decision was considered and made deliberately;
it is not a patch number that appears in any output.

---

## Rationale

**Per-row version column produces mixed-version CSV.** Legacy rows already in the
ledger have no version field. Adding a `schema_version` column to new rows produces a
file where old rows have `""` and new rows have `"1"`. Any consumer that validates the
version column must handle this mixed state, which negates the benefit.

**Per-file sentinel breaks raw-CSV consumers.** The cowork bundle reader and external
reporting tools open `trade_ledger.csv` as a plain CSV file. A sentinel row at the
top (e.g., `# schema_version=1`) or a sidecar file requires every consumer to be
updated before a schema change ships. This couples unrelated consumers to each other's
release timing.

**Name-keyed access and append-at-end already provide forward compatibility.** Design
v1 §6's rule — new columns append after the nine legacy columns — means that a
consumer written against the nine-column schema reads the new file without modification:
`csv.DictReader` ignores unknown columns by default, and the nine fields it knows
about are still present in the same positions. This covers the common case (adding
columns) without any version plumbing.

**Incompatible changes (column removal, type change, rename) require coordinated
deployment regardless of versioning strategy.** A sentinel does not make this easier;
it only adds a detection step. The correct response to an incompatible change is a
migration script, not a version bump in the file.

---

## Consequences

- Any Python code that reads `trade_ledger.csv` and accesses a new column by name
  will silently return `""` if run against a pre-Phase-1 ledger file (before the new
  columns exist). Callers that need the new columns must handle empty-string values.
  This is consistent with the `None`-for-missing-date semantics in `LedgerRow`.

- If a schema change is incompatible (not an append), a migration script must be
  written and run before the new code deploys. There is no auto-detection mechanism;
  the operator is responsible for sequencing the migration.

- `LEDGER_SCHEMA_VERSION` is available for internal assertions or logging if a
  migration script needs to confirm its own version context. It is not a runtime
  dispatch mechanism.

---

## Alternatives considered

**Per-file sidecar (`trade_ledger.csv.version`).** Rejected; adds a new file to track
and sync. Atomicity of the sidecar relative to the CSV is not guaranteed.

**Version as first CSV column.** Rejected; breaks column-index consumers and produces
mixed-version files.

**Header comment (`# version=1` as first line).** Rejected; not valid CSV; breaks
`csv.DictReader` unless consumers strip it explicitly.
