"""Tests for scripts.migrate_ledger_v2.

Hermetic: every test passes an explicit --ledger tmp path. The live
Drive ledger is never touched by this suite.
"""

from __future__ import annotations

import csv
import io
import subprocess
import sys
from pathlib import Path

from scripts.grailzee_common import LEDGER_COLUMNS, parse_ledger_csv
from scripts.migrate_ledger_v2 import BACKUP_SUFFIX, migrate

V2_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = V2_ROOT / "scripts" / "migrate_ledger_v2.py"

V1_HEADER = (
    "date_closed,cycle_id,brand,reference,account,buy_price,sell_price\n"
)
V2_HEADER_LINE = ",".join(LEDGER_COLUMNS)


def _write_v1(path: Path, rows: list[str]) -> None:
    path.write_text(V1_HEADER + "\n".join(rows) + ("\n" if rows else ""))


class TestMigrateHappyPath:
    def test_single_row_migration(self, tmp_path):
        ledger = tmp_path / "trade_ledger.csv"
        _write_v1(ledger, ["2026-02-05,cycle_2026-03,Rolex,216570,RES,9550,10000"])

        rc = migrate(str(ledger), dry_run=False, force=False)
        assert rc == 0

        content = ledger.read_text().splitlines()
        assert content[0] == V2_HEADER_LINE
        assert content[1] == ",2026-02-05,,cycle_2026-03,Rolex,216570,RES,9550,10000"

    def test_backup_preserved(self, tmp_path):
        ledger = tmp_path / "trade_ledger.csv"
        _write_v1(ledger, ["2026-02-05,cycle_2026-03,Rolex,216570,RES,9550,10000"])
        original_bytes = ledger.read_bytes()

        migrate(str(ledger), dry_run=False, force=False)

        backup = Path(str(ledger) + BACKUP_SUFFIX)
        assert backup.exists()
        assert backup.read_bytes() == original_bytes

    def test_legacy_rows_have_blank_buy_fields(self, tmp_path):
        ledger = tmp_path / "trade_ledger.csv"
        _write_v1(ledger, [
            "2026-02-05,cycle_2026-03,Rolex,216570,RES,9550,10000",
            "2026-03-03,cycle_2026-05,Rolex,116900,NR,7399,7501",
        ])

        migrate(str(ledger), dry_run=False, force=False)
        loaded = parse_ledger_csv(str(ledger))

        assert len(loaded) == 2
        for row in loaded:
            assert row.buy_date is None
            assert row.buy_cycle_id is None
            assert row.sell_cycle_id.startswith("cycle_")

    def test_sell_cycle_id_matches_cycle_id_from_date(self, tmp_path):
        """A.6 sanity: derived sell_cycle_id == cycle_id_from_date(sell_date).
        Verifies the migration's derivation matches the legacy cycle_id
        column so no rows flip cycles under the rewrite."""
        ledger = tmp_path / "trade_ledger.csv"
        _write_v1(ledger, [
            "2026-02-05,cycle_2026-03,Rolex,216570,RES,9550,10000",
            "2026-03-03,cycle_2026-05,Rolex,116900,NR,7399,7501",
            "2026-04-19,cycle_2026-08,Tudor,M28500-0005,NR,2200,2400",
        ])

        migrate(str(ledger), dry_run=False, force=False)
        loaded = parse_ledger_csv(str(ledger))

        cycles = {row.sell_date.isoformat(): row.sell_cycle_id for row in loaded}
        assert cycles["2026-02-05"] == "cycle_2026-03"
        assert cycles["2026-03-03"] == "cycle_2026-05"
        assert cycles["2026-04-19"] == "cycle_2026-08"

    def test_fourteen_row_migration(self, tmp_path):
        """Full 14-row migration mirroring the live ledger shape. Each
        row's derived sell_cycle_id must match its legacy cycle_id."""
        ledger = tmp_path / "trade_ledger.csv"
        _write_v1(ledger, [
            "2026-04-19,cycle_2026-08,Tudor,M28500-0005,NR,2200,2400",
            "2026-04-19,cycle_2026-08,Tudor,M28600-0009,NR,2200,2800",
            "2026-04-19,cycle_2026-08,Tudor,M79000N-0002,NR,3400,3700",
            "2026-04-19,cycle_2026-08,Tudor,79470-0001,NR,3000,2950",
            "2026-03-25,cycle_2026-06,Tudor,M28500-0003,NR,1800,2350",
            "2026-03-24,cycle_2026-06,Tudor,M79830RB-0001,NR,2750,3450",
            "2026-03-11,cycle_2026-05,Tudor,21010,NR,1750,1701",
            "2026-03-03,cycle_2026-05,Rolex,116900,NR,7399,7501",
            "2026-02-25,cycle_2026-04,Tudor,79830RB,NR,2950,3050",
            "2026-02-16,cycle_2026-04,Tudor,28500,NR,1750,2130",
            "2026-02-16,cycle_2026-04,Tudor,79360N,RES,8900,9850",
            "2026-02-16,cycle_2026-04,Tudor,79230R,NR,2950,3100",
            "2026-02-16,cycle_2026-04,Tudor,79230B,NR,2600,2900",
            "2026-02-05,cycle_2026-03,Rolex,216570,RES,9550,10000",
        ])

        rc = migrate(str(ledger), dry_run=False, force=False)
        assert rc == 0

        loaded = parse_ledger_csv(str(ledger))
        assert len(loaded) == 14
        # Every row carries a valid sell_cycle_id and blank buy fields.
        for row in loaded:
            assert row.buy_date is None
            assert row.buy_cycle_id is None
            assert row.sell_cycle_id.startswith("cycle_2026-")


