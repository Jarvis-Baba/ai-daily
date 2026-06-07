// From editorial_telemetry_*.json → EventState

import type { EditorialTelemetry } from "../types/raw";
import type { EventItem, EventState } from "../state/dashboard";

const ROLE_ORDER = ["hook", "context", "pivot", "amplifier", "contradiction", "closer"];

const ROLE_LABEL: Record<string, string> = {
  hook:           "Hook",
  context:        "Context",
  pivot:          "Pivot",
  amplifier:      "Amplifier",
  contradiction:  "Contradiction",
  closer:         "Closer",
};

export function adaptEditorial(
  editorial: EditorialTelemetry | null
): EventState {
  if (!editorial) {
    return { items: [], candidateCount: 0, selectedCount: 0, unassignedCount: 0 };
  }

  const items: EventItem[] = [];

  for (const role of ROLE_ORDER) {
    const entry = editorial.role_assignment[role];
    if (entry) {
      items.push({ title: entry.event, type: entry.type, role: ROLE_LABEL[role] ?? role });
    }
  }

  for (const u of editorial.unassigned) {
    items.push({ title: u.event, type: u.type, role: null, reason: u.reason });
  }

  return {
    items,
    candidateCount: editorial.candidate_events,
    selectedCount: editorial.selected_events,
    unassignedCount: editorial.unassigned_events,
  };
}
