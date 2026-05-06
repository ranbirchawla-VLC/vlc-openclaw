/**
 * otel-helpers.js -- OTEL wrapping utilities for gtd-tools plugin.
 *
 * Exported so unit tests can import helpers without requiring the OpenClaw
 * plugin SDK. index.js imports from here.
 */
import { randomBytes } from "crypto";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { trace, context, propagation, SpanStatusCode } from "@opentelemetry/api";

const __pluginDir = dirname(fileURLToPath(import.meta.url));
const __workspaceDir = dirname(dirname(__pluginDir));

export const PYTHON =
  process.env.OPENCLAW_PYTHON_BIN ||
  join(__workspaceDir, ".venv", "bin", "python");

export const SCRIPTS = join(__workspaceDir, "gtd-workspace", "scripts");

export const PLUGIN_TRACER = "gtd-tools";

export const SPAWN_ENV = {
  OTEL_SERVICE_NAME: PLUGIN_TRACER,
  OTEL_EXPORTER_OTLP_ENDPOINT:
    process.env.OTEL_EXPORTER_OTLP_ENDPOINT || "http://localhost:4318",
  OTEL_EXPORTER_OTLP_PROTOCOL:
    process.env.OTEL_EXPORTER_OTLP_PROTOCOL || "http/protobuf",
};

/** Extract W3C traceparent from the active OTel context.
 *  Falls back to randomly-generated root if no SDK is registered (tests, pre-init). */
export function activeTraceparent() {
  const carrier = {};
  propagation.inject(context.active(), carrier);
  if (carrier.traceparent) return carrier.traceparent;
  const traceId = randomBytes(16).toString("hex");
  const parentId = randomBytes(8).toString("hex");
  return `00-${traceId}-${parentId}-01`;
}

/**
 * Produce a tool result from spawnSync output.
 * Sets span status and error attributes on failure per span contract v1.
 * Never includes user content (params values) in span attributes.
 *
 * error.code vocabulary (locked):
 *   subprocess_spawn_error  -- result.error set (OS-level spawn failure)
 *   subprocess_nonzero_exit -- status !== 0 or empty stdout
 *   output_parse_failure    -- JSON.parse(stdout) throws
 */
export function toToolResult(result, span, toolName) {
  if (result.error) {
    span.setStatus({ code: SpanStatusCode.ERROR, message: "subprocess spawn error" });
    span.setAttributes({
      "error.type": "subprocess_spawn_error",
      "error.code": "subprocess_spawn_error",
      "error.location": toolName,
      "error.context": result.error.code ?? "spawn_failed",
    });
    return {
      content: [{ type: "text", text: JSON.stringify({ ok: false, error: result.error.message }) }],
    };
  }

  const stdout = (result.stdout ?? "").trim();
  if (result.status !== 0 || !stdout) {
    const stderr = (result.stderr ?? "").trim();
    span.setStatus({ code: SpanStatusCode.ERROR, message: stderr || "script exited non-zero" });
    span.setAttributes({
      "error.type": "subprocess_nonzero_exit",
      "error.code": "subprocess_nonzero_exit",
      "error.location": toolName,
      "error.context": `status=${result.status}`,
    });
    return {
      content: [{ type: "text", text: JSON.stringify({ ok: false, error: stderr || "script exited non-zero", status: result.status }) }],
    };
  }

  let parsed;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    span.setStatus({ code: SpanStatusCode.ERROR, message: "failed to parse script output" });
    span.setAttributes({
      "error.type": "output_parse_failure",
      "error.code": "output_parse_failure",
      "error.location": toolName,
      "error.context": `stdout_length=${stdout.length}`,
    });
    return {
      content: [{ type: "text", text: JSON.stringify({ ok: false, error: "failed to parse script output", raw: stdout.slice(0, 500) }) }],
    };
  }

  return { content: [{ type: "text", text: JSON.stringify(parsed) }] };
}

/**
 * Execute a plugin tool with OTEL startActiveSpan wrapping.
 * spawnFn: (params, extraEnv) => spawnSync result.
 * Injects TRACEPARENT into subprocess env from the active span context.
 */
export function executeWithSpan(tracer, toolName, spawnFn, params) {
  return tracer.startActiveSpan(`gtd.tool.${toolName}`, (span) => {
    span.setAttributes({
      "tool.name": toolName,
      "agent.id": "gtd",
      "plugin.name": "gtd-tools",
    });
    try {
      const result = spawnFn(params, { TRACEPARENT: activeTraceparent() });
      return toToolResult(result, span, toolName);
    } finally {
      span.end();
    }
  });
}
