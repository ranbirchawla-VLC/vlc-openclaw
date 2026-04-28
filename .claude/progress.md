# progress.md — Grailzee Eval v2 / Rational Sequence

**Working root**: `/Users/ranbirchawla/ai-code/vlc-openclaw` (not `.openclaw/workspace`)
**Branch**: `feature/grailzee-eval-v2`
**Remote**: in sync at `d5c9c34` (pushed 2026-04-28; 1c + 1c.5 + tests-commit)
**Canonical state doc**: `GRAILZEE_SYSTEM_STATE.md` at repo root. Read that first.

Session-open protocol: read `GRAILZEE_SYSTEM_STATE.md`, then this file.

---

## Status at a glance

| Item | State |
|---|---|
| Schema version | v3 (cache `schema_version: 3` since 2b) |
| Tests | `make test-grailzee-eval`: 1030 passed, 71 skipped, 0 failed |
| Cowork suite | `make test-grailzee-cowork`: 235 passed, 0 failed |
| Step 0 (schema lock) | DONE; `bfc68cd` pushed |
| Step 1 (`evaluate_deal.py` + bot wiring) | DONE; `c8b8494` pushed |
| Step 1 patch (margin-floor rounding) | DONE; `2ec21e5` pushed |
| Step 1.3 (human-facing label fields + deal.md) | DONE; `4d65a4e` pushed |
| Step 2 (producer chain + bundle validation) | DONE; `2113935` pushed |
| Chore (clean baseline before Shape G) | DONE; `374ee54` pushed |
| Shape G commit 1 (override math layer) | DONE; `607f793` pushed |
| Doc: Branch A guardrails + lock #2 clause | DONE; `b21a0c4` pushed |
| Shape K 1a (GRAILZEE_ROOT env-var) | DONE; `a790f5d` + `1e38de7` pushed |
| Shape K 1b (agent surface lockdown) | DONE; `8c9cc8f` + `2ce167f` pushed |
| env object revert (gateway blowup fix) | DONE; `~/.openclaw/openclaw.json` edited directly, not committed |
| Laptop rebase onto origin/main | BLOCKED — terminal restart needed (see note below) |
| Shape K 1b.5 (stdin dispatch: report_pipeline + ledger_manager) | NEXT UP — scope expanded from report_pipeline-only |
| Shape K 1c (plugin scaffold + register evaluate_deal) | DONE; `8e83b25` local (not pushed) |
| Shape K 1c.5 (spec-drift fixup: JSON _run_from_argv, spawnArgv, error envelope) | DONE; local (not pushed) |
| Shape K 1d (report_pipeline plugin registration) | NOT STARTED |
| Shape K 1e (update_name_cache plugin registration) | NOT STARTED |
| Shape K 1f (AGENTS.md final pass + SKILL.md hard rules) | NOT STARTED |
| Shape K commit 2 (override wiring + deal.md branch) | NOT STARTED |
| Step 3 (strategy skill update) | NOT STARTED |
| INBOUND apply (cycle_2026-08) | DONE; `state/cycle_focus.json` written |
| State doc Section 4 | Pending operator draft; entries: ae253aa, 2a852cb, c7f90d5, bfc68cd, c8b8494, 2ec21e5, 4d65a4e, 2113935, 374ee54, 607f793, b21a0c4, a790f5d, 1e38de7, 8c9cc8f, 2ce167f |
| §5.5 spot-check | Rides next live Grailzee cycle |
| 2a ingest_and_archive live rehearsal | Open; closes with §5.5 |
| Operator gate (gateway restart + Telegram test) | BLOCKED on 1b.5 + GRAILZEE_ROOT injection resolution |

---

## Rational sequence (current)

**Step 0** — Lock schemas — **DONE** (`bfc68cd`)
**Step 1** — Wire bot end-to-end against mock — **DONE** (`c8b8494` + `2ec21e5` + `4d65a4e`)
**Step 2** — Wire producer chain forward — **DONE** (`2113935`)
**Shape G commit 1** — Override math layer — **DONE** (`607f793`)
**Doc commit** — Branch A guardrails + lock #2 clause — **DONE** (`b21a0c4`)
**Shape K 1a** — GRAILZEE_ROOT env-var refactor — **DONE** (`a790f5d` + `1e38de7`)
**Shape K 1b** — Agent surface lockdown — **DONE** (`8c9cc8f` + `2ce167f`)
**Shape K 1b.5** — stdin dispatch for report_pipeline + ledger_manager — **NEXT UP**
**Shape K 1c** — plugin scaffold + register evaluate_deal — **DONE** (`8e83b25`)
**Shape K 1c.5** — spec-drift fixup on 1c — **DONE** (local)
**Shape K 1d** — report_pipeline plugin registration — after 1b.5
**Shape K 1e** — update_name_cache plugin registration — after 1d
**Shape K 1f** — AGENTS.md final pass + SKILL.md hard rules — after 1e
**Shape K commit 2** — Wire override into `evaluate()` + deal.md branch
**Step 3** — Wire strategy session — Sonnet
**Step 4** — Sale folder json ingest — design outstanding
**Step 5** — Verify report pipeline — verification only

