"""B.7 bundled fix: build_brief.py markdown footer ``papers_required``
linkage was inconsistent.

Pre-fix the footer string was hardcoded "Papers required on every
deal." regardless of sourcing_rules.json's ``papers_required`` value;
the JSON brief's top-level ``sourcing_rules.papers_required`` field
correctly reflected the file. Fix: footer reads from
``sourcing_rules['papers_required']`` so the markdown matches the JSON.

Per-target hardcoded ``papers_required: True`` (build_brief.py:214) is
out of scope for this fix; flagged as Phase D backlog.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from scripts.build_brief import build_brief


def _ref(brand="Tudor", model="BB GMT", reference="79830RB",
         median=3200, st_pct=0.6, max_buy_nr=2910, max_buy_res=2770,
         risk_nr=8.0, signal="Strong", recommend_reserve=False,
         floor=3000, volume=5) -> dict:
    return {
        "brand": brand, "model": model, "reference": reference,
        "median": median, "st_pct": st_pct, "max_buy_nr": max_buy_nr,
        "max_buy_res": max_buy_res, "risk_nr": risk_nr, "signal": signal,
        "recommend_reserve": recommend_reserve, "floor": floor, "volume": volume,
    }


def _run_brief_with_papers_setting(tmp_path, papers_required: bool) -> str:
    """Run build_brief with sourcing_rules.papers_required overridden;
    return the markdown brief contents."""
    from scripts.config_helper import write_config
    from scripts.grailzee_common import (
        SOURCING_RULES_FACTORY_DEFAULTS,
        _reset_sourcing_rules_cache,
    )

    _reset_sourcing_rules_cache()
    rules_path = tmp_path / "sourcing_rules.json"
    content = json.loads(json.dumps(SOURCING_RULES_FACTORY_DEFAULTS))
    content["papers_required"] = papers_required
    write_config(rules_path, content, [], "test")

    all_results = {"references": {"79830RB": _ref()}, "dj_configs": {}}
    trends = {"trends": [], "momentum": {}}
    brief_json = str(tmp_path / "sourcing_brief.json")

    # build_brief imports load_sourcing_rules from grailzee_common; patch
    # the call site so we don't need to wire the file through every loader
    # cache toggle.
    try:
        with patch("scripts.build_brief.BRIEF_PATH", brief_json), \
             patch("scripts.build_brief.load_sourcing_rules",
                   return_value=content):
            result = build_brief(all_results, trends, {}, {}, {}, str(tmp_path))
    finally:
        _reset_sourcing_rules_cache()

    md_path = Path(result["md_path"])
    return md_path.read_text()


class TestPapersRequiredFooterLinkage:
    def test_footer_reflects_required_when_true(self, tmp_path):
        md = _run_brief_with_papers_setting(tmp_path, papers_required=True)
        assert "Papers required on every deal." in md
        assert "Papers not required." not in md

    def test_footer_reflects_not_required_when_false(self, tmp_path):
        """Pre-fix this would have failed: footer was hardcoded
        "Papers required on every deal." regardless of the config.
        Post-fix it reads from sourcing_rules['papers_required']."""
        md = _run_brief_with_papers_setting(tmp_path, papers_required=False)
        assert "Papers not required." in md
        assert "Papers required on every deal." not in md
