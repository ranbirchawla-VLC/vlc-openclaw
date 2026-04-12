"""Tests for gtd_delegation.py"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from gtd_delegation import list_delegated, follow_up, resolve
