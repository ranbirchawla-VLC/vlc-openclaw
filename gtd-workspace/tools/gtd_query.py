"""Query stored items by context, area, tag, status, or type.

Usage: python3 gtd_query.py [--context @computer] [--area work]
                             [--status active] [--type task] [--tag tagname]
"""

from __future__ import annotations
import argparse
import sys


def query(
    context: str | None = None,
    area: str | None = None,
    status: str | None = None,
    item_type: str | None = None,
    tag: str | None = None,
) -> list[dict]:
    """Return items matching all supplied filters."""
    raise NotImplementedError


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--context")
    parser.add_argument("--area")
    parser.add_argument("--status", choices=["active", "waiting", "someday", "done"])
    parser.add_argument("--type", dest="item_type", choices=["task", "idea", "parking_lot"])
    parser.add_argument("--tag")
    args = parser.parse_args()
    results = query(args.context, args.area, args.status, args.item_type, args.tag)
    for item in results:
        print(item)
