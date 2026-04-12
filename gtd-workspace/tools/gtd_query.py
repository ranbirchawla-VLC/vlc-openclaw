"""Retrieve and rank GTD task records by filter criteria.

Usage: python3 gtd_query.py <user_id> [--status active] [--context @computer]
                              [--priority high] [--energy low]
                              [--duration-max 30] [--limit 5]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import Energy, Priority, TaskStatus, read_jsonl, user_path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Numeric rank for priority sorting: higher = more urgent
_PRIORITY_RANK: dict[Priority, int] = {
    Priority.low:      0,
    Priority.normal:   1,
    Priority.high:     2,
    Priority.critical: 3,
}

# Statuses omitted from results unless the caller explicitly requests them
_EXCLUDED_BY_DEFAULT: frozenset[str] = frozenset({
    TaskStatus.done,
    TaskStatus.cancelled,
    TaskStatus.archived,
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def query(
    user_id: str,
    status: str | None = None,
    context: str | None = None,
    priority: str | None = None,
    energy: str | None = None,
    duration_minutes: int | None = None,
    limit: int = 5,
) -> list[dict]:
    """Return ranked task records for user_id matching all supplied filters.

    Only reads tasks.jsonl — never returns idea or parking_lot records.
    Excludes done, cancelled, and archived records unless status is explicit.
    Sorts by priority descending (critical first), then created_at ascending.
    Never reads another user's data.

    Args:
        user_id: Identifies whose storage to read.
        status: Exact status to filter on. If None, excludes done/cancelled/archived.
        context: Exact context string to match (e.g. "@computer").
        priority: Exact priority to filter on.
        energy: Exact energy level to filter on.
        duration_minutes: Maximum duration threshold (inclusive). Records with null
            duration are included since their duration is unknown.
        limit: Maximum number of records to return (default 5).

    Returns:
        List of task dicts, sorted and capped at limit.
    """
    path = user_path(user_id) / "tasks.jsonl"
    records = read_jsonl(path)

    # Defensive guard: only task records ever leave this function
    records = [r for r in records if r.get("record_type") == "task"]

    if status is None:
        records = [r for r in records if r.get("status") not in _EXCLUDED_BY_DEFAULT]
    else:
        records = [r for r in records if r.get("status") == status]

    if context is not None:
        records = [r for r in records if r.get("context") == context]

    if priority is not None:
        records = [r for r in records if r.get("priority") == priority]

    if energy is not None:
        records = [r for r in records if r.get("energy") == energy]

    if duration_minutes is not None:
        # Include records with null duration (unknown) — they don't violate the threshold
        records = [
            r for r in records
            if r.get("duration_minutes") is None
            or r["duration_minutes"] <= duration_minutes
        ]

    # Sort: priority descending, then created_at ascending (oldest first within same priority)
    records.sort(
        key=lambda r: (
            -_PRIORITY_RANK.get(r.get("priority", ""), 0),
            r.get("created_at", ""),
        )
    )

    return records[:limit]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query GTD task records")
    parser.add_argument("user_id", help="User ID whose tasks to query")
    parser.add_argument(
        "--status",
        choices=[e.value for e in TaskStatus],
    )
    parser.add_argument("--context", help="Context filter, e.g. @computer")
    parser.add_argument(
        "--priority",
        choices=[e.value for e in Priority],
    )
    parser.add_argument("--energy", choices=[e.value for e in Energy])
    parser.add_argument(
        "--duration-max",
        type=int,
        dest="duration_minutes",
        metavar="MINUTES",
        help="Include only tasks at or under this many minutes (null-duration tasks included)",
    )
    parser.add_argument("--limit", type=int, default=5, help="Max results (default 5)")
    args = parser.parse_args()

    results = query(
        args.user_id,
        status=args.status,
        context=args.context,
        priority=args.priority,
        energy=args.energy,
        duration_minutes=args.duration_minutes,
        limit=args.limit,
    )
    print(json.dumps(results, indent=2))
    sys.exit(0)
