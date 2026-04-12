"""Persist validated items to the task store.

Never write to the task store directly — always use this tool.
Usage: python3 gtd_write.py <item.json>
"""

from __future__ import annotations
import sys
from pathlib import Path


def write_item(item_path: Path) -> None:
    """Read item JSON, merge into task store safely."""
    raise NotImplementedError


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: gtd_write.py <item.json>")
        sys.exit(1)
    write_item(Path(sys.argv[1]))
