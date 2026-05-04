"""Tests for turn_state.py capability routing tool.

Covers:
- Classifier: slash command routing, free-form deal detection, keyword routing, default
- Capability loading: file present, file absent, default/unknown intents return empty
- compute_turn_state: integration with injected capabilities_dir
- Main entry point: stdin JSON -> stdout JSON via subprocess
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from turn_state import _classify, _load_capability, compute_turn_state


# ─── Classifier ──────────────────────────────────────────────────────


class TestClassifier:
    def test_eval_slash(self):
        assert _classify("/eval") == "evaluate_deal"

    def test_eval_slash_with_deal_content(self):
        assert _classify("/eval Tudor 79830RB $2,750") == "evaluate_deal"

    def test_eval_slash_case_insensitive(self):
        assert _classify("/EVAL Tudor") == "evaluate_deal"

    def test_report_slash(self):
        assert _classify("/report") == "report"

    def test_report_slash_case_insensitive(self):
        assert _classify("/REPORT") == "report"

    def test_ledger_slash(self):
        assert _classify("/ledger") == "ledger"

    def test_ledger_slash_case_insensitive(self):
        assert _classify("/LEDGER") == "ledger"

    def test_free_form_deal_dollar_with_comma(self):
        assert _classify("Tudor 79830RB at $2,750") == "evaluate_deal"

    def test_free_form_deal_dollar_no_space(self):
        assert _classify("Rolex 116610LN $8500") == "evaluate_deal"

    def test_free_form_deal_dollar_mid_sentence(self):
        assert _classify("Can I buy this Omega 210.30 for $3,200?") == "evaluate_deal"

    def test_free_form_deal_dollar_with_axes(self):
        assert _classify("Breitling A17320 $2,400 Black Arabic NR") == "evaluate_deal"

    def test_report_keyword_new_report(self):
        assert _classify("new report is ready") == "report"

    def test_report_keyword_report_is_in(self):
        assert _classify("report is in") == "report"

    def test_report_keyword_xlsx(self):
        assert _classify("grailzee_2026-05-04.xlsx is in") == "report"

    def test_report_keyword_pipeline(self):
        assert _classify("run the pipeline") == "report"

    def test_report_keyword_grailzee_pro(self):
        assert _classify("new grailzee pro is in") == "report"

    def test_ledger_keyword_ledger(self):
        assert _classify("fold in the ledger update") == "ledger"

    def test_ledger_keyword_ingest(self):
        assert _classify("run the ingest") == "ledger"

    def test_ledger_keyword_watchtrack(self):
        assert _classify("new watchtrack file is ready") == "ledger"

    def test_ledger_keyword_extract(self):
        assert _classify("new extract is ready") == "ledger"

    def test_ledger_keyword_jsonl(self):
        assert _classify("drop the jsonl") == "ledger"

    def test_ledger_keyword_fold_in(self):
        assert _classify("fold in the new extract") == "ledger"

    def test_unknown_message_default(self):
        assert _classify("hello") == "default"

    def test_empty_message_default(self):
        assert _classify("") == "default"

    def test_question_default(self):
        assert _classify("what can you do?") == "default"

    def test_slash_eval_prefix_precedence(self):
        # /eval is explicit; slash takes priority even without $
        assert _classify("/eval Tudor 79830RB 2750") == "evaluate_deal"

    def test_leading_whitespace_stripped(self):
        assert _classify("  /ledger  ") == "ledger"


# ─── Capability loading ───────────────────────────────────────────────


class TestCapabilityLoading:
    def test_evaluate_deal_loads_deal_md(self, tmp_path: Path):
        caps = tmp_path / "capabilities"
        caps.mkdir()
        (caps / "deal.md").write_text("deal instructions")
        assert _load_capability("evaluate_deal", str(caps)) == "deal instructions"

    def test_report_loads_report_md(self, tmp_path: Path):
        caps = tmp_path / "capabilities"
        caps.mkdir()
        (caps / "report.md").write_text("report instructions")
        assert _load_capability("report", str(caps)) == "report instructions"

    def test_ledger_loads_ledger_md(self, tmp_path: Path):
        caps = tmp_path / "capabilities"
        caps.mkdir()
        (caps / "ledger.md").write_text("ledger instructions")
        assert _load_capability("ledger", str(caps)) == "ledger instructions"

    def test_default_intent_returns_empty(self, tmp_path: Path):
        caps = tmp_path / "capabilities"
        caps.mkdir()
        assert _load_capability("default", str(caps)) == ""

    def test_missing_file_returns_empty(self, tmp_path: Path):
        caps = tmp_path / "capabilities"
        caps.mkdir()
        # deal.md intentionally absent
        assert _load_capability("evaluate_deal", str(caps)) == ""

    def test_unknown_intent_returns_empty(self, tmp_path: Path):
        caps = tmp_path / "capabilities"
        caps.mkdir()
        assert _load_capability("surprise_intent", str(caps)) == ""


# ─── compute_turn_state integration ──────────────────────────────────


class TestComputeTurnState:
    @pytest.fixture()
    def caps_dir(self, tmp_path: Path) -> str:
        caps = tmp_path / "capabilities"
        caps.mkdir()
        (caps / "deal.md").write_text("## Deal Evaluation\nBuy or pass.")
        (caps / "report.md").write_text("## Report Processing\nRun the pipeline.")
        (caps / "ledger.md").write_text("## Ledger Ingest\nFold it in.")
        return str(caps)

    def test_eval_route_returns_deal_content(self, caps_dir: str):
        result = compute_turn_state("/eval Tudor 79830RB $2,750", capabilities_dir=caps_dir)
        assert result["intent"] == "evaluate_deal"
        assert "Deal Evaluation" in result["capability_prompt"]

    def test_report_route_returns_report_content(self, caps_dir: str):
        result = compute_turn_state("new report is in", capabilities_dir=caps_dir)
        assert result["intent"] == "report"
        assert "Report Processing" in result["capability_prompt"]

    def test_ledger_route_returns_ledger_content(self, caps_dir: str):
        result = compute_turn_state("/ledger", capabilities_dir=caps_dir)
        assert result["intent"] == "ledger"
        assert "Ledger Ingest" in result["capability_prompt"]

    def test_default_route_returns_empty_prompt(self, caps_dir: str):
        result = compute_turn_state("hello", capabilities_dir=caps_dir)
        assert result["intent"] == "default"
        assert result["capability_prompt"] == ""

    def test_free_form_deal_routes_to_evaluate_deal(self, caps_dir: str):
        result = compute_turn_state("Rolex 116610LN $8,500 Black Arabic NR", capabilities_dir=caps_dir)
        assert result["intent"] == "evaluate_deal"

    def test_result_keys_exact(self, caps_dir: str):
        result = compute_turn_state("/eval", capabilities_dir=caps_dir)
        assert set(result.keys()) == {"intent", "capability_prompt"}

    def test_live_capabilities_dir_deal_md_exists(self):
        # Smoke: real capabilities dir on disk serves deal.md
        result = compute_turn_state("/eval")
        assert result["intent"] == "evaluate_deal"
        assert len(result["capability_prompt"]) > 0

    def test_live_capabilities_dir_ledger_md_exists(self):
        result = compute_turn_state("/ledger")
        assert result["intent"] == "ledger"
        assert len(result["capability_prompt"]) > 0

    def test_live_capabilities_dir_report_md_exists(self):
        result = compute_turn_state("/report")
        assert result["intent"] == "report"
        assert len(result["capability_prompt"]) > 0


# ─── Main entry point (subprocess) ───────────────────────────────────


class TestMain:
    _SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "turn_state.py")
    _PYTHON = "python3.12"

    def _run(self, payload: dict) -> dict:
        proc = subprocess.run(
            [self._PYTHON, self._SCRIPT],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )
        return json.loads(proc.stdout)

    def test_slash_eval_returns_ok(self):
        result = self._run({"user_message": "/eval Tudor 79830RB $2,750"})
        assert result["ok"] is True
        assert result["data"]["intent"] == "evaluate_deal"

    def test_slash_ledger_returns_ok(self):
        result = self._run({"user_message": "/ledger"})
        assert result["ok"] is True
        assert result["data"]["intent"] == "ledger"

    def test_slash_report_returns_ok(self):
        result = self._run({"user_message": "/report"})
        assert result["ok"] is True
        assert result["data"]["intent"] == "report"

    def test_data_has_capability_prompt_key(self):
        result = self._run({"user_message": "/eval"})
        assert "capability_prompt" in result["data"]

    def test_default_intent_returns_ok_empty_prompt(self):
        result = self._run({"user_message": "hello"})
        assert result["ok"] is True
        assert result["data"]["intent"] == "default"
        assert result["data"]["capability_prompt"] == ""

    def test_missing_user_message_returns_error(self):
        result = self._run({})
        assert result["ok"] is False
        assert "user_message" in result["error"]

    def test_invalid_json_returns_error(self):
        proc = subprocess.run(
            [self._PYTHON, self._SCRIPT],
            input="not json",
            capture_output=True,
            text=True,
        )
        result = json.loads(proc.stdout)
        assert result["ok"] is False

    def test_non_string_user_message_returns_error(self):
        result = self._run({"user_message": 42})
        assert result["ok"] is False
