# ADR-0005: WatchTrack extraction agent emits JSONL with flat type-discriminated records

**Status:** Accepted
**Decided:** 2026-04-29
**Sub-step:** 1.2 corrective pass
**Implemented in:** `scripts/ingest_sales.py` — `transform_jsonl`, `_transform_jsonl_inner`

---

## Context

Phase 1 Gate 3 (2026-04-29) failed at line 2 char 1 of `watchtrack_full_final.jsonl`
with `json.JSONDecodeError: Extra data`. Sub-step 1.2's `_transform_jsonl_inner` called
`json.loads(path.read_text())` on the entire file and then iterated `raw["sales"]` and
`raw["purchases"]`. The real WatchTrack extract is line-delimited JSONL, not a single
JSON document with nested arrays.

Design v1 §7 correctly describes the real schema. Sub-step 1.2's build prompt named
specific transaction IDs (TEY1104, TEY1048, etc.) without embedding the actual record
content; the build agent invented the single-document wrapper shape. Design v1 §13.1
also contained a test list referencing `ERPBatchInvalid` on three "ambiguous-services"
cases, which contradicted design v1 §11's statement that validity belongs to the
extraction agent. This internal inconsistency is resolved by this ADR and the
corrective pass.

---

## Decision

The WatchTrack extraction agent's output placed at
`$GRAILZEE_DATA_ROOT/sales_data/watchtrack_YYYY-MM-DD.jsonl` is JSONL:

- **Line-delimited.** One JSON object per line. No wrapper structure.
- **Flat records.** Each line is a complete, independent transaction record.
- **Type-discriminated.** Every record carries a top-level `type` field with one of
  three values: `"Sale"`, `"Purchase"`, `"Trade"`.

`transform_jsonl` parses the file line-by-line (`json.loads` per non-blank line), not
as a single JSON document. Records are bucketed by `type` into in-memory Sale and
Purchase sets before the join. `Trade` records are silently skipped. Any type value
other than these three raises `SchemaShiftDetected`.

`json.JSONDecodeError` on any line is wrapped into `SchemaShiftDetected` with the line
number and offending content snippet attached, so operator-facing telemetry remains
structured even on parse failures.

---

## Field contract confirmed from production records

Field paths verified by locating them in three records extracted verbatim from the
production fixture `watchtrack_full_final.jsonl` (sha256 `029238eb558a2aea...`) and
embedded in the 1.2 rebuild prompt per post-mortem §5 mandatory rule:

| Field path | Observed in |
|---|---|
| `Sale.type` | `"Sale"` — TEY1083, TEY1048 |
| `Sale.platform` | `["Grailzee"]` (list, not string) — TEY1083, TEY1048 |
| `Sale.status` | `"Fulfilled"`, `"Pending"` — TEY1083 (Fulfilled), TEY1092 (Pending) |
| `Sale.created_at` | `"2026-03-02T18:56:45Z"` — TEY1083 |
| `Sale.services[].name` | `"Platform fee"` — TEY1083 (full shape), TEY1048 (minimal) |
| `Sale.services[].actual_cost` | `99` — TEY1083; `49` — TEY1048 |
| `Sale.line_items[].stock_id` | `"57238"` — TEY1083; `"297Z8"` — TEY1048 |
| `Sale.line_items[].brand` | `"Tudor"` — TEY1083 |
| `Sale.line_items[].reference_number` | `"M79360N-0024"` — TEY1083 |
| `Sale.line_items[].cost_of_item` | `8900` — TEY1083; `12000` — TEY1048 |
| `Sale.line_items[].unit_price` | `9850` — TEY1083; `11000` — TEY1048 |
| `Sale.line_items[].delivered_date` | `"2026-03-04T15:30:10.61Z"` — TEY1083 |
| `Purchase.type` | `"Purchase"` — TEYPA1061 |
| `Purchase.created_at` | `"2026-02-02T14:31:25Z"` — TEYPA1061 |
| `Purchase.line_items[0].delivered_date` | `"2026-02-04T18:45:18Z"` — TEYPA1061 |
| `Purchase.payments[].payment_date` | `"2026-02-02T16:20:38Z"` — TEYPA1061 |

Key finding: `line_items` is a plural list on both Sale and Purchase records. The
pre-rebuild implementation used `line_item` (singular) — a second bug beyond the
JSONL parsing bug.

---

## Validity boundary

Validity rules (empty services, anomalous fee structures, multi-service entries,
non-{49,99} Platform fee amounts in real production data) belong to the extraction
agent per design v1 §11. `transform_jsonl` trusts its input and raises
`SchemaShiftDetected` only on structural parse failures: unparseable JSON, missing
`type` field, unknown type value, and fields required for the transform (created_at,
line_items, stock_id, cost_of_item, unit_price, Platform fee entry).

The `ERPBatchInvalid` class is not raised by `transform_jsonl`. It is raised by
`merge_rows` (duplicate stock_id within a single batch) — an extraction-agent
contract violation at the batch level.

---

## Rejected alternative

**Single JSON document with `{"sales": [...], "purchases": [...]}` wrapper.** This was
the hallucinated shape sub-step 1.2 was built against. It does not exist in the data
and never has. All design v1 §13.1 test cases that referenced this shape or its
`raw["sales"]` / `raw["purchases"]` iteration pattern are struck and replaced with
JSONL-aware tests derived from real production records.

---

## Consequences

- Any consumer of the JSONL artifact (cowork bundle reader, future analyzers) must
  parse the file line-by-line, not as a single JSON document.
- All test fixtures for `transform_jsonl` are real-derived subsets of the production
  fixture. Synthetic JSONL files are prohibited for data-shape fixtures per the
  post-mortem §5 rule.
- `transform_jsonl` returns `tuple[list[LedgerRow], list[dict]]` — the second element
  is the list of skipped-row entries `{transaction_id, reason}` (currently populated
  only for Pending Sales). The orchestrator threads this into `IngestManifest.rows_skipped`.
