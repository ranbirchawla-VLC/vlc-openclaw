"""Structured review scan of all GTD records for a user.

Sections (in priority order):
  1. active_tasks_missing_metadata  — active tasks without context or area
  2. stale_active_tasks             — active tasks not updated in >14 days
  3. ideas_overdue_for_review       — ideas past their review cadence
  4. waiting_for_followup           — waiting/delegated tasks untouched 7+ days
  5. parking_lot_unclassified       — all active parking-lot items

Usage: python3 gtd_review.py <user_id>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from common import ReviewCadence, TaskStatus, now_iso, parse_iso, read_jsonl, user_path

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_STALE_DAYS = 14          # active task with no update for more than this is stale
_WAITING_DAYS = 7         # waiting/delegated task untouched for 7+ days needs follow-up

_CADENCE_DAYS: dict[ReviewCadence, int] = {
    ReviewCadence.weekly:    7,
    ReviewCadence.monthly:   30,
    ReviewCadence.quarterly: 90,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _days_since(ts: str, now: datetime) -> int:
    """Return the number of whole days elapsed since ts."""
    return (now - parse_iso(ts)).days


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def review(user_id: str) -> dict:
    """Scan all GTD records and return a structured review object.

    Reads tasks.jsonl, ideas.jsonl, and parking-lot.jsonl for user_id.
    Returns sections in the specified priority order with per-section counts.
    Never calls the LLM.

    Args:
        user_id: Identifies whose storage to scan.

    Returns:
        {
            sections: [
                { name: str, items: list[dict], count: int },
                ...   # five sections in priority order
            ],
            total_items_flagged: int,
            reviewed_at: iso8601,
        }
    """
    now = datetime.now(timezone.utc)

    tasks = read_jsonl(user_path(user_id) / "tasks.jsonl")
    ideas = read_jsonl(user_path(user_id) / "ideas.jsonl")
    parking_lot = read_jsonl(user_path(user_id) / "parking-lot.jsonl")

    # --- Section 1: active tasks missing required metadata -----------------
    missing_metadata = [
        t for t in tasks
        if t.get("status") == TaskStatus.active
        and (not t.get("context") or not t.get("area"))
    ]

    # --- Section 2: stale active tasks (>14 days since last update) --------
    stale_tasks = [
        t for t in tasks
        if t.get("status") == TaskStatus.active
        and t.get("updated_at")
        and _days_since(t["updated_at"], now) > _STALE_DAYS
    ]

    # --- Section 3: ideas overdue for review --------------------------------
    overdue_ideas = []
    for idea in ideas:
        cadence = idea.get("review_cadence")
        if cadence not in _CADENCE_DAYS:
            continue
        # Fall back to created_at when the idea has never been reviewed
        reference_ts = idea.get("last_reviewed_at") or idea.get("created_at")
        if reference_ts and _days_since(reference_ts, now) > _CADENCE_DAYS[cadence]:
            overdue_ideas.append(idea)

    # --- Section 4: waiting-for items needing follow-up (7+ days) ----------
    waiting_followup = [
        t for t in tasks
        if t.get("status") in (TaskStatus.waiting, TaskStatus.delegated)
        and t.get("updated_at")
        and _days_since(t["updated_at"], now) >= _WAITING_DAYS
    ]

    # --- Section 5: active parking-lot items --------------------------------
    parking_unclassified = [p for p in parking_lot if p.get("status") == TaskStatus.active]

    # --- Assemble in priority order -----------------------------------------
    sections = [
        {
            "name":  "active_tasks_missing_metadata",
            "items": missing_metadata,
            "count": len(missing_metadata),
        },
        {
            "name":  "stale_active_tasks",
            "items": stale_tasks,
            "count": len(stale_tasks),
        },
        {
            "name":  "ideas_overdue_for_review",
            "items": overdue_ideas,
            "count": len(overdue_ideas),
        },
        {
            "name":  "waiting_for_followup",
            "items": waiting_followup,
            "count": len(waiting_followup),
        },
        {
            "name":  "parking_lot_unclassified",
            "items": parking_unclassified,
            "count": len(parking_unclassified),
        },
    ]

    return {
        "sections":            sections,
        "total_items_flagged": sum(s["count"] for s in sections),
        "reviewed_at":         now_iso(),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run GTD review scan for a user")
    parser.add_argument("user_id", help="User ID whose records to scan")
    args = parser.parse_args()

    result = review(args.user_id)
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0)
