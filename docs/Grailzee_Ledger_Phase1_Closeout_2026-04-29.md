# Grailzee Ledger Redo — Phase 1 Closeout

**Date:** 2026-04-29
**Version:** v2 — supervisor-side durability work completed in this session.
**Status:** Phase 1 shipped. Production ledger canonical. Branch ready to merge to `main` after fixture commit.
**Branch (pre-merge):** `feature/grailzee-ledger-phase1-v2`
**Authority:** Permanent record of what Phase 1 delivered. Successor sessions reference this as the authoritative summary.

**Predecessors:**
- `Grailzee_Ledger_Redo_Design_v1.md` — locked spec
- `Grailzee_Ledger_Redo_Design_v1_1.md` — amendments locked 2026-04-29
- `Grailzee_Ledger_Redo_Design_Session_Handoff_2026-04-28.md` — design handoff
- `Grailzee_ShapeK_Resume_2026-04-28.md` — sequencing context, sibling track
- `Grailzee_Ledger_Phase1_Corrective_Pass_Handoff_2026-04-29.md` — corrective handoff
- `Grailzee_Ledger_Phase1_Closeout_Handoff_2026-04-29.md` — closeout handoff
- `Vardalux_Postmortem_Spec_Reality_Gap_2026-04-29.md` — methodology lock
- `docs/decisions/ADR-0006-real-data-sample-records-rule.md`
- `docs/decisions/ADR-0007-why-this-matters-rule.md`
- `SUPERVISOR_ROLE.md` v2

---

## 1. What shipped

The three business goals from design v1 §1, status post-cutover:

**§1.1 — Complete Grailzee performance visibility.** Delivered. Every closed Grailzee trade in `trade_ledger.csv` derives from the WatchTrack canonical extract via the validated Phase 1 pipeline. Sufficient precision for cycle, monthly, and rolling-window performance review.

**§1.2 — System-driven reference focus.** Delivered on the data side. Strategy skill input is canonical. Live consumption smoke test deferred to next cycle (operator decision); coverage will land via unit tests against the consumption layer rather than a live skill invocation against production state.

**§1.3 — WatchTrack as single source of truth.** Delivered on the input side. Cutover regenerated the production ledger from WatchTrack; pre-redo rows (8 UNKNOWN-account from Telegram + 6 other legacy) do not carry forward. Operational follow-up named below: deprecating the Telegram `ledger_manager.py log` path closes §1.3 fully.

---

## 2. Build summary

Phase 1 was Python-only — no plugin, no Telegram, no MCP — per design v1 §13.1. Sub-step pattern: each sub-step a paste-ready Code prompt, three-gate discipline (Gate 1 automated tests, Gate 2 code-reviewer subagent in fresh context, Gate 3 real-data smoke).

**Sub-steps shipped:**
1.1 Schema, dataclasses, path resolution
1.2 Single-file ingest transformation (parser rebuilt during corrective pass)
1.3 Lockfile and atomic write
1.4 Merge and prune logic
1.5 Archive move
1.6 Manifest assembly
1.7 Orchestrator entry point

**Test counts at branch tip:**
- ledger: 332 green
- eval: 1366 green / 71 skipped
- cowork: 235 green

**Key commits on `feature/grailzee-ledger-phase1-v2`:**
- `e003427` — parser rebuild + ADR-0005 (extraction-agent JSONL contract)
- `66fe0ec` — integration fixture cascade (Phase 1 build complete)
- `ae80d3a` — production ledger cutover script + execution
- (fixture commit, post-cutover) — canonical Gate 3 fixture with NR/RES relabels per closeout handoff §2 decision 3

---

## 3. Cutover outcome

The production ledger was regenerated from WatchTrack on 2026-04-29 per the cutover prompt and design v1 §2 amendment (cutover regenerates from canonical source — see v1.1 amendment 7).

| Verification | Expected | Actual |
|---|---|---|
| Row count post-prune | 16 | 16 |
| NR | 11 | 11 |
| RES | 5 | 5 |
| UNKNOWN | 0 | 0 |
| Schema | 13 columns | 13 columns |
| `.bak` file | exists, not overwritten | exists, 882 bytes, intact |
| Pruned (>6 months) | 3 (TEY1007, TEY1021, TEY1022) | 3 |
| Skipped (Pending) | 2 (TEY1104, TEY1092) | 2 |
| Idempotency | second run no-op | confirmed |

`trade_ledger.csv.pre-redo-2026-04-29.bak` retained at the canonical Grailzee data root as the recovery path.

---

## 4. Customer-facing failure — named and resolved

Phase 1 burned seven sub-steps and 308 tests against a hallucinated schema before real-data Gate 3 caught the failure. The build agent had invented a wrapper schema (`{"sales": [...], "purchases": [...]}`) and implemented `json.loads(path.read_text())` against the JSONL fixture; tests passed because the test fixtures shared the invented schema. The failure surfaced at line 2, character 1, of the real fixture parse.

The corrective pass rebuilt the parser correctly (`transform_jsonl` reads line-delimited JSON with type-discriminated records), fixed test fixtures to slice from the real WatchTrack data, and locked the §6.1 validity decision (`SchemaShiftDetected` on `services=[]` Grailzee Sales — validity belongs to extraction-agent territory, not to the parser).