Architecture lock: three surfaces (Telegram bot, cowork, chat strategy skill). Wide CSV is strategy input. Yes/no only on deal eval. Premium scalar uniform. No inter-cycle tracking in this stack.

---

## Laptop rebase — blocked (2026-04-28)

**Branch**: `feature/grailzee-eval-v2` at `d5c9c34`, clean working tree, in sync with origin.

**origin/main advances**: 8 commits (NutriOS v3 merge + support commits). Rebase is needed.

**Blocker 1 (resolved)**: `pydantic` not installed on laptop. Added by 1c.5 to `requirements.txt` but never installed here. Fixed: `pip install pydantic==2.13.3`.

**Blocker 2 (pending)**: 37 test failures in `test-grailzee-eval` — all `PermissionError: [Errno 1] Operation not permitted` on Google Drive Shared Drive paths (`GrailzeeData/state/`). Affected test files: `test_monthly_goals_starter.py` (11), `test_quarterly_allocation_starter.py` (11), `test_roll_cycle.py` (14), `test_grailzee_common.py` (1). Root cause: terminal process lacks Full Disk Access on this laptop. Fix: grant Full Disk Access to terminal in System Settings → Privacy & Security → Full Disk Access, then **restart terminal**. Pre-rebase baseline on desktop was 1030/71/0.

**Resume sequence after terminal restart**:
1. Confirm `python3.12 -m pytest skills/grailzee-eval/tests` green (expect ~1030 passed, 71 skipped, 0 failed)
2. Run `make test-grailzee-cowork` (expect 235 passed)
3. `git rebase origin/main` (expected conflict-free — NutriOS paths are parallel)
4. Re-run both test targets; confirm counts match pre-rebase
5. `git push --force-with-lease`

---

## Shape K 1c.5 — spec-drift fixup (2026-04-28)

**Cause:** 1c surfaced that `_run_from_argv` in evaluate_deal.py is argparse-based; spec §1.5 assumed it was JSON-aware. 1c used spawnStdin as a workaround. 1c.5 fixes the root.

**Scope:**
- `evaluate_deal.py`: added `_Input(BaseModel, extra='forbid')`, rewired `_run_from_dict` to use Pydantic validation with correct error codes (all exit 0), added JSON-aware `_run_from_argv`, renamed old argparse path to `_run_legacy`. Detection: `sys.argv[1].startswith("{")` → JSON path; `len(sys.argv)==1` → stdin; else → argparse. Used `{` prefix (unambiguous for JSON object) instead of `not startswith("-")` (breaks on positional args).
- `index.js`: evaluate_deal switched from `spawnStdin` to `spawnArgv`.
- `requirements.txt`: `pydantic>=2.0.0` added.
- `Grailzee_Plugin_API_Spec_v1.md`: dated addendum at end of file correcting §1.5/§1.6.
- Tests: contract tests updated with strict exit-0 assertions and full error envelope checks; `test_argv_error_bad_input` uses `{not valid json` (starts with `{`, goes to JSON path); unknown-field rejection test added; no_match test added; `candidate_bucket_labels` length assertion added; argv dispatch test class added.

**Gates closed from 1c subagent:** M2 (error envelope inconsistency), m4 (exit code), m1 (candidate_bucket_labels), m2 (no_match coverage).

**Baseline:** 1021 → 1030 / 71 / 0.

---

## Session 2026-04-28: env object revert (gateway blowup)

### Problem

Commit 1b added `"env": {"GRAILZEE_ROOT": "..."}` as an object under the `grailzee-eval` entry in `~/.openclaw/openclaw.json`. This is a non-working pattern — gateway rejected it on restart.

### Fix

Removed the `env` object block from the grailzee-eval agent entry in `~/.openclaw/openclaw.json` directly. `tools.allow` block is intact and unchanged. The file is outside the repo; no commit needed.

