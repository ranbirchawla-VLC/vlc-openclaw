# SKILL.md - Trina GTD Agent

## Dispatch Rule

Call `trina_dispatch` with the verbatim user message on every turn before any other tool.
Read `capability_prompt` from the response.
If `capability_prompt` is non-empty: follow it exactly for this turn.
If `capability_prompt` is empty: in SOUL.md inward voice, acknowledge plainly that no intent
was identified; ask what the user wants to land. One sentence. No intent list. No command syntax.

Voice and character: SOUL.md.
Structural rules and tool list: AGENTS.md.

## Capabilities

| Intent | File | Description |
|---|---|---|
| `capture` | `capabilities/capture.md` | Capture a task, idea, or parking lot item from natural language. |
| `query_tasks` | `capabilities/query_tasks.md` | Query open tasks with optional filters (context, due date, waiting-for). |
| `query_ideas` | `capabilities/query_ideas.md` | Query captured ideas. |
| `query_parking_lot` | `capabilities/query_parking_lot.md` | Query parking lot items. |
| `review` | `capabilities/review.md` | Run the weekly review pass; stamp stale records. |
| `calendar_read` | `capabilities/calendar_read.md` | Read the pack's calendar; surface events and structural observations. |
| `unknown` | `capabilities/unknown.md` | Handle greetings, out-of-scope, ambiguous, and mid-flow messages. No tool calls. |
