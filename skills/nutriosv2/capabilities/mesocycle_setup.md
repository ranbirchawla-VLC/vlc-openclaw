# Capability: Mesocycle Setup

Handles Capability 1 — scratch path. Clone path is sub-step 9.

## HARD RULES (non-negotiable)

- **Never substitute a value the user did not give.** If a numeric input is
  missing, ask. Do not infer from cycle name, context, prior conversations,
  or convention.
- **Never describe the Python tool, its inputs, or its algorithm to the user.**
  The user does not need to know a script exists.
- **Read back numbers exactly as the tool returns them.** Do not re-explain,
  re-derive, or annotate them. If the tool says 2086, you say 2086.
- **"Maintenance", "cut", "bulk" are user-chosen names, not constraints.**
  The numeric constraints come only from the intent fields the user fills in.
  A cycle named "maintenance" with a deficit of 1850 kcal/week is a deficit
  cycle — period. Do not override.
- **When the user supplies a deficit value, pass it through verbatim.**
  Even if the cycle name suggests otherwise, the user's stated number wins.
- **The deficit input is weekly kcal.** Pass it to compute_candidate_macros
  exactly as the user states it. Never divide, multiply, or adjust before
  calling the tool. The tool handles the weekly-to-daily conversion internally.
- **Zero arithmetic.** Per project CLAUDE.md: every number you say came from a tool
  return. Do not compute, redistribute, sum, average, or restate-with-recomputed-totals.
  No expressions of the form `<number> <operator> <number> = <number>` ever.
  If you find yourself about to write a number you computed, stop and call the tool.
- **Recompute on intent change.** When the user changes any of
  {weekly_deficit_target, protein_floor, fat_ceiling, TDEE_estimate, weeks, dose_weekday},
  call `compute_candidate_macros` again with the updated values before any further macro
  discussion. Do not reuse the prior weekly intake number. Existing user-stated row
  overrides may be re-applied via `recompute_macros_with_overrides` only after the new
  baseline is fetched.
- **If any tool returns an error** (over-budget, floor/ceiling violation), surface the
  constraint in plain language and ask how the user wants to resolve it. Do not proceed
  with the prior table.

## Conversation flow

1. Greet, confirm setup intent ("Let's set up a new mesocycle").
2. Ask: name for this cycle (free text, e.g. "cut", "maintenance").
3. Ask: how many weeks (integer, >= 1).
4. Ask: dose day of week (offer buttons: Mon Tue Wed Thu Fri Sat Sun → returns 0..6).
5. Collect intent — all optional, ask conversationally:
   - Weekly deficit target in kcal? (e.g. 3500 = ~1 lb/week; 0 = true maintenance)
   - Daily protein floor in grams?
   - Daily fat ceiling in grams?
   - Estimated daily TDEE in kcal? (required if deficit given)
   - Any notes or doctor's instructions? (free text)
6. For each of the 7 rows (offset 0 = dose day, offset 1 = next day, ..., offset 6 = day before dose):
   - Determine the row's weekday name by counting forward from the dose day the user gave.
     If dose day is Sunday: offset 0 = Sunday, offset 1 = Monday, offset 2 = Tuesday,
     offset 3 = Wednesday, offset 4 = Thursday, offset 5 = Friday, offset 6 = Saturday.
     Apply the same forward-count logic for any other dose day.
   - Call `compute_candidate_macros` with the intent values for that offset.
   - Read back the result labeled by weekday name with all four fields, e.g.:
     "Sunday: 2,086 cal; 175g protein, 65g fat, 200g carbs."
   - If any values are null, say what's missing and ask the user to fill in.
   - User may accept or revise each row. Repeat until confirmed.
   - Ask for any per-row restrictions (free text, e.g. "low fat after dose"). Empty is fine.
7. Read back the full 7-row table as a compact summary. Label each row by weekday name.
   Include all four fields for every row: calories, protein_g (g), fat_g (g), carbs_g (g).
8. Ask for confirmation ("Does this look right? Confirm to lock it in.").
9. On confirmation: call `lock_mesocycle` with all collected values.
   - Use today's date (ISO format: YYYY-MM-DD) as `start_date`. Do not ask the user for it.
   - Report back: "Done. Cycle [name] locked — ID [id], runs [start] to [end]."

## Adjustment flow (row override)

When the user proposes changing a specific day's calories during table negotiation
(e.g., "Monday should be 1,550; raise the rest"):

1. Identify the override: which weekday the user named, and the new calorie value.
   Convert the weekday name to its offset using the same mapping as step 6:
   offset 0 = dose day, offset 1 = one day later, offset 2 = two days later, etc.
   Example: dose day Sunday, user names Monday => offset '1'.
   Example: dose day Sunday, user names Wednesday => offset '3'.
2. Call `recompute_macros_with_overrides` with:
   - `estimated_tdee_kcal` and `target_deficit_kcal` passed through verbatim from the
     user's original intent (same values used in compute_candidate_macros).
   - `dose_weekday`, `protein_floor_g`, `fat_ceiling_g` from the active setup.
   - `overrides`: a map of the offset string key to `{"calories": <user-value>}`.
3. Read back the full 7-row result labeled by weekday name, including all four fields.
   State the weekly_kcal_target from the tool response; do not sum the rows yourself.
4. If the tool returns an error, tell the user which constraint was violated
   (e.g., "that Monday value leaves the remaining days below your protein floor of 175g;
   want to try a lower number?"). Ask how to resolve; do not silently proceed.

## Read-back flow ("what's my cycle")

When the user asks about their active cycle ("what's my cycle", "show my plan",
"what are my macros today", etc.):

1. Call `get_active_mesocycle`.
2. If null: "No active cycle yet — want to set one up?"
3. If found: read back in plain language:
   - Cycle name and ID
   - Dose weekday (as a word: Monday, Tuesday, etc. — never a number)
   - Date range (start → end)
   - Today's macro row: compute which offset today falls on relative to the most
     recent dose day, then surface that row's calories/protein/fat/carbs and any
     restrictions.

## Rules

- All dates are set by Python (lock_mesocycle sets start_date to today).
- Label each macro row by weekday name only (e.g., "Sunday", "Monday"); never by numeric offset (+0, +1, etc.); never by relative description ("day after dose", "day 1", "dose day").
- Never use the word "offset" when speaking to the user. Start the macro table directly with weekday-labeled rows; no preamble explaining the numbering scheme.
- Zero arithmetic: every number you state was returned by a tool. See project CLAUDE.md.
- Macros are immutable once locked. If the user wants to change them, that is a
  new cycle (sub-step 9 handles mid-cycle changes).
