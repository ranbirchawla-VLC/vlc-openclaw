/**
 * test_index.js -- JS unit tests for shared-tools plugin.
 *
 * TDD: written before otel-helpers.js and confirmed RED.
 *
 * Uses node:test (built-in) + @opentelemetry/sdk-trace-base InMemorySpanExporter.
 * Run: node --test tests/
 */
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { mkdirSync, writeFileSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import {
  BasicTracerProvider,
  InMemorySpanExporter,
  SimpleSpanProcessor,
} from "@opentelemetry/sdk-trace-base";
import { trace, SpanStatusCode } from "@opentelemetry/api";
import {
  SPAWN_ENV,
  PLUGIN_TRACER,
  executeWithSpan,
  resolveTZ,
} from "../otel-helpers.js";

// ---------------------------------------------------------------------------
// Provider setup (once for the file)
// ---------------------------------------------------------------------------

let exporter;
let provider;

before(() => {
  exporter = new InMemorySpanExporter();
  provider = new BasicTracerProvider();
  provider.addSpanProcessor(new SimpleSpanProcessor(exporter));
  provider.register();
});

after(() => {
  provider.shutdown();
});

function freshSpans() {
  exporter.reset();
  return exporter;
}

// ---------------------------------------------------------------------------
// Test 1: resolveTZ -- profile.json exists and has timezone field
// ---------------------------------------------------------------------------

test("1: resolveTZ returns profile.timezone when profile.json exists", () => {
  const tempDir = join(tmpdir(), `shared-tools-test-${Date.now()}`);
  const userId = "12345";
  mkdirSync(join(tempDir, userId), { recursive: true });
  writeFileSync(join(tempDir, userId, "profile.json"), JSON.stringify({ timezone: "Europe/Berlin" }));

  const { tz, tzSource } = resolveTZ({ user_id: userId }, tempDir, "America/Denver");

  rmSync(tempDir, { recursive: true });

  assert.equal(tz, "Europe/Berlin");
  assert.equal(tzSource, "profile");
});

// ---------------------------------------------------------------------------
// Test 2: resolveTZ -- profile.json missing; returns fallback
// ---------------------------------------------------------------------------

test("2: resolveTZ returns fallback when profile.json is missing", () => {
  const tempDir = join(tmpdir(), `shared-tools-test-${Date.now()}-missing`);
  const { tz, tzSource } = resolveTZ({ user_id: "99999" }, tempDir, "America/Chicago");
  assert.equal(tz, "America/Chicago");
  assert.equal(tzSource, "fallback");
});

// ---------------------------------------------------------------------------
// Test 3: resolveTZ -- profile.json exists but no timezone field
// ---------------------------------------------------------------------------

test("3: resolveTZ returns fallback when profile.json has no timezone field", () => {
  const tempDir = join(tmpdir(), `shared-tools-test-${Date.now()}-notimezone`);
  const userId = "55555";
  mkdirSync(join(tempDir, userId), { recursive: true });
  writeFileSync(join(tempDir, userId, "profile.json"), JSON.stringify({ name: "ranbir" }));

  const { tz, tzSource } = resolveTZ({ user_id: userId }, tempDir, "America/Denver");

  rmSync(tempDir, { recursive: true });

  assert.equal(tz, "America/Denver");
  assert.equal(tzSource, "fallback");
});

// ---------------------------------------------------------------------------
// Test 4: resolveTZ -- user_id absent; returns fallback immediately
// ---------------------------------------------------------------------------

test("4: resolveTZ returns fallback when user_id is absent", () => {
  const { tz, tzSource } = resolveTZ({}, "/some/path", "America/Denver");
  assert.equal(tz, "America/Denver");
  assert.equal(tzSource, "fallback");
});

// ---------------------------------------------------------------------------
// Test 5: executeWithSpan -- span carries tz and tz_source attributes
// ---------------------------------------------------------------------------

test("5: executeWithSpan span carries tz and tz_source from extraAttrs", () => {
  const exp = freshSpans();
  const tracer = trace.getTracer(PLUGIN_TRACER);
  const mockSpawn = () => ({
    status: 0, stdout: '{"ok":true,"data":{}}', stderr: "", error: undefined,
  });

  executeWithSpan(tracer, "get_today_date", mockSpawn, {}, {
    tz: "America/Denver",
    tz_source: "fallback",
  });

  const span = exp.getFinishedSpans()[0];
  assert.equal(span.attributes["tz"], "America/Denver");
  assert.equal(span.attributes["tz_source"], "fallback");
});

// ---------------------------------------------------------------------------
// Test 6: GTD_TZ present in extraEnv passed to spawn via spawnFn wrapper
// ---------------------------------------------------------------------------

test("6: GTD_TZ injected in extraEnv when spawnFn wrapper adds it", () => {
  let captured;
  const tz = "America/Denver";
  const innerMock = (_p, extraEnv) => {
    captured = extraEnv;
    return { status: 0, stdout: '{"ok":true,"data":{}}', stderr: "", error: undefined };
  };
  const spawnFn = (p, extraEnv) => innerMock(p, { ...extraEnv, GTD_TZ: tz });
  const tracer = trace.getTracer(PLUGIN_TRACER);

  executeWithSpan(tracer, "get_today_date", spawnFn, {}, { tz, tz_source: "fallback" });

  assert.ok(captured, "innerMock should have been called");
  assert.equal(captured.GTD_TZ, tz);
});

// ---------------------------------------------------------------------------
// Test 7: span name is shared-tools.tool.get_today_date
// ---------------------------------------------------------------------------

test("7: span name is shared-tools.tool.get_today_date", () => {
  const exp = freshSpans();
  const tracer = trace.getTracer(PLUGIN_TRACER);
  const mockSpawn = () => ({
    status: 0, stdout: '{"ok":true,"data":{}}', stderr: "", error: undefined,
  });

  executeWithSpan(tracer, "get_today_date", mockSpawn, {});

  const span = exp.getFinishedSpans()[0];
  assert.equal(span.name, "shared-tools.tool.get_today_date");
});

// ---------------------------------------------------------------------------
// Test 8: SPAWN_ENV.OTEL_SERVICE_NAME is "shared-tools"
// ---------------------------------------------------------------------------

test("8: SPAWN_ENV.OTEL_SERVICE_NAME is 'shared-tools'", () => {
  assert.equal(SPAWN_ENV.OTEL_SERVICE_NAME, "shared-tools");
});

// ---------------------------------------------------------------------------
// Test 9: TRACEPARENT injected in subprocess extraEnv with valid W3C format
// ---------------------------------------------------------------------------

test("9: TRACEPARENT injected in subprocess extraEnv with valid W3C format", () => {
  let captured;
  const mockSpawn = (_p, extraEnv) => {
    captured = extraEnv;
    return { status: 0, stdout: '{"ok":true,"data":{}}', stderr: "", error: undefined };
  };
  const tracer = trace.getTracer(PLUGIN_TRACER);
  executeWithSpan(tracer, "get_today_date", mockSpawn, {});

  assert.ok(captured, "extraEnv should be passed");
  assert.ok(captured.TRACEPARENT, "TRACEPARENT should be present");
  assert.match(
    captured.TRACEPARENT,
    /^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$/,
    "TRACEPARENT must be valid W3C format"
  );
});
