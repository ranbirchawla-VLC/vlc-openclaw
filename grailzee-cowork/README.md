# vardalux-grailzee-cowork

Claude Code plugin that bridges the Grailzee agent (local auction analysis)
with the Chat strategy workflow. Two modes, one skill (`grailzee-bundle`):

- **OUTBOUND** — packages the current GrailzeeData state (cache, cycle focus,
  goals, ledger snippet, brief, latest report CSV) into a single validated
  `.zip` for upload to a Chat strategy session.
- **INBOUND** — validates a strategy-session `.zip` and atomically writes the
  returned planning artifacts (cycle focus, monthly goals, quarterly
  allocation) back into GrailzeeData state.

The plugin is self-contained. It does not import from `skills/grailzee-eval/`
at runtime. Path coupling is through the `--grailzee-root` CLI flag.

## Layout

```
grailzee-cowork/
├── .claude-plugin/plugin.json
├── skills/grailzee-bundle/SKILL.md
├── grailzee_bundle/
│   ├── build_bundle.py   # OUTBOUND
│   └── unpack_bundle.py  # INBOUND
└── tests/
```

## Testing

Tests run from repo root via the project-level `pytest.ini`:

```
python3 -m pytest
```

The root `pytest.ini` scopes discovery to `skills/grailzee-eval/tests` and
`grailzee-cowork/tests`, and adds both skill roots to `pythonpath` under
disjoint package names (`scripts` for grailzee-eval, `grailzee_bundle` for
grailzee-cowork) so imports never collide.
