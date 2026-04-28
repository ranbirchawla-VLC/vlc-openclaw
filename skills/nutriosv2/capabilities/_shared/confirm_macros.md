# Shared sub-flow: confirm_macros

<!-- INCLUSION CONVENTION
This file is a shared sub-flow snippet, not a standalone capability.
The capability prompt loader (scripts/turn_state.py) has no dynamic include mechanism.
Callers embed this snippet content with an adapted header; the embed is NOT verbatim.

Permitted adaptations when embedding:
- Rename step numbers for local continuity (e.g. Step 1 becomes Step 2a in a larger flow).
- Replace "Proceed to what the calling capability does next" with a specific step reference.
- Drop the "Confirmed macros are now in conversation context" terminal paragraph; callers own that.
- Retitle the HARD RULES section to distinguish it from other HARD RULES in the same file.

When this file changes, update every embedding manually:
  - capabilities/meal_log.md
  - capabilities/recipe_build.md (sub-step 4; not yet built)
Diff the embed against this source and apply each change; the step-number adaptation is the
only intentional divergence.
-->

<!-- BEGIN confirm_macros -->
## Confirm macros sub-flow

Fires when you have a food description and need macros confirmed before any write.

**Step 1.** Call `estimate_macros_from_description` with the description verbatim. One
call per food item only.

**Step 2.** After the tool returns, call the `message` tool with:
- `message`: "[food_description]: [calories] cal, [protein_g]g protein, [fat_g]g fat, [carbs_g]g carbs. Does that look right?"
- `buttons`: `[[{"text": "Yes", "callback_data": "confirm_yes"}, {"text": "No", "callback_data": "confirm_no"}, {"text": "Change", "callback_data": "confirm_change"}]]`

Your text block must be `NO_REPLY`. Stop. Do not generate any text for Yes, No, or
Change paths in this turn — those are handled when the user responds.

**When the user responds:**

- "Yes" / "confirm_yes" / "looks good" / "correct" / "right": confirmed macros are
  the estimator output unchanged. Proceed to what the calling capability does next.

- "No" / "confirm_no" / "wrong" / "that's off": ask in one message:
  "What are the macros? I need calories, protein (g), fat (g), and carbs (g)."
  Wait for the user's reply. Confirmed macros are those user-supplied values verbatim.
  Proceed to next.

- "Change" / "confirm_change" / or user directly states a correction
  (e.g. "the carbs are 45", "change protein to 2"):
  Apply the stated change to exactly one field. All other fields remain from the
  estimator result verbatim. Do not recompute any other field.
  Call the `message` tool again with the updated values and buttons (same format as
  Step 2). Text block must be `NO_REPLY`. Stop. Wait for the user's confirmation.

## HARD RULES

- Call `estimate_macros_from_description` exactly once per food item.
- Read all values verbatim; zero arithmetic, zero rounding, zero substitution.
- After Step 2 message tool call: stop. Do not generate text for future branches in this turn.
- On Change: change exactly one field; all others are unchanged from the estimator result.
- Do not narrate the estimation process or describe the tool.
<!-- END confirm_macros -->
