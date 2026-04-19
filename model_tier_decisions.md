# Model Tier Decisions — Grailzee System

**Status:** Locked. Revisit only on measurable degradation or architectural change.
**Captured:** April 19, 2026
**Scope:** All three LLM surfaces in the Grailzee system.

---

## The decision

| Surface | Location | Model | Reasoning |
|---|---|---|---|
| grailzee-bundle (Cowork plugin) | `grailzee-cowork/skills/grailzee-bundle/` | **Haiku 4.5** | Dispatcher + JSON relay. Python owns hashing, validation, atomic writes. LLM classifies intent (outbound/inbound/ambiguous) and relays structured output. No synthesis, no judgment. |
| grailzee-eval (OpenClaw agent) | `skills/grailzee-eval/` | **Sonnet 4.5** | Intent dispatch + voice composition + web research for name resolution. Python owns all math, filtering, aggregations, state writes. LLM composes Vardalux-voice responses from pre-structured JSON and resolves 2–5 unknown references per cycle via web search. |
| Chat strategy skill (Phase 24b) | Chat-level skill, separate directory | **Opus 4.7** | Multi-turn strategic partner. Reads bundle, synthesizes past performance against present data, pushes back on weak reasoning, handles four modes (cycle planning, monthly review, quarterly allocation, config tuning), produces structured outputs. Capability question, not cost question. |

---

## Why this works (the underlying architecture)

The model tier pattern is only possible because of the architectural discipline the rest of the system enforces. If that discipline broke, the model tiers would need to climb to compensate.

**The division of labor:**
- **Python does analysis.** Every metric, every filter, every score, every aggregation. Deterministic, auditable, testable.
- **LLM does language, judgment, and research.** Parsing intent, composing voice, resolving unknowns via web search, framing structured data.
- **Memory (MNEMO) handles business context.** Fees, margin formulas, account rules, prior decisions — seeded as semantic memory and injected on every call automatically. Prompt files don't carry this load.

With this in place, a well-written capability file + a well-structured JSON handoff + the right injected memory context is enough for a smaller model to handle what would otherwise look like a bigger task. Inverting any of the three forces a model-tier escalation.

---

## Why each tier is right

### Haiku 4.5 — grailzee-bundle

The skill has two modes (outbound bundle build, inbound bundle unpack) and runs twice per cycle. The LLM:

- Classifies user intent across outbound vs inbound vs ambiguous
- Extracts a zip path from the user message (inbound only)
- Invokes one Python script with known arguments
- Relays JSON output verbatim — no number rewriting
- Surfaces script errors verbatim

The `What the LLM Does NOT Do` section explicitly forbids the hard work (hashing, manifest validation, choosing roles, writing to state). The LLM is a thin dispatcher over well-tested Python.

Haiku handles this reliably when the capability file carries explicit trigger phrase lists — which the plan does.

**If Haiku misfires on intent in practice:** add more explicit trigger phrases to SKILL.md first. Upgrade to Sonnet only if phrase expansion doesn't resolve it.

### Sonnet 4.5 — grailzee-eval agent

Workload mix on the agent side:

- Intent dispatch across five paths in SKILL.md (simple)
- Capability-file-driven workflows for deal / targets / ledger (simple — read JSON, frame response)
- Web search for name resolution on 2–5 unknown references per report (moderately hard — parse search results, pick official model name, follow naming conventions from `name_cache.json` examples)
- Voice composition across deal responses, target lists, trade confirmations, and biweekly report summaries (moderately hard — voice matters, and the biweekly summary is the longest composition)

Opus would be spending capacity on work that Python and MNEMO already handle. Haiku would be shaky on voice and slightly riskier on name resolution edge cases. Sonnet with well-structured capability files and injected business context hits the right capability/cost balance.

**The biweekly report summary is the thing to watch.** It's the longest single composition the agent produces. If voice degrades (em-dashes appearing, over-formatted bullets, generic "AI-sounding" prose, loss of the poetic/editorial Vardalux tone), the fix is to add voice exemplars to `capabilities/report.md` — not to upgrade the model. Voice discipline rules from the broader Vardalux content work apply:

- No em-dashes
- No bullet points in narrative copy
- Hook in the first line
- Story does the work without over-explaining

These should be explicit in the capability file, not just implicit assumptions.

