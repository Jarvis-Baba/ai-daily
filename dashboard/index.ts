// ============================================================
// Dashboard entry point.
//
// Usage:
//   import { buildDashboardState } from "./index";
//   const state = buildDashboardState(records, editorial, fingerprint);
//
// Or individual adapters:
//   import { adaptFunnel } from "./index";
//   const funnel = adaptFunnel(records, editorial);
// ============================================================

import type { TelemetryRecord, EditorialTelemetry, StructuralFingerprint } from "./types/raw";
import type { DashboardState } from "./state/dashboard";
import { adaptFunnel, adaptInbox } from "./adapters/signals";
import { adaptEditorial } from "./adapters/editorial";
import { adaptSourceHealth } from "./adapters/source-health";
import { adaptDailyMetrics } from "./adapters/metrics";
import { adaptPipelineHealth } from "./adapters/pipeline-health";

// Re-export individual adapters for partial refresh
export { adaptFunnel, adaptInbox } from "./adapters/signals";
export { adaptEditorial } from "./adapters/editorial";
export { adaptSourceHealth } from "./adapters/source-health";
export { adaptDailyMetrics } from "./adapters/metrics";
export { adaptPipelineHealth } from "./adapters/pipeline-health";

// Re-export types for consumers
export type {
  DashboardState,
  FunnelState,
  FunnelStep,
  EventState,
  EventItem,
  SourceHealthState,
  SourceHealthItem,
  DailyMetricsState,
  PipelineHealthState,
  InboxState,
  InboxItem,
} from "./state/dashboard";

export type {
  TelemetryRecord,
  EditorialTelemetry,
  StructuralFingerprint,
} from "./types/raw";

export function buildDashboardState(
  records: TelemetryRecord[],
  editorial: EditorialTelemetry | null,
  fingerprint: StructuralFingerprint | null
): DashboardState {
  return {
    funnel:       adaptFunnel(records, editorial),
    events:       adaptEditorial(editorial),
    sourceHealth: adaptSourceHealth(records),
    dailyMetrics: adaptDailyMetrics(
      records,
      editorial?.candidate_events ?? null,
      editorial?.selected_events ?? null,
      fingerprint
    ),
    pipelineHealth: adaptPipelineHealth(fingerprint),
    inbox: adaptInbox(records),
  };
}
