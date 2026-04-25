"""Tests for nutrios_time — built TDD, one function at a time."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import nutrios_time


# ---------------------------------------------------------------------------
# now()
# ---------------------------------------------------------------------------

def test_now_returns_utc_aware():
    dt = nutrios_time.now()
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timedelta(0)
