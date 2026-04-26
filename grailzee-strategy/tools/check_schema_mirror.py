#!/usr/bin/env python3
"""Fail if grailzee-strategy/schema drifts from grailzee-cowork/schema.

The strategy_output_v1.json schema is intentionally duplicated in both
plugin directories — grailzee-strategy (this repo) and
grailzee-cowork. The contract between the Chat skill and the cowork
unpack_bundle.py path depends on the two copies being byte-identical.

Run this before every commit that touches either schema file, and wire
it into CI once CI exists. Exits 0 on parity, non-zero on drift.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO_ROOT = HERE.parent

SCHEMA_PAIRS: list[tuple[Path, Path]] = [
    (
        HERE / "schema" / "strategy_output_v1.json",
        REPO_ROOT / "grailzee-cowork" / "schema" / "strategy_output_v1.json",
    ),
    (
        HERE / "schema" / "cycle_shortlist_v1.json",
        REPO_ROOT / "grailzee-cowork" / "schema" / "cycle_shortlist_v1.json",
    ),
]


def _check_pair(strategy: Path, cowork: Path) -> int:
    for path in (strategy, cowork):
        if not path.exists():
            print(f"MISSING: {path}", file=sys.stderr)
            return 2

    strategy_bytes = strategy.read_bytes()
    cowork_bytes = cowork.read_bytes()

    if strategy_bytes == cowork_bytes:
        print(f"OK: {strategy.name} byte-identical across both plugins.")
        return 0

    print(f"DRIFT: {strategy.name} copies differ.", file=sys.stderr)
    print(f"  strategy: {strategy}", file=sys.stderr)
    print(f"  cowork:   {cowork}", file=sys.stderr)
    print(
        f"  sizes: {len(strategy_bytes)} vs {len(cowork_bytes)} bytes",
        file=sys.stderr,
    )
    print(
        "Run `diff` on the two files, reconcile the contents, and re-run.",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    result = 0
    for strategy, cowork in SCHEMA_PAIRS:
        rc = _check_pair(strategy, cowork)
        if rc != 0:
            result = rc
    return result


if __name__ == "__main__":
    sys.exit(main())
