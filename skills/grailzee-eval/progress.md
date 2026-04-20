# progress.md — Grailzee Eval v2 build

**Purpose:** Session-restart doc. Read this first in a fresh session to pick up where the last one ended.

---

## Status at a glance

- **Branch:** `feature/grailzee-eval-v2`
- **Head:** `ae792ef [known-issues] log sourcing_brief path mismatch (Issue 3)`
- **Ahead of `origin/feature/grailzee-eval-v2`:** 6 commits; push blocked (see Known Issue below re: 448 MB blob in ancestor `35d6c53`). Last successful push was `baa90d5` earlier this session.
- **Tests:** 698 passing from repo root (`python3 -m pytest`). Skill-only: 542 passing. Cowork: 156 passing.
- **Phase complete:** Phase 24b
- **Session 5 (tonight, 2026-04-19):** Mac Studio end-to-end dry-run in progress; several first-run gaps surfaced and logged.
- **Phase next:** finish Phase 25 (first live cycle_planning round-trip) after push is unblocked and operator loop validates.

---

## Session 5 — Mac Studio dry-run, what happened tonight

### Cleanup

- Stale v1 snapshot `skills/grailzee-eval.zip` removed and committed as `baa90d5` (pushed). Git history preserves original at `23979ea`.
- Phase 0 report archived to `~/vardalux-archive/GRAILZEE_V2_PHASE0_REPORT_2026-04-16.md`; `skills/grailzee-eval-v2/` fully removed.
- GTD runtime jsonl files (`gtd-workspace/storage/gtd-agent/users/8712103657/*.jsonl`) set to `skip-worktree` so live GTD state never shows up in `git status`.

### Plugin staging for manual install

Both plugins staged at `~/Desktop/vardalux-plugins/`:

- `grailzee-cowork/` (21 files, 248K) + `grailzee-cowork-v0.1.0.zip` (63K). `claude plugin validate` passes.
- `grailzee-strategy/` (11 files, 84K) + `grailzee-strategy-v0.1.0.zip` (29K). Dev-side artifacts stripped (`TESTING.md`, `REVIEW_phase24b_strategy.md`, `tools/check_schema_mirror.py`); canonical source untouched.

### MNEMO seeding

MNEMO proxy healthy at `127.0.0.1:9999`. Twelve memories added: 5 semantic (fee/margin model, branded-NR scope, presentation premium threshold, ledger scope, MAX BUY formulas), 7 procedural (folder layout, ledger CSV schema, name_cache, cycle id format, tactical-vs-strategy separation, analyzer thresholds ownership, model-tier per surface, strategy session workflow). `mnemo-cli memory search` is not a subcommand; retrievability was not verified via CLI.

### OpenClaw integration state (read-only discovery)

- Agent `grailzee` registered in `~/.openclaw/openclaw.json` against `skills/grailzee-eval/`. Telegram route `channel: telegram + accountId: grailzee` → `agentId: grailzee`. Name-gate enforced in SKILL.md (regex `\bGrailzee\b`, case-insensitive), not in OpenClaw config.
- Model tier: `claude-sonnet-4-6` across all three layers (defaults, agent list, agent-dir models.json). **Gap:** `model_tier_decisions.md` and seeded MNEMO memory both say "Sonnet 4.5"; actual config is 4.6. Either doc+memory are stale or config drifted; reconcile before merge.
- MNEMO wired as provider; `agents.defaults.memorySearch.enabled=false` (auto-injection is proxy-side only, per design).
- No new inbound Telegram activity since Apr 12.

### First-run bundle build gaps (filed as Known Issues)

Discovered during dry-run. All logged in `grailzee-cowork/KNOWN_ISSUES.md`:

- **Issue 1 (Medium-High):** OUTBOUND bundle treats all strategy state files as required via `_read_required()`. On first cycle_planning none of `cycle_focus.json`, `monthly_goals.json`, `quarterly_allocation.json` exist. Workaround: placeholder files. Proper fix: builder should treat these as optional in `cycle_planning` mode.
- **Issue 2 (High, MUST fix before merge):** `is_cycle_focus_current()` always returns False after first INBOUND write. Strategy schema `decisions.cycle_focus` has no `cycle_id` field (cycle_id lives at strategy_output top level); INBOUND's `_emit()` writes the block verbatim; agent reads the file and finds no cycle_id match. Fixture divergence hid this: bundle-side `_default_cycle_focus` has cycle_id, strategy-output `make_strategy_cycle_focus` does not. Fix: INBOUND should inject cycle_id from strategy_output top level before writing.
- **Issue 3 (Medium):** `sourcing_brief` path mismatch. Analyzer writes `state/sourcing_brief.json`; bundle builder reads `output/briefs/sourcing_brief_<cycle_id>.json`. Nothing bridges the two. Fix direction: analyzer's `report_pipeline` should publish to `output/briefs/` as its final step (option a, matches architectural split).

