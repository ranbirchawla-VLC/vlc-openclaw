"""delegation.py -- LLM-visible plugin entry point for waiting-for items.

Groups tasks by their waiting_for person. Returns a non-standard envelope
(groups, not items) documented as the deliberate exception to the Lock 6
standard query shape.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_here = Path(__file__).parent
sys.path.insert(0, str(_here))          # scripts/gtd/
sys.path.insert(0, str(_here.parent))   # scripts/

from pydantic import BaseModel

from common import GTDError, err, get_gtd_config, ok
from otel_common import get_tracer
from opentelemetry.trace import Status, StatusCode
from _tools_common import read_jsonl, user_path


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class _Input(BaseModel):
    person: str | None = None
    limit: int | None = None


# ---------------------------------------------------------------------------
# OTEL context attributes
# ---------------------------------------------------------------------------

_CONTEXT_ENV: dict[str, str] = {
    "user.id":         "OPENCLAW_USER_ID",
    "session.id":      "OPENCLAW_SESSION_ID",
    "channel.type":    "OPENCLAW_CHANNEL_TYPE",
    "channel.peer_id": "OPENCLAW_CHANNEL_PEER_ID",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def delegation(
    person: str | None = None,
    limit: int | None = None,
    requesting_user_id: str = "",
) -> dict:
    """Return waiting-for tasks grouped by person.

    Return shape differs from the standard query envelope by design:
    {groups: [{person, count, items}], total_items, truncated}

    limit applies per-group (caps items shown for each person).
    truncated fires if any group exceeds limit.
    """
    config = get_gtd_config()
    effective_limit = min(limit if limit is not None else config.default_query_limit, config.max_query_limit)

    tracer = get_tracer("gtd.delegation")
    with tracer.start_as_current_span("gtd.delegation") as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("tool.name", "delegation")
        span.set_attribute("request.type", "query")
        for attr, env_var in _CONTEXT_ENV.items():
            val = os.environ.get(env_var)
            if val:
                span.set_attribute(attr, val)
        if person is not None:
            span.set_attribute("query.person", person)
        span.set_attribute("query.limit", effective_limit)

        try:
            if not requesting_user_id:
                raise GTDError("internal_error", "OPENCLAW_USER_ID not set")

            path = user_path(requesting_user_id) / "tasks.jsonl"
            records = read_jsonl(path)

            waiting = [r for r in records if r.get("waiting_for")]
            if person is not None:
                waiting = [r for r in waiting if r.get("waiting_for") == person]

            groups_map: dict[str, list[dict]] = {}
            for r in waiting:
                p = r["waiting_for"]
                if p not in groups_map:
                    groups_map[p] = []
                groups_map[p].append(r)

            truncated = False
            group_list: list[dict] = []
            total_items = 0
            for p in sorted(groups_map):
                items = groups_map[p]
                total_items += len(items)
                limited = items[:effective_limit]
                if len(items) > effective_limit:
                    truncated = True
                group_list.append({"person": p, "count": len(items), "items": limited})

            span.set_attribute("result.total_items", total_items)
            span.set_attribute("result.group_count", len(group_list))

            return {
                "groups": group_list,
                "total_items": total_items,
                "truncated": truncated,
            }

        except GTDError as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, exc.message))
            raise


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        err(GTDError("internal_error", "Usage: python delegation.py <args.json>"))
        return
    try:
        args = json.loads(sys.argv[1])
        inp = _Input(**args)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        err(GTDError("internal_error", f"Invalid input: {exc}"))
        return

    requesting_user_id = os.environ.get("OPENCLAW_USER_ID", "")
    try:
        result = delegation(
            person=inp.person,
            limit=inp.limit,
            requesting_user_id=requesting_user_id,
        )
        ok(result)
    except GTDError as exc:
        err(exc)


if __name__ == "__main__":
    main()
