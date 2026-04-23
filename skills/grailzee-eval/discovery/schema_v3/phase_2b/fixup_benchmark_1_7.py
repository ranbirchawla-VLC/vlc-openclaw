"""Part §1.7; analytical-quality benchmark prep for operator read.

Picks 10 references across the signal range, dumps side-by-side v2 vs v3
(post-fixup) shape. v2 reference comes from the live Drive v2 cache
(W1.5 source, schema_version=2). v3 reference comes from a fresh W1+W2
regeneration under the post-fixup code path.

Window mismatch is acceptable for a SHAPE comparison; the operator is
reading to judge "less useful for strategy session," which is about
field set and presentation, not market values.
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

DRIVE_ROOT = (
    "/Users/ranbirchawla/Library/CloudStorage/"
    "GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/"
    "Vardalux Shared Drive/GrailzeeData"
)
W1 = Path(DRIVE_ROOT) / "reports_csv" / "grailzee_2026-04-06.csv"
W2 = Path(DRIVE_ROOT) / "reports_csv" / "grailzee_2026-04-21.csv"
V2_CACHE_PATH = Path(DRIVE_ROOT) / "state" / "analysis_cache.json"
FIXTURES = V2_ROOT / "tests" / "fixtures"
NAME_CACHE = FIXTURES / "name_cache_seed.json"

# 10 references chosen to span the signal range + cover DJ config layer
TARGET_REFS = [
    "79830RB",     # Tudor BB GMT Pepsi (high-volume Strong in v2)
    "126300",      # Rolex DJ 41 (DJ config parent)
    "126334",      # Rolex DJ 41 Fluted (2nd highest volume)
    "79360N",      # Tudor BB Chrono
    "126710BLNR",  # Rolex GMT-Master II Batman
    "124060",      # Rolex Submariner No-Date
    "28500",       # Tudor BB 58 (per-piece inventory joins)
    "A17320",      # Breitling SO Heritage
    "116500LN",    # Rolex Daytona ceramic
    "215.30.44.22.01.002",  # Omega Seamaster PO deep dive
]


def pick_ref(cache: dict, target: str) -> dict | None:
    """Find a reference in a cache by exact key match or by `reference` field."""
    refs = cache.get("references", {})
    if target in refs:
        return refs[target]
    for key, entry in refs.items():
        if entry.get("reference") == target:
            return entry
    return None


def main() -> int:
    print("# §1.7 analytical-quality benchmark (v2 vs v3 post-fixup)")
    print()
    print("**Window note**: v2 is Drive's live cache (source W1.5 = 2026-03-23).")
    print("v3 is fresh W1+W2 regeneration under post-fixup code. Window mismatch")
    print("is tolerated for shape comparison; operator reads for \"less useful for")
    print("strategy session\" judgment, not market-value drift.")
    print()

    v2_cache = json.loads(V2_CACHE_PATH.read_text())
    print(f"v2 cache: schema_version={v2_cache.get('schema_version')}, "
          f"refs={len(v2_cache.get('references', {}))}, "
          f"source={v2_cache.get('source_report')}")

    tmp_root = Path(tempfile.mkdtemp(prefix="fixup_bench_1_7_"))
    try:
        state_dir = tmp_root / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        output_dir = tmp_root / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        ledger_path = state_dir / "trade_ledger.csv"
        ledger_path.write_text(
            "buy_date,sell_date,buy_cycle_id,sell_cycle_id,"
            "brand,reference,account,buy_price,sell_price\n"
        )
        cache_path = state_dir / "analysis_cache.json"

        w1_copy = tmp_root / "grailzee_2026-04-06.csv"
        w2_copy = tmp_root / "grailzee_2026-04-21.csv"
        shutil.copy2(W1, w1_copy)
        shutil.copy2(W2, w2_copy)

        run_analysis(
            csv_paths=[str(w2_copy), str(w1_copy)],
            output_folder=str(output_dir),
            ledger_path=str(ledger_path),
            cache_path=str(cache_path),
            backup_path=str(state_dir / "backup"),
            name_cache_path=str(NAME_CACHE),
            cycle_focus_path=str(state_dir / "cycle_focus.json"),
        )

        v3_cache = json.loads(cache_path.read_text())
        print(f"v3 cache (fresh): schema_version={v3_cache.get('schema_version')}, "
              f"refs={len(v3_cache.get('references', {}))}, "
              f"source={v3_cache.get('source_report')}")
        print()

        for ref_id in TARGET_REFS:
            v2_ref = pick_ref(v2_cache, ref_id)
            v3_ref = pick_ref(v3_cache, ref_id)
            print(f"## {ref_id}")
            print()
            if v2_ref is None:
                print(f"  v2: (not in v2 cache)")
            else:
                print(f"  v2 ({v2_ref.get('brand','?')} {v2_ref.get('model','?')}):")
                for k in sorted(v2_ref.keys()):
                    v = v2_ref[k]
                    if isinstance(v, dict):
                        # Compact dict
                        v_short = json.dumps(v, default=str)[:200]
                        print(f"    {k}: {v_short}")
                    else:
                        print(f"    {k}: {v}")
            print()
            if v3_ref is None:
                print(f"  v3: (not in v3 cache)")
            else:
                print(f"  v3 ({v3_ref.get('brand','?')} {v3_ref.get('model','?')}):")
                for k in sorted(v3_ref.keys()):
                    v = v3_ref[k]
                    if k == "buckets":
                        print(f"    buckets: ({len(v)} buckets)")
                        for bk, bd in list(v.items())[:6]:
                            sig = bd.get("signal", "?")
                            med = bd.get("median")
                            vol = bd.get("volume", 0)
                            st = bd.get("st_pct")
                            ns = bd.get("named_special")
                            print(f"      {bk}: signal={sig} median={med} "
                                  f"volume={vol} st_pct={st} "
                                  f"named_special={ns}")
                        if len(v) > 6:
                            print(f"      ... (+{len(v)-6} more)")
                    elif isinstance(v, dict):
                        v_short = json.dumps(v, default=str)[:200]
                        print(f"    {k}: {v_short}")
                    else:
                        print(f"    {k}: {v}")
            print()
            print("---")
            print()
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
