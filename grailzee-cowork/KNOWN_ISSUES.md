# Known Issues — grailzee-cowork

## Issue 1: OUTBOUND bundle requires all strategy state files on first cycle_planning session

**Surfaced:** 2026-04-19 during Session 5 Mac Studio end-to-end dry-run.

**Symptom:**
Running the outbound bundle build on first-ever use fails iteratively with "Bundle build failed: Missing <file>" for each strategy state file that hasn't been produced yet. Observed failures: cycle_focus.json, monthly_goals.json. Likely also: quarterly_allocation.json and possibly the six threshold config files.

**Root cause:**
grailzee_bundle/build_bundle.py treats ALL strategy state files as required inputs via _read_required() (file-exists check). On a first cycle_planning session, none of these files exist — they are OUTPUTS of strategy sessions that haven't run yet.

**Workaround in use:**
Operator writes placeholders for each missing file before the bundle build. Placeholders contain cycle_id for agent-side anchoring, placeholder: true marker, and null/empty field values. INBOUND overwrites them on first real strategy commit.

**Proper fix direction:**
Bundle builder should treat missing strategy-state files (cycle_focus, monthly_goals, quarterly_allocation) as optional when session_mode=cycle_planning, emitting null in the bundle manifest. For non-cycle_planning modes, strategy files should still be required. Threshold config files (signal, scoring, momentum, window, premium, margin) are a separate class — they should probably ship with sensible defaults in state/ on initial setup, not require first-session fabrication.

**Priority:** Medium-High — must be fixed before merge to main. Current behavior makes the plugin unusable for any first-ever operator without the workaround knowledge.

**Status:** Open

---

## Issue 2: is_cycle_focus_current() always returns False after first INBOUND write

**Surfaced:** 2026-04-19 during Session 5 discovery while investigating Issue 1.

**Symptom:**
grailzee_common.py's is_cycle_focus_current() reads top-level cycle_id from state/cycle_focus.json and compares against current_cycle_id. Any agent-side logic that gates on "is current focus fresh" will fail immediately after the first real strategy session commits.

**Root cause:**
The strategy_output.json schema's decisions.cycle_focus block has no cycle_id field — cycle_id lives at strategy_output top level. Cowork INBOUND's _emit() at unpack_bundle.py:509-513 writes the cycle_focus block verbatim, so state/cycle_focus.json gets targets/capital_target/etc. but no cycle_id. The agent then reads that file and sees no cycle_id match.

**Evidence of fixture divergence hiding this:**
- Bundle-side fixture (_default_cycle_focus) has cycle_id
- Strategy-output fixture (make_strategy_cycle_focus) has schema fields, no cycle_id
Tests pass; production breaks on first real session.

**Proper fix direction:**
Cowork INBOUND should inject cycle_id from strategy_output.json top-level into the cycle_focus block before writing. Coupling stays in one place.

**Priority:** High — MUST be fixed before merge to main.

**Status:** Open

---

## Issue 3: sourcing_brief path mismatch between analyzer output and bundle builder expectation

**Surfaced:** 2026-04-19 during Session 5 bundle build investigation.

**Symptom:**
Bundle builder expects sourcing_brief at output/briefs/sourcing_brief_<cycle_id>.json but the grailzee-eval analyzer writes it to state/sourcing_brief.json. Without manual intervention, the file is never at the path the builder needs.

**Root cause:**
Two possible design intents conflict:
- state/sourcing_brief.json as ephemeral working state produced by the analyzer
- output/briefs/sourcing_brief_<cycle>.json as the canonical archived deliverable the bundle should carry

Nothing currently bridges these — no post-analyzer publish step, no builder fallback to state/.

**Workaround in use:**
Operator manually copies state/sourcing_brief.json to output/briefs/sourcing_brief_<cycle_id>.json after each analyzer run.

**Proper fix direction:**
Either (a) the analyzer's report_pipeline should publish the sourcing brief to output/briefs/<cycle>.json as its final step, or (b) the bundle builder should read from state/sourcing_brief.json directly. Option (a) matches the architectural split (state = working, output = canonical).

**Priority:** Medium — fix before merge to main. Breaks clean first-run UX.

**Status:** Open
