"""NutriOS v2 store — disk I/O, per-user path resolution, atomic writes.

All paths are built from data_root() / "users" / user_id / <constant>.
No path supplied by the LLM or user_text is ever trusted.
Write paths are atomic (write temp → fsync → os.replace).
JSONL files are append-only; no in-place rewrite ever occurs.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from nutrios_models import (
    Event, NeedsSetup, State, Recipe,
)


class StoreError(Exception):
    """Typed exception for store-layer failures. Always carries a named message."""


# ---------------------------------------------------------------------------
# Per-user lock table — prevents concurrent next_id collisions on same user
# ---------------------------------------------------------------------------

_user_locks: dict[str, threading.Lock] = {}
_lock_table_lock = threading.Lock()


def _user_lock(user_id: str) -> threading.Lock:
    with _lock_table_lock:
        if user_id not in _user_locks:
            _user_locks[user_id] = threading.Lock()
        return _user_locks[user_id]


# ---------------------------------------------------------------------------
# Path validation helpers
# ---------------------------------------------------------------------------

_VALID_USER_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_VALID_CYCLE_ID = re.compile(r"^[A-Za-z0-9_]+$")

_JSON_ALLOWLIST = frozenset({
    "profile.json",
    "goals.json",
    "protocol.json",
    "events.json",
    "recipes.json",
    "aliases.json",
    "portions.json",
    "state.json",
    "_needs_setup.json",
    "_migration_marker.json",
})

_JSONL_ALLOWLIST = frozenset({
    "weigh_ins.jsonl",
    "med_notes.jsonl",
})

_COUNTER_ALLOWLIST = frozenset({
    "last_entry_id",
    "last_weigh_in_id",
    "last_med_note_id",
    "last_event_id",
    "last_recipe_id",
})


def _validate_json_filename(filename: str) -> None:
    if filename in _JSON_ALLOWLIST:
        return
    # mesocycles/<cycle_id>.json
    if filename.startswith("mesocycles/"):
        tail = filename[len("mesocycles/"):]
        if tail.endswith(".json"):
            cycle_id = tail[:-5]
            if _VALID_CYCLE_ID.match(cycle_id):
                return
    raise ValueError(f"Filename not on allowlist: {filename!r}")


def _validate_jsonl_filename(filename: str) -> None:
    if filename in _JSONL_ALLOWLIST:
        return
    # log/YYYY-MM-DD.jsonl
    if filename.startswith("log/") and filename.endswith(".jsonl"):
        name = filename[4:-6]
        try:
            from datetime import date
            date.fromisoformat(name)
            return
        except ValueError:
            pass
    raise ValueError(f"JSONL filename not on allowlist: {filename!r}")


# ---------------------------------------------------------------------------
# Root and per-user path resolution
# ---------------------------------------------------------------------------

def data_root() -> Path:
    """Return the data root from NUTRIOS_DATA_ROOT env var. Raises if unset."""
    val = os.environ.get("NUTRIOS_DATA_ROOT")
    if not val:
        raise EnvironmentError("NUTRIOS_DATA_ROOT environment variable is not set")
    return Path(val)


def user_dir(user_id: str) -> Path:
    """Return per-user directory path. Validates user_id for safety."""
    if not user_id or not _VALID_USER_ID.match(user_id):
        raise ValueError(
            f"Invalid user_id {user_id!r}: must be non-empty, no path separators or whitespace"
        )
    return data_root() / "users" / user_id


# ---------------------------------------------------------------------------
# Atomic write helpers
# ---------------------------------------------------------------------------

def _atomic_write_text(dest: Path, content: str) -> None:
    """Write content to dest atomically via a temp file in the same directory."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dest.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, dest)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Index lookup
# ---------------------------------------------------------------------------

def resolve_user_id_from_peer(channel_peer: str) -> str:
    """Map a channel peer identifier to a user_id via _index/users.json.

    Security boundary: the only path that maps external identifiers to user_id.
    Does not validate the peer string itself — peer is an opaque lookup key.
    The returned user_id is validated downstream by user_dir().
    """
    index_path = data_root() / "_index" / "users.json"
    if not index_path.exists():
        raise StoreError(
            f"User index not initialized at {index_path}. "
            "Run scaffold or nutrios_migrate to create _index/users.json."
        )
    try:
        index = json.loads(index_path.read_text())
    except json.JSONDecodeError as exc:
        raise StoreError(f"Failed to parse _index/users.json: {exc}") from exc
    if not isinstance(index, dict):
        raise StoreError(
            f"_index/users.json must be a JSON object, got {type(index).__name__}"
        )
    if channel_peer not in index:
        raise StoreError(f"Channel peer {channel_peer!r} not in user index")
    resolved = index[channel_peer]
    if not isinstance(resolved, str):
        raise StoreError(
            f"Index entry for {channel_peer!r} must be a str user_id, "
            f"got {type(resolved).__name__!r}"
        )
    return resolved