### Placeholders written to live GrailzeeData

To unblock Ranbir's next bundle build attempt (on Cowork side):

- `state/cycle_focus.json` (703 bytes; `placeholder: true`, cycle_id `cycle_2026-07`).
- `state/monthly_goals.json` (355 bytes; month `2026-04`).
- `state/quarterly_allocation.json` (310 bytes; quarter `2026-Q2`).
- `output/briefs/sourcing_brief_cycle_2026-07.json` (615,578 bytes; copied from `state/sourcing_brief.json`). Directory `output/briefs/` created (did not exist).

Threshold config files (`signal_thresholds`, `scoring_thresholds`, `momentum_thresholds`, `window_config`, `premium_config`, `margin_config`) are NOT required by the bundle builder; not placeholder'd.

### Unresolved anomaly

`state/sourcing_brief.json` was rewritten today at 15:01 (`schema_version: 2`, 392 targets, matching mtime to the second). Tests verified hermetic (`unittest.mock.patch` on `BRIEF_PATH`, heavy `tmp_path` use, no `CloudStorage` refs in test tree); no cron, launchctl, or LaunchAgents entry. Paths in `grailzee_common.py` are hardcoded with no env-var override. Most likely explanation: manual invocation of `build_brief.py` against `GRAILZEE_ROOT` from a terminal outside this session. Not acted on.

### Unpushed branch state

Six commits ahead of origin:

```
ae792ef [known-issues] log sourcing_brief path mismatch (Issue 3)
536ba4b [known-issues] generalize Issue 1 to all strategy state files + flag threshold-config separate class
77d908a [known-issues] log cycle_focus chicken-and-egg + cycle_id injection gap
4a0bd0d Intake: haiku default, sonnet escalation for ambiguous invoices
0489f33 Ignore fastembed cache, remove from tracking
35d6c53 GTD agent: haiku default, sonnet for /review only   ← 448 MB blob
```

`35d6c53` accidentally committed the full `fastembed_cache` model tree, including a 448 MB binary blob at `.fastembed_cache/models--intfloat--multilingual-e5-small/blobs/ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665`. Follow-up commit `0489f33` ran `git rm --cached` but the blob persists in `35d6c53`'s tree; GitHub pre-receive rejects every push. **Blocker for merge to main.** Fix when ready: `git filter-repo --path .fastembed_cache --invert-paths` or interactive rebase + `git rm --cached` + amend on `35d6c53`. Do not attempt without operator eyes on it.

### Secret hygiene flag

`~/.openclaw/openclaw.json` and `~/.openclaw/agents/grailzee/agent/models.json` store bot tokens + MNEMO apiKey + gateway auth token in plaintext at mode 0600. Protected by disk ACLs; anyone with shell access to this user sees everything. Non-blocking; consider Keychain or `.env` sourcing later.

---

## Shipped (phases 1–24b)

