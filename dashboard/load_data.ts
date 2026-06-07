// ============================================================
// I/O layer — the ONLY file that reads from or writes to disk.
// Every other file in dashboard/ is a pure function.
// ============================================================

import fs from "fs";
import path from "path";
import { PATHS } from "./paths";
import type { TelemetryRecord, EditorialTelemetry, StructuralFingerprint } from "./types/raw";
import type { SourceHealthState } from "./state/dashboard";

// ── Loaders ──

/** Read today's telemetry JSONL into an array of TelemetryRecord. */
export function loadTelemetryRecords(date: string): TelemetryRecord[] {
  const file = PATHS.telemetryForDate(date);
  if (!fs.existsSync(file)) return [];

  const raw = fs.readFileSync(file, "utf-8").trim();
  if (!raw) return [];

  const records: TelemetryRecord[] = [];
  for (const line of raw.split("\n")) {
    try {
      records.push(JSON.parse(line));
    } catch {
      // Skip corrupted lines silently
    }
  }
  return records;
}

/** Read the editorial telemetry JSON for a given date. Returns null if missing. */
export function loadEditorialTelemetry(date: string): EditorialTelemetry | null {
  const file = PATHS.editorialForDate(date);
  if (!fs.existsSync(file)) return null;

  try {
    return JSON.parse(fs.readFileSync(file, "utf-8")) as EditorialTelemetry;
  } catch {
    return null;
  }
}

/** Read the structural fingerprint JSON for a given date. Returns null if missing. */
export function loadFingerprint(date: string): StructuralFingerprint | null {
  const file = PATHS.fingerprintForDate(date);
  if (!fs.existsSync(file)) return null;

  try {
    return JSON.parse(fs.readFileSync(file, "utf-8")) as StructuralFingerprint;
  } catch {
    return null;
  }
}

/** Convenience: load all three data sources for today in one call. */
export function loadTodaysData() {
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  const records = loadTelemetryRecords(today);
  const editorial = loadEditorialTelemetry(today);
  const fingerprint = loadFingerprint(today);
  return { records, editorial, fingerprint, date: today };
}

// ── Writers ──

/** Atomic write for source_health.json. Never leaves a half-written file on disk. */
export function writeSourceHealth(snapshot: SourceHealthState): void {
  const dir = path.dirname(PATHS.sourceHealth);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  const tmp = PATHS.sourceHealth + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(snapshot, null, 2), "utf-8");
  fs.renameSync(tmp, PATHS.sourceHealth);
}

// ── CLI ──
// Usage: npx tsx load_data.ts [YYYY-MM-DD]
// Editorial telemetry is dated for the target day (e.g. 2026-06-08),
// but telemetry/fingerprint are dated for the day the pipeline ran (often day-1).

if (require.main === module) {
  const { buildDashboardState } = require("./index");

  const arg = process.argv[2] || new Date().toISOString().slice(0, 10);
  const dateCompact = arg.replace(/-/g, "");

  function tryLoad(d: string) {
    if (d.length === 10) {
      // YYYY-MM-DD → try YYYYMMDD for telemetry, YYYY-MM-DD for editorial
      const dc = d.replace(/-/g, "");
      return {
        records: loadTelemetryRecords(dc),
        editorial: loadEditorialTelemetry(d),
        fingerprint: loadFingerprint(dc),
        dateUsed: d,
      };
    }
    // YYYYMMDD
    return {
      records: loadTelemetryRecords(d),
      editorial: null,
      fingerprint: loadFingerprint(d),
      dateUsed: d,
    };
  }

  // Try the given date first, then fall back to day-1 for telemetry/fingerprint
  let data = tryLoad(arg);
  const hasRecords = data.records.length > 0;

  if (!hasRecords && arg.includes("-")) {
    // Telemetry might be dated day-1. Try editorial date - 1 day.
    const d = new Date(arg);
    d.setDate(d.getDate() - 1);
    const prev = d.toISOString().slice(0, 10);
    console.error(`No telemetry for ${arg}, trying ${prev} …`);
    const prevData = tryLoad(prev);
    // Merge: keep editorial from original, take records+fingerprint from prev
    data = {
      records: prevData.records,
      editorial: data.editorial || prevData.editorial,
      fingerprint: prevData.fingerprint,
      dateUsed: arg,
    };
  }

  console.error(
    `records=${data.records.length} editorial=${data.editorial ? "✓" : "✗"} fingerprint=${data.fingerprint ? "✓" : "✗"}`
  );

  const state = buildDashboardState(data.records, data.editorial, data.fingerprint);
  process.stdout.write(JSON.stringify(state, null, 2));
}