**Methodology gap closed in this session:**
- `Vardalux_Postmortem_Spec_Reality_Gap_2026-04-29.md` §5 — sample-records rule (standing reference).
- `docs/decisions/ADR-0006-real-data-sample-records-rule.md` — accepted, binding.
- `docs/decisions/ADR-0007-why-this-matters-rule.md` — accepted, binding.
- `SUPERVISOR_ROLE.md` v2 — both rules encoded in "Code prompt shape" and "Failure modes" sections; pre-emit audit added; methodology rules section added as single anchor.

The customer-facing failure event is resolved. The methodology that allowed it is closed.

---

## 5. Locked decisions during corrective pass

Five decisions from the closeout handoff §2, recorded here as the permanent record:

1. **§6.1 validity decision.** `transform_jsonl` raises `SchemaShiftDetected` on `services=[]` Grailzee Sales (option C). Validity belongs to extraction-agent territory, not to the parser.
2. **Pending-skip filter.** `transform_jsonl` skips top-level `status == "Pending"` Sales with manifest entry; re-evaluable on next batch when status flips. Idempotent by construction.
3. **Fixture data fix.** Operator hand-edited the canonical Gate 3 fixture: 6 earliest legacy Grailzee Sales relabeled RES ($99 Platform fee), 5 later legacy + TEY1081/TEY1091/TEY1092 filled with NR ($49 Platform fee). 14 records edited; sha256 byte-identical copy at the canonical Drive path.
4. **Consignment in scope.** Design v1 §2's "consignment out of scope" line is struck. Consignment Sales are real Grailzee performance and belong in the ledger. Translator-not-calculator: pass through, downstream interprets.
5. **Cutover regenerates from source.** Design v1 §2's "forward-only, does not reprocess history" line is struck. WatchTrack is the canonical source (§1.3); cutover regenerates the ledger from it.

All five locked into design v1.1 amendments (4, 5, 3, 6, 7 respectively).

---

## 6. What did not ship in Phase 1

Phase 2 work, named in design v1 §13:

- Plugin scaffold — `ingest_sales` registered as the fifth grailzee-eval tool, with Pydantic `_Input` model and unified error envelope routing.
- Bot capability route — Telegram trigger phrase, manifest-shape formatting.
- Cowork shared-lock wrapping — `_read_full_ledger` wrapped in `with_shared_lock(...)`.
- Phase 2 Gate 3 smoke — real extract drop, real bot command, real ledger update via the deployed surface.

These open in a separate build cycle. Sequencing is the next-steps design session's call.

---

## 7. Operational follow-ups (named, not Phase 1 blockers)

1. **Telegram `ledger_manager.py log` path deprecation.** §1.3 is achieved on the input side via cutover, but the manual-entry path still exists in code. Without removal, an operator under pressure can reintroduce the duplicate-entry / UNKNOWN-account problem. Recommend deprecation: either remove the command or make it raise on invocation pointing at WatchTrack as the canonical path.
2. **Strategy-skill ledger-consumption documentation.** New column ordering post-cutover (per design §6: new columns appended at end). Brief operator-facing note.
3. **Strategy-skill consumption-layer unit tests** (operator's substitute for live smoke test). Tests against a fixed ledger CSV slice verify column ordering, type handling on edge cases, and bucket rollups. Catches schema drift without requiring live invocation. Real Phase 2 input.

---

## 8. Carry-forwards

Documented, no action this closeout:

1. **File-order ISO-dash chronology** — known under locked naming convention, not a bug.
2. **Defensive-guard test coupling for `sell_cycle_id`** — sound test, fragility note. Documented in v1.1 amendment 8.
3. **Cache temporal alignment** (audit §9) — `median_at_trade` reflects today's cache snapshot, not the snapshot when the trade occurred. Future capital-velocity-analyzer concern.
4. **Dead `apply_premium_adjustment` cleanup** (audit §10) — separate cleanup track.
5. **Multi-line-item Purchases** — `buy_received_date` uses `line_items[0]`. Documented in v1.1 amendment 10.

---

## 9. Supervisor-side durability work (completed in this session)

All artifacts named in closeout handoff §3.2 produced and ready for operator lock:

1. **`Grailzee_Ledger_Redo_Design_v1_1.md`** — twelve amendments compiled. Read alongside v1; v1.1 wins on conflicts.
2. **`docs/decisions/ADR-0006-real-data-sample-records-rule.md`** — methodology rule for real-data sub-step prompts.
3. **`docs/decisions/ADR-0007-why-this-matters-rule.md`** — business-framing rule for build prompts.
4. **`SUPERVISOR_ROLE.md` v2** — both ADRs encoded into "Code prompt shape" and "Failure modes." Pre-emit audit added. Methodology rules section added.
5. **`Grailzee_ShapeK_Resume_2026-04-28.md` §7 update** — Phase 1 status replaced with closeout content. Sequencing-check question retained for future Shape K supervisor seats.

ADR-0006 and ADR-0007 land in `docs/decisions/` as part of the durability commit. v1.1 and ShapeK §7 update land in project knowledge / Drive per existing convention. SUPERVISOR_ROLE.md v2 replaces v1 in the operating contract location.

---

## 10. Phase 1 status

**Shipped.** Code merged. Production ledger canonical. Customer-facing failure resolved. Methodology gap closed in the same closeout via post-mortem §5 → ADRs → SUPERVISOR_ROLE v2.

Next: operator-driven decision on next-steps design session opening. The session's read-first list should include the post-mortem, both ADRs, SUPERVISOR_ROLE v2, design v1 + v1.1, and this closeout.

---

*End of Phase 1 closeout record.*
