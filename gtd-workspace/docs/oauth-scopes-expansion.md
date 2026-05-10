# Trina — Complete Google OAuth Credential Spec

Single OAuth credential covering all Trina surfaces: Calendar, Contacts, Gmail.
One token file at `~/.openclaw/credentials/gtd-google-token.json`.

Updated 2026-05-10.

---

## Complete scope list (all scopes, one per line)

```
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/calendar.events
https://www.googleapis.com/auth/contacts
https://www.googleapis.com/auth/contacts.other.readonly
https://www.googleapis.com/auth/directory.readonly
https://mail.google.com/
```

---

## What each scope enables

### Calendar

| Scope | Operations covered |
|---|---|
| `auth/calendar` | Read calendars list; read, create, update, delete events; add Zoom conferencing via Workspace add-on |
| `auth/calendar.events` | Read, create, update, delete individual events; required alongside `calendar` for event write operations |

Both calendar scopes are already live. No change needed there.

### Contacts

| Scope | Operations covered |
|---|---|
| `auth/contacts` | List contacts; get contact; create contact; update name/email/phone/address/notes; add and remove contact group memberships (tags/labels); delete contact |
| `auth/contacts.other.readonly` | Read "Other contacts" — people from Gmail/Calendar history not in main Contacts; required for autocomplete and "did you mean" search |
| `auth/directory.readonly` | Read Google Workspace org directory; surfaces shared company contacts across the workspace |

Contact groups (what Google Contacts calls labels/tags) are managed via the People API `contactGroups` endpoint. The `auth/contacts` scope covers all group operations: create group, rename group, add member, remove member, delete group.

### Gmail

| Scope | Operations covered |
|---|---|
| `mail.google.com/` | Read inbox; read message body and attachments; search by query; list threads; send new message; reply; forward; create and save drafts; add labels; remove labels; move to trash; permanently delete |

`mail.google.com/` is the full-access Gmail scope. It covers every operation you named. Using the single full-access scope avoids the need to re-auth each time a new Gmail operation is added.

---

## Zoom

No separate OAuth credential required. Zoom is integrated into Google Workspace as a conferencing add-on. To create a Zoom meeting, include `conferenceData` in the Calendar API create/update request:

```json
"conferenceData": {
  "createRequest": {
    "requestId": "<unique-string-per-request>",
    "conferenceSolutionKey": { "type": "addOn" }
  }
}
```

Pass `conferenceDataVersion=1` in the query parameters. Google routes the request to the Zoom add-on; the join URL comes back in `conferenceData.entryPoints` on the event response.

---

## Re-authentication

1. Open Google Cloud Console → APIs & Services → OAuth consent screen → Scopes
2. Add all scopes from the list above that are not yet present
3. Save the consent screen
4. Delete `~/.openclaw/credentials/gtd-google-token.json`
5. Trigger any script that calls `get_google_credentials()` — it will open a browser OAuth flow
6. Sign in and accept all requested scopes; the token is written back to the same path

All surfaces (Calendar, Contacts, Gmail) share this single token file.
