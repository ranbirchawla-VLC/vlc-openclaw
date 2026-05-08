# update_profile - Profile Update Capability

## Purpose

Update an existing user's timezone or display name. The LLM resolves city names
to IANA timezone strings before calling the tool.

## Workflow

1. Read the user's intent: timezone change, name change, or both.
2. If timezone is mentioned as a city ("New York", "Denver", "London"), resolve
   it to the correct IANA string before calling the tool.
3. Call `update_profile({user_id, name?, timezone?})` with only the fields being changed.
4. On `ok: true`: confirm per Verbatim Render Rule (Branch A).
5. On `ok: false`: read `error.code`; route to Branch B or C.

**Tool parameters:**

| Parameter | Value |
|---|---|
| `user_id` | `sender_id` from conversation metadata |
| `name` | New display name (omit if not changing) |
| `timezone` | IANA timezone string resolved from city (omit if not changing) |

## Verbatim Render Rule

On success, render from `data.profile`:
- Timezone update: "Done — timezone set to [timezone from data.profile.timezone]."
- Name update: "Done — I'll call you [name from data.profile.name] from now on."
- Both: "Done — [name], timezone set to [timezone]."

## Branches

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. Success | `ok: true` | Render per Verbatim Render Rule |
| B. `invalid_timezone` | `error.code = "invalid_timezone"` | "That timezone didn't register — try a city name like Denver, New York, or London." |
| C. `storage_io_failed` | `error.code = "storage_io_failed"` | "Something went wrong. Try again in a moment." |

## Composition Guardrails

1. Resolve city → IANA string yourself; never ask the user for an IANA string.
2. Only pass fields that are actually being changed; omit the rest.
3. No persistence narration.
4. If the city is ambiguous, pick the most likely zone and confirm before calling.

## LLM Responsibilities

- Identify which fields the user wants to change.
- Resolve city name to IANA timezone string if timezone is being updated.
- Call `update_profile` with `user_id` and only the changed fields.
- Render from `data.profile` per Verbatim Render Rule on success.
- On `invalid_timezone`: ask the user to try a different city name.

## What the LLM Does NOT Do

- Does not ask the user for an IANA string.
- Does not pass fields the user did not request to change.
- Does not confirm the update before `ok: true`.
- Does not narrate tool calls.
