# vlc-openclaw; repo-level test runner
#
# Named targets only. No variables, no wildcards.
# Each target is a fixed string so it can be allowlisted in .claude/settings.json.
#
# `make test` runs bare $(PYTEST), which discovers all skills via pytest.ini
# testpaths = skills. When a new skill is added, its tests are automatically
# included in `make test` once placed under skills/<name>/tests/.
#
# Pattern for adding a new skill:
#   1. Place lib and tests under skills/<skill-name>/lib/ and skills/<skill-name>/tests/
#   2. Add a block below following the nutriOS pattern exactly:
#        test-<skill-name>:
#        	$(PYTEST) skills/<skill-name>/tests
#        test-<skill-name>-<module>:
#        	$(PYTEST) skills/<skill-name>/tests/test_<module>.py
#   3. Add each new target name to the .PHONY line and to the help echo list.
#   4. Allowlist the new Bash(make test-<skill-name>*) patterns in .claude/settings.json.

PYTHON = .venv/bin/python
PYTEST = python3.12 -m pytest

.PHONY: help setup test test-fast test-llm lint test-nutrios test-nutrios-time test-nutrios-store test-nutrios-engine test-nutrios-models test-nutrios-context test-nutriosv2 test-nutriosv2-foundation test-nutriosv2-models test-nutriosv2-mesocycle test-nutriosv2-intent test-nutriosv2-turn-state test-nutriosv2-llm test-nutriosv2-llm-3x test-grailzee-eval test-grailzee-eval-build-shortlist test-grailzee-eval-run-analysis test-grailzee-eval-evaluate-deal test-grailzee-eval-report-pipeline test-grailzee-eval-ingest-sales-plugin test-grailzee-cowork test-grailzee-ledger test-grailzee-ledger-schema test-grailzee-ledger-transform test-grailzee-ledger-lock test-grailzee-ledger-merge test-grailzee-ledger-prune test-grailzee-ledger-archive test-grailzee-ledger-read test-grailzee-ledger-orchestrator test-grailzee-ledger-integration

help:
	@echo "Available targets:"
	@echo "  make setup                       - create .venv and install workspace dev deps (idempotent)"
	@echo "  make test                        - full suite (Python + LLM)"
	@echo "  make test-fast                   - Python tests only (skip LLM)"
	@echo "  make test-llm                    - LLM integration tests only"
	@echo "  make lint                        - no-op (ruff not configured yet)"
	@echo "  make test-grailzee-eval            - run all grailzee-eval tests"
	@echo "  make test-grailzee-eval-build-shortlist - run build_shortlist tests"
	@echo "  make test-grailzee-eval-run-analysis    - run run_analysis tests"
	@echo "  make test-grailzee-eval-evaluate-deal   - run evaluate_deal tests"
	@echo "  make test-grailzee-cowork          - run all grailzee-cowork tests"
	@echo "  make test-grailzee-ledger          - run all grailzee ledger redo tests"
	@echo "  make test-grailzee-ledger-schema   - run sub-step 1.1 schema tests only"
	@echo "  make test-grailzee-ledger-transform - run sub-step 1.2 transform tests only"
	@echo "  make test-grailzee-ledger-lock      - run sub-step 1.3 lock/atomic write tests only"
	@echo "  make test-grailzee-ledger-merge     - run sub-step 1.4 merge/Rule Y tests only"
	@echo "  make test-grailzee-ledger-prune     - run sub-step 1.5 prune tests only"
	@echo "  make test-grailzee-ledger-archive   - run sub-step 1.6 archive move tests only"
	@echo "  make test-grailzee-ledger-read      - run sub-step 1.7 read_ledger_csv tests only"
	@echo "  make test-grailzee-ledger-orchestrator - run sub-step 1.7 orchestrator tests only"
	@echo "  make test-grailzee-ledger-integration  - run sub-step 1.7 integration tests only"
	@echo "  make test-nutrios                - run all NutriOS v1 tests"
	@echo "  make test-nutrios-time           - run nutrios_time tests"
	@echo "  make test-nutrios-store          - run nutrios_store tests"
	@echo "  make test-nutrios-engine         - run nutrios_engine tests"
	@echo "  make test-nutrios-models         - run nutrios_models tests"
	@echo "  make test-nutrios-context        - run nutrios_context tests"
	@echo "  make test-nutriosv2              - run all NutriOS v3 tests (Python + LLM)"
	@echo "  make test-nutriosv2-foundation   - run sub-step 0 common.py tests"
	@echo "  make test-nutriosv2-models       - run Pydantic model tests"
	@echo "  make test-nutriosv2-mesocycle    - run mesocycle tool tests"
	@echo "  make test-nutriosv2-intent       - run intent classifier tests"
	@echo "  make test-nutriosv2-turn-state   - run turn_state tool tests"
	@echo "  make test-nutriosv2-llm          - run NutriOS v3 LLM tests (single run)"
	@echo "  make test-nutriosv2-llm-3x       - run NutriOS v3 LLM tests 3x require-all-pass"

