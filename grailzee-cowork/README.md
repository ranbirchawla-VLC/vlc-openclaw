# vardalux-grailzee-cowork

Claude Code plugin that bridges the Grailzee agent (local auction analysis)
with the Chat strategy workflow. Two modes, one skill (`grailzee-bundle`):

- **OUTBOUND** — packages the current GrailzeeData state (cache, cycle focus,
  goals, quarterly allocation, ledger snippet, brief, latest report CSV)
  into a single validated `.zip` for upload to a Chat strategy session.
- **INBOUND** — validates a strategy-session `.zip` and atomically writes the
  returned planning artifacts (cycle focus, monthly goals, quarterly
  allocation) back into GrailzeeData state.

The plugin is self-contained. It does not import from `skills/grailzee-eval/`
at runtime. Coupling is through the `--grailzee-root` CLI flag.

## Layout

```
grailzee-cowork/
├── .claude-plugin/plugin.json
├── skills/grailzee-bundle/SKILL.md
├── grailzee_bundle/
│   ├── build_bundle.py   # OUTBOUND
│   └── unpack_bundle.py  # INBOUND
└── tests/
    ├── _fixtures.py
    ├── test_build_bundle.py
    ├── test_unpack_bundle.py
    └── test_round_trip.py
```

## CLI

**OUTBOUND**
```
python grailzee_bundle/build_bundle.py --grailzee-root <PATH> [--output-dir DIR]
```
Writes `grailzee_outbound_<cycle>_<YYYYMMDD_HHMMSS_ffffff>.zip` into
`<PATH>/bundles/` (or `DIR` if `--output-dir` is given). Prints the path on
stdout. Exits non-zero with a descriptive stderr message if any required
input is missing or malformed.

**INBOUND**
```
python grailzee_bundle/unpack_bundle.py <BUNDLE.zip> --grailzee-root <PATH>
```
Runs the 8-rule validation sequence. On success, atomically writes
`cycle_focus.json` / `monthly_goals.json` / `quarterly_allocation.json`
into `<PATH>/state/` and prints a JSON summary on stdout. On failure,
exits non-zero with the specific rule name in the stderr message; no
state files are touched.

`--allow-cycle-mismatch` relaxes rule 4 (cycle_id alignment) for the edge
case where the agent has not yet rolled to the inbound bundle's cycle.

## Bundle format

Manifest schema `v1`. All members have sha256 + size_bytes recorded in the
manifest. OUTBOUND bundles carry seven roles; INBOUND bundles carry up to
three (`cycle_focus`, `monthly_goals`, `quarterly_allocation`). Role names
differ across directions by design: OUTBOUND's `cycle_focus_current`
reports "what's current on the agent"; INBOUND's `cycle_focus` delivers
"the new plan the Chat session decided on."

Boundary detection (`scope.month_boundary`, `scope.quarter_boundary`) is
stamped into outbound manifests. The anchor is the most recent
`run_history.json` entry whose `cycle_id` differs from the current cache
— not simply the last entry, which the agent may have written for the
current cycle before bundling.

## Testing

Run from repo root:

```
python3 -m pytest grailzee-cowork/tests/
```

Or the full suite (grailzee-eval + grailzee-cowork):

```
python3 -m pytest
```

The repo-root `pytest.ini` scopes discovery to both test trees and adds
both skill roots to `pythonpath` under disjoint package names (`scripts`
for grailzee-eval, `grailzee_bundle` for grailzee-cowork) so imports
never collide. `--import-mode=importlib` isolates the same-named `tests`
packages between the two sides.

## Plugin metadata

See `.claude-plugin/plugin.json`. The plugin is named
`vardalux-grailzee-cowork`; the single skill is `grailzee-bundle`.
