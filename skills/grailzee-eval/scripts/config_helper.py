"""Shared helpers for Grailzee config files.

Every strategy-writable config file in the Grailzee refactor follows the
no-nulls rule from grailzee_schema_design_v1_1.md Section 2: every field
has a concrete factory default at file creation, and a top-level
``defaulted_fields`` array of dotted paths tracks which fields are still
at their factory default vs. strategy-set.

This module is the library every config consumer routes through. Library
only — no CLI, no side-effects at import. Atomic write uses temp-file +
fsync + os.replace, with try/except cleanup of the temp on any failure
(the pattern backfill_ledger and roll_cycle have but without the
cleanup).

Scope: config files only. Data files (analysis_cache, trade_ledger,
cycle_outcome, shortlist) legitimately carry null and do not route
through this helper. Per v1.1 Section 2: "Config is what SHOULD; data
is what IS."

Public API:
- read_config(path)                         — load + validate schema_version present
- write_config(path, content, defaulted_fields, updated_by) — atomic write
- mark_field_set(path, field_path, updated_by)             — remove dotted path
- is_defaulted(config, field_path)          — bool check
- schema_version_or_fail(config, expected)  — version compatibility gate

Canonical Grailzee attributes (cycle_id, source_report, references_count,
trades_processed, brand_count) are out of scope for this module — none
of them apply to config-file operations. Span attributes are
config-specific: path, field_path, updated_by, defaulted_count,
schema_version, outcome.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
if str(V2_ROOT) not in sys.path:
    sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import get_tracer  # noqa: E402

tracer = get_tracer(__name__)

# Keys the helper manages on every write. Included in the emitted JSON
# at fixed positions; callers don't need to set them in ``content``.
MANAGED_KEYS: frozenset[str] = frozenset({"last_updated", "updated_by", "defaulted_fields"})


class NullNotAllowedError(ValueError):
    """A top-level config field was None on write_config.

    Carries ``field`` (the offending top-level key) for programmatic
    access; the str() carries the human-readable message.
    """

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


class SchemaVersionError(ValueError):
    """schema_version is missing, newer than expected, or malformed."""


def _now_iso_utc() -> str:
    """ISO 8601 UTC timestamp with 'Z' suffix. Matches manifest convention."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _sorted_unique(items: Iterable[str]) -> list[str]:
    """Dedupe + alphabetical sort. Raises if any item is not a string."""
    seen: list[str] = []
    as_set: set[str] = set()
    for i, item in enumerate(items):
        if not isinstance(item, str):
            raise ValueError(
                f"defaulted_fields[{i}] is {type(item).__name__}, expected str"
            )
        if item not in as_set:
            as_set.add(item)
            seen.append(item)
    return sorted(seen)


def _validate_no_top_level_nulls(content: dict) -> None:
    """Raise NullNotAllowedError if any top-level value in ``content`` is None.

    Per v1.1 Section 2 + task A.1 spec: the no-null check is top-level only.
    Nested null values inside data sections embedded in config files are
    out of scope for this helper — callers that embed data sections own
    their own validation.
    """
    for key, value in content.items():
        if value is None:
            raise NullNotAllowedError(
                field=key,
                message=(
                    f"Top-level config field {key!r} is None; "
                    f"config files must use concrete factory defaults, "
                    f"not null (v1.1 §2 no-nulls rule)."
                ),
            )


def _atomic_write_json(path: str, payload: dict) -> None:
    """Atomic JSON write: tmp + fsync + os.replace. Cleans tmp on failure.

    Creates parent directory if absent. Raises OSError on filesystem
    failure; the original file is left untouched in every failure mode.
    """
    target = os.path.abspath(path)
    parent = os.path.dirname(target) or "."
    os.makedirs(parent, exist_ok=True)
    tmp = target + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


# ─── Public API ──────────────────────────────────────────────────────


def read_config(path: str | os.PathLike) -> dict:
    """Load a config file and validate ``schema_version`` is present.

    Returns the parsed dict as-is; caller accesses fields directly. Use
    ``schema_version_or_fail`` to gate on a specific expected version,
    ``is_defaulted`` to query the ``defaulted_fields`` array.

    Raises:
        FileNotFoundError: path does not exist
        ValueError:        file is not valid JSON, top-level is not an object,
                           or schema_version is missing
    """
    with tracer.start_as_current_span("config_helper.read_config") as span:
        path_str = str(path)
        span.set_attribute("path", path_str)

        if not os.path.exists(path_str):
            span.set_attribute("outcome", "missing")
            raise FileNotFoundError(f"Config file not found: {path_str}")

        try:
            with open(path_str, "r", encoding="utf-8") as f:
                parsed: Any = json.load(f)
        except json.JSONDecodeError as exc:
            span.set_attribute("outcome", "malformed")
            raise ValueError(
                f"Config file {path_str} is not valid JSON: {exc}"
            ) from exc

        if not isinstance(parsed, dict):
            span.set_attribute("outcome", "malformed")
            raise ValueError(
                f"Config file {path_str} top-level must be a JSON object, "
                f"got {type(parsed).__name__}"
            )

        if "schema_version" not in parsed:
            span.set_attribute("outcome", "missing_schema_version")
            raise ValueError(
                f"Config file {path_str} is missing required 'schema_version' field"
            )

        span.set_attribute("schema_version", parsed["schema_version"])
        span.set_attribute(
            "defaulted_count", len(parsed.get("defaulted_fields", []) or [])
        )
        span.set_attribute("outcome", "ok")
        return parsed