setup:
	test -d .venv || python3.11 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e "./skills/nutriosv2[dev]"

test:
	$(PYTEST)

test-fast:
	$(PYTEST) -m "not llm"

test-llm:
	$(PYTEST) -m "llm"

lint:
	@echo "lint: no linter configured (ruff not installed)"

test-grailzee-eval:
	$(PYTEST) skills/grailzee-eval/tests

test-grailzee-eval-build-shortlist:
	$(PYTEST) skills/grailzee-eval/tests/test_build_shortlist.py

test-grailzee-eval-run-analysis:
	$(PYTEST) skills/grailzee-eval/tests/test_run_analysis.py

test-grailzee-eval-evaluate-deal:
	$(PYTEST) skills/grailzee-eval/tests/test_evaluate_deal.py

test-grailzee-eval-report-pipeline:
	$(PYTEST) skills/grailzee-eval/tests/test_report_pipeline.py

test-grailzee-eval-ingest-sales-plugin:
	$(PYTEST) skills/grailzee-eval/tests/test_ingest_sales_plugin.py

test-grailzee-cowork:
	$(PYTEST) grailzee-cowork/tests

test-grailzee-ledger:
	$(PYTEST) skills/grailzee-eval/tests/test_ingest_sales_schema.py skills/grailzee-eval/tests/test_ingest_sales_transform.py skills/grailzee-eval/tests/test_ingest_sales_lock.py skills/grailzee-eval/tests/test_ingest_sales_merge.py skills/grailzee-eval/tests/test_ingest_sales_prune.py skills/grailzee-eval/tests/test_ingest_sales_archive.py skills/grailzee-eval/tests/test_ingest_sales_read.py skills/grailzee-eval/tests/test_ingest_sales_orchestrator.py skills/grailzee-eval/tests/test_ingest_sales_integration.py

test-grailzee-ledger-schema:
	$(PYTEST) skills/grailzee-eval/tests/test_ingest_sales_schema.py

test-grailzee-ledger-transform:
	$(PYTEST) skills/grailzee-eval/tests/test_ingest_sales_transform.py

test-grailzee-ledger-lock:
	$(PYTEST) skills/grailzee-eval/tests/test_ingest_sales_lock.py

test-grailzee-ledger-merge:
	$(PYTEST) skills/grailzee-eval/tests/test_ingest_sales_merge.py

test-grailzee-ledger-prune:
	$(PYTEST) skills/grailzee-eval/tests/test_ingest_sales_prune.py

test-grailzee-ledger-archive:
	$(PYTEST) skills/grailzee-eval/tests/test_ingest_sales_archive.py

test-grailzee-ledger-read:
	$(PYTEST) skills/grailzee-eval/tests/test_ingest_sales_read.py

test-grailzee-ledger-orchestrator:
	$(PYTEST) skills/grailzee-eval/tests/test_ingest_sales_orchestrator.py

test-grailzee-ledger-integration:
	$(PYTEST) skills/grailzee-eval/tests/test_ingest_sales_integration.py

test-nutrios:
	$(PYTEST) skills/nutrios/tests

test-nutrios-time:
	$(PYTEST) skills/nutrios/tests/test_nutrios_time.py

test-nutrios-store:
	$(PYTEST) skills/nutrios/tests/test_nutrios_store.py

test-nutrios-engine:
	$(PYTEST) skills/nutrios/tests/test_nutrios_engine.py

test-nutrios-models:
	$(PYTEST) skills/nutrios/tests/test_nutrios_models.py

test-nutrios-context:
	$(PYTEST) skills/nutrios/tests/test_nutrios_context.py

test-nutriosv2:
	$(PYTEST) skills/nutriosv2/scripts/tests -m "not llm"
	$(PYTHON) skills/nutriosv2/scripts/run_llm_3x.py

test-nutriosv2-foundation:
	$(PYTEST) skills/nutriosv2/scripts/tests/test_common.py

test-nutriosv2-models:
	$(PYTEST) skills/nutriosv2/scripts/tests/test_models.py

test-nutriosv2-mesocycle:
	$(PYTEST) skills/nutriosv2/scripts/tests/test_mesocycle.py

test-nutriosv2-intent:
	$(PYTEST) skills/nutriosv2/scripts/tests/test_intent_classifier.py

test-nutriosv2-turn-state:
	$(PYTEST) skills/nutriosv2/scripts/tests/test_turn_state.py

test-nutriosv2-llm:
	$(PYTEST) skills/nutriosv2/scripts/tests/llm

test-nutriosv2-llm-3x:
	$(PYTHON) skills/nutriosv2/scripts/run_llm_3x.py
