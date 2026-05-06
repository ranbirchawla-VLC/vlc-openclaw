# progress.md — index

Each workspace tracks its own progress. Open the relevant file for the session.

| Workspace | Progress file | Status |
|---|---|---|
| Grailzee (eval + ledger) | `skills/grailzee-eval/progress.md` | Track 1 Shape K ACTIVE |
| GTD | `gtd-workspace/progress.md` | Sub-step 2b.3 SHIPPED |
| NutriOS v2 | `skills/nutriosv2/progress.md` | Exec lockdown CLOSED; sub-step closure pending |

## Session-open protocol

1. Identify the workspace for this session
2. Read that workspace's `progress.md`
3. For Grailzee: also read `GRAILZEE_SYSTEM_STATE.md` at repo root

## Why workspace-scoped files

Parallel sessions on different tracks were causing merge conflicts in a single
monolithic progress.md. Each workspace file is only touched by sessions working
in that workspace.
