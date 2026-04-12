#!/usr/bin/env node
/**
 * pdf_read.js — Extract text from a PDF file using pdftotext (poppler).
 *
 * Input (JSON on stdin):
 *   { "path": "/full/path/to/file.pdf" }
 *
 * Output (JSON on stdout):
 *   { "ok": true, "text": "..." }
 *   { "ok": false, "error": "..." }
 */

const fs = require("fs");
const { execSync } = require("child_process");

async function main() {
  let input = {};
  try {
    const raw = fs.readFileSync("/dev/stdin", "utf-8").trim();
    if (raw) input = JSON.parse(raw);
  } catch (e) {}

  if (!input.path) {
    console.log(JSON.stringify({ ok: false, error: "Missing path" }));
    return;
  }

  if (!fs.existsSync(input.path)) {
    console.log(JSON.stringify({ ok: false, error: `File not found: ${input.path}` }));
    return;
  }

  try {
    const text = execSync(`/opt/homebrew/bin/pdftotext "${input.path}" -`, {
      maxBuffer: 10 * 1024 * 1024,
    }).toString("utf-8");
    console.log(JSON.stringify({ ok: true, text }));
  } catch (err) {
    console.log(JSON.stringify({ ok: false, error: err.message }));
  }
}

main();
