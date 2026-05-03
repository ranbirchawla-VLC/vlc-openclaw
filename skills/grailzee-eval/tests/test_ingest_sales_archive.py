"""Tests for archive_jsonl (design v1 §12, sub-step 1.6).

Fixtures use ISO-dash date filenames (watchtrack_YYYY-MM-DD.jsonl) so that
_TRAILING_N never fires on the fixture name itself. The suffix after the last
underscore in an ISO date contains hyphens, not pure digits, so the regex
does not match and _next_archive_path always starts from _2.
"""

import errno
from pathlib import Path

import pytest

from scripts.ingest_sales import ArchiveMoveFailed, archive_jsonl


# ─── Helpers ─────────────────────────────────────────────────────────


def _write(path: Path, content: str = '{"sales":[],"purchases":[]}') -> Path:
    path.write_text(content)
    return path


# Realistic ISO-date filename used across most tests. Stem watchtrack_2026-04-29
# ends in "-29" (not "_29"), so _TRAILING_N does not match.
_FNAME = "watchtrack_2026-04-29.jsonl"
_FNAME2 = "watchtrack_2026-04-30.jsonl"


# ─── Clean move ──────────────────────────────────────────────────────


class TestArchiveJsonlCleanMove:
    def test_moves_file_to_archive_dir(self, tmp_path):
        src = _write(tmp_path / _FNAME)
        archive = tmp_path / "archive"
        archive_jsonl(src, archive)
        assert not src.exists()
        assert (archive / _FNAME).exists()

    def test_returns_destination_path(self, tmp_path):
        src = _write(tmp_path / _FNAME)
        archive = tmp_path / "archive"
        dest = archive_jsonl(src, archive)
        assert dest == archive / _FNAME

    def test_moved_file_preserves_content(self, tmp_path):
        payload = '{"sales":[{"id":1}],"purchases":[]}'
        src = _write(tmp_path / _FNAME, payload)
        archive = tmp_path / "archive"
        dest = archive_jsonl(src, archive)
        assert dest.read_text() == payload

    def test_creates_archive_dir_when_absent(self, tmp_path):
        src = _write(tmp_path / _FNAME)
        archive = tmp_path / "archive"
        assert not archive.exists()
        archive_jsonl(src, archive)
        assert archive.is_dir()

    def test_creates_nested_archive_dir(self, tmp_path):
        src = _write(tmp_path / _FNAME)
        archive = tmp_path / "deep" / "nested" / "archive"
        archive_jsonl(src, archive)
        assert archive.is_dir()

    def test_tolerates_existing_archive_dir(self, tmp_path):
        src = _write(tmp_path / _FNAME)
        archive = tmp_path / "archive"
        archive.mkdir()
        archive_jsonl(src, archive)
        assert (archive / _FNAME).exists()


# ─── Idempotent skip ─────────────────────────────────────────────────


class TestIdempotentSkip:
    def test_removes_source_when_content_matches(self, tmp_path):
        src = _write(tmp_path / _FNAME, "same")
        archive = tmp_path / "archive"
        archive.mkdir()
        _write(archive / _FNAME, "same")
        archive_jsonl(src, archive)
        assert not src.exists()

    def test_returns_existing_archive_path(self, tmp_path):
        src = _write(tmp_path / _FNAME, "same")
        archive = tmp_path / "archive"
        archive.mkdir()
        existing = _write(archive / _FNAME, "same")
        dest = archive_jsonl(src, archive)
        assert dest == existing

    def test_archive_content_unchanged(self, tmp_path):
        src = _write(tmp_path / _FNAME, "same")
        archive = tmp_path / "archive"
        archive.mkdir()
        _write(archive / _FNAME, "same")
        archive_jsonl(src, archive)
        assert (archive / _FNAME).read_text() == "same"

    def test_info_log_emitted(self, tmp_path, caplog):
        import logging
        src = _write(tmp_path / _FNAME, "same")
        archive = tmp_path / "archive"
        archive.mkdir()
        _write(archive / _FNAME, "same")
        with caplog.at_level(logging.INFO, logger="scripts.ingest_sales"):
            archive_jsonl(src, archive)
        assert any("Idempotent archive" in r.message for r in caplog.records)
        assert any(_FNAME in r.message for r in caplog.records)


