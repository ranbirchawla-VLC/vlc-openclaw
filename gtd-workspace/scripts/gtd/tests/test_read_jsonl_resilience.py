"""test_read_jsonl_resilience.py -- read_jsonl handles partial/malformed lines.

Partial final line is a real failure mode when append-with-fsync crashes
mid-write. The current implementation (bare json.loads in a list comprehension)
raises JSONDecodeError on a truncated line; this test suite guards the fix.
"""
from __future__ import annotations

import json

from _tools_common import read_jsonl   # re-exported from tools/common.py


def test_read_jsonl_skips_partial_line(tmp_path):
    """JSONL file with one valid line plus a truncated final line returns
    exactly the one valid record without raising."""
    f = tmp_path / "test.jsonl"
    valid_record = {"id": "abc", "title": "ok"}
    f.write_text(
        json.dumps(valid_record) + "\n"
        + '{"id": "xyz", "title": "trunc',   # truncated — no closing brace/newline
        encoding="utf-8",
    )
    result = read_jsonl(f)
    assert result == [valid_record]


def test_read_jsonl_all_valid(tmp_path):
    """Normal JSONL with multiple valid lines returns all records."""
    f = tmp_path / "test.jsonl"
    records = [{"id": str(i), "v": i} for i in range(5)]
    f.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n",
        encoding="utf-8",
    )
    assert read_jsonl(f) == records
