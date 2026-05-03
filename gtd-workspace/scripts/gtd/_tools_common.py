"""Single canonical load of tools/common.py for scripts/gtd/ modules.

Python caches this module after first import, so validate.py and write.py
share identical class objects -- enum identity works correctly across both.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "gtd._tools_common",
    Path(__file__).parent.parent.parent / "tools" / "common.py",
)
_mod = importlib.util.module_from_spec(_spec)   # type: ignore[arg-type]
_spec.loader.exec_module(_mod)                   # type: ignore[union-attr]

# Enums
Energy:           type = _mod.Energy
IdeaStatus:       type = _mod.IdeaStatus
ParkingLotReason: type = _mod.ParkingLotReason
Priority:         type = _mod.Priority
ProfileStatus:    type = _mod.ProfileStatus
PromotionState:   type = _mod.PromotionState
ReviewCadence:    type = _mod.ReviewCadence
Source:           type = _mod.Source
TaskStatus:       type = _mod.TaskStatus

# Storage helpers
append_jsonl    = _mod.append_jsonl
assert_user_match = _mod.assert_user_match
new_id          = _mod.new_id
now_iso         = _mod.now_iso
user_path       = _mod.user_path
