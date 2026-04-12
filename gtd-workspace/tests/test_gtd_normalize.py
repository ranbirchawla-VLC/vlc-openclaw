"""Tests for gtd_normalize.py"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from gtd_normalize import normalize
