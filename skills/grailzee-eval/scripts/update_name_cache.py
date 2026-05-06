"""Write confirmed model-name entries to name_cache.json.

Called by the grailzee-eval agent after web-resolving unnamed references.
Accepts a batch of entries so the agent makes one tool call per cycle
rather than one per reference.

Usage (plugin / JSON argv):
    python3 scripts/update_name_cache.py '{"entries": [{"reference": "126610LN", "brand": "Rolex", "model": "Submariner Date"}, ...]}'

Returns:
    {"status": "ok", "written": N, "skipped": N}
    written = new entries added; skipped = already present (idempotent).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, ValidationError

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import (
    NAME_CACHE_PATH,
    attach_parent_trace_context,
    get_tracer,
    load_name_cache,
    save_name_cache,
)

tracer = get_tracer(__name__)


class _Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str
    brand: str
    model: str
    alt_refs: Optional[list[str]] = None


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[_Entry]
    name_cache_path: Optional[str] = None


def _error(error_type: str, message: str) -> dict:
    return {"status": "error", "error_type": error_type, "message": message}


def run(entries: list[_Entry], name_cache_path: str | None = None) -> dict:
    path = name_cache_path or NAME_CACHE_PATH
    cache = load_name_cache(path)

    written = 0
    skipped = 0

    with tracer.start_as_current_span("update_name_cache.run") as span:
        span.set_attribute("entries_count", len(entries))
        span.set_attribute("cache_path", path)

        for entry in entries:
            if entry.reference in cache:
                skipped += 1
                continue
            record: dict = {"brand": entry.brand, "model": entry.model}
            if entry.alt_refs:
                record["alt_refs"] = entry.alt_refs
            cache[entry.reference] = record
            written += 1

        if written:
            save_name_cache(cache, path)

        span.set_attribute("written_count", written)
        span.set_attribute("skipped_count", skipped)
        span.set_attribute("outcome", "ok")

    return {"status": "ok", "written": written, "skipped": skipped}


def _run_from_dict(data: dict) -> int:
    try:
        inp = _Input(**data)
    except ValidationError as exc:
        errors = exc.errors()
        if any(e["type"] == "missing" for e in errors):
            missing = ", ".join(str(e["loc"][-1]) for e in errors if e["type"] == "missing")
            print(json.dumps(_error("missing_arg", f"Missing required field: {missing}")))
        else:
            print(json.dumps(_error("bad_input", str(exc))))
        return 0

    try:
        result = run(inp.entries, inp.name_cache_path)
    except Exception as exc:
        print(json.dumps(_error("internal_error", str(exc))))
        return 0

    print(json.dumps(result))
    return 0


def _run_from_argv() -> int:
    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as exc:
        print(json.dumps(_error("bad_input", f"Invalid JSON in argv[1]: {exc}")))
        return 0
    if not isinstance(payload, dict):
        print(json.dumps(_error("bad_input", f"Expected JSON object, got {type(payload).__name__}")))
        return 0
    return _run_from_dict(payload)


if __name__ == "__main__":
    with attach_parent_trace_context():
        if len(sys.argv) > 1 and sys.argv[1].startswith("{"):
            sys.exit(_run_from_argv())
        try:
            payload = json.loads(sys.stdin.read())
        except json.JSONDecodeError as exc:
            print(json.dumps(_error("bad_input", f"Invalid JSON on stdin: {exc}")))
            sys.exit(0)
        sys.exit(_run_from_dict(payload))
