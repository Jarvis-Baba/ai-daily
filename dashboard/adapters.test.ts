// ============================================================
// 42 test cases covering all 6 adapters.
// Mock data field names match types/raw.ts schemas 1:1.
// ============================================================

import {
  adaptFunnel,
  adaptInbox,
} from "./adapters/signals";
import { adaptEditorial } from "./adapters/editorial";
import { adaptSourceHealth } from "./adapters/source-health";
import { adaptDailyMetrics } from "./adapters/metrics";
import { adaptPipelineHealth } from "./adapters/pipeline-health";
import type { TelemetryRecord, EditorialTelemetry, StructuralFingerprint } from "./types/raw";

// ── Shared fixtures ──

function makeRecord(overrides: Partial<TelemetryRecord> = {}): TelemetryRecord {
  return {
    url: "https://example.com/article",
    canonical_url: "https://example.com/article",
    status: "success",
    artifact_id: "sha256-abc123",
    fetcher: "basic",
    latency_ms: 120,
    content_length: 4500,
    content_hash: "abc123",
    media_count: 0,
    has_screenshot: false,
    artifact_type: "article",
    source_name: "Ars Technica",
    timestamp: "2026-06-08T01:15:00.000Z",
    ...overrides,
  };
}

const RECORDS_3_OK: TelemetryRecord[] = [
  makeRecord({ source_name: "Ars Technica", timestamp: "2026-06-08T01:10:00.000Z" }),
  makeRecord({ source_name: "OpenAI Blog", timestamp: "2026-06-08T01:12:00.000Z" }),
  makeRecord({ source_name: "Ars Technica", timestamp: "2026-06-08T01:15:00.000Z", latency_ms: 200 }),
];

const RECORDS_MIXED: TelemetryRecord[] = [
  makeRecord({ status: "success", source_name: "Ars Technica" }),
  makeRecord({ status: "success", source_name: "OpenAI Blog", latency_ms: 350 }),
  makeRecord({ status: "error", source_name: "Ars Technica", latency_ms: 0 }),
  makeRecord({ status: "success", source_name: "GitHub Blog" }),
  makeRecord({ status: "error", source_name: "OpenAI Blog", latency_ms: 5000 }),
];

function makeEditorial(overrides?: Partial<EditorialTelemetry>): EditorialTelemetry {
  return {
    editorial_telemetry_version: "1.0",
    run_date: "2026-06-08",
    candidate_events: 7,
    selected_events: 5,
    unassigned_events: 2,
    discarded_events: 0,
    selection_ratio: 1.0,
    role_assignment: {
      hook: { event: "Codex launch", type: "capability" },
      context: { event: "Copilot pricing shift", type: "behavioral" },
      pivot: { event: "Meta AI hack", type: "governance" },
      amplifier: { event: "Gartner leader", type: "ecosystem" },
      closer: { event: "Claude Code auto mode", type: "capability" },
    },
    unassigned: [
      { event: "LLM lexical overlap study", type: "research_result", reason: "no_role_match" },
      { event: "LLM attitude study", type: "research_result", reason: "no_role_match" },
    ],
    ...overrides,
  };
}

function makeFingerprint(overrides?: Partial<StructuralFingerprint>): StructuralFingerprint {
  return {
    timestamp: "2026-06-07T17:15:38.104Z",
    evidence_count: 152,
    cluster_count: 24,
    evidence_in_clusters: 84,
    orphan_count: 68,
    orphan_ratio: 0.4474,
    cluster_entropy: 4.2665,
    mean_cluster_size: 3.5,
    aggregation_ratio: 3.5,
    event_count: 7,
    event_yield: 0.0461,
    source_count: 7,
    cluster_size_distribution: { size_6: 7, size_4: 3, size_2: 12, size_3: 2, size_1: 68 },
    decomposition: {
      h_source: 1.7587,
      coverage: 0.5526,
      h_cluster: 4.2665,
      compression_ratio: 0.2917,
      interpretation: "diverse sources; moderate clustering; aggressive LLM merge",
    },
    ...overrides,
  };
}

// ════════════════════════════════════════════════════════════
// adaptFunnel  (8 cases)
// ════════════════════════════════════════════════════════════