# ─── Collision suffix ─────────────────────────────────────────────────


class TestCollisionSuffix:
    def test_creates_suffixed_path_when_content_differs(self, tmp_path):
        src = _write(tmp_path / _FNAME, "new")
        archive = tmp_path / "archive"
        archive.mkdir()
        _write(archive / _FNAME, "old")
        dest = archive_jsonl(src, archive)
        assert dest == archive / "watchtrack_2026-04-29_2.jsonl"

    def test_creates_suffixed_path_when_size_differs(self, tmp_path):
        # Exercises the else-branch (sizes differ; sha256 not used for idempotency
        # check, but both hashes still computed for the warning log).
        src = _write(tmp_path / _FNAME, "short")
        archive = tmp_path / "archive"
        archive.mkdir()
        _write(archive / _FNAME, "a-much-longer-content")
        dest = archive_jsonl(src, archive)
        assert dest == archive / "watchtrack_2026-04-29_2.jsonl"

    def test_increments_to_three_when_two_taken(self, tmp_path):
        src = _write(tmp_path / _FNAME, "new")
        archive = tmp_path / "archive"
        archive.mkdir()
        _write(archive / _FNAME, "old")
        _write(archive / "watchtrack_2026-04-29_2.jsonl", "other")
        dest = archive_jsonl(src, archive)
        assert dest == archive / "watchtrack_2026-04-29_3.jsonl"

    def test_source_removed_on_collision(self, tmp_path):
        src = _write(tmp_path / _FNAME, "new")
        archive = tmp_path / "archive"
        archive.mkdir()
        _write(archive / _FNAME, "old")
        archive_jsonl(src, archive)
        assert not src.exists()

    def test_original_archive_contents_unchanged(self, tmp_path):
        src = _write(tmp_path / _FNAME, "new")
        archive = tmp_path / "archive"
        archive.mkdir()
        _write(archive / _FNAME, "old")
        archive_jsonl(src, archive)
        assert (archive / _FNAME).read_text() == "old"

    def test_warning_log_emitted(self, tmp_path, caplog):
        import logging
        src = _write(tmp_path / _FNAME, "new")
        archive = tmp_path / "archive"
        archive.mkdir()
        _write(archive / _FNAME, "old")
        with caplog.at_level(logging.WARNING, logger="scripts.ingest_sales"):
            archive_jsonl(src, archive)
        assert any("collision" in r.message.lower() for r in caplog.records)

    def test_warning_log_contains_hashes(self, tmp_path, caplog):
        import hashlib
        import logging
        content_new = "new-content"
        content_old = "old-content"
        src = _write(tmp_path / _FNAME, content_new)
        archive = tmp_path / "archive"
        archive.mkdir()
        _write(archive / _FNAME, content_old)
        with caplog.at_level(logging.WARNING, logger="scripts.ingest_sales"):
            archive_jsonl(src, archive)
        msg = " ".join(r.message for r in caplog.records if "collision" in r.message.lower())
        # Both sha256 hashes must appear in the warning message.
        src_hash = hashlib.sha256(content_new.encode()).hexdigest()
        dest_hash = hashlib.sha256(content_old.encode()).hexdigest()
        assert src_hash in msg
        assert dest_hash in msg

    def test_already_suffixed_source_increments_without_double_suffix(self, tmp_path):
        # Source is watchtrack_2026-04-29_2.jsonl (already suffixed).
        # Archive already has watchtrack_2026-04-29_2.jsonl with different content.
        # _next_archive_path should parse _2, increment to _3 → no _2_2.
        suffixed_name = "watchtrack_2026-04-29_2.jsonl"
        src = _write(tmp_path / suffixed_name, "new")
        archive = tmp_path / "archive"
        archive.mkdir()
        _write(archive / suffixed_name, "old")
        dest = archive_jsonl(src, archive)
        assert dest == archive / "watchtrack_2026-04-29_3.jsonl"


