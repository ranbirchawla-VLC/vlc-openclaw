"""Tests for scripts.config_helper — the shared config-file helper.

Covers the five public entry points (read_config, write_config,
mark_field_set, is_defaulted, schema_version_or_fail) plus the atomic
write primitive's behaviour on failure.

Fixtures are real-feeling: a brand_floors-shaped config with a couple
of entries and a defaulted_fields array. Tests run via the workspace
pytest.ini.
"""

from __future__ import annotations

import json
import os

import pytest

from scripts.config_helper import (
    MANAGED_KEYS,
    NullNotAllowedError,
    SchemaVersionError,
    defaulted_fields_of,
    is_defaulted,
    mark_field_set,
    read_config,
    schema_version_or_fail,
    write_config,
)


# ───────────────────────────────────────────────────────────────────────
# Fixture helpers
# ───────────────────────────────────────────────────────────────────────


def _fixture_content() -> dict:
    """A brand_floors-shaped config. Top-level fields are all non-null
    (nested data sections may legitimately carry nested dicts, but
    nothing at top level is ever None)."""
    return {
        "schema_version": 1,
        "brands": {
            "Rolex": {"floor_pct": 5.0, "tradeable": True, "asset_class": "watch"},
            "Tudor": {"floor_pct": 10.0, "tradeable": True, "asset_class": "watch"},
        },
    }


def _default_fields() -> list[str]:
    return ["brands.Rolex.floor_pct", "brands.Tudor.floor_pct"]


def _write_fixture(tmp_path, *, content=None, defaulted_fields=None, updated_by="test"):
    p = tmp_path / "brand_floors.json"
    write_config(
        p,
        content or _fixture_content(),
        defaulted_fields if defaulted_fields is not None else _default_fields(),
        updated_by,
    )
    return p


# ═══════════════════════════════════════════════════════════════════════
# 1. read_config
# ═══════════════════════════════════════════════════════════════════════


class TestReadConfig:
    def test_happy_path(self, tmp_path):
        p = _write_fixture(tmp_path)
        c = read_config(p)
        assert c["schema_version"] == 1
        assert c["brands"]["Rolex"]["floor_pct"] == 5.0
        assert c["defaulted_fields"] == sorted(_default_fields())
        assert c["updated_by"] == "test"
        assert c["last_updated"].endswith("Z")

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="not found"):
            read_config(tmp_path / "nope.json")

    def test_malformed_json_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid JSON"):
            read_config(p)

    def test_missing_schema_version_raises(self, tmp_path):
        p = tmp_path / "no_sv.json"
        p.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
        with pytest.raises(ValueError, match="schema_version"):
            read_config(p)

    def test_top_level_not_object_raises(self, tmp_path):
        p = tmp_path / "list.json"
        p.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
        with pytest.raises(ValueError, match="must be a JSON object"):
            read_config(p)

    def test_accepts_empty_defaulted_fields(self, tmp_path):
        p = _write_fixture(tmp_path, defaulted_fields=[])
        c = read_config(p)
        assert c["defaulted_fields"] == []


# ═══════════════════════════════════════════════════════════════════════
# 2. write_config — round-trip + validation + atomicity
# ═══════════════════════════════════════════════════════════════════════


