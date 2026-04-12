"""Validate a JSON object against the appropriate schema.

Usage: python3 gtd_validate.py <type> <file.json>
Types: task, idea, parking_lot, profile
"""

from __future__ import annotations
import sys
from pathlib import Path


def validate(item_type: str, file_path: Path) -> bool:
    """Validate file against schema for item_type. Returns True if valid."""
    raise NotImplementedError


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: gtd_validate.py <type> <file.json>")
        sys.exit(1)
    item_type = sys.argv[1]
    file_path = Path(sys.argv[2])
    ok = validate(item_type, file_path)
    sys.exit(0 if ok else 1)