**Current grailzee-eval entry shape** (post-revert):
```json
{
  "id": "grailzee-eval",
  "name": "grailzee-eval",
  "workspace": "/Users/ranbirchawla/ai-code/vlc-openclaw/skills/grailzee-eval",
  "agentDir": "/Users/ranbirchawla/.openclaw/agents/grailzee-eval/agent",
  "model": "claude-sonnet-4-6",
  "tools": {
    "allow": ["evaluate_deal", "report_pipeline", "ledger_manager", "message"]
  }
}
```

### Open question: GRAILZEE_ROOT injection

With the `env` object removed, `GRAILZEE_ROOT` is not being injected into tool processes at gateway launch. `grailzee_common.py` has an env var fallback to the hardcoded Drive path (`os.getenv("GRAILZEE_ROOT", "<hardcoded>")`), so tools will function — they fall back to the default. But the env-var override path from 1a is not active.

**What the workspace `openclaw.json` declares**: `"env": ["GRAILZEE_ROOT"]` — an array of var names, which is the informational declaration format per AGENT_ARCHITECTURE.md. This does not inject the value; it just tells OpenClaw what the tool expects.

**Resolution needed before operator gate**: Determine the correct syntax for injecting env var values via root openclaw.json (if the gateway supports it at all), or confirm that shell-level export is the expected injection mechanism. Until resolved, the fallback path in grailzee_common.py covers live operation.

---

## Session 2026-04-28: Capability contract review (read-only)

Full read-only analysis of all three registered tools against openclaw.json dispatch shape, capability files, and Architecture Lock.

### evaluate_deal — Honored

**Dispatch**: Works correctly. Script has dual entry: `len(sys.argv) > 1` → argparse (tests/CLI); no args → `json.loads(sys.stdin.read())` (OpenClaw). JSON piped by OpenClaw maps correctly to `_run_from_dict`. All errors routed to stdout as shaped JSON; no stack trace leaks.

**deal.md fit**: Well-matched with two documented gaps, both expected (not-yet-shipped):
- `headroom_pct` field in `math` dict undocumented (always `None` in single_bucket path today; will carry a value when override_match ships in commit 2)
- `override_match` branch absent from deal.md and from the `match_resolution` enum in the documented output shape

**Contract quality**: Strong. Label fields (`match_resolution_label`, `plan_status_label`, `bucket_label`, `candidate_bucket_labels`) are all display-ready verbatim strings. Verbatim-render rule is fully implemented. Errors are operator-visible. Idempotent.

### ledger_manager — Mechanically broken

**Dispatch**: Broken. Script is argparse-only, no stdin dispatch. OpenClaw pipes JSON to stdin; `parser.parse_args()` gets empty `sys.argv[1:]`; `args.command is None`; exits 2 with help text to stdout. The `subcommand` key in the inputSchema never reaches the script.

**Capability file**: None exists. `ls capabilities/` shows only `deal.md` and `report.md`. The Architecture Lock explicitly cut `ledger.md` from the operator surface (trade logging flows via sale folder json drops, not Telegram). However, `ledger_manager` is registered in openclaw.json and in `tools.allow`, and the query subcommands (`summary`, `premium`, `cycle_rollup`) are not explicitly cut.

**Supervisor question**: Is `ledger_manager` on the Telegram tool surface intentionally (for future use) or accidentally? Without a capability file, the LLM has no routing instructions for it. The `log` subcommand should not be reachable from Telegram per the architecture lock, but all four subcommands are available to the argparse entry point.

**Output shape**: Errors go to `file=sys.stderr` in `cmd_log` and others — inconsistent with `evaluate_deal.py` pattern (which routes all errors to stdout as shaped JSON). If OpenClaw only surfaces stdout to the LLM, error messages are invisible.

**Fix scope for 1b.5**: Stdin dispatch wrapper at `__main__` mapping `subcommand` key → argv tokens, plus required-arg validation per subcommand. Estimate ~40 lines. Supervisor must also decide: add a capability file, or remove `ledger_manager` from `tools.allow` until Phase D.

### report_pipeline — Mechanically broken

**Dispatch**: Broken. Same pattern as ledger_manager: argparse-only, no stdin dispatch. argparse errors on missing positional `input_report` (required). JSON piped by OpenClaw is never read.

**Fix scope for 1b.5**: Stdin dispatch wrapper at `__main__` mapping `input_report` → positional argv and `output_folder` → `--output-folder` flag, then delegating to `main()`. Estimate ~20 lines. Internal override flags (`--csv-dir`, `--ledger`, etc.) are not in the inputSchema and need not be exposed.

**report.md fit**: Two structural contradictions with the post-1b surface:

