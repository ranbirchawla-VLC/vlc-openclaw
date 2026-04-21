"""Phase A.5 installer for quarterly_allocation.json.

Writes ``<STATE_PATH>/quarterly_allocation.json`` with starter values
supplied by Ranbir at the building-chat handoff (total_capital=45000).
Empty objects for brand_allocations/category_allocations are valid
no-nulls values per v1.1 §2 (empty collection, not null). Sentinel
``quarter="starter"`` is a placeholder the strategy session overwrites
at the first quarterly commit.

Drive-backed (STATE_PATH), not workspace state. Cowork apply writes
here at every quarterly commit, so the file shares its write lifecycle
with the other cycle/monthly/quarterly configs. Diverges from
A.2/A.3/A.4, which target workspace state for repo-committed configs.

Refuses to overwrite an existing file unless ``--force`` is passed.
The existing file would typically carry strategy-set values; silent
overwrite would destroy that.

Usage:
    python3 scripts/install_quarterly_allocation.py                # writes to STATE_PATH
    python3 scripts/install_quarterly_allocation.py --target PATH  # custom target
    python3 scripts/install_quarterly_allocation.py --force        # allow overwrite
    python3 scripts/install_quarterly_allocation.py --dry-run      # no write

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

from scripts.config_helper import MANAGED_KEYS, leaf_paths, write_config
from scripts.grailzee_common import STATE_PATH, get_tracer

tracer = get_tracer(__name__)

QUARTERLY_ALLOCATION_NAME = "quarterly_allocation.json"
QUARTERLY_ALLOCATION_SCHEMA_VERSION = 1
UPDATED_BY = "phase_a_install"

# Sentinel quarter; strategy overwrites at first quarterly commit.
STARTER_QUARTER = "starter"

QUARTERLY_ALLOCATION_FACTORY_CONTENT: dict = {
    "schema_version": QUARTERLY_ALLOCATION_SCHEMA_VERSION,
    "quarter": STARTER_QUARTER,
    "total_capital": 45000,
    "brand_allocations": {},
    "category_allocations": {},
}


def _defaulted_fields_for_quarterly(content: dict) -> list[str]:
    """Return sorted defaulted-field paths for quarterly_allocation.

    `leaf_paths` recurses into dicts and treats a non-dict as the leaf.
    An empty dict recurses to nothing and gets dropped entirely, which
    would lose ``brand_allocations`` and ``category_allocations`` from
    defaulted_fields. Strategy edits those two as whole units (by brand,
    by category), so we want them as parent paths, not as "nothing"
    because they happen to start empty. Walk top-level keys and inject
    any empty-dict path leaf_paths missed.
    """
    paths = set(leaf_paths(content))
    for key, value in content.items():
        if key in MANAGED_KEYS or key == "schema_version":
            continue
        if isinstance(value, dict) and not value:
            paths.add(key)
    return sorted(paths)


def install(target: str, *, force: bool, dry_run: bool) -> int:
    """Install the config file. Returns the intended exit code."""
    with tracer.start_as_current_span("install_quarterly_allocation") as span:
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

        content = json.loads(json.dumps(QUARTERLY_ALLOCATION_FACTORY_CONTENT))
        defaulted = sorted(_defaulted_fields_for_quarterly(content))
        span.set_attribute("defaulted_count", len(defaulted))

        if dry_run:
            print(
                json.dumps(
                    {
                        "target": target,
                        "would_write": True,
                        "defaulted_fields": defaulted,
                        "schema_version": content["schema_version"],
                        "quarter": content["quarter"],
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
            "Target path for quarterly_allocation.json. "
            "Defaults to STATE_PATH/quarterly_allocation.json (Drive-backed)."
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

    target = args.target or f"{STATE_PATH}/{QUARTERLY_ALLOCATION_NAME}"
    return install(target, force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
