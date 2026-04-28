import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { spawnSync } from "child_process";

const PYTHON = "/Users/ranbirchawla/.openclaw/workspace/.venv/bin/python";
const SCRIPTS = "/Users/ranbirchawla/.openclaw/workspace/skills/nutriosv2/scripts";

function spawnArgv(script, params) {
  return spawnSync(
    PYTHON,
    [`${SCRIPTS}/${script}`, JSON.stringify(params)],
    { encoding: "utf8", env: { ...process.env } }
  );
}

function spawnStdin(script, params) {
  return spawnSync(
    PYTHON,
    [`${SCRIPTS}/${script}`],
    { encoding: "utf8", input: JSON.stringify(params), env: { ...process.env } }
  );
}

function toToolResult(result) {
  if (result.error) {
    return { content: [{ type: "text", text: JSON.stringify({ ok: false, error: result.error.message }) }] };
  }
  const stdout = (result.stdout ?? "").trim();
  if (result.status !== 0 || !stdout) {
    const stderr = (result.stderr ?? "").trim();
    return { content: [{ type: "text", text: JSON.stringify({ ok: false, error: stderr || "script exited non-zero", status: result.status }) }] };
  }
  let parsed;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    return { content: [{ type: "text", text: JSON.stringify({ ok: false, error: "failed to parse script output", raw: stdout.slice(0, 500) }) }] };
  }
  return { content: [{ type: "text", text: JSON.stringify(parsed) }] };
}

export default definePluginEntry({
  id: "nutriosv2-tools",
  name: "NutriOS v2 Tools",
  description: "Custom tools for the NutriOS v2 agent",
  register(api) {
    api.registerTool({
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
      async execute(_id, params) {
        return toToolResult(spawnArgv("get_daily_reconciled_view.py", params));
      },
    });

    api.registerTool({
      name: "estimate_macros_from_description",
      description: "Estimate calories, protein, fat, and carbs for a food description via LLM. Returns {calories, protein_g, fat_g, carbs_g, confidence}. confidence is 'high', 'medium', or 'low'.",
      parameters: {
        type: "object",
        properties: {
          description: { type: "string", description: "Natural-language food description, verbatim from the user" },
        },
        required: ["description"],
      },
      async execute(_id, params) {
        return toToolResult(spawnArgv("estimate_macros.py", params));
      },
    });

    api.registerTool({
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
      async execute(_id, params) {
        return toToolResult(spawnArgv("write_meal_log.py", params));
      },
    });

    api.registerTool({
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
      async execute(_id, params) {
        return toToolResult(spawnStdin("turn_state.py", params));
      },
    });
  },
});
