// ============================================================
// UI consumption shapes.
// Dashboard components only import from this file (and index.ts).
// They NEVER touch types/raw.ts.
// ============================================================

// ── Funnel ──

export interface FunnelStep {
  label: string;
  count: number;
  pctOfPrev: number; // 0..1; first step is always 1.0
}

export interface FunnelState {
  steps: FunnelStep[];
}

// ── Events ──

export interface EventItem {
  title: string;
  type: string;
  role: string | null; // null = unassigned
  reason?: string;     // only set for unassigned
}

export interface EventState {
  items: EventItem[];
  candidateCount: number;
  selectedCount: number;
  unassignedCount: number;
}

// ── Source Health ──

export interface SourceHealthItem {
  source: string;
  ok: number;
  error: number;
  total: number;
  successRate: number;  // 0..1
  avgLatencyMs: number;
}

export interface SourceHealthState {
  sources: SourceHealthItem[];
}

// ── Daily Metrics ──

export interface DailyMetricsState {
  date: string;
  fetchTotal: number;
  fetchOk: number;
  candidates: number;
  published: number;
  sourceCount: number;
  orphanRatio: number;
  clusterCount: number;
  clusterEntropy: number;
  meanClusterSize: number;
  eventYield: number;
}

// ── Inbox ──

export interface InboxItem {
  url: string;
  source: string;
  status: "success" | "error";
  latencyMs: number;
  timestamp: string;
}

export interface InboxState {
  items: InboxItem[];
}

// ── Structural Health ──
// Fingerprint-derived only. Operational counts live in Funnel + Daily Metrics.
// All fields null when fingerprint file is missing.

export interface PipelineHealthState {
  evidenceCount: number | null;
  clusterCount: number | null;
  orphanRatio: number | null;
  clusterEntropy: number | null;
  aggregationRatio: number | null;
  eventYield: number | null;
}

// ── Aggregate ──

export interface DashboardState {
  funnel: FunnelState;
  events: EventState;
  sourceHealth: SourceHealthState;
  dailyMetrics: DailyMetricsState;
  pipelineHealth: PipelineHealthState;
  inbox: InboxState;
}
