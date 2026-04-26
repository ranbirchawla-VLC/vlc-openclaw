"""Tests for scripts.evaluate_deal under the v3 / Step 1 contract.

Contract reference: Grailzee_Architecture_Lock_2026-04-26 + Step 1 prompt.
- Yes/no only on deal eval; no MAYBE state.
- v3 cache is the source of truth (schema_version 3, per-bucket market fields).
- Matcher narrows by 0-3 optional axes (dial_numerals, auction_type,
  dial_color) until single bucket; ambiguous returns candidates so the LLM
  can ask one clarifying question.
- Premium scalar (analyzer_config.scoring.premium_scalar_fraction) applied
  uniformly to bucket.median; max_buy recomputed at evaluation time.
- cycle_focus surfaces on_plan boolean + matching target metadata; does
  NOT gate the decision (math gates the decision).
- _on_demand_analysis fallback is deleted; cache miss returns
  match_resolution: reference_not_found with decision: no.

Hand-computed math:
  premium_scalar = 0.10, target_margin = 0.05, NR_FIXED = 149.

  Boundary case (yes_at_margin_floor):
    median = 1090
    adjusted_price = 1090 * 1.10 = 1199.0
    max_buy = (1199 - 149) / 1.05 = 1000.0
    listing_price = 1000  → margin_pct = (1199 - 1000 - 149)/1000 * 100 = 5.0%

  Strong yes:
    median = 3200, listing = 2000
    adjusted_price = 3520.0
    max_buy = (3520 - 149)/1.05 ≈ 3210.476 → rounded to 3210
    margin_pct ≈ 68.55%

  No (above max):
    median = 3200, listing = 3500
    max_buy ≈ 3210; listing > max_buy → no.

Return shape:
    {
      "decision": "yes" | "no",
      "reference": str,
      "bucket": {dial_numerals, auction_type, dial_color, named_special} | None,
      "math": {listing_price, premium_scalar, adjusted_price, max_buy, margin_pct} | None,
      "cycle_context": {on_plan: bool, target_match: dict | None},
      "match_resolution": "single_bucket | ambiguous | no_match | reference_not_found",
      "candidates": [bucket_dict, ...]   # only on ambiguous
    }
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.grailzee_common import (
    CACHE_SCHEMA_VERSION,
    NR_FIXED,
    _reset_analyzer_config_cache,
)
from scripts.evaluate_deal import (
    evaluate,
    _match_buckets,
    _parse_price_arg,
)


# ─── Fixture builders ────────────────────────────────────────────────


def _make_bucket(
    *,
    dial_numerals: str = "Arabic",
    auction_type: str = "nr",
    dial_color: str = "Black",
    named_special: str | None = None,
    signal: str = "Strong",
    median: float | None = 3200,
    max_buy_nr: float | None = 2910,
    max_buy_res: float | None = 2860,
    risk_nr: float | None = 8.5,
    volume: int = 12,
    st_pct: float | None = 0.78,
    condition_mix: str = '{"very good":0.5,"like new":0.5}',
) -> dict:
    """Build one v3 bucket dict.

    Note auction_type is lowercased in the bucket body (per
    analyze_buckets.score_bucket); dial_numerals and dial_color are
    case-preserved.
    """
    return {
        "dial_numerals": dial_numerals,
        "auction_type": auction_type,
        "dial_color": dial_color,
        "named_special": named_special,
        "signal": signal,
        "median": median,
        "max_buy_nr": max_buy_nr,
        "max_buy_res": max_buy_res,
        "risk_nr": risk_nr,
        "volume": volume,
        "st_pct": st_pct,
        "condition_mix": condition_mix,
        "capital_required_nr": None,
        "capital_required_res": None,
        "expected_net_at_median_nr": None,
        "expected_net_at_median_res": None,
    }


def _bucket_key(bucket: dict) -> str:
    return (
        f"{bucket['dial_numerals'].lower()}"
        f"|{bucket['auction_type'].lower()}"
        f"|{bucket['dial_color'].lower()}"
    )


def _make_ref(
    *,
    brand: str = "Tudor",
    model: str = "BB GMT Pepsi",
    reference: str = "79830RB",
    buckets: list[dict] | None = None,
    named: bool = True,
) -> dict:
    """Build one v3 per-reference cache entry."""
    bucket_dict = {}
    if buckets:
        for b in buckets:
            bucket_dict[_bucket_key(b)] = b
    return {
        "brand": brand,
        "model": model,
        "reference": reference,
        "named": named,
        "trend_signal": None,
        "trend_median_change": None,
        "trend_median_pct": None,
        "momentum": None,
        "confidence": None,
        "buckets": bucket_dict,
    }


def _make_v3_cache(
    *,
    refs: dict | None = None,
    cycle_id: str = "cycle_2026-15",
    generated_at: str = "2026-04-15T10:30:00",
    source_report: str = "grailzee_2026-04-12.csv",
) -> dict:
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_report": source_report,
        "cycle_id": cycle_id,
        "premium_status": {
            "avg_premium": 0,
            "trade_count": 0,
            "threshold_met": False,
            "adjustment": 0,
            "trades_to_threshold": 10,
        },
        "references": refs or {},
        "dj_configs": {},
    }


def _write_cache(tmp_path, cache_dict) -> str:
    p = tmp_path / "analysis_cache.json"
    p.write_text(json.dumps(cache_dict, indent=2))
    return str(p)


def _write_cycle_focus(tmp_path, focus_dict) -> str:
    p = tmp_path / "cycle_focus.json"
    p.write_text(json.dumps(focus_dict, indent=2))
    return str(p)


def _on_plan_focus(*targets: dict, cycle_id: str = "cycle_2026-15") -> dict:
    return {
        "cycle_id": cycle_id,
        "targets": list(targets),
        "capital_target": 60000,
        "volume_target": 10,
        "target_margin_fraction": 0.05,
        "brand_emphasis": [],
        "brand_pullback": [],
        "notes": "",
    }


@pytest.fixture(autouse=True)
def _reset_config_between_tests():
    """Each test gets a fresh analyzer_config read.

    The module caches the config across calls; tests that override the
    config path or rely on production defaults need a clean slate so
    earlier-test state does not leak.
    """
    _reset_analyzer_config_cache()
    yield
    _reset_analyzer_config_cache()


# ═══════════════════════════════════════════════════════════════════════
# A. Matcher resolution
# ═══════════════════════════════════════════════════════════════════════


class TestMatcherResolution:
    """Direct tests for _match_buckets pure-function matcher."""

    def test_single_bucket_no_axes(self):
        b = _make_bucket()
        ref = _make_ref(buckets=[b])
        resolution, picked, candidates = _match_buckets(ref)
        assert resolution == "single_bucket"
        assert picked is b
        assert candidates == []

    def test_single_bucket_axes_match(self):
        b = _make_bucket(dial_numerals="Arabic", auction_type="nr", dial_color="Black")
        ref = _make_ref(buckets=[b])
        resolution, picked, _ = _match_buckets(
            ref, dial_numerals="Arabic", auction_type="NR", dial_color="Black",
        )
        assert resolution == "single_bucket"
        assert picked is b

    def test_axes_narrow_to_single(self):
        b1 = _make_bucket(dial_color="Black")
        b2 = _make_bucket(dial_color="Blue")
        b3 = _make_bucket(dial_color="Slate")
        ref = _make_ref(buckets=[b1, b2, b3])
        resolution, picked, _ = _match_buckets(ref, dial_color="Blue")
        assert resolution == "single_bucket"
        assert picked["dial_color"] == "Blue"

    def test_axes_partial_narrow_to_single(self):
        b1 = _make_bucket(dial_numerals="Arabic", dial_color="Black")
        b2 = _make_bucket(dial_numerals="Arabic", dial_color="Blue")
        b3 = _make_bucket(dial_numerals="Roman", dial_color="Black")
        ref = _make_ref(buckets=[b1, b2, b3])
        # dial_numerals="Roman" alone narrows to one
        resolution, picked, _ = _match_buckets(ref, dial_numerals="Roman")
        assert resolution == "single_bucket"
        assert picked["dial_numerals"] == "Roman"

    def test_ambiguous_no_axes_multiple_buckets(self):
        b1 = _make_bucket(dial_color="Black")
        b2 = _make_bucket(dial_color="Blue")
        ref = _make_ref(buckets=[b1, b2])
        resolution, picked, candidates = _match_buckets(ref)
        assert resolution == "ambiguous"
        assert picked is None
        assert len(candidates) == 2
        assert {c["dial_color"] for c in candidates} == {"Black", "Blue"}

    def test_ambiguous_axes_partial_no_narrow(self):
        b1 = _make_bucket(dial_numerals="Arabic", dial_color="Black")
        b2 = _make_bucket(dial_numerals="Arabic", dial_color="Blue")
        ref = _make_ref(buckets=[b1, b2])
        resolution, picked, candidates = _match_buckets(ref, dial_numerals="Arabic")
        assert resolution == "ambiguous"
        assert picked is None
        assert len(candidates) == 2

    def test_no_match_axes_unmatched(self):
        b = _make_bucket(dial_color="Black")
        ref = _make_ref(buckets=[b])
        resolution, picked, candidates = _match_buckets(ref, dial_color="Green")
        assert resolution == "no_match"
        assert picked is None
        assert candidates == []

    def test_axes_case_insensitive(self):
        b = _make_bucket(dial_numerals="Arabic", auction_type="nr", dial_color="Black")
        ref = _make_ref(buckets=[b])
        resolution, picked, _ = _match_buckets(
            ref, dial_numerals="arabic", auction_type="nr", dial_color="black",
        )
        assert resolution == "single_bucket"
        assert picked is b


# ═══════════════════════════════════════════════════════════════════════
# B. Decision math (yes/no only)
# ═══════════════════════════════════════════════════════════════════════


class TestDecisionMath:

    def test_yes_well_below_max(self, tmp_path):
        """Listing price clearly below max_buy → yes.

        median=3200, premium=0.10, target=0.05, NR fees=149.
        adjusted_price = 3520.0
        max_buy unrounded = 3210.476 → rounded = 3210
        listing=2000 → margin = (3520-2000-149)/2000 = 68.55%
        """
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200, signal="Strong")]),
        }))
        result = evaluate(
            "Tudor", "79830RB", 2000,
            cache_path=cache_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
        )
        assert result["decision"] == "yes"
        assert result["match_resolution"] == "single_bucket"
        assert result["math"]["adjusted_price"] == pytest.approx(3520.0)
        assert result["math"]["max_buy"] == 3210
        assert result["math"]["listing_price"] == 2000
        assert result["math"]["premium_scalar"] == pytest.approx(0.10)
        assert result["math"]["margin_pct"] == pytest.approx(68.55, abs=0.01)

    def test_yes_at_margin_floor(self, tmp_path):
        """Boundary case: listing == max_buy → margin_pct == 5.0% (target).

        Hand-picked so rounding holds:
          median = 1090
          adjusted_price = 1090 * 1.10 = 1199
          max_buy = (1199 - 149) / 1.05 = 1000.0 (rounds to 1000)
          listing = 1000 → margin = (1199 - 1000 - 149)/1000 * 100 = 5.0%
        """
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "FLOOR": _make_ref(
                reference="FLOOR",
                buckets=[_make_bucket(median=1090, signal="Strong")],
            ),
        }))
        result = evaluate(
            "Tudor", "FLOOR", 1000,
            cache_path=cache_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
        )
        assert result["decision"] == "yes"
        assert result["math"]["max_buy"] == 1000
        assert result["math"]["listing_price"] == 1000
        assert result["math"]["adjusted_price"] == pytest.approx(1199.0)
        assert result["math"]["margin_pct"] == pytest.approx(5.0, abs=0.01)

    def test_max_buy_floor_rounds_below_5pct_unrounded(self, tmp_path):
        """Architecture lock §1: 5% margin floor is non-negotiable.

        Hand-picked case where nearest-rounding and floor-rounding diverge:
          median = 2768
          adjusted_price = 2768 * 1.10 = 3044.8
          max_buy unrounded = (3044.8 - 149) / 1.05 = 2757.9048

          nearest-round → 2760 (margin at 2760 = 4.92%; violates floor)
          floor-round   → 2750 (margin at 2750 = 5.30%; safe)

        Assertions: max_buy is 2750 (floor-rounded); listing at 2750 is
        yes with margin_pct >= 5.0; listing at 2760 is no (above max).
        Old round(_, -1) returned 2760 and would have flagged 2760 as yes
        with margin 4.92%, breaking the architectural floor.
        """
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "FLOOR2": _make_ref(
                reference="FLOOR2",
                buckets=[_make_bucket(median=2768, signal="Strong")],
            ),
        }))

        result_at_floor = evaluate(
            "Tudor", "FLOOR2", 2750,
            cache_path=cache_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
        )
        assert result_at_floor["math"]["max_buy"] == 2750
        assert result_at_floor["decision"] == "yes"
        assert result_at_floor["math"]["margin_pct"] >= 5.0

        result_above = evaluate(
            "Tudor", "FLOOR2", 2760,
            cache_path=cache_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
        )
        assert result_above["math"]["max_buy"] == 2750
        assert result_above["decision"] == "no"

    def test_no_above_max(self, tmp_path):
        """Listing > max_buy → no, math still populated."""
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200, signal="Strong")]),
        }))
        result = evaluate(
            "Tudor", "79830RB", 3500,
            cache_path=cache_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
        )
        assert result["decision"] == "no"
        assert result["match_resolution"] == "single_bucket"
        assert result["math"]["max_buy"] == 3210
        assert result["math"]["listing_price"] == 3500
        # margin_pct = (3520 - 3500 - 149)/3500 * 100 = -3.686%
        assert result["math"]["margin_pct"] == pytest.approx(-3.69, abs=0.01)

    def test_no_signal_pass(self, tmp_path):
        """Signal=Pass → no even if math would clear."""
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "PASSREF": _make_ref(
                brand="TestBrand", model="Pass", reference="PASSREF",
                buckets=[_make_bucket(median=3200, signal="Pass", risk_nr=55.0)],
            ),
        }))
        result = evaluate(
            "TestBrand", "PASSREF", 1000,
            cache_path=cache_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
        )
        assert result["decision"] == "no"
        # math still populated for visibility
        assert result["math"] is not None
        assert result["bucket"]["named_special"] is None

    def test_low_data_signal_no(self, tmp_path):
        """Bucket with signal=Low data → no (math fields nullable)."""
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "LOW": _make_ref(
                reference="LOW",
                buckets=[_make_bucket(
                    signal="Low data", median=None, max_buy_nr=None, max_buy_res=None,
                    risk_nr=None, volume=2,
                )],
            ),
        }))
        result = evaluate(
            "Tudor", "LOW", 1000,
            cache_path=cache_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
        )
        assert result["decision"] == "no"
        assert result["match_resolution"] == "single_bucket"


# ═══════════════════════════════════════════════════════════════════════
# C. Premium scalar applied uniformly
# ═══════════════════════════════════════════════════════════════════════


class TestPremiumScalar:

    def test_premium_scalar_in_math(self, tmp_path):
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200)]),
        }))
        result = evaluate(
            "Tudor", "79830RB", 2000,
            cache_path=cache_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
        )
        # production analyzer_config defaults to 0.10
        assert result["math"]["premium_scalar"] == pytest.approx(0.10)

    def test_adjusted_price_uses_scalar(self, tmp_path):
        """adjusted_price = bucket.median * (1 + premium_scalar)."""
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=5000)]),
        }))
        result = evaluate(
            "Tudor", "79830RB", 4000,
            cache_path=cache_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
        )
        # 5000 * 1.10 = 5500
        assert result["math"]["adjusted_price"] == pytest.approx(5500.0)


# ═══════════════════════════════════════════════════════════════════════
# D. Cycle context (on_plan; does not gate decision)
# ═══════════════════════════════════════════════════════════════════════


class TestCycleContext:

    def test_on_plan_true(self, tmp_path):
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200)]),
        }))
        focus_path = _write_cycle_focus(
            tmp_path,
            _on_plan_focus(
                {"reference": "79830RB", "brand": "Tudor", "model": "BB GMT",
                 "cycle_reason": "GMT season", "max_buy_override": None},
            ),
        )
        result = evaluate(
            "Tudor", "79830RB", 2000,
            cache_path=cache_path,
            cycle_focus_path=focus_path,
        )
        assert result["cycle_context"]["on_plan"] is True
        tm = result["cycle_context"]["target_match"]
        assert tm["reference"] == "79830RB"
        assert tm["brand"] == "Tudor"

    def test_off_plan_false(self, tmp_path):
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200)]),
        }))
        focus_path = _write_cycle_focus(
            tmp_path,
            _on_plan_focus(
                {"reference": "OTHER", "brand": "Other", "model": "Other",
                 "cycle_reason": "x", "max_buy_override": None},
            ),
        )
        result = evaluate(
            "Tudor", "79830RB", 2000,
            cache_path=cache_path,
            cycle_focus_path=focus_path,
        )
        assert result["cycle_context"]["on_plan"] is False
        assert result["cycle_context"]["target_match"] is None

    def test_no_cycle_focus_file(self, tmp_path):
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200)]),
        }))
        result = evaluate(
            "Tudor", "79830RB", 2000,
            cache_path=cache_path,
            cycle_focus_path=str(tmp_path / "missing_focus.json"),
        )
        assert result["cycle_context"]["on_plan"] is False
        assert result["cycle_context"]["target_match"] is None

    def test_off_plan_does_not_gate_yes(self, tmp_path):
        """Math clears + off plan → decision still yes (cycle is metadata)."""
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200)]),
        }))
        focus_path = _write_cycle_focus(
            tmp_path,
            _on_plan_focus(
                {"reference": "OTHER", "brand": "Other", "model": "Other",
                 "cycle_reason": "x", "max_buy_override": None},
            ),
        )
        result = evaluate(
            "Tudor", "79830RB", 2000,
            cache_path=cache_path,
            cycle_focus_path=focus_path,
        )
        assert result["decision"] == "yes"
        assert result["cycle_context"]["on_plan"] is False


# ═══════════════════════════════════════════════════════════════════════
# E. Match resolutions surfaced through evaluate()
# ═══════════════════════════════════════════════════════════════════════


class TestMatchResolutions:

    def test_ambiguous_returns_candidates(self, tmp_path):
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "126300": _make_ref(
                brand="Rolex", model="DJ 41", reference="126300",
                buckets=[
                    _make_bucket(dial_color="Black", median=11000),
                    _make_bucket(dial_color="Blue", median=12000),
                ],
            ),
        }))
        result = evaluate(
            "Rolex", "126300", 9500,
            cache_path=cache_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
        )
        assert result["decision"] == "no"
        assert result["match_resolution"] == "ambiguous"
        assert result["bucket"] is None
        assert result["math"] is None
        assert len(result["candidates"]) == 2
        # candidates carry enough for the LLM to ask one clarifying question
        for c in result["candidates"]:
            assert "dial_numerals" in c
            assert "auction_type" in c
            assert "dial_color" in c

    def test_no_match_returns_no(self, tmp_path):
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(dial_color="Black")]),
        }))
        result = evaluate(
            "Tudor", "79830RB", 2000,
            dial_color="Green",
            cache_path=cache_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
        )
        assert result["decision"] == "no"
        assert result["match_resolution"] == "no_match"
        assert result["bucket"] is None
        assert result["math"] is None

    def test_reference_not_found(self, tmp_path):
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket()]),
        }))
        result = evaluate(
            "Breitling", "UNKNOWN999", 3000,
            cache_path=cache_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
        )
        assert result["decision"] == "no"
        assert result["match_resolution"] == "reference_not_found"
        assert result["bucket"] is None
        assert result["math"] is None
        assert result["reference"] == "UNKNOWN999"


# ═══════════════════════════════════════════════════════════════════════
# F. Reference lookup variants (preserved from v2)
# ═══════════════════════════════════════════════════════════════════════


class TestReferenceLookup:
    """Cache lookup tolerates the same reference-string variants as v2."""

    def test_normalized_match_trailing_dot_zero(self, tmp_path):
        """Excel artifact: 79830RB.0 maps to 79830RB."""
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket()]),
        }))
        result = evaluate(
            "Tudor", "79830RB.0", 2000,
            cache_path=cache_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
        )
        assert result["match_resolution"] == "single_bucket"

    def test_stripped_match_m_prefix(self, tmp_path):
        """Tudor M-prefix: M79830RB matches 79830RB."""
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket()]),
        }))
        result = evaluate(
            "Tudor", "M79830RB", 2000,
            cache_path=cache_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
        )
        assert result["match_resolution"] == "single_bucket"


# ═══════════════════════════════════════════════════════════════════════
# G. Error paths
# ═══════════════════════════════════════════════════════════════════════


class TestErrorPaths:

    def test_missing_cache_file(self, tmp_path):
        result = evaluate(
            "Tudor", "79830RB", 2000,
            cache_path=str(tmp_path / "nonexistent.json"),
        )
        assert result["decision"] == "no"
        assert result["match_resolution"] == "error"
        assert "no_cache" in result["error"]

    def test_stale_schema(self, tmp_path):
        """v2 cache (schema_version=2) → error."""
        stale = _make_v3_cache()
        stale["schema_version"] = 2
        cache_path = _write_cache(tmp_path, stale)
        result = evaluate(
            "Tudor", "79830RB", 2000,
            cache_path=cache_path,
        )
        assert result["decision"] == "no"
        assert result["match_resolution"] == "error"
        assert "stale_schema" in result["error"]

    def test_bad_price_arg(self):
        with pytest.raises(ValueError):
            _parse_price_arg("abc")

    def test_parse_price_strips_formatting(self):
        assert _parse_price_arg("$2,750") == 2750.0
        assert _parse_price_arg("3000") == 3000.0


# ═══════════════════════════════════════════════════════════════════════
# H. CLI smoke
# ═══════════════════════════════════════════════════════════════════════


class TestCLI:

    def test_cli_smoke(self, tmp_path):
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200)]),
        }))
        script = str(
            Path(__file__).resolve().parent.parent / "scripts" / "evaluate_deal.py"
        )
        proc = subprocess.run(
            [
                sys.executable, script,
                "Tudor", "79830RB", "2000",
                "--cache", cache_path,
                "--cycle-focus", str(tmp_path / "no_focus.json"),
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert result["decision"] in ("yes", "no")
        assert "math" in result
        assert "match_resolution" in result

    def test_cli_with_axes(self, tmp_path):
        """CLI accepts --dial-numerals, --auction-type, --dial-color."""
        cache_path = _write_cache(tmp_path, _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[
                _make_bucket(dial_color="Black"),
                _make_bucket(dial_color="Blue"),
            ]),
        }))
        script = str(
            Path(__file__).resolve().parent.parent / "scripts" / "evaluate_deal.py"
        )
        proc = subprocess.run(
            [
                sys.executable, script,
                "Tudor", "79830RB", "2000",
                "--dial-color", "Blue",
                "--cache", cache_path,
                "--cycle-focus", str(tmp_path / "no_focus.json"),
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert result["match_resolution"] == "single_bucket"
        assert result["bucket"]["dial_color"] == "Blue"

    def test_cli_bad_price(self, tmp_path):
        cache_path = _write_cache(tmp_path, _make_v3_cache())
        script = str(
            Path(__file__).resolve().parent.parent / "scripts" / "evaluate_deal.py"
        )
        proc = subprocess.run(
            [
                sys.executable, script,
                "Tudor", "79830RB", "notanumber",
                "--cache", cache_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert proc.returncode == 1
        result = json.loads(proc.stdout)
        assert result.get("error") == "bad_price"
