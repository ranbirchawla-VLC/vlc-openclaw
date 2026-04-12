#!/usr/bin/env node
/**
 * nutrios_read.js — Read and parse a JSON file from the NutriOS data store.
 *
 * Input (JSON on stdin):
 *   { "path": "protocol.json" }
 *   Path is relative to NUTRIOS_DATA_ROOT, or absolute.
 *
 * Output (JSON on stdout):
 *   { "ok": true, "data": { ...parsed JSON... } }
 *   { "ok": false, "error": "..." }
 */

const fs = require("fs");
const path = require("path");

const DATA_ROOT = process.env.NUTRIOS_DATA_ROOT;

function resolve(p) {
  if (!p) return null;
  if (path.isAbsolute(p)) return p;
  if (!DATA_ROOT) return null;
  return path.join(DATA_ROOT, p);
}

async function main() {
  let input;
  try {
    const raw = fs.readFileSync("/dev/stdin", "utf8");
    input = JSON.parse(raw);
  } catch (e) {
    console.log(JSON.stringify({ ok: false, error: "Invalid input JSON: " + e.message }));
    process.exit(0);
  }

  const filePath = resolve(input.path);
  if (!filePath) {
    console.log(JSON.stringify({ ok: false, error: "No path provided or NUTRIOS_DATA_ROOT not set" }));
    process.exit(0);
  }

  // Check if file exists
  if (!fs.existsSync(filePath)) {
    console.log(JSON.stringify({ ok: false, error: "File not found: " + input.path }));
    process.exit(0);
  }

  // Check for zero-byte file (possible Drive sync conflict)
  const stat = fs.statSync(filePath);
  if (stat.size === 0) {
    // Wait 2 seconds and retry — may be a Google Drive sync conflict
    await new Promise((r) => setTimeout(r, 2000));
    const stat2 = fs.statSync(filePath);
    if (stat2.size === 0) {
      // Try .bak file
      const bakPath = filePath + ".bak";
      if (fs.existsSync(bakPath) && fs.statSync(bakPath).size > 0) {
        try {
          const bakData = JSON.parse(fs.readFileSync(bakPath, "utf8"));
          console.log(JSON.stringify({
            ok: true,
            data: bakData,
            warning: "Restored from .bak — original file was empty (possible sync conflict)"
          }));
          process.exit(0);
        } catch (e) {
          // .bak is also corrupt
        }
      }
      console.log(JSON.stringify({
        ok: false,
        error: "File is empty (0 bytes) — possible Google Drive sync conflict: " + input.path
      }));
      process.exit(0);
    }
  }

  // Read and parse
  let raw;
  try {
    raw = fs.readFileSync(filePath, "utf8");
  } catch (e) {
    console.log(JSON.stringify({ ok: false, error: "Cannot read file: " + e.message }));
    process.exit(0);
  }

  try {
    const data = JSON.parse(raw);
    console.log(JSON.stringify({ ok: true, data }));
  } catch (e) {
    // Return parse error with raw content for repair attempts
    console.log(JSON.stringify({
      ok: false,
      error: "JSON parse error: " + e.message,
      raw_content: raw.substring(0, 2000) // first 2000 chars for repair
    }));
  }
}

main();
