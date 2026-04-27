"""Shared fixture builders for grailzee-cowork tests.

These helpers build the minimum disk state the OUTBOUND and INBOUND
bundle paths need: a fake GrailzeeData tree (state/, reports_csv/,
bundles/) with plausible, schema-valid content.

Kept deliberately small. Each test tweaks what it cares about; the
builder fills in the rest.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

FAKE_CYCLE_ID = "cycle_2026-04"
FAKE_PRIOR_CYCLE_ID = "cycle_2026-03"

CACHE_SCHEMA_VERSION = 2


def _default_cache(cycle_id: str) -> dict[str, Any]:
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "cycle_id": cycle_id,
        "generated_at": "2026-04-15T12:00:00Z",
        "references": {
            "79830RB": {
                "brand": "Tudor",
                "model": "BB GMT Pepsi",
                "reference": "79830RB",
                "max_buy_nr": 2910,
                "signal": "Strong",
            },
            "210.30": {
                "brand": "Omega",
                "model": "SMD 300M",
                "reference": "210.30",
                "max_buy_nr": 4200,
                "signal": "Normal",
            },
        },
    }


def _default_cycle_focus(cycle_id: str) -> dict[str, Any]:
    return {
        "cycle_id": cycle_id,
        "focus_refs": ["79830RB", "210.30"],
        "themes": ["GMT steel", "SMD ceramic"],
    }


def _default_monthly_goals() -> dict[str, Any]:
    return {
        "month": "2026-04",
        "revenue_target": 40000,
        "deal_count_target": 6,
    }


def _monthly_goals_with_return_pct(monthly_return_pct: float = 0.12) -> dict[str, Any]:
    """Monthly goals fixture with monthly_return_pct set.

    ``monthly_return_pct`` is a fraction in (0, 1) exclusive. Default 0.12
    (12%). Used to exercise the optional field added in Step 0 Schema 1.
    """
    return {
        "month": "2026-05",
        "revenue_target": 45000,
        "deal_count_target": 7,
        "monthly_return_pct": monthly_return_pct,
    }


def _default_quarterly_allocation() -> dict[str, Any]:
    return {
        "quarter": "2026-Q2",
        "allocations": {"Tudor": 0.35, "Omega": 0.25, "Rolex": 0.20, "other": 0.20},
    }


def _default_run_history(cycle_id: str, with_boundary: bool) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    if with_boundary:
        # Prior entry with a DIFFERENT cycle_id — build_bundle's boundary
        # detector compares the current cache cycle_id against the most recent
        # DIFFERENT cycle_id in run history (not against its own most recent
        # entry, which may have been written by the agent earlier this cycle).
        entries.append(
            {
                "cycle_id": FAKE_PRIOR_CYCLE_ID,
                "generated_at": "2026-03-18T10:00:00Z",
            }
        )
    entries.append({"cycle_id": cycle_id, "generated_at": "2026-04-15T12:00:00Z"})
    return {"runs": entries}


_SHORTLIST_HEADER = (
    "brand,reference,model,dial_numerals,auction_type,dial_color,named_special,"
    "signal,median,max_buy_nr,max_buy_res,st_pct,volume,risk_nr,"
    "capital_required_nr,capital_required_res,expected_net_at_median_nr,"
    "expected_net_at_median_res,trend_signal,trend_median_change,trend_median_pct,"
    "momentum_score,momentum_label,confidence_trades,confidence_profitable,"
    "confidence_win_rate,confidence_avg_roi,confidence_avg_premium,"
    "confidence_last_trade,keep"
)

_SHORTLIST_DEFAULT_ROW = (
    "Tudor,79830RB,BB GMT Pepsi,Arabic,nr,black,,Strong,3200,2910,2860,75.0,12,8.5,"
    "2959,3009,241,191,,,,,,,,,,,,"
)

_DEFAULT_SHORTLIST_CSV = f"{_SHORTLIST_HEADER}\n{_SHORTLIST_DEFAULT_ROW}\n"


def build_fake_grailzee_tree(
    root: Path,
    *,
    cycle_id: str = FAKE_CYCLE_ID,
    with_boundary: bool = False,
    cache: dict[str, Any] | None = None,
    cycle_focus: dict[str, Any] | None = None,
    monthly_goals: dict[str, Any] | None = None,
    quarterly_allocation: dict[str, Any] | None = None,
    run_history: dict[str, Any] | None = None,
    ledger_rows: list[dict[str, Any]] | None = None,
    report_csv_contents: dict[str, str] | None = None,
    shortlist_csv_contents: str | None = None,
) -> dict[str, Path]:
    """Create a fake GrailzeeData tree under `root`. Return map of key paths."""
    state = root / "state"
    output = root / "output"
    briefs = output / "briefs"
    reports_csv = root / "reports_csv"
    bundles = root / "bundles"
    for d in (state, briefs, reports_csv, bundles):
        d.mkdir(parents=True, exist_ok=True)

    cache_path = state / "analysis_cache.json"
    cache_path.write_text(json.dumps(cache or _default_cache(cycle_id)))

    focus_path = state / "cycle_focus.json"
    focus_path.write_text(json.dumps(cycle_focus or _default_cycle_focus(cycle_id)))

    monthly_path = state / "monthly_goals.json"
    monthly_path.write_text(json.dumps(monthly_goals or _default_monthly_goals()))

    quarterly_path = state / "quarterly_allocation.json"
    quarterly_path.write_text(
        json.dumps(quarterly_allocation or _default_quarterly_allocation())
    )

    run_history_path = state / "run_history.json"
    run_history_path.write_text(
        json.dumps(run_history or _default_run_history(cycle_id, with_boundary))
    )

    ledger_path = state / "trade_ledger.csv"
    if ledger_rows is None:
        ledger_path.write_text(
            "cycle_id,reference,net_profit,roi_pct\n"
            f"{cycle_id},79830RB,340,14.5\n"
            f"{cycle_id},210.30,820,22.0\n"
        )
    else:
        header = "cycle_id,reference,net_profit,roi_pct\n"
        lines = [
            f"{r['cycle_id']},{r['reference']},{r['net_profit']},{r['roi_pct']}"
            for r in ledger_rows
        ]
        ledger_path.write_text(header + "\n".join(lines) + ("\n" if lines else ""))

    if report_csv_contents is None:
        report_csv_contents = {
            "grailzee_2026-04-15.csv": (
                "brand,model,reference,sale_price,sale_date\n"
                "Tudor,BB GMT Pepsi,79830RB,3200,2026-04-10\n"
                "Omega,SMD 300M,210.30,4400,2026-04-11\n"
            ),
            "grailzee_2026-04-02.csv": (
                "brand,model,reference,sale_price,sale_date\n"
                "Tudor,BB GMT Pepsi,79830RB,3100,2026-04-01\n"
            ),
        }
    for name, contents in report_csv_contents.items():
        (reports_csv / name).write_text(contents)

    shortlist_path = state / f"cycle_shortlist_{cycle_id}.csv"
    shortlist_path.write_text(
        shortlist_csv_contents if shortlist_csv_contents is not None
        else _DEFAULT_SHORTLIST_CSV
    )

    return {
        "root": root,
        "state": state,
        "output": output,
        "briefs": briefs,
        "reports_csv": reports_csv,
        "bundles": bundles,
        "cache": cache_path,
        "cycle_focus": focus_path,
        "monthly_goals": monthly_path,
        "quarterly_allocation": quarterly_path,
        "run_history": run_history_path,
        "ledger": ledger_path,
        "shortlist": shortlist_path,
    }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_inbound_bundle_zip(
    zip_path: Path,
    *,
    cycle_id: str = FAKE_CYCLE_ID,
    payloads: dict[str, Any] | None = None,
    manifest_override: dict[str, Any] | None = None,
    extra_entries: dict[str, bytes] | None = None,
    omit_manifest: bool = False,
) -> Path:
    """Build an INBOUND-shaped .zip at `zip_path`. Returns `zip_path`.

    `payloads` maps role → JSON-serializable content. Default payloads
    cover all three INBOUND roles (cycle_focus, monthly_goals,
    quarterly_allocation).

    `manifest_override`, if provided, replaces the computed manifest
    entirely (used to test malformed-manifest rejection).

    `extra_entries` inject raw bytes at arbitrary zip paths (used to
    test path-traversal and name-whitelist rejection).
    """
    if payloads is None:
        payloads = {
            "cycle_focus": _default_cycle_focus(cycle_id),
            "monthly_goals": _default_monthly_goals(),
            "quarterly_allocation": _default_quarterly_allocation(),
        }

    role_to_filename = {
        "cycle_focus": "cycle_focus.json",
        "monthly_goals": "monthly_goals.json",
        "quarterly_allocation": "quarterly_allocation.json",
    }

    files_meta: list[dict[str, Any]] = []
    encoded_payloads: dict[str, bytes] = {}
    for role, content in payloads.items():
        filename = role_to_filename.get(role, f"{role}.json")
        data = json.dumps(content).encode("utf-8")
        encoded_payloads[filename] = data
        files_meta.append(
            {
                "path": filename,
                "role": role,
                "sha256": _sha256(data),
                "size_bytes": len(data),
            }
        )

    manifest = manifest_override or {
        "manifest_version": 1,
        "bundle_kind": "inbound",
        "generated_at": "2026-04-15T13:00:00Z",
        "cycle_id": cycle_id,
        "source": "chat-strategy-session",
        "scope": {"month_boundary": False, "quarter_boundary": False},
        "files": files_meta,
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if not omit_manifest:
            zf.writestr("manifest.json", json.dumps(manifest))
        for filename, data in encoded_payloads.items():
            zf.writestr(filename, data)
        for arcname, data in (extra_entries or {}).items():
            zf.writestr(arcname, data)

    return zip_path


def read_zip_manifest(zip_path: Path) -> dict[str, Any]:
    """Extract and decode manifest.json from a bundle .zip."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        return json.loads(zf.read("manifest.json").decode("utf-8"))


