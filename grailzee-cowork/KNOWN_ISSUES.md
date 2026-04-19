# Known Issues — grailzee-cowork

## Issue 1: OUTBOUND bundle requires cycle_focus.json on first cycle_planning session

**Surfaced:** 2026-04-19 during Session 5 Mac Studio end-to-end dry-run.

**Symptom:**
Running the outbound bundle build in cycle_planning mode fails with "Bundle build failed: Missing cycle_focus: <path>/state/cycle_focus.json"

**Root cause:**
The bundle builder in grailzee_bundle/build_bundle.py treats state/cycle_focus.json as a required input. On the FIRST cycle_planning session for a new cycle, that file does not yet exist — it is produced by the strategy session itself. Chicken-and-egg.

**Workaround in use:**
Operator manually writes a placeholder cycle_focus.json before the first bundle build.

**Proper fix direction:**
Bundle builder should treat missing cycle_focus.json as valid for session_mode=cycle_planning and include a null placeholder in the bundle manifest. Other session modes may still reasonably require it to exist.

**Priority:** Medium — fix before merge to main OR document as manual step for first-cycle sessions.

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
