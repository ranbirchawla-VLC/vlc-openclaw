"""Phase A.4 installer for sourcing_rules.json.

Writes ``state/sourcing_rules.json`` with the factory defaults defined
in ``grailzee_common.SOURCING_RULES_FACTORY_DEFAULTS`` and populates
``defaulted_fields`` with every non-managed leaf path: condition_minimum,
papers_required, keyword_filters.include, keyword_filters.exclude. All
four are strategy-tunable, unlike brand_floors where structural fields
(tradeable, asset_class) were excluded. Uses config_helper.leaf_paths
since the schema has no structural-vs-tunable split for this file.

Refuses to overwrite an existing file unless ``--force`` is passed.
The existing file would typically carry strategy-set values; silent
overwrite would destroy that.

Usage:
    python3 scripts/install_sourcing_rules.py                # writes to workspace state
    python3 scripts/install_sourcing_rules.py --target PATH  # custom target
    python3 scripts/install_sourcing_rules.py --force        # allow overwrite
    python3 scripts/install_sourcing_rules.py --dry-run      # no write

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
from scripts.grailzee_common import (
    SOURCING_RULES_FACTORY_DEFAULTS,
    SOURCING_RULES_NAME,
    config_path,
    get_tracer,
)

tracer = get_tracer(__name__)

UPDATED_BY = "phase_a_install"


def install(target: str, *, force: bool, dry_run: bool) -> int:
    """Install the config file. Returns the intended exit code."""
    with tracer.start_as_current_span("install_sourcing_rules") as span:
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

        content = json.loads(json.dumps(SOURCING_RULES_FACTORY_DEFAULTS))
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
            "Target path for sourcing_rules.json. "
            "Defaults to WORKSPACE_STATE_PATH/sourcing_rules.json."
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

    target = args.target or config_path(SOURCING_RULES_NAME)
    return install(target, force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
