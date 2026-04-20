"""Tests for scripts.backfill_ledger (Phase A CLI).

HERMETICITY WARNING: these tests use grailzee_common which may reference
live Drive paths. Do not run pytest until test hermeticity is verified
on this branch. See Session 5 close doc, Deferred follow-ups #3.

Covers:
  - valid 14-row seed
  - invalid dates, accounts (R vs RES), prices ($, comma, negative, zero)
  - missing columns, empty reference, BOM header, whitespace-padded header
  - duplicate row, future date
  - --dry-run atomicity (no writes)
  - real-write atomicity (rename failure leaves ledger intact)
  - dedup of pre-existing rows
  - brand-mismatch WARNING does not fail
  - missing grailzee_common attr → exit 3
  - --force bypasses validation errors for the bad row only
  - --no-roll skips roll_cycle invocation
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import pytest

TESTS_DIR = Path(__file__).resolve().parent
V2_ROOT = TESTS_DIR.parent
SCRIPTS_DIR = V2_ROOT / "scripts"
if str(V2_ROOT) not in sys.path:
    sys.path.insert(0, str(V2_ROOT))

from scripts import backfill_ledger as bl  # noqa: E402


# ─── Fixture helpers ──────────────────────────────────────────────────


HEADER_INPUT = "date_closed,brand,reference,account,buy_price,sell_price,notes\n"
HEADER_WITH_BOM = "\ufeff" + HEADER_INPUT
HEADER_WITH_TRAILING_SPACE = (
    "date_closed ,brand,reference,account,buy_price,sell_price,notes\n"
)


def _row(dt: str, brand: str, ref: str, acct: str, buy: str, sell: str,
         notes: str = "") -> str:
    return f"{dt},{brand},{ref},{acct},{buy},{sell},{notes}\n"


def _write(tmp_path: Path, name: str, text: str) -> str:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def _write_bytes(tmp_path: Path, name: str, data: bytes) -> str:
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def _empty_ledger(tmp_path: Path, name: str = "ledger.csv") -> str:
    p = tmp_path / name
    p.write_text(
        "date_closed,cycle_id,brand,reference,account,buy_price,sell_price\n",
        encoding="utf-8",
    )
    return str(p)


@pytest.fixture
def no_name_cache(tmp_path: Path) -> str:
    """Name cache path that deliberately does not exist."""
    return str(tmp_path / "no_such_name_cache.json")


@pytest.fixture
def empty_name_cache(tmp_path: Path) -> str:
    p = tmp_path / "empty_name_cache.json"
    p.write_text("{}", encoding="utf-8")
    return str(p)


@pytest.fixture(autouse=True)
def _mock_subprocess(monkeypatch: pytest.MonkeyPatch):
    """Stub subprocess.run globally so post-write hooks don't touch Drive.

    Tests that care about subprocess calls replace this with their own
    recorder (see test_no_roll_skips_rollup, test_real_write_invokes_hooks).
    """
    def _fake_run(cmd, capture_output=False, text=False, **kwargs):
        class _R:
            returncode = 0
            stdout = "(subprocess stubbed in tests)"
            stderr = ""
        return _R()
    monkeypatch.setattr("scripts.backfill_ledger.subprocess.run", _fake_run)


# ─── Seed fixtures (match Phase A production seed layout) ─────────────


VALID_14 = HEADER_WITH_BOM.replace(
    "date_closed,", "date_closed ,"  # trailing space on column name
) + (
    _row("4/19/26", "Tudor", "M28500-0005", "NR", "2200", "2400")
    + _row("4/19/26", "Tudor", "M28600-0009", "NR", "2200", "2800")
    + _row("4/19/26", "Tudor", "M79000N-0002", "NR", "3400", "3700")
    + _row("4/19/26", "Tudor", "79470-0001", "NR", "3000", "2950")
    + _row("3/25/26", "Tudor", "M28500-0003", "NR", "1800", "2350")
    + _row("3/24/26", "Tudor", "M79830RB-0001", "NR", "2750", "3450")
    + _row("3/11/26", "Tudor", "21010", "NR", "1750", "1701")
    + _row("3/3/26", "Rolex", "116900", "NR", "7399", "7501")
    + _row("2/25/26", "Tudor", "79830RB", "NR", "2950", "3050")
    + _row("2/16/26", "Tudor", "28500", "NR", "1750", "2130")
    + _row("2/16/26", "Tudor", "79360N", "RES", "8900", "9850")
    + _row("2/16/26", "Tudor", "79230R", "NR", "2950", "3100")
    + _row("2/16/26", "Tudor", "79230B", "NR", "2600", "2900")
    + _row("2/5/26", "Rolex", "216570", "RES", "9550", "10000")
)


# ═══════════════════════════════════════════════════════════════════════
# Parse / normalization
# ═══════════════════════════════════════════════════════════════════════


class TestReadInput:
    def test_bom_stripped(self, tmp_path):
        p = _write_bytes(
            tmp_path, "bom.csv",
            b"\xef\xbb\xbf" + HEADER_INPUT.encode()
            + _row("3/3/26", "Rolex", "116900", "NR", "7399", "7501").encode(),
        )
        rows, errs = bl.read_input(p)
        assert errs == []
        assert len(rows) == 1
        assert rows[0]["date_closed"] == "3/3/26"

    def test_trailing_space_header_accepted(self, tmp_path):
        p = _write(
            tmp_path, "ws.csv",
            HEADER_WITH_TRAILING_SPACE
            + _row("2/5/26", "Rolex", "216570", "RES", "9550", "10000"),
        )
        rows, errs = bl.read_input(p)
        assert errs == []
        assert len(rows) == 1

    def test_missing_column_returns_file_error(self, tmp_path):
        bad_header = "date_closed,brand,reference,account,buy_price,sell_price\n"
        p = _write(tmp_path, "missing.csv", bad_header + "2026-01-01,A,B,NR,1,2\n")
        rows, errs = bl.read_input(p)
        assert rows == []
        assert len(errs) == 1
        assert "Missing required columns" in errs[0]
        assert "notes" in errs[0]

    def test_values_whitespace_trimmed(self, tmp_path):
        p = _write(
            tmp_path, "ws_vals.csv",
            HEADER_INPUT + "  3/3/26 , Rolex , 116900 , NR , 7399 , 7501 , \n",
        )
        rows, errs = bl.read_input(p)
        assert errs == []
        assert rows[0]["brand"] == "Rolex"
        assert rows[0]["buy_price"] == "7399"


# ═══════════════════════════════════════════════════════════════════════
# Per-row validation
# ═══════════════════════════════════════════════════════════════════════


class TestDateParsing:
    def test_iso_accepted(self):
        assert bl.parse_date("2026-03-03") == date(2026, 3, 3)

    def test_slash_short_year_accepted(self):
        assert bl.parse_date("3/3/26") == date(2026, 3, 3)

    def test_slash_long_year_accepted(self):
        assert bl.parse_date("3/3/2026") == date(2026, 3, 3)

    def test_garbage_rejected(self):
        assert bl.parse_date("yesterday") is None

    def test_euro_rejected(self):
        assert bl.parse_date("03-03-2026") is None


class TestPriceParsing:
    def test_integer_accepted(self):
        assert bl.parse_price("2750") == 2750.0

    def test_decimal_accepted(self):
        assert bl.parse_price("2750.50") == 2750.5

    def test_dollar_sign_rejected(self):
        assert bl.parse_price("$2750") is None

    def test_comma_rejected(self):
        assert bl.parse_price("2,750") is None

    def test_whitespace_inside_rejected(self):
        assert bl.parse_price("27 50") is None

    def test_zero_rejected(self):
        assert bl.parse_price("0") is None

    def test_negative_rejected(self):
        assert bl.parse_price("-100") is None


class TestAccountValidation:
    def _build(self, tmp_path, acct: str) -> str:
        return _write(
            tmp_path, "acct.csv",
            HEADER_INPUT + _row("3/3/26", "Rolex", "116900", acct, "100", "200"),
        )

    def test_nr_valid(self, tmp_path):
        p = self._build(tmp_path, "NR")
        rows, _ = bl.read_input(p)
        norm, errs = bl.validate_row(rows[0], date(2026, 4, 20))
        assert errs == []
        assert norm["account"] == "NR"

    def test_res_valid(self, tmp_path):
        p = self._build(tmp_path, "RES")
        rows, _ = bl.read_input(p)
        norm, errs = bl.validate_row(rows[0], date(2026, 4, 20))
        assert errs == []

    @pytest.mark.parametrize("bad", ["R", "r", "Res", "RESERVE", "nr", ""])
    def test_strict_rejections(self, tmp_path, bad):
        p = self._build(tmp_path, bad)
        rows, _ = bl.read_input(p)
        norm, errs = bl.validate_row(rows[0], date(2026, 4, 20))
        assert norm is None
        assert any("invalid account" in e for e in errs)


class TestFieldValidation:
    def test_future_date_rejected(self, tmp_path):
        future = (date.today() + timedelta(days=5)).strftime("%m/%d/%Y")
        p = _write(
            tmp_path, "future.csv",
            HEADER_INPUT + _row(future, "Tudor", "28500", "NR", "100", "200"),
        )
        rows, _ = bl.read_input(p)
        norm, errs = bl.validate_row(rows[0], date.today())
        assert norm is None
        assert any("future" in e.lower() for e in errs)

    def test_empty_reference_rejected(self, tmp_path):
        p = _write(
            tmp_path, "empty_ref.csv",
            HEADER_INPUT + _row("3/3/26", "Rolex", "", "NR", "100", "200"),
        )
        rows, _ = bl.read_input(p)
        norm, errs = bl.validate_row(rows[0], date(2026, 4, 20))
        assert norm is None
        assert any("reference is empty" in e for e in errs)

    def test_reference_with_internal_whitespace_rejected(self, tmp_path):
        p = _write(
            tmp_path, "ws_ref.csv",
            HEADER_INPUT + "3/3/26,Rolex,126 610,NR,100,200,\n",
        )
        rows, _ = bl.read_input(p)
        norm, errs = bl.validate_row(rows[0], date(2026, 4, 20))
        assert norm is None
        assert any("internal whitespace" in e for e in errs)

    def test_empty_brand_rejected(self, tmp_path):
        p = _write(
            tmp_path, "empty_brand.csv",
            HEADER_INPUT + _row("3/3/26", "", "116900", "NR", "100", "200"),
        )
        rows, _ = bl.read_input(p)
        norm, errs = bl.validate_row(rows[0], date(2026, 4, 20))
        assert norm is None
        assert any("brand is empty" in e for e in errs)


# ═══════════════════════════════════════════════════════════════════════
# Brand-mismatch warning
# ═══════════════════════════════════════════════════════════════════════


class TestBrandMismatchWarning:
    def test_mismatch_emits_warning(self, tmp_path, no_name_cache, capsys):
        """116900 is cached as Rolex; input says Tudor → WARNING, not error."""
        cache = tmp_path / "cache.json"
        cache.write_text(
            '{"116900": {"brand": "Rolex", "model": "Air-King"}}',
            encoding="utf-8",
        )
        inp = _write(
            tmp_path, "tudor_116900.csv",
            HEADER_INPUT + _row("3/3/26", "Tudor", "116900", "NR", "7399", "7501"),
        )
        ledger = _empty_ledger(tmp_path)
        rc = bl.main([inp, "--dry-run",
                       "--ledger", ledger,
                       "--name-cache", str(cache)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Brand warnings:     1" in out
        assert "116900" in out
        assert "Tudor" in out and "Rolex" in out

    def test_alt_ref_matched(self, tmp_path, capsys):
        """alt_refs entry triggers lookup."""
        cache = tmp_path / "cache.json"
        cache.write_text(
            '{"79230B": {"brand": "Tudor", "alt_refs": ["M79230B-0007"]}}',
            encoding="utf-8",
        )
        inp = _write(
            tmp_path, "alt.csv",
            HEADER_INPUT
            + _row("3/3/26", "Rolex", "M79230B-0007", "NR", "100", "200"),
        )
        ledger = _empty_ledger(tmp_path)
        rc = bl.main([inp, "--dry-run", "--ledger", ledger,
                      "--name-cache", str(cache)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Brand warnings:     1" in out

    def test_no_cache_entry_no_warning(self, tmp_path, empty_name_cache, capsys):
        inp = _write(
            tmp_path, "unknown.csv",
            HEADER_INPUT
            + _row("3/3/26", "Tudor", "NOVEL-REF-999", "NR", "100", "200"),
        )
        ledger = _empty_ledger(tmp_path)
        rc = bl.main([inp, "--dry-run", "--ledger", ledger,
                      "--name-cache", empty_name_cache])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Brand warnings:     0" in out

    def test_missing_cache_file_does_not_crash(
        self, tmp_path, no_name_cache, capsys
    ):
        inp = _write(
            tmp_path, "nocache.csv",
            HEADER_INPUT + _row("3/3/26", "Tudor", "28500", "NR", "100", "200"),
        )
        ledger = _empty_ledger(tmp_path)
        rc = bl.main([inp, "--dry-run", "--ledger", ledger,
                      "--name-cache", no_name_cache])
        assert rc == 0


# ═══════════════════════════════════════════════════════════════════════
# Dedup
# ═══════════════════════════════════════════════════════════════════════


class TestDedup:
    def test_existing_row_skipped(self, tmp_path, empty_name_cache, capsys):
        ledger = tmp_path / "ledger.csv"
        ledger.write_text(
            "date_closed,cycle_id,brand,reference,account,buy_price,sell_price\n"
            "2026-03-03,cycle_2026-05,Rolex,116900,NR,7399,7501\n",
            encoding="utf-8",
        )
        inp = _write(
            tmp_path, "dup.csv",
            HEADER_INPUT
            + _row("3/3/26", "Rolex", "116900", "NR", "7399", "7501")
            + _row("3/4/26", "Rolex", "116900", "NR", "7399", "7502"),
        )
        rc = bl.main([inp, "--dry-run", "--ledger", str(ledger),
                      "--name-cache", empty_name_cache])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Duplicates:         1" in out
        # Second row (different sell price) is NOT a duplicate
        assert "Valid rows:         2" in out

    def test_in_batch_duplicates_caught(
        self, tmp_path, empty_name_cache, capsys
    ):
        ledger = _empty_ledger(tmp_path)
        inp = _write(
            tmp_path, "inbatch_dup.csv",
            HEADER_INPUT
            + _row("3/3/26", "Rolex", "116900", "NR", "7399", "7501")
            + _row("3/3/26", "Rolex", "116900", "NR", "7399", "7501"),
        )
        rc = bl.main([inp, "--dry-run", "--ledger", ledger,
                      "--name-cache", empty_name_cache])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Duplicates:         1" in out


# ═══════════════════════════════════════════════════════════════════════
# Cycle-id derivation
# ═══════════════════════════════════════════════════════════════════════


class TestCycleId:
    def test_all_14_rows_get_cycle(self, tmp_path, empty_name_cache, capsys):
        inp = _write(tmp_path, "valid14.csv", VALID_14)
        ledger = _empty_ledger(tmp_path)
        rc = bl.main([inp, "--dry-run", "--ledger", ledger,
                      "--name-cache", empty_name_cache])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Valid rows:         14" in out
        for cycle in ("cycle_2026-03", "cycle_2026-04", "cycle_2026-05",
                      "cycle_2026-06", "cycle_2026-08"):
            assert cycle in out


# ═══════════════════════════════════════════════════════════════════════
# Dry-run atomicity
# ═══════════════════════════════════════════════════════════════════════


class TestDryRun:
    def test_dry_run_writes_nothing(
        self, tmp_path, empty_name_cache, capsys
    ):
        ledger = _empty_ledger(tmp_path)
        before_mtime = os.path.getmtime(ledger)
        before_content = Path(ledger).read_text(encoding="utf-8")

        inp = _write(tmp_path, "valid14.csv", VALID_14)
        rc = bl.main([inp, "--dry-run", "--ledger", ledger,
                      "--name-cache", empty_name_cache])
        capsys.readouterr()  # discard

        assert rc == 0
        assert Path(ledger).read_text(encoding="utf-8") == before_content
        assert os.path.getmtime(ledger) == before_mtime


# ═══════════════════════════════════════════════════════════════════════
# Real-write atomicity
# ═══════════════════════════════════════════════════════════════════════


class TestRealWriteAtomicity:
    def test_real_write_appends(
        self, tmp_path, empty_name_cache, capsys
    ):
        ledger = _empty_ledger(tmp_path)
        inp = _write(tmp_path, "valid14.csv", VALID_14)
        rc = bl.main([inp, "--ledger", ledger, "--name-cache", empty_name_cache,
                      "--no-roll"])
        capsys.readouterr()
        assert rc == 0

        content = Path(ledger).read_text(encoding="utf-8")
        lines = [ln for ln in content.splitlines() if ln.strip()]
        # header + 14 rows
        assert len(lines) == 15
        assert lines[0].startswith("date_closed,cycle_id,")
        assert "cycle_2026-08" in content
        assert "116900" in content

    def test_rename_failure_leaves_ledger_intact(
        self, tmp_path, empty_name_cache, monkeypatch, capsys
    ):
        ledger = _empty_ledger(tmp_path)
        original = Path(ledger).read_text(encoding="utf-8")
        inp = _write(tmp_path, "valid14.csv", VALID_14)

        def _boom(src, dst):
            raise OSError("simulated rename failure")
        monkeypatch.setattr("scripts.backfill_ledger.os.replace", _boom)

        rc = bl.main([inp, "--ledger", ledger, "--name-cache", empty_name_cache,
                      "--no-roll"])
        capsys.readouterr()
        assert rc == 2
        # Ledger untouched
        assert Path(ledger).read_text(encoding="utf-8") == original


# ═══════════════════════════════════════════════════════════════════════
# --force semantics
# ═══════════════════════════════════════════════════════════════════════


class TestForce:
    def test_force_bypasses_validation(
        self, tmp_path, empty_name_cache, capsys
    ):
        """One bad row among good ones: --force imports the good ones."""
        mixed = (
            HEADER_INPUT
            + _row("3/3/26", "Rolex", "116900", "NR", "7399", "7501")  # good
            + _row("bad-date", "Tudor", "28500", "NR", "1750", "2130")  # bad
            + _row("3/11/26", "Tudor", "21010", "NR", "1750", "1701")   # good
        )
        inp = _write(tmp_path, "mixed.csv", mixed)
        ledger = _empty_ledger(tmp_path)
        rc = bl.main([inp, "--force", "--ledger", ledger,
                      "--name-cache", empty_name_cache, "--no-roll"])
        capsys.readouterr()
        assert rc == 0
        content = Path(ledger).read_text(encoding="utf-8")
        assert "116900" in content
        assert "21010" in content
        assert "bad-date" not in content

    def test_no_force_with_bad_row_exits_1(
        self, tmp_path, empty_name_cache, capsys
    ):
        mixed = (
            HEADER_INPUT
            + _row("3/3/26", "Rolex", "116900", "NR", "7399", "7501")
            + _row("bad-date", "Tudor", "28500", "NR", "1750", "2130")
        )
        inp = _write(tmp_path, "mixed.csv", mixed)
        ledger = _empty_ledger(tmp_path)
        original = Path(ledger).read_text(encoding="utf-8")

        rc = bl.main([inp, "--ledger", ledger,
                      "--name-cache", empty_name_cache, "--no-roll"])
        capsys.readouterr()
        assert rc == 1
        assert Path(ledger).read_text(encoding="utf-8") == original


# ═══════════════════════════════════════════════════════════════════════
# --no-roll
# ═══════════════════════════════════════════════════════════════════════


class TestNoRoll:
    def test_no_roll_skips_rollup(
        self, tmp_path, empty_name_cache, monkeypatch, capsys
    ):
        ledger = _empty_ledger(tmp_path)
        inp = _write(tmp_path, "valid14.csv", VALID_14)

        calls: list[list[str]] = []

        def _recorder(cmd, capture_output=False, text=False, **kwargs):
            calls.append(list(cmd))

            class _R:
                returncode = 0
                stdout = ""
                stderr = ""
            return _R()

        monkeypatch.setattr(
            "scripts.backfill_ledger.subprocess.run", _recorder
        )
        rc = bl.main([inp, "--ledger", ledger,
                      "--name-cache", empty_name_cache, "--no-roll"])
        capsys.readouterr()
        assert rc == 0
        # ledger_manager called twice, roll_cycle never
        assert any("ledger_manager.py" in " ".join(c) for c in calls)
        assert not any("roll_cycle.py" in " ".join(c) for c in calls)

    def test_roll_cycle_invoked_per_unique_cycle(
        self, tmp_path, empty_name_cache, monkeypatch, capsys
    ):
        ledger = _empty_ledger(tmp_path)
        inp = _write(tmp_path, "valid14.csv", VALID_14)

        calls: list[list[str]] = []

        def _recorder(cmd, capture_output=False, text=False, **kwargs):
            calls.append(list(cmd))

            class _R:
                returncode = 0
                stdout = ""
                stderr = ""
            return _R()

        monkeypatch.setattr(
            "scripts.backfill_ledger.subprocess.run", _recorder
        )
        rc = bl.main([inp, "--ledger", ledger,
                      "--name-cache", empty_name_cache])
        capsys.readouterr()
        assert rc == 0
        roll_calls = [c for c in calls if "roll_cycle.py" in " ".join(c)]
        cycles_invoked = {c[-1] for c in roll_calls}
        assert cycles_invoked == {
            "cycle_2026-03", "cycle_2026-04", "cycle_2026-05",
            "cycle_2026-06", "cycle_2026-08",
        }


# ═══════════════════════════════════════════════════════════════════════
# Missing grailzee_common attr → exit 3
# ═══════════════════════════════════════════════════════════════════════


class TestDependencyCheck:
    def test_missing_cycle_id_from_date_exits_3(
        self, tmp_path, empty_name_cache, monkeypatch, capsys
    ):
        import scripts.grailzee_common as gc_mod
        monkeypatch.delattr(gc_mod, "cycle_id_from_date")
        inp = _write(tmp_path, "valid14.csv", VALID_14)
        ledger = _empty_ledger(tmp_path)
        rc = bl.main([inp, "--dry-run", "--ledger", ledger,
                      "--name-cache", empty_name_cache])
        err = capsys.readouterr().err
        assert rc == 3
        assert "missing required attrs" in err
        assert "cycle_id_from_date" in err
        assert "Section 12.3" in err

    def test_missing_normalize_ref_exits_3(
        self, tmp_path, empty_name_cache, monkeypatch, capsys
    ):
        import scripts.grailzee_common as gc_mod
        monkeypatch.delattr(gc_mod, "normalize_ref")
        inp = _write(tmp_path, "valid14.csv", VALID_14)
        ledger = _empty_ledger(tmp_path)
        rc = bl.main([inp, "--dry-run", "--ledger", ledger,
                      "--name-cache", empty_name_cache])
        err = capsys.readouterr().err
        assert rc == 3
        assert "normalize_ref" in err


# ═══════════════════════════════════════════════════════════════════════
# Seed file integration
# ═══════════════════════════════════════════════════════════════════════


class TestSeedFile:
    """Smoke-test against the actual Phase A seed file."""

    SEED = str(V2_ROOT / "state_seeds" / "grailzee_ledger_backlog.csv")

    def test_seed_dry_run_clean(self, tmp_path, empty_name_cache, capsys):
        ledger = _empty_ledger(tmp_path)
        rc = bl.main([self.SEED, "--dry-run", "--ledger", ledger,
                      "--name-cache", empty_name_cache])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Parsed rows:        14" in out
        assert "Valid rows:         14" in out
        assert "Validation errors:  0" in out
        assert "Duplicates:         0" in out

    def test_seed_future_date_rejected_in_live_context(
        self, tmp_path, empty_name_cache
    ):
        """If today falls before 2026-04-19, the seed would fail validation.
        As of 2026-04-20 (spec date) this passes; assertion is documentary.
        """
        assert date.today() >= date(2026, 4, 19), (
            "Seed includes 2026-04-19; if today is earlier, dates are 'future' "
            "and must be rejected. Update seed or today assumption."
        )
