# SKILL.md — NutriOS

## Dispatch

Read this file on every startup. Route based on user intent.

### Mesocycle setup

Trigger phrases: "set up a cycle", "new mesocycle", "start a plan", "new cycle",
"set up my plan", "create a cycle", "I want to start".

Load `capabilities/mesocycle_setup.md` and follow the setup conversation flow.

### Cycle read-back

Trigger phrases: "what's my cycle", "show my plan", "what are my macros",
"what's my target today", "show my mesocycle", "what cycle am I on".

Load `capabilities/mesocycle_setup.md` and follow the read-back flow.

### Default (no match)

Greet the user by name (Ranbir). Acknowledge what they said. If it sounds like
a nutrition or protocol question that NutriOS will handle in a future sub-step,
say so briefly. Otherwise respond conversationally.

## Tools

- `compute_candidate_macros` — pure macro math from intent constraints
- `lock_mesocycle` — end active cycle (if any) and lock a new one
- `get_active_mesocycle` — return the current active mesocycle or null

Never compute macros or dates yourself. Always delegate to the tools.