1. **Step 2 "find newest workbook"**: Instructs the LLM to run `ls -t reports/*.xlsx | head -1` when the operator doesn't supply a path. `exec` is removed from `tools.allow`. This path is dead. `input_report` is required in the inputSchema — the LLM must always have a path. If the operator doesn't supply one, there's no mechanism to discover it. Fix: either make the script scan for the newest xlsx internally when `input_report` is omitted, or update report.md to require the operator to always name the file.

2. **Step 5 name-cache append**: Instructs the LLM to call `python3 -c "from scripts.grailzee_common import append_name_cache_entry; ..."`. This requires `exec`. Dead. Fix options: (a) register `append_name_cache` as a fifth tool, or (b) have `report_pipeline` perform name-cache resolution internally and return resolved names in the output dict, removing the LLM from that loop entirely. Option (b) is cleaner and aligns with Decision #2 (Python deterministic).

**Error output**: `report_pipeline.py` routes errors to `file=sys.stderr` (line 162). On failure, stdout is empty. The LLM sees nothing and has no error to surface. Fix alongside the stdin dispatch wrapper.

---

## Session 2026-04-28: Dispatch verification (partial read-only, interrupted)

Pre-session on 2026-04-28, a dispatch-verification read (per-tool Q1-Q6 on script entry points) was started but interrupted by the user before the report was delivered. The capability contract review above supersedes and covers the same ground more completely. Key finding from that read:

**Reference agent (nutriosv2 `compute_candidate_macros.py`) deviates from AGENT_ARCHITECTURE.md canonical pattern.** The canonical template specifies `json.loads(sys.stdin.read())`. nutriosv2 scripts use `sys.argv[1]` as a JSON string argument. The two patterns are incompatible — OpenClaw cannot use both simultaneously. Which pattern OpenClaw actually uses needs to be confirmed at the gateway level before 1b.5 is implemented. `evaluate_deal.py`'s stdin dispatch is the assumed-correct pattern given the openclaw.json command entries have no `args` field and no positional args after the script path. Verify against a working nutriosv2 session log or OpenClaw gateway source before building 1b.5.

---

## Shape K 1b.5 — Scope (expanded)

**Original scope**: report_pipeline stdin dispatch only.

**Expanded scope after capability review**:
1. `report_pipeline.py`: stdin dispatch wrapper + error routing to stdout
2. `ledger_manager.py`: stdin dispatch wrapper + error routing to stdout
3. `report.md`: fix Steps 2 and 5 (dead exec paths) — supervisor decides fix direction for each
4. Confirm `ledger_manager` surface decision (capability file or remove from tools.allow)
5. Confirm GRAILZEE_ROOT injection mechanism before operator gate

**Prerequisite**: Confirm which invocation pattern OpenClaw actually uses (stdin JSON vs. sys.argv[1] JSON string). See dispatch verification note above.

**Blocks**: operator gate (gateway restart + Telegram test).

---

## Shape K 1b outstanding items (carried forward)

**1c — SKILL.md + capability prompt hardening**: Add `## Hard Rules` block at top of SKILL.md before dispatch. Add "call the registered tool; do not call via exec" framing to deal.md and report.md. No code change; doc-only commit. Depends on report.md fixes landing in 1b.5 first.

**query_targets registration** deferred to Phase D. Script at old workspace path reads deprecated `sourcing_brief.json`. Not in scope until Phase D rebuild.

**Operator gate** (after 1b.5 + 1c + GRAILZEE_ROOT resolved + gateway restart):
- `openclaw gateway restart` then `openclaw tui`
- Decision on `~/.openclaw/agents/grailzee/agent/` (two small files: auth-profiles.json 37B, models.json 696B — safe to accept fresh start)
- Send one test deal through Telegram; confirm normal response
- `audit_session.py --latest grailzee-eval`: expect 0 forbidden, 0 exec bypasses

---

## Shape K commit 2 carry-forwards (from Shape G commit 1)

- Wire `_override_math` into `evaluate()`: new branch when `_match_buckets()` returns `no_match`, `cycle_context["on_plan"]` is True, and `target_match["max_buy_override"]` is not None
- Override path does not floor-round `max_buy` (operator committed to precise price)
- New `deal.md` Branch C for `override_match` resolution (inherits Branch A guardrails)
- OTEL span coverage for `_override_math` and `_decision_math` (both currently unspanned)
- Update deal.md math shape to include `headroom_pct`; update `match_resolution` enum to include `override_match`

---

## Session 2026-04-27: Shape K hardening (1a + 1b)

### Forensic audit baseline

Ran `audit_session.py --latest grailzee` against most recent session JSONL. Result: **13/13 tool calls forbidden, 9 exec->python bypasses, 0 registered.** Agent read SKILL.md and deal.md via `read`, then called `evaluate_deal.py` directly via `exec` for every deal eval. Forensic audit confirmed working on agent id `grailzee` (not `grailzee-eval`).