def write_config(
    path: str | os.PathLike,
    content: dict,
    defaulted_fields: Iterable[str],
    updated_by: str,
) -> None:
    """Atomically write a config file.

    Stamps ``last_updated`` (now, ISO 8601 UTC with Z suffix) and
    ``updated_by`` into the emitted JSON. Writes ``defaulted_fields``
    alphabetically sorted and deduped.

    Validates before writing:
    - ``content`` is a dict containing ``schema_version``
    - No top-level value in ``content`` is None (v1.1 §2 no-nulls rule;
      nested data-section nulls are out of scope per task A.1 spec)
    - ``updated_by`` is a non-empty string
    - Every item in ``defaulted_fields`` is a string

    Any three managed keys (``last_updated``, ``updated_by``,
    ``defaulted_fields``) present in ``content`` are overridden by the
    explicit arguments — passing them in ``content`` is silently
    tolerated but does not take effect. This keeps call sites readable
    (the caller can pass a full parsed config back in without stripping
    managed fields).

    Raises:
        ValueError:             schema_version missing, updated_by empty,
                                defaulted_fields has non-strings
        NullNotAllowedError:    top-level field is None
        OSError:                filesystem failure during atomic write
    """
    with tracer.start_as_current_span("config_helper.write_config") as span:
        path_str = str(path)
        span.set_attribute("path", path_str)
        span.set_attribute("updated_by", updated_by)

        if not isinstance(content, dict):
            span.set_attribute("outcome", "bad_content_type")
            raise ValueError(
                f"write_config content must be a dict, got {type(content).__name__}"
            )
        if "schema_version" not in content:
            span.set_attribute("outcome", "missing_schema_version")
            raise ValueError(
                "write_config: content must include 'schema_version'"
            )
        if not isinstance(updated_by, str) or not updated_by.strip():
            span.set_attribute("outcome", "bad_updated_by")
            raise ValueError(
                "write_config: updated_by must be a non-empty string"
            )

        # Strip managed keys from the payload; we re-inject ours below.
        payload = {k: v for k, v in content.items() if k not in MANAGED_KEYS}

        try:
            _validate_no_top_level_nulls(payload)
        except NullNotAllowedError:
            span.set_attribute("outcome", "null_detected")
            raise

        try:
            sorted_fields = _sorted_unique(defaulted_fields)
        except ValueError:
            span.set_attribute("outcome", "bad_defaulted_fields")
            raise

        payload["last_updated"] = _now_iso_utc()
        payload["updated_by"] = updated_by
        payload["defaulted_fields"] = sorted_fields

        span.set_attribute("schema_version", payload["schema_version"])
        span.set_attribute("defaulted_count", len(sorted_fields))

        try:
            _atomic_write_json(path_str, payload)
        except OSError:
            span.set_attribute("outcome", "io_error")
            raise

        span.set_attribute("outcome", "ok")


def mark_field_set(
    path: str | os.PathLike,
    field_path: str,
    updated_by: str,
) -> None:
    """Remove ``field_path`` from the config's ``defaulted_fields`` array.

    Idempotent: if the field path is already absent (or ``defaulted_fields``
    itself is missing/empty), this is a no-op write that still updates
    ``last_updated`` and ``updated_by`` — on the theory that the strategy
    intent to set this field should be recorded even when the array state
    didn't change.

    The existing content on disk is preserved verbatim apart from the
    three managed keys.

    Raises:
        FileNotFoundError:  path does not exist
        ValueError:         file malformed, schema_version missing, bad field_path
        OSError:            filesystem failure during atomic write
    """
    with tracer.start_as_current_span("config_helper.mark_field_set") as span:
        path_str = str(path)
        span.set_attribute("path", path_str)
        span.set_attribute("field_path", field_path)
        span.set_attribute("updated_by", updated_by)

        if not isinstance(field_path, str) or not field_path.strip():
            span.set_attribute("outcome", "bad_field_path")
            raise ValueError(
                "mark_field_set: field_path must be a non-empty string"
            )

        current = read_config(path_str)
        existing = current.get("defaulted_fields") or []
        if not isinstance(existing, list):
            span.set_attribute("outcome", "bad_defaulted_fields")
            raise ValueError(
                f"Config file {path_str} has non-list 'defaulted_fields' "
                f"({type(existing).__name__})"
            )

        if field_path in existing:
            new_fields = [f for f in existing if f != field_path]
            was_present = True
        else:
            new_fields = list(existing)
            was_present = False

        span.set_attribute("was_present", was_present)

        write_config(
            path=path_str,
            content=current,
            defaulted_fields=new_fields,
            updated_by=updated_by,
        )

        span.set_attribute("outcome", "removed" if was_present else "absent")


