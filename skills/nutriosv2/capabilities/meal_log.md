# Capability: Meal Log

Handles Capability 3 — logging what the user ate.

## Voice rules

Cross-cutting rules (zero arithmetic, no process narration, verbatim readback)
live in the vlc-openclaw CLAUDE.md "LLM voice rules" section.
Apply them without restatement. Read tool-returned values verbatim; produce no
values, dates, or structural facts in your own composition.

## Flow

When the user describes a meal or asks to log food:

1. Confirm what they ate (restate their description so they can correct it).
2. Ask for the macros in one message: "And the macros? I need calories, protein (g),
   fat (g), and carbs (g)."
3. Once you have all four values, call write_meal_log with:
   - user_id: the user's Telegram ID
   - food_description: what the user described, verbatim
   - macros: {"calories": <int>, "protein_g": <int>, "fat_g": <int>, "carbs_g": <int>}
   - source: "ad_hoc"
   - recipe_id: null
   - recipe_name_snapshot: null
   - supersedes_log_id: null
   - active_timezone: "America/Denver"
4. Read back: "[food_description] logged. [calories] cal, [protein_g]g protein,
   [fat_g]g fat, [carbs_g]g carbs. Log [log_id]."

## Rules

- Never estimate or infer macros. If the user has not provided all four values, ask.
- Read all macro values from the tool result verbatim.
- source is always "ad_hoc" for user-described meals.
- If write_meal_log returns an error, surface it in plain language and ask the user
  to confirm whether to retry.
