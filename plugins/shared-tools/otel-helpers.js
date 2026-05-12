/**
 * otel-helpers.js -- OTEL wrapping utilities for shared-tools plugin.
 *
 * Exported so unit tests can import helpers without requiring the OpenClaw
 * plugin SDK. index.js imports from here.
 *
 * resolveTZ is exported as a pure function for direct test injection
 * (no fs mock needed; tests pass a temp dir path).
 */
import { randomBytes } from "crypto";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { homedir } from "os";
import { context, propagation, SpanStatusCode } from "@opentelemetry/api";

const __pluginDir = dirname(fileURLToPath(import.meta.url));
const __workspaceDir = dirname(dirname(__pluginDir));

export const PYTHON =
  process.env.OPENCLAW_PYTHON_BIN || "python3";

export const SCRIPTS = join(__workspaceDir, "scripts", "shared");

export const PLUGIN_TRACER = "shared-tools";

export const SPAWN_ENV = {
  OTEL_SERVICE_NAME: PLUGIN_TRACER,
  OTEL_EXPORTER_OTLP_ENDPOINT:
    process.env.OTEL_EXPORTER_OTLP_ENDPOINT || "http://localhost:4318",
  OTEL_EXPORTER_OTLP_PROTOCOL:
    process.env.OTEL_EXPORTER_OTLP_PROTOCOL || "http/protobuf",
};

/** Extract W3C traceparent from the active OTel context.
 *  Falls back to randomly-generated root if no SDK is registered. */
export function activeTraceparent() {
  const carrier = {};
  propagation.inject(context.active(), carrier);
  if (carrier.traceparent) return carrier.traceparent;
  const traceId = randomBytes(16).toString("hex");
  const parentId = randomBytes(8).toString("hex");
  return `00-${traceId}-${parentId}-01`;
}

/**
 * Resolve timezone for the request.
 * Reads profile.json from agentDataPath/<user_id>/profile.json when user_id is present.
 * Falls back to defaultTz (or America/Denver) when profile is absent or has no timezone field.
 *
 * Pure function; exported for direct test injection without mocking fs.
 */
export function resolveTZ(params, agentDataPath, defaultTz) {
  const fallback = { tz: defaultTz ?? "America/Denver", tzSource: "fallback" };
  if (!params.user_id || !agentDataPath) return fallback;
  const profilePath = join(agentDataPath, String(params.user_id), "profile.json");
  try {
    const profile = JSON.parse(readFileSync(profilePath, "utf8"));
    if (profile.timezone) return { tz: profile.timezone, tzSource: "profile" };
  } catch {
    // profile missing or unreadable; use fallback
  }
  return fallback;
}

/**
 * Produce a tool result from spawnSync output.
 * Sets span status and error attributes on failure per span contract v1.
 * Never includes user content (params values) in span attributes.
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
 * extraAttrs: additional span attributes (e.g. tz, tz_source).
 * Injects TRACEPARENT into subprocess env from the active span context.
 * Span named: shared-tools.tool.<toolName>
 */
export function executeWithSpan(tracer, toolName, spawnFn, params, extraAttrs = {}) {
  return tracer.startActiveSpan(`shared-tools.tool.${toolName}`, (span) => {
    span.setAttributes({
      "tool.name": toolName,
      "plugin.name": "shared-tools",
      ...extraAttrs,
    });
    try {
      const result = spawnFn(params, { TRACEPARENT: activeTraceparent() });
      return toToolResult(result, span, toolName);
    } finally {
      span.end();
    }
  });
}
