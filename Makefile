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
PYTEST = $(PYTHON) -m pytest

.PHONY: help setup test test-fast test-llm lint test-nutrios test-nutrios-time test-nutrios-store test-nutrios-engine test-nutrios-models test-nutrios-context test-nutriosv2 test-nutriosv2-foundation test-nutriosv2-models test-nutriosv2-mesocycle test-nutriosv2-intent test-nutriosv2-turn-state test-nutriosv2-llm test-nutriosv2-llm-3x test-gtd test-gtd-storage test-gtd-helpers test-gtd-common test-gtd-otel test-gtd-calendar test-gtd-internal

help:
	@echo "Available targets:"
	@echo "  make setup                       - create .venv and install workspace dev deps (idempotent)"
	@echo "  make test                        - full suite (Python + LLM)"
	@echo "  make test-fast                   - Python tests only (skip LLM)"
	@echo "  make test-llm                    - LLM integration tests only"
	@echo "  make lint                        - no-op (ruff not configured yet)"
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
	@echo "  make test-gtd                    - run all GTD workspace tests"
	@echo "  make test-gtd-storage            - run migrate_storage.py tests"
	@echo "  make test-gtd-helpers            - run common.py + otel_common.py tests"
	@echo "  make test-gtd-common             - run scripts/common.py tests only"
	@echo "  make test-gtd-otel               - run otel_common.py tests only"
	@echo "  make test-gtd-calendar           - run calendar tool tests only"
	@echo "  make test-gtd-internal           - run 2b.1 internal modules (normalize, validate, write)"

setup:
	test -d .venv || python3.11 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e "./skills/nutriosv2[dev]"
	$(PYTHON) -m pip install -e "./gtd-workspace[dev]"

test:
	$(PYTEST)

test-fast:
	$(PYTEST) -m "not llm"

test-llm:
	$(PYTEST) -m "llm"

lint:
	@echo "lint: no linter configured (ruff not installed)"

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

test-gtd:
	$(PYTEST) gtd-workspace/scripts

test-gtd-internal:
	$(PYTEST) gtd-workspace/scripts/gtd/tests gtd-workspace/scripts/test_common.py

test-gtd-storage:
	$(PYTEST) gtd-workspace/scripts/test_migrate_storage.py

test-gtd-helpers:
	$(PYTEST) gtd-workspace/scripts/test_common.py gtd-workspace/scripts/test_otel_common.py

test-gtd-common:
	$(PYTEST) gtd-workspace/scripts/test_common.py

test-gtd-otel:
	$(PYTEST) gtd-workspace/scripts/test_otel_common.py

test-gtd-calendar:
	$(PYTEST) gtd-workspace/scripts/calendar
