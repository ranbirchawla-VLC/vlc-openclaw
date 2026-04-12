"""Normalize raw captures into task/idea/parking_lot schema.

Usage: python3 gtd_normalize.py '<raw_input>'
"""

from __future__ import annotations
import sys


def normalize(raw_input: str) -> dict:
    """Parse raw input and return a candidate item dict with inferred type."""
    raise NotImplementedError


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: gtd_normalize.py '<raw_input>'")
        sys.exit(1)
    raw = sys.argv[1]
    result = normalize(raw)
    print(result)
