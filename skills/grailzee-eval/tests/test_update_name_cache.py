"""Tests for scripts.update_name_cache."""

import json
from pathlib import Path

import pytest

from scripts.update_name_cache import _Entry, _run_from_dict, run


def _cache_path(tmp_path: Path) -> str:
    return str(tmp_path / "name_cache.json")


class TestRun:
    def test_writes_new_entry(self, tmp_path):
        path = _cache_path(tmp_path)
        entries = [_Entry(reference="126610LN", brand="Rolex", model="Submariner Date")]
        result = run(entries, path)

        assert result == {"status": "ok", "written": 1, "skipped": 0}
        cache = json.loads(Path(path).read_text())
        assert cache["126610LN"] == {"brand": "Rolex", "model": "Submariner Date"}

    def test_skips_existing_entry(self, tmp_path):
        path = _cache_path(tmp_path)
        Path(path).write_text(json.dumps({"126610LN": {"brand": "Rolex", "model": "Submariner Date"}}))

        entries = [_Entry(reference="126610LN", brand="Rolex", model="Submariner Date")]
        result = run(entries, path)

        assert result == {"status": "ok", "written": 0, "skipped": 1}

    def test_batch_mixed_new_and_existing(self, tmp_path):
        path = _cache_path(tmp_path)
        Path(path).write_text(json.dumps({"116900": {"brand": "Rolex", "model": "Air-King"}}))

        entries = [
            _Entry(reference="116900", brand="Rolex", model="Air-King"),
            _Entry(reference="126610LN", brand="Rolex", model="Submariner Date"),
        ]
        result = run(entries, path)

        assert result["written"] == 1
        assert result["skipped"] == 1
        cache = json.loads(Path(path).read_text())
        assert "126610LN" in cache
        assert "116900" in cache

    def test_writes_alt_refs_when_provided(self, tmp_path):
        path = _cache_path(tmp_path)
        entries = [_Entry(reference="79830RB", brand="Tudor", model="BB GMT Pepsi", alt_refs=["M79830RB"])]
        run(entries, path)

        cache = json.loads(Path(path).read_text())
        assert cache["79830RB"]["alt_refs"] == ["M79830RB"]

    def test_no_alt_refs_key_when_absent(self, tmp_path):
        path = _cache_path(tmp_path)
        entries = [_Entry(reference="126610LN", brand="Rolex", model="Submariner Date")]
        run(entries, path)

        cache = json.loads(Path(path).read_text())
        assert "alt_refs" not in cache["126610LN"]

    def test_empty_entries_list(self, tmp_path):
        path = _cache_path(tmp_path)
        result = run([], path)
        assert result == {"status": "ok", "written": 0, "skipped": 0}

    def test_creates_cache_file_when_missing(self, tmp_path):
        path = _cache_path(tmp_path)
        assert not Path(path).exists()
        entries = [_Entry(reference="126610LN", brand="Rolex", model="Submariner Date")]
        run(entries, path)
        assert Path(path).exists()

    def test_does_not_write_file_when_nothing_new(self, tmp_path):
        path = _cache_path(tmp_path)
        Path(path).write_text(json.dumps({"126610LN": {"brand": "Rolex", "model": "Submariner Date"}}))
        mtime_before = Path(path).stat().st_mtime

        entries = [_Entry(reference="126610LN", brand="Rolex", model="Submariner Date")]
        run(entries, path)

        assert Path(path).stat().st_mtime == mtime_before


class TestRunFromDict:
    def test_happy_path(self, tmp_path, capsys):
        path = _cache_path(tmp_path)
        rc = _run_from_dict({
            "entries": [{"reference": "126610LN", "brand": "Rolex", "model": "Submariner Date"}],
            "name_cache_path": path,
        })
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["status"] == "ok"
        assert out["written"] == 1

    def test_missing_entries_field(self, capsys):
        rc = _run_from_dict({})
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["status"] == "error"
        assert out["error_type"] == "missing_arg"

    def test_entry_missing_required_field(self, tmp_path, capsys):
        path = _cache_path(tmp_path)
        rc = _run_from_dict({
            "entries": [{"reference": "126610LN", "brand": "Rolex"}],
            "name_cache_path": path,
        })
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["status"] == "error"
        assert out["error_type"] == "missing_arg"

    def test_unknown_field_rejected(self, tmp_path, capsys):
        path = _cache_path(tmp_path)
        rc = _run_from_dict({
            "entries": [],
            "name_cache_path": path,
            "unknown_field": "x",
        })
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["status"] == "error"
        assert out["error_type"] == "bad_input"

    def test_ok_envelope_exact_keys(self, tmp_path, capsys):
        """ok envelope is exactly {status, written, skipped}."""
        path = _cache_path(tmp_path)
        _run_from_dict({"entries": [], "name_cache_path": path})
        out = json.loads(capsys.readouterr().out)
        assert set(out.keys()) == {"status", "written", "skipped"}
