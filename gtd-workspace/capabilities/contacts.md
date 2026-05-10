# contacts - Contacts Capability

## Purpose

Search Google Contacts and create new contacts. Contact resolution during event
creation is handled automatically by `create_event` and `update_event` — this
capability is for explicit contact operations ("find Heather's email",
"add Marcus to my contacts").

## Workflow — Search

1. Extract search query (name or email fragment) from user message.
2. Call `search_contacts` with `{user_id, query}`.
3. On `ok: true`: render contacts per Verbatim Render Rule (Branch A).
4. On empty results (total_count: 0): Branch B.

## Workflow — Create

1. Extract fields from user message. Required: `name`, `email`. Optional: `phone`, `first_name`, `last_name`, `company`, `title`, `notes`, `phone_type` (mobile/work/home), `email_type` (work/home/other).
2. Call `create_contact` with `{user_id}` and all available fields.
3. On `ok: true`: confirm creation (Branch C).
4. On `ok: false`: route to Branch D.

## Verbatim Render Rule

On search results, render each contact: "[name] — [email]" (plus phone, company, title if present).
On create success, render: "Added [name] ([email])[, [title] at [company]] to your contacts." Only include the title/company clause if those fields are non-null in `data.contact`.

## Branches

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. Contacts found | `total_count > 0` | List matches: name, email, phone, company, title (omit fields that are null) |
| B. No results | `total_count = 0` | "No contacts found for '[query]'." |
| C. Contact created | `ok: true` from create_contact | "Added [name] ([email])[, [title] at [company]] to your contacts." |
| D. `contacts_api_error` | `error.code = "contacts_api_error"` | Name the failure; offer to try again |
| E. Missing email | Email not yet provided by user | Ask: "What's their email address?" Do not call `create_contact` until you have a valid email. |

## Composition Guardrails

1. No arithmetic or inference — render contact fields exactly as returned.
2. On ambiguous search (multiple results): list all matches; ask the user which one.
3. Do not create a contact without confirming name and email with the user first.

## LLM Responsibilities

- Extract query for search; or name, email, and any available optional fields (phone, company, title, notes, first_name, last_name, phone_type, email_type) for create.
- Call the appropriate tool.
- Render from `data.contacts` or `data.contact` fields.

## What the LLM Does NOT Do

- Does not guess email addresses.
- Does not create a contact without a valid email from the user.
- Does not merge or modify existing contacts (update_contact not yet built).
