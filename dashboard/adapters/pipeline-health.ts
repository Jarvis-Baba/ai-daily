// Structural health — fingerprint-derived metrics only.
// Operational counts (fetch/candidate/published) are in Funnel + Daily Metrics.
// All fields are null when fingerprint is missing: null = "unknown", not zero.

import type { StructuralFingerprint } from "../types/raw";
import type { PipelineHealthState } from "../state/dashboard";

export function adaptPipelineHealth(
  fingerprint: StructuralFingerprint | null
): PipelineHealthState {
  return {
    evidenceCount:    fingerprint?.evidence_count    ?? null,
    clusterCount:     fingerprint?.cluster_count     ?? null,
    orphanRatio:      fingerprint?.orphan_ratio      ?? null,
    clusterEntropy:   fingerprint?.cluster_entropy   ?? null,
    aggregationRatio: fingerprint?.aggregation_ratio ?? null,
    eventYield:       fingerprint?.event_yield       ?? null,
  };
}
