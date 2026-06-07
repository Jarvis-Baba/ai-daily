// Funnel + Inbox adapters — both consume TelemetryRecord[] from signals.jsonl

import type { TelemetryRecord, EditorialTelemetry } from "../types/raw";
import type { FunnelState, FunnelStep, InboxState } from "../state/dashboard";

export function adaptFunnel(
  records: TelemetryRecord[],
  editorial: EditorialTelemetry | null
): FunnelState {
  const total = records.length;
  const ok = records.filter((r) => r.status === "success").length;
  const candidates = editorial?.candidate_events ?? 0;
  const published = editorial?.selected_events ?? 0;

  const steps: FunnelStep[] = [
    { label: "Raw fetches",      count: total,     pctOfPrev: 1 },
    { label: "Fetch OK",         count: ok,        pctOfPrev: total     ? ok / total     : 0 },
    { label: "Candidate events", count: candidates, pctOfPrev: ok       ? candidates / ok : 0 },
    { label: "Published",        count: published,  pctOfPrev: candidates ? published / candidates : 0 },
  ];

  return { steps };
}

export function adaptInbox(records: TelemetryRecord[]): InboxState {
  const items = records
    .map((r) => ({
      url: r.canonical_url || r.url,
      source: r.source_name,
      status: r.status,
      latencyMs: r.latency_ms,
      timestamp: r.timestamp,
    }))
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp));

  return { items };
}
