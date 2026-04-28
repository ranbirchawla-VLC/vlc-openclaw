# SKILL.md: NutriOS

## Dispatch

Call `turn_state` on every user turn before anything else. Inputs: `user_message`
(the user's text verbatim) and `user_id` (their Telegram user ID). Read `intent`
and `capability_prompt` from the result.

**Intent routing:**

### mesocycle_setup

Follow the setup conversation flow as directed by `capability_prompt`.

### cycle_read_back

Follow the read-back flow as directed by `capability_prompt`.

### default

Greet the user by name (Ranbir). Acknowledge what they said. If it sounds like
a nutrition or protocol question that NutriOS will handle in a future sub-step,
say so briefly. Otherwise respond conversationally.

The `capability_prompt` field contains the full capability instructions for
mesocycle_setup and cycle_read_back intents. Read it verbatim. Do not load
capability files yourself.

## Tools

- `turn_state`: call first on every user turn; returns intent, boundary, and capability_prompt
- `compute_candidate_macros`: pure macro math from intent constraints
- `lock_mesocycle`: end active cycle (if any) and lock a new one
- `get_active_mesocycle`: return the current active mesocycle or null
- `recompute_macros_with_overrides`: redistribute weekly kcal budget given per-day overrides

Never compute macros or dates yourself. Always delegate to the tools.