class TestMigrateDryRun:
    def test_dry_run_preserves_file(self, tmp_path):
        ledger = tmp_path / "trade_ledger.csv"
        _write_v1(ledger, ["2026-02-05,cycle_2026-03,Rolex,216570,RES,9550,10000"])
        before = ledger.read_bytes()

        rc = migrate(str(ledger), dry_run=True, force=False)
        assert rc == 0
        assert ledger.read_bytes() == before

    def test_dry_run_no_backup(self, tmp_path):
        ledger = tmp_path / "trade_ledger.csv"
        _write_v1(ledger, ["2026-02-05,cycle_2026-03,Rolex,216570,RES,9550,10000"])

        migrate(str(ledger), dry_run=True, force=False)
        backup = Path(str(ledger) + BACKUP_SUFFIX)
        assert not backup.exists()

    def test_dry_run_preview_quotes_comma_values(self, tmp_path, capsys):
        """A value containing a comma must round-trip through the dry-run
        preview without corrupting column boundaries. Regression guard
        for the ",".join-based preview that mis-rendered such rows."""
        ledger = tmp_path / "trade_ledger.csv"
        # Use csv.writer to emit a properly-quoted v1 row whose brand
        # contains a comma. The migration accepts it; the preview must
        # preserve the comma without splitting into extra columns.
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["date_closed", "cycle_id", "brand", "reference",
                    "account", "buy_price", "sell_price"])
        w.writerow(["2026-02-05", "cycle_2026-03", "Rolex, Inc.",
                    "216570", "RES", "9550", "10000"])
        ledger.write_text(buf.getvalue())

        rc = migrate(str(ledger), dry_run=True, force=False)
        assert rc == 0

        out = capsys.readouterr().out
        # Strip the JSON summary block and the preview banner; parse what
        # follows as CSV. The comma-containing brand must land in a
        # single column, not split across two.
        preview_marker = "── dry-run preview (no disk writes) ──"
        assert preview_marker in out
        preview_csv = out.split(preview_marker, 1)[1].strip()
        rows = list(csv.reader(io.StringIO(preview_csv)))
        assert rows[0] == list(LEDGER_COLUMNS)
        data_row = rows[1]
        # Column count unchanged; brand preserved verbatim.
        assert len(data_row) == len(LEDGER_COLUMNS)
        brand_idx = list(LEDGER_COLUMNS).index("brand")
        assert data_row[brand_idx] == "Rolex, Inc."


