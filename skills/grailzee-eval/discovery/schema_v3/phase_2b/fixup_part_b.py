"""Part B; W2-only operational rehearsal end-to-end through run_analysis.

Seeds a fresh temp tree with W2 as the only CSV, runs run_analysis.run_analysis,
verifies the resulting analysis_cache.json shape post-fixup.

Per v1 prompt §6 Part B + fixup Part B new verifications:
- schema_version == 3
- confidence dict present at reference level
- premium_vs_market / realized_premium fields absent across all entries
- trend_* fields null (not "No prior data" string) on single-CSV run
- bucket_keys all lowercase
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.run_analysis import run_analysis  # noqa: E402
from scripts.grailzee_common import CACHE_SCHEMA_VERSION  # noqa: E402

DRIVE_ROOT = (
    "/Users/ranbirchawla/Library/CloudStorage/"
    "GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/"
    "Vardalux Shared Drive/GrailzeeData"
)
W2 = Path(DRIVE_ROOT) / "reports_csv" / "grailzee_2026-04-21.csv"
FIXTURES = V2_ROOT / "tests" / "fixtures"
NAME_CACHE = FIXTURES / "name_cache_seed.json"

RIPPED_FIELDS = {
    "premium_vs_market_pct", "premium_vs_market_sale_count",
    "realized_premium_pct", "realized_premium_trade_count",
    "median", "max_buy_nr", "max_buy_res", "risk_nr", "signal",
    "volume", "st_pct", "condition_mix",
    "capital_required_nr", "capital_required_res",
    "expected_net_at_median_nr", "expected_net_at_median_res",
}
RIPPED_SUMMARY = {"strong_count", "normal_count", "reserve_count", "caution_count"}
KEEP_LIST = {
    "brand", "model", "reference", "named",
    "trend_signal", "trend_median_change", "trend_median_pct",
    "momentum", "confidence", "buckets",
}


def main() -> int:
    print("# Part B; W2-only operational rehearsal (2b fixup)")
    print()
    assert W2.exists(), f"W2 missing: {W2}"
    assert CACHE_SCHEMA_VERSION == 3, f"bad CACHE_SCHEMA_VERSION: {CACHE_SCHEMA_VERSION}"

    tmp_root = Path(tempfile.mkdtemp(prefix="fixup_part_b_"))
    try:
        csv_copy = tmp_root / "grailzee_2026-04-21.csv"
        shutil.copy2(W2, csv_copy)

        output_dir = tmp_root / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        state_dir = tmp_root / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        ledger_path = state_dir / "trade_ledger.csv"
        ledger_path.write_text(
            "buy_date,sell_date,buy_cycle_id,sell_cycle_id,"
            "brand,reference,account,buy_price,sell_price\n"
        )
        cache_path = state_dir / "analysis_cache.json"
        backup_dir = state_dir / "backup"

        print(f"Temp tree: {tmp_root}")
        print(f"Running run_analysis on W2 only...")
        result = run_analysis(
            csv_paths=[str(csv_copy)],
            output_folder=str(output_dir),
            ledger_path=str(ledger_path),
            cache_path=str(cache_path),
            backup_path=str(backup_dir),
            name_cache_path=str(NAME_CACHE),
            cycle_focus_path=str(state_dir / "cycle_focus.json"),
        )
        print(f"cycle_id: {result['cycle_id']}")
        print(f"unnamed count: {len(result['unnamed'])}")
        print()

        cache = json.loads(cache_path.read_text())

        # Schema version
        print(f"schema_version: {cache['schema_version']}")
        assert cache["schema_version"] == 3
        print(f"  PASS: schema_version == 3")
        print()

        # Top-level keys
        expected_top = {
            "schema_version", "generated_at", "source_report", "cycle_id",
            "market_window", "premium_status", "references", "dj_configs",
            "changes", "breakouts", "watchlist", "brands", "unnamed", "summary",
        }
        actual_top = set(cache.keys())
        missing_top = expected_top - actual_top
        print(f"Missing top-level keys: {missing_top}")
        assert not missing_top
        print(f"  PASS: all top-level keys present")
        print()

        # Summary shape
        print(f"Summary keys: {sorted(cache['summary'].keys())}")
        leaked_summary = RIPPED_SUMMARY & set(cache["summary"].keys())
        assert not leaked_summary, f"ripped summary fields: {leaked_summary}"
        print(f"  PASS: no per-signal reference counts in summary")
        print()

        # Reference count
        refs = cache["references"]
        dj = cache["dj_configs"]
        print(f"References: {len(refs)}")
        print(f"DJ configs: {len(dj)}")
        print()

        # Per-reference shape
        leaked_refs = []
        missing_keep_refs = []
        confidence_present_refs = 0
        trend_null_refs = 0
        for ref_key, rd in refs.items():
            actual = set(rd.keys())
            leaked = RIPPED_FIELDS & actual
            missing = KEEP_LIST - actual
            if leaked:
                leaked_refs.append((ref_key, sorted(leaked)))
            if missing:
                missing_keep_refs.append((ref_key, sorted(missing)))
            if "confidence" in rd:
                confidence_present_refs += 1
            if rd.get("trend_signal") is None:
                trend_null_refs += 1

        print(f"References with leaked ripped fields: {len(leaked_refs)}")
        for rk, lk in leaked_refs[:5]:
            print(f"  {rk}: {lk}")
        assert not leaked_refs
        print(f"  PASS: no ripped fields leak into reference entries")
        print()

        print(f"References missing keep-list fields: {len(missing_keep_refs)}")
        for rk, mk in missing_keep_refs[:5]:
            print(f"  {rk}: {mk}")
        assert not missing_keep_refs
        print(f"  PASS: every reference carries the full keep-list")
        print()

        print(f"References with confidence key present: {confidence_present_refs} / {len(refs)}")
        assert confidence_present_refs == len(refs)
        print(f"  PASS: confidence key present on every reference (value may be null)")
        print()

        print(f"References with trend_signal is None (W2-only run): "
              f"{trend_null_refs} / {len(refs)}")
        assert trend_null_refs == len(refs)
        print(f"  PASS: trend_signal null (not 'No prior data' string) on single-CSV run")
        print()

        # DJ config shape
        leaked_dj = []
        dj_trend_null = 0
        dj_confidence_null = 0
        for cfg_name, cfg in dj.items():
            actual = set(cfg.keys())
            leaked = RIPPED_FIELDS & actual
            if leaked:
                leaked_dj.append((cfg_name, sorted(leaked)))
            if cfg.get("trend_signal") is None:
                dj_trend_null += 1
            if cfg.get("confidence") is None:
                dj_confidence_null += 1

        print(f"DJ configs with leaked ripped fields: {len(leaked_dj)}")
        for cn, lk in leaked_dj[:5]:
            print(f"  {cn}: {lk}")
        assert not leaked_dj
        print(f"  PASS: no ripped fields leak into DJ config entries")
        print()

        print(f"DJ configs with trend_signal null: {dj_trend_null} / {len(dj)}")
        print(f"DJ configs with confidence null: {dj_confidence_null} / {len(dj)}")
        assert dj_trend_null == len(dj)
        assert dj_confidence_null == len(dj)
        print(f"  PASS: DJ configs always carry null trend/confidence")
        print()

        # bucket_key lowercase audit
        bad_case_keys = []
        total_buckets = 0
        for rd in refs.values():
            for bk in rd.get("buckets", {}).keys():
                total_buckets += 1
                if bk != bk.lower():
                    bad_case_keys.append(bk)
        print(f"Total buckets: {total_buckets}")
        print(f"Mixed-case bucket_keys: {len(bad_case_keys)}")
        assert not bad_case_keys
        print(f"  PASS: all bucket_keys lowercase")
        print()

        # Cache file byte sanity (exists, non-trivial size)
        size = cache_path.stat().st_size
        print(f"Cache file size: {size} bytes")
        assert size > 1000
        print(f"  PASS: cache file written")
        print()

        print("ALL PART B CHECKS PASSED.")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
