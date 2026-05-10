# contacts - Contacts Capability

## Purpose

Search Google Contacts and create new contacts. Contact resolution during event
creation is handled automatically by `create_event` and `update_event` — this
capability is for explicit contact operations ("find Heather's email",
"add Marcus to my contacts").

## Workflow — Search

1. Extract search query (name or email fragment) from user message.
2. Call `search_contacts` with `{query}`.
3. On `ok: true`: render contacts per Verbatim Render Rule (Branch A).
4. On empty results (total_count: 0): Branch B.

## Workflow — Create

1. Extract name and email from user message (and phone if provided).
2. Call `create_contact` with `{name, email}` plus optional `phone`.
3. On `ok: true`: confirm creation (Branch C).
4. On `ok: false`: route to Branch D.

## Verbatim Render Rule

On search results, render each contact: "[name] — [email]" (plus phone if present).
On create success, render: "Added [name] ([email]) to your contacts."

## Branches

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. Contacts found | `total_count > 0` | List matches: name, email, phone (if present) |
| B. No results | `total_count = 0` | "No contacts found for '[query]'." |
| C. Contact created | `ok: true` from create_contact | "Added [name] ([email]) to your contacts." |
| D. `contacts_api_error` | `error.code = "contacts_api_error"` | Name the failure; offer to try again |

## Composition Guardrails

1. No arithmetic or inference — render contact fields exactly as returned.
2. On ambiguous search (multiple results): list all matches; ask the user which one.
3. Do not create a contact without confirming name and email with the user first.

## LLM Responsibilities

- Extract query for search or name/email/phone for create.
- Call the appropriate tool.
- Render from `data.contacts` or `data.contact` fields.

## What the LLM Does NOT Do

- Does not guess email addresses.
- Does not create a contact without a valid email from the user.
- Does not merge or modify existing contacts (update_contact not yet built).
