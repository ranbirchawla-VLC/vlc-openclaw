# ADR-0004: LedgerRow field nullability contract

**Status:** Accepted  
**Decided:** 2026-04-29  
**Sub-step:** 1.5 (corrective)  
**Implemented in:** `scripts/ingest_sales.py` — `LedgerRow`, `_row_to_csv_dict`

---

## Context

Sub-step 1.5 introduced `prune_by_sell_date`, which includes a defensive guard:
`if row.sell_date is None: keep`. At the same time, the Gate 2 corrective for 1.5
added a matching None guard in `_row_to_csv_dict` (`sell_date.isoformat() if
sell_date else ""`). Both changes were accepted but the `LedgerRow` type annotation
(`sell_date: date`) did not reflect the runtime posture — the code handled `None`
but the type system still prohibited it.

Deferring this to Phase 2 was considered and rejected. The gap between annotation and
runtime behavior is a contract ambiguity that affects every consumer of `LedgerRow`.
Resolving it as a Phase 1 decision eliminates the gap before the 1.7 orchestrator
and the Phase 2 read path are built.

---

## Decision

### D1 — `sell_date` is `date | None`

`LedgerRow.sell_date` is changed from `date` to `date | None`. Legacy rows that
predate sell_date tracking are represented with `sell_date=None`. Such rows:

- are never pruned (§10 rolling-window rule; `prune_by_sell_date` keeps them)
- serialize to empty string in the CSV sell_date column (consistent with the
  `buy_date` None→"" pattern established at A.6 migration)

`sell_date=None` has no default value in the dataclass; callers must pass it
explicitly. No row produced by `transform_jsonl` will have `sell_date=None`
(the `created_at` field is required; `SchemaShiftDetected` fires if absent). The
None case is reserved for rows loaded from a legacy CSV where the sell_date column
is blank.

**Data verification note:** The live `trade_ledger.csv` (14 rows queried 2026-04-29)
shows all rows have sell_date populated and account ∈ {NR, RES}. Design v1 references
eight UNKNOWN-account rows as legacy evidence for this posture; those rows could not
be verified from the current live ledger (design doc unavailable). The annotation
change is forward-compatible regardless and required for annotation/runtime coherence.

### D2 — `sell_cycle_id` stays `str` (non-optional)

All observed legacy rows (14 in live ledger; 13 in state_seeds backlog) have
`sell_cycle_id` populated. The field is required by the v2 ledger schema and derived
at every known write path (`backfill_ledger.py`, `migrate_ledger_v2.py`,
`_transform_jsonl_inner`). Rows with `sell_date=None` would still have been written
by a path that derived `sell_cycle_id` from the date at write time.

If the 1.7 read path encounters a CSV row with blank `sell_cycle_id`, it must raise
rather than silently construct a `LedgerRow(sell_cycle_id="")`. An empty
`sell_cycle_id` is a data-integrity signal, not a normal `None` state.

### D3 — All other required fields stay non-optional

Full audit, field by field:

| Field | Type | Verdict | Basis |
|---|---|---|---|
| `stock_id` | `str` | Non-optional | Required by `transform_jsonl`; `SchemaShiftDetected` if missing |
| `sell_date` | `date \| None` | **Nullable** | D1 above |
| `sell_cycle_id` | `str` | Non-optional | D2 above; all observed rows populated |
| `brand` | `str` | Non-optional | `backfill_ledger` validates non-empty; `transform_jsonl` defaults to `""` (non-None) |
| `reference` | `str` | Non-optional | Same validation pattern as brand |
| `account` | `str` | Non-optional | "NR", "RES" for new rows; legacy rows may carry "UNKNOWN" as a string — non-None in all cases |
| `buy_price` | `float` | Non-optional | Required by both write paths; `SchemaShiftDetected` if missing |
| `sell_price` | `float` | Non-optional | Same as buy_price |
| `buy_date` | `date \| None` | Nullable | Pre-existing; blank for all 14 live rows |
| `buy_cycle_id` | `str \| None` | Nullable | Pre-existing; blank for all 14 live rows |
| `buy_received_date` | `date \| None` | Nullable | Phase 1 addition; absent in pre-Phase-1 CSV rows |
| `sell_delivered_date` | `date \| None` | Nullable | Phase 1 addition; absent in pre-Phase-1 CSV rows |
| `buy_paid_date` | `date \| None` | Nullable | Phase 1 addition; absent in pre-Phase-1 CSV rows |

### D4 — Serialization: None → empty string, consistent with `buy_date`

`_row_to_csv_dict` renders `sell_date=None` as `""` (empty string). This is
identical to the `buy_date` None→"" pattern established in the A.6 migration and
present since the original implementation. The pattern is: nullable date fields
produce empty CSV columns; downstream readers that expect a date in these columns
must treat empty string as "not present."

---

## Rationale

Annotating `sell_date` as `date | None` when the runtime handles `None` but the
type says `date` produces a silent divergence that is worse than acknowledging the
nullable contract explicitly. The divergence would compound: every Phase 2 consumer
that reads the type annotation would believe sell_date is always a date and omit None
guards, producing crashes when legacy rows surface. Closing the gap in Phase 1 costs
one annotation change and three tests.

The `account` field does not need nullability despite legacy rows potentially carrying
"UNKNOWN". A string value (even a non-NR/non-RES string) is not `None`; nullability
and value-domain constraints are separate questions. Phase 2 may add account validation
at the read path, but that is a validation concern, not an annotation concern.

---

## Consequences

- `LedgerRow.sell_date` is `date | None`. Any caller that assumed `sell_date` is
  always a `date` may need a None guard. Within Phase 1, the affected callers are:
  - `prune_by_sell_date` (guard already present from 1.5)
  - `_row_to_csv_dict` (guard added in 1.5 Gate 2 corrective)
  - `_transform_jsonl_inner` (does not construct legacy rows; always has valid date)
  - Phase 2 read path: must handle empty sell_date column in CSV
- `sell_cycle_id` stays non-optional. The 1.7 read path inherits an obligation:
  raise on blank sell_cycle_id rather than silently produce an empty-string field.
- The `# type: ignore[arg-type]` comments in test fixtures are removed.

---

## Alternatives considered

**Keep `sell_date: date` and document the runtime divergence in a note.** Rejected.
Documents a known wrong annotation as acceptable. Every future type checker run and
IDE user would see `date` and write code without a None guard. The cost of closing the
gap now (one line) is lower than the ongoing cost of the divergence.

**Make `sell_date: date | None = None` (with default).** Rejected. A default of None
would make it possible to construct a LedgerRow without providing sell_date at all,
hiding silent omissions. Callers that accidentally omit sell_date would get a None row
rather than a TypeError. The field stays positional (no default); explicit `None`
must be passed.

**Audit further into buy_price/sell_price nullability.** Both are validated as
positive non-null numbers by every write path. Annotating them as `float | None`
would over-engineer forward compatibility that no observed data supports. Deferred.
