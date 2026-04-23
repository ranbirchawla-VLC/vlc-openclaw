"""Part A; W1+W2 union logic validation for 2b fixup.

Per v1 prompt §6 Part A + fixup Part A new verification.
Load W1+W2, build buckets, score, check shape.
Prints a findings block to stdout; write to fixup_part_a_findings.md by
redirecting or piping.
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import Counter

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent.parent.parent  # skills/grailzee-eval/
sys.path.insert(0, str(V2_ROOT))

from scripts.ingest import load_and_canonicalize  # noqa: E402
from scripts.analyze_buckets import run as analyze_run  # noqa: E402

DRIVE_ROOT = (
    "/Users/ranbirchawla/Library/CloudStorage/"
    "GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/"
    "Vardalux Shared Drive/GrailzeeData"
)
W1 = Path(DRIVE_ROOT) / "reports_csv" / "grailzee_2026-04-06.csv"
W2 = Path(DRIVE_ROOT) / "reports_csv" / "grailzee_2026-04-21.csv"

KEEP_LIST = {
    "brand", "model", "reference", "named",
    "trend_signal", "trend_median_change", "trend_median_pct",
    "momentum", "confidence", "buckets",
}
RIPPED = {
    "premium_vs_market_pct", "premium_vs_market_sale_count",
    "realized_premium_pct", "realized_premium_trade_count",
    "median", "max_buy_nr", "max_buy_res", "risk_nr", "signal",
    "volume", "st_pct", "condition_mix",
    "capital_required_nr", "capital_required_res",
    "expected_net_at_median_nr", "expected_net_at_median_res",
}


def main() -> int:
    print("# Part A; W1+W2 union logic validation (2b fixup)")
    print()
    assert W1.exists(), f"W1 missing: {W1}"
    assert W2.exists(), f"W2 missing: {W2}"

    rows, summary = load_and_canonicalize([W1, W2])
    print(f"Source rows: {summary.source_rows_total}")
    print(f"Canonical rows: {summary.canonical_rows_emitted}")
    print()

    # Score via write_cache call path up to the all_results layer.
    # Pass name_cache=None so analyze_buckets uses the default.
    all_results = analyze_run(rows, None)
    refs = all_results["references"]
    dj = all_results["dj_configs"]

    total_refs = len(refs)
    total_buckets = sum(len(rd.get("buckets", {})) for rd in refs.values())
    n3_buckets = sum(
        1 for rd in refs.values()
        for bd in rd.get("buckets", {}).values()
        if (bd.get("volume") or 0) >= 3
    )
    scored_buckets = sum(
        1 for rd in refs.values()
        for bd in rd.get("buckets", {}).values()
        if bd.get("signal") != "Low data"
    )
    eligible_refs_n3 = sum(
        1 for rd in refs.values()
        if any(
            (bd.get("volume") or 0) >= 3
            for bd in rd.get("buckets", {}).values()
        )
    )
    eligible_refs_nonlow = sum(
        1 for rd in refs.values()
        if any(
            bd.get("signal") != "Low data"
            for bd in rd.get("buckets", {}).values()
        )
    )
    print(f"Total references: {total_refs}")
    print(f"Total buckets: {total_buckets}")
    print(f"Buckets with volume >= 3: {n3_buckets}")
    print(f"Scored buckets (signal != Low data): {scored_buckets}")
    print(f"References with >=1 n>=3 bucket: {eligible_refs_n3}")
    print(f"References with >=1 signal!=Low-data bucket: {eligible_refs_nonlow}")
    print()

    # bucket_key lowercase audit
    bad_case = []
    for rd in refs.values():
        for bk in rd.get("buckets", {}).keys():
            if bk != bk.lower():
                bad_case.append(bk)
    print(f"Mixed-case bucket_keys: {len(bad_case)}")
    if bad_case[:5]:
        print(f"  samples: {bad_case[:5]}")
    print()

    # Shape audit: every reference entry carries exactly KEEP_LIST after
    # write_cache runs. Here we are pre-write_cache, so entries may have
    # fewer fields (write_cache adds trend/momentum/confidence). Verify
    # the pre-write shape has: brand, model, reference, named, buckets.
    pre_write_keep = {"brand", "model", "reference", "named", "buckets"}
    pre_write_bad = []
    for ref_key, rd in refs.items():
        actual = set(rd.keys())
        missing = pre_write_keep - actual
        leaked_ripped = RIPPED & actual
        if missing or leaked_ripped:
            pre_write_bad.append(
                (ref_key, sorted(missing), sorted(leaked_ripped))
            )
    print(f"References with missing keep-list or leaked ripped fields (pre-write): {len(pre_write_bad)}")
    for ref_key, missing, leaked in pre_write_bad[:5]:
        print(f"  {ref_key}: missing={missing} leaked={leaked}")
    print()

    # Signal distribution across buckets
    sig_counter: Counter[str] = Counter()
    for rd in refs.values():
        for bd in rd.get("buckets", {}).values():
            sig_counter[bd.get("signal", "<missing>")] += 1
    print("Signal distribution across buckets:")
    for sig, count in sig_counter.most_common():
        print(f"  {sig}: {count}")
    print()

    # DJ config audit
    print(f"DJ configs: {len(dj)}")
    for cfg_name, cfg in dj.items():
        bc = len(cfg.get("buckets", {}))
        print(f"  {cfg_name}: {bc} buckets")
    print()

    # Phase 2b I.4 comparison point: W1+W2 union had 722 eligible buckets
    # (n >= 3), 504 refs with eligible bucket. Verify within 3% tolerance.
    prior_eligible_buckets = 722
    prior_eligible_refs = 504
    eb_pct = abs(n3_buckets - prior_eligible_buckets) / prior_eligible_buckets * 100
    er_pct = abs(eligible_refs_n3 - prior_eligible_refs) / prior_eligible_refs * 100
    print(f"n>=3 bucket delta vs Phase 2b I.4: "
          f"{n3_buckets} vs {prior_eligible_buckets} ({eb_pct:.1f}%)")
    print(f"n>=3 ref delta vs Phase 2b I.4: "
          f"{eligible_refs_n3} vs {prior_eligible_refs} ({er_pct:.1f}%)")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
