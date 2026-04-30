# ADR-0006: Real-data sample records required in build prompts for data-shape sub-steps

**Status:** Accepted
**Decided:** 2026-04-29
**Origin:** `Vardalux_Postmortem_Spec_Reality_Gap_2026-04-29.md` §5
**Implemented in:** SUPERVISOR_ROLE.md v2 — "Code prompt shape" and "Pre-emit audit" sections

---

## Context

Phase 1 Gate 3 (2026-04-29) failed at line 2, char 1 of `watchtrack_full_final.jsonl`.
The build agent's `_transform_jsonl_inner` called `json.loads(path.read_text())` and
then iterated `raw["sales"]` and `raw["purchases"]`. The real WatchTrack extract is
line-delimited JSONL with no wrapper structure.

The root cause was not the parse call. It was that the sub-step 1.2 build prompt named
specific transaction IDs (`TEY1104`, `TEY1048`, etc.) without embedding the actual record
content. The build agent invented the single-document wrapper schema from design v1 §7's
prose description alone. Test fixtures were authored to match the invented shape; 308
tests across 7 sub-steps passed against the hallucinated schema. The failure surfaced only
at Gate 3 when the real fixture was loaded for the first time.

This is a structural failure mode: the build agent cannot distinguish a correct schema
from a plausible one if it has never seen real records. Prose descriptions and field tables
in design documents are not a substitute for embedded record content. The agent reads
prose as specification; it reads embedded records as constraint.

---

## Decision

Before authoring any spec, test fixture, or data-shape description for a sub-step that
parses, transforms, validates, or emits records from an external system, the prompt author
(supervisor) must:

1. **Read real records from the source.** Not a schema doc, not a field table — the actual
   bytes that the parser will consume.
2. **Embed at minimum three verbatim records in the build prompt.** Complete, unmodified,
   character-for-character. Include records that cover the type variety the parser handles
   (e.g., Sale, Purchase, Trade in the WatchTrack case).
3. **Draw test fixture content from embedded records.** Test fixtures for data-shape
   coverage must be derived from the embedded records, not authored from spec text.
4. **Name what you verified.** The prompt must explicitly state which fields were confirmed
   by reading real records and from which records the verification came.

---

## Scope

**Applies when:** a sub-step implementation parses, transforms, validates, or produces
records whose shape is determined by an external system (API, CRM export, JSONL extract,
CSV dump, etc.).

**Does not apply when:** the sub-step operates entirely on data whose shape is defined by
this codebase (e.g., a `LedgerRow` dataclass we own; a config file we write).

**Threshold:** if you would use the word "schema" or "format" to describe what the code
must handle, this rule applies.

---

## Rejected alternatives

**Reference the schema doc and trust the build agent.** This is how sub-step 1.2 was
built. It produced a correct-looking implementation against an invented schema. The
failure cost: rebuilt parser, 8 deleted test fixtures, 7 new real-derived fixtures,
ADR-0005, full corrective pass.

**Embed a field table instead of full records.** Field tables describe structure; they do
not expose encoding details, null patterns, or structural surprises (e.g., `line_items`
vs `line_item`, `services=[]` vs populated). Full records are required.

---

## Consequences

- Gate 3 failures caused by schema hallucination are prevented at prompt-authoring time,
  not discovered at production load time.
- ADR-0005 is the downstream locked decision produced by the corrective pass this rule
  would have prevented.
- Every sub-step prompt that touches external-system records must list the source records
  used and confirm the fields verified. The supervisor pre-emit audit (SUPERVISOR_ROLE.md
  v2) enforces this before prompt emission.
- The principle underlying this rule, stated at the class level: **the build agent
  cannot distinguish a correct schema from a plausible one without real data. Spec text
  and field tables do not close this gap.**
