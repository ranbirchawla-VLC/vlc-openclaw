"""Hand-rolled validator for strategy_output_v1.json payloads.

The canonical spec lives at ``grailzee-cowork/schema/strategy_output_v1.json``
(JSON Schema 2020-12). This module implements the same rules in pure Python
with human-readable error messages keyed by dotted path. The JSON Schema
file is the reference for anyone wanting to validate externally; this is
the runtime validator.

Decision log:
- Hand-rolled rather than importing jsonschema. The schema is small enough
  that custom error messages beat jsonschema's default output, and there's
  value in staying on stdlib-only for a plugin that ships.
- Cross-field rules (at-least-one-non-null) aren't cleanly expressible in
  JSON Schema without workarounds; doing them in Python is clearer.
"""

from __future__ import annotations

import re
from typing import Any

SCHEMA_VERSION = 1
SESSION_MODES = {"cycle_planning", "monthly_review", "quarterly_allocation", "config_tuning"}
PRODUCED_BY_PREFIX = "grailzee-strategy/"

ISO_UTC_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z$"
)
CYCLE_ID_PATTERN = re.compile(r"^cycle_[0-9]{4}-[0-9]{2}$")
MONTH_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}$")
QUARTER_PATTERN = re.compile(r"^[0-9]{4}-Q[1-4]$")

CONFIG_SUB_KEYS = (
    "signal_thresholds",
    "scoring_thresholds",
    "momentum_thresholds",
    "window_config",
    "premium_config",
    "margin_config",
)

DECISION_KEYS = ("cycle_focus", "monthly_goals", "quarterly_allocation", "config_updates")

TOP_LEVEL_REQUIRED = (
    "strategy_output_version",
    "generated_at",
    "cycle_id",
    "session_mode",
    "produced_by",
    "decisions",
    "session_artifacts",
)


class StrategyOutputValidationError(ValueError):
    """Raised when a strategy_output.json payload fails validation."""


def _fail(path: str, reason: str) -> None:
    raise StrategyOutputValidationError(f"{path}: {reason}")


def _require_type(value: Any, expected: type | tuple[type, ...], path: str, desc: str) -> None:
    if not isinstance(value, expected):
        actual = type(value).__name__
        _fail(path, f"expected {desc}, got {actual}")


def _require_bool_not_int(value: Any, path: str) -> None:
    # bool is a subclass of int in Python; reject where we mean a number.
    if isinstance(value, bool):
        _fail(path, "expected number, got bool")


def _require_number(value: Any, path: str) -> None:
    _require_bool_not_int(value, path)
    if not isinstance(value, (int, float)):
        _fail(path, f"expected number, got {type(value).__name__}")


def _require_integer(value: Any, path: str) -> None:
    if isinstance(value, bool):
        _fail(path, "expected integer, got bool")
    if not isinstance(value, int):
        _fail(path, f"expected integer, got {type(value).__name__}")


def _require_string(value: Any, path: str, *, min_length: int = 0) -> None:
    if not isinstance(value, str):
        _fail(path, f"expected string, got {type(value).__name__}")
    if len(value) < min_length:
        _fail(path, f"string length {len(value)} < required min_length {min_length}")


def _require_object(value: Any, path: str) -> None:
    if not isinstance(value, dict):
        _fail(path, f"expected object, got {type(value).__name__}")


def _require_exact_keys(obj: dict[str, Any], allowed: tuple[str, ...], path: str) -> None:
    """All keys in ``allowed`` must be present; no extras allowed."""
    present = set(obj.keys())
    allowed_set = set(allowed)
    missing = allowed_set - present
    if missing:
        _fail(path, f"missing required keys: {sorted(missing)!r}")
    extra = present - allowed_set
    if extra:
        _fail(path, f"unknown keys rejected: {sorted(extra)!r}")


def _validate_target(entry: Any, path: str) -> None:
    _require_object(entry, path)
    _require_exact_keys(
        entry,
        ("reference", "brand", "model", "cycle_reason", "max_buy_override"),
        path,
    )
    _require_string(entry["reference"], f"{path}.reference", min_length=1)
    _require_string(entry["brand"], f"{path}.brand", min_length=1)
    _require_string(entry["model"], f"{path}.model", min_length=1)
    _require_string(entry["cycle_reason"], f"{path}.cycle_reason", min_length=1)
    mbo = entry["max_buy_override"]
    if mbo is not None:
        _require_number(mbo, f"{path}.max_buy_override")


