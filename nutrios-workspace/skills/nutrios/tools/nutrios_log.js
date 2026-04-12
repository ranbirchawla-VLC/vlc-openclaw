#!/usr/bin/env node
/**
 * nutrios_log.js — Daily food, water, and dose logging for NutriOS.
 *
 * Actions:
 *   add    — Append food entry, auto-assign id, recalculate totals
 *   undo   — Remove entry with highest id, recalculate
 *   delete — Remove entry by id, recalculate
 *   edit   — Update entry by id, recalculate
 *   water  — Increment water_count
 *   dose   — Set dose_logged to true
 *
 * Input (JSON on stdin):
 *   add:    { "action": "add", "entry": {...}, "targets": {...}, "day_type": "..." }
 *   undo:   { "action": "undo" }
 *   delete: { "action": "delete", "entry_id": 3 }
 *   edit:   { "action": "edit", "entry_id": 2, "entry": { ...updated... } }
 *   water:  { "action": "water" }
 *   dose:   { "action": "dose" }
 *
 * Output (JSON on stdout):
 *   { "ok": true, "totals": {...}, "remaining": {...}, "log_path": "...", ... }
 *   { "ok": false, "error": "..." }
 */

const fs = require("fs");
const path = require("path");

const DATA_ROOT = process.env.NUTRIOS_DATA_ROOT;
const TZ = process.env.NUTRIOS_TZ || "America/Denver";

function getTodayDate() {
  const now = new Date();
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return fmt.format(now); // YYYY-MM-DD
}

function getTodayDow() {
  const now = new Date();
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    weekday: "long",
  });
  return fmt.format(now).toLowerCase();
}

function resolve(p) {
  if (!p) return null;
  if (path.isAbsolute(p)) return p;
  if (!DATA_ROOT) return null;
  return path.join(DATA_ROOT, p);
}

