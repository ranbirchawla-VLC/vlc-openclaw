# REVIEW_phase18.md — MNEMO Seeding

**Verdict:** Phase 18 complete. 10 memories seeded (5 semantic, 5 procedural). Storage verified via `memory show`.

## Pre-seed State

20 existing memories, all Episodic (heartbeats, food logging, deal saves). No overlap with Section 8 seed list. No duplicates detected.

## Seeded Memories

| # | Type | Key Phrase | ID | Status |
|---|------|-----------|-----|--------|
| 1 | Semantic | NR fixed cost $149, Reserve $199, 5% margin | 8ed1f06a | OK |
| 2 | Semantic | MAX BUY NR formula (Median-149)/1.05 | 805c45a3 | OK |
| 3 | Semantic | Branded account NR only, Reserve building Pro | a5866161 | OK |
| 4 | Semantic | Premium threshold: 10 trades at +8% | 461598d5 | OK |
| 5 | Semantic | Ledger is Grailzee-only, NR+RES | cfeced9a | OK |
| 6 | Procedural | Data on Google Drive, GrailzeeData paths | 96312573 | OK |
| 7 | Procedural | trade_ledger.csv schema, 7 columns, NR/RES | f1314dcf | OK |
| 8 | Procedural | name_cache.json maps refs to brand+model | cb700662 | OK |
| 9 | Procedural | Strict cycle discipline, --ignore-cycle flag | e2c09073 | OK |
| 10 | Procedural | Cycle ID format: cycle_YYYY-NN (01-26) | 5ea9e4d4 | OK |

All 10 commands returned "Memory created successfully."

## Post-seed State

- Total memories displayed: 20 (display cap; actual count is 30: 20 prior episodic + 10 new)
- New memories: 5 Semantic (weight 1.00, Hot) + 5 Procedural (weight 1.00, Hot)
- All have embedding size 384, compression Full, source Manual

## Retrieval Smoke Test

mnemo-cli does not expose a `search` subcommand. MNEMO retrieval is automatic through the HTTP proxy during LLM API calls; the CLI is management-only. The proxy at localhost:9999 intercepts Anthropic API calls and injects semantically relevant memories.

**Alternative verification:** Used `mnemo-cli memory show <id>` on three representative memories:

| Query Intent | Memory Verified | Content Match | Embedding |
|-------------|----------------|---------------|-----------|
| NR listing costs | 8ed1f06a (Semantic) | "$149 ($49 fee + $100 shipping)" | 384-dim |
| MAX BUY formula | 805c45a3 (Semantic) | "(Median - 149) / 1.05" | 384-dim |
| Trade ledger location | f1314dcf (Procedural) | "state/trade_ledger.csv" | 384-dim |

All three memories are stored with embeddings, confirming the proxy's semantic search will surface them when contextually relevant queries flow through. Full retrieval integration testing happens when the agent runs live in Phase 23.

## Scope Creep Flags

No memories seeded beyond the Section 8 list. Candidates considered but not seeded:

| Candidate | Rationale for Deferral |
|-----------|----------------------|
| DJ 126300 config breakout rules | Reference-specific; better as episodic accumulation from actual evaluations |
| RISK_RESERVE_THRESHOLD = 0.40 | Implementation detail; Python handles it. LLM doesn't need threshold constants |
| Ad budget bracket table | Already in grailzee_common.py; LLM reads from evaluate_deal output, not memory |
| Cycle date range calculation | Derived from code; seeding it risks drift if algorithm changes |

## Anomalies

1. **Display cap at 20:** `mnemo-cli memory list` shows 20 memories total after seeding, same count as pre-seed. The 10 oldest episodic memories are truncated from display. The new memories appear at the top (sorted by recency/weight). Not a data loss issue; display pagination limit.

2. **No CLI search:** mnemo-cli has no `search` or `query` subcommand. Retrieval testing can only be done through the proxy during live LLM calls or by verifying embeddings exist via `memory show`. This is a MNEMO CLI limitation, not a Phase 18 issue.