### Shape K 1a — `a790f5d` + `1e38de7`

`grailzee_common.py` lines 28-32: `GRAILZEE_ROOT` hardcoded literal replaced with `os.getenv("GRAILZEE_ROOT", "<same default>")`. `os` was already imported. Three new tests in `test_grailzee_root_env.py`: default fall-through, override, derived-path inheritance. `_restore_module` fixture has `try/finally` guard (review fix). Smoke test confirmed: schema_version 3 / cycle_2026-08 / 3,878 refs, Drive accessible with env var unset. Baseline: 982 → 985 passed.

### Shape K 1b — `8c9cc8f` + `2ce167f`

**`skills/grailzee-eval/openclaw.json`** rewritten: 4 tools (evaluate_deal, report_pipeline, ledger_manager, message). Env updated from `["GRAILZEE_DATA_ROOT", "GRAILZEE_TZ"]` to `["GRAILZEE_ROOT"]`.

**`~/.openclaw/openclaw.json`** (outside repo): `grailzee` → `grailzee-eval` rename (id, name, agentDir). `tools.allow` added with 4 tools. `env.GRAILZEE_ROOT` declared as object (pattern later found non-working; reverted 2026-04-28). Binding `agentId` updated; `accountId: "grailzee"` unchanged (ties to bot token).

**`AGENTS.md`** replaced wholesale: grailzee-specific content per AGENT_ARCHITECTURE.md template. Identity, Tools Available (4 tools), Hard Rules (exec/read/write/edit/browser/canvas prohibited, never calculate, NO_REPLY rule, no codebase exploration).

**3 new tests** in `test_agent_surface.py`: workspace openclaw.json shape, root config entry shape, AGENTS.md section presence. Baseline: 985 → 988 passed.

Note: `test_agent_surface.py` tests the root config shape as it was in commit 1b (with the env object). After the 2026-04-28 revert, the root config no longer matches what those tests assert. Tests will need updating in 1b.5.

---

## Session 2026-04-27: Doc commit — Branch A guardrails + lock #2 clause (`b21a0c4`)

Doc-only; no code, no tests.

**`skills/grailzee-eval/capabilities/deal.md`** — `### Composition guardrails` section inserted inside Branch A, after the example shape template. Three hard constraints: numbers verbatim, framing decision-helping not decision-making, length-bounded (1 paragraph, 3-5 sentences). Branch C inherits all three.

**`docs/decisions/Grailzee_Architecture_Lock_2026-04-26.md`** — added to repo for the first time (was project-knowledge-only at Downloads path). Clarifying clause appended under decision #2: LLM may compose Branch A prose around verbatim math; Branch A guardrails are the sole sanctioned slot; all other surfaces remain pure verbatim.

---

## Session 2026-04-27: Shape G commit 1 (`607f793`)

**`_override_math(override_price, listing_price) -> dict`** — pure function, no I/O.
- `max_buy = override_price`; `headroom_pct = ((override_price - listing_price) / override_price) * 100`
- `premium_scalar`, `adjusted_price`, `margin_pct` all `None`; guard: `ValueError` if `override_price <= 0`

**`headroom_pct: None`** added to `_decision_math()` return dict (shape parity).

**`"override_match"`** added to `_MATCH_RESOLUTION_LABELS` — emitted in Shape K commit 2.

**12 new tests**: `TestOverrideMath` (10), `TestOverrideMatchResolution` (1), `TestBucketMathHeadroomRegression` (1). Count: 970 → 982 passed.

---

## Pointers

- State truth: `GRAILZEE_SYSTEM_STATE.md` (repo root)
- Decision locks: `docs/decisions/`
- Architecture lock: `docs/decisions/Grailzee_Architecture_Lock_2026-04-26.md` (in repo since `b21a0c4`)
- Rational sequence: `Downloads/GZ-4-25/GZ-4-26/files/Grailzee_Implementation_Sequence_2026-04-26.md`
- Strategy skill: `grailzee-strategy/` (repo root)
- Cowork plugin: `grailzee-cowork/` (repo root)
- Per-agent OpenClaw config: `skills/grailzee-eval/openclaw.json`
- Root OpenClaw config: `~/.openclaw/openclaw.json` (outside repo; env object removed 2026-04-28)
- Step 1 mock fixture: `grailzee-cowork/tests/fixtures/mock_strategy_output.json`
- INBOUND apply bundle path: `GrailzeeData/bundles/` (NOT `output/`)
- Full prior build log: `.claude/progress-v0.md`
