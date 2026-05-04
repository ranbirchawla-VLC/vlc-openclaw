# GTD Workspace — Known Issues

Non-blocking carry-forwards from sub-step gates. Each entry lists priority and the target sub-step for resolution.

| ID | Description | Priority | Target |
|----|-------------|----------|--------|
| KI-001 | `_SCOPES` in calendar scripts includes both `calendar` and `calendar.events`; the latter is a subset of the former. Drop `calendar.events`. | P3 | next opportunity |
| KI-002 | `test_get_events.py` Case 5 has `main.__wrapped__ = None` as dead code with no effect. Remove. | P3 | next opportunity |
| KI-003 | `toToolResult` duplicated between `gtd-tools` and `nutriosv2-tools`. Extract to shared plugin-utils package before the third plugin lands (Sub-step 5 Gmail send). Decide pattern at Sub-step 5 prep. | P2 | before Sub-step 5 |
| KI-004 | `get_events.py`: `_now_iso()` / `_seven_days_iso()` called before span opens; span attributes set after. Move time computation inside span. | P3 | next opportunity |
| KI-005 | `calendar/conftest.py` `sys.path.insert` for the calendar directory is redundant; pytest auto-adds test dir. Remove. | P3 | next opportunity |
| KI-006 | `get_events.py` `_map_event`: no comment noting `htmlLink` to `html_link` camelCase-to-snake_case conversion. Add comment. | P3 | next opportunity |
| KI-007 | Flat 1-second retry sleep on Google API 5xx; Google recommends truncated exponential backoff. Fine for dev; required before sustained production calendar traffic. | P2 | before production traffic on calendar tools |
| KI-008 | `_CONTEXT_ENV` dict duplicated in both calendar scripts. Extract to `otel_common.py` when a third script needs it. | P3 | when third plugin tool lands |
| KI-009 | Plugin registration in root `openclaw.json` is an operator-side manual step. Standing risk across all agents; codify in deploy runbook. | P3 | runbook pass |
