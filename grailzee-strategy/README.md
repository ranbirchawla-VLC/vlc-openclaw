# grailzee-strategy

Chat-side skill for Vardalux Grailzee strategy sessions.

The Grailzee agent runs deterministic analysis locally on the operator's
machine — signals, scoring, ledger, reports. This skill is the judgment
layer: cycle planning, monthly review, quarterly allocation, and config
tuning. It produces a single `strategy_output.json` that the sibling
`grailzee-cowork` plugin validates and applies atomically.

## Relationship to other components

```
    GrailzeeData/              ← local agent, deterministic
        state/
        output/

          │
          │  (1) cowork builds outbound bundle .zip
          ▼
    grailzee-cowork plugin  ──────────────────►  Chat (this skill)
          ▲                                            │
          │                                            │ (2) strategy session
          │                                            │     produces
          │                                            │     strategy_output.json
          │                                            ▼
          │           (3) operator hands JSON back to cowork
          └────────────────────────────────────────────┘
                   (4) cowork unpacks, validates, applies atomically
```

Three components, one handshake:

- **Local agent** (GrailzeeData/) — owns state, does analysis.
- **grailzee-cowork plugin** — outbound `.zip` builder + inbound applier
  for both `.zip` (Phase 24a) and `strategy_output.json` (Phase 24b).
- **grailzee-strategy skill** (this repo) — runs the chat session,
  writes the JSON.

## Layout

```
grailzee-strategy/
├── SKILL.md                              ← skill entrypoint (loaded by Chat)
├── README.md                             ← this file (developer docs)
├── TESTING.md                            ← manual test playbook
├── schema/
│   └── strategy_output_v1.json           ← byte-identical to cowork copy
└── references/
    ├── strategy-framework.md             ← per-mode decision framework
    └── mode_fixtures/
        ├── cycle_planning.json           ← realistic payload shapes
        ├── monthly_review.json
        ├── quarterly_allocation.json
        └── config_tuning.json
```

The schema under `schema/` is kept byte-identical to
`grailzee-cowork/schema/strategy_output_v1.json`. If one
changes, the other must change in lockstep. This duplication is
deliberate: the Chat skill needs its own copy because it operates
without filesystem access to the cowork plugin, and a bumped schema
version on one side without the other breaks the contract.

## The four session modes

| Mode | Trigger | Primary decision section |
|---|---|---|
| `cycle_planning` (default) | New cycle starting | `cycle_focus` |
| `monthly_review` | `scope.month_boundary: true` in bundle | `monthly_goals` |
| `quarterly_allocation` | `scope.quarter_boundary: true` in bundle | `quarterly_allocation` |
| `config_tuning` | Explicit operator request only | `config_updates` |

`session_mode` captures operator intent as a single string. Which
decision sections actually get populated is driven by the scope flags
in the outbound bundle's `manifest.json`, NOT by the mode name. The
"primary decision section" column above is the usual single-section
outcome; when scope flags compound, a session populates multiple
sections. For example, a `cycle_planning` session on a month boundary
populates both `cycle_focus` and `monthly_goals`. `config_updates` is
the one exception — it is populated only on `session_mode:
config_tuning`, never inferred from flags.

See `references/strategy-framework.md` for the full rule.

## The output contract

`strategy_output.json` is version 1. Hard rules:

- `strategy_output_version: 1`
- `cycle_id` matches `^cycle_[0-9]{4}-[0-9]{2}$`
- `produced_by` starts with `grailzee-strategy/` (use
  `grailzee-strategy/0.1.0`)
- At least one of `decisions.cycle_focus`, `decisions.monthly_goals`,
  `decisions.quarterly_allocation`, `decisions.config_updates` must be
  non-null
- `target_margin_fraction` is a fraction in `(0, 1)` — `0.05` = 5%,
  never `5`
- `session_artifacts.cycle_brief_md` is required and non-empty
- `additionalProperties: false` across the whole document

See `schema/strategy_output_v1.json` for the full spec and
`references/mode_fixtures/` for one realistic payload per mode.

## How the operator uses this

1. Operator runs the local agent to build the outbound bundle:
   ```
   python grailzee-cowork/grailzee_bundle/build_bundle.py \
     --grailzee-root <path-to-GrailzeeData>
   ```
   This produces a `.zip` under `GrailzeeData/cowork_outbound/`.
2. Operator uploads the `.zip` to Chat with a strategy prompt.
3. Chat activates this skill, reads the bundle, runs the session, and
   hands back a `strategy_output.json` code block.
4. Operator saves the JSON to a file and runs:
   ```
   python grailzee-cowork/grailzee_bundle/unpack_bundle.py \
     strategy_output.json \
     --grailzee-root <path-to-GrailzeeData>
   ```
5. Cowork validates, applies each populated decision atomically to
   `state/`, and archives the brief (markdown + XLSX + JSON) to
   `output/briefs/`.

Step 5's archive leg is best-effort; state is the source of truth. An
archive write failure does not roll back the state commit.

## Version

- Skill version: `0.1.0` (set in `produced_by`)
- Schema version: `1` (set in `strategy_output_version`)

## Model

This skill runs on Claude Opus 4.7 (via Chat). The strategy work is
primarily synthesis and judgment, not deterministic computation — the
numbers come from the outbound bundle, the prose comes from the model.
