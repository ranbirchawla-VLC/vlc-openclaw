# OpenClaw Latency Reduction Playbook
**Stack:** OpenClaw Gateway · Anthropic API · MNEMO · Telegram Bots · Mac Studio  
**Status Tracking:** Check off each step as implemented. Re-evaluate with Honeycomb traces after each phase.  
**Last Updated:** May 2026

---

## ✅ Step 1 — Telegram streamMode + IPv4 First
*Status: DONE*

---

## Step 2 — Session Hygiene & Context Window Cap
**Est. Gain:** 30–50% response time reduction  
**Effort:** ~15 minutes  
**Background:**  
OpenClaw retains full conversation history, tool outputs, and error logs in the active context window by default. Every byte gets re-sent on every API call. A session that starts at ~5K tokens can balloon past 150K tokens by the tenth exchange, pushing response times past 20 seconds. This is the most common cause of gradual, progressive slowdowns on OpenClaw — bots feel fast on day one and sluggish within a week.

**Actions:**
- [ ] In your OpenClaw config, reduce `maxContextTokens` from the default 400K to **100K** — the vast majority of tasks never need more
- [ ] Enforce session-per-task discipline: issue `/new` or `openclaw reset session` after each independent task completes (watch lookups, invoice processing runs, etc.)
- [ ] Use `/compact` proactively before sessions feel sluggish — don't wait for auto-compaction to trigger
- [ ] Add a session reset to the end of each agent's task completion handler so sessions are fresh on next invocation

**Verification with Honeycomb:**  
After implementing, look at the `input_tokens` attribute on your LLM call spans. Before: you'll see climbing token counts across a session. After: they should reset to baseline at task boundaries.

---

## Step 3 — Anthropic Prompt Caching on Static Sections
**Est. Gain:** Up to 85% latency reduction on long-prompt calls  
**Effort:** ~30 minutes  
**Background:**  
Anthropic's prompt caching stores the computed KV state of your prompt prefixes server-side, so Claude does not reprocess the same system instructions, agent instructions, or static documents on every request. Anthropic's own benchmarks show a 79% latency reduction for 100K-token document queries (11.5s → 2.4s). Cache reads cost 10% less than standard input tokens; the tradeoff is a 25% higher write cost, which pays off rapidly across repeated calls.

**Critical nuance:** Cache ONLY stable content. Caching dynamic content (tool results, conversation turns) can paradoxically *increase* latency because it triggers cache writes for content that won't be reused. The winning pattern is system-prompt-only caching with dynamic content appended at the tail.

**Actions:**
- [ ] Add `cache_control: {"type": "ephemeral"}` to your static system prompt block(s) in your Anthropic API calls
- [ ] Add `cache_control` to your static agent instruction blocks (SOUL.md content, workspace context)
- [ ] Ensure dynamic content (user messages, tool outputs, MNEMO-retrieved context) is appended **after** all cached static blocks
- [ ] If using MNEMO to inject retrieved context: structure prompts so MNEMO-served static knowledge lands before the dynamic user message, not after it
- [ ] Do NOT cache tool result blocks or multi-turn conversation history

**Example prompt structure (correct ordering):**
```
[SYSTEM PROMPT]                         ← cache_control: ephemeral
[AGENT INSTRUCTIONS / SOUL.md]          ← cache_control: ephemeral
[STATIC KNOWLEDGE / MNEMO retrieved]    ← cache_control: ephemeral
[CONVERSATION HISTORY]                  ← no cache
[CURRENT USER MESSAGE]                  ← no cache
[TOOL RESULTS]                          ← no cache
```

**Verification with Honeycomb:**  
Look for `cache_read_input_tokens` in your API response metadata. Target >80% cache hit rate on repeated agent calls. Low hit rate means your cached blocks are changing between calls — audit what's being marked as static.

---

## Step 4 — Model Tiering
**Est. Gain:** 50–80% reduction in average response time; 60–80% cost reduction  
**Effort:** ~10 minutes config change  
**Background:**  
Using Opus-class models for every agent task is the fastest way to accumulate unnecessary latency. OpenClaw supports multi-model routing — the key is assigning the right model to the right task type. Most operational tasks (classification, routing, lookups, formatting) don't need Opus. Reserve it for the ~10% of tasks that genuinely require deep, multi-step reasoning.

**Model Reference:**

| Model | Typical Latency | Best For |
|---|---|---|
| Claude Haiku 4.5 | ~1–2s | Routing decisions, classification, simple lookups, formatting |
| Claude Sonnet 4.6 | 2–5s | Most daily tasks: writing, code review, watch market lookups, Telegram responses |
| Claude Opus 4.6 | 5–15s | Complex reasoning, architecture decisions, valuation analysis requiring deep judgment |

**Actions:**
- [ ] Audit your current agent configs — note which model each agent is assigned
- [ ] Set Sonnet as the default model for all Telegram-facing bots
- [ ] Set Haiku for any pure routing/classification agents (intent detection, message triage)
- [ ] Reserve Opus only for explicitly flagged deep-analysis tasks — consider an opt-in `/deep` flag in Telegram
- [ ] For Vardalux watch lookup agents: Sonnet is sufficient; Haiku can handle simple price check queries

**Verification with Honeycomb:**  
Group spans by model name. Calculate average latency per model tier and confirm distribution matches intent (most volume on Haiku/Sonnet, minimal on Opus).

---

## Step 5 — Parallel Tool Calls & Parallel Subagent Spawning
**Est. Gain:** Up to 90% on multi-tool tasks; 4x throughput improvement  
**Effort:** ~30–60 minutes  
**Background:**  
Sequential tool execution stacks latency linearly. Four 300ms tool calls run sequentially = 1.2s total; run in parallel = 300ms total. Anthropic's own multi-agent research system reduced complex query time by 90% by redesigning agent prompts to encourage parallel sub-task spawning. For watch market lookups fetching Chrono24 price, comparable sales, and exchange rates simultaneously, parallelization is directly applicable.