# ─── Phase 24b: strategy_output.json fixtures ─────────────────────────

def make_strategy_cycle_focus(
    *,
    reference: str = "79830RB",
    brand: str = "Tudor",
    model: str = "BB GMT Pepsi",
) -> dict[str, Any]:
    """Default schema-valid cycle_focus block for strategy_output payloads."""
    return {
        "targets": [
            {
                "reference": reference,
                "brand": brand,
                "model": model,
                "cycle_reason": "Core performer with momentum signal",
                "max_buy_override": None,
            }
        ],
        "capital_target": 15000,
        "volume_target": 5,
        "target_margin_fraction": 0.05,
        "brand_emphasis": [brand],
        "brand_pullback": [],
        "notes": "Session default cycle focus.",
    }


def make_strategy_monthly_goals() -> dict[str, Any]:
    return {
        "month": "2026-04",
        "revenue_target": 40000,
        "volume_target": 12,
        "platform_mix": {"Grailzee": 60, "eBay": 30, "Chrono24": 10},
        "focus_notes": "Premium performers on Grailzee.",
        "review_notes": "March hit volume; missed revenue.",
    }


def make_strategy_quarterly_allocation() -> dict[str, Any]:
    return {
        "quarter": "2026-Q2",
        "capital_allocation": {"Tudor": 25000, "Rolex": 40000},
        "inventory_mix_target": {"Strong": 70, "Normal": 30},
        "review_notes": "Rebalancing into Tudor.",
    }


