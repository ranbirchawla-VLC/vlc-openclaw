# turn_state Dispatch Architecture — Grailzee Eval

**Date**: 2026-05-05
**Branch**: feature/grailzee-eval-v2
**Commits**: a5eeb80, b62dfe2

---

## The Problem

The grailzee-eval agent has three operational modes — deal evaluation, report
processing, and ledger ingest — each with distinct instructions in a capability
file (`deal.md`, `report.md`, `ledger.md`). The agent needs those instructions
in context before it can do anything useful.

The prior AGENTS.md approach: "Read one file: SKILL.md." This fails silently
because no `read` tool exists in `tools.allow`. The model receives the
instruction but cannot execute it; the capability files never land in context.
The symptom: the model falls back to generic behavior, ignores Branch A/B/C/D
templates, synthesizes its own math, and overrides the tool's yes/no decision.

The root failure observed at the operator gate (2026-05-03):

- Turn 1 (M7941A1A0RU-0003): LLM described "the script" (tech leak), hallucinated
  a blue dial not in the tool output, ignored the verbatim-render rule.
- Turn 2 (79830RB): LLM synthesized margin math from `cycle_reason` prose and
  concluded "should be a strong buy signal," directly overriding the tool's
  `decision: no`.

Both failures trace to one cause: no capability instructions in context.

---

## Why Per-Session File Reads Are Not The Answer

Putting "read SKILL.md" in AGENTS.md is the wrong shape even if a `read` tool
existed. The model reads once at session start; if the session continues across
multiple intent types (deal, then ledger, then deal again), the first read
binds the wrong capability for later turns. Per-session reads are also
invisible to the tool call log — you cannot audit whether the read happened,
what it returned, or whether the model used it.

The right shape: a first-call-every-turn tool that injects fresh instructions
explicitly, leaves an audit trail in the tool call log, and can be tested
independently of the model.

---

## The Solution: turn_state

`skills/grailzee-eval/scripts/turn_state.py` — stdin-dispatched Python script,
registered as a plugin tool, called first on every turn via AGENTS.md PREFLIGHT.

### What it does

1. Receives `{user_message: str}` from the model.
2. Classifies intent: slash command match first, then `$`-price signal for
   free-form deals, then keyword patterns for report and ledger.
3. Reads the matching capability file from disk — fresh every call, no caching.
4. Returns `{intent, capability_prompt}`.

The model reads `capability_prompt` and follows it. If `capability_prompt` is
empty (unrecognized message), PREFLIGHT instructs the model to return one line
naming the three commands.

### Classifier routing

| Input | Intent | Capability file |
|---|---|---|
| `/eval ...` | `evaluate_deal` | `capabilities/deal.md` |
| `/report` | `report` | `capabilities/report.md` |
| `/ledger` | `ledger` | `capabilities/ledger.md` |
| Free-form with `$\d` | `evaluate_deal` | `capabilities/deal.md` |
| `new report`, `.xlsx`, `pipeline` | `report` | `capabilities/report.md` |
| `ledger`, `ingest`, `watchtrack`, `extract`, `jsonl` | `ledger` | `capabilities/ledger.md` |
| Anything else | `default` | (empty; one-line reply) |

Free-form deal detection uses `$` as the price signal. Without `$`, the
operator uses `/eval`. This trades recall for precision: a false positive
(routing a non-deal to evaluate_deal) is worse than requiring the `/eval`
prefix, because the model would then try to call evaluate_deal with no
parseable price.

### AGENTS.md PREFLIGHT

```
## PREFLIGHT

Before every response, call `turn_state` with the verbatim user message.
Read `capability_prompt` from the response. If non-empty, it contains your
complete instructions for this turn. Follow them exactly. If empty, the
message is not a recognized command; reply with one line:

    /eval for deal evaluation, /report to run the analyzer, /ledger to fold in a sales extract.

No response before turn_state completes.
```

The hard constraint — "no response before turn_state completes" — is what
closes the gate. Without it, a model that is confident about intent may skip
the call and respond from memory.

### Why this shape works

