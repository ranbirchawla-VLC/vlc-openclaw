"""Tests for scripts/get_today_date.py."""

from __future__ import annotations
import json
import os
import re
import sys
from datetime import datetime as _datetime
from unittest.mock import patch
import zoneinfo as _zoneinfo

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common as common_mod
from get_today_date import run_get_today_date


# ---------------------------------------------------------------------------
# Output shape
# ---------------------------------------------------------------------------


def test_returns_dict_with_date_key() -> None:
    result = run_get_today_date()
    assert "date" in result


def test_date_matches_iso_format() -> None:
    result = run_get_today_date()
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", result["date"]), (
        f"expected YYYY-MM-DD, got {result['date']!r}"
    )


# ---------------------------------------------------------------------------
# Timezone correctness
# ---------------------------------------------------------------------------


def test_denver_date_differs_from_utc_at_midnight_boundary() -> None:
    # Freeze at 2026-04-25 05:30 UTC.
    # UTC date  => 2026-04-25
    # Denver (MDT = UTC-6) date => 2026-04-24  (23:30 previous night)
    frozen_utc = _datetime(2026, 4, 25, 5, 30, 0, tzinfo=_zoneinfo.ZoneInfo("UTC"))

    def mock_now(tz=None):
        return frozen_utc.astimezone(tz) if tz is not None else frozen_utc

    with patch.object(common_mod, "datetime") as mock_dt:
        mock_dt.now.side_effect = mock_now
        result = run_get_today_date()

    assert result["date"] == "2026-04-24", (
        f"expected Denver date 2026-04-24, got {result['date']!r}"
    )


# ---------------------------------------------------------------------------
# Empty argv (no input required)
# ---------------------------------------------------------------------------


def test_empty_argv_returns_date(capsys) -> None:
    # main() must work with no sys.argv[1]; tool takes no input.
    original_argv = sys.argv
    sys.argv = ["get_today_date.py"]
    try:
        from get_today_date import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        captured = json.loads(capsys.readouterr().out)
        assert captured["ok"] is True
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", captured["data"]["date"])
    finally:
        sys.argv = original_argv
