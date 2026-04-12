#!/usr/bin/env python3
"""
Evaluator shim for tests.

Accepts the same CLI signature as evaluate_deal.py but ignores all arguments.
Reads the GRAILZEE_FIXTURE environment variable and writes that file's contents
to stdout, simulating evaluate_deal.py's JSON response.

Usage (by test harness):
  GRAILZEE_FIXTURE=/path/to/fixture.json python3 eval_shim.py Tudor 79830RB 3800
"""
import json
import os
import sys

fixture_path = os.environ.get("GRAILZEE_FIXTURE")
if not fixture_path:
    print(json.dumps({
        "status": "error",
        "error": "no_fixture",
        "message": "GRAILZEE_FIXTURE env var is not set",
    }))
    sys.exit(1)

try:
    with open(fixture_path, encoding="utf-8") as f:
        sys.stdout.write(f.read())
except OSError as e:
    print(json.dumps({
        "status": "error",
        "error": "fixture_not_found",
        "message": str(e),
    }))
    sys.exit(1)