describe("adaptFunnel", () => {
  it("1. computes full 4-step funnel", () => {
    const result = adaptFunnel(RECORDS_3_OK, makeEditorial());
    expect(result.steps).toHaveLength(4);
    expect(result.steps[0]).toEqual({ label: "Raw fetches", count: 3, pctOfPrev: 1 });
    expect(result.steps[1]).toEqual({ label: "Fetch OK", count: 3, pctOfPrev: 1 });
    expect(result.steps[2]).toEqual({ label: "Candidate events", count: 7, pctOfPrev: 7 / 3 });
    expect(result.steps[3]).toEqual({ label: "Published", count: 5, pctOfPrev: 5 / 7 });
  });

  it("2. returns zero steps when records are empty", () => {
    const result = adaptFunnel([], makeEditorial());
    expect(result.steps[0].count).toBe(0);
    expect(result.steps[1].pctOfPrev).toBe(0); // 0/0 → 0
  });

  it("3. handles null editorial — candidates and published fall to 0", () => {
    const result = adaptFunnel(RECORDS_3_OK, null);
    expect(result.steps[2].count).toBe(0);
    expect(result.steps[3].count).toBe(0);
  });

  it("4. handles editorial with zero candidates", () => {
    const result = adaptFunnel(RECORDS_3_OK, makeEditorial({ candidate_events: 0, selected_events: 0 }));
    expect(result.steps[2].count).toBe(0);
    expect(result.steps[3].pctOfPrev).toBe(0);
  });

  it("5. all-error records → Fetch OK step is zero", () => {
    const records = [
      makeRecord({ status: "error" }),
      makeRecord({ status: "error" }),
    ];
    const result = adaptFunnel(records, makeEditorial());
    expect(result.steps[0].count).toBe(2);
    expect(result.steps[1].count).toBe(0);
    expect(result.steps[2].pctOfPrev).toBe(0);
  });

  it("6. more candidates than OK fetches (clustering amplifies)", () => {
    const result = adaptFunnel(RECORDS_3_OK, makeEditorial({ candidate_events: 12 }));
    expect(result.steps[2].pctOfPrev).toBe(4); // 12/3
  });

  it("7. all OK but zero candidates → funnel narrows to zero", () => {
    const result = adaptFunnel(RECORDS_3_OK, makeEditorial({ candidate_events: 0, selected_events: 0 }));
    expect(result.steps[2].count).toBe(0);
    expect(result.steps[3].count).toBe(0);
  });

  it("8. single record happy path", () => {
    const result = adaptFunnel([makeRecord()], makeEditorial({ candidate_events: 1, selected_events: 1 }));
    expect(result.steps[0].count).toBe(1);
    expect(result.steps[1].count).toBe(1);
    expect(result.steps[2].count).toBe(1);
    expect(result.steps[3].count).toBe(1);
  });
});

// ════════════════════════════════════════════════════════════
// adaptInbox  (4 cases)
// ════════════════════════════════════════════════════════════

describe("adaptInbox", () => {
  it("9. returns items sorted by timestamp descending", () => {
    const result = adaptInbox(RECORDS_3_OK);
    expect(result.items).toHaveLength(3);
    expect(result.items[0].timestamp).toBe("2026-06-08T01:15:00.000Z");
    expect(result.items[2].timestamp).toBe("2026-06-08T01:10:00.000Z");
  });

  it("10. empty records → empty items", () => {
    const result = adaptInbox([]);
    expect(result.items).toEqual([]);
  });

  it("11. items include url, source, status, latency, timestamp", () => {
    const result = adaptInbox([makeRecord({ status: "error", latency_ms: 500 })]);
    expect(result.items[0]).toMatchObject({
      url: "https://example.com/article",
      source: "Ars Technica",
      status: "error",
      latencyMs: 500,
    });
  });

  it("12. uses canonical_url when available", () => {
    const record = makeRecord({ canonical_url: "https://canonical.example.com", url: "https://raw.example.com" });
    const result = adaptInbox([record]);
    expect(result.items[0].url).toBe("https://canonical.example.com");
  });
});

// ════════════════════════════════════════════════════════════
// adaptEditorial  (8 cases)
// ════════════════════════════════════════════════════════════

