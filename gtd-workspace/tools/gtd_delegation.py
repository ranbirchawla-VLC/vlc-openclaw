"""Track delegated tasks, follow-up cadence, and resolution.

Usage: python3 gtd_delegation.py --action <list|follow_up|resolve>
                                  [--status <pending|overdue|resolved>]
                                  [--id <task_id>]
"""

from __future__ import annotations
import argparse
import sys


def list_delegated(status: str | None = None) -> list[dict]:
    """Return delegated tasks, optionally filtered by status."""
    raise NotImplementedError


def follow_up(task_id: str) -> dict:
    """Prepare follow-up draft for a delegated task."""
    raise NotImplementedError


def resolve(task_id: str) -> None:
    """Mark a delegated task as resolved."""
    raise NotImplementedError


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=["list", "follow_up", "resolve"])
    parser.add_argument("--status", choices=["pending", "overdue", "resolved"])
    parser.add_argument("--id")
    args = parser.parse_args()

    match args.action:
        case "list":
            results = list_delegated(args.status)
            for item in results:
                print(item)
        case "follow_up":
            if not args.id:
                print("--id required for follow_up")
                sys.exit(1)
            print(follow_up(args.id))
        case "resolve":
            if not args.id:
                print("--id required for resolve")
                sys.exit(1)
            resolve(args.id)
