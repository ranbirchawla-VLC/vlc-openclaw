"""Grouped view of delegation and waiting-for items for a user.

Reads tasks.jsonl and selects records where:
  - delegate_to is non-null, OR
  - waiting_for is non-null, OR
  - status is "waiting" or "delegated"

Groups by person (delegate_to takes precedence over waiting_for).
Groups sorted by oldest untouched item first; items within each group
sorted by updated_at ascending.

Usage: python3 gtd_delegation.py <user_id>
"""

from __future__ import annotations

import argparse
import json
import sys

from common import TaskStatus, read_jsonl, user_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def delegation(user_id: str) -> dict:
    """Return delegation-relevant records grouped by person.

    Args:
        user_id: Identifies whose tasks.jsonl to read.

    Returns:
        {
            groups: [
                {
                    person: str,
                    items: list[dict],
                    oldest_untouched: iso8601,
                },
                ...  # sorted by oldest_untouched ascending
            ],
            total_items: int,
        }
    """
    tasks = read_jsonl(user_path(user_id) / "tasks.jsonl")

    grouped: dict[str, list[dict]] = {}

    for task in tasks:
        delegate_to = task.get("delegate_to")
        waiting_for = task.get("waiting_for")
        status = task.get("status", "")

        # delegate_to takes precedence; fall back to waiting_for
        person = delegate_to or waiting_for

        # Exclude tasks with no delegation relationship at all
        if not person and status not in (TaskStatus.waiting, TaskStatus.delegated):
            continue

        # Tasks with status waiting/delegated but no named person get a group key
        if not person:
            person = "unknown"

        grouped.setdefault(person, []).append(task)

    # Sort items within each group by updated_at ascending (oldest touched first)
    for items in grouped.values():
        items.sort(key=lambda r: r.get("updated_at", ""))

    # Build group objects; oldest_untouched is the first item's updated_at after sort
    groups = [
        {
            "person":           person,
            "items":            items,
            "oldest_untouched": items[0]["updated_at"] if items else "",
        }
        for person, items in grouped.items()
    ]

    # Sort groups: oldest untouched across all items in the group first
    groups.sort(key=lambda g: g["oldest_untouched"])

    total = sum(len(g["items"]) for g in groups)
    return {"groups": groups, "total_items": total}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="List delegation and waiting-for items grouped by person"
    )
    parser.add_argument("user_id", help="User ID whose delegation items to list")
    args = parser.parse_args()

    result = delegation(args.user_id)
    print(json.dumps(result, indent=2))
    sys.exit(0)