**If Sonnet starts failing on the agent:** check capability files for voice exemplar coverage first, confirm MNEMO is injecting business context as expected, check that Python is still producing the right JSON shape. Upgrade to Opus only if those check out and voice is still degrading.

### Opus 4.7 — Chat strategy skill

The strategy skill is where "strategic partner" is the actual product. The skill:

- Reads a bundle with multiple state files (analysis cache, ledger, prior cycle focus, prior cycle outcome, monthly/quarterly state)
- Synthesizes past performance against present data
- Conducts multi-turn planning with pushback on weak reasoning
- Handles four modes: cycle planning, monthly review, quarterly allocation, config tuning
- Produces structured outputs (`cycle_focus.json`, `cycle_brief.md`, optionally updated config files)

The whole reason the strategy workflow is split from the Telegram agent is that the conversation needs multi-turn depth and genuine pushback when your capital plan doesn't match your volume target, or when you're rationalizing an off-cycle pick. That kind of pushback is where model capability shows up most.

Secondary reason for Opus: the conversation is multi-turn with growing context (bundle at start, evolving decision trail, final confirmation). Opus handles long-context reasoning more reliably, which matters for "we discussed this three turns ago, does the capital plan still hold?"

Strategy runs once every two weeks. Total Opus spend per cycle is one session. Cost delta against Sonnet is rounding error compared to the value of getting the strategy right.

---

## Cost shape reinforces capability shape

Frequency of invocation inverts with cost per call:

- Haiku (cheap): runs twice per cycle
- Sonnet (mid): runs many times per cycle (every deal query, target query, trade log, report processing)
- Opus (expensive): runs once per cycle

Total Opus spend per cycle is bounded. Sonnet does the bulk and sits at the right capability/cost point. Haiku's cost contribution is a rounding error. If the pattern inverted — Opus on the bundle skill, Haiku on strategy — the architecture would be wrong, not just the cost.

---

## Model tier as architectural diagnostic

When one of these three starts misfiring, the first question is NOT "do we need a bigger model."

The first question is: **what is the LLM doing that it shouldn't be?**

- If Haiku can't handle the bundle skill, the capability file is probably asking the LLM to do Python work.
- If Sonnet can't handle the agent, either the capability files lack voice exemplars, MNEMO isn't injecting context properly, or a script is returning unstructured output the LLM has to re-derive.
- If Opus can't handle strategy, the bundle is probably missing state the strategist needs to reason with, or the skill is trying to compute things that should be pre-computed.

Upgrading the model without diagnosing the cause just hides the architectural drift. The drift still compounds and eventually shows up somewhere else.

---

## What would force reconsideration

Revisit these tier assignments if:

1. **Voice degrades measurably on agent output** and adding voice exemplars to capability files doesn't fix it. Then consider Opus for the agent.
2. **Haiku misclassifies bundle intent** after trigger phrase expansion. Then consider Sonnet for the bundle skill.
3. **New capability added to any surface that requires different cognitive work** than what's currently there. Re-evaluate that surface's tier independently.
4. **Anthropic ships a new model tier** that changes the capability/cost curve meaningfully.

Do NOT revisit on:

- A single bad response (noise, not signal)
- Cost anxiety (Opus on strategy is a once-per-cycle cost, not a recurring expense)
- General "maybe we should upgrade" instinct without a specific failure mode

---

## Installation note

When setting up each surface, the model selection mechanism differs:

- **OpenClaw agent:** model selection is configured in the agent's runtime environment (MNEMO config, OpenClaw settings, or equivalent — confirm at install time).
- **Cowork plugin:** Claude Code's plugin model selection mechanism. If per-plugin selection isn't exposed at install time, the plugin inherits the global Claude Code setting. Flag at install; the grailzee-bundle skill is fine on Haiku, but a global Claude Code Sonnet/Opus setting will just mean paying slightly more for a simple workload — not a correctness issue.
- **Chat strategy skill:** Chat-level model selection. Confirm Opus is the active model when running a strategy session.

---

## Reference to broader architecture patterns

This doc is specific to Grailzee. The portable patterns that make these tier choices possible are documented separately in `architecture_patterns.md` — specifically:

- Python / LLM / memory separation of concerns
- Capability file template with explicit "does NOT do" section
- JSON cache as the Python → LLM handoff interface
- Wrapper scripts over LLM-driven shell chaining
- Token economics of the capability dispatch pattern

If a future project wants to reuse the tier logic, those patterns are the prerequisite.
