#!/usr/bin/env node
/**
 * nutrios_write.js — Write JSON to the NutriOS data store.
 *
 * Input (JSON on stdin):
 *   { "path": "protocol.json", "data": {...}, "merge": true }
 *
 * Merge behaviour:
 *   merge: true  → deep-merge objects. ARRAYS ARE REPLACED, not concatenated.
 *   merge: false → full overwrite of the entire file.
 *
 * Write safety:
 *   - Creates parent directories automatically
 *   - Writes to a temp file first (.tmp), then atomic rename
 *   - Backs up current file to .bak before overwriting
 *
 * Output (JSON on stdout):
 *   { "ok": true, "wrote": "/absolute/path" }
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

/**
 * Deep merge: objects are recursively merged, arrays are REPLACED.
 */
function deepMerge(target, source) {
  const result = { ...target };
  for (const key of Object.keys(source)) {
    const srcVal = source[key];
    const tgtVal = result[key];

    if (Array.isArray(srcVal)) {
      // Arrays are REPLACED, not concatenated
      result[key] = srcVal;
    } else if (
      srcVal !== null &&
      typeof srcVal === "object" &&
      !Array.isArray(srcVal) &&
      tgtVal !== null &&
      typeof tgtVal === "object" &&
      !Array.isArray(tgtVal)
    ) {
      result[key] = deepMerge(tgtVal, srcVal);
    } else {
      result[key] = srcVal;
    }
  }
  return result;
}

function main() {
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

  // Ensure parent directory exists
  const dir = path.dirname(filePath);
  try {
    fs.mkdirSync(dir, { recursive: true });
  } catch (e) {
    console.log(JSON.stringify({ ok: false, error: "Cannot create directory: " + e.message }));
    process.exit(0);
  }

  let dataToWrite = input.data;

  // If merge mode, read existing and deep-merge
  if (input.merge === true && fs.existsSync(filePath)) {
    try {
      const existing = JSON.parse(fs.readFileSync(filePath, "utf8"));
      dataToWrite = deepMerge(existing, input.data);
    } catch (e) {
      // If existing file is corrupt, just overwrite
    }
  }

  const content = JSON.stringify(dataToWrite, null, 2) + "\n";
  const tmpPath = filePath + ".tmp";
  const bakPath = filePath + ".bak";

  try {
    // Backup existing file
    if (fs.existsSync(filePath)) {
      fs.copyFileSync(filePath, bakPath);
    }

    // Write to temp file
    fs.writeFileSync(tmpPath, content, "utf8");

    // Atomic rename
    fs.renameSync(tmpPath, filePath);

    console.log(JSON.stringify({ ok: true, wrote: filePath }));
  } catch (e) {
    // Clean up temp file if it exists
    try {
      if (fs.existsSync(tmpPath)) fs.unlinkSync(tmpPath);
    } catch (_) {}

    console.log(JSON.stringify({ ok: false, error: "Write failed: " + e.message }));
  }
}

main();
