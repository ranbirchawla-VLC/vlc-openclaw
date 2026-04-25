# vlc-openclaw — repo-level test runner
#
# Named targets only. No variables, no wildcards.
# Each target is a fixed string so it can be allowlisted in .claude/settings.json.
#
# Pattern for adding a new skill:
#   1. Place lib and tests under skills/<skill-name>/lib/ and skills/<skill-name>/tests/
#   2. Add a block below following the nutriOS pattern exactly:
#        test-<skill-name>:
#        	$(PYTEST) skills/<skill-name>/tests
#        test-<skill-name>-<module>:
#        	$(PYTEST) skills/<skill-name>/tests/test_<module>.py
#   3. Add each new target name to the .PHONY line and to the help echo list.
#
# IMPORTANT: recipe lines must start with a literal tab character, not spaces.
# Verify with: cat -A Makefile | grep -E "^\^I"

PYTEST = python3.12 -m pytest

.PHONY: help test test-nutrios test-nutrios-time test-nutrios-store test-nutrios-engine test-nutrios-models

help:
	@echo "Available targets:"
	@echo "  make test                   - run full test suite (all skills)"
	@echo "  make test-nutrios           - run all NutriOS tests"
	@echo "  make test-nutrios-time      - run nutrios_time tests"
	@echo "  make test-nutrios-store     - run nutrios_store tests"
	@echo "  make test-nutrios-engine    - run nutrios_engine tests"
	@echo "  make test-nutrios-models    - run nutrios_models tests"

test:
	$(PYTEST) skills/nutrios/tests

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
