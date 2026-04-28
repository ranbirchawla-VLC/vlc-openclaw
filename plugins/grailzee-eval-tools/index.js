import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { spawnSync } from "child_process";

const PYTHON = "/Users/ranbirchawla/.pyenv/versions/3.12.10/bin/python3.12";
const SCRIPTS = "/Users/ranbirchawla/ai-code/vlc-openclaw/skills/grailzee-eval/scripts";

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
  id: "grailzee-eval-tools",
  name: "Grailzee Eval Tools",
  description: "Deal evaluation and cycle reporting tools for the Grailzee agent",
  register(api) {
    api.registerTool({
      name: "evaluate_deal",
      description: "Evaluate a deal against the Grailzee bucket cache and cycle plan. Returns a yes/no buy decision with pricing math visible.",
      parameters: {
        type: "object",
        properties: {
          brand: {
            type: "string",
            description: "Watch brand, verbatim from the deal post (e.g. 'Tudor', 'Rolex'). Case-insensitive on the script side.",
          },
          reference: {
            type: "string",
            description: "Reference number, verbatim from the deal post (e.g. '79830RB', '116610LN'). Case-sensitive on the script side.",
          },
          listing_price: {
            type: "string",
            description: "Asking price as a USD amount. $ and commas are accepted (e.g. '$3,500', '3500', '3,500.00'). Stripped and parsed by the script.",
          },
          dial_numerals: {
            type: "string",
            enum: ["Arabic", "Roman", "Stick", "No Numerals"],
            description: "Dial numeral style if known. Omit when the deal post does not specify; treated as wildcard.",
          },
          auction_type: {
            type: "string",
            enum: ["NR", "RES"],
            description: "Auction type if known. NR = no reserve, RES = reserve. Omit when not specified; treated as wildcard.",
          },
          dial_color: {
            type: "string",
            description: "Dial color if known (e.g. 'black', 'blue', 'green'). Free-form string, lowercased server-side. Omit when not specified; treated as wildcard.",
          },
        },
        required: ["brand", "reference", "listing_price"],
      },
      async execute(_id, params) {
        return toToolResult(spawnStdin("evaluate_deal.py", params));
      },
    });
  },
});
