# Capability: Meal Log

Handles Capability 3: logging what the user ate (ad-hoc path).

## Voice rules

Cross-cutting rules (zero arithmetic, no process narration, verbatim readback)
live in the vlc-openclaw CLAUDE.md "LLM voice rules" section.
Apply them without restatement. Read tool-returned values verbatim; produce no
values, dates, or structural facts in your own composition.

## Flow

When the user describes food they ate, go to Step 2a.
When the user's message already includes all four macro values (calories, protein,
fat, carbs) explicitly, skip Step 2a. Use the user-supplied values verbatim and go
directly to Step 2b to confirm them.
When the user's message is a button response (Yes / No / Change) or a correction
("the carbs are 45", "change protein to 2"), continue the confirm flow from wherever
it was; do not restart estimation.

<!-- BEGIN ADAPTED EMBED: capabilities/_shared/confirm_macros.md
     Adaptations: step numbers renamed for local continuity; terminal "calling capability
     owns" paragraph replaced by Step 3 reference.
     Update discipline: when confirm_macros.md changes, diff and apply here. -->

**Step 2a.** Call `estimate_macros_from_description` with the description verbatim. One
call per food item only.

**Step 2b.** Call the `message` tool with the macro values (from the estimator in Step 2a, or from the user's message when all four were supplied explicitly):
- `message`: "[food_description]: [calories] cal, [protein_g]g protein, [fat_g]g fat, [carbs_g]g carbs. Does that look right?"
- `buttons`: `[[{"text": "Yes", "callback_data": "confirm_yes"}, {"text": "No", "callback_data": "confirm_no"}, {"text": "Change", "callback_data": "confirm_change"}]]`

Your text block must be `NO_REPLY`. Do not produce any other text in this turn.
Stop here. Do not generate any text for the Yes, No, or Change paths in this turn.

**When the user responds:**

- "Yes" / "confirm_yes" / "looks good" / "correct" / "right": proceed to Step 3.

- "No" / "confirm_no": ask in one message: "What are the macros? I need calories,
  protein (g), fat (g), and carbs (g)." Wait. Confirmed macros = user-supplied values
  verbatim. Proceed to Step 3.

- "Change" / "confirm_change" / user directly states a correction:
  Apply the stated change to exactly one field. All other fields from the estimator
  result unchanged. Do not recompute any other field.
  Call the `message` tool with updated values and buttons (same format as Step 2b).
  Text block must be `NO_REPLY`. Stop.

## HARD RULES (confirm_macros embed)

- Call `estimate_macros_from_description` exactly once per food item.
- Read all values verbatim; zero arithmetic, zero substitution.
- Rounding rule: user-facing readback shows estimator values as returned. Tool call
  args in Step 3 must be integers; round protein_g, fat_g, carbs_g only when building
  the tool call, not before.
- After Step 2b buttons: stop. Do not generate text for future branches in the same turn.
- On Change: change exactly one field; all others from the estimator result unchanged.
- Do not narrate the estimation process or describe the tool.

<!-- END ADAPTED EMBED -->

**Step 3: Write the log entry.** Once macros are confirmed, call `write_meal_log` with:
- `user_id`: the user's Telegram ID
- `food_description`: what the user described, verbatim
- `macros`: `{"calories": <int>, "protein_g": <int>, "fat_g": <int>, "carbs_g": <int>}`
- `source`: `"ad_hoc"`
- `recipe_id`: `null`
- `recipe_name_snapshot`: `null`
- `supersedes_log_id`: `null`
- `active_timezone`: `"America/Denver"`

**Step 4: Today's remaining.** Call `get_daily_reconciled_view` with:
- `user_id`: the user's Telegram ID
- `date`: today's date in America/Denver (YYYY-MM-DD format)
- `active_timezone`: `"America/Denver"`

**Step 5: Read back** verbatim from the tool results:
> "Logged [food_description] (log [log_id]). Remaining today: [remaining.calories] cal,
> [remaining.protein_g]g protein, [remaining.fat_g]g fat, [remaining.carbs_g]g carbs."

If `remaining` is `null` (no active cycle):
> "Logged [food_description] (log [log_id])."

## RULES

- Do not call write_meal_log before macros are confirmed.
- If estimate_macros_from_description returns an error: "Sorry, I couldn't estimate
  macros for that right now. What are the calories, protein (g), fat (g), and carbs (g)?"
  Take the user's values and proceed to Step 3. Do not describe the error.
- If write_meal_log returns an error, surface it in plain language and ask whether to retry.
- `source` is always `"ad_hoc"` for user-described meals in this flow.
