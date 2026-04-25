# CLAUDE.md — vlc-openclaw

## Project Overview
Vardalux Collections OpenClaw workspace. Multi-agent system for running our luxury business and some personal time management skills

## Core Principle
LLM = synthesis + human judgment. Python = everything deterministic.
If it's math, formatting, templating, or substitutions → Python.
If it's writing, visual assessment, or strategic decisions → micro-skill.


## Build Order (follow strictly)
1. schema/draft_schema.json
2. tools/run_pricing.py
3. tools/run_char_subs.py
4. tools/run_checklist.py
5. tools/run_phase_b.py
6. tools/run_grailzee_gate.py
7. skills/step3a-canonical/SKILL.md + references/voice-tone.md
8. skills/step1-photos/SKILL.md
9. skills/step0-watchtrack/SKILL.md
10. pipeline.py

Python tools first, micro-skills second, orchestrator last.

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
- No external deps beyond `requests` and `reportlab` (already installed)
- Error messages to stdout (OpenClaw captures for Slack/Telegram)
- references/ folder is read-only at runtime
- Character substitutions: sort by string length descending before applying
- Shared data travels through `_draft.json`, not through context
- Prefer match/case over if/elif chains when branching on a known value (platform names, step numbers, condition ratings)


## Repo Structure
- `skills/` — existing OpenClaw skills (DO NOT modify without asking)
- `watch-listing-workspace/` — new decomposed pipeline (active build target)
- `memory/` — OpenClaw memory files
- `pipelines/` — pipeline definitions
- `Vardalux_Listing_Pipeline_Decomposition_Spec.md` — THE SPEC (read this first)

## Git Workflow
- Never commit directly to main
- Use feature branches: `feature/step-N-description`
- Commit after each tool passes tests
- Commit messages: `[build] tool_name — what was built/fixed`

## What NOT to Do
- Do not rebuild existing assets (generate_listing_pdf.py, draft_save.py, 
  platform-templates.md, character-substitutions.md, posting-checklist.md)
- Do not delete or modify the monolith skill
- Do not skip test validation
- Do not combine multiple build steps without confirmation