| Phase | What | Key artifact |
|---|---|---|
| 1 | `grailzee_common.py` + scaffolding | `scripts/grailzee_common.py` |
| 2 | Seed `name_cache.json` | `scripts/seed_name_cache.py` |
| 3 | Ledger read + manager | `scripts/read_ledger.py`, `scripts/ledger_manager.py` |
| 4 | Backfill historical trades | `scripts/backfill_ledger.py` |
| 5 | Excel → CSV ingest | `scripts/ingest_report.py` |
| 6 | Reference analyzer | `scripts/analyze_references.py` |
| 7 | Trend/momentum scoring | `scripts/analyze_trends.py` |
| 8 | Emerged/shifted/faded | `scripts/analyze_changes.py` |
| 9 | Breakout detection | `scripts/analyze_breakouts.py` |
| 10 | Watchlist detection | `scripts/analyze_watchlist.py` |
| 11 | Brand rollups | `scripts/analyze_brands.py` |
| 12 | Cycle outcome rollup | `scripts/roll_cycle.py` |
| 13 | Output builders | `scripts/build_spreadsheet.py`, `build_summary.py`, `build_brief.py` |
| 14 | Cache writer v2 | `scripts/write_cache.py` |
| 15 | Orchestrator | `scripts/run_analysis.py` |
| 16 | Deal evaluator v2 | `scripts/evaluate_deal.py` |
| 17 | Targets v2 (later rewritten in Phase 19) | *replaced in Phase 19* |
| 18 | MNEMO seeding | Session 5 (tonight) |
| 19 | Capability files + `query_targets.py` rewrite | `capabilities/*.md`, `scripts/query_targets.py` |
| 19.5 | Pipeline wrapper | `scripts/report_pipeline.py` |
| 20 | Top-level dispatcher | `SKILL.md` |
| 21 | Pre-deletion audit; 3 tests deleted (v1/v2 equivalence harness) | `REVIEW_phase21.md` |
| 22/23 | Migration; v2 renamed into production slot; v1 deleted | commit `1bb8119` |
| 24a | Cowork plugin; OUTBOUND + INBOUND bundle handoff (sibling dir; does not import from this skill at runtime) | `grailzee-cowork/` |
| 24b A | Cowork INBOUND extended to accept `strategy_output.json` alongside `.zip`; hand-rolled validator, 5-sheet XLSX builder, best-effort archive to `output/briefs/`, atomic state commit preserved | `grailzee-cowork/grailzee_bundle/strategy_schema.py`, `build_strategy_xlsx.py`, extended `unpack_bundle.py`; `REVIEW_phase24b_cowork.md` |
| 24b B | Chat strategy skill; four session modes (`cycle_planning`, `monthly_review`, `quarterly_allocation`, `config_tuning`) producing validated `strategy_output.json`; byte-identical schema mirror with cowork, enforced by guard script | `grailzee-strategy/` (sibling dir); `REVIEW_phase24b_strategy.md` |

Batch B1 hygiene session and OTel retrofit shipped between Phase 17 and Phase 19 (see `REVIEW_batchB1.md`, `REVIEW_otel_retrofit.md`).

---

## Remaining (Phase 25)

- **Unblock push.** Rewrite `35d6c53` to drop `.fastembed_cache/` files, force-push the branch. Must be done deliberately with operator present; destructive-ish.
- **Address Issue 2 (cycle_id injection) before merge.** High priority.
- **Decide Issue 1 + Issue 3 fixes (or accept placeholder workaround for now).**
- **Reconcile model tier:** either pin config to Sonnet 4.5 or update `model_tier_decisions.md` + MNEMO memory #11 to reflect the actual 4.6.
- **Complete operator dry-run loop.** Ranbir to retry the bundle build from Cowork with placeholders in place; run a first live `cycle_planning` session; produce a real `strategy_output.json`; apply it back via Cowork INBOUND against real state.
- **Merge `feature/grailzee-eval-v2` → `main`** once the above passes.

---

## Session 3 decisions (D1–D5)

From `DECISIONS_session3_kickoff.md`, binding on Phases 19+:

- **D1** — `report_pipeline.py` wrapper is the single invocation for report processing. Capabilities do not thread state paths.
- **D2** — Ledger rejection = abort with `"re-send with corrections"` (no corrective round-trip in SKILL).
- **D3** — No cycle gate on targets or deal. Deal Branch B (`status: "not_found"`) = market context only, no forced recommendation.
- **D4** — `query_targets.py` emits a two-section Strong/Normal block, MAX BUY (NR) DESC. One-tier-empty preserves header; both-tiers-empty collapses to a single fallback line.
- **D5** — Config-driven analyzer thresholds. **Deferred to a later phase.** Not active yet.

---

## Skill inventory

**Root:**
- `SKILL.md` (top-level dispatcher, name-gate + 5 paths)
- `AGENTS.md`, `SOUL.md`, `USER.md`, `IDENTITY.md`, `TOOLS.md`, `HEARTBEAT.md` (scaffolding)
- `Grailzee_Eval_v2_Implementation.md` (THE SPEC; §14 has the phase table)
- `DECISIONS_session3_kickoff.md` (D1–D5)
- REVIEW_phase{1–21}.md + REVIEW_batchB1.md + REVIEW_otel_retrofit.md. Phase 22/23 folded into commit message; Phase 24a review at `grailzee-cowork/REVIEW_phase24a.md`; Phase 24b reviews at `grailzee-cowork/REVIEW_phase24b_cowork.md` and `grailzee-strategy/REVIEW_phase24b_strategy.md`.

