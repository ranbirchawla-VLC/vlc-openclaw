# REVIEW — Phase 24b Deliverable B (grailzee-strategy)

**Reviewer:** code-reviewer subagent
**Date:** 2026-04-19
**Scope:** grailzee-strategy/ (new skill, C9–C11 commits on
`feature/grailzee-eval-v2`)

## Verdict

**Ship-with-nits.** The skill is coherent, the schema contract is
mirrored byte-identically (confirmed by diff), all four fixtures pass
the cowork validator, and the documentation structure is sane. The
critical findings were all in the "tighten before the first real
operator session" bucket, not blockers. The self-check checklist was
meaningfully underspecified against what the validator actually
enforces — that was the one thing worth insisting on before live use,
because there is no feedback loop from the validator back to the model.

All critical and recommended findings have been resolved or explicitly
punted with rationale below.

## Critical findings — RESOLVED

### 1. `SKILL.md` self-check missed several validator rules the model can still violate

**Finding:** The cowork validator enforces rules the original self-check
didn't prompt the model to verify: ISO-8601 format with `Z` suffix,
`cycle_id` regex, `month`/`quarter` patterns, `decisions` exact_keys
(not just "at least one non-null"), `platform_mix` per-value bounds,
`targets` minItems, config envelope on every non-null sub, untouched
config subs must be null (not carried forward).

**Resolution:** Rewrote the self-check section in `SKILL.md` from a
flat 9-item list to a grouped checklist covering: top-level shape (5
items), decisions block (3 items), cycle_focus (3 items), monthly_goals
(2 items), quarterly_allocation (2 items), config_updates (4 items),
artifacts and closure (2 items). Every item corresponds to a specific
validator rejection path. Led the section with explicit framing: "the
cowork validator is strict and you won't see its error messages before
the operator runs it."

Commit: this commit.

### 2. `SKILL.md` and `README.md` disagreed on whether `session_mode` drives section population

**Finding:** The README's "Populates" column implied a 1:1 mapping from
mode to section, but the explanatory paragraph and SKILL.md both said
scope flags are authoritative. Skimming maintainers would retain the
table, not the walk-back.

**Resolution:** Renamed the column from "Populates" to "Primary
decision section" and rewrote the explanatory paragraph to be explicit
that scope flags drive actual population, `config_updates` is the one
exception (never inferred from flags), and compounding is possible
(`cycle_planning` on a month boundary populates both `cycle_focus` and
`monthly_goals`).

Commit: this commit.

### 3. Neither `SKILL.md` nor `strategy-framework.md` specified the `session_mode`-vs-scope-flag compound rule

**Finding:** What should the model do if `session_mode: cycle_planning`
AND `scope.month_boundary: true`? Populate both, or only one? Ambiguous
in both docs.

**Resolution:** Stated the rule explicitly in three places:

1. `SKILL.md` "Mode dispatch" section now lists each decision section's
   trigger condition separately and closes with: "Scopes can compound.
   A cycle_planning session on a month boundary populates BOTH
   cycle_focus AND monthly_goals."
2. `strategy-framework.md` "Decision framework per session_mode"
   preamble now carries the same compound-scope statement, with the
   `config_updates` exception called out.
3. `README.md` "Four session modes" section now explains the compound
   behaviour with the same example.

One rule, three consistent statements. The `config_updates` exception
(never inferred from flags) is stated in all three.

Commit: this commit.

## Recommended — RESOLVED

### 4. `quarterly_allocation.json` fixture had `Grand_Seiko` (underscore) vs "Grand Seiko" (space) drift

**Finding:** JSON keys used the underscored form; the prose used the
spaced form. That teaches the model it's fine to substitute variants
when "JSON looks nicer" and breaks state-query anchoring.

**Resolution:** Replaced `Grand_Seiko` with `Cartier` throughout the
fixture (both the JSON `capital_allocation` key and the brief prose,
including the rationale which now references Cartier Santos). Cartier
is a plausible $15k-range exploratory allocation. Updated the
canonical brand list in `strategy-framework.md` to drop Grand Seiko
and add Cartier. Also added an explicit "Use the same string in JSON
keys and in prose (no underscore/space drift)" instruction to the
framework's brand-naming note.

(User-global-instructions specifically ask not to suggest Grand Seiko.
Flagging that Cartier replacement also respects that directive.)

Commit: this commit.

### 5. `SKILL.md` claimed `additionalProperties: false` "across the whole document" — not quite true

**Finding:** `configSubBlock` in the schema does not set
`additionalProperties: false`. That's deliberate — sub-configs carry
config-specific fields — but the overreaching claim would confuse
future maintainers.

**Resolution:** Rephrased the "What NOT to do" bullet in `SKILL.md` to:
"Every object is closed (`additionalProperties: false`) **except** the
six config sub-blocks inside `config_updates`, which accept
config-specific fields beyond the required envelope (e.g.
`strong_min_net_margin_pct`, `platform_overrides`). Everywhere else,
stray keys are rejected." The self-check's closing "no fields outside
the schema" item carries the same parenthetical.

Commit: this commit.

### 6. No mechanical enforcement of the schema mirror

**Finding:** The schema is duplicated across `grailzee-strategy/` and
`grailzee-cowork/` by design, but only a manual `diff` in TESTING.md
guarded drift. Manual guards on critical invariants rot.