def make_strategy_config_updates(
    *,
    include: tuple[str, ...] = ("signal_thresholds",),
) -> dict[str, Any]:
    """Return a config_updates block with `include` sub-configs populated.

    Each sub-config carries the D5 metadata envelope plus one dummy field.
    """
    template = {
        "version": 2,
        "updated_at": "2026-04-19T12:00:00Z",
        "updated_by": "strategy_session",
        "notes": "Session retune.",
        "placeholder_field": 1.5,
    }
    block: dict[str, Any] = {
        "signal_thresholds": None,
        "scoring_thresholds": None,
        "momentum_thresholds": None,
        "window_config": None,
        "premium_config": None,
        "margin_config": None,
        "change_notes": "Test retune.",
    }
    for key in include:
        block[key] = dict(template)
    return block


def make_strategy_output(
    *,
    cycle_id: str = FAKE_CYCLE_ID,
    session_mode: str = "cycle_planning",
    include_cycle_focus: bool = True,
    include_monthly: bool = False,
    include_quarterly: bool = False,
    include_configs: tuple[str, ...] = (),
    cycle_brief_md: str = "# Cycle Brief\n\nFocus: Tudor.",
    produced_by: str = "grailzee-strategy/0.1.0",
    generated_at: str = "2026-04-19T10:30:00Z",
) -> dict[str, Any]:
    """Build a schema-valid strategy_output payload.

    Defaults to a minimal cycle_planning payload with only cycle_focus
    populated. Flags toggle the other three decision sections on.
    """
    decisions: dict[str, Any] = {
        "cycle_focus": make_strategy_cycle_focus() if include_cycle_focus else None,
        "monthly_goals": make_strategy_monthly_goals() if include_monthly else None,
        "quarterly_allocation": (
            make_strategy_quarterly_allocation() if include_quarterly else None
        ),
        "config_updates": (
            make_strategy_config_updates(include=include_configs)
            if include_configs
            else None
        ),
    }
    return {
        "strategy_output_version": 1,
        "generated_at": generated_at,
        "cycle_id": cycle_id,
        "session_mode": session_mode,
        "produced_by": produced_by,
        "decisions": decisions,
        "session_artifacts": {"cycle_brief_md": cycle_brief_md},
    }


def write_strategy_output(path: Path, payload: dict[str, Any]) -> Path:
    """Serialize a payload to disk (indent=2 JSON). Returns path."""
    path.write_text(json.dumps(payload, indent=2))
    return path
