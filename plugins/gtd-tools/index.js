import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { spawnSync } from "child_process";
import { trace } from "@opentelemetry/api";
import { TOOLS } from "./tool-schemas.js";
import {
  PYTHON,
  SCRIPTS,
  PLUGIN_TRACER,
  SPAWN_ENV,
  executeWithSpan,
} from "./otel-helpers.js";

function spawnArgv(script, params, extraEnv = {}) {
  return spawnSync(
    PYTHON,
    [`${SCRIPTS}/${script}`, JSON.stringify(params)],
    { encoding: "utf8", env: { ...process.env, ...SPAWN_ENV, ...extraEnv } }
  );
}

function spawnStdin(script, params, extraEnv = {}) {
  return spawnSync(
    PYTHON,
    [`${SCRIPTS}/${script}`],
    { encoding: "utf8", input: JSON.stringify(params), env: { ...process.env, ...SPAWN_ENV, ...extraEnv } }
  );
}

export default definePluginEntry({
  id: "gtd-tools",
  name: "GTD Tools",
  description: "Custom tools for the GTD agent",
  register(api) {
    for (const { _script, _spawn, ...schema } of TOOLS) {
      const spawnFn = _spawn === "stdin"
        ? (params, extraEnv) => spawnStdin(_script, params, extraEnv)
        : (params, extraEnv) => spawnArgv(_script, params, extraEnv);
      api.registerTool({
        ...schema,
        async execute(_id, params) {
          return executeWithSpan(
            trace.getTracer(PLUGIN_TRACER),
            schema.name,
            spawnFn,
            params
          );
        },
      });
    }
  },
});
