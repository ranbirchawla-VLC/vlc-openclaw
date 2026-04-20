# Grailzee Strategy Framework

Reference for the Chat strategy session. Read this before producing
any `strategy_output.json`. Pair it with the schema at
`schema/strategy_output_v1.json` and the example payloads in
`mode_fixtures/`.

## What this session is for

The Grailzee agent runs deterministic analysis (signals, scoring,
ledger, reports) locally on the operator's machine. This session
adds the layer the agent can't do: judgment. Specifically:

- Reading the cycle's performance in narrative form, not just numbers
- Deciding which references to lead with this cycle and why
- Rebalancing capital across brands / tiers when the data moves
- Retuning analyzer thresholds when signal quality drifts
- Writing a brief the operator can read, react to, and carry forward

The session's output is a single `strategy_output.json` payload that
the cowork plugin validates, applies atomically to `state/`, and
archives to `output/briefs/`. State is the source of truth; the
archive is the human-readable companion.

## Reading the outbound bundle

Every session starts with the operator handing over a bundle `.zip`
produced by `grailzee-cowork`. Before deciding anything, read the
bundle in this order:

1. **`manifest.json` → `scope`** — `month_boundary` and
   `quarter_boundary` flags tell you whether this session spans a
   rollover. If `month_boundary: true`, the operator expects
   `monthly_goals` populated. If `quarter_boundary: true`, same for
   `quarterly_allocation`. Both flags false and `session_mode:
   cycle_planning` → `cycle_focus` only. (Both flags false and
   `session_mode: config_tuning` → `config_updates` only, since
   config_tuning never reads the flags.)

2. **`sourcing_brief.json`** — the agent's current read. This is the
   richest signal of what the operator has already seen. If this
   brief is strong, your job is to layer judgment on top, not to
   restate it.

3. **`trade_ledger_snippet.csv`** — current cycle's closes with
   `net_profit` and `roi_pct`. Check margin drift: if `roi_pct`
   clusters below `target_margin_fraction * 100`, that's a signal
   to retune `margin_config` or reconsider platform mix, not just
   to push harder on sourcing.

4. **`analysis_cache.json`** — every reference the agent knows
   about, with `signal`, `max_buy_nr`, `brand`, `model`. This is
   your source for populating `cycle_focus.targets`.

5. **`cycle_focus_current.json`** — what the agent currently
   focuses on. Your `cycle_focus` decision either confirms, evolves,
   or replaces this.

6. **`monthly_goals.json` / `quarterly_allocation.json`** — current
   state. If you're not crossing the relevant boundary, leave these
   untouched (decision section null). If you ARE crossing, write a
   full replacement.

7. **`cycle_outcome_previous.meta.json` + `cycle_outcome_previous.json`**
   — the most recent completed cycle that produced real trade data, as
   resolved by the bundle builder. Read the meta first:
   - `source_cycle_id` — which cycle this payload is for. Usually the
     cycle immediately before `cycle_id`, but NOT always: cycles with
     zero trades are skipped, so a `cycle_2026-08` planning session
     may surface `cycle_2026-06` as the source if cycle 07 had no
     closes. Call the skip out in the brief's headline or PERFORMANCE
     section when it happens.
   - `skipped_cycles` — the empty cycles walked past, if any.
   - `resolution_note` — human-readable summary of what was resolved.
   - `source_cycle_id: null` means no prior cycle has trade data (first
     session on a fresh deployment, or the ledger hasn't accumulated
     14-day closes yet). In that case `cycle_outcome_previous.json` is
     absent from the bundle; do NOT render empty PERFORMANCE or
     WHAT WE ACTUALLY BOUGHT sections. The brief should say explicitly
     "no prior cycle outcome available" and frame purely from current
     signal + cache.

   When the outcome file IS present, its payload is the same structure
   `roll_cycle.py` produces: `cycle_id`, `date_range`, `trades[]`,
   `summary`, and `cycle_focus` (snapshot of what was targeted at the
   time). Use the `summary` totals (total_trades, profitable, avg_roi,
   total_net, capital_deployed) in the brief's PERFORMANCE section.
   Use `trades[]` with their `in_focus` flags for WHAT WE ACTUALLY
   BOUGHT — off-cycle closes (`in_focus: false`) are the tell that
   the prior plan missed the shot. Anchor every quantified claim
   ("we did X% ROI") to these numbers, not to the operator's memory.