**`capabilities/` (4 files, all aligned with D1–D4):**
- `ledger.md` — trade logging + performance queries
- `deal.md` — single-watch deal evaluation (Branches A and B per D3)
- `report.md` — report pipeline wrapper invocation (D1)
- `targets.md` — Strong/Normal hunting list (D4)

**`scripts/` (23 files):** entry points relevant to SKILL.md: `report_pipeline.py`, `evaluate_deal.py`, `query_targets.py`, `ledger_manager.py`, `read_ledger.py`.

**`tests/` (21 test files):** 542 passing.

**Sibling plugins:**
- `grailzee-cowork/` — Claude Code plugin. OUTBOUND `.zip` + INBOUND dual-input (`.zip` or `strategy_output.json`). 156 tests. Does not import from `skills/grailzee-eval/` at runtime. Now carries `KNOWN_ISSUES.md`.
- `grailzee-strategy/` — Chat-side skill (not a Claude Code plugin). Four session modes, one output contract. Schema byte-identical to cowork's; `tools/check_schema_mirror.py` guards the invariant.

---

## Open scope-creep flags (deferred; do not ship in current phases)

From `REVIEW_phase20.md`:
- **Flag A — Path 2a state-carrying.** Priceless deal query is stateless; operator re-sends brand + ref + price on the next turn.
- **Flag B — Sell-side queries.** "What can I sell X for?" would be a new capability.

From `DECISIONS_session3_kickoff.md`:
- **D5 (config-driven thresholds)** — deferred. Analyzer thresholds are still hardcoded.

From Phase 22/23:
- **analysis_cache_sample.json fixture key-shape hygiene** — deferred; noted during migration, not blocking.

From Session 5:
- **Slot-filling for ambiguous ledger-vs-deal inputs.** `Grailzee, closed the Tudor 79830RB at $3200` has one dollar + trade verb; routes to deal eval under current Path 1 rule ("≥2 dollar amounts"), but operator intent is trade log with missing buy price.
- **Ledger confirmation synonym set is small.** Only `yes`/`y`/`confirm`/`proceed` accept the write. Wispr Flow dictation commonly produces `sure`, `go ahead`, `do it`, `yep` — currently treated as abort.
- **Report Step 2 has no "no xlsx found" handler.** If `reports/*.xlsx` is empty the pipeline call fails opaquely.
- **Unnamed-ref resolution rubric is loose.** Report Step 5 relies on LLM judgement for "confident match"; consider explicit signal (brand + reference string in top-3 search results).
- **Secret hygiene.** See Session 5 flag above.

---

## How to restart

1. `cd /Users/ranbirchawla/.openclaw/workspace/skills/grailzee-eval`
2. `git status` — expect clean working tree (GTD jsonl files are skip-worktree and do not surface)
3. `git log --oneline -10` — head should be `ae792ef` locally; origin still at `baa90d5`
4. `python3 -m pytest tests/ -q` — confirm 542 passing (skill-only)
5. From repo root `/Users/ranbirchawla/.openclaw/workspace`: `python3 -m pytest` — confirm 698 passing
6. `python3 /Users/ranbirchawla/.openclaw/workspace/grailzee-strategy/tools/check_schema_mirror.py` — confirm schema byte-identity
7. Read in order:
   - `progress.md` (this file)
   - `../../grailzee-cowork/KNOWN_ISSUES.md` (three Session 5 issues)
   - `DECISIONS_session3_kickoff.md` (D1–D5)
   - `../../grailzee-cowork/REVIEW_phase24b_cowork.md`
   - `../../grailzee-strategy/REVIEW_phase24b_strategy.md`
   - `Grailzee_Eval_v2_Implementation.md` §14–15
8. Next concrete action: unblock the push (history rewrite on `35d6c53`); then resume Phase 25.

---

## Operating pattern (applies to all phases)

- User plans and gates. Claude executes.
- Hard stop at phase boundaries. No drifting into the next phase without a new prompt.
- Opening moves → state summary → **STOP** → plan → **STOP** → execute.
- Every completed module gets a code-review pass before commit.
- One phase = one (or at most two) commits, with a `REVIEW_phase{N}.md` capturing the work. Phase 24 reviews live with their respective plugins as siblings.
