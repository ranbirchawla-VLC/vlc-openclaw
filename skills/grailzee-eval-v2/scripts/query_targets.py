"""Query active hunting targets — two-section Strong/Normal lookup.

Reads analysis_cache.json, filters references by signal tier, emits a
two-section text block for Telegram. No cycle gate, no filters, no sort
overrides — pure lookup per D3 + D4 (session 3 kickoff).

Output shape:

    STRONG
    {brand} {model} — {reference} — ${max_buy_nr}
    ...sorted by max_buy_nr DESC

    NORMAL
    {brand} {model} — {reference} — ${max_buy_nr}
    ...sorted by max_buy_nr DESC

When both tiers are empty, output collapses to a single line:
``No references at Strong or Normal signal.`` Section headers with no
entries are preserved when only one tier is empty — an empty STRONG
section is itself information for the operator.

Usage:
    python3 query_targets.py [--cache PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from opentelemetry.trace import StatusCode

from scripts.grailzee_common import CACHE_PATH, CACHE_SCHEMA_VERSION, get_tracer

tracer = get_tracer(__name__)

EMPTY_MESSAGE = "No references at Strong or Normal signal."


def _format_line(ref: dict) -> str:
    """Render one reference as '{brand} {model} — {reference} — ${max_buy_nr}'.

    Text fields degrade gracefully (missing brand/model/reference render
    as empty). ``max_buy_nr`` fails loud on None via ``int(None)`` —
    a missing price is a cache-integrity bug that should surface.
    """
    brand = ref.get("brand", "") or ""
    model = ref.get("model", "") or ""
    display = f"{brand} {model}".strip() if brand else model
    reference = ref.get("reference", "") or ""
    return f"{display} — {reference} — ${int(ref['max_buy_nr'])}"


def build_sections(cache: dict) -> tuple[list[dict], list[dict]]:
    """Split cache references into Strong and Normal, sorted by max_buy_nr DESC.

    Ties on ``max_buy_nr`` break on dict-insertion order (Python 3.7+).
    Analyzer insertion order is stable per cache run.
    """
    refs = cache.get("references", {})
    strong = [r for r in refs.values() if r.get("signal") == "Strong"]
    normal = [r for r in refs.values() if r.get("signal") == "Normal"]
    return (
        sorted(strong, key=lambda r: -r["max_buy_nr"]),
        sorted(normal, key=lambda r: -r["max_buy_nr"]),
    )


def format_output(strong: list[dict], normal: list[dict]) -> str:
    """Render the two-section block. Single-line fallback when both empty."""
    if not strong and not normal:
        return EMPTY_MESSAGE
    parts = ["STRONG"]
    parts.extend(_format_line(r) for r in strong)
    parts.append("")
    parts.append("NORMAL")
    parts.extend(_format_line(r) for r in normal)
    return "\n".join(parts)


def query_targets(cache_path: str | None = None) -> str:
    """Read cache, filter to Strong/Normal, return formatted output string.

    Raises FileNotFoundError if the cache file is missing.
    Raises ValueError if the cache schema version is below required.
    """
    resolved = cache_path or CACHE_PATH
    with tracer.start_as_current_span("query_targets.run") as span:
        span.set_attribute("cache_path", resolved)
        try:
            p = Path(resolved)
            if not p.exists():
                raise FileNotFoundError(
                    f"No analysis cache at {resolved!r}. Run the analyzer first."
                )
            cache = json.loads(p.read_text())
            schema = cache.get("schema_version", 0)
            if schema < CACHE_SCHEMA_VERSION:
                raise ValueError(
                    f"Cache schema version {schema} below required "
                    f"{CACHE_SCHEMA_VERSION}. Re-run the analyzer."
                )
            strong, normal = build_sections(cache)
            span.set_attribute("strong_count", len(strong))
            span.set_attribute("normal_count", len(normal))
            return format_output(strong, normal)
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Query Grailzee active hunting targets (Strong + Normal)."
    )
    parser.add_argument("--cache", default=None, help="Path to analysis_cache.json")
    args = parser.parse_args()
    try:
        print(query_targets(cache_path=args.cache))
        return 0
    except Exception as exc:
        print(f"Target query failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
