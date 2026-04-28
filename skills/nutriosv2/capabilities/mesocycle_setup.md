# Capability: Mesocycle Setup

Handles Capability 1; scratch path. Clone path is sub-step 9.

## Voice rules

Cross-cutting rules (zero arithmetic, no process narration, no tool description,
verbatim readback) live in the vlc-openclaw CLAUDE.md "LLM voice rules" section.
Apply them without restatement. The standing instruction: read tool-returned values
verbatim; produce no values, dates, or structural facts in your own composition.

## Capability rules

- **Never expose offset indexing in any form.** Not "offset 0", not "(offset 1)",
  not "+0/+1" column labels. Use weekday names exclusively.
  The day after a Sunday dose is "Monday", not "offset 1" or "+1".
- **If TDEE is given but deficit is absent, ask before computing.** Do not pass 0
  unless the user has explicitly stated "0", "no deficit", or "true maintenance".
  The cycle name alone is not a deficit statement.
  Prohibited example: user says "name it maintenance" + gives TDEE but no deficit;
  you ask "What's your weekly deficit target? Say 0 for true maintenance."
  You do not call compute_candidate_macros with target_deficit_kcal=0 until confirmed.
- **"Maintenance", "cut", "bulk" are labels, not constraints.** Numeric constraints
  come only from the values the user explicitly states. A cycle named "maintenance"
  with a deficit of 1,850 kcal/week is a deficit cycle. Do not override.
- **Pass deficit verbatim.** The user's stated number wins, regardless of cycle name.
- **Deficit unit: confirm before computing.** When the user supplies a deficit value
  without explicit unit context, apply NB-18 below. Pass the confirmed value and unit
  to compute_candidate_macros via deficit_unit.
- **Recompute on intent change.** When the user changes any of
  {deficit target, protein floor, fat ceiling, TDEE, weeks, dose day},
  call compute_candidate_macros again before any further macro discussion.
- **If any tool returns an error** (over-budget, floor/ceiling violation), surface the
  constraint in plain language and ask how the user wants to resolve it.

## NB-18: Numeric input confirmation

When the user supplies a deficit value where unit or scope could be read more than one
way, emit a read-back turn with three Telegram inline-keyboard buttons before computing.

Example message text: "Got it — 1,850 kcal weekly deficit. Confirm?"
buttons: [[{"text": "Yes", "callback_data": "yes"}, {"text": "No", "callback_data": "no"}, {"text": "Change", "callback_data": "change"}]]

- **Yes:** value commits. Call compute_candidate_macros with deficit_unit="weekly_kcal"
  (or "daily_kcal" if the user stated daily). Flow advances.
- **No:** ask what the user meant.
- **Change:** ask the user to re-enter the value.

Also accept plain-text fallback. "yes", "correct", "right", "yep", "that's right"
all mean Yes. "no", "wrong", "incorrect", "actually" mean No. Parse intent, not exact strings.

When the user explicitly states the unit ("500 a day", "1850 per week"), skip the
confirmation and call compute_candidate_macros directly with the correct deficit_unit.

## Conversation flow

When the user starts setup, walk through these inputs one question at a time.
Ask and wait for each answer before moving on. Do not front-load multiple questions.

1. Confirm intent: "Let's set up a new mesocycle. What do you want to call this cycle?"
2. Ask: "How many weeks?"
3. Ask: "What day do you dose?" — offer day buttons:
   buttons: [[{"text": "Mon", "callback_data": "0"}, {"text": "Tue", "callback_data": "1"}, {"text": "Wed", "callback_data": "2"}, {"text": "Thu", "callback_data": "3"}, {"text": "Fri", "callback_data": "4"}, {"text": "Sat", "callback_data": "5"}, {"text": "Sun", "callback_data": "6"}]]
   Never default the dose day. Always ask. Accept button callbacks (0..6) or day-name text.
4. Collect intent; ask conversationally one at a time:
   - Weekly deficit target in kcal? Apply NB-18 confirmation if unit is ambiguous.
     Required when TDEE is given. 0 = true maintenance but must be stated; never infer 0 from cycle name.
   - Daily protein floor in grams?
   - Daily fat ceiling in grams?
   - Estimated daily TDEE in kcal?
   - Any notes or doctor's instructions? (free text, empty ok)
5. For each of the 7 days, starting from the dose day and counting forward one day at a time:
   - Determine the weekday name by counting forward from the dose day.
     Example: dose day Sunday → rows are Sunday, Monday, Tuesday, Wednesday, Thursday, Friday, Saturday.
     Example: dose day Monday → rows are Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday.
   - Call compute_candidate_macros with the confirmed intent values.
   - Read back labeled by full weekday name: "Sunday: 2,086 cal; 175g protein, 65g fat, 200g carbs."
   - If any values are null, say what's missing and ask the user to fill in.
   - User may accept or revise each row. Repeat until confirmed.
   - Ask for per-day restrictions (free text, empty ok).
6. Read back the full 7-day plan as a compact summary. Label each row by weekday name.
   Include all four fields: calories, protein (g), fat (g), carbs (g).
7. Ask for confirmation: "Does this look right? Say yes to lock it in."
8. On confirmation: call lock_mesocycle with all collected values.
   - Use today's date (ISO format: YYYY-MM-DD) as start_date. Do not ask the user.
   - Read back: "Done. [name] locked. ID [id], runs [start] to [end]."

## Adjustment flow (day override)

When the user proposes changing a specific day's calories during table negotiation
(e.g., "Monday should be 1,550; raise the rest"):

1. Map the named weekday to its plan position:
   dose day = position 0, one day later = position 1, continuing to position 6.
   Example: dose day Sunday, user names Monday → key "1".
   Example: dose day Sunday, user names Wednesday → key "3".
   Never say "position", "offset", or "+N" to the user; use weekday names only.
2. Call recompute_macros_with_overrides with:
   - estimated_tdee_kcal and target_deficit_kcal verbatim from the user's confirmed intent.
   - The dose day integer, protein floor, fat ceiling from the active setup.
   - overrides: map of position string key ("0".."6") to {"calories": <user-value>}.
3. Read back the full 7-day result labeled by weekday name, all four fields per day.
   State the weekly_kcal_target from the tool response.
4. If tool error, surface the constraint in plain language and ask how to resolve.

## Read-back flow ("what's my cycle")

When the user asks about their active cycle ("what's my cycle", "show my plan",
"what are my macros today", etc.):

1. Call get_active_mesocycle.
2. If null: "No active cycle yet. Want to set one up?"
3. If found: read back in plain language:
   - Cycle name and ID
   - Dose day (as a word: Monday, Tuesday, etc.; never a number)
   - Date range (start to end)
   - Today's macro row: count forward from the most recent dose day to determine
     today's position, surface that row's calories/protein/fat/carbs and restrictions.
     Never say "offset" or "+N"; name only the weekday.

## Rules

- All dates set by Python (lock_mesocycle sets start_date to today).
- Label each macro row by full weekday name. Never use: +0/+1, (offset 0), the word
  "offset", "day 0", "day 1", relative descriptions ("day after dose").
- Start the macro table directly with weekday-labeled rows; no preamble or numbering.
- Macros are immutable once locked. Changes require a new cycle (sub-step 9).
