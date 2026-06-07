// ============================================================
// Raw file schemas — 1:1 match with actual JSON on disk.
// UI code must NEVER import from this file directly.
// ============================================================

// ── telemetry/*.jsonl (one record per line) ──

export interface TelemetryRecord {
  url: string;
  canonical_url: string;
  status: "success" | "error";
  artifact_id: string;
  fetcher: string;
  latency_ms: number;
  content_length: number;
  content_hash: string;
  media_count: number;
  has_screenshot: boolean;
  artifact_type: string;
  source_name: string;
  timestamp: string;
}

// ── editorial_telemetry_*.json ──

export interface EditorialTelemetry {
  editorial_telemetry_version: string;
  run_date: string;
  candidate_events: number;
  selected_events: number;
  unassigned_events: number;
  discarded_events: number;
  selection_ratio: number;
  role_assignment: Record<string, RoleAssignment | undefined>;
  unassigned: UnassignedEvent[];
}

export interface RoleAssignment {
  event: string;
  type: string;
}

export interface UnassignedEvent {
  event: string;
  type: string;
  reason: string;
}

// ── structural_fingerprint_*.json ──

export interface StructuralFingerprint {
  timestamp: string;
  evidence_count: number;
  cluster_count: number;
  evidence_in_clusters: number;
  orphan_count: number;
  orphan_ratio: number;
  cluster_entropy: number;
  mean_cluster_size: number;
  aggregation_ratio: number;
  event_count: number;
  event_yield: number;
  source_count: number;
  cluster_size_distribution: Record<string, number>;
  decomposition: FingerprintDecomposition;
}

export interface FingerprintDecomposition {
  h_source: number;
  coverage: number;
  h_cluster: number;
  compression_ratio: number;
  interpretation: string;
}
