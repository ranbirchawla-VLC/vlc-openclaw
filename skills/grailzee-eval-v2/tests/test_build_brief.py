"""Tests for scripts.build_brief; sourcing brief (JSON + MD) per guide Section 12.2.

Partial extraction from v1 analyze_report.py:718-980. Adapted for v2.
v1/v2 equivalence: priority scoring and target schema match v1; schema_version
bumped to 2.

Hand-computed priority scores:
──────────────────────────────────────────────────────────────────────
  Ref       Signal   trend_pct  vol  st_pct  sig  trnd  vol  st  TOTAL  Label
  ──────────────────────────────────────────────────────────────────
  79830RB   Strong   6.67       5    0.60    +3   +2    +0   +1  6      HIGH
  A17320    Normal   0.0        3    0.45    +2   +1    +0   +0  3      LOW
  91650     Reserve  -6.0       15   0.80    +1   +0    +1   +1  3      LOW
──────────────────────────────────────────────────────────────────────

Sweet spot = round(max_buy * 0.9, -1):
  79830RB: round(2910 * 0.9, -1) = round(2619, -1) = 2620
  A17320:  round(2100 * 0.9, -1) = round(1890, -1) = 1890
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.build_brief import build_brief, _priority_score, _priority_label


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


def _build(tmp_path, refs=None, trends=None):
    all_results = {
        "references": refs if refs is not None else {"79830RB": _ref()},
        "dj_configs": {},
    }
    tr = trends if trends is not None else {"trends": [], "momentum": {}}
    # Patch BRIEF_PATH to tmp_path
    brief_json = str(tmp_path / "sourcing_brief.json")
    with patch("scripts.build_brief.BRIEF_PATH", brief_json):
        return build_brief(all_results, tr, {}, {}, {}, str(tmp_path))


# ═══════════════════════════════════════════════════════════════════════
# Priority scoring
# ═══════════════════════════════════════════════════════════════════════


class TestPriorityScoring:
    def test_strong_rising_with_st(self):
        """Strong(+3) + trend 6.67%(+2) + vol<15(+0) + st 0.60(+1) = 6 -> HIGH."""
        rd = _ref(signal="Strong", volume=5, st_pct=0.60)
        assert _priority_score(rd, 6.67) == 6
        assert _priority_label(6) == "HIGH"

    def test_normal_flat_low_st(self):
        """Normal(+2) + trend 0%(+1) + vol<15(+0) + st 0.45(+0) = 3 -> LOW."""
        rd = _ref(signal="Normal", volume=3, st_pct=0.45)
        assert _priority_score(rd, 0.0) == 3
        assert _priority_label(3) == "LOW"

    def test_reserve_falling_high_vol_high_st(self):
        """Reserve(+1) + trend -6%(+0) + vol 15(+1) + st 0.80(+1) = 3 -> LOW."""
        rd = _ref(signal="Reserve", volume=15, st_pct=0.80)
        assert _priority_score(rd, -6.0) == 3
        assert _priority_label(3) == "LOW"

    def test_medium_boundary(self):
        """Score 4 -> MEDIUM. Score 5 -> MEDIUM. Score 6 -> HIGH."""
        assert _priority_label(4) == "MEDIUM"
        assert _priority_label(5) == "MEDIUM"
        assert _priority_label(6) == "HIGH"

    def test_pass_signal_excluded(self, tmp_path):
        """Pass and Low data signals excluded from targets."""
        refs = {
            "P1": _ref(reference="P1", signal="Pass"),
            "P2": _ref(reference="P2", signal="Low data"),
            "OK": _ref(reference="OK", signal="Strong"),
        }
        result = _build(tmp_path, refs=refs)
        brief = json.loads(Path(result["json_path"]).read_text())
        target_refs = [t["reference"] for t in brief["targets"]]
        assert "P1" not in target_refs
        assert "P2" not in target_refs
        assert "OK" in target_refs


# ═══════════════════════════════════════════════════════════════════════
# Sweet spot calculation
# ═══════════════════════════════════════════════════════════════════════


class TestSweetSpot:
    def test_nr_sweet_spot(self, tmp_path):
        """79830RB NR: round(2910 * 0.9, -1) = 2620."""
        result = _build(tmp_path)
        brief = json.loads(Path(result["json_path"]).read_text())
        t = brief["targets"][0]
        assert t["sweet_spot"] == 2620

    def test_reserve_sweet_spot(self, tmp_path):
        """Reserve ref uses max_buy_res: round(2100 * 0.9, -1) = 1890."""
        refs = {"A17320": _ref(
            brand="Breitling", model="SO Heritage", reference="A17320",
            max_buy_res=2100, signal="Reserve", recommend_reserve=True,
        )}
        result = _build(tmp_path, refs=refs)
        brief = json.loads(Path(result["json_path"]).read_text())
        t = brief["targets"][0]
        assert t["sweet_spot"] == 1890
        assert t["format"] == "Reserve"


# ═══════════════════════════════════════════════════════════════════════
# JSON schema
# ═══════════════════════════════════════════════════════════════════════


class TestJSONSchema:
    def test_top_level_keys(self, tmp_path):
        result = _build(tmp_path)
        brief = json.loads(Path(result["json_path"]).read_text())
        assert set(brief.keys()) == {
            "schema_version", "generated_at", "valid_until",
            "sourcing_rules", "targets", "summary",
        }
        assert brief["schema_version"] == 2

    def test_target_keys(self, tmp_path):
        result = _build(tmp_path)
        brief = json.loads(Path(result["json_path"]).read_text())
        t = brief["targets"][0]
        expected_keys = {
            "brand", "model", "reference", "priority", "priority_score",
            "max_buy", "sweet_spot", "median", "floor", "format", "signal",
            "risk_vg_pct", "volume", "sell_through", "trend", "trend_pct",
            "momentum", "search_terms", "condition_filter", "papers_required",
            "action", "notes",
        }
        assert set(t.keys()) == expected_keys

    def test_summary_keys(self, tmp_path):
        result = _build(tmp_path)
        brief = json.loads(Path(result["json_path"]).read_text())
        s = brief["summary"]
        assert set(s.keys()) == {
            "total_targets", "high_priority", "medium_priority",
            "low_priority", "lowest_entry_point", "highest_entry_point",
        }

    def test_sourcing_rules_present(self, tmp_path):
        result = _build(tmp_path)
        brief = json.loads(Path(result["json_path"]).read_text())
        rules = brief["sourcing_rules"]
        assert rules["us_inventory_only"] is True
        assert rules["papers_required"] is True
        assert len(rules["platform_priority"]) == 5


# ═══════════════════════════════════════════════════════════════════════
# Full fixture deep equality
# ═══════════════════════════════════════════════════════════════════════


class TestFullFixture:
    def test_target_values(self, tmp_path):
        """Verify target fields against hand-computed constants."""
        trends = {
            "trends": [{
                "reference": "79830RB", "brand": "Tudor", "model": "BB GMT",
                "prev_median": 3000, "curr_median": 3200, "med_change": 200,
                "med_pct": 6.67, "prev_st": None, "curr_st": None,
                "st_change": None, "prev_vol": 4, "curr_vol": 5,
                "signals": ["Momentum"], "signal_str": "Momentum",
            }],
            "momentum": {"79830RB": {"score": 1, "label": "Warming"}},
        }
        result = _build(tmp_path, trends=trends)
        brief = json.loads(Path(result["json_path"]).read_text())
        t = brief["targets"][0]
        assert t["reference"] == "79830RB"
        assert t["priority"] == "HIGH"
        assert t["priority_score"] == 6
        assert t["max_buy"] == 2910
        assert t["sweet_spot"] == 2620
        assert t["format"] == "NR"
        assert t["trend"] == "Momentum"
        assert t["trend_pct"] == 6.7  # round(6.67, 1)
        assert t["momentum"] == {"score": 1, "label": "Warming"}
        assert t["action"] == "auto_evaluate"


# ═══════════════════════════════════════════════════════════════════════
# Markdown output
# ═══════════════════════════════════════════════════════════════════════


class TestMarkdownOutput:
    def test_md_file_exists(self, tmp_path):
        result = _build(tmp_path)
        assert Path(result["md_path"]).exists()

    def test_md_contains_sections(self, tmp_path):
        result = _build(tmp_path)
        content = Path(result["md_path"]).read_text()
        assert "# Vardalux Sourcing Brief" in content
        assert "## Active Targets" in content
        assert "## Search Keywords" in content
        assert "## Platform Scan Order" in content

    def test_md_filename_convention(self, tmp_path):
        result = _build(tmp_path)
        assert "Vardalux_Sourcing_Brief_" in Path(result["md_path"]).name


# ═══════════════════════════════════════════════════════════════════════
# Search terms
# ═══════════════════════════════════════════════════════════════════════


class TestSearchTerms:
    def test_tudor_search_terms(self, tmp_path):
        """Tudor ref without M prefix gets M-prefixed variant."""
        result = _build(tmp_path)
        brief = json.loads(Path(result["json_path"]).read_text())
        t = brief["targets"][0]
        assert "Tudor 79830RB" in t["search_terms"]
        assert "Tudor M79830RB" in t["search_terms"]

    def test_omega_search_terms(self, tmp_path):
        """Omega ref with dots gets dot-stripped variant."""
        refs = {"210.30.42.20.03.001": _ref(
            brand="Omega", model="Seamaster", reference="210.30.42.20.03.001",
        )}
        result = _build(tmp_path, refs=refs)
        brief = json.loads(Path(result["json_path"]).read_text())
        t = brief["targets"][0]
        assert "Omega 21030422003001" in t["search_terms"]


# ═══════════════════════════════════════════════════════════════════════
# Empty input
# ═══════════════════════════════════════════════════════════════════════


class TestEmptyInput:
    def test_empty_produces_valid_json(self, tmp_path):
        result = _build(tmp_path, refs={})
        brief = json.loads(Path(result["json_path"]).read_text())
        assert brief["targets"] == []
        assert brief["summary"]["total_targets"] == 0
        assert brief["summary"]["lowest_entry_point"] == 0
        assert brief["summary"]["highest_entry_point"] == 0

    def test_empty_produces_valid_md(self, tmp_path):
        result = _build(tmp_path, refs={})
        assert Path(result["md_path"]).exists()
        content = Path(result["md_path"]).read_text()
        assert "0 references" in content


# ═══════════════════════════════════════════════════════════════════════
# Momentum integration
# ═══════════════════════════════════════════════════════════════════════


class TestMomentum:
    def test_momentum_included_when_available(self, tmp_path):
        trends = {"trends": [], "momentum": {"79830RB": {"score": 2, "label": "Heating Up"}}}
        result = _build(tmp_path, trends=trends)
        brief = json.loads(Path(result["json_path"]).read_text())
        t = brief["targets"][0]
        assert t["momentum"] == {"score": 2, "label": "Heating Up"}

    def test_momentum_null_when_absent(self, tmp_path):
        result = _build(tmp_path, trends={"trends": [], "momentum": {}})
        brief = json.loads(Path(result["json_path"]).read_text())
        t = brief["targets"][0]
        assert t["momentum"] is None
