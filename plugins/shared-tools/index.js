import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { spawnSync } from "child_process";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { trace } from "@opentelemetry/api";
import { TOOLS } from "./tool-schemas.js";
import {
  PYTHON,
  SCRIPTS,
  PLUGIN_TRACER,
  SPAWN_ENV,
  executeWithSpan,
  resolveTZ,
} from "./otel-helpers.js";

const __pluginDir = dirname(fileURLToPath(import.meta.url));

function loadAgentSettings() {
  try {
    return JSON.parse(readFileSync(join(__pluginDir, "agent-settings.json"), "utf8"));
  } catch {
    return {};
  }
}

const _AGENT_SETTINGS = loadAgentSettings();

function spawnArgv(script, params, extraEnv = {}) {
  return spawnSync(
    PYTHON,
    [`${SCRIPTS}/${script}`, JSON.stringify(params)],
    { encoding: "utf8", env: { ...process.env, ...SPAWN_ENV, ...extraEnv } }
  );
}

export default definePluginEntry({
  id: "shared-tools",
  name: "Shared Tools",
  description: "Cross-agent utility tools (get_today_date, etc.)",
  register(api) {
    for (const { _script, _spawn, ...schema } of TOOLS) {
      api.registerTool((ctx) => ({
        ...schema,
        async execute(_id, params) {
          const agentId = ctx.agentId ?? "unknown";
          const s = _AGENT_SETTINGS[agentId] ?? {};
          const { tz, tzSource } = resolveTZ(params, s.agent_data_path, s.default_timezone);
          return executeWithSpan(
            trace.getTracer(PLUGIN_TRACER),
            schema.name,
            (p, extraEnv) => spawnArgv(_script, p, { ...extraEnv, GTD_TZ: tz }),
            params,
            { tz, tz_source: tzSource, agent_id: agentId }
          );
        },
      }));
    }
  },
});
