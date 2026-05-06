# CLAUDE.md — vlc-openclaw

## Project Overview
Vardalux Collections OpenClaw workspace. Multi-agent system for running our luxury business and some personal time management skills

The repo also houses the Grailzee analyzer at `skills/grailzee-eval-v2/`, 
currently in active refactor against `grailzee_schema_design_v1.md` and 
`v1_1.md`. Schema phases A through D land in place. The carve-out: the 
"DO NOT modify skills/ without asking" rule does not apply to this 
directory during the refactor.

## Core Principle
LLM = synthesis + human judgment. Python = everything deterministic.
If it's math, formatting, templating, or substitutions → Python.
If it's writing, visual assessment, or strategic decisions → micro-skill.

## Per-Task Standard
Every Claude Code task ends with a review report and stops. Does not commit. 
Report includes:
- Files changed with line counts
- What the change does, in two sentences
- Verification step run and result. If verification fails, report and stop. 
  Do not patch around the failure without flagging
- OTEL spans added or modified, with attributes
- Anything noticed during the work worth eyeballing: edge cases, surprising 
  existing code, schema refinements, ambiguity in the task spec
- Anything implied by the task but not done, with reasoning
- Specific things to verify before commit

Reviewer commits or returns for changes. If returned, Claude Code adjusts 
and re-reports against the same standard.

## OTEL Standard
Top-level functions in any tool or script wrap in spans. Attributes are 
consistent within a subproject (cycle_id, source_report, references_count 
for Grailzee; listing_ref, platform, step_number for watch-listing). 
Honeycomb exporter wired at end of refactor; instrumentation present from 
day one.

## Schema and Config Files
Config files (any file written by strategy and read by automation) follow 
the no-nulls rule: every field has a concrete factory default at file 
creation. Fields at default land in a top-level `defaulted_fields` array 
of dotted paths. Strategy writes remove paths from the array. Per the 
Grailzee schema v1.1 standing rule.

Per-file `schema_version` is required. Consumers read the version, route 
to the appropriate parser, and fail loud on a newer-than-self version.

Config files carry `last_updated` (ISO timestamp) and `updated_by` 
(session id or script name) on every write.

## Testing Requirements
- Every Python tool MUST have tests before it is considered complete
- Always use `make test-*` targets (not raw pytest) to run tests.
- It is always safe to run `make test`, `make test-nutrios-*` without asking.
- For TDD, prefer the most specific target (e.g., `make test-nutrios-time`).
- Every tool must be runnable standalone: `python tool_name.py /path/to/_draft.json`
- Every tool validates _draft.json against the schema before operating
- Do NOT present code as complete until tests pass
- Run tests after every edit to a test file

## Code Standards
- Python 3.10+
- No external deps beyond `requests` and `reportlab` for watch-listing 
  tools. Grailzee analyzer additionally permits `opentelemetry-sdk` and 
  `opentelemetry-exporter-otlp` for Honeycomb wiring.
- Error messages to stdout (OpenClaw captures for Slack/Telegram)
- references/ folder is read-only at runtime
- Character substitutions: sort by string length descending before applying
- Shared data travels through `_draft.json`, not through context
- Prefer match/case over if/elif chains when branching on a known value 
  (platform names, step numbers, condition ratings)

## Session-Open Protocol

Each workspace has its own progress file. Read the right one for the session:

| Workspace | Progress file |
|---|---|
| Grailzee | `skills/grailzee-eval/progress.md` + `GRAILZEE_SYSTEM_STATE.md` |
| GTD | `gtd-workspace/progress.md` |
| NutriOS v2 | `skills/nutriosv2/progress.md` |
| Index | `.claude/progress.md` (workspace index only) |

Do not update `.claude/progress.md` — update the workspace file directly.

## Repo Structure
- `skills/` — existing OpenClaw skills (DO NOT modify without asking). 
  Active commission: `skills/grailzee-eval/` for the Grailzee eval v2 build.
- `gtd-workspace/` — GTD agent workspace
- `plugins/` — OpenClaw plugin tools (one plugin per agent)
- `memory/` — OpenClaw memory files
- `pipelines/` — pipeline definitions
- `state/` — Grailzee analyzer reads/writes here (config files, cache, 
  ledger, cycle outcomes)

## Git Workflow
- Never commit directly to main
- Use feature branches: `feature/step-N-description` for watch-listing; 
  `feature/grailzee-<phase>-<task>` for Grailzee (e.g., 
  `feature/grailzee-A1-helper`)
- Commit after each tool passes tests
- Commit only after the close-out report is reviewed
- Commit messages: `[build] tool_name — what was built/fixed`

## What NOT to Do
- Do not skip test validation
- Do not combine multiple build steps without confirmation
- Do not modify analyzer files outside the commissioned task's scope (each 
  Grailzee task names its file scope explicitly)
