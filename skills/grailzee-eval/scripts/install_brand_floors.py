"""Phase A.3 installer for brand_floors.json.

Writes ``state/brand_floors.json`` with the five confirmed brand
entries from schema v1.1 §1 Item 1 (Rolex, Tudor, Breitling, Cartier,
Omega) and populates ``defaulted_fields`` with exactly the five
``brands.<Name>.floor_pct`` paths. Structural fields ``tradeable`` and
``asset_class`` are intentionally NOT in ``defaulted_fields``: the
brand is being declared as part of the tradeable universe, and only
the floor_pct is the strategic value strategy will re-set over time.
Per v1.1 §1 Item 1 verbatim.

Refuses to overwrite an existing file unless ``--force`` is passed.
The existing file would typically carry strategy-set floor_pct values;
silent overwrite would destroy that.

Usage:
    python3 scripts/install_brand_floors.py                # writes to workspace state
    python3 scripts/install_brand_floors.py --target PATH  # custom target
    python3 scripts/install_brand_floors.py --force        # allow overwrite
    python3 scripts/install_brand_floors.py --dry-run      # no write

Exit codes:
    0  installed (or dry-run preview ok)
    1  target exists and --force was not passed
    2  filesystem error during atomic write
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
if str(V2_ROOT) not in sys.path:
    sys.path.insert(0, str(V2_ROOT))

from scripts.config_helper import write_config
from scripts.grailzee_common import config_path, get_tracer

tracer = get_tracer(__name__)

BRAND_FLOORS_NAME = "brand_floors.json"
BRAND_FLOORS_SCHEMA_VERSION = 1
UPDATED_BY = "phase_a_install"

# Verbatim from grailzee_schema_design_v1_1.md §1 Item 1. Every floor_pct
# is strategy-tunable; tradeable and asset_class are structural
# declarations that strategy may edit but do not track as "defaulted."
BRAND_FLOORS_FACTORY_CONTENT: dict = {
    "schema_version": BRAND_FLOORS_SCHEMA_VERSION,
    "brands": {
        "Rolex":     {"floor_pct": 5.0,  "tradeable": True, "asset_class": "watch"},
        "Tudor":     {"floor_pct": 10.0, "tradeable": True, "asset_class": "watch"},
        "Breitling": {"floor_pct": 10.0, "tradeable": True, "asset_class": "watch"},
        "Cartier":   {"floor_pct": 10.0, "tradeable": True, "asset_class": "watch"},
        "Omega":     {"floor_pct": 8.0,  "tradeable": True, "asset_class": "watch"},
    },
}


def _floor_pct_paths(content: dict) -> list[str]:
    """Return the sorted list of ``brands.<Name>.floor_pct`` paths.

    Walks only the ``brands`` subtree and keys on ``floor_pct``. Other
    per-brand fields (tradeable, asset_class) are structural; per v1.1
    Item 1 they are excluded from ``defaulted_fields``. Using a
    purpose-built walker rather than ``config_helper.leaf_paths`` keeps
    the exclusion explicit at the call site — a future reader sees
    immediately why tradeable/asset_class are absent.

    Precondition: called on installer-trusted content (i.e. a dict
    built from ``BRAND_FLOORS_FACTORY_CONTENT`` or a validated
    structurally equivalent dict). Malformed inputs — non-dict brand
    entries, brands missing ``floor_pct`` — are silently skipped; they
    cannot arise from the installer's own content constant. Do not
    reuse this helper on strategy-edited live files without adding
    raise-on-malformed semantics.
    """
    brands = content.get("brands")
    if not isinstance(brands, dict):
        return []
    paths: list[str] = []
    for brand_name, brand_entry in brands.items():
        if not isinstance(brand_entry, dict):
            continue
        if "floor_pct" in brand_entry:
            paths.append(f"brands.{brand_name}.floor_pct")
    return sorted(paths)


def install(target: str, *, force: bool, dry_run: bool) -> int:
    """Install the config file. Returns the intended exit code."""
    with tracer.start_as_current_span("install_brand_floors") as span:
        span.set_attribute("target", target)
        span.set_attribute("force", force)
        span.set_attribute("dry_run", dry_run)

        exists = os.path.exists(target)
        span.set_attribute("target_exists", exists)

        if exists and not force:
            print(
                f"Refusing to overwrite existing {target}. "
                f"Pass --force if you really mean it.",
                file=sys.stderr,
            )
            span.set_attribute("outcome", "refused_existing")
            return 1

        content = json.loads(json.dumps(BRAND_FLOORS_FACTORY_CONTENT))
        defaulted = _floor_pct_paths(content)
        span.set_attribute("defaulted_count", len(defaulted))
        span.set_attribute("brand_count", len(content["brands"]))

        if dry_run:
            print(
                json.dumps(
                    {
                        "target": target,
                        "would_write": True,
                        "defaulted_fields": defaulted,
                        "schema_version": content["schema_version"],
                        "brand_count": len(content["brands"]),
                    },
                    indent=2,
                )
            )
            span.set_attribute("outcome", "dry_run")
            return 0

        try:
            write_config(
                path=target,
                content=content,
                defaulted_fields=defaulted,
                updated_by=UPDATED_BY,
            )
        except OSError as exc:
            print(f"Filesystem error writing {target}: {exc}", file=sys.stderr)
            span.set_attribute("outcome", "io_error")
            return 2

        print(f"Wrote {target} with {len(defaulted)} defaulted fields.")
        span.set_attribute("outcome", "written")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        default=None,
        help=(
            "Target path for brand_floors.json. "
            "Defaults to WORKSPACE_STATE_PATH/brand_floors.json."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing target file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the intended payload without writing.",
    )
    args = parser.parse_args()

    target = args.target or config_path(BRAND_FLOORS_NAME)
    return install(target, force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
