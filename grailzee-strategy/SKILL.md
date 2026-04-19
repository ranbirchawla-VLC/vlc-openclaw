---
name: grailzee-strategy
description: Chat-side strategy session for Vardalux Grailzee cycles. Operator uploads an outbound bundle .zip from the grailzee-cowork plugin; this skill reads the cycle state, runs the strategy conversation, and produces a validated strategy_output.json the operator hands back to cowork for atomic apply. Four modes — cycle_planning, monthly_review, quarterly_allocation, config_tuning.
---

# grailzee-strategy

The Chat-side counterpart to the `grailzee-cowork` plugin. One skill,
four session modes, one output contract: `strategy_output.json`
conforming to `schema/strategy_output_v1.json`.

## When to activate

The operator uploads a `.zip` file named like
`grailzee_outbound_cycle_YYYY-NN_*.zip` and asks for a strategy
session, a cycle plan, a monthly review, a quarterly rebalance, or a
config tune. If any of those conditions are met, activate.

If the operator uploads a `.zip` and asks ambiguously ("what do you
make of this?"), default to `cycle_planning` mode and call out the
assumption in your first message.

## Before you write anything

Read in order (all are in the uploaded `.zip`):

1. `manifest.json` — note `scope.month_boundary` and
   `scope.quarter_boundary`. These drive which decision sections the
   session is responsible for populating.
2. `sourcing_brief.json` — the agent's current narrative read.
3. `trade_ledger_snippet.csv` — realized margins and ROI for the
   current cycle's closes.
4. `analysis_cache.json` — every known reference with `signal`,
   `max_buy_nr`, `brand`, `model`.
5. `cycle_focus_current.json` — what the agent currently focuses on.
6. `monthly_goals.json` / `quarterly_allocation.json` — current state.
7. `latest_report/grailzee_YYYY-MM-DD.csv` — raw market snapshot, for
   spot-checks only.

Then read `references/strategy-framework.md` for the per-mode decision
framework, the `session_artifacts.cycle_brief_md` conventions, and the
guardrails. Then look at the closest `references/mode_fixtures/*.json`
for shape.

## Mode dispatch

| Operator signal | `session_mode` |
|---|---|
| "new cycle", "plan the cycle", "what do we lead with" | `cycle_planning` |
| "monthly review", "wrap up April", "May plan" | `monthly_review` |
| "quarterly rebalance", "Q3 allocation", "brand capital shift" | `quarterly_allocation` |
| "retune thresholds", "change the signal floor", "fix the margin config" | `config_tuning` |

`session_mode` captures operator intent. Which decision sections you
actually populate is driven by the bundle's scope flags — see
`references/strategy-framework.md` for the full table.

## Output contract

A single JSON document: `strategy_output.json`, schema version 1.

Hard rules (the validator rejects anything that violates these):

- Top-level `strategy_output_version` must be `1`.
- `generated_at` must be ISO-8601 UTC with `Z` suffix.
- `cycle_id` must match `^cycle_[0-9]{4}-[0-9]{2}$`.
- `session_mode` must be one of:
  `cycle_planning | monthly_review | quarterly_allocation | config_tuning`.
- `produced_by` must start with `grailzee-strategy/`. Use
  `grailzee-strategy/0.1.0`.
- At least one of `decisions.cycle_focus`,
  `decisions.monthly_goals`, `decisions.quarterly_allocation`,
  `decisions.config_updates` must be non-null.
- `target_margin_fraction` is a **fraction** (e.g. `0.05` = 5%),
  NOT a percentage. Must be in `(0, 1)` exclusive.
- `config_updates`, when non-null: at least one of the six
  sub-configs must be non-null, `change_notes` must be non-empty,
  and every non-null sub must carry the envelope
  (`version`, `updated_at`, `updated_by`, `notes`).
- `session_artifacts.cycle_brief_md` is required and must be a
  non-empty markdown string.

See `schema/strategy_output_v1.json` for the full spec and the four
example payloads in `references/mode_fixtures/` for shape.

## Delivery

Hand the operator:

1. The full `strategy_output.json` as a code block they can
   download or paste into a file.
2. A one-paragraph summary of what's in it (which decisions
   populated, what the headline move is).
3. Instructions to run:
   ```
   python grailzee-cowork/grailzee_bundle/unpack_bundle.py \
     strategy_output.json \
     --grailzee-root <path-to-GrailzeeData>
   ```
4. A note that the plugin will: validate the schema, confirm
   `cycle_id` matches the current cache, atomically write each
   populated decision to `state/`, and archive the brief +
   XLSX + JSON to `output/briefs/`.

## What NOT to do

- Do NOT produce partial JSON that doesn't validate. If the session
  didn't produce at least one decision section, surface that to the
  operator and ask what to do — don't pad a section with current
  state just to fill it.
- Do NOT invent references that aren't in `analysis_cache.json`.
  Every `cycle_focus.target` must correspond to a ref the agent
  knows about, OR be flagged in `notes` as operator-requested without
  prior coverage.
- Do NOT change the margin floor (`target_margin_fraction`) without
  explicit operator direction. Standard is `0.05`.
- Do NOT retune config sub-blocks unless `session_mode` is
  `config_tuning`. Other modes keep `config_updates: null`.
- Do NOT guess the current config version. Read it from the
  corresponding file in the outbound bundle if present; otherwise
  ask the operator.
- Do NOT add fields outside the schema. `additionalProperties:
  false` is set across the whole document.

## Self-check before delivering

Before you hand the JSON to the operator, verify:

- [ ] `strategy_output_version` is `1`
- [ ] `cycle_id` matches the bundle's manifest
- [ ] At least one decision section is non-null
- [ ] `target_margin_fraction` is a fraction, not a percentage
- [ ] `session_mode` is one of the four enum values
- [ ] `produced_by` starts with `grailzee-strategy/`
- [ ] `session_artifacts.cycle_brief_md` is present and non-empty
- [ ] If `config_updates` is non-null: every non-null sub carries
      the envelope; at least one sub is non-null; `change_notes` is
      present and non-empty
- [ ] No fields outside the schema

If any check fails, fix and re-verify before delivery.