function recalcTotals(entries, targets) {
  const totals = { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 };
  for (const e of entries) {
    if (e.macros) {
      totals.calories += e.macros.calories || 0;
      totals.protein_g += e.macros.protein_g || 0;
      totals.carbs_g += e.macros.carbs_g || 0;
      totals.fat_g += e.macros.fat_g || 0;
    }
  }

  // Round totals
  totals.calories = Math.round(totals.calories);
  totals.protein_g = Math.round(totals.protein_g * 10) / 10;
  totals.carbs_g = Math.round(totals.carbs_g * 10) / 10;
  totals.fat_g = Math.round(totals.fat_g * 10) / 10;

  const remaining = {
    calories: (targets.calories || 0) - totals.calories,
    protein_g: Math.round(((targets.protein_g || 0) - totals.protein_g) * 10) / 10,
    carbs_g: Math.round(((targets.carbs_g || 0) - totals.carbs_g) * 10) / 10,
    fat_g: Math.round(((targets.fat_g || 0) - totals.fat_g) * 10) / 10,
  };

  return { totals, remaining };
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

  if (!DATA_ROOT) {
    console.log(JSON.stringify({ ok: false, error: "NUTRIOS_DATA_ROOT not set" }));
    process.exit(0);
  }

  const today = getTodayDate();
  const logDir = resolve("logs");
  const logPath = path.join(logDir, today + ".json");

  // Ensure logs directory
  try {
    fs.mkdirSync(logDir, { recursive: true });
  } catch (_) {}

  // Read existing log or create empty
  let log;
  if (fs.existsSync(logPath)) {
    try {
      log = JSON.parse(fs.readFileSync(logPath, "utf8"));
    } catch (e) {
      log = null;
    }
  }

  if (!log) {
    log = {
      date: today,
      day_type: input.day_type || "",
      targets: input.targets || { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 },
      entries: [],
      running_totals: { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 },
      remaining: input.targets || { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 },
      water_count: 0,
      dose_logged: false,
      day_notes: "",
    };
  }

  // Update targets and day_type if provided (context may have changed)
  if (input.targets) log.targets = input.targets;
  if (input.day_type) log.day_type = input.day_type;

  const action = input.action || "add";

  switch (action) {
    case "add": {
      if (!input.entry) {
        console.log(JSON.stringify({ ok: false, error: "No entry provided for add action" }));
        process.exit(0);
      }
      // Auto-assign id
      const maxId = log.entries.reduce((max, e) => Math.max(max, e.id || 0), 0);
      const entry = { id: maxId + 1, ...input.entry };
      log.entries.push(entry);

      const { totals, remaining } = recalcTotals(log.entries, log.targets);
      log.running_totals = totals;
      log.remaining = remaining;

      writeLog(logPath, log);
      console.log(JSON.stringify({
        ok: true,
        action: "add",
        entry_id: entry.id,
        entry_macros: entry.macros,
        totals,
        remaining,
        log_path: logPath,
        water_count: log.water_count,
        dose_logged: log.dose_logged,
      }));
      break;
    }

    case "undo": {
      if (log.entries.length === 0) {
        console.log(JSON.stringify({ ok: false, error: "No entries to undo" }));
        process.exit(0);
      }
      // Remove entry with highest id
      const maxId = Math.max(...log.entries.map((e) => e.id || 0));
      const removed = log.entries.find((e) => e.id === maxId);
      log.entries = log.entries.filter((e) => e.id !== maxId);

      const { totals, remaining } = recalcTotals(log.entries, log.targets);
      log.running_totals = totals;
      log.remaining = remaining;

      writeLog(logPath, log);
      console.log(JSON.stringify({
        ok: true,
        action: "undo",
        removed_entry: removed,
        totals,
        remaining,
        log_path: logPath,
      }));
      break;
    }

    case "delete": {
      const entryId = input.entry_id;
      if (!entryId) {
        console.log(JSON.stringify({ ok: false, error: "No entry_id provided for delete" }));
        process.exit(0);
      }
      const removed = log.entries.find((e) => e.id === entryId);
      if (!removed) {
        console.log(JSON.stringify({ ok: false, error: "Entry id " + entryId + " not found" }));
        process.exit(0);
      }
      log.entries = log.entries.filter((e) => e.id !== entryId);

      const { totals, remaining } = recalcTotals(log.entries, log.targets);
      log.running_totals = totals;
      log.remaining = remaining;

      writeLog(logPath, log);
      console.log(JSON.stringify({
        ok: true,
        action: "delete",
        removed_entry: removed,
        totals,
        remaining,
        log_path: logPath,
      }));
      break;
    }

    case "edit": {
      const editId = input.entry_id;
      if (!editId) {
        console.log(JSON.stringify({ ok: false, error: "No entry_id provided for edit" }));
        process.exit(0);
      }
      const idx = log.entries.findIndex((e) => e.id === editId);
      if (idx === -1) {
        console.log(JSON.stringify({ ok: false, error: "Entry id " + editId + " not found" }));
        process.exit(0);
      }

      // Merge updated fields into existing entry
      const updated = { ...log.entries[idx] };
      if (input.entry) {
        if (input.entry.description) updated.description = input.entry.description;
        if (input.entry.macros) updated.macros = { ...updated.macros, ...input.entry.macros };
        if (input.entry.time) updated.time = input.entry.time;
        if (input.entry.source) updated.source = input.entry.source;
      }
      log.entries[idx] = updated;

      const { totals, remaining } = recalcTotals(log.entries, log.targets);
      log.running_totals = totals;
      log.remaining = remaining;

      writeLog(logPath, log);
      console.log(JSON.stringify({
        ok: true,
        action: "edit",
        updated_entry: updated,
        totals,
        remaining,
        log_path: logPath,
      }));
      break;
    }

    case "water": {
      log.water_count = (log.water_count || 0) + 1;
      writeLog(logPath, log);
      console.log(JSON.stringify({
        ok: true,
        action: "water",
        water_count: log.water_count,
        log_path: logPath,
      }));
      break;
    }

    case "dose": {
      log.dose_logged = true;
      writeLog(logPath, log);
      console.log(JSON.stringify({
        ok: true,
        action: "dose",
        dose_logged: true,
        log_path: logPath,
      }));
      break;
    }

    default:
      console.log(JSON.stringify({ ok: false, error: "Unknown action: " + action }));
  }
}

function writeLog(logPath, log) {
  const content = JSON.stringify(log, null, 2) + "\n";
  const tmpPath = logPath + ".tmp";
  const bakPath = logPath + ".bak";

  try {
    if (fs.existsSync(logPath)) {
      fs.copyFileSync(logPath, bakPath);
    }
    fs.writeFileSync(tmpPath, content, "utf8");
    fs.renameSync(tmpPath, logPath);
  } catch (e) {
    try {
      if (fs.existsSync(tmpPath)) fs.unlinkSync(tmpPath);
    } catch (_) {}
    throw e;
  }
}

main();
