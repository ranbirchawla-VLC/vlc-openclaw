import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { spawnSync } from "child_process";
import { randomBytes } from "crypto";
import { trace, context, propagation } from "@opentelemetry/api";

const PYTHON = "/Users/ranbirchawla/.pyenv/versions/3.12.10/bin/python3.12";
const SCRIPTS = "/Users/ranbirchawla/ai-code/vlc-openclaw/skills/grailzee-eval/scripts";

// ingest_sales.py refuses to run without GRAILZEE_ROOT explicitly set.
// The gateway process does not inherit shell env vars, so inject it here.
// All values fall back to their defaults if already set in the gateway env.
const GRAILZEE_ROOT = process.env.GRAILZEE_ROOT ||
  "/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Shared Drive/GrailzeeData";

const OTEL_EXPORTER_OTLP_ENDPOINT = process.env.OTEL_EXPORTER_OTLP_ENDPOINT || "http://localhost:4318";
const OTEL_EXPORTER_OTLP_PROTOCOL = process.env.OTEL_EXPORTER_OTLP_PROTOCOL || "http/protobuf";
const OTEL_SERVICE_NAME = process.env.OTEL_SERVICE_NAME || "grailzee-eval-tools";

const SPAWN_ENV = {
  ...process.env,
  GRAILZEE_ROOT,
  OTEL_EXPORTER_OTLP_ENDPOINT,
  OTEL_EXPORTER_OTLP_PROTOCOL,
  OTEL_SERVICE_NAME,
};

// Extract W3C traceparent from the active OTel context. Falls back to a
// randomly-generated root if no SDK is registered (e.g. during tests).
function activeTraceparent() {
  const carrier = {};
  propagation.inject(context.active(), carrier);
  if (carrier.traceparent) return carrier.traceparent;
  const traceId = randomBytes(16).toString("hex");
  const parentId = randomBytes(8).toString("hex");
  return `00-${traceId}-${parentId}-01`;
}

const GRAILZEE_TRACER = "grailzee-eval-tools";

function spawnArgv(script, params, extraEnv = {}) {
  return spawnSync(
    PYTHON,
    [`${SCRIPTS}/${script}`, JSON.stringify(params)],
    { encoding: "utf8", env: { ...SPAWN_ENV, ...extraEnv } }
  );
}

function spawnStdin(script, params, extraEnv = {}) {
  return spawnSync(
    PYTHON,
    [`${SCRIPTS}/${script}`],
    { encoding: "utf8", input: JSON.stringify(params), env: { ...SPAWN_ENV, ...extraEnv } }
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
      execute(_id, params) {
        return trace.getTracer(GRAILZEE_TRACER).startActiveSpan("grailzee.tool.evaluate_deal", (span) => {
          span.setAttributes({
            "tool.name": "evaluate_deal",
            "grailzee.brand": params.brand ?? "",
            "grailzee.reference": params.reference ?? "",
          });
          const result = toToolResult(spawnArgv("evaluate_deal.py", params, { TRACEPARENT: activeTraceparent() }));
          span.end();
          return result;
        });
      },
    });

    api.registerTool({
      name: "report_pipeline",
      description: "Ingest the latest Grailzee Pro .xlsx report, run analysis, and write the analysis cache. Takes no required inputs; all path overrides are optional test hooks.",
      parameters: {
        type: "object",
        properties: {},
        required: [],
      },
      execute(_id, params) {
        return trace.getTracer(GRAILZEE_TRACER).startActiveSpan("grailzee.tool.report_pipeline", (span) => {
          span.setAttributes({ "tool.name": "report_pipeline" });
          const result = toToolResult(spawnArgv("report_pipeline.py", params, { TRACEPARENT: activeTraceparent() }));
          span.end();
          return result;
        });
      },
    });

    api.registerTool({
      name: "ingest_sales",
      description: "Run one ledger ingest cycle: scan sales_data/ for WatchTrack JSONL batches, transform, merge, prune, write, and archive. Takes no required inputs; all path overrides are optional test hooks.",
      parameters: {
        type: "object",
        properties: {},
        required: [],
      },
      execute(_id, params) {
        return trace.getTracer(GRAILZEE_TRACER).startActiveSpan("grailzee.tool.ingest_sales", (span) => {
          span.setAttributes({ "tool.name": "ingest_sales" });
          const result = toToolResult(spawnArgv("ingest_sales.py", params, { TRACEPARENT: activeTraceparent() }));
          span.end();
          return result;
        });
      },
    });

    api.registerTool({
      name: "turn_state",
      description: "Call first on every user turn. Classifies intent and returns the capability instructions for this turn. Returns {intent, capability_prompt}. Follow capability_prompt exactly.",
      parameters: {
        type: "object",
        properties: {
          user_message: {
            type: "string",
            description: "Verbatim text the operator sent",
          },
        },
        required: ["user_message"],
      },
      execute(_id, params) {
        return trace.getTracer(GRAILZEE_TRACER).startActiveSpan("grailzee.tool.turn_state", (span) => {
          span.setAttributes({ "tool.name": "turn_state" });
          const result = toToolResult(spawnStdin("turn_state.py", params, { TRACEPARENT: activeTraceparent() }));
          span.end();
          return result;
        });
      },
    });
  },
});
