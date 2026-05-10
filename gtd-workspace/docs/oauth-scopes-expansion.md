# OAuth Scopes — Trina Expansion

Scopes required to support calendar write, Zoom meeting creation, Google Contacts
management, and Gmail management. Prepared 2026-05-10.

---

## Google OAuth (single credential, all scopes in one token)

### Already configured (no action needed)

These are live in `~/.openclaw/credentials/gtd-google-token.json`:

```
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/calendar.events
```

These cover: read events, create events, update events, cancel/delete events, and
adding Google Meet conferencing data. No new calendar scopes required.

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
- `contacts.other.readonly` — read "other contacts" (suggested contacts from Gmail history); needed for autocomplete/search
- `directory.readonly` — read Google Workspace directory entries (shared org contacts); useful if workspace directory is populated

**Gmail scope:**
- `mail.google.com/` — full Gmail access: read, search, send, draft, label, trash, delete. This is the widest scope; use it once rather than stacking narrower scopes that still require re-auth to add later.

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

## Zoom OAuth (separate credential, separate OAuth app)

Zoom uses its own OAuth server (`zoom.us`), not Google. Requires:
1. A Zoom OAuth app created at marketplace.zoom.us
2. Separate credential stored in `~/.openclaw/credentials/` (e.g. `gtd-zoom-token.json`)
3. A new plugin or shared-tools script for Zoom API calls

### Scopes

```
meeting:write
meeting:read
user:read
```

**What each covers:**
- `meeting:write` — create meeting, update meeting, delete meeting; join URL is returned in the create response
- `meeting:read` — get meeting details after creation (needed if join URL must be retrieved separately)
- `user:read` — read the authenticated user's profile; required to resolve the host `userId` when creating a meeting

### Zoom API endpoint

`POST https://api.zoom.us/v2/users/me/meetings` — creates a meeting and returns `join_url`, `start_url`, `id`.

### Notes

- Zoom does not share the Google credential; it is a separate OAuth 2.0 flow
- The join URL is in the create response; no second API call needed for basic scheduling
- `meeting:write:admin` scope exists for account-level admin creation; `meeting:write` is sufficient for the authenticated user's own meetings

---

## Re-authentication procedure

After adding scopes in Google Cloud Console:

1. Delete `~/.openclaw/credentials/gtd-google-token.json` to force re-auth
2. The next time a calendar or Gmail script runs, it will prompt for re-authorization through the browser OAuth flow
3. Accept all requested scopes; the new token will be written back to the same path

For Zoom, create a new OAuth app at marketplace.zoom.us, add the scopes above, and
implement the token storage and refresh pattern matching the Google credential setup.
