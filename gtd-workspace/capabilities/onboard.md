# onboard - New User Registration Capability

## Purpose

Walk a new user through profile setup: name and timezone. Once complete, they
can use all GTD tools. Returning users who say hello get a direct greeting using
their stored name.

## Workflow

1. Call `update_profile({user_id})` in read-only mode to check registration status.
2. If `ok: true` — user is registered. Greet them by name from `data.profile.name`
   and ask what they want to do. End turn.
3. If `error.code = "unknown_user"` — new user. Ask for their name. End turn.
4. On the follow-up turn (name provided in context):
   Ask for their timezone using the city-name example format. End turn.
5. On the next turn (city provided in context):
   Resolve the city to an IANA timezone string (e.g. "Denver" → "America/Denver",
   "New York" → "America/New_York", "London" → "Europe/London").
   Call `update_profile({user_id, name, timezone})`.
6. On `ok: true`: confirm setup per Verbatim Render Rule (Branch A).
7. On `ok: false`: read `error.code`; route to Branch C or D.

**Tool parameters for read-only check:**

| Parameter | Value |
|---|---|
| `user_id` | `sender_id` from conversation metadata |

**Tool parameters for create:**

| Parameter | Value |
|---|---|
| `user_id` | `sender_id` from conversation metadata |
| `name` | Name provided by the user in conversation |
| `timezone` | IANA string resolved by you from the user's city |

## Verbatim Render Rule

On successful registration: "You're set up, [name]. What would you like to do?"
On returning user: "Hey [name] — what do you want to land?"

## Branches

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. New user registered | `ok: true` after create call | "You're set up, [name]. What would you like to do?" |
| B. Returning user | `ok: true` on read-only check | "Hey [name] — what do you want to land?" |
| C. `invalid_timezone` | `error.code = "invalid_timezone"` | "That timezone didn't register — try a city name like Denver, New York, or London." |
| D. `storage_io_failed` | `error.code = "storage_io_failed"` | "Something went wrong saving your profile. Try again in a moment." |

## Composition Guardrails

1. One question per turn. Do not ask for name and timezone in the same message.
2. Resolve city → IANA string yourself; never ask the user for an IANA string.
3. Do not confirm registration until `update_profile` returns `ok: true`.
4. No persistence narration ("saving your profile now...").
5. If the user's city is ambiguous (e.g. "Springfield"), pick the most likely
   IANA zone and confirm: "I'll set you to America/Chicago — is that right?"

## LLM Responsibilities

- Call `update_profile({user_id})` to check registration status.
- If new: collect name then timezone in separate turns using conversation context.
- Resolve city name to IANA timezone string before calling `update_profile`.
- Call `update_profile({user_id, name, timezone})` to register.
- Render from `data.profile.name` on success.

## What the LLM Does NOT Do

- Does not ask the user for an IANA timezone string directly.
- Does not confirm registration before `ok: true`.
- Does not ask multiple questions in one turn.
- Does not narrate tool calls.