def is_defaulted(config: dict, field_path: str) -> bool:
    """Return True if ``field_path`` is in ``config['defaulted_fields']``.

    Missing or non-list ``defaulted_fields`` is treated as empty
    (returns False). Consumers who need to distinguish "file is missing
    the array entirely" from "array is empty" should inspect ``config``
    directly.
    """
    with tracer.start_as_current_span("config_helper.is_defaulted") as span:
        span.set_attribute("field_path", field_path)
        fields = config.get("defaulted_fields") if isinstance(config, dict) else None
        if not isinstance(fields, list):
            span.set_attribute("outcome", "no_defaulted_fields")
            return False
        result = field_path in fields
        span.set_attribute("outcome", "defaulted" if result else "set")
        return result


def schema_version_or_fail(
    config: dict,
    expected_version: int,
) -> int:
    """Compatibility gate. Return the file's schema_version if readable by us.

    - If the file's version equals the expected version: return it.
    - If the file's version is OLDER than expected: return it. The caller
      is responsible for routing to a legacy parser or deciding that the
      old version is acceptable.
    - If the file's version is NEWER than expected: raise. A newer
      file was written by code that knows things we don't; parsing it
      with today's logic risks silent wrong answers.
    - If schema_version is missing or not an integer: raise.

    This function does not mutate anything.
    """
    with tracer.start_as_current_span("config_helper.schema_version_or_fail") as span:
        span.set_attribute("expected_version", expected_version)

        if not isinstance(config, dict):
            span.set_attribute("outcome", "bad_config_type")
            raise SchemaVersionError(
                f"schema_version_or_fail: config must be dict, "
                f"got {type(config).__name__}"
            )

        version = config.get("schema_version")
        if version is None:
            span.set_attribute("outcome", "missing")
            raise SchemaVersionError(
                "Config is missing required 'schema_version' field"
            )
        if not isinstance(version, int) or isinstance(version, bool):
            span.set_attribute("outcome", "bad_type")
            raise SchemaVersionError(
                f"schema_version must be int, got {type(version).__name__}"
            )

        span.set_attribute("schema_version", version)

        if version > expected_version:
            span.set_attribute("outcome", "newer")
            raise SchemaVersionError(
                f"Config schema_version={version} is newer than this "
                f"code supports (expected up to {expected_version}); "
                f"refusing to parse — upgrade the reader first."
            )

        span.set_attribute(
            "outcome",
            "match" if version == expected_version else "older",
        )
        return version


def defaulted_fields_of(config: dict) -> list[str]:
    """Convenience: return the config's defaulted_fields as a list.

    Missing or malformed entry yields ``[]``. This is not a validator —
    it's a safe accessor for consumers that want to iterate without
    checking the type themselves.
    """
    fields = config.get("defaulted_fields") if isinstance(config, dict) else None
    if not isinstance(fields, list):
        return []
    return [f for f in fields if isinstance(f, str)]


def leaf_paths(content: dict, *, prefix: str = "") -> list[str]:
    """Return every leaf dotted path in ``content``, excluding managed keys.

    Shared across Phase A installers so each of analyzer_config,
    brand_floors, sourcing_rules, etc. can populate ``defaulted_fields``
    uniformly. A leaf is a value that is not a dict. Managed keys
    (schema_version, last_updated, updated_by, defaulted_fields) are
    excluded because they are file-level metadata, not configurable
    fields that strategy commits.

    Paths are returned in insertion order; installers typically
    ``sorted()`` the result before writing.
    """
    paths: list[str] = []
    for key, value in content.items():
        if key in MANAGED_KEYS or key == "schema_version":
            continue
        dotted = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            paths.extend(leaf_paths(value, prefix=dotted))
        else:
            paths.append(dotted)
    return paths


# Optional sentinel kept for symmetric naming with the module's exports.
# The caller's code reads cleaner as
#   ``from scripts.config_helper import read_config, write_config, ...``
# so this sentinel is intentionally not a star-export gate.
__all__ = [
    "NullNotAllowedError",
    "SchemaVersionError",
    "read_config",
    "write_config",
    "mark_field_set",
    "is_defaulted",
    "schema_version_or_fail",
    "defaulted_fields_of",
    "leaf_paths",
]