# ---------------------------------------------------------------------------
# JSON read/write
# ---------------------------------------------------------------------------

def read_json(user_id: str, filename: str, model: type[BaseModel]) -> BaseModel | None:
    """Read a validated JSON file. Returns None if the file does not exist."""
    _validate_json_filename(filename)
    path = user_dir(user_id) / filename
    if not path.exists():
        return None
    return model.model_validate_json(path.read_text())


def write_json(user_id: str, filename: str, model: BaseModel) -> None:
    """Atomically write a Pydantic model as JSON."""
    _validate_json_filename(filename)
    dest = user_dir(user_id) / filename
    _atomic_write_text(dest, model.model_dump_json(indent=2))


def read_json_raw(user_id: str, filename: str) -> dict | None:
    """Read a JSON file as a raw dict, bypassing model validation.

    Used by setup_resume during migration Phase 2 when _pending_kcal scratch
    fields on day_patterns would be stripped by Pydantic's extra='forbid'.
    Filename is allowlisted via the same _validate_json_filename path.
    """
    _validate_json_filename(filename)
    path = user_dir(user_id) / filename
    if not path.exists():
        return None
    return json.loads(path.read_text())


def write_json_raw(user_id: str, filename: str, data: dict) -> None:
    """Atomically write a raw dict as JSON, bypassing model validation.

    Companion to read_json_raw — used to preserve scratch fields across
    setup_resume writes that the canonical model would otherwise strip.
    """
    _validate_json_filename(filename)
    dest = user_dir(user_id) / filename
    _atomic_write_text(dest, json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# JSONL append and read (Tripwire 2: no in-place rewrite)
# ---------------------------------------------------------------------------

def append_jsonl(user_id: str, filename: str, model: BaseModel) -> None:
    """Atomically append one JSON line to a JSONL file.

    Pattern: write existing content + new line to a temp file, then os.replace.
    This is the ONLY write path for JSONL files. No in-place rewrite ever.
    """
    _validate_jsonl_filename(filename)
    dest = user_dir(user_id) / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    new_line = model.model_dump_json() + "\n"

    fd, tmp_path = tempfile.mkstemp(dir=dest.parent)
    try:
        with os.fdopen(fd, "w") as f:
            if dest.exists():
                f.write(dest.read_text())
            f.write(new_line)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, dest)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_jsonl_batch(user_id: str, filename: str, models: list[BaseModel]) -> None:
    """Atomically write a JSONL file from a list of models in one shot.

    Companion to append_jsonl for migration's batch-write efficiency: append_jsonl
    rewrites the whole file once per record, which is O(N²) over N records.
    write_jsonl_batch serializes the full list once, writes via the same
    tempfile + fsync + os.replace primitive append_jsonl uses, then renames.

    Tripwire 2 atomicity is preserved: same path validation, same allowlist,
    same atomic-replace pattern. Distinct from append_jsonl in that this
    OVERWRITES whatever exists at the target path. Migration writes weigh_ins,
    med_notes, and daily logs from scratch into a fresh user dir; runtime keeps
    using append_jsonl. Mixing the two against the same file in a single run
    would overwrite earlier appends — callers must pick one mode per file.
    """
    _validate_jsonl_filename(filename)
    dest = user_dir(user_id) / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    if not models:
        content = ""
    else:
        content = "".join(m.model_dump_json() + "\n" for m in models)

    fd, tmp_path = tempfile.mkstemp(dir=dest.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, dest)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def tail_jsonl(user_id: str, filename: str, n: int) -> list[dict]:
    """Return last n lines of a JSONL file as parsed dicts."""
    _validate_jsonl_filename(filename)
    path = user_dir(user_id) / filename
    if not path.exists():
        return []
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    return [json.loads(line) for line in lines[-n:]]


def read_jsonl_all(user_id: str, filename: str) -> list[dict]:
    """Return every line of a JSONL file as parsed dicts.

    Companion to tail_jsonl. Per-user JSONL files are bounded — daily logs,
    weigh-ins, and med-notes accumulate slowly — so reading everything is
    safe in practice. Tools that need "all entries to date" use this rather
    than tail_jsonl with a magic-number n.
    """
    _validate_jsonl_filename(filename)
    path = user_dir(user_id) / filename
    if not path.exists():
        return []
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    return [json.loads(line) for line in lines]