- **Auditable**: every turn has a `turn_state` call in the tool log with the
  classified intent visible.
- **Fresh**: capability files read from disk every call; editing `deal.md`
  takes effect on the next turn without a gateway restart.
- **Testable**: classifier, capability loader, and entry point all have
  independent unit tests (50 tests total).
- **Single operator**: no user_id, no session boundary tracking, no history
  resets. This is a single-operator agent; the nutriosv2 complexity that
  handles intent transitions between users is not needed here.

---

## Second Fix: GRAILZEE_ROOT Environment Injection

`ingest_sales.py` refuses to run without `GRAILZEE_ROOT` explicitly set in
the environment; it raises `EnvironmentError` rather than falling back to a
default path. This is intentional: the script writes to the production ledger
on Google Drive and a silent fallback to the wrong path would be a data hazard.

The gateway process does not inherit shell environment variables, so
`GRAILZEE_ROOT` was never present. Fix: `index.js` defines `SPAWN_ENV` as a
module constant and passes it to all `spawnSync` calls:

```javascript
const GRAILZEE_ROOT = process.env.GRAILZEE_ROOT ||
  "/Users/ranbirchawla/Library/CloudStorage/.../GrailzeeData";

const SPAWN_ENV = { ...process.env, GRAILZEE_ROOT };
```

`process.env.GRAILZEE_ROOT` wins if the gateway has it; the production Drive
path is the fallback. All three tools (`evaluate_deal`, `report_pipeline`,
`ingest_sales`) and `turn_state` use `SPAWN_ENV`.

---

## Gate Testing Findings

Two bugs surfaced during operator gate testing after turn_state was wired.

### 1. "No Numerals numerals" label bug

`_bucket_label` in `evaluate_deal.py` unconditionally appended `" numerals"`
to the `dial_numerals` value:

```python
return f"{color_part}, {dial_numerals} numerals, {auction_type}"
```

For the enum value `"No Numerals"` this produced `"No Numerals numerals"`.
Fix: conditional append — `"No Numerals"` renders verbatim; `Arabic`, `Roman`,
`Stick` get `" numerals"` appended.

### 2. auction_type defaulted to wildcard; free-form messages always hit Branch B

`deal.md` Step 1 said "pass an axis only when the operator names it." With
`auction_type` omitted, `evaluate_deal` treated it as a wildcard and returned
`match_resolution: ambiguous` for any reference that had both NR and RES
bucket variants — which includes most Tudor and Rolex references.

The operator expectation: Grailzee deals are NR unless explicitly stated.
Fix: `deal.md` Step 1 now defaults `auction_type` to `NR`; the operator passes
`RES` when needed.

---

## Backlog Item Added

**Unknown reference resolution in /report**: the report pipeline returns an
`unnamed` list of references it could not resolve to model names. The current
`report.md` instructs the agent to web-search each and call
`append_name_cache_entry`. This was not fully validated in the gate test.
Needs a dedicated test pass with a report that actually contains unnamed
references.

---

## Files Changed

| File | Change |
|---|---|
| `skills/grailzee-eval/scripts/turn_state.py` | New — classifier + capability loader + stdin entry point |
| `skills/grailzee-eval/tests/test_turn_state.py` | New — 50 tests |
| `plugins/grailzee-eval-tools/index.js` | turn_state registration (spawnStdin) + SPAWN_ENV |
| `skills/grailzee-eval/AGENTS.md` | PREFLIGHT section replaces "Read one file: SKILL.md" |
| `skills/grailzee-eval/capabilities/deal.md` | auction_type NR default; LLM responsibilities updated |
| `skills/grailzee-eval/scripts/evaluate_deal.py` | No Numerals label fix in `_bucket_label` |
| `skills/grailzee-eval/tests/test_plugin_shape.py` | turn_state assertions + spawnStdin dispatch check |
| `skills/grailzee-eval/tests/test_agent_surface.py` | turn_state added to tools allow pin |
| `Makefile` | test-grailzee-eval-turn-state target |
| `update_openclaw_config.py` | One-time script to add turn_state to tools.allow in openclaw.json |