describe("adaptEditorial", () => {
  it("13. full editorial with assigned + unassigned events", () => {
    const result = adaptEditorial(makeEditorial());
    expect(result.candidateCount).toBe(7);
    expect(result.selectedCount).toBe(5);
    expect(result.unassignedCount).toBe(2);
    expect(result.items).toHaveLength(7); // 5 assigned + 2 unassigned
  });

  it("14. null editorial → empty state", () => {
    const result = adaptEditorial(null);
    expect(result.items).toEqual([]);
    expect(result.candidateCount).toBe(0);
  });

  it("15. assigned events appear in role order", () => {
    const result = adaptEditorial(makeEditorial());
    const assigned = result.items.filter((i) => i.role !== null);
    expect(assigned[0].role).toBe("Hook");
    expect(assigned[1].role).toBe("Context");
    expect(assigned[2].role).toBe("Pivot");
    expect(assigned[3].role).toBe("Amplifier");
    expect(assigned[4].role).toBe("Closer");
  });

  it("16. unassigned events have null role and reason", () => {
    const result = adaptEditorial(makeEditorial());
    const unassigned = result.items.filter((i) => i.role === null);
    expect(unassigned).toHaveLength(2);
    expect(unassigned[0].reason).toBe("no_role_match");
  });

  it("17. missing role (contradiction) → simply skipped", () => {
    const ed = makeEditorial();
    delete ed.role_assignment.contradiction; // was never set
    const result = adaptEditorial(ed);
    const roles = result.items.filter((i) => i.role !== null).map((i) => i.role);
    expect(roles).not.toContain("Contradiction");
  });

  it("18. all roles empty → only unassigned returned", () => {
    const ed = makeEditorial({
      role_assignment: {},
      selected_events: 0,
      unassigned_events: 3,
      unassigned: [
        { event: "Event A", type: "research", reason: "no_role_match" },
        { event: "Event B", type: "research", reason: "no_role_match" },
        { event: "Event C", type: "research", reason: "low_score" },
      ],
    });
    const result = adaptEditorial(ed);
    expect(result.items.filter((i) => i.role !== null)).toHaveLength(0);
    expect(result.items.filter((i) => i.role === null)).toHaveLength(3);
  });

  it("19. no unassigned → all events have roles", () => {
    const ed = makeEditorial({ unassigned: [], unassigned_events: 0 });
    const result = adaptEditorial(ed);
    expect(result.items.every((i) => i.role !== null)).toBe(true);
  });

  it("20. unassigned with empty reason", () => {
    const ed = makeEditorial({ unassigned: [{ event: "no reason", type: "unknown", reason: "" }] });
    const result = adaptEditorial(ed);
    expect(result.items.find((i) => i.title === "no reason")?.reason).toBe("");
  });
});

// ════════════════════════════════════════════════════════════
// adaptSourceHealth  (7 cases)
// ════════════════════════════════════════════════════════════

describe("adaptSourceHealth", () => {
  it("21. aggregates multiple sources correctly", () => {
    const result = adaptSourceHealth(RECORDS_MIXED);
    expect(result.sources).toHaveLength(3);
    const ars = result.sources.find((s) => s.source === "Ars Technica")!;
    expect(ars.ok).toBe(1);
    expect(ars.error).toBe(1);
    expect(ars.total).toBe(2);
    expect(ars.successRate).toBe(0.5);
  });

  it("22. empty records → empty sources", () => {
    const result = adaptSourceHealth([]);
    expect(result.sources).toEqual([]);
  });

  it("23. single source with all ok", () => {
    const result = adaptSourceHealth(RECORDS_3_OK.filter((r) => r.source_name === "Ars Technica"));
    expect(result.sources).toHaveLength(1);
    expect(result.sources[0].successRate).toBe(1);
  });

  it("24. all-error source has successRate 0", () => {
    const records = [makeRecord({ status: "error" }), makeRecord({ status: "error" })];
    const result = adaptSourceHealth(records);
    expect(result.sources[0].successRate).toBe(0);
  });

  it("25. avgLatencyMs is rounded to integer", () => {
    const records = [
      makeRecord({ latency_ms: 100, source_name: "TestSrc" }),
      makeRecord({ latency_ms: 200, source_name: "TestSrc" }),
    ];
    const result = adaptSourceHealth(records);
    expect(result.sources[0].avgLatencyMs).toBe(150);
  });

  it("26. sources sorted by total descending", () => {
    const result = adaptSourceHealth(RECORDS_MIXED);
    expect(result.sources[0].total).toBeGreaterThanOrEqual(result.sources[1].total);
    expect(result.sources[1].total).toBeGreaterThanOrEqual(result.sources[2].total);
  });

  it("27. zero-latency records don't break average", () => {
    const records = [makeRecord({ latency_ms: 0, status: "error" })];
    const result = adaptSourceHealth(records);
    expect(result.sources[0].avgLatencyMs).toBe(0);
  });
});

// ════════════════════════════════════════════════════════════
// adaptPipelineHealth  (5 cases — structural only, no fetch/editorial)
// ════════════════════════════════════════════════════════════

