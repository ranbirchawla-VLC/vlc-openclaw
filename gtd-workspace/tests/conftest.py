"""Pytest configuration: add tools/ to the import path for all tests.

Shared fixtures for GTD tool and integration tests.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import pytest
from common import append_jsonl, new_id, now_iso, user_path


# ---------------------------------------------------------------------------
# Storage isolation
# ---------------------------------------------------------------------------

@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect GTD_STORAGE_ROOT to a temporary directory for one test."""
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# User identity
# ---------------------------------------------------------------------------

@pytest.fixture
def user_a(storage: Path) -> str:
    return "user_alpha"


@pytest.fixture
def user_b(storage: Path) -> str:
    return "user_beta"


@pytest.fixture
def chat_a() -> str:
    return "chat_alpha_001"


@pytest.fixture
def chat_b() -> str:
    return "chat_beta_002"


# ---------------------------------------------------------------------------
# Record builder factories
# ---------------------------------------------------------------------------

@pytest.fixture
def make_task():
    """Return a factory that builds minimal pre-stamped valid task records."""
    def factory(user_id: str, chat_id: str, **kwargs) -> dict:
        ts = now_iso()
        base = {
            "id":               new_id(),
            "record_type":      "task",
            "user_id":          user_id,
            "telegram_chat_id": chat_id,
            "title":            "Do the thing",
            "context":          "@computer",
            "area":             "business",
            "priority":         "normal",
            "energy":           "medium",
            "duration_minutes": None,
            "status":           "active",
            "delegate_to":      None,
            "waiting_for":      None,
            "notes":            None,
            "source":           "telegram_text",
            "created_at":       ts,
            "updated_at":       ts,
            "completed_at":     None,
        }
        return {**base, **kwargs}
    return factory


@pytest.fixture
def make_idea():
    """Return a factory that builds minimal pre-stamped valid idea records."""
    def factory(user_id: str, chat_id: str, **kwargs) -> dict:
        ts = now_iso()
        base = {
            "id":               new_id(),
            "record_type":      "idea",
            "user_id":          user_id,
            "telegram_chat_id": chat_id,
            "title":            "Some idea",
            "domain":           "ai-automation",
            "context":          "@computer",
            "review_cadence":   "monthly",
            "promotion_state":  "raw",
            "spark_note":       None,
            "status":           "active",
            "source":           "telegram_text",
            "created_at":       ts,
            "updated_at":       ts,
            "last_reviewed_at": None,
            "promoted_task_id": None,
        }
        return {**base, **kwargs}
    return factory
