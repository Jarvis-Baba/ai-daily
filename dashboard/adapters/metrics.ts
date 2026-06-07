// From records + editorial + fingerprint → DailyMetricsState

import type { TelemetryRecord, StructuralFingerprint } from "../types/raw";
import type { DailyMetricsState } from "../state/dashboard";

export function adaptDailyMetrics(
  records: TelemetryRecord[],
  editorialCandidates: number | null,
  editorialPublished: number | null,
  fingerprint: StructuralFingerprint | null
): DailyMetricsState {
  const sources = new Set(records.map((r) => r.source_name));

  return {
    date: records[0]?.timestamp?.slice(0, 10) ?? "",
    fetchTotal: records.length,
    fetchOk: records.filter((r) => r.status === "success").length,
    candidates: editorialCandidates ?? 0,
    published: editorialPublished ?? 0,
    sourceCount: sources.size,
    orphanRatio: fingerprint?.orphan_ratio ?? 0,
    clusterCount: fingerprint?.cluster_count ?? 0,
    clusterEntropy: fingerprint?.cluster_entropy ?? 0,
    meanClusterSize: fingerprint?.mean_cluster_size ?? 0,
    eventYield: fingerprint?.event_yield ?? 0,
  };
}