class TestWriteConfigRoundTrip:
    def test_round_trip_integrity(self, tmp_path):
        original = _fixture_content()
        p = _write_fixture(tmp_path, content=original, updated_by="round_trip_test")
        restored = read_config(p)
        # Everything from content is present, unmutated
        assert restored["schema_version"] == 1
        assert restored["brands"] == original["brands"]
        # Managed fields are stamped in
        assert restored["updated_by"] == "round_trip_test"
        assert restored["last_updated"].endswith("Z")

    def test_last_updated_is_iso8601_utc_with_z(self, tmp_path):
        p = _write_fixture(tmp_path)
        c = read_config(p)
        stamp = c["last_updated"]
        # Format: YYYY-MM-DDTHH:MM:SSZ (no fractional, no +00:00)
        assert stamp.endswith("Z")
        assert "T" in stamp
        assert "+" not in stamp

    def test_defaulted_fields_are_sorted(self, tmp_path):
        p = _write_fixture(
            tmp_path,
            defaulted_fields=["zeta", "alpha", "mu"],
        )
        c = read_config(p)
        assert c["defaulted_fields"] == ["alpha", "mu", "zeta"]

    def test_defaulted_fields_deduped(self, tmp_path):
        p = _write_fixture(
            tmp_path,
            defaulted_fields=["alpha", "beta", "alpha"],
        )
        c = read_config(p)
        assert c["defaulted_fields"] == ["alpha", "beta"]

    def test_empty_defaulted_fields_is_valid(self, tmp_path):
        p = _write_fixture(tmp_path, defaulted_fields=[])
        c = read_config(p)
        assert c["defaulted_fields"] == []

    def test_managed_keys_in_content_are_overridden(self, tmp_path):
        # Caller passed stale managed keys in content; write_config
        # must strip them and re-inject its own values.
        stale = {
            "schema_version": 1,
            "last_updated": "1999-01-01T00:00:00Z",
            "updated_by": "stale",
            "defaulted_fields": ["old"],
            "brands": {},
        }
        p = tmp_path / "managed.json"
        write_config(p, stale, defaulted_fields=["fresh"], updated_by="fresh_caller")
        c = read_config(p)
        assert c["last_updated"] != "1999-01-01T00:00:00Z"
        assert c["updated_by"] == "fresh_caller"
        assert c["defaulted_fields"] == ["fresh"]

    def test_creates_parent_dir(self, tmp_path):
        nested = tmp_path / "nested" / "deeper" / "brand_floors.json"
        write_config(nested, _fixture_content(), _default_fields(), "nested_test")
        assert nested.exists()


class TestWriteConfigValidation:
    def test_top_level_null_raises(self, tmp_path):
        bad = {"schema_version": 1, "brands": {}, "foo": None}
        p = tmp_path / "null.json"
        with pytest.raises(NullNotAllowedError) as exc_info:
            write_config(p, bad, [], "null_test")
        assert exc_info.value.field == "foo"
        assert "foo" in str(exc_info.value)
        # File must NOT have been created
        assert not p.exists()

    def test_nested_null_is_permitted(self, tmp_path):
        # v1.1 §2 exempts data sections inside config files. Per task A.1,
        # the helper's check is top-level only.
        nested_null = {
            "schema_version": 1,
            "brands": {"Rolex": {"realized_premium_pct": None}},
        }
        p = tmp_path / "nested_null.json"
        write_config(p, nested_null, [], "nested_null_test")
        c = read_config(p)
        assert c["brands"]["Rolex"]["realized_premium_pct"] is None

    def test_missing_schema_version_raises(self, tmp_path):
        bad = {"brands": {}}
        p = tmp_path / "no_sv.json"
        with pytest.raises(ValueError, match="schema_version"):
            write_config(p, bad, [], "sv_test")
        assert not p.exists()

    def test_non_dict_content_raises(self, tmp_path):
        p = tmp_path / "nondict.json"
        with pytest.raises(ValueError, match="must be a dict"):
            write_config(p, ["not", "a", "dict"], [], "nondict_test")
        assert not p.exists()

    def test_empty_updated_by_raises(self, tmp_path):
        p = tmp_path / "empty_updater.json"
        with pytest.raises(ValueError, match="updated_by"):
            write_config(p, _fixture_content(), [], "")
        with pytest.raises(ValueError, match="updated_by"):
            write_config(p, _fixture_content(), [], "   ")
        assert not p.exists()

    def test_non_string_in_defaulted_fields_raises(self, tmp_path):
        p = tmp_path / "bad_fields.json"
        with pytest.raises(ValueError, match="defaulted_fields"):
            write_config(p, _fixture_content(), ["alpha", 42, "beta"], "test")
        assert not p.exists()