8. **`latest_report/grailzee_YYYY-MM-DD.csv`** — raw market data
   snapshot. Usually consulted only for spot-checking specific
   references.

## Decision framework per `session_mode`

`session_mode` is a single string — the operator's stated intent at
session start. It does NOT determine which decision sections you
populate; the scope flags in `manifest.json` do that. Scope flags can
compound: a `cycle_planning` session on a month boundary populates BOTH
`cycle_focus` AND `monthly_goals`. The one exception is `config_updates`,
which is populated ONLY when `session_mode: config_tuning` — never
inferred from scope flags. Populate only the sections the session
actually produced.

### `cycle_planning` (default)

Operator is starting a new cycle. Expected output: `cycle_focus`
populated; other sections null unless a boundary flag is also set.

**What `cycle_focus` must include:**

- `targets`: **3–6 references** the operator will lead with. Each
  target carries a one-sentence `cycle_reason` that ties the pick
  to data the agent already has (signal, margin history, confirmed
  buyer, momentum, etc.). Vague reasons ("looks good") are a
  rejection signal for the operator.
- `capital_target`: deployable dollars this cycle. Pulls from the
  operator's dictation; if absent, use the last cycle's value from
  `cycle_focus_current.json` as a default and call it out in notes.
- `volume_target`: integer unit count, not dollars.
- `target_margin_fraction`: **fraction, not percentage**. `0.05`
  means 5%. The standard Vardalux floor is 5% net; only deviate on
  explicit operator direction.
- `brand_emphasis`: brands to push this cycle. Can be empty.
- `brand_pullback`: brands to avoid. Can be empty.
- `notes`: the **why** behind the capital/volume numbers.
  Mechanical restatement of the targets belongs in `cycle_reason`,
  not here.

**`max_buy_override`** on a target is the escape hatch for cases
where the agent's computed `max_buy_nr` doesn't match the operator's
read (e.g. confirmed buyer at a known price). Leave null if the
agent's number is fine. Setting this to the agent's existing
`max_buy_nr` is noise — don't do it.

### `monthly_review`

Fires on `scope.month_boundary: true`. Expected output:
`monthly_goals` populated. `cycle_focus` usually stays null unless
the operator also wants a mid-cycle refresh.

**What `monthly_goals` must include:**

- `month`: the **new** month in `YYYY-MM` form. Not the one just
  closed.
- `revenue_target` / `volume_target`: set for the new month.
  Informed by the prior month's realized numbers, which live in the
  ledger snippet.
- `platform_mix`: percentages by platform. Should sum to ~100. If
  you don't have a clear read, use an empty object — the validator
  permits that as a partial update signal.
- `focus_notes`: the **forward-looking** judgment. What to lean
  into this month.
- `review_notes`: the **backward-looking** recap. What the prior
  month actually did — volume vs target, revenue vs target, margin
  actual, standouts, misses. This is what operators re-read most.

### `quarterly_allocation`

Fires on `scope.quarter_boundary: true`. Expected output:
`quarterly_allocation` populated.

**What `quarterly_allocation` must include:**

- `quarter`: the **new** quarter in `YYYY-QN` form.
- `capital_allocation`: brand → dollar allocation. Sum is the total
  quarterly capital. Include an "other" bucket.
- `inventory_mix_target`: tier → percentage (e.g.
  `{"Strong": 60, "Normal": 30, "Weak": 10}`). Sum to ~100.
- `review_notes`: prior quarter recap with **quantified deltas**
  per brand. Operators resist unquantified rebalancing — anchor
  every Q-over-Q shift to a realized number.

Watch out for **rebalancing drift**: don't move more than one brand
per quarter by >$10k without an explicit data trigger in the recap.
Churn-for-churn's-sake hurts inventory turn.

### `config_tuning`

