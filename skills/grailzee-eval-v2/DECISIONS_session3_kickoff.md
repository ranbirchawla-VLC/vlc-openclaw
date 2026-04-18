# DECISIONS — Session 3 Kickoff

**Captured:** April 18, 2026
**Source:** Chat-side supervision session preceding Claude Code Session 3
**Status:** Locked. No re-litigation without new information.

---

## D1 — Report orchestration: build report_pipeline.py wrapper

**Decision:** Build a thin Python wrapper that handles ingest + CSV glob + analyze as one orchestrated call. `capabilities/report.md` invokes the wrapper, not raw shell steps.

**Phase assignment:** Phase 19.5 — executes before Phase 19 capability files are written. Estimated 30–45 minutes of code + tests + code-reviewer + REVIEW_phase19_5.md.

**Rationale:** Batch B1 (commits 9a84d86, 06ea683) hardened three contracts in ingest_report.py — stderr warning on mtime fallback, raise instead of silent datetime.now(), required --output-dir with no default. Inlining these steps in the LLM layer puts the agent in charge of honoring those contracts across three shell invocations under Telegram latency — the exact error class B1 was built against. File globbing in the LLM layer is the silent-wrong-result pattern specifically. Wrapper also closes the orchestrator observability gap: the 12 OTel spans added in Phase 17 live inside run_analysis() and leave ingest uninstrumented; wrapper is the natural home for an ingest + glob span.

**Supersedes:** Nothing. Net-new.

---

## D2 — Ledger confirmation rejection: abort with resend

**Decision:** In capabilities/ledger.md sub-mode A (trade logging), when the operator replies "no" to the parsed confirmation, the agent aborts and replies "please re-send with corrections." No in-chat field-level editing UI.

**Rationale:** "No" signals the parse was wrong but carries no information on which field. Asking "which field?" builds stateful editing across turns inside a Telegram group chat, with field-name contracts the operator must learn and partial state to invalidate on abandonment. Stateless retype is idempotent, one turn, matches Telegram's interaction model.

**Revisit trigger:** If real-usage retype rate exceeds ~1 in 5 trades, reconsider. Until then, abort path holds.

**Supersedes:** Nothing. Implementation plan left this unspecified.

---

## D3 — Cycle discipline on targets: REMOVED

**Decision:** The `targets` capability does not gate on cycle focus. No `--ignore-cycle` flag. No allowlist. No strategic framing as blocker. Q1 (hunt list) is answered from current analyzer math regardless of whether a strategy session has run.

**Rationale:** Two fundamental operator questions, both tactical, both always-answered:

**Q1 — "What should I hunt on Grailzee right now?"**
Answer: deterministic Python lookup against the latest analyzer output. Telegram-terse. No LLM judgment, no strategic framing, no gate. The operator already knows the business; they need the list because memory fails mid-sourcing and opening Chat is friction.

**Q2 — "I found a deal. Does Grailzee work?"**
Answer: if Grailzee data exists, LLM reads the data and gives a reasoned recommendation grounded in business context (fees, margin, Profit for Acquisition model). If no Grailzee data, LLM delivers web-sourced market context only — NO forced recommendation. The absence of Grailzee data is itself the answer.

Strategy is a separate Chat-level product. It produces cycle briefs that shape operator thinking. It does not gate tactical answers in Telegram.

**Supersedes (in implementation plan):**

- Section 4 "Cycle discipline enforcement" — the block-targets-until-strategy-runs behavior is out
- Section 10.3 capabilities/targets.md — gate message, --ignore-cycle flag, cycle_reason field in output all removed. Rewritten against two-section Strong/Normal lookup per D4.
- Section 10.2 capabilities/deal.md not-found branch — plan had LLM compute recommendation from web comps. Now: market context only.

`cycle_focus.json` as a state file may still exist if the strategy skill writes it for archival purposes (Phase 24). No Phase 19 capability reads it.

---

## D4 — Q1 hunt list: two-section Strong/Normal, MAX BUY desc

**Decision:** `query_targets.py` returns two sections in one Telegram message:

```
STRONG
{model_name} — {reference} — ${max_buy_nr}
...sorted by max_buy_nr descending

NORMAL
{model_name} — {reference} — ${max_buy_nr}
...sorted by max_buy_nr descending
```

No Caution tier. No Reserve tier. No momentum labels, signal annotations, ledger stats, or prose. Reserve MAX BUY not shown — tactical sourcing uses NR pricing. Full detail for all tiers lives in the Excel output on disk.