def _validate_cycle_focus(section: Any, path: str) -> None:
    if section is None:
        return
    _require_object(section, path)
    _require_exact_keys(
        section,
        (
            "targets",
            "capital_target",
            "volume_target",
            "target_margin_fraction",
            "brand_emphasis",
            "brand_pullback",
            "notes",
        ),
        path,
    )
    targets = section["targets"]
    if not isinstance(targets, list):
        _fail(f"{path}.targets", f"expected array, got {type(targets).__name__}")
    if len(targets) < 1:
        _fail(f"{path}.targets", "targets must contain at least one entry")
    for i, t in enumerate(targets):
        _validate_target(t, f"{path}.targets[{i}]")

    capital = section["capital_target"]
    _require_number(capital, f"{path}.capital_target")
    if capital < 0:
        _fail(f"{path}.capital_target", f"must be >= 0, got {capital}")

    volume = section["volume_target"]
    _require_integer(volume, f"{path}.volume_target")
    if volume < 0:
        _fail(f"{path}.volume_target", f"must be >= 0, got {volume}")

    tmf = section["target_margin_fraction"]
    _require_number(tmf, f"{path}.target_margin_fraction")
    if not (0 < tmf < 1):
        _fail(
            f"{path}.target_margin_fraction",
            f"must be in (0, 1) exclusive; got {tmf}. "
            f"This field is a fraction (0.05 = 5%), not a percentage.",
        )

    for field_name in ("brand_emphasis", "brand_pullback"):
        arr = section[field_name]
        if not isinstance(arr, list):
            _fail(f"{path}.{field_name}", f"expected array, got {type(arr).__name__}")
        for i, v in enumerate(arr):
            _require_string(v, f"{path}.{field_name}[{i}]")

    _require_string(section["notes"], f"{path}.notes")


_MONTHLY_GOALS_REQUIRED = (
    "month", "revenue_target", "volume_target", "platform_mix", "focus_notes", "review_notes",
)
_MONTHLY_GOALS_OPTIONAL = ("monthly_return_pct",)


def _validate_monthly_goals(section: Any, path: str) -> None:
    if section is None:
        return
    _require_object(section, path)
    present = set(section.keys())
    missing = set(_MONTHLY_GOALS_REQUIRED) - present
    if missing:
        _fail(path, f"missing required keys: {sorted(missing)!r}")
    extra = present - set(_MONTHLY_GOALS_REQUIRED) - set(_MONTHLY_GOALS_OPTIONAL)
    if extra:
        _fail(path, f"unknown keys rejected: {sorted(extra)!r}")
    _require_string(section["month"], f"{path}.month", min_length=1)
    if not MONTH_PATTERN.match(section["month"]):
        _fail(f"{path}.month", f"must match ^[0-9]{{4}}-[0-9]{{2}}$, got {section['month']!r}")

    revenue = section["revenue_target"]
    _require_number(revenue, f"{path}.revenue_target")
    if revenue < 0:
        _fail(f"{path}.revenue_target", f"must be >= 0, got {revenue}")

    volume = section["volume_target"]
    _require_integer(volume, f"{path}.volume_target")
    if volume < 0:
        _fail(f"{path}.volume_target", f"must be >= 0, got {volume}")

    platform_mix = section["platform_mix"]
    _require_object(platform_mix, f"{path}.platform_mix")
    # Empty object is explicitly permitted (partial update).
    for platform, pct in platform_mix.items():
        sub_path = f"{path}.platform_mix[{platform!r}]"
        _require_number(pct, sub_path)
        if not (0 <= pct <= 100):
            _fail(sub_path, f"must be in [0, 100], got {pct}")

    _require_string(section["focus_notes"], f"{path}.focus_notes")
    _require_string(section["review_notes"], f"{path}.review_notes")

    mrp = section.get("monthly_return_pct")
    if mrp is not None:
        _require_number(mrp, f"{path}.monthly_return_pct")
        if not (0 < mrp < 1):
            _fail(
                f"{path}.monthly_return_pct",
                f"must be in (0, 1) exclusive; got {mrp}. "
                f"This field is a fraction (0.12 = 12%), not a percentage.",
            )


def _validate_quarterly_allocation(section: Any, path: str) -> None:
    if section is None:
        return
    _require_object(section, path)
    _require_exact_keys(
        section,
        ("quarter", "capital_allocation", "inventory_mix_target", "review_notes"),
        path,
    )
    _require_string(section["quarter"], f"{path}.quarter", min_length=1)
    if not QUARTER_PATTERN.match(section["quarter"]):
        _fail(f"{path}.quarter", f"must match ^[0-9]{{4}}-Q[1-4]$, got {section['quarter']!r}")

    capital = section["capital_allocation"]
    _require_object(capital, f"{path}.capital_allocation")
    for bucket, amount in capital.items():
        sub_path = f"{path}.capital_allocation[{bucket!r}]"
        _require_number(amount, sub_path)
        if amount < 0:
            _fail(sub_path, f"must be >= 0, got {amount}")

    inventory = section["inventory_mix_target"]
    _require_object(inventory, f"{path}.inventory_mix_target")
    for tier, pct in inventory.items():
        sub_path = f"{path}.inventory_mix_target[{tier!r}]"
        _require_number(pct, sub_path)
        if not (0 <= pct <= 100):
            _fail(sub_path, f"must be in [0, 100], got {pct}")

    _require_string(section["review_notes"], f"{path}.review_notes")


