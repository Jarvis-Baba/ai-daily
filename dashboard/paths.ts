// Path constants — single source of truth for all file I/O.
// Only load_data.ts imports from this file.

import path from "path";

const ROOT = path.resolve(__dirname, "..");
const OUTPUT = path.join(ROOT, "output");
const ARTIFACTS = path.join(OUTPUT, "artifacts");
const TELEMETRY = path.join(ARTIFACTS, "telemetry");
const CALIBRATION = path.join(ARTIFACTS, "calibration");

export const PATHS = {
  root: ROOT,
  output: OUTPUT,
  artifacts: ARTIFACTS,
  telemetryDir: TELEMETRY,
  calibrationDir: CALIBRATION,

  /** Today's telemetry JSONL — one file per day, e.g. 20260607.jsonl */
  telemetryForDate: (date: string) => path.join(TELEMETRY, `${date}.jsonl`),

  /** Editorial telemetry — one JSON per day */
  editorialForDate: (date: string) =>
    path.join(CALIBRATION, `editorial_telemetry_${date}.json`),

  /** Structural fingerprint — one JSON per day */
  fingerprintForDate: (date: string) =>
    path.join(TELEMETRY, `structural_fingerprint_${date}.json`),

  /** Source health snapshot (atomic-write target) */
  sourceHealth: path.join(ARTIFACTS, "source_health.json"),
} as const;
