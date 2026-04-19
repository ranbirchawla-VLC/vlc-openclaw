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

STRATEGY_SCHEMA = HERE / "schema" / "strategy_output_v1.json"
COWORK_SCHEMA = REPO_ROOT / "grailzee-cowork" / "schema" / "strategy_output_v1.json"


def main() -> int:
    for path in (STRATEGY_SCHEMA, COWORK_SCHEMA):
        if not path.exists():
            print(f"MISSING: {path}", file=sys.stderr)
            return 2

    strategy_bytes = STRATEGY_SCHEMA.read_bytes()
    cowork_bytes = COWORK_SCHEMA.read_bytes()

    if strategy_bytes == cowork_bytes:
        print(f"OK: {STRATEGY_SCHEMA.name} byte-identical across both plugins.")
        return 0

    print("DRIFT: schema copies differ.", file=sys.stderr)
    print(f"  strategy: {STRATEGY_SCHEMA}", file=sys.stderr)
    print(f"  cowork:   {COWORK_SCHEMA}", file=sys.stderr)
    print(
        f"  sizes: {len(strategy_bytes)} vs {len(cowork_bytes)} bytes",
        file=sys.stderr,
    )
    print(
        "Run `diff` on the two files, reconcile the contents, and re-run.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