class TestWriteConfigAtomicity:
    """The atomic write strategy is: write to <path>.tmp, fsync, os.replace.
    On any exception, the tmp file is cleaned up and the original path is
    left untouched."""

    def test_original_preserved_on_null_detection(self, tmp_path):
        p = _write_fixture(tmp_path, updated_by="v1")
        before = p.read_bytes()
        with pytest.raises(NullNotAllowedError):
            write_config(
                p,
                {"schema_version": 1, "oops": None, "brands": {}},
                [],
                "v2",
            )
        # Original file is byte-identical
        assert p.read_bytes() == before

    def test_no_orphan_tmp_file_on_failure(self, tmp_path):
        p = _write_fixture(tmp_path)
        # Cause failure at a later stage: invalid defaulted_fields item
        with pytest.raises(ValueError, match="defaulted_fields"):
            write_config(p, _fixture_content(), ["ok", 42], "test")
        assert not (tmp_path / "brand_floors.json.tmp").exists()

    def test_tmp_file_cleaned_on_atomic_write_failure(self, tmp_path, monkeypatch):
        """Inject os.replace failure mid-write; confirm tmp is cleaned up."""
        import scripts.config_helper as ch

        original_replace = os.replace
        calls: list[tuple] = []

        def failing_replace(src, dst):
            calls.append((src, dst))
            raise OSError("simulated replace failure")

        monkeypatch.setattr(ch.os, "replace", failing_replace)

        p = tmp_path / "boom.json"
        with pytest.raises(OSError, match="simulated"):
            write_config(p, _fixture_content(), _default_fields(), "boom_test")
        # os.replace was attempted
        assert calls
        # tmp file was cleaned
        assert not (tmp_path / "boom.json.tmp").exists()
        # Real file never appeared
        assert not p.exists()

    def test_atomic_write_uses_tmp_path_naming(self, tmp_path):
        """Runtime smoke: a successful write leaves no tmp behind."""
        p = tmp_path / "brand_floors.json"
        write_config(p, _fixture_content(), _default_fields(), "smoke")
        assert p.exists()
        assert not (tmp_path / "brand_floors.json.tmp").exists()


# ═══════════════════════════════════════════════════════════════════════
# 3. mark_field_set
# ═══════════════════════════════════════════════════════════════════════


class TestMarkFieldSet:
    def test_removes_present_path(self, tmp_path):
        p = _write_fixture(tmp_path)
        mark_field_set(p, "brands.Rolex.floor_pct", updated_by="strategy_sets_rolex")
        c = read_config(p)
        assert "brands.Rolex.floor_pct" not in c["defaulted_fields"]
        assert "brands.Tudor.floor_pct" in c["defaulted_fields"]

    def test_idempotent_on_absent_path(self, tmp_path):
        p = _write_fixture(tmp_path, defaulted_fields=["brands.Rolex.floor_pct"])
        mark_field_set(p, "brands.Tudor.floor_pct", updated_by="strategy")
        c = read_config(p)
        # Original path still present, absent target did nothing to the list
        assert c["defaulted_fields"] == ["brands.Rolex.floor_pct"]

    def test_updates_last_updated_and_updated_by_even_when_absent(self, tmp_path):
        p = _write_fixture(tmp_path, defaulted_fields=[], updated_by="install")
        before = read_config(p)
        mark_field_set(p, "not.there", updated_by="strategy_touched_anyway")
        after = read_config(p)
        assert after["updated_by"] == "strategy_touched_anyway"
        # last_updated changed (both have Z-suffix ISO stamps)
        assert after["last_updated"] >= before["last_updated"]

    def test_removes_last_remaining_path_yields_empty_array(self, tmp_path):
        p = _write_fixture(tmp_path, defaulted_fields=["only.one"])
        mark_field_set(p, "only.one", updated_by="strategy")
        c = read_config(p)
        assert c["defaulted_fields"] == []

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mark_field_set(
                tmp_path / "nope.json", "some.field", updated_by="test"
            )

    def test_empty_field_path_raises(self, tmp_path):
        p = _write_fixture(tmp_path)
        with pytest.raises(ValueError, match="field_path"):
            mark_field_set(p, "", updated_by="test")
        with pytest.raises(ValueError, match="field_path"):
            mark_field_set(p, "   ", updated_by="test")

    def test_non_list_defaulted_fields_raises(self, tmp_path):
        """Hand-crafted corrupt file with defaulted_fields as something
        other than a list. The helper should refuse rather than overwrite."""
        p = tmp_path / "corrupt.json"
        p.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "last_updated": "2026-04-21T00:00:00Z",
                    "updated_by": "corrupt",
                    "defaulted_fields": "not_a_list",
                    "brands": {},
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="non-list"):
            mark_field_set(p, "whatever", updated_by="test")

    def test_atomic_no_tmp_left_behind(self, tmp_path):
        p = _write_fixture(tmp_path)
        mark_field_set(p, "brands.Rolex.floor_pct", updated_by="strategy")
        # No tmp file after successful mark
        assert not any(
            name.endswith(".tmp") for name in os.listdir(tmp_path)
        )


