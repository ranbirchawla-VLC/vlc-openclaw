# Capability: Today View

Handles Capability 4 (today path): user asks what they have eaten or what remains today.

## Voice rules

Cross-cutting rules (zero arithmetic, no process narration, verbatim readback)
live in the vlc-openclaw CLAUDE.md "LLM voice rules" section.
Apply them without restatement. Read tool-returned values verbatim; produce no
values, dates, or structural facts in your own composition.

## Flow

**Step 1: Fetch today's data.**

Call `get_daily_reconciled_view` with:
- `user_id`: the user's Telegram ID
- `date`: the `today_date` value from the `turn_state` result (YYYY-MM-DD format)
- `active_timezone`: `"America/Denver"`

**Step 2: Read back verbatim.**

**No active cycle** (`target` is `null`):
> "No active cycle. Want to set one up?"

Stop here. Do not auto-route to setup.

**Expired cycle** (`is_expired` is `true`):

Prefix the normal read-back with one line:
> "Your cycle has expired."

Then show entries and summary exactly as the active-cycle path below.

**Active cycle; entries present:**

List each entry on its own line using the `entries` array from the tool result:
> [food_description]: [macros.calories] cal, [macros.protein_g]g p, [macros.fat_g]g f, [macros.carbs_g]g c

Then on the next line, the summary:
> Target: [target.calories] cal / [target.protein_g]g p / [target.fat_g]g f / [target.carbs_g]g c. Consumed: [consumed.calories] cal / [consumed.protein_g]g p / [consumed.fat_g]g f / [consumed.carbs_g]g c. Remaining: [remaining.calories] cal / [remaining.protein_g]g p / [remaining.fat_g]g f / [remaining.carbs_g]g c.

**Active cycle; no entries (empty day):**
> Nothing logged yet.

Then the summary line in the same format (consumed will be 0 across all fields; remaining will match target).

Read-back is a plain text block. Do not call the `message` tool. Do not add inline buttons.

## HARD RULES

- Call `get_daily_reconciled_view` exactly once.
- Pass `today_date` from the `turn_state` result verbatim as the `date` argument. Do not compute or derive the date.
- Read all values verbatim from the tool result. Zero arithmetic, zero substitution.
- `remaining` is computed by the tool; read it back as returned, never derive it yourself.
- Do not describe the tool, the lookup, or how the date was determined.
- Do not round or reformat any numeric value.
