import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { spawnSync } from "child_process";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { TOOLS } from "./tool-schemas.js";

const __pluginDir = dirname(fileURLToPath(import.meta.url));
const __workspaceDir = dirname(dirname(__pluginDir));  // plugins/gtd-tools/ -> plugins/ -> workspace/

// OPENCLAW_PYTHON_BIN overrides the workspace .venv default for non-standard installs.
const PYTHON = process.env.OPENCLAW_PYTHON_BIN || join(__workspaceDir, ".venv", "bin", "python");
const SCRIPTS = join(__workspaceDir, "gtd-workspace", "scripts", "calendar");

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
  id: "gtd-tools",
  name: "GTD Tools",
  description: "Custom tools for the GTD agent",
  register(api) {
    for (const { _script, _spawn, ...schema } of TOOLS) {
      const spawn = _spawn === "stdin" ? spawnStdin : spawnArgv;
      api.registerTool({
        ...schema,
        async execute(_id, params) {
          return toToolResult(spawn(_script, params));
        },
      });
    }
  },
});
