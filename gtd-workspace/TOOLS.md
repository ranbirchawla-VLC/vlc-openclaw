# Tools: GTD Workspace

Plugin tools registered with the gateway. All tool calls go through the plugin surface; no direct script invocation.

---

## Dispatcher

| Tool | Description |
|------|-------------|
| `trina_dispatch` | Classify intent from the verbatim user message and return the matching capability prompt. Call first on every turn before any other tool. Returns `{ok: true, data: {intent, capability_prompt}}`. |

---

## Date Utility

| Tool | Description |
|------|-------------|
| `get_today_date` | Return today's date as YYYY-MM-DD in the user's timezone. Registered in `shared-tools` plugin (not gtd-tools). Pass `user_id` to resolve per-user timezone from `profile.json`; falls back to `America/Denver`. Returns `{ok: true, data: {date: "YYYY-MM-DD"}}`. Call before any flow that requires the current date: due-date capture, overdue queries, review window, calendar default. |

---

## Calendar Tools

| Tool | Description |
|------|-------------|
| `create_event` | Create a calendar event. Pass `attendee_names` (display names) and/or `attendees` (emails); Python resolves names via Google Contacts. Set `add_zoom: true` to attach Zoom. Returns `{ok: true, data: {event: {id, summary, start, end, html_link, attendees, zoom_url}}}`. Error codes: `contact_not_found` (with `unresolved_names`), `calendar_api_error`. |
| `update_event` | Update fields on an existing event (PATCH). Only provided fields are changed. Same attendee resolution as create_event. Requires `event_id` from `list_events`. |
| `cancel_event` | Cancel a calendar event. Notifies attendees by default (`send_updates: "all"`). Returns `{cancelled: true, event_id}`. |
| `search_contacts` | Search Google Contacts by name or email. Returns `{contacts: [{resource_name, name, email, phone, all_emails}], total_count}`. |
| `create_contact` | Create a new Google Contact. Requires `name` and `email`; optional `phone`. |
| `list_events` | List upcoming Google Calendar events. Returns `{ok: true, data: {events: [{id, summary, start, end, attendees, location, description, html_link}]}}`. |
| `get_event` | Get a single Google Calendar event by ID. Returns `{ok: true, data: {event: {...}}}` with the full event object. |

---

## GTD Tools

| Tool | Description |
|------|-------------|
| `update_profile` | Read or create/update a user profile. Call with `{user_id}` only to check registration (returns current profile or `unknown_user`). Call with `{user_id, name, timezone}` to create or update. `timezone` must be a valid IANA string resolved by the LLM from the user's city. Returns `{ok: true, data: {profile: {user_id, name, timezone, registered_at, updated_at}}}`. Error codes: `unknown_user`, `missing_required_field`, `invalid_timezone`, `storage_io_failed`. |
| `complete` | Mark a GTD task or idea as done. Returns `{ok: true, data: {completed: {id, title, status, completed_at, ...}}}`. Only task and idea are supported. Always call `query_tasks` or `query_ideas` first to obtain `record_id`. Error codes: `record_not_found`, `already_completed`, `unsupported_record_type`, `storage_io_failed`. |
| `capture` | Capture a GTD record (task, idea, or parking_lot). Returns `{ok: true, data: {captured: {...}}}`. Captured fields by type; task: id, title, context, project, priority, waiting_for, due_date, notes, status, created_at, updated_at, last_reviewed, completed_at. idea: id, title, topic, content, status, created_at, updated_at, last_reviewed, completed_at. parking_lot: id, content, reason, status, created_at, updated_at, last_reviewed, completed_at. record_type, source, telegram_chat_id excluded. |
| `query_tasks` | Query GTD tasks with optional filters. Returns `{ok: true, data: {items, total_count, truncated}}`. |
| `query_ideas` | Query GTD ideas. Returns `{ok: true, data: {items, total_count, truncated}}`. |
| `query_parking_lot` | Query GTD parking lot items. Returns `{ok: true, data: {items, total_count, truncated}}`. |
| `review` | Run a structured GTD review pass; stamp stale records per record type. Returns `{ok: true, data: {reviewed_at: <iso>, by_type: {tasks: {items, total_count, truncated}, ideas: {...}, parking_lot: {...}}}}`. On partial stamp failure: `{ok: false, error: {code: "storage_unavailable", path: <failing-file>}}`. |

---

## Paths

```
storage_root:  $GTD_STORAGE_ROOT
user_data:     {storage_root}/gtd-agent/users/{user_id}/
capabilities:  gtd-workspace/capabilities/
memory:        gtd-workspace/memory/
```
