"""contacts_api.py -- Google People API helpers shared by calendar and contacts tools.

Internal module; not registered with the gateway. Provides:
  search_contacts(query) -> list[dict]
  get_primary_email(name) -> str | None
  create_contact(name, email, phone=None) -> dict

All functions build their own service client; callers pass credentials.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_here = Path(__file__).parent
sys.path.insert(0, str(_here.parent))   # scripts/

from common import GTDError, get_google_credentials
from otel_common import _is_transient_google, get_tracer
from opentelemetry.trace import Status, StatusCode

from googleapiclient.discovery import build

_SCOPES = [
    "https://www.googleapis.com/auth/contacts",
    "https://www.googleapis.com/auth/contacts.other.readonly",
    "https://www.googleapis.com/auth/directory.readonly",
]
_MAX_RETRIES = 3
_PERSON_FIELDS = "names,emailAddresses,phoneNumbers,memberships"


def _people_service():
    creds = get_google_credentials(_SCOPES)
    return build("people", "v1", credentials=creds)


def _retry(fn):
    """Retry fn up to _MAX_RETRIES times on transient errors; raise on exhaustion."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        if attempt > 0:
            time.sleep(1)
        try:
            return fn()
        except Exception as exc:
            if _is_transient_google(exc):
                last_exc = exc
                continue
            raise
    raise last_exc  # type: ignore[misc]


def _fmt_contact(person: dict) -> dict:
    """Project a People API person resource to a flat dict."""
    names = person.get("names", [])
    emails = person.get("emailAddresses", [])
    phones = person.get("phoneNumbers", [])
    return {
        "resource_name": person.get("resourceName"),
        "name":  names[0].get("displayName") if names else None,
        "email": emails[0].get("value") if emails else None,
        "phone": phones[0].get("value") if phones else None,
        "all_emails": [e.get("value") for e in emails],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_contacts(query: str) -> list[dict]:
    """Search contacts by name or email. Returns list of projected contact dicts.

    Searches both personal contacts and Other Contacts (Gmail suggestions).
    Returns empty list if no matches; raises GTDError on API failure.
    """
    tracer = get_tracer("gtd.contacts")
    with tracer.start_as_current_span("gtd.contacts.search") as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("contacts.query_length", len(query))
        try:
            service = _people_service()

            def _call():
                return service.people().searchContacts(
                    query=query,
                    readMask=_PERSON_FIELDS,
                    pageSize=10,
                ).execute()

            result = _retry(_call)
            results = result.get("results", [])
            contacts = [_fmt_contact(r["person"]) for r in results if "person" in r]
            span.set_attribute("contacts.result_count", len(contacts))
            return contacts

        except GTDError:
            raise
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise GTDError(
                "contacts_api_error",
                f"Contacts search failed: {exc}",
                error_type=type(exc).__name__,
            ) from exc


def get_primary_email(name: str) -> str | None:
    """Return the primary email for the first contact matching name, or None.

    Used internally by create_event to resolve attendee names to emails.
    """
    results = search_contacts(name)
    if not results:
        return None
    return results[0].get("email")


def create_contact(name: str, email: str, phone: str | None = None) -> dict:
    """Create a new Google Contact with name, email, and optional phone.

    Returns the created contact as a projected dict.
    Raises GTDError on API failure or invalid input.
    """
    if not name or not name.strip():
        raise GTDError("missing_required_field", "name is required", field="name")
    if not email or "@" not in email:
        raise GTDError("invalid_email", f"Not a valid email address: {email!r}", email=email)

    tracer = get_tracer("gtd.contacts")
    with tracer.start_as_current_span("gtd.contacts.create") as span:
        span.set_attribute("agent.id", "gtd")
        try:
            service = _people_service()
            body: dict = {
                "names": [{"displayName": name, "givenName": name}],
                "emailAddresses": [{"value": email, "type": "work"}],
            }
            if phone:
                body["phoneNumbers"] = [{"value": phone, "type": "mobile"}]

            def _call():
                return service.people().createContact(
                    body=body,
                    personFields=_PERSON_FIELDS,
                ).execute()

            person = _retry(_call)
            contact = _fmt_contact(person)
            span.set_attribute("contacts.resource_name", contact.get("resource_name", ""))
            return contact

        except GTDError:
            raise
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise GTDError(
                "contacts_api_error",
                f"Contact creation failed: {exc}",
                error_type=type(exc).__name__,
            ) from exc