class TestMigrateIdempotence:
    def test_already_v2_is_no_op(self, tmp_path):
        """A file already in v2 shape is not migrated again and leaves
        no backup. Running the script twice is safe."""
        ledger = tmp_path / "trade_ledger.csv"
        # First migration converts v1 to v2.
        _write_v1(ledger, ["2026-02-05,cycle_2026-03,Rolex,216570,RES,9550,10000"])
        rc1 = migrate(str(ledger), dry_run=False, force=False)
        assert rc1 == 0
        v2_content = ledger.read_bytes()

        # Remove backup so we can detect whether a second run creates one.
        backup = Path(str(ledger) + BACKUP_SUFFIX)
        backup.unlink()

        rc2 = migrate(str(ledger), dry_run=False, force=False)
        assert rc2 == 0
        assert ledger.read_bytes() == v2_content
        assert not backup.exists()


class TestMigrateSafety:
    def test_missing_ledger_fails(self, tmp_path):
        ledger = tmp_path / "no_such.csv"
        rc = migrate(str(ledger), dry_run=False, force=False)
        assert rc == 1

    def test_refuses_overwrite_existing_backup(self, tmp_path):
        ledger = tmp_path / "trade_ledger.csv"
        _write_v1(ledger, ["2026-02-05,cycle_2026-03,Rolex,216570,RES,9550,10000"])
        backup = Path(str(ledger) + BACKUP_SUFFIX)
        backup.write_text("an earlier backup")

        rc = migrate(str(ledger), dry_run=False, force=False)
        assert rc == 1
        # Ledger stayed v1-shape because migration refused.
        assert "date_closed" in ledger.read_text()

    def test_force_overwrites_existing_backup(self, tmp_path):
        ledger = tmp_path / "trade_ledger.csv"
        _write_v1(ledger, ["2026-02-05,cycle_2026-03,Rolex,216570,RES,9550,10000"])
        backup = Path(str(ledger) + BACKUP_SUFFIX)
        backup.write_text("an earlier backup")

        rc = migrate(str(ledger), dry_run=False, force=True)
        assert rc == 0
        assert ledger.read_text().startswith(V2_HEADER_LINE)
        # With --force, backup gets replaced with the current pre-migration
        # contents (just-overwritten by shutil.copy2 of the v1 file).
        assert "date_closed" in backup.read_text()

    def test_cycle_mismatch_aborts(self, tmp_path):
        """If the legacy cycle_id disagrees with the cycle derived from
        date_closed, the migration aborts. Prevents silent data drift."""
        ledger = tmp_path / "trade_ledger.csv"
        # 2026-03-03 falls in cycle_2026-05, but the row says cycle_2026-07.
        _write_v1(ledger, ["2026-03-03,cycle_2026-07,Rolex,116900,NR,7399,7501"])

        rc = migrate(str(ledger), dry_run=False, force=False)
        assert rc == 1
        # File untouched because aborted pre-backup.
        assert "date_closed" in ledger.read_text()


class TestMigrateCLI:
    def test_cli_dry_run(self, tmp_path):
        ledger = tmp_path / "trade_ledger.csv"
        _write_v1(ledger, ["2026-02-05,cycle_2026-03,Rolex,216570,RES,9550,10000"])

        r = subprocess.run(
            [sys.executable, str(SCRIPT), "--ledger", str(ledger), "--dry-run"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "rows_migrated" in r.stdout
        # File not rewritten on dry-run.
        assert "date_closed" in ledger.read_text()
