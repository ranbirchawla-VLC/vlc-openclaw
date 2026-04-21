"""Phase A.5 installer for cycle_focus.json.

Writes ``<STATE_PATH>/cycle_focus.json`` with starter values supplied by
Ranbir at the building-chat handoff (capital_target=15000,
volume_target=4, target_margin_fraction=0.05 carried forward from
analyzer_config). Empty arrays for targets/brand_emphasis/brand_pullback
are valid no-nulls values per v1.1 §2. Sentinel ``cycle_id="starter"``
and epoch ``cycle_date_range`` are placeholders the strategy session
overwrites at the first cycle-planning commit; `is_cycle_focus_current`
never matches "starter" so agent-side freshness gates behave correctly.

Drive-backed (STATE_PATH), not workspace state. Cowork apply writes
here at every cycle commit, so the file shares its write lifecycle
with the data files (cache, ledger, cycle outcomes) that also live on
Drive. Diverges from A.2/A.3/A.4 installers, which target workspace
state because those configs are committed into the repo.

Schema_version 1 ships here; C.1 will bump to v2 (target entries grow
to objects with stamped predictions). The v1-shape file is readable
by the existing `load_cycle_focus` loader, which performs no
schema_version check.

Refuses to overwrite an existing file unless ``--force`` is passed.
The existing file would typically carry strategy-set values; silent
overwrite would destroy that.

Usage:
    python3 scripts/install_cycle_focus.py                # writes to STATE_PATH
    python3 scripts/install_cycle_focus.py --target PATH  # custom target
    python3 scripts/install_cycle_focus.py --force        # allow overwrite
    python3 scripts/install_cycle_focus.py --dry-run      # no write

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

CYCLE_FOCUS_NAME = "cycle_focus.json"
CYCLE_FOCUS_SCHEMA_VERSION = 1
UPDATED_BY = "phase_a_install"

# Sentinel cycle_id; strategy overwrites at first cycle-planning commit.
# `is_cycle_focus_current("starter")` returns False by design so agent-side
# freshness checks never treat the starter file as a real cycle focus.
STARTER_CYCLE_ID = "starter"

# Sentinel cycle_date_range. Epoch bounds keep the no-nulls rule satisfied
# without pretending the starter represents any real date window.
EPOCH_DATE = "1970-01-01"

CYCLE_FOCUS_FACTORY_CONTENT: dict = {
    "schema_version": CYCLE_FOCUS_SCHEMA_VERSION,
    "cycle_id": STARTER_CYCLE_ID,
    "cycle_date_range": {"start": EPOCH_DATE, "end": EPOCH_DATE},
    "capital_target": 15000,
    "volume_target": 4,
    "target_margin_fraction": 0.05,
    "targets": [],
    "brand_emphasis": [],
    "brand_pullback": [],
    "notes": "Starter values. Strategy session at first cycle planning will overwrite.",
}


def _defaulted_fields_for_cycle_focus(content: dict) -> list[str]:
    """Return the sorted defaulted-field paths for cycle_focus content.

    `leaf_paths` recurses into dicts, so it would enumerate
    ``cycle_date_range.start`` and ``cycle_date_range.end`` as separate
    paths. Strategy commits the whole date range as one unit — granular
    start/end defaulting is meaningless — so we collapse any path under
    ``cycle_date_range.*`` to the parent ``cycle_date_range``. Arrays
    (targets, brand_emphasis, brand_pullback) are already natural stop
    points for leaf_paths and need no collapse.
    """
    raw = leaf_paths(content)
    collapsed: set[str] = set()
    for path in raw:
        if path.startswith("cycle_date_range."):
            collapsed.add("cycle_date_range")
        else:
            collapsed.add(path)
    return sorted(collapsed)


def install(target: str, *, force: bool, dry_run: bool) -> int:
    """Install the config file. Returns the intended exit code."""
    with tracer.start_as_current_span("install_cycle_focus") as span:
        span.set_attribute("target", target)
        span.set_attribute("force", force)
        span.set_attribute("dry_run", dry_run)
        span.set_attribute("cycle_id", STARTER_CYCLE_ID)

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

        content = json.loads(json.dumps(CYCLE_FOCUS_FACTORY_CONTENT))
        defaulted = _defaulted_fields_for_cycle_focus(content)
        span.set_attribute("defaulted_count", len(defaulted))

        if dry_run:
            print(
                json.dumps(
                    {
                        "target": target,
                        "would_write": True,
                        "defaulted_fields": defaulted,
                        "schema_version": content["schema_version"],
                        "cycle_id": content["cycle_id"],
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
            "Target path for cycle_focus.json. "
            "Defaults to STATE_PATH/cycle_focus.json (Drive-backed)."
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

    target = args.target or f"{STATE_PATH}/{CYCLE_FOCUS_NAME}"
    return install(target, force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
