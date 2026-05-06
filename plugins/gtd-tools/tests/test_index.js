/**
 * test_index.js -- Phase 1 JS unit tests for OTEL wrapping in gtd-tools plugin.
 *
 * TDD: these tests were written before otel-helpers.js implementation and confirmed
 * RED against the un-retrofitted index.js.
 *
 * Uses node:test (built-in) + @opentelemetry/sdk-trace-base InMemorySpanExporter.
 * Run: node --test tests/
 */
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
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
// Test 1: startActiveSpan invoked per execute; span named gtd.tool.<toolname>
// ---------------------------------------------------------------------------

test("1: startActiveSpan wraps execute and names span gtd.tool.<toolname>", () => {
  const exp = freshSpans();
  const tracer = trace.getTracer(PLUGIN_TRACER);
  const mockSpawn = (_p, _e) => ({
    status: 0, stdout: '{"ok":true,"data":{}}', stderr: "", error: undefined,
  });

  executeWithSpan(tracer, "capture", mockSpawn, {});

  const spans = exp.getFinishedSpans();
  assert.equal(spans.length, 1, "exactly one span per execute");
  assert.equal(spans[0].name, "gtd.tool.capture");
});

// ---------------------------------------------------------------------------
// Test 2: SPAWN_ENV includes OTEL_SERVICE_NAME = "gtd-tools"
// ---------------------------------------------------------------------------

test("2: SPAWN_ENV.OTEL_SERVICE_NAME is gtd-tools", () => {
  assert.equal(SPAWN_ENV.OTEL_SERVICE_NAME, "gtd-tools");
});

// ---------------------------------------------------------------------------
// Test 3: TRACEPARENT injected in subprocess env; valid W3C format
// ---------------------------------------------------------------------------

test("3: TRACEPARENT injected into subprocess extraEnv with valid W3C format", () => {
  let captured;
  const mockSpawn = (_p, extraEnv) => {
    captured = extraEnv;
    return { status: 0, stdout: '{"ok":true,"data":{}}', stderr: "", error: undefined };
  };
  const tracer = trace.getTracer(PLUGIN_TRACER);
  executeWithSpan(tracer, "query_tasks", mockSpawn, {});

  assert.ok(captured, "extraEnv should be passed to spawnFn");
  assert.ok(captured.TRACEPARENT, "TRACEPARENT should be present in extraEnv");
  assert.match(
    captured.TRACEPARENT,
    /^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$/,
    "TRACEPARENT must be valid W3C format"
  );
});

// ---------------------------------------------------------------------------
// Test 4: plugin span attributes present: tool.name, agent.id, plugin.name
// ---------------------------------------------------------------------------

test("4: plugin span carries tool.name, agent.id, plugin.name attributes", () => {
  const exp = freshSpans();
  const tracer = trace.getTracer(PLUGIN_TRACER);
  const mockSpawn = () => ({
    status: 0, stdout: '{"ok":true,"data":{}}', stderr: "", error: undefined,
  });

  executeWithSpan(tracer, "review", mockSpawn, {});

  const span = exp.getFinishedSpans()[0];
  assert.ok(span, "span should exist");
  assert.equal(span.attributes["tool.name"], "review");
  assert.equal(span.attributes["agent.id"], "gtd");
  assert.equal(span.attributes["plugin.name"], "gtd-tools");
});

// ---------------------------------------------------------------------------
// Test 5: error path -- subprocess_spawn_error
// ---------------------------------------------------------------------------

test("5a: subprocess_spawn_error sets span status ERROR and correct attributes", () => {
  const exp = freshSpans();
  const tracer = trace.getTracer(PLUGIN_TRACER);
  const mockSpawn = () => ({
    error: { message: "spawn ENOENT", code: "ENOENT" },
    status: null, stdout: "", stderr: "",
  });

  executeWithSpan(tracer, "capture", mockSpawn, {});

  const span = exp.getFinishedSpans()[0];
  assert.equal(span.status.code, SpanStatusCode.ERROR);
  assert.equal(span.attributes["error.type"], "subprocess_spawn_error");
  assert.equal(span.attributes["error.code"], "subprocess_spawn_error");
  assert.ok(span.attributes["error.location"], "error.location must be set");
  assert.ok(span.attributes["error.context"], "error.context must be set");
});

// ---------------------------------------------------------------------------
// Test 5b: subprocess_nonzero_exit
// ---------------------------------------------------------------------------

test("5b: subprocess_nonzero_exit sets span status ERROR and correct attributes", () => {
  const exp = freshSpans();
  const tracer = trace.getTracer(PLUGIN_TRACER);
  const mockSpawn = () => ({
    status: 1, stdout: "", stderr: "internal error", error: undefined,
  });

  executeWithSpan(tracer, "query_tasks", mockSpawn, {});

  const span = exp.getFinishedSpans()[0];
  assert.equal(span.status.code, SpanStatusCode.ERROR);
  assert.equal(span.attributes["error.code"], "subprocess_nonzero_exit");
});

// ---------------------------------------------------------------------------
// Test 5c: output_parse_failure
// ---------------------------------------------------------------------------

test("5c: output_parse_failure sets span status ERROR and correct attributes", () => {
  const exp = freshSpans();
  const tracer = trace.getTracer(PLUGIN_TRACER);
  const mockSpawn = () => ({
    status: 0, stdout: "not-json-{broken", stderr: "", error: undefined,
  });

  executeWithSpan(tracer, "capture", mockSpawn, {});

  const span = exp.getFinishedSpans()[0];
  assert.equal(span.status.code, SpanStatusCode.ERROR);
  assert.equal(span.attributes["error.code"], "output_parse_failure");
});

// ---------------------------------------------------------------------------
// Test 6: error span omits exception.message and exception.stacktrace
// ---------------------------------------------------------------------------

test("6: error span omits exception.message and exception.stacktrace", () => {
  const exp = freshSpans();
  const tracer = trace.getTracer(PLUGIN_TRACER);
  const mockSpawn = () => ({
    status: 1, stdout: "", stderr: "some error", error: undefined,
  });

  executeWithSpan(tracer, "capture", mockSpawn, {});

  const span = exp.getFinishedSpans()[0];
  assert.ok(
    !("exception.message" in span.attributes),
    "exception.message must be absent"
  );
  assert.ok(
    !("exception.stacktrace" in span.attributes),
    "exception.stacktrace must be absent"
  );
});

// ---------------------------------------------------------------------------
// Test 7: error span contains no user content from params
// ---------------------------------------------------------------------------

test("7: error span attributes contain no user content from params", () => {
  const exp = freshSpans();
  const tracer = trace.getTracer(PLUGIN_TRACER);
  const sensitiveParams = {
    record: { title: "SENTINEL_TITLE_99999", content: "SENTINEL_SECRET_CONTENT" },
  };
  const mockSpawn = (_p, _e) => ({
    status: 1, stdout: "", stderr: "error", error: undefined,
  });

  executeWithSpan(tracer, "capture", mockSpawn, sensitiveParams);

  const span = exp.getFinishedSpans()[0];
  const attrValues = Object.values(span.attributes).map(String);
  for (const val of attrValues) {
    assert.ok(
      !val.includes("SENTINEL_TITLE_99999"),
      `span attribute must not contain user param value: ${val}`
    );
    assert.ok(
      !val.includes("SENTINEL_SECRET_CONTENT"),
      `span attribute must not contain user param value: ${val}`
    );
  }
});
