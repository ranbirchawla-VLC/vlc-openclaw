"""nutrios_write.py — write entrypoint for non-JSONL targets (2/10).

Writes goals.json, protocol.json, mesocycles/<cycle_id>.json, or recipes.json
with appropriate gating BEFORE any disk mutation. Atomic at the tool level —
if the gate rejects, no write occurs.

Gating per scope:
    goals       → protected_gate_range on every MacroRange where current
                  has protected=True. Multiple diffs → one confirm covers all.
    protocol    → protected_gate_protocol.
    mesocycle   → none (TDEE / deficit edits are not protected).
    recipes     → none (recipe lifecycle is not protected; nutrios_recipe
                  has its own duplicate-name guard).

Stdout: one ToolResult JSON line on success or gate rejection. Validation
errors propagate up and exit non-zero.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from nutrios_models import (
    ToolResult, GateResult, Goals, Protocol, Mesocycle, Recipe, MacroRange,
)
import nutrios_engine as engine
import nutrios_render as render
import nutrios_store as store


class WriteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    scope: Literal["goals", "protocol", "mesocycle", "recipes"]
    payload: dict
    confirm: str | None = None


# ---------------------------------------------------------------------------
# Goals gate — walk every protected MacroRange, confirm-phrase covers all
# ---------------------------------------------------------------------------

def _gate_goals(current: Goals, proposed: Goals, confirm: str) -> GateResult:
    """Check every protected MacroRange in current vs proposed.

    Returns the first failing GateResult. Returns ok=True if every
    protected range either matches or passes with the confirm phrase.
    Added or removed day_patterns are structural changes and are not
    gated here — the gate is value-change-on-protected-range only.
    """
    pairs: list[tuple[MacroRange, MacroRange]] = [
        (current.defaults.protein_g, proposed.defaults.protein_g),
        (current.defaults.carbs_g,   proposed.defaults.carbs_g),
        (current.defaults.fat_g,     proposed.defaults.fat_g),
    ]

    proposed_by_type = {p.day_type: p for p in proposed.day_patterns}
    for cp in current.day_patterns:
        if cp.day_type in proposed_by_type:
            pp = proposed_by_type[cp.day_type]
            pairs.extend([
                (cp.protein_g, pp.protein_g),
                (cp.carbs_g,   pp.carbs_g),
                (cp.fat_g,     pp.fat_g),
            ])

    for cur, prop in pairs:
        result = engine.protected_gate_range(cur, prop, confirm or "")
        if not result.ok:
            return result
    return GateResult(ok=True, reason=None, applied=True)


# ---------------------------------------------------------------------------
# Per-scope dispatch
# ---------------------------------------------------------------------------

def _write_goals(inp: WriteInput) -> ToolResult:
    proposed = Goals.model_validate(inp.payload)
    current = store.read_json(inp.user_id, "goals.json", Goals)
    if current is None:
        # First-time write: no current state to gate against.
        store.write_json(inp.user_id, "goals.json", proposed)
        return ToolResult(display_text=render.render_write_confirm("goals"))

    gate = _gate_goals(current, proposed, inp.confirm or "")
    if not gate.ok:
        return ToolResult(display_text=render.render_gate_error(gate))
    store.write_json(inp.user_id, "goals.json", proposed)
    return ToolResult(display_text=render.render_write_confirm("goals"))


def _write_protocol(inp: WriteInput) -> ToolResult:
    proposed = Protocol.model_validate(inp.payload)
    current = store.read_json(inp.user_id, "protocol.json", Protocol)
    if current is None:
        store.write_json(inp.user_id, "protocol.json", proposed)
        return ToolResult(display_text=render.render_write_confirm("protocol"))

    gate = engine.protected_gate_protocol(current, proposed, inp.confirm or "")
    if not gate.ok:
        return ToolResult(display_text=render.render_gate_error(gate))
    store.write_json(inp.user_id, "protocol.json", proposed)
    return ToolResult(display_text=render.render_write_confirm("protocol"))


def _write_mesocycle(inp: WriteInput) -> ToolResult:
    proposed = Mesocycle.model_validate(inp.payload)
    store.write_json(inp.user_id, f"mesocycles/{proposed.cycle_id}.json", proposed)
    return ToolResult(display_text=render.render_write_confirm("mesocycle"))


def _write_recipes(inp: WriteInput) -> ToolResult:
    """Bulk-replace recipes.json. Per-recipe lifecycle goes through nutrios_recipe.

    Strict: payload must include a 'recipes' key (empty list is fine, but
    omission is a caller error). Bulk writes clear-all are destructive,
    so we require the explicit key rather than treat absence as empty.
    """
    if "recipes" not in inp.payload:
        raise ValueError("recipes payload must include a 'recipes' key (list, possibly empty)")
    raw_list = inp.payload["recipes"]
    if not isinstance(raw_list, list):
        raise ValueError("recipes payload's 'recipes' field must be a list")
    recipes = [Recipe.model_validate(r) for r in raw_list]
    store.write_recipes(inp.user_id, recipes)
    return ToolResult(display_text=render.render_write_confirm("recipes"))


# ---------------------------------------------------------------------------
# Top-level dispatch
# ---------------------------------------------------------------------------

def main(argv_json: str) -> ToolResult:
    inp = WriteInput.model_validate_json(argv_json)
    match inp.scope:
        case "goals":
            return _write_goals(inp)
        case "protocol":
            return _write_protocol(inp)
        case "mesocycle":
            return _write_mesocycle(inp)
        case "recipes":
            return _write_recipes(inp)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: nutrios_write '<json_argv>'"}), file=sys.stderr)
        sys.exit(2)
    result = main(sys.argv[1])
    print(result.model_dump_json())
