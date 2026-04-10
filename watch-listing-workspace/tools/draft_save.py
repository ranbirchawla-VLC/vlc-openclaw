#!/usr/bin/env python3
"""
draft_save.py — Safe _draft.json read/merge/validate/write tool.

Usage (from exec):
  python3 /path/to/draft_save.py <folder_path> '<json_patch>'

- Reads existing _draft.json from folder_path (if exists)
- Deep-merges the JSON patch into the existing draft
- Validates the result
- Writes atomically (write to .tmp, then rename)
- Returns {"ok": true, "path": "..."} or {"ok": false, "error": "..."}

The patch can be a partial object — only the keys provided are updated.
Nested objects are merged, not replaced. Arrays are replaced.

Example:
  python3 draft_save.py "/path/to/folder" '{"step": 3, "phase": "A_complete", "canonical": {"title": "..."}}'
"""

import json
import os
import sys
import tempfile


def deep_merge(base, patch):
    """Deep merge patch into base. Arrays are replaced, dicts are merged."""
    if not isinstance(base, dict) or not isinstance(patch, dict):
        return patch
    result = dict(base)
    for key, val in patch.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"ok": False, "error": "Usage: draft_save.py <folder_path> '<json_patch>'"}))
        sys.exit(1)

    folder_path = sys.argv[1]
    patch_str = sys.argv[2]

    # Parse the patch
    try:
        patch = json.loads(patch_str)
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "error": f"Invalid JSON patch: {e}"}))
        sys.exit(1)

    draft_path = os.path.join(folder_path, "_draft.json")

    # Read existing draft if present
    existing = {}
    if os.path.exists(draft_path):
        try:
            with open(draft_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except json.JSONDecodeError as e:
            # Existing draft is corrupt — back it up and start fresh
            backup_path = draft_path + ".corrupt.bak"
            try:
                os.rename(draft_path, backup_path)
            except OSError:
                pass
            existing = {}

    # Merge
    merged = deep_merge(existing, patch)

    # Validate by round-tripping through json
    try:
        validated = json.loads(json.dumps(merged))
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Validation failed after merge: {e}"}))
        sys.exit(1)

    # Atomic write: write to .tmp then rename
    tmp_path = draft_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(validated, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, draft_path)
    except OSError as e:
        print(json.dumps({"ok": False, "error": f"Write failed: {e}"}))
        sys.exit(1)

    print(json.dumps({"ok": True, "path": draft_path}))


if __name__ == "__main__":
    main()
