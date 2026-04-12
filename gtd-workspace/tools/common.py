"""Common utilities for GTD pipeline tools.

Schema loading, path resolution, user-scoped JSONL I/O, and shared enums.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Source(str, Enum):
    telegram_text = "telegram_text"
    telegram_voice = "telegram_voice"
    alexa = "alexa"
    manual = "manual"
    import_ = "import"  # 'import' is a Python keyword; value is "import"


class TaskStatus(str, Enum):
    active = "active"
    waiting = "waiting"
    delegated = "delegated"
    done = "done"
    cancelled = "cancelled"
    archived = "archived"


class IdeaStatus(str, Enum):
    active = "active"
    on_hold = "on_hold"
    archived = "archived"
    promoted = "promoted"


class Priority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    critical = "critical"


class Energy(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ReviewCadence(str, Enum):
    weekly = "weekly"
    monthly = "monthly"
    quarterly = "quarterly"


class PromotionState(str, Enum):
    raw = "raw"
    incubating = "incubating"
    promoted_to_task = "promoted_to_task"
    promoted_to_project = "promoted_to_project"
    archived = "archived"


class ParkingLotReason(str, Enum):
    ambiguous_capture = "ambiguous_capture"
    missing_required_context = "missing_required_context"
    low_confidence_parse = "low_confidence_parse"


# ---------------------------------------------------------------------------
# Storage path resolution
# ---------------------------------------------------------------------------

_DEFAULT_STORAGE_ROOT = Path(__file__).parent.parent / "storage"


def storage_root() -> Path:
    """Return the GTD storage root from GTD_STORAGE_ROOT env var or default."""
    raw = os.environ.get("GTD_STORAGE_ROOT")
    if raw:
        return Path(raw)
    return _DEFAULT_STORAGE_ROOT


def user_path(user_id: str) -> Path:
    """Return the resolved storage path for a given user_id.

    Creates the directory tree if it does not exist.
    Raises ValueError for empty user_id.
    """
    if not user_id or not user_id.strip():
        raise ValueError("user_id must not be empty")
    path = storage_root() / "gtd-agent" / "users" / user_id
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# User isolation guard
# ---------------------------------------------------------------------------

def assert_user_match(record_user_id: str, requesting_user_id: str) -> None:
    """Raise ValueError if record_user_id does not match requesting_user_id."""
    if record_user_id != requesting_user_id:
        raise ValueError(
            f"User isolation violation: record belongs to '{record_user_id}', "
            f"not '{requesting_user_id}'"
        )


# ---------------------------------------------------------------------------
# JSONL I/O
# ---------------------------------------------------------------------------

def read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file and return a list of dicts.

    Returns an empty list if the file does not exist.
    """
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def append_jsonl(path: Path, record: dict) -> None:
    """Append a single dict as a JSON line to a JSONL file.

    Creates the file and parent directories if missing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# ID and timestamp helpers
# ---------------------------------------------------------------------------

def new_id() -> str:
    """Return a new UUID4 string."""
    return str(uuid.uuid4())


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()