Fires only on explicit operator request — NEVER inferred from scope
flags. Expected output: `config_updates` populated with one or more
of the six D5 sub-configs.

**The six configs**: `signal_thresholds`, `scoring_thresholds`,
`momentum_thresholds`, `window_config`, `premium_config`,
`margin_config`. Each sub-config is a **full replacement** of
`state/<name>.json` — not a patch. Preserve every field the config
needs, not just the ones you're changing.

**Envelope (required on every non-null sub)**:

- `version`: increment from the current file's version (read from
  the outbound bundle's state copy if present, else 1).
- `updated_at`: the session's `generated_at` timestamp.
- `updated_by`: `"strategy_session"`.
- `notes`: one-to-two-sentence rationale for this specific sub.

**`change_notes`** at the `config_updates` level summarizes what
shifted across all sub-configs. If the operator reads only one
thing about this session, it's this field.

**Guardrails:**

- Never tune more than **two sub-configs in a single session**.
  Large simultaneous shifts make the before/after unattributable.
- Every change needs a **data anchor** (a ledger observation, a
  signal drift, a fee change). Changes without anchors are
  operator fatigue in JSON.
- Leave the four untouched sub-configs **explicitly null**. Don't
  carry forward the current contents — that would produce identical
  writes and confuse the "changed in this session" read.

## Writing `session_artifacts.cycle_brief_md`

Required on every session. The plugin archives it to
`output/briefs/<cycle_id>_strategy_brief.md` where the operator
re-reads it days later out of context.

**Brief structure** (adapt headings to the session's subject):

1. **Headline** — one or two sentences. What's the state of play.
2. **Decisions** — the populated decision sections, rendered as
   readable prose or tables. Redundant with the JSON decisions; the
   brief exists for human reading.
3. **Follow-ups** — what to watch, re-run triggers, what the
   session deferred.

Use GitHub-flavored markdown. Tables are fine for target lists and
allocation breakdowns. Absolute dates over relative ("April", not
"last month") so the brief doesn't rot when the operator opens it
three weeks later.

## When NOT to populate a section

The INBOUND contract is: only the non-null decision sections
produce state writes. A null section means "no change this
session". This is more valuable than it looks — it lets a
`monthly_review` session leave cycle_focus untouched without a
blank-out write.

Always set to null rather than empty when there's nothing to say:

- No mid-cycle focus change → `cycle_focus: null`
- No month boundary → `monthly_goals: null`
- No quarter boundary → `quarterly_allocation: null`
- No config retune → `config_updates: null`

The schema requires **at least one** non-null decision. A session
with nothing to commit is not a session worth archiving.

## Vardalux-specific context

- **Standard margin floor**: 5% net (`target_margin_fraction: 0.05`).
  Confirmed via `grailzee_common.TARGET_MARGIN` on the agent side.
- **Capital**: dollar figures. No euros, no fractional dollars below
  the cent. Store as numbers (JSON number), not strings.
- **Brands**: prefer canonical names — `Tudor`, `Rolex`, `Omega`,
  `Cartier`, `Patek Philippe`. Use the same string in JSON keys and
  in prose (no underscore/space drift). Platform names as the agent
  writes them — `Grailzee`, `eBay`, `Chrono24`.
- **Cycle IDs**: `cycle_YYYY-NN` form. `NN` is an incrementing cycle
  counter (01–99), not a month or week number. The schema regex
  enforces format only; semantic range validation is the agent's
  responsibility at cycle creation.

## Guardrails (things to NEVER do)

- **Never** embed percentages as numbers-over-100 for
  `target_margin_fraction`. 5% is `0.05`, not `5`.
- **Never** populate a decision section with the current state's
  contents just to have it present. That produces a no-op write.
- **Never** guess a `cycle_reason` from brand+model alone. If the
  reference isn't in `analysis_cache.json`, say so in notes — don't
  hallucinate a signal read.
- **Never** set `produced_by` to anything other than a string
  starting with `grailzee-strategy/`. The validator rejects other
  prefixes.
- **Never** skip `session_artifacts.cycle_brief_md`. It's required
  by the schema; more importantly, the operator's archive depends
  on it.