# ═══════════════════════════════════════════════════════════════════════
# 4. is_defaulted
# ═══════════════════════════════════════════════════════════════════════


class TestIsDefaulted:
    def test_true_when_present(self):
        config = {"defaulted_fields": ["a.b", "c.d"]}
        assert is_defaulted(config, "a.b") is True

    def test_false_when_absent(self):
        config = {"defaulted_fields": ["a.b"]}
        assert is_defaulted(config, "x.y") is False

    def test_missing_defaulted_fields_returns_false(self):
        config = {"schema_version": 1}
        assert is_defaulted(config, "a.b") is False

    def test_non_list_defaulted_fields_returns_false(self):
        config = {"defaulted_fields": "oops"}
        assert is_defaulted(config, "a.b") is False

    def test_empty_list_returns_false(self):
        config = {"defaulted_fields": []}
        assert is_defaulted(config, "a.b") is False

    def test_non_dict_config_returns_false(self):
        assert is_defaulted(None, "a.b") is False
        assert is_defaulted([], "a.b") is False


# ═══════════════════════════════════════════════════════════════════════
# 5. schema_version_or_fail
# ═══════════════════════════════════════════════════════════════════════


class TestSchemaVersionOrFail:
    def test_matching_version(self):
        assert schema_version_or_fail({"schema_version": 1}, 1) == 1

    def test_older_version_returned(self):
        assert schema_version_or_fail({"schema_version": 1}, 2) == 1

    def test_newer_version_raises(self):
        with pytest.raises(SchemaVersionError, match="newer than this code"):
            schema_version_or_fail({"schema_version": 3}, 2)

    def test_missing_version_raises(self):
        with pytest.raises(SchemaVersionError, match="missing"):
            schema_version_or_fail({"brands": {}}, 1)

    def test_none_version_raises(self):
        with pytest.raises(SchemaVersionError, match="missing"):
            schema_version_or_fail({"schema_version": None}, 1)

    def test_non_int_version_raises(self):
        with pytest.raises(SchemaVersionError, match="must be int"):
            schema_version_or_fail({"schema_version": "1"}, 1)

    def test_bool_version_rejected(self):
        # True is an int in Python; protect against it accidentally passing.
        with pytest.raises(SchemaVersionError, match="must be int"):
            schema_version_or_fail({"schema_version": True}, 1)

    def test_non_dict_config_raises(self):
        with pytest.raises(SchemaVersionError, match="must be dict"):
            schema_version_or_fail(None, 1)


# ═══════════════════════════════════════════════════════════════════════
# 6. defaulted_fields_of (convenience accessor)
# ═══════════════════════════════════════════════════════════════════════


class TestDefaultedFieldsOf:
    def test_returns_list(self):
        assert defaulted_fields_of({"defaulted_fields": ["a", "b"]}) == ["a", "b"]

    def test_missing_returns_empty(self):
        assert defaulted_fields_of({}) == []

    def test_non_list_returns_empty(self):
        assert defaulted_fields_of({"defaulted_fields": "oops"}) == []

    def test_filters_non_strings(self):
        assert defaulted_fields_of({"defaulted_fields": ["a", 42, "b", None]}) == ["a", "b"]

    def test_non_dict_returns_empty(self):
        assert defaulted_fields_of(None) == []


# ═══════════════════════════════════════════════════════════════════════
# 7. Module constants sanity
# ═══════════════════════════════════════════════════════════════════════


def test_managed_keys_contents():
    assert MANAGED_KEYS == {"last_updated", "updated_by", "defaulted_fields"}
