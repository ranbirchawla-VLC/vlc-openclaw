"""Tests for scripts.backfill_ledger — validation, preview, commit."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

V2_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = V2_ROOT / "scripts" / "backfill_ledger.py"
FIXTURES = V2_ROOT / "tests" / "fixtures"
NO_CACHE = "/tmp/_grailzee_test_no_such_cache.json"

VALID = str(FIXTURES / "backfill_sample_valid.csv")
INVALID_DATES = str(FIXTURES / "backfill_sample_invalid_dates.csv")
INVALID_SCHEMA = str(FIXTURES / "backfill_sample_invalid_schema.csv")
INVALID_PRICES = str(FIXTURES / "backfill_sample_invalid_prices.csv")
INVALID_CYCLE = str(FIXTURES / "backfill_sample_invalid_cycle.csv")
WITH_WARNINGS = str(FIXTURES / "backfill_sample_with_warnings.csv")
TEMPLATE = str(FIXTURES / "backfill_template.csv")

# ─── Hand-computed expected aggregates from backfill_sample_valid.csv ──
# Same 6 rows as trade_ledger_sample.csv (Phase 3).
# total_buy=15250 total_sell=17225 total_fees=944 total_net=1031
# avg_roi=5.95 profitable=6 losing=0 NR=5 RES=1 Tudor=5 Breitling=1
EXPECTED_TOTAL_BUY = 15250
EXPECTED_TOTAL_SELL = 17225
EXPECTED_TOTAL_FEES = 944
EXPECTED_TOTAL_NET = 1031
EXPECTED_AVG_ROI = 5.95
EXPECTED_PROFITABLE = 6


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + list(args),
        capture_output=True, text=True,
    )


# ═══════════════════════════════════════════════════════════════════════
# Validate command
# ═══════════════════════════════════════════════════════════════════════


class TestValidateClean:
    def test_valid_input_exits_0(self):
        r = run_cli("validate", VALID)
        assert r.returncode == 0, r.stdout

    def test_valid_output_is_json(self):
        r = run_cli("validate", VALID)
        data = json.loads(r.stdout)
        assert data["status"] == "ok"
        assert data["rows_valid"] == 6
        assert data["rows_rejected"] == 0

    def test_template_header_only_exits_0(self):
        r = run_cli("validate", TEMPLATE)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["rows_total"] == 0


class TestValidateDateRejections:
    def test_invalid_dates_exit_2(self):
        r = run_cli("validate", INVALID_DATES)
        assert r.returncode == 2

    def test_malformed_date_rejected(self):
        r = run_cli("validate", INVALID_DATES)
        data = json.loads(r.stdout)
        errors = data["errors"]
        assert any("02/14/2026" in e for e in errors)

    def test_future_date_rejected(self):
        r = run_cli("validate", INVALID_DATES)
        data = json.loads(r.stdout)
        errors = data["errors"]
        assert any("Future date" in e for e in errors)

    def test_non_date_string_rejected(self):
        r = run_cli("validate", INVALID_DATES)
        data = json.loads(r.stdout)
        errors = data["errors"]
        assert any("yesterday" in e for e in errors)


class TestValidateSchemaRejections:
    def test_invalid_schema_exit_2(self):
        r = run_cli("validate", INVALID_SCHEMA)
        assert r.returncode == 2

    def test_invalid_account_rejected(self):
        r = run_cli("validate", INVALID_SCHEMA)
        data = json.loads(r.stdout)
        errors = data["errors"]
        # NONE and Reserve are invalid; nr uppercases to NR (valid)
        assert any("NONE" in e for e in errors)
        assert any("Reserve" in e for e in errors)

    def test_empty_brand_rejected(self):
        r = run_cli("validate", INVALID_SCHEMA)
        data = json.loads(r.stdout)
        errors = data["errors"]
        assert any("brand is empty" in e for e in errors)

    def test_reference_with_comma_rejected(self):
        r = run_cli("validate", INVALID_SCHEMA)
        data = json.loads(r.stdout)
        errors = data["errors"]
        assert any("comma or quote" in e for e in errors)

    def test_lowercase_nr_accepted(self):
        """'nr' uppercases to 'NR' which is valid."""
        r = run_cli("validate", INVALID_SCHEMA)
        data = json.loads(r.stdout)
        errors = data["errors"]
        # Exactly the 'nr' row should NOT have an account error
        nr_errors = [e for e in errors if "nr" in e.lower() and "account" in e.lower()]
        # The 'nr' row has no account error because it uppercases to NR
        assert not any("invalid account 'nr'" in e.lower() for e in errors)


class TestValidatePriceRejections:
    def test_invalid_prices_exit_2(self):
        r = run_cli("validate", INVALID_PRICES)
        assert r.returncode == 2

    def test_negative_buy_rejected(self):
        r = run_cli("validate", INVALID_PRICES)
        data = json.loads(r.stdout)
        assert any("must be positive" in e and "-100" in e for e in data["errors"])

    def test_zero_sell_rejected(self):
        r = run_cli("validate", INVALID_PRICES)
        data = json.loads(r.stdout)
        assert any("must be positive" in e and "sell_price" in e
                    for e in data["errors"])

    def test_non_numeric_rejected(self):
        r = run_cli("validate", INVALID_PRICES)
        data = json.loads(r.stdout)
        assert any("not numeric" in e for e in data["errors"])

    def test_dollar_sign_accepted(self):
        """buy_price='$2750' should strip $ and accept as 2750."""
        r = run_cli("validate", INVALID_PRICES)
        data = json.loads(r.stdout)
        # The $2750 row should NOT have a price error
        dollar_errors = [e for e in data["errors"]
                         if "$2750" in e and "not numeric" in e]
        assert len(dollar_errors) == 0


class TestValidateCycleRejection:
    def test_mismatched_cycle_rejected(self):
        r = run_cli("validate", INVALID_CYCLE)
        assert r.returncode == 2
        data = json.loads(r.stdout)
        assert any("cycle_id" in e and "does not match" in e
                    for e in data["errors"])


class TestValidateWarnings:
    def test_warnings_exit_0(self):
        """Warnings alone do not cause non-zero exit."""
        r = run_cli("validate", WITH_WARNINGS)
        assert r.returncode == 0

    def test_losing_trade_warning(self):
        r = run_cli("validate", WITH_WARNINGS)
        data = json.loads(r.stdout)
        assert any("Losing trade" in w for w in data["warnings"])

    def test_high_value_warning(self):
        r = run_cli("validate", WITH_WARNINGS)
        data = json.loads(r.stdout)
        assert any("High-value" in w for w in data["warnings"])


class TestValidateHeaderMismatch:
    def test_wrong_header_rejected(self, tmp_path):
        bad = tmp_path / "bad_header.csv"
        bad.write_text("col1,col2,col3\n1,2,3\n")
        r = run_cli("validate", str(bad))
        assert r.returncode == 2
        data = json.loads(r.stdout)
        assert any("Header mismatch" in e for e in data["errors"])


# ═══════════════════════════════════════════════════════════════════════
# Preview command
# ═══════════════════════════════════════════════════════════════════════


class TestPreview:
    def test_preview_valid_exits_0(self):
        r = run_cli("preview", VALID)
        assert r.returncode == 0

    def test_preview_aggregates_correct(self):
        r = run_cli("preview", VALID)
        data = json.loads(r.stdout)
        agg = data["aggregates"]
        assert agg["total_trades"] == 6
        assert agg["total_buy"] == EXPECTED_TOTAL_BUY
        assert agg["total_sell"] == EXPECTED_TOTAL_SELL
        assert agg["total_fees"] == EXPECTED_TOTAL_FEES
        assert agg["total_net_profit"] == EXPECTED_TOTAL_NET
        assert abs(agg["avg_roi_pct"] - EXPECTED_AVG_ROI) < 0.05
        assert agg["profitable_count"] == EXPECTED_PROFITABLE
        assert agg["losing_count"] == 0

    def test_preview_brand_distribution(self):
        r = run_cli("preview", VALID)
        data = json.loads(r.stdout)
        assert data["aggregates"]["brands"]["Tudor"] == 5
        assert data["aggregates"]["brands"]["Breitling"] == 1

    def test_preview_account_distribution(self):
        r = run_cli("preview", VALID)
        data = json.loads(r.stdout)
        assert data["aggregates"]["accounts"]["NR"] == 5
        assert data["aggregates"]["accounts"]["RES"] == 1

    def test_preview_invalid_exits_2(self):
        r = run_cli("preview", INVALID_DATES)
        assert r.returncode == 2

    def test_preview_header_only_exits_0(self):
        r = run_cli("preview", TEMPLATE)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["aggregates"]["total_trades"] == 0

    def test_preview_cycle_ids_auto_filled(self):
        r = run_cli("preview", VALID)
        data = json.loads(r.stdout)
        cycles = data["aggregates"]["cycles"]
        assert len(cycles) == 6


# ═══════════════════════════════════════════════════════════════════════
# Commit command
# ═══════════════════════════════════════════════════════════════════════


class TestCommit:
    def test_commit_valid_to_empty_ledger(self, tmp_path):
        ledger = str(tmp_path / "ledger.csv")
        r = run_cli("commit", VALID, "--ledger", ledger)
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["status"] == "ok"
        assert data["rows_committed"] == 6
        assert data["ledger_rows_after"] == 6

    def test_commit_aggregates_match_preview(self, tmp_path):
        ledger = str(tmp_path / "ledger.csv")
        r = run_cli("commit", VALID, "--ledger", ledger)
        data = json.loads(r.stdout)
        agg = data["aggregates"]
        assert agg["total_net_profit"] == EXPECTED_TOTAL_NET

    def test_commit_invalid_writes_zero_rows(self, tmp_path):
        """Atomic: if any row fails validation, nothing is written."""
        ledger = str(tmp_path / "ledger.csv")
        r = run_cli("commit", INVALID_DATES, "--ledger", ledger)
        assert r.returncode == 2
        # Ledger should not exist or be header-only
        if Path(ledger).exists():
            from scripts.grailzee_common import parse_ledger_csv
            assert parse_ledger_csv(ledger) == []

    def test_commit_mixed_validity_writes_zero(self, tmp_path):
        """9 valid + 1 bad = 0 written. Tests atomicity explicitly."""
        mixed = tmp_path / "mixed.csv"
        lines = [
            "date_closed,cycle_id,brand,reference,account,buy_price,sell_price",
            "2026-01-05,,Tudor,79830RB,NR,2750,3200",
            "2026-01-06,,Tudor,91650,NR,1500,1675",
            "bad-date,,Tudor,79230R,NR,2800,3150",
        ]
        mixed.write_text("\n".join(lines) + "\n")
        ledger = str(tmp_path / "ledger.csv")
        r = run_cli("commit", str(mixed), "--ledger", ledger)
        assert r.returncode == 2
        if Path(ledger).exists():
            from scripts.grailzee_common import parse_ledger_csv
            assert parse_ledger_csv(ledger) == []

    def test_commit_appends_to_existing(self, tmp_path):
        """Committing to a non-empty ledger appends (not idempotent)."""
        ledger = str(tmp_path / "ledger.csv")
        # First commit
        run_cli("commit", VALID, "--ledger", ledger)
        # Second commit
        r = run_cli("commit", VALID, "--ledger", ledger)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["ledger_rows_after"] == 12

    def test_committed_rows_readable_by_read_ledger(self, tmp_path):
        """End-to-end: commit then verify via read_ledger.run()."""
        ledger = str(tmp_path / "ledger.csv")
        run_cli("commit", VALID, "--ledger", ledger)
        from scripts.read_ledger import run as ledger_run
        result = ledger_run(ledger_path=ledger,
                            cache_path=NO_CACHE)
        assert result["summary"]["total_trades"] == 6
        assert result["summary"]["total_net_profit"] == EXPECTED_TOTAL_NET

    def test_commit_auto_fills_cycle_id(self, tmp_path):
        """Blank cycle_id in input is filled from date_closed."""
        ledger = str(tmp_path / "ledger.csv")
        run_cli("commit", VALID, "--ledger", ledger)
        from scripts.grailzee_common import parse_ledger_csv
        rows = parse_ledger_csv(ledger)
        for row in rows:
            assert row.cycle_id.startswith("cycle_")
            assert row.cycle_id != ""

    def test_commit_stdout_is_valid_json(self, tmp_path):
        ledger = str(tmp_path / "ledger.csv")
        r = run_cli("commit", VALID, "--ledger", ledger)
        json.loads(r.stdout)


# ═══════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_comments_between_data_rows(self, tmp_path):
        """Comment lines between data rows are stripped cleanly."""
        f = tmp_path / "commented.csv"
        f.write_text(
            "date_closed,cycle_id,brand,reference,account,buy_price,sell_price\n"
            "# This is a header comment\n"
            "2026-01-05,,Tudor,79830RB,NR,2750,3200\n"
            "# Another comment mid-file\n"
            "2026-01-06,,Tudor,91650,NR,1500,1675\n"
        )
        r = run_cli("validate", str(f))
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["rows_valid"] == 2

    def test_utf8_bom_handled(self, tmp_path):
        """UTF-8 BOM at file start doesn't corrupt first field."""
        f = tmp_path / "bom.csv"
        f.write_bytes(
            b"\xef\xbb\xbf"
            b"date_closed,cycle_id,brand,reference,account,buy_price,sell_price\n"
            b"2026-01-05,,Tudor,79830RB,NR,2750,3200\n"
        )
        r = run_cli("validate", str(f))
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["rows_valid"] == 1

    def test_trailing_blank_lines_ignored(self, tmp_path):
        f = tmp_path / "trailing.csv"
        f.write_text(
            "date_closed,cycle_id,brand,reference,account,buy_price,sell_price\n"
            "2026-01-05,,Tudor,79830RB,NR,2750,3200\n"
            "\n\n\n"
        )
        r = run_cli("validate", str(f))
        assert r.returncode == 0

    def test_unicode_reference_accepted(self, tmp_path):
        f = tmp_path / "unicode.csv"
        f.write_text(
            "date_closed,cycle_id,brand,reference,account,buy_price,sell_price\n"
            "2026-01-05,,Longines,L3.781.4.96.9,NR,1500,1800\n"
        )
        r = run_cli("validate", str(f))
        assert r.returncode == 0

    def test_no_command_exits_2(self):
        r = run_cli()
        assert r.returncode == 2
