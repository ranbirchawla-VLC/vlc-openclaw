# OAuth Scopes — Trina Expansion

Scopes required to support calendar write, Zoom meeting creation (via Google Workspace
add-on), Google Contacts management, and Gmail management. Prepared 2026-05-10.

---

## Google OAuth (single credential, all scopes in one token)

### Already configured (no action needed)

These are live in `~/.openclaw/credentials/gtd-google-token.json`:

```
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/calendar.events
```

These cover: read events, create events, update events, cancel/delete events, and
adding conferencing data (including Zoom via the Workspace add-on). No new calendar
scopes required.

### New scopes to add

Re-authenticate with the existing credential adding these scopes:

```
https://www.googleapis.com/auth/contacts
https://www.googleapis.com/auth/contacts.other.readonly
https://www.googleapis.com/auth/directory.readonly
https://mail.google.com/
```

**Contacts scopes:**
- `contacts` — full access: list, get, create, update, delete contacts
- `contacts.other.readonly` — read "other contacts" (suggested contacts from Gmail history); needed for autocomplete and search
- `directory.readonly` — read Google Workspace directory entries (shared org contacts)

**Gmail scope:**
- `mail.google.com/` — full Gmail access: read, search, send, draft, label, trash, delete. Use the full scope once rather than stacking narrower scopes that each require a separate re-auth to add.

### Full scope list for re-authentication (copy-paste)

```
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/calendar.events
https://www.googleapis.com/auth/contacts
https://www.googleapis.com/auth/contacts.other.readonly
https://www.googleapis.com/auth/directory.readonly
https://mail.google.com/
```

---

## Zoom — no separate OAuth needed

Zoom is integrated into Google Workspace as a conferencing add-on. Creating a Zoom
meeting is handled entirely through the Google Calendar API `conferenceData` field
when creating or updating an event:

```json
"conferenceData": {
  "createRequest": {
    "requestId": "<unique-per-request-id>",
    "conferenceSolutionKey": { "type": "addOn" }
  }
}
```

Pass `conferenceDataVersion=1` in the API query parameters. Google routes the request
to the Zoom Workspace add-on, which generates the meeting and returns the join URL in
the event response under `conferenceData.entryPoints`.

No Zoom API credentials, no Zoom OAuth app, no separate Zoom scopes required.

---

## Re-authentication procedure

After adding scopes in Google Cloud Console (APIs & Services → Credentials → OAuth
consent screen → Scopes):

1. Delete `~/.openclaw/credentials/gtd-google-token.json` to force re-auth
2. The next time a calendar or Gmail script runs, it will prompt for browser OAuth
3. Accept all requested scopes; the new token is written back to the same path

Note: all Google surfaces (Calendar, Contacts, Gmail) share the single token file.
