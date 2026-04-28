// Tool schema definitions for the nutriosv2-tools plugin.
// Each entry: { _script, _spawn, name, description, parameters }.
// _script and _spawn are internal fields used by index.js to build execute functions.
// The emit script (scripts/emit-schemas.js) strips them and renames parameters -> inputSchema.
export const TOOLS = [
  {
    _script: "get_daily_reconciled_view.py",
    _spawn: "argv",
    name: "get_daily_reconciled_view",
    description: "Return reconciled daily intake vs. mesocycle target for a user. Returns {target, consumed, remaining, is_expired, entries}. remaining is {calories, protein_g, fat_g, carbs_g} as integers; null when no active cycle.",
    parameters: {
      type: "object",
      properties: {
        user_id: { type: "integer", description: "Telegram user ID" },
        date: { type: "string", description: "ISO date (YYYY-MM-DD) in the user's local timezone" },
        active_timezone: { type: "string", description: "User's IANA timezone, e.g. 'America/Denver'" },
      },
      required: ["user_id", "date", "active_timezone"],
    },
  },
  {
    _script: "estimate_macros.py",
    _spawn: "argv",
    name: "estimate_macros_from_description",
    description: "Estimate calories, protein, fat, and carbs for a food description via LLM. Returns {calories, protein_g, fat_g, carbs_g, confidence}. confidence is 'high', 'medium', or 'low'.",
    parameters: {
      type: "object",
      properties: {
        description: { type: "string", description: "Natural-language food description, verbatim from the user" },
      },
      required: ["description"],
    },
  },
  {
    _script: "write_meal_log.py",
    _spawn: "argv",
    name: "write_meal_log",
    description: "Append a meal log entry for a user. Returns {log_id}.",
    parameters: {
      type: "object",
      properties: {
        user_id: { type: "integer", description: "Telegram user ID" },
        food_description: { type: "string", description: "What the user ate, verbatim" },
        macros: {
          type: "object",
          description: "Confirmed macro values",
          properties: {
            calories: { type: "integer" },
            protein_g: { type: "integer" },
            fat_g: { type: "integer" },
            carbs_g: { type: "integer" },
          },
          required: ["calories", "protein_g", "fat_g", "carbs_g"],
        },
        source: { type: "string", enum: ["recipe", "ad_hoc"], description: "Log source; use 'ad_hoc' for user-described meals" },
        active_timezone: { type: "string", description: "User's IANA timezone, e.g. 'America/Denver'" },
        recipe_id: { type: ["integer", "null"], description: "Required when source is 'recipe'; omit or null for ad_hoc" },
        recipe_name_snapshot: { type: ["string", "null"], description: "Recipe name at time of log; omit or null for ad_hoc" },
        supersedes_log_id: { type: ["integer", "null"], description: "Log ID this entry corrects; omit or null when not superseding" },
      },
      required: ["user_id", "food_description", "macros", "source", "active_timezone"],
    },
  },
  {
    _script: "compute_candidate_macros.py",
    _spawn: "argv",
    name: "compute_candidate_macros",
    description: "Compute candidate daily macros from a user's intent. Returns {weekly_deficit_kcal, daily_deficit_kcal, calories, protein_g, fat_g, carbs_g}. Any field may be null when the corresponding input is missing. Does not persist anything.",
    parameters: {
      type: "object",
      properties: {
        target_deficit_kcal: { type: ["integer", "null"], description: "Deficit value; unit determined by deficit_unit" },
        deficit_unit: { type: "string", enum: ["weekly_kcal", "daily_kcal"], default: "weekly_kcal", description: "Unit for target_deficit_kcal; omit to use weekly_kcal" },
        protein_floor_g: { type: ["integer", "null"], description: "Minimum daily protein in grams" },
        fat_ceiling_g: { type: ["integer", "null"], description: "Maximum daily fat in grams" },
        estimated_tdee_kcal: { type: ["integer", "null"], description: "Estimated total daily energy expenditure in kcal" },
      },
      required: [],
    },
  },
  {
    _script: "lock_mesocycle.py",
    _spawn: "argv",
    name: "lock_mesocycle",
    description: "Lock a new active mesocycle for a user. Ends any prior active cycle and writes the new one to disk. Returns {mesocycle_id, name, start_date, end_date}.",
    parameters: {
      type: "object",
      properties: {
        user_id: { type: "integer", description: "Telegram user ID" },
        name: { type: "string", description: "Cycle name, verbatim from user" },
        weeks: { type: "integer", description: "Cycle duration in weeks (>= 1)" },
        start_date: { type: "string", description: "ISO date (YYYY-MM-DD); use turn_state.today_date verbatim" },
        dose_weekday: { type: "integer", description: "Dose day as integer 0=Mon..6=Sun" },
        macro_table: {
          type: "array",
          description: "Exactly 7 macro rows, one per day starting from dose day",
          items: {
            type: "object",
            properties: {
              calories: { type: "integer" },
              protein_g: { type: "integer" },
              fat_g: { type: "integer" },
              carbs_g: { type: "integer" },
              restrictions: { type: "array", items: { type: "string" } },
            },
            required: ["calories", "protein_g", "fat_g", "carbs_g", "restrictions"],
          },
          minItems: 7,
          maxItems: 7,
        },
        intent: {
          type: "object",
          description: "User's confirmed intent values",
          properties: {
            target_deficit_kcal: { type: ["integer", "null"] },
            protein_floor_g: { type: ["integer", "null"] },
            fat_ceiling_g: { type: ["integer", "null"] },
            rationale: { type: "string" },
          },
          required: ["target_deficit_kcal", "protein_floor_g", "fat_ceiling_g", "rationale"],
        },
      },
      required: ["user_id", "name", "weeks", "start_date", "dose_weekday", "macro_table", "intent"],
    },
  },
  {
    _script: "get_active_mesocycle.py",
    _spawn: "argv",
    name: "get_active_mesocycle",
    description: "Return the active mesocycle for a user. Returns the full Mesocycle object {mesocycle_id, name, weeks, start_date, end_date, dose_weekday, macro_table, intent, status, created_at, ended_at}, or null if no active cycle.",
    parameters: {
      type: "object",
      properties: {
        user_id: { type: "integer", description: "Telegram user ID" },
      },
      required: ["user_id"],
    },
  },
  {
    _script: "recompute_macros_with_overrides.py",
    _spawn: "argv",
    name: "recompute_macros_with_overrides",
    description: "Redistribute a weekly kcal budget across 7 days given per-day calorie overrides. Call when the user proposes changing a specific day's calories during table negotiation. Returns {weekly_kcal_target, rows} where rows is 7 MacroRow objects (calories, protein_g, fat_g, carbs_g, restrictions) with redistributed values. Does not persist anything.",
    parameters: {
      type: "object",
      properties: {
        estimated_tdee_kcal: { type: "integer", description: "User's estimated total daily energy expenditure in kcal; verbatim from confirmed intent" },
        target_deficit_kcal: { type: "integer", description: "Weekly deficit in kcal; verbatim from confirmed intent" },
        dose_weekday: { type: "integer", description: "Dose day as integer 0=Mon..6=Sun" },
        protein_floor_g: { type: "integer", description: "Minimum daily protein in grams for non-overridden rows" },
        fat_ceiling_g: { type: "integer", description: "Maximum daily fat in grams for non-overridden rows" },
        overrides: {
          type: "object",
          description: "Map of plan-position string key ('0'..'6') to row override.",
          additionalProperties: {
            type: "object",
            properties: {
              calories:  { type: "integer" },
              protein_g: { type: "integer" },
              fat_g:     { type: "integer" },
            },
            required: ["calories"],
          },
        },
      },
      required: ["estimated_tdee_kcal", "target_deficit_kcal", "dose_weekday", "protein_floor_g", "fat_ceiling_g", "overrides"],
    },
  },
  {
    _script: "turn_state.py",
    _spawn: "stdin",
    name: "turn_state",
    description: "Call first on every user turn. Classifies intent, detects intent-transition boundary, and returns the routed capability prompt read fresh from disk. Returns {intent, ambiguous, boundary, capability_prompt, today_date}.",
    parameters: {
      type: "object",
      properties: {
        user_message: { type: "string", description: "Verbatim text the user sent" },
        user_id: { type: "integer", description: "Telegram user ID" },
        intent_override: {
          type: "string",
          enum: ["mesocycle_setup", "cycle_read_back", "meal_log", "today_view", "default"],
          description: "Skip classifier and force this intent. Used for slash command dispatch.",
        },
      },
      required: ["user_message", "user_id"],
    },
  },
];