**Resolution:** Added `grailzee-strategy/tools/check_schema_mirror.py`,
a standalone Python script that reads both schema files, exits 0 on
byte-identity, exits non-zero with a diagnostic message on drift.
Handles missing files separately. Documented in TESTING.md Test 1 as
the canonical pre-commit / pre-CI check, with the inline `diff`
command kept for manual inspection. Verified the happy path locally
(exit 0, prints "byte-identical across both plugins").

Commit: this commit.

### 7. `TESTING.md` Test 5 expected `"other"` bucket; validator doesn't enforce it

**Finding:** The "other" bucket in `capital_allocation` is a framework
convention (framework line 134), not a validator rule. TESTING.md
promoted it to an expected pass/fail outcome without flagging the
distinction.

**Resolution:** Softened the Test 5 bullet to: "`capital_allocation`
has an `other` bucket (framework convention — not a validator rule,
but flag missing `other` as a judgment miss)". Distinguishes hard
validator rules from judgment-quality expectations without removing
the check.

Commit: this commit.

### 8. `TESTING.md` Test 7 acknowledged the `cycle_2026-15` regex hole with no resolution

**Finding:** The regex `^cycle_[0-9]{4}-[0-9]{2}$` accepts semantically
invalid months (00, 13, 15, 99). Test 7 honestly flagged this but
left the resolution unowned.

**Resolution:** Wrote the ownership explicitly into
`strategy-framework.md` "Vardalux-specific context" / Cycle IDs bullet:
"NN is an incrementing cycle counter (01–99), not a month or week
number. The schema regex enforces format only; semantic range
validation is the agent's responsibility at cycle creation." The
self-check in SKILL.md mirrors this ("NN segment is a cycle counter
(01–99), not a month number").

The regex itself is unchanged. Tightening it would require a
coordinated change across both schema copies AND `build_bundle.py`'s
mirror regex AND new cowork tests, which is out of Deliverable B
scope. Documented contract is acceptable; the semantic guard lives on
the agent side where the cycle counter is actually assigned.

Commit: this commit.

### 9. README.md "Layout" diagram missing blank line (cosmetic)

**Resolution:** Skipped — cosmetic only, reviewer classified as
"Cosmetic. Fine."

## Nits — RESOLVED (most)

- **SKILL.md line 90 "download" → "copy"**: applied. Claude code blocks
  have a copy button, not download.
- **Framework brief structure "session-mode independent"**: reworded to
  "adapt headings to the session's subject". More honest — the
  headings in the four fixture briefs are clearly subject-adapted.
- **Framework line 35 qualifier**: applied. The "both flags false →
  cycle_focus session" statement now reads: "Both flags false and
  `session_mode: cycle_planning` → `cycle_focus` only. (Both flags
  false and `session_mode: config_tuning` → `config_updates` only,
  since config_tuning never reads the flags.)"
- **Hard-coded `grailzee-strategy/0.1.0` in two files**: skipped per
  CLAUDE.md guidance to not refactor for hypothetical future changes.
  A version bump will touch both files directly.
- **Framework line 179 "operator fatigue in JSON"**: kept as-is per
  reviewer's explicit "keep it" note.

## What the reviewer liked (recorded for posterity)

- Schema byte-identity confirmed; README paragraph explaining *why* the
  duplication exists is load-bearing.
- All four mode fixtures pass the cowork validator.
- `cycle_reason` strings in `cycle_planning.json` are quantified and
  grounded — sets the right quality bar.
- `monthly_review.json`'s `review_notes` quantifies volume, revenue,
  margin, attributes the miss, uses absolute dates.
- `config_tuning.json` honours the "at most two sub-configs per
  session" guardrail and leaves the other four explicitly null.
- Skill correctly defers all enforcement to the validator; doesn't
  attempt to replicate rules.
- `strategy-framework.md` is right-sized for a file the model reads
  every session.

## Test coverage read

Reviewer's assessment: the manual playbook is above-average. Steps are
concrete, outcomes are checkable, the doc is honest about what it
can't test (deferred to cowork's automated suite: 60+ tests covering
schema, archive, state commit).

Two concerns raised by reviewer, both addressed:

1. **Soft expectations** like "3–6 targets" or "sum to ~100" —
   partially addressed by the restructured self-check, which now
   distinguishes hard validator rules from judgment-quality
   observations. TESTING.md still uses soft language for judgment
   quality, which is appropriate — the hard rules are the validator's
   job.
2. **The `cycle_2026-15` unowned hole** — resolved by writing the
   ownership into the framework doc; see Recommended #8.

The coverage split (manual for skill activation and judgment quality,
automated on the cowork side for contract enforcement) is correct.

## Sign-off

All critical and recommended findings resolved in this commit. Skill is
ready for first-operator use. Re-verified fixture validation after the
Cartier rename: all four mode_fixtures still pass cowork's
`validate_strategy_output`.

Files reviewed and subsequently modified:
- `grailzee-strategy/SKILL.md` — self-check, additionalProperties,
  download→copy, mode dispatch compound-scope rule
- `grailzee-strategy/README.md` — "Populates" column renamed and
  explanation rewritten
- `grailzee-strategy/TESTING.md` — Test 1 now points at guard script;
  Test 5 "other" bucket softened
- `grailzee-strategy/references/strategy-framework.md` — compound-scope
  rule, brand canonicalisation (Cartier for Grand Seiko, underscore
  drift warning), cycle_id semantic range, line 35 qualifier, brief
  structure wording
- `grailzee-strategy/references/mode_fixtures/quarterly_allocation.json`
  — Grand_Seiko → Cartier throughout

New file:
- `grailzee-strategy/tools/check_schema_mirror.py` — byte-identity
  guard, standalone, exits 0 on parity / non-zero on drift
