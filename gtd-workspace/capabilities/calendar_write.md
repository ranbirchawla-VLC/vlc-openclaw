# calendar_write - Calendar Write Capability

## Purpose

Create, update, and cancel calendar events. Contact resolution is Python's job:
pass display names in `attendee_names` and Python looks them up in Google Contacts.
The LLM handles date/time parsing, confirmation rendering, and the contact-not-found
clarification branch.

## Workflow — Create

1. Extract: summary, date/time (start + end), attendees (names or emails), Zoom needed?
2. Call `get_today_date` with `{user_id}` to get today's date and timezone.
3. Resolve relative dates ("tomorrow", "Friday at 3pm") to ISO datetime strings using
   `data.timezone` from `get_today_date`. Format: `YYYY-MM-DDTHH:MM:SS` (no UTC offset).
4. Call `create_event` with `{user_id, summary, start, end}` plus optional fields.
   - Use `attendee_names` for display names; Python resolves to emails.
   - Use `attendees` for email addresses you already have.
   - Set `add_zoom: true` if a Zoom meeting was requested.
5. On `ok: true`: render per Verbatim Render Rule (Branch A).
6. On `contact_not_found`: ask for the email (Branch B).
7. On other `ok: false`: route to Branch C.

## Workflow — Update

1. Call `list_events` to identify the event and get its `id`.
2. Call `get_today_date` if new dates are involved.
3. Call `update_event` with `{user_id, event_id}` and only the fields being changed.
4. On `ok: true`: render updated event (Branch A).
5. On `contact_not_found`: same as Branch B — ask for the email; retry with `attendees` when user replies.

## Workflow — Cancel

1. Call `list_events` to identify the event and get its `id`.
2. Call `cancel_event` with `{user_id, event_id}`.
3. On `ok: true`: confirm cancellation (Branch D).

## Verbatim Render Rule

On successful create or update, render from `data.event`:
- "Scheduled: [summary] on [start date] at [start time]."
- If attendees present: "Invited: [names or emails from data.event.attendees]."
- If `zoom_url` present: "Zoom: [zoom_url]."

Times are already in the user's local timezone — render as-is, no conversion.

## Branches

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. Success (create/update) | `ok: true` | Render summary, time, attendees, zoom_url from data.event |
| B. `contact_not_found` | `error.code = "contact_not_found"`; `error.unresolved_names` present | Ask: "I couldn't find [name] in contacts — what's their email?" One question; end turn. When the user replies with an email: call `create_event` directly with that email in `attendees` — do NOT call `trina_dispatch`. Carry all original parameters (summary, start, end, add_zoom, etc.); drop the unresolved name from `attendee_names`. |
| C. `calendar_api_error` | `error.code = "calendar_api_error"` | Name the failure plainly; offer to try again |
| D. Cancelled | `ok: true` from cancel_event | "Cancelled — [summary]. Attendees notified." |

## Composition Guardrails

1. Always call `get_today_date` before constructing start/end datetime strings.
2. Use `data.timezone` from `get_today_date` for all datetime construction.
3. Times are Python's responsibility — never compute offsets or convert timezones.
4. For cancel: always call `list_events` first to confirm which event the user means before cancelling.
5. One question per turn on contact_not_found — do not ask for multiple missing emails at once.
6. On contact_not_found reply: call `create_event` or `update_event` directly — never re-dispatch via `trina_dispatch`. The user's email reply is a continuation of this flow, not a new intent.

## LLM Responsibilities

- Parse user intent: create vs update vs cancel.
- Call `get_today_date` to anchor relative dates.
- Construct ISO datetime strings from natural language using the returned timezone.
- Pass display names in `attendee_names`; Python resolves to emails.
- Render from `data.event` fields; do not recompose or embellish.

## What the LLM Does NOT Do

- Does not compute timezone offsets or convert times.
- Does not guess event IDs — always call `list_events` first.
- Does not confirm cancellation before `ok: true` from cancel_event.
- Does not ask for multiple pieces of missing info in one turn.
