# Grailzee Architecture Lock — 2026-04-26

**Status:** Locked at architectural session close, 2026-04-26.
**Supersedes:** Phase 2c Work Plan v1.1 wave decomposition. Wave numbering retired; rational sequence governs going forward.
**Predecessor read:** All decisions in this artifact were derived from operator-stated business outcomes. Where prior code, tests, or scope decisions conflict, this artifact is authoritative.

---

## Business outcome

Hit a known monthly margin-return target on Grailzee-deployed capital. Operating math: per-deal margin floor 5%, velocity ~2.4 turns per month at 1.5 cycles per month, capital example $60k, monthly target ~12% return ≈ $7,200. Floor is non-negotiable; velocity is the lever; mix produces the monthly outcome.

The agent stack exists to serve this outcome. Every API surface justifies against it.

## Vardalux premium

Vardalux sells at ~10-15% above other Grailzee sellers on the same reference, attributed to photos and presentation. Treated as a scalar applied uniformly for now. Per-reference premium tracking with recency weighting is V3 work, not in current scope.

---

## Operator-facing surfaces

Three surfaces. Everything else is implementation behind these boundaries.

**Surface 1 — Telegram bot (grailzee-eval agent).** Operator pastes a deal in Telegram. Bot answers yes/no with math visible. If no, inline button offers market comp search. Operator triggers report ingest from this surface.

**Surface 2 — Cowork plugin (Code).** Operator builds the biweekly bundle. Cowork packages state into outbound zip. Operator hands strategy output back; cowork validates and writes state. Implementation hides wiring; operator says "build the bundle" or hands over the json, cowork does the rest.

**Surface 3 — Chat strategy skill (claude.ai).** Operator uploads bundle, runs the strategy session, iterates on hunt list and judgment, produces strategy_output.json. Reads the wide CSV, ledger, prior cycle outcome.

---

## Five outcomes mapped to surfaces

| Outcome | What operator does | Which surface |
|---|---|---|
| **O1** Hit monthly margin-return target | Sets target, deploys capital, reviews results biweekly | Umbrella; served by O2-O5 |
| **O2** Decide if a specific deal is a buy | Pastes deal in Telegram | Surface 1 |
| **O3** Plan the cycle | Runs biweekly flow: report → bundle → strategy → INBOUND | Surfaces 1, 2, 3 |
| **O4** Log auction wins for strategy | Drops sale json in sale folder | Surface 2 (bundle ingest) |
| **O5** Keep data live | Triggers report ingest | Surface 1 |

---

## Biweekly flow

1. Email from Grailzee. Operator drops xlsx in Drive folder.
2. Telegram: "process new report." Bot runs analyzer pipeline. Cache + premium scalar updated.
3. Cowork: "build the bundle." Wide CSV plus state plus sale folder jsons packaged.
4. Operator uploads zip to chat. Strategy session runs. Wide CSV reviewed against ledger and prior outcome. Operator layers sourceability and judgment. Strategy emits strategy_output.json.
5. Cowork validates strategy_output, writes state files atomically.
6. Bot reads state. Two weeks of deal evals against the cycle plan.

Friction is acceptable because the flow runs every two weeks. Value is correct math at every step plus a focused list the bot operates against in-cycle.

---

## What got cut

| Cut | Reason |
|---|---|
| `ledger.md` capability and trade-logging Path 1 | Auction wins flow via sale folder json drops, not Telegram entry |
| `targets.md` capability and Path 5 | Cycle plan is the source of truth; raw Strong/Normal cache list bypasses strategy session work |
| Performance query Path 4 (`how are we doing`) | ERP owns inter-cycle tracking; review at biweekly strategy session |
| "Maybe" decision state | Finance, not emotions; yes/no only |
| Per-reference premium rollup | Premium is a scalar today; per-reference tracking is V3 |
| Hunt-list vs commit-list distinction in state | Operator carries the distinction in their head; persistence layer does not need both |
| `build_summary.py`, `build_brief.py`, `build_spreadsheet.py`, `analyze_brands.py` | Strategy session reads wide CSV directly and writes its own brief; no operator surface consumes these outputs |
| `analyze_references.py` (as primary scorer) | Replaced by `analyze_buckets.py` per v3 schema |

---

## Locked architectural decisions

1. **Three operator surfaces, no more.** Telegram bot, cowork, chat strategy skill. Any new capability justifies against an operator outcome before it ships.
2. **Python deterministic, LLM translator.** AA §2.7. Per CLAUDE.md voice rules. Every user-facing number, date, structural fact comes from a Python tool result. LLM reads verbatim, never composes.

   *Clarifying clause (added 2026-04-27):* LLM may compose translation prose around verbatim math output under `deal.md` Branch A guardrails. LLM never composes facts; LLM never makes the decision. Branch A guardrails are the sole sanctioned slot for LLM-composed prose; all other surfaces remain pure verbatim.

3. **Wide CSV is the strategy input.** Hundreds of rows, every reference × bucket, all math done. Strategy reads breadth; operator filters by sourceability in conversation.
4. **Schemas are contracts.** Wide CSV column schema and strategy_output json schema are written, validated at producer and consumer boundaries.
5. **Premium scalar applied uniformly.** Single config value. No per-reference variance until V3.
6. **Yes/no only on deal eval.** Math clears or it doesn't. No maybe. Comp-search button on no.
7. **Sale folder json ingest.** Auction wins flow via folder drop, not bot entry. Designed in detail later this week.
8. **No inter-cycle tracking surface in this stack.** ERP owns that. Strategy session is the review surface.

---

*End of architectural lock. Reference for all subsequent supervisor sessions and build prompts.*