**Actions:**
- [ ] Confirm `disable_parallel_tool_use` is NOT set to `true` in any agent configs (check all OpenClaw agent YAML/JSON files)
- [ ] Audit which agents make multiple sequential tool calls that could be independent — any agent fetching data from multiple sources before synthesizing is a candidate
- [ ] For multi-agent orchestration: restructure orchestrator prompts to spawn subagents concurrently rather than chaining them (async fan-out pattern)
- [ ] For Vardalux watch agents: if a task requires listing data + market comps + pricing history, invoke these as parallel tool calls in a single LLM turn
- [ ] Review OpenClaw's multi-agent parallel execution settings — enable concurrent subagent spawning in gateway config

**Verification with Honeycomb:**  
In your trace waterfall, look for sequential LLM eval spans stacking vertically (one after another). After optimization, those spans should appear horizontally (overlapping in time). This is the most visually obvious improvement in Honeycomb.

---

## Step 6 — Heartbeat Interval Tuning
**Est. Gain:** 10–20% background token reduction; reduces context pollution  
**Effort:** ~10 minutes  
**Background:**  
Background heartbeat loops that run too frequently silently drain tokens between user interactions. This inflates rolling context, which in turn slows inference. An aggressive 2-minute heartbeat on a monitoring agent can generate background token consumption that outpaces actual user-driven calls. The fix is matching heartbeat frequency to actual information change rate.

**Recommended Intervals:**

| Agent Type | Recommended Heartbeat |
|---|---|
| Active Telegram bot responding to messages | Event-driven (no polling) |
| Watch market data monitors (Chrono24, Grailzee) | 15–30 minutes |
| Invoice processing / document pipeline | On-demand / webhook-triggered only |
| Passive background monitors | 30–60 minutes |

**Actions:**
- [ ] Audit all agent heartbeat/polling intervals in your OpenClaw config
- [ ] Rewrite heartbeat prompts to log only **what changed** since last run — if nothing changed, one line maximum
- [ ] Convert any heartbeat-based agents that could be webhook/event-driven to event triggers instead
- [ ] For watch market monitors: price data doesn't change minute-to-minute; 15–30 min intervals are appropriate

**Verification with Honeycomb:**  
Look at span volume on background agents over a 1-hour window. After tuning, you should see a clear reduction in total span count from polling agents while user-driven spans remain unchanged.

---

## Step 7 — Workspace File Trimming
**Est. Gain:** 20–40% reduction in baseline prompt size; faster initial TTFT  
**Effort:** ~30 minutes  
**Background:**  
OpenClaw loads workspace files (SOUL.md, AGENTS.md, MEMORY.md) into every agent session's context automatically. Oversized files bloat the baseline context before the user message even arrives — meaning you're paying in latency and tokens before any real work begins.

**Target File Sizes:**

| File | Target Size | Strategy |
|---|---|---|
| `SOUL.md` | < 1 KB | Personality and core directives only; no examples |
| `AGENTS.md` | < 10 KB | Agent routing rules only; move agent details to individual agent files |
| `MEMORY.md` | < 3 KB | Recent high-value context only; purge stale entries weekly |
| Detailed content | `vault/` directory | Retrieved on-demand via MNEMO, not injected on every call |

**Actions:**
- [ ] Audit current file sizes: `wc -c SOUL.md AGENTS.md MEMORY.md` in your OpenClaw workspace
- [ ] Move any knowledge base content, examples, or reference data from workspace files to `vault/` for MNEMO-managed retrieval
- [ ] Reduce SOUL.md to core identity + directive statements only — strip examples or elaborations
- [ ] Trim AGENTS.md to routing rules only — move per-agent instructions to individual agent config files
- [ ] Set a weekly MEMORY.md review cadence: prune anything older than 2 weeks that isn't actively referenced
- [ ] Add file size checks to your deployment workflow to prevent drift

**Verification with Honeycomb:**  
Compare `input_tokens` on the first turn of a fresh session before vs. after trimming. The difference should match your file size cuts. If first-turn tokens are still high after trimming, something else is being injected at session start — investigate auto-injected context sources in OpenClaw gateway config.

---

## Ongoing: Honeycomb OTEL Monitoring Checklist

**Spans to instrument:**
- [ ] `gen_ai.operation.name` — tag every LLM call with agent/task name
- [ ] Model name + provider on every LLM span
- [ ] `input_tokens` and `output_tokens` per span
- [ ] TTFT (time to first token) per LLM call
- [ ] Tool call duration per tool name
- [ ] Agent loop iteration count

**Alerts to configure:**
- [ ] Agent completing >15 tool calls without converging → likely stuck loop
- [ ] Single agent session input_tokens exceeding 80K → context bloat warning
- [ ] Any LLM span duration >15s → latency spike alert
- [ ] Cache hit rate dropping below 70% on agents with prompt caching enabled

**Waterfall patterns to watch for:**
- Vertical stacking of LLM eval spans = sequential execution to parallelize (Step 5)
- Rising token counts across a single session = context bloat (Step 2)
- One extremely long span dominating trace = wrong model tier (Step 4)
- Repeated short background spans dominating volume = heartbeat too aggressive (Step 6)

---

## Progress Log

| Date | Step | Notes / Observations |
|---|---|---|
| May 2026 | ✅ Step 1 | streamMode off + IPv4 first — DONE |
| | Step 2 | |
| | Step 3 | |
| | Step 4 | |
| | Step 5 | |
| | Step 6 | |
| | Step 7 | |