def _validate_config_sub_block(section: Any, path: str) -> None:
    if section is None:
        return
    _require_object(section, path)
    envelope = ("version", "updated_at", "updated_by", "notes")
    for field in envelope:
        if field not in section:
            _fail(path, f"missing required envelope key {field!r}")
    _require_integer(section["version"], f"{path}.version")
    if section["version"] < 1:
        _fail(f"{path}.version", f"must be >= 1, got {section['version']}")
    _require_string(section["updated_at"], f"{path}.updated_at", min_length=1)
    _require_string(section["updated_by"], f"{path}.updated_by", min_length=1)
    _require_string(section["notes"], f"{path}.notes")


def _validate_config_updates(section: Any, path: str) -> None:
    if section is None:
        return
    _require_object(section, path)
    _require_exact_keys(section, CONFIG_SUB_KEYS + ("change_notes",), path)
    non_null_subs = [k for k in CONFIG_SUB_KEYS if section[k] is not None]
    if not non_null_subs:
        _fail(
            path,
            f"at least one of {list(CONFIG_SUB_KEYS)!r} must be non-null; "
            f"omit config_updates entirely (set to null) if no config changes are intended",
        )
    for sub in CONFIG_SUB_KEYS:
        _validate_config_sub_block(section[sub], f"{path}.{sub}")
    _require_string(section["change_notes"], f"{path}.change_notes", min_length=1)


def _validate_decisions(section: Any, path: str) -> None:
    _require_object(section, path)
    _require_exact_keys(section, DECISION_KEYS, path)
    non_null = [k for k in DECISION_KEYS if section[k] is not None]
    if not non_null:
        _fail(
            path,
            f"at least one of {list(DECISION_KEYS)!r} must be non-null; "
            f"empty strategy output has nothing to apply",
        )
    _validate_cycle_focus(section["cycle_focus"], f"{path}.cycle_focus")
    _validate_monthly_goals(section["monthly_goals"], f"{path}.monthly_goals")
    _validate_quarterly_allocation(section["quarterly_allocation"], f"{path}.quarterly_allocation")
    _validate_config_updates(section["config_updates"], f"{path}.config_updates")


def _validate_session_artifacts(section: Any, path: str) -> None:
    _require_object(section, path)
    _require_exact_keys(section, ("cycle_brief_md",), path)
    _require_string(section["cycle_brief_md"], f"{path}.cycle_brief_md", min_length=1)


def validate_strategy_output(payload: Any) -> None:
    """Validate a strategy_output.json payload.

    Raises ``StrategyOutputValidationError`` with a dotted-path error
    message on the first failure. Returns None on success.
    """
    _require_object(payload, "$")
    _require_exact_keys(payload, TOP_LEVEL_REQUIRED, "$")

    if payload["strategy_output_version"] != SCHEMA_VERSION:
        _fail(
            "$.strategy_output_version",
            f"must be {SCHEMA_VERSION}, got {payload['strategy_output_version']!r}",
        )

    generated_at = payload["generated_at"]
    _require_string(generated_at, "$.generated_at", min_length=1)
    if not ISO_UTC_PATTERN.match(generated_at):
        _fail(
            "$.generated_at",
            f"must be ISO-8601 UTC with Z suffix (e.g. 2026-04-19T10:30:00Z), got {generated_at!r}",
        )

    cycle_id = payload["cycle_id"]
    _require_string(cycle_id, "$.cycle_id", min_length=1)
    if not CYCLE_ID_PATTERN.match(cycle_id):
        _fail("$.cycle_id", f"must match ^cycle_[0-9]{{4}}-[0-9]{{2}}$, got {cycle_id!r}")

    session_mode = payload["session_mode"]
    if session_mode not in SESSION_MODES:
        _fail(
            "$.session_mode",
            f"must be one of {sorted(SESSION_MODES)!r}, got {session_mode!r}",
        )

    produced_by = payload["produced_by"]
    _require_string(produced_by, "$.produced_by", min_length=1)
    if not produced_by.startswith(PRODUCED_BY_PREFIX):
        _fail(
            "$.produced_by",
            f"must start with {PRODUCED_BY_PREFIX!r}, got {produced_by!r}",
        )

    _validate_decisions(payload["decisions"], "$.decisions")
    _validate_session_artifacts(payload["session_artifacts"], "$.session_artifacts")
