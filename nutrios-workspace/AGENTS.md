# AGENTS.md - NutriOS Agent

This is the NutriOS dedicated agent workspace.

## On Every Message

Load and follow the NutriOS skill:
- `skills/nutrios/SKILL.md`

The NutriOS skill is the SOLE handler for every inbound message.
Do not load any other skills or system prompts.

## Data Store

NutriOS data lives in: `data/`

All nutrios_read / nutrios_write paths are relative to `data/`.
