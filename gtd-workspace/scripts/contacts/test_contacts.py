"""Tests for contacts/contacts_api.py, search_contacts.py, create_contact.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

_here = Path(__file__).parent
sys.path.insert(0, str(_here))
sys.path.insert(0, str(_here.parent))

import otel_common


def _make_http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"error")


def _people_service_mock(results: list | None = None, created: dict | None = None) -> MagicMock:
    service = MagicMock()
    service.people.return_value.searchContacts.return_value.execute.return_value = {
        "results": results or []
    }
    service.people.return_value.createContact.return_value.execute.return_value = (
        created or {}
    )
    return service


def _person(
    name: str = "Heather VanHalen",
    email: str = "heather@example.com",
    resource_name: str = "people/123",
    company: str | None = None,
    title: str | None = None,
) -> dict:
    p: dict = {
        "resourceName": resource_name,
        "names": [{"displayName": name}],
        "emailAddresses": [{"value": email}],
        "phoneNumbers": [],
        "memberships": [],
    }
    if company or title:
        org: dict = {}
        if company:
            org["name"] = company
        if title:
            org["title"] = title
        p["organizations"] = [org]
    return p


# ---------------------------------------------------------------------------
# Test 1: search_contacts returns projected contacts
# ---------------------------------------------------------------------------

def test_search_contacts_returns_results() -> None:
    """search_contacts returns list of projected dicts on match."""
    from contacts_api import search_contacts

    person = _person()
    service = _people_service_mock(results=[{"person": person}])

    with patch("contacts_api.build", return_value=service), \
         patch("contacts_api.get_google_credentials", return_value=MagicMock()):
        results = search_contacts("Heather")

    assert len(results) == 1
    assert results[0]["name"] == "Heather VanHalen"
    assert results[0]["email"] == "heather@example.com"
    assert results[0]["resource_name"] == "people/123"


# ---------------------------------------------------------------------------
# Test 2: search_contacts returns empty list when no results
# ---------------------------------------------------------------------------

def test_search_contacts_empty() -> None:
    """search_contacts returns [] when no contacts match."""
    from contacts_api import search_contacts

    service = _people_service_mock(results=[])

    with patch("contacts_api.build", return_value=service), \
         patch("contacts_api.get_google_credentials", return_value=MagicMock()):
        results = search_contacts("Nobody")

    assert results == []


# ---------------------------------------------------------------------------
# Test 3: get_primary_email returns first email
# ---------------------------------------------------------------------------

def test_get_primary_email_found() -> None:
    """get_primary_email returns email when contact found."""
    from contacts_api import get_primary_email

    person = _person(email="heather@example.com")
    service = _people_service_mock(results=[{"person": person}])

    with patch("contacts_api.build", return_value=service), \
         patch("contacts_api.get_google_credentials", return_value=MagicMock()):
        email = get_primary_email("Heather VanHalen")

    assert email == "heather@example.com"


# ---------------------------------------------------------------------------
# Test 4: get_primary_email returns None when not found
# ---------------------------------------------------------------------------

def test_get_primary_email_not_found() -> None:
    """get_primary_email returns None when no contact found."""
    from contacts_api import get_primary_email

    service = _people_service_mock(results=[])

    with patch("contacts_api.build", return_value=service), \
         patch("contacts_api.get_google_credentials", return_value=MagicMock()):
        email = get_primary_email("Nobody Here")

    assert email is None


# ---------------------------------------------------------------------------
# Test 5: create_contact creates and returns contact
# ---------------------------------------------------------------------------

def test_create_contact_success() -> None:
    """create_contact creates contact and returns projected dict."""
    from contacts_api import create_contact

    created = _person(name="Marcus Lee", email="marcus@example.com",
                      resource_name="people/456")
    service = _people_service_mock(created=created)

    with patch("contacts_api.build", return_value=service), \
         patch("contacts_api.get_google_credentials", return_value=MagicMock()):
        contact = create_contact("Marcus Lee", "marcus@example.com")

    assert contact["name"] == "Marcus Lee"
    assert contact["email"] == "marcus@example.com"
    assert contact["resource_name"] == "people/456"


# ---------------------------------------------------------------------------
# Test 6: create_contact raises invalid_email on bad email
# ---------------------------------------------------------------------------

def test_create_contact_invalid_email() -> None:
    """GTDError('invalid_email') raised when email missing @."""
    from contacts_api import create_contact
    from common import GTDError

    with pytest.raises(GTDError) as exc_info:
        create_contact("Bob", "not-an-email")

    assert exc_info.value.code == "invalid_email"


# ---------------------------------------------------------------------------
# Test 7: search_contacts plugin tool main() round-trip
# ---------------------------------------------------------------------------

def test_search_contacts_tool_main(capsys) -> None:
    """search_contacts main() returns ok envelope with contacts list."""
    from search_contacts import main

    person = _person()
    service = _people_service_mock(results=[{"person": person}])
    args = json.dumps({"query": "Heather"})

    with patch("contacts_api.build", return_value=service), \
         patch("contacts_api.get_google_credentials", return_value=MagicMock()), \
         patch.object(sys, "argv", ["search_contacts.py", args]):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["data"]["total_count"] == 1
    assert output["data"]["contacts"][0]["name"] == "Heather VanHalen"


# ---------------------------------------------------------------------------
# Test 8: create_contact plugin tool main() round-trip
# ---------------------------------------------------------------------------

def test_create_contact_tool_main(capsys) -> None:
    """create_contact main() returns ok envelope with contact."""
    from create_contact import main

    created = _person(name="Marcus Lee", email="marcus@example.com")
    service = _people_service_mock(created=created)
    args = json.dumps({"name": "Marcus Lee", "email": "marcus@example.com"})

    with patch("contacts_api.build", return_value=service), \
         patch("contacts_api.get_google_credentials", return_value=MagicMock()), \
         patch.object(sys, "argv", ["create_contact.py", args]):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["data"]["contact"]["name"] == "Marcus Lee"


# ---------------------------------------------------------------------------
# Test 9: _fmt_contact surfaces company and title from organizations
# ---------------------------------------------------------------------------

def test_fmt_contact_surfaces_company_and_title() -> None:
    """_fmt_contact returns company and title when organizations present.

    Production failure: search results omit company/title; LLM cannot
    distinguish contacts with the same name at different companies.
    """
    from contacts_api import _fmt_contact

    person = _person(company="Acme Corp", title="VP Sales")
    contact = _fmt_contact(person)

    assert contact["company"] == "Acme Corp"
    assert contact["title"] == "VP Sales"


def test_fmt_contact_company_title_none_when_absent() -> None:
    """_fmt_contact returns None for company/title when organizations absent."""
    from contacts_api import _fmt_contact

    person = _person()
    contact = _fmt_contact(person)

    assert contact["company"] is None
    assert contact["title"] is None


# ---------------------------------------------------------------------------
# Test 10: create_contact passes company and title in API body
# ---------------------------------------------------------------------------

def test_create_contact_company_and_title_in_body() -> None:
    """company and title written to organizations[0] in People API body.

    Production failure: company/title silently dropped; contact created without org info.
    """
    from contacts_api import create_contact

    created = _person(name="Dana Cole", email="dana@example.com",
                      company="Riviera LLC", title="Director")
    service = _people_service_mock(created=created)

    with patch("contacts_api.build", return_value=service), \
         patch("contacts_api.get_google_credentials", return_value=MagicMock()):
        contact = create_contact(
            "Dana Cole", "dana@example.com",
            company="Riviera LLC", title="Director",
        )

    body = service.people.return_value.createContact.call_args.kwargs["body"]
    assert body["organizations"][0]["name"] == "Riviera LLC"
    assert body["organizations"][0]["title"] == "Director"
    assert contact["company"] == "Riviera LLC"
    assert contact["title"] == "Director"


# ---------------------------------------------------------------------------
# Test 11: phone_type and email_type respected
# ---------------------------------------------------------------------------

def test_create_contact_phone_and_email_type() -> None:
    """phone_type and email_type are written to the API body correctly.

    Production failure: all phones created as mobile, all emails as work
    regardless of user specification.
    """
    from contacts_api import create_contact

    created = _person(name="Test User", email="test@example.com")
    service = _people_service_mock(created=created)

    with patch("contacts_api.build", return_value=service), \
         patch("contacts_api.get_google_credentials", return_value=MagicMock()):
        create_contact(
            "Test User", "test@example.com",
            phone="555-1234",
            phone_type="work",
            email_type="home",
        )

    body = service.people.return_value.createContact.call_args.kwargs["body"]
    assert body["phoneNumbers"][0]["type"] == "work"
    assert body["emailAddresses"][0]["type"] == "home"


# ---------------------------------------------------------------------------
# Test 12: notes written as biographies
# ---------------------------------------------------------------------------

def test_create_contact_notes_written() -> None:
    """notes written to biographies[0] with TEXT_PLAIN contentType.

    Production failure: notes silently dropped; no way to attach context to a contact.
    """
    from contacts_api import create_contact

    created = _person()
    service = _people_service_mock(created=created)

    with patch("contacts_api.build", return_value=service), \
         patch("contacts_api.get_google_credentials", return_value=MagicMock()):
        create_contact("Test", "test@example.com", notes="Met at trade show 2026.")

    body = service.people.return_value.createContact.call_args.kwargs["body"]
    assert body["biographies"][0]["value"] == "Met at trade show 2026."
    assert body["biographies"][0]["contentType"] == "TEXT_PLAIN"


# ---------------------------------------------------------------------------
# Test 13: main() round-trip with all new fields
# ---------------------------------------------------------------------------

def test_create_contact_tool_main_full_fields(capsys) -> None:
    """main() accepts all new fields and threads them through to the API."""
    from create_contact import main

    created = _person(name="Dana Cole", email="dana@example.com",
                      company="Riviera LLC", title="Director")
    service = _people_service_mock(created=created)
    args = json.dumps({
        "name": "Dana Cole",
        "email": "dana@example.com",
        "phone": "303-555-0101",
        "first_name": "Dana",
        "last_name": "Cole",
        "company": "Riviera LLC",
        "title": "Director",
        "notes": "Met at Vegas summit.",
        "phone_type": "work",
        "email_type": "work",
    })

    with patch("contacts_api.build", return_value=service), \
         patch("contacts_api.get_google_credentials", return_value=MagicMock()), \
         patch.object(sys, "argv", ["create_contact.py", args]):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    contact = output["data"]["contact"]
    assert contact["company"] == "Riviera LLC"
    assert contact["title"] == "Director"
