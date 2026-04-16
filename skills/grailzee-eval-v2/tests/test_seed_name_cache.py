"""Tests for seed_name_cache.py and the fixture itself."""

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

V2_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = V2_ROOT / "tests" / "fixtures" / "name_cache_seed.json"
SEED_SCRIPT = V2_ROOT / "scripts" / "seed_name_cache.py"

# The spec claims 23 but the actual JSON has 22 unique keys and the
# brand counts (10+4+3+1+4) sum to 22. The JSON content is authoritative.
EXPECTED_ENTRY_COUNT = 22


class TestFixtureIntegrity:
    """The fixture file is the source of truth. Validate its shape."""

    def test_fixture_exists(self):
        assert FIXTURE_PATH.exists(), f"Fixture missing: {FIXTURE_PATH}"

    def test_fixture_is_valid_json(self):
        with open(FIXTURE_PATH) as f:
            json.load(f)

    def test_fixture_has_expected_entry_count(self):
        with open(FIXTURE_PATH) as f:
            data = json.load(f)
        assert len(data) == EXPECTED_ENTRY_COUNT, (
            f"Expected {EXPECTED_ENTRY_COUNT} entries, got {len(data)}"
        )

    def test_fixture_brand_distribution(self):
        """Sanity-check brand counts match plan Section 7.7."""
        with open(FIXTURE_PATH) as f:
            data = json.load(f)
        counts = Counter(entry["brand"] for entry in data.values())
        assert counts["Tudor"] == 10
        assert counts["Omega"] == 4
        assert counts["Breitling"] == 3
        assert counts["Cartier"] == 1
        assert counts["Rolex"] == 4

    def test_every_entry_has_brand_and_model(self):
        with open(FIXTURE_PATH) as f:
            data = json.load(f)
        for ref, entry in data.items():
            assert "brand" in entry, f"{ref} missing brand"
            assert "model" in entry, f"{ref} missing model"
            assert isinstance(entry["brand"], str)
            assert isinstance(entry["model"], str)

    def test_alt_refs_are_lists_when_present(self):
        with open(FIXTURE_PATH) as f:
            data = json.load(f)
        for ref, entry in data.items():
            if "alt_refs" in entry:
                assert isinstance(entry["alt_refs"], list)
                assert all(isinstance(r, str) for r in entry["alt_refs"])

    def test_dj_126300_has_config_breakout_flag(self):
        """DJ 126300 requires config breakout per plan Section 7.7."""
        with open(FIXTURE_PATH) as f:
            data = json.load(f)
        assert data["126300"].get("config_breakout") is True

    def test_entries_with_alt_refs(self):
        """Three entries should have alt_refs: 79830RB, 79230R, 79230B."""
        with open(FIXTURE_PATH) as f:
            data = json.load(f)
        refs_with_alts = sorted(k for k, v in data.items() if "alt_refs" in v)
        assert refs_with_alts == ["79230B", "79230R", "79830RB"]


class TestSeedScript:
    """Exercise seed_name_cache.py via subprocess so arg parsing and
    exit codes are actually tested."""

    def test_dry_run_writes_nothing(self, tmp_path):
        target = tmp_path / "name_cache.json"
        result = subprocess.run(
            [sys.executable, str(SEED_SCRIPT),
             "--target", str(target), "--dry-run"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert not target.exists()
        assert "dry-run" in result.stdout.lower()

    def test_fresh_seed_creates_file_with_all_entries(self, tmp_path):
        target = tmp_path / "name_cache.json"
        result = subprocess.run(
            [sys.executable, str(SEED_SCRIPT), "--target", str(target)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert target.exists()
        with open(target) as f:
            data = json.load(f)
        assert len(data) == EXPECTED_ENTRY_COUNT

    def test_seed_is_idempotent(self, tmp_path):
        target = tmp_path / "name_cache.json"
        # First run
        subprocess.run([sys.executable, str(SEED_SCRIPT),
                        "--target", str(target)],
                       capture_output=True, text=True, check=True)

        # Second run; same content preserved
        result = subprocess.run(
            [sys.executable, str(SEED_SCRIPT), "--target", str(target)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        with open(target) as f:
            data = json.load(f)
        assert len(data) == EXPECTED_ENTRY_COUNT

    def test_seed_preserves_existing_entries(self, tmp_path):
        """If someone has manually added a reference, re-seeding should
        not overwrite it."""
        target = tmp_path / "name_cache.json"
        existing = {
            "CUSTOM_REF": {"brand": "Patek", "model": "Nautilus 5711"},
        }
        target.write_text(json.dumps(existing))

        subprocess.run([sys.executable, str(SEED_SCRIPT),
                        "--target", str(target)],
                       capture_output=True, text=True, check=True)

        with open(target) as f:
            data = json.load(f)
        assert "CUSTOM_REF" in data
        assert data["CUSTOM_REF"]["model"] == "Nautilus 5711"
        assert len(data) == EXPECTED_ENTRY_COUNT + 1

    def test_force_overwrites_existing(self, tmp_path):
        target = tmp_path / "name_cache.json"
        existing = {"CUSTOM_REF": {"brand": "Patek", "model": "5711"}}
        target.write_text(json.dumps(existing))

        subprocess.run([sys.executable, str(SEED_SCRIPT),
                        "--target", str(target), "--force"],
                       capture_output=True, text=True, check=True)

        with open(target) as f:
            data = json.load(f)
        assert "CUSTOM_REF" not in data
        assert len(data) == EXPECTED_ENTRY_COUNT

    def test_corrupt_json_errors_cleanly(self, tmp_path):
        """If the existing cache is corrupt JSON, script exits non-zero
        and suggests --force."""
        target = tmp_path / "name_cache.json"
        target.write_text("not valid json{{{")
        result = subprocess.run(
            [sys.executable, str(SEED_SCRIPT), "--target", str(target)],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "corrupt" in result.stderr.lower() or "force" in result.stderr.lower()

    def test_corrupt_json_with_force_succeeds(self, tmp_path):
        """--force overwrites a corrupt cache cleanly."""
        target = tmp_path / "name_cache.json"
        target.write_text("not valid json{{{")
        result = subprocess.run(
            [sys.executable, str(SEED_SCRIPT),
             "--target", str(target), "--force"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        with open(target) as f:
            data = json.load(f)
        assert len(data) == EXPECTED_ENTRY_COUNT

    def test_unreachable_drive_is_warning_not_error(self, tmp_path):
        """If the target directory doesn't exist, script warns but
        exits 0. Caller can handle manually."""
        bad_target = tmp_path / "nonexistent_dir" / "name_cache.json"
        result = subprocess.run(
            [sys.executable, str(SEED_SCRIPT), "--target", str(bad_target)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "unreachable" in result.stderr.lower() or \
               "warning" in result.stderr.lower()