describe("adaptPipelineHealth", () => {

  it("28. full fingerprint — all structural fields populated", () => {
    const result = adaptPipelineHealth(makeFingerprint());
    expect(result.evidenceCount).toBe(152);
    expect(result.clusterCount).toBe(24);
    expect(result.orphanRatio).toBeCloseTo(0.4474);
    expect(result.clusterEntropy).toBeCloseTo(4.2665);
    expect(result.aggregationRatio).toBeCloseTo(3.5);
    expect(result.eventYield).toBeCloseTo(0.0461);
  });

  it("29. null fingerprint → all fields are null", () => {
    const result = adaptPipelineHealth(null);
    expect(result.evidenceCount).toBeNull();
    expect(result.clusterCount).toBeNull();
    expect(result.orphanRatio).toBeNull();
    expect(result.clusterEntropy).toBeNull();
    expect(result.aggregationRatio).toBeNull();
    expect(result.eventYield).toBeNull();
  });

  it("30. zero-valued fields preserved as 0 (not null)", () => {
    const fp = makeFingerprint({ evidence_count: 0, cluster_count: 0, orphan_ratio: 0, cluster_entropy: 0, aggregation_ratio: 0, event_yield: 0 });
    const result = adaptPipelineHealth(fp);
    expect(result.evidenceCount).toBe(0);
    expect(result.clusterCount).toBe(0);
    expect(result.orphanRatio).toBe(0);
    expect(result.clusterEntropy).toBe(0);
  });

  it("31. partial fingerprint — missing optional fields preserved as given", () => {
    const result = adaptPipelineHealth(makeFingerprint({ event_yield: 0.08 }));
    expect(result.eventYield).toBeCloseTo(0.08);
    expect(result.evidenceCount).toBe(152); // from fixture default
  });

  it("32. high values — orphanRatio 0.9, large clusters", () => {
    const fp = makeFingerprint({ evidence_count: 500, cluster_count: 50, orphan_ratio: 0.9, cluster_entropy: 5.6 });
    const result = adaptPipelineHealth(fp);
    expect(result.evidenceCount).toBe(500);
    expect(result.clusterCount).toBe(50);
    expect(result.orphanRatio).toBeCloseTo(0.9);
    expect(result.clusterEntropy).toBeCloseTo(5.6);
  });
});

// ════════════════════════════════════════════════════════════
// adaptDailyMetrics  (7 cases)
// ════════════════════════════════════════════════════════════

describe("adaptDailyMetrics", () => {
  const FP = makeFingerprint();

  it("36. full data — all fields mapped", () => {
    const result = adaptDailyMetrics(RECORDS_MIXED, 7, 5, FP);
    expect(result.date).toBe("2026-06-08");
    expect(result.fetchTotal).toBe(5);
    expect(result.fetchOk).toBe(3);
    expect(result.candidates).toBe(7);
    expect(result.published).toBe(5);
    expect(result.sourceCount).toBe(3);
    expect(result.orphanRatio).toBeCloseTo(0.4474);
    expect(result.clusterCount).toBe(24);
    expect(result.clusterEntropy).toBeCloseTo(4.2665);
    expect(result.meanClusterSize).toBeCloseTo(3.5);
    expect(result.eventYield).toBeCloseTo(0.0461);
  });

  it("37. null candidates/published → fall to 0", () => {
    const result = adaptDailyMetrics(RECORDS_3_OK, null, null, FP);
    expect(result.candidates).toBe(0);
    expect(result.published).toBe(0);
  });

  it("38. null fingerprint → fingerprint fields fall to 0", () => {
    const result = adaptDailyMetrics(RECORDS_3_OK, 7, 5, null);
    expect(result.orphanRatio).toBe(0);
    expect(result.clusterCount).toBe(0);
    expect(result.clusterEntropy).toBe(0);
    expect(result.meanClusterSize).toBe(0);
    expect(result.eventYield).toBe(0);
  });

  it("39. empty records → empty date, no sources", () => {
    const result = adaptDailyMetrics([], 0, 0, null);
    expect(result.date).toBe("");
    expect(result.fetchTotal).toBe(0);
    expect(result.sourceCount).toBe(0);
  });

  it("40. all error records — fetchOk is zero", () => {
    const records = [makeRecord({ status: "error" }), makeRecord({ status: "error" })];
    const result = adaptDailyMetrics(records, 0, 0, null);
    expect(result.fetchTotal).toBe(2);
    expect(result.fetchOk).toBe(0);
  });

  it("41. sourceCount correctly deduplicates", () => {
    const records = [
      makeRecord({ source_name: "A" }),
      makeRecord({ source_name: "A" }),
      makeRecord({ source_name: "B" }),
    ];
    const result = adaptDailyMetrics(records, 0, 0, null);
    expect(result.sourceCount).toBe(2);
  });

  it("42. all fingerprint values passed through correctly", () => {
    const customFp = makeFingerprint({
      evidence_count: 200,
      cluster_count: 30,
      orphan_ratio: 0.55,
      cluster_entropy: 5.0,
      mean_cluster_size: 4.0,
      event_yield: 0.08,
    });
    const result = adaptDailyMetrics(RECORDS_3_OK, 10, 8, customFp);
    expect(result.orphanRatio).toBeCloseTo(0.55);
    expect(result.clusterCount).toBe(30);
    expect(result.clusterEntropy).toBeCloseTo(5.0);
  });
});