No code cap on list length. Realistic outcome is 10–12 references total across both sections; Telegram's 4000-char soft limit is not a concern at that scale.

**Filter:**

- Strong: `signal == "Strong"`, sorted by `max_buy_nr` DESC
- Normal: `signal == "Normal"`, sorted by `max_buy_nr` DESC

Tier assignment is made inside `analyze_references.py` using thresholds read from config files (see D5). `query_targets.py` is pure lookup — it reads `analysis_cache.json` and formats output.

**Supersedes (in implementation plan):**

- Section 10.3 output format — rewritten against this spec
- Phase 17 query_targets.py scope — rewritten against this spec

---

## D5 — Tunable analyzer parameters: config files, not code

**Decision:** All judgment-call thresholds in the analyzer move out of code and into JSON config files in `GrailzeeData/state/`. `analyze_references.py` and peer modules read the configs at run time. Retunes happen via file edits — ultimately orchestrated by the Phase 24 strategy skill, via direct JSON edit in the interim.

**Config files (one per concern):**

| File | Controls |
|---|---|
| `GrailzeeData/state/signal_thresholds.json` | Strong/Normal/Reserve/Caution tier cutoffs |
| `GrailzeeData/state/scoring_thresholds.json` | Minimum sales floor, quality condition set |
| `GrailzeeData/state/momentum_thresholds.json` | Momentum score cutoffs, breakout signals, watch list criteria |
| `GrailzeeData/state/window_config.json` | Pricing window size, trend window size |
| `GrailzeeData/state/premium_config.json` | Presentation premium threshold and formula parameters |
| `GrailzeeData/state/margin_config.json` | Target margin, account fee structure |

**Each config file carries metadata:**

```json
{
  "version": 1,
  "updated_at": "ISO-8601 timestamp",
  "updated_by": "strategy_session | manual | seed",
  "notes": "reason for this version",
  "...config-specific fields..."
}
```

**Design boundary — CRITICAL:**

Configs contain numbers, strings, and booleans only. Any logic lives in Python. If a future change requires computing a new metric to feed tier rules, that's a code change in analyze_references.py, not a config change. The config layer tunes thresholds against existing metrics — it does not add new metrics. This boundary prevents the config layer from rotting into a scripting surface.

**Safety rails in loader:**

- Schema validation on read (version, required fields, parseable values)
- Missing or malformed file → fall back to safe defaults baked into Python + emit stderr warning. Never hard-fail the analyzer on config issues.
- Unknown future version → warn, use defaults, continue.

**Phase impact:**

**Phase 2 (seeding):** add sibling seed step for all six config files. Values match whatever the current v1 `analyze_report.py` uses, so day-one v2 behavior matches v1 exactly. No silent behavior drift in cutover.

**Phase 6 (analyze_references.py extraction):** logic extraction from v1 parameterizes against config reads instead of hardcoded constants. `grailzee_common.py` gains `load_signal_thresholds()` and peer loaders, mirroring `load_name_cache()` pattern.

**Phase 18 (MNEMO seeding):** add one memory noting the config-layer pattern exists and the strategy skill owns retunes.

**Phase 24 (strategy skill):** gains a fourth mode — config tuning — alongside cycle planning, monthly review, and quarterly allocation. Skill's SKILL.md carries the authoritative registry of tunable files, their schemas, and their write contracts. Users do not need to remember file paths; the skill does. Skill writes with backup rotation (mirror of write_cache.py Flag #6), requires a notes field on every retune, shows diff before write.

**Supersedes (in implementation plan):**

- Phase 6 analyze_references.py scope — threshold values now config-driven
- Phase 11 MNEMO seeding — one memory added
- Section 11 strategy skill scope — fourth mode added

---

## Summary of implementation plan sections superseded by this chat

- Section 4 "Cycle discipline enforcement" (D3)
- Section 10.2 deal.md not-found branch recommendation path (D3)
- Section 10.3 targets.md cycle-gated behavior and output format (D3, D4)
- Section 11 strategy skill scope — fourth mode added (D5)
- Phase 6 analyze_references.py hardcoded thresholds (D5)
- Phase 17 query_targets.py scope (D3, D4)

Implementation plan sections NOT changed by this chat:

- All architectural decisions (Section 2 core design principles)
- All Python decomposition structure (Section 12)
- All migration protocol (Section 15)
- All other Phase specifications

---

**End of decisions. Any Claude Code work in this repo from this point forward honors these decisions as locked until new information forces reconsideration.**