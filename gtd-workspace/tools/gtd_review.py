"""Surface items for daily or weekly review; flag stale next actions.

Usage: python3 gtd_review.py --mode <daily|weekly>
"""

from __future__ import annotations
import argparse
import sys


def review(mode: str) -> dict:
    """Run review for the given mode. Returns summary dict."""
    raise NotImplementedError


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["daily", "weekly"])
    args = parser.parse_args()
    result = review(args.mode)
    print(result)