# ─── OS error and EXDEV ───────────────────────────────────────────────


class TestOSErrors:
    def test_exdev_raises_archive_move_failed(self, tmp_path, monkeypatch):
        import os
        src = _write(tmp_path / _FNAME)
        archive = tmp_path / "archive"

        def _raise_exdev(src_path, dst_path):
            raise OSError(errno.EXDEV, "Invalid cross-device link", str(src_path))

        monkeypatch.setattr(os, "rename", _raise_exdev)
        with pytest.raises(ArchiveMoveFailed) as exc_info:
            archive_jsonl(src, archive)
        assert isinstance(exc_info.value.__cause__, OSError)

    def test_exdev_not_absorbed_no_fallback(self, tmp_path, monkeypatch):
        import os
        src = _write(tmp_path / _FNAME)
        archive = tmp_path / "archive"

        def _raise_exdev(src_path, dst_path):
            raise OSError(errno.EXDEV, "Invalid cross-device link", str(src_path))

        monkeypatch.setattr(os, "rename", _raise_exdev)
        # Source must still exist: no copy+unlink fallback occurred.
        with pytest.raises(ArchiveMoveFailed):
            archive_jsonl(src, archive)
        assert src.exists()

    def test_generic_oserror_raises_archive_move_failed(self, tmp_path, monkeypatch):
        import os
        src = _write(tmp_path / _FNAME)
        archive = tmp_path / "archive"

        def _raise(src_path, dst_path):
            raise OSError("simulated disk full")

        monkeypatch.setattr(os, "rename", _raise)
        with pytest.raises(ArchiveMoveFailed) as exc_info:
            archive_jsonl(src, archive)
        assert isinstance(exc_info.value.__cause__, OSError)


# ─── OTEL span attributes ─────────────────────────────────────────────


class TestOTELSpan:
    def test_span_outcome_archived(self, span_exporter, tmp_path):
        src = _write(tmp_path / _FNAME)
        archive = tmp_path / "archive"
        dest = archive_jsonl(src, archive)
        sp = next(
            (s for s in span_exporter.get_finished_spans()
             if s.name == "ingest_sales.archive_jsonl"), None
        )
        assert sp is not None, "ingest_sales.archive_jsonl span not found"
        assert sp.attributes["source_file"] == _FNAME
        assert sp.attributes["archive_dir"] == str(archive)
        assert sp.attributes["archived_path"] == str(dest)
        assert sp.attributes["outcome"] == "archived"

    def test_span_outcome_idempotent_skip(self, span_exporter, tmp_path):
        src = _write(tmp_path / _FNAME2, "same")
        archive = tmp_path / "archive"
        archive.mkdir()
        _write(archive / _FNAME2, "same")
        archive_jsonl(src, archive)
        sp = next(
            (s for s in span_exporter.get_finished_spans()
             if s.name == "ingest_sales.archive_jsonl"), None
        )
        assert sp is not None
        assert sp.attributes["outcome"] == "idempotent_skip"

    def test_span_outcome_collision_suffixed(self, span_exporter, tmp_path):
        src = _write(tmp_path / _FNAME, "new")
        archive = tmp_path / "archive"
        archive.mkdir()
        _write(archive / _FNAME, "old")
        archive_jsonl(src, archive)
        sp = next(
            (s for s in span_exporter.get_finished_spans()
             if s.name == "ingest_sales.archive_jsonl"), None
        )
        assert sp is not None
        assert sp.attributes["outcome"] == "collision_suffixed"

    def test_no_outcome_attribute_on_os_error(self, span_exporter, tmp_path, monkeypatch):
        import os
        src = _write(tmp_path / _FNAME)
        archive = tmp_path / "archive"

        def _raise(src_path, dst_path):
            raise OSError("simulated failure")

        monkeypatch.setattr(os, "rename", _raise)
        with pytest.raises(ArchiveMoveFailed):
            archive_jsonl(src, archive)
        sp = next(
            (s for s in span_exporter.get_finished_spans()
             if s.name == "ingest_sales.archive_jsonl"), None
        )
        assert sp is not None
        assert "outcome" not in sp.attributes
