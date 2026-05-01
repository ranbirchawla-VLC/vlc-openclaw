"""get_today_date; return today's date in the agent timezone.

Usage: python3 get_today_date.py [ignored]

Returns {ok: true, data: {date: "YYYY-MM-DD"}}.
"""

from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import ok, today_str

# FORWARD: active_timezone hardcoded to AGENT_TZ ("America/Denver").
# Multi-timezone wiring is post-spike work; see meal_log.md REDLINE 1.


def run_get_today_date() -> dict:
    return {"date": today_str()}


def main() -> None:
    ok(run_get_today_date())


if __name__ == "__main__":
    main()
