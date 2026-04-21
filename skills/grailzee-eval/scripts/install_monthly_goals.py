"""Phase A.5 installer for monthly_goals.json.

Writes ``<STATE_PATH>/monthly_goals.json`` with starter values supplied
by Ranbir at the building-chat handoff (capital_target=30000,
volume_target=8). Empty arrays for brand_emphasis/brand_pullback are
valid no-nulls values per v1.1 §2. Sentinel ``month="starter"`` is a
placeholder the strategy session overwrites at the first monthly
commit.

Drive-backed (STATE_PATH), not workspace state. Cowork apply writes
here at every monthly commit, so the file shares its write lifecycle
with the other cycle/monthly/quarterly configs. Diverges from
A.2/A.3/A.4, which target workspace state for repo-committed configs.

Refuses to overwrite an existing file unless ``--force`` is passed.
The existing file would typically carry strategy-set values; silent
overwrite would destroy that.

Usage:
    python3 scripts/install_monthly_goals.py                # writes to STATE_PATH
    python3 scripts/install_monthly_goals.py --target PATH  # custom target
    python3 scripts/install_monthly_goals.py --force        # allow overwrite
    python3 scripts/install_monthly_goals.py --dry-run      # no write

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

from scripts.config_helper import leaf_paths, write_config
from scripts.grailzee_common import STATE_PATH, get_tracer

tracer = get_tracer(__name__)

MONTHLY_GOALS_NAME = "monthly_goals.json"
MONTHLY_GOALS_SCHEMA_VERSION = 1
UPDATED_BY = "phase_a_install"

# Sentinel month; strategy overwrites at first monthly commit.
STARTER_MONTH = "starter"

MONTHLY_GOALS_FACTORY_CONTENT: dict = {
    "schema_version": MONTHLY_GOALS_SCHEMA_VERSION,
    "month": STARTER_MONTH,
    "capital_target": 30000,
    "volume_target": 8,
    "brand_emphasis": [],
    "brand_pullback": [],
}


def install(target: str, *, force: bool, dry_run: bool) -> int:
    """Install the config file. Returns the intended exit code."""
    with tracer.start_as_current_span("install_monthly_goals") as span:
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

        content = json.loads(json.dumps(MONTHLY_GOALS_FACTORY_CONTENT))
        # Flat structure with array leaves; leaf_paths returns the right
        # answer directly. No collapse needed (A.4 keyword_filters pattern).
        defaulted = sorted(leaf_paths(content))
        span.set_attribute("defaulted_count", len(defaulted))

        if dry_run:
            print(
                json.dumps(
                    {
                        "target": target,
                        "would_write": True,
                        "defaulted_fields": defaulted,
                        "schema_version": content["schema_version"],
                        "month": content["month"],
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
            "Target path for monthly_goals.json. "
            "Defaults to STATE_PATH/monthly_goals.json (Drive-backed)."
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

    target = args.target or f"{STATE_PATH}/{MONTHLY_GOALS_NAME}"
    return install(target, force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