# ---------------------------------------------------------------------------
# Events convenience wrappers
# ---------------------------------------------------------------------------

def read_events(user_id: str) -> list[Event]:
    """Read events.json and return the events list.

    Requires wrapped format: {"events": [...], "version": 1}.
    Raw-list format is rejected with a clear StoreError pointing at migration.
    Returns [] when the file does not exist.
    """
    path = user_dir(user_id) / "events.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise StoreError(f"Failed to parse events.json: {exc}") from exc
    if not isinstance(raw, dict) or "events" not in raw:
        raise StoreError(
            'events.json must use wrapped format {"events": [...], "version": 1}. '
            "If migrating from raw-list format, run nutrios_migrate."
        )
    return [Event.model_validate(e) for e in raw["events"]]


def write_events(user_id: str, events: list[Event]) -> None:
    """Atomically rewrite events.json in wrapped format (whole-file write is acceptable here)."""
    dest = user_dir(user_id) / "events.json"
    content = json.dumps(
        {"version": 1, "events": [e.model_dump(mode="json") for e in events]},
        indent=2,
    )
    _atomic_write_text(dest, content)


# ---------------------------------------------------------------------------
# Recipes convenience wrappers — wrapped format mirrors events.json
# ---------------------------------------------------------------------------

def read_recipes(user_id: str) -> list[Recipe]:
    """Read recipes.json and return the recipes list.

    Requires wrapped format: {"recipes": [...], "version": 1}.
    Returns [] when the file does not exist.
    """
    path = user_dir(user_id) / "recipes.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise StoreError(f"Failed to parse recipes.json: {exc}") from exc
    if not isinstance(raw, dict) or "recipes" not in raw:
        raise StoreError(
            'recipes.json must use wrapped format {"recipes": [...], "version": 1}.'
        )
    return [Recipe.model_validate(r) for r in raw["recipes"]]


def write_recipes(user_id: str, recipes: list[Recipe]) -> None:
    """Atomically rewrite recipes.json in wrapped format."""
    dest = user_dir(user_id) / "recipes.json"
    content = json.dumps(
        {"version": 1, "recipes": [r.model_dump(mode="json") for r in recipes]},
        indent=2,
    )
    _atomic_write_text(dest, content)


# ---------------------------------------------------------------------------
# Aliases — flat dict mapping case-insensitive alias → resolved name
# ---------------------------------------------------------------------------

def read_aliases(user_id: str) -> dict[str, str]:
    """Read aliases.json. Returns {} when file missing.

    Wrapped format: {"version": 1, "aliases": {alias: target}}.
    Legacy raw-dict format ({"alias": "target", ...}) is also accepted —
    aliases.json predates v2 in some workspaces, so the read path is
    permissive even though writes always use the wrapped form.
    """
    path = user_dir(user_id) / "aliases.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise StoreError(f"Failed to parse aliases.json: {exc}") from exc
    if not isinstance(raw, dict):
        raise StoreError(f"aliases.json must be a JSON object, got {type(raw).__name__}")
    if "aliases" in raw and isinstance(raw["aliases"], dict):
        return raw["aliases"]
    return raw  # legacy flat format


# ---------------------------------------------------------------------------
# Atomic counter increment
# ---------------------------------------------------------------------------

def next_id(
    user_id: str,
    counter: Literal["last_entry_id", "last_weigh_in_id", "last_med_note_id", "last_event_id", "last_recipe_id"],
) -> int:
    """Atomically increment a counter in state.json and return the new value."""
    if counter not in _COUNTER_ALLOWLIST:
        raise ValueError(f"Unknown counter: {counter!r}")
    with _user_lock(user_id):
        state_raw = read_json(user_id, "state.json", State)
        state = state_raw if state_raw is not None else State()
        new_val = getattr(state, counter) + 1
        updated = state.model_copy(update={counter: new_val})
        write_json(user_id, "state.json", updated)
    return new_val


# ---------------------------------------------------------------------------
# NeedsSetup helpers
# ---------------------------------------------------------------------------

def read_needs_setup(user_id: str) -> NeedsSetup:
    """Return NeedsSetup (all false) if the file is missing."""
    result = read_json(user_id, "_needs_setup.json", NeedsSetup)
    return result if result is not None else NeedsSetup()


def clear_needs_setup_marker(
    user_id: str,
    field: Literal["gallbladder", "tdee", "carbs_shape", "deficits", "nominal_deficit"],
) -> None:
    """Set a single setup marker to False. Atomic write."""
    current = read_needs_setup(user_id)
    updated = current.model_copy(update={field: False})
    write_json(user_id, "_needs_setup.json", updated)
