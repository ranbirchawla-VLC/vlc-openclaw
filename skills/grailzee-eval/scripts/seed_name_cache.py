"""Seed the production name_cache.json from the fixture.

Idempotent. Run as:
  python3 scripts/seed_name_cache.py                # writes to Drive
  python3 scripts/seed_name_cache.py --dry-run      # prints actions
  python3 scripts/seed_name_cache.py --target PATH  # custom target

If the Drive path is unreachable, logs a warning and exits 0 (not
an error; the fixture itself is the source of truth and can be
seeded to Drive later manually).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
FIXTURE_PATH = V2_ROOT / "tests" / "fixtures" / "name_cache_seed.json"

# Import shared constants
sys.path.insert(0, str(V2_ROOT))
from scripts.grailzee_common import (
    NAME_CACHE_PATH,
    load_name_cache,
    save_name_cache,
    get_tracer,
)

tracer = get_tracer(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=NAME_CACHE_PATH,
                        help=f"Target path (default: {NAME_CACHE_PATH})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen, don't write")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite entire target (default: merge)")
    args = parser.parse_args()

    with tracer.start_as_current_span("seed_name_cache") as span:
        span.set_attribute("target", args.target)
        span.set_attribute("dry_run", args.dry_run)
        span.set_attribute("force", args.force)

        # Load fixture
        if not FIXTURE_PATH.exists():
            print(f"ERROR: Fixture missing: {FIXTURE_PATH}", file=sys.stderr)
            return 2

        with open(FIXTURE_PATH) as f:
            seed = json.load(f)
        span.set_attribute("seed_count", len(seed))

        target_dir = Path(args.target).parent

        # Drive reachability check
        if not target_dir.exists():
            print(f"WARNING: Target directory unreachable: {target_dir}",
                  file=sys.stderr)
            print("  The fixture has been prepared at: " + str(FIXTURE_PATH))
            print("  Mount Google Drive or copy manually when available.")
            span.set_attribute("drive_reachable", False)
            return 0
        span.set_attribute("drive_reachable", True)

        # Load existing
        if args.force:
            existing = {}
        else:
            try:
                existing = load_name_cache(args.target)
            except (json.JSONDecodeError, ValueError) as exc:
                print(f"ERROR: Existing cache is corrupt: {exc}",
                      file=sys.stderr)
                print("  Re-run with --force to overwrite.",
                      file=sys.stderr)
                return 3
        span.set_attribute("existing_count", len(existing))

        # Merge (seed doesn't overwrite existing entries)
        added = 0
        for ref, entry in seed.items():
            if ref not in existing:
                existing[ref] = entry
                added += 1
        span.set_attribute("added_count", added)

        if args.dry_run:
            print(f"[dry-run] Would write {len(existing)} entries to "
                  f"{args.target}")
            print(f"[dry-run]   {added} new, {len(existing) - added} existing")
            return 0

        save_name_cache(existing, args.target)
        print(f"Seeded {args.target}")
        print(f"  Total entries: {len(existing)}")
        print(f"  New from seed: {added}")
        print(f"  Pre-existing preserved: {len(existing) - added}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
