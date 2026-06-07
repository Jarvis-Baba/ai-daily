// From telemetry records → SourceHealthState (by-source_name aggregation)

import type { TelemetryRecord } from "../types/raw";
import type { SourceHealthItem, SourceHealthState } from "../state/dashboard";

interface SourceBucket {
  ok: number;
  error: number;
  latencies: number[];
}

export function adaptSourceHealth(
  records: TelemetryRecord[]
): SourceHealthState {
  const bySource = new Map<string, SourceBucket>();

  for (const r of records) {
    let b = bySource.get(r.source_name);
    if (!b) {
      b = { ok: 0, error: 0, latencies: [] };
      bySource.set(r.source_name, b);
    }
    if (r.status === "success") b.ok++;
    else b.error++;
    b.latencies.push(r.latency_ms);
  }

  const sources: SourceHealthItem[] = [];
  for (const [source, b] of bySource) {
    const total = b.ok + b.error;
    sources.push({
      source,
      ok: b.ok,
      error: b.error,
      total,
      successRate: total ? b.ok / total : 0,
      avgLatencyMs: b.latencies.length
        ? Math.round(b.latencies.reduce((a, c) => a + c, 0) / b.latencies.length)
        : 0,
    });
  }

  sources.sort((a, b) => b.total - a.total);
  return { sources };
}
