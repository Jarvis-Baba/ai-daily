// ============================================================
// Static HTML renderer. Input: DashboardState JSON → Output: self-contained HTML.
// Usage: npx tsx render_html.ts < dashboard_state.json > dashboard.html
//    or: npx tsx render_html.ts dashboard_state.json dashboard.html
// ============================================================

import fs from "fs";
import type { DashboardState } from "./state/dashboard";

// ── Helpers ──

function pct(v: number): string {
  return (v * 100).toFixed(1) + "%";
}

function bar(value: number, max: number, color: string): string {
  const w = max > 0 ? Math.max(1, Math.round((value / max) * 100)) : 0;
  return `<div class="bar-wrap"><div class="bar" style="width:${w}%;background:${color}"></div><span>${value}</span></div>`;
}

function nullDash(v: number | null): string {
  return v === null ? "—" : String(v);
}

function statusDot(success: number): string {
  if (success >= 0.9) return '<span style="color:#22c55e">●</span>';
  if (success >= 0.5) return '<span style="color:#f59e0b">●</span>';
  return '<span style="color:#ef4444">●</span>';
}

const ROLE_COLORS: Record<string, string> = {
  Hook: "#8b5cf6",
  Context: "#3b82f6",
  Pivot: "#f59e0b",
  Amplifier: "#ef4444",
  Contradiction: "#ec4899",
  Closer: "#22c55e",
};

// ── Module renderers ──

function renderFunnel(s: DashboardState): string {
  const steps = s.funnel.steps;
  const max = Math.max(...steps.map((x) => x.count), 1);
  const colors = ["#6366f1", "#22c55e", "#f59e0b", "#ef4444"];

  const rows = steps
    .map(
      (step, i) => `
    <div class="funnel-row">
      <div class="funnel-label">${step.label}</div>
      ${bar(step.count, max, colors[i])}
      <div class="funnel-pct">${i === 0 ? "—" : pct(step.pctOfPrev)}</div>
    </div>`
    )
    .join("");

  return `
  <section>
    <h2>📊 Funnel</h2>
    <div class="funnel">${rows}</div>
    <div class="muted">pctOfPrev 显示在右侧</div>
  </section>`;
}

function renderEvents(s: DashboardState): string {
  const items = s.events.items
    .map((e) => {
      const tag = e.role
        ? `<span class="tag" style="background:${ROLE_COLORS[e.role] || "#888"}">${e.role}</span>`
        : `<span class="tag unassigned">unassigned</span>`;
      const reason = e.reason ? `<span class="reason">${e.reason}</span>` : "";
      return `<div class="event-item">${tag} <span class="event-title">${esc(e.title)}</span> <span class="event-type">${esc(e.type)}</span> ${reason}</div>`;
    })
    .join("");

  return `
  <section>
    <h2>📰 Events</h2>
    <div class="events-meta">
      <span>Candidates: <strong>${s.events.candidateCount}</strong></span>
      <span>Selected: <strong>${s.events.selectedCount}</strong></span>
      <span>Unassigned: <strong>${s.events.unassignedCount}</strong></span>
    </div>
    <div class="events">${items}</div>
  </section>`;
}

function renderSourceHealth(s: DashboardState): string {
  const rows = s.sourceHealth.sources
    .map(
      (src) => `
    <tr>
      <td>${statusDot(src.successRate)}</td>
      <td>${esc(src.source)}</td>
      <td class="num">${src.ok}</td>
      <td class="num">${src.error}</td>
      <td class="num">${pct(src.successRate)}</td>
      <td class="num">${src.avgLatencyMs}ms</td>
    </tr>`
    )
    .join("");

  return `
  <section>
    <h2>🏥 Source Health</h2>
    <table>
      <thead><tr><th></th><th>Source</th><th>OK</th><th>Err</th><th>Rate</th><th>Avg Latency</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </section>`;
}

function renderStructuralHealth(s: DashboardState): string {
  const m = s.pipelineHealth;
  if (m.evidenceCount === null && m.clusterCount === null) {
    return `<section><h2>🧬 Structural Health</h2><div class="muted">Fingerprint data not available for this date.</div></section>`;
  }

  const cards = [
    { label: "Evidence",   value: nullDash(m.evidenceCount),    color: "#6366f1" },
    { label: "Clusters",   value: nullDash(m.clusterCount),     color: "#8b5cf6" },
    { label: "Orphan %",   value: m.orphanRatio  !== null ? pct(m.orphanRatio)  : "—", color: m.orphanRatio !== null && m.orphanRatio > 0.4 ? "#ef4444" : "#22c55e" },
    { label: "Entropy",    value: m.clusterEntropy !== null ? m.clusterEntropy.toFixed(2) : "—", color: "#f59e0b" },
    { label: "Aggregation",value: m.aggregationRatio !== null ? m.aggregationRatio.toFixed(1) : "—", color: "#3b82f6" },
    { label: "Yield",      value: m.eventYield !== null ? pct(m.eventYield) : "—", color: "#22c55e" },
  ];

  const items = cards
    .map(
      (c) => `
    <div class="struct-card" style="border-left: 3px solid ${c.color}">
      <div class="struct-label">${c.label}</div>
      <div class="struct-value" style="color:${c.color}">${c.value}</div>
    </div>`
    )
    .join("");

  return `
  <section class="struct-hero">
    <h2>🧬 Structural Health</h2>
    <div class="struct-grid">${items}</div>
    <div class="muted">AI Daily 独有指标 — 来自聚类和主题管线，非普通 RSS Reader 可提供</div>
  </section>`;
}

function renderDailyMetrics(s: DashboardState): string {
  const m = s.dailyMetrics;
  return `
  <section>
    <h2>📈 Daily Metrics</h2>
    <div class="metric-grid">
      ${kv("Date", m.date)}
      ${kv("Fetch Total", m.fetchTotal)}
      ${kv("Fetch OK", m.fetchOk)}
      ${kv("Candidates", m.candidates)}
      ${kv("Published", m.published)}
      ${kv("Sources", m.sourceCount)}
    </div>
  </section>`;
}

function renderInbox(s: DashboardState): string {
  const rows = s.inbox.items
    .map(
      (item, i) => `
    <tr>
      <td class="num">${i + 1}</td>
      <td><a href="${esc(item.url)}" target="_blank">${truncateUrl(item.url)}</a></td>
      <td>${esc(item.source)}</td>
      <td class="num">${item.latencyMs}ms</td>
      <td>${item.timestamp}</td>
    </tr>`
    )
    .join("");

  return `
  <section>
    <h2>📬 Inbox <span class="muted">(${s.inbox.items.length} items)</span></h2>
    <div class="inbox-wrap">
    <table>
      <thead><tr><th>#</th><th>URL</th><th>Source</th><th>Latency</th><th>Timestamp</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    </div>
  </section>`;
}

// ── Tiny template helpers ──

function kv(label: string, value: string | number): string {
  return `<div class="kv"><span class="kv-label">${label}</span><span class="kv-value">${value}</span></div>`;
}

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function truncateUrl(url: string, max = 70): string {
  return url.length > max ? url.slice(0, max) + "…" : url;
}

// ── Page shell ──

const CSS = /*css*/ `
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; line-height: 1.5; }
header { text-align: center; padding: 32px 0; border-bottom: 1px solid #1e293b; margin-bottom: 32px; }
header h1 { font-size: 24px; font-weight: 700; }
header .date { color: #94a3b8; margin-top: 4px; }
section { background: #1e293b; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; }
h2 { font-size: 18px; font-weight: 600; margin-bottom: 16px; }
.muted { color: #64748b; font-size: 13px; margin-top: 8px; }
a { color: #60a5fa; text-decoration: none; }
a:hover { text-decoration: underline; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid #334155; font-size: 14px; }
th { color: #94a3b8; font-weight: 500; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
.num { text-align: right; font-variant-numeric: tabular-nums; }

.funnel-row { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.funnel-label { width: 140px; font-size: 14px; color: #94a3b8; text-align: right; flex-shrink: 0; }
.funnel-pct { width: 60px; font-size: 13px; color: #94a3b8; text-align: right; flex-shrink: 0; }
.bar-wrap { flex: 1; display: flex; align-items: center; gap: 10px; }
.bar { height: 24px; border-radius: 4px; min-width: 2px; transition: width 0.3s; }
.bar-wrap span { font-size: 13px; color: #e2e8f0; white-space: nowrap; }

.events-meta { display: flex; gap: 24px; margin-bottom: 16px; font-size: 14px; color: #94a3b8; }
.event-item { padding: 8px 0; border-bottom: 1px solid #1e293b; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 14px; }
.event-title { flex: 1; }
.event-type { color: #64748b; font-size: 12px; }
.tag { padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; color: #fff; white-space: nowrap; }
.tag.unassigned { background: #334155; color: #94a3b8; }
.reason { color: #f59e0b; font-size: 12px; }

.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; }
.kv { background: #0f172a; border-radius: 8px; padding: 10px 14px; }
.kv-label { font-size: 12px; color: #64748b; display: block; }
.kv-value { font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; }

.inbox-wrap { max-height: 480px; overflow-y: auto; }

.struct-hero section { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); }
.struct-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.struct-card { background: #0f172a; border-radius: 8px; padding: 18px 20px; }
.struct-label { font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
.struct-value { font-size: 32px; font-weight: 700; font-variant-numeric: tabular-nums; }

footer { text-align: center; color: #475569; font-size: 12px; padding: 24px 0; }
`;

function htmlPage(state: DashboardState, date: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Daily Dashboard — ${date}</title>
<style>${CSS}</style>
</head>
<body>
<header>
  <h1>🧠 AI Daily Dashboard</h1>
  <div class="date">${date}</div>
</header>
<main>
	${renderFunnel(state)}
	${renderStructuralHealth(state)}
	<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
	${renderDailyMetrics(state)}
	${renderEvents(state)}
	</div>
	${renderSourceHealth(state)}
	${renderInbox(state)}
</main>
<footer>Generated at ${new Date().toISOString()} · AI Daily Dashboard v0.1</footer>
</body>
</html>`;
}

// ── CLI ──

if (require.main === module) {
  let input: string;

  const arg = process.argv[2];
  if (arg && fs.existsSync(arg)) {
    input = fs.readFileSync(arg, "utf-8");
  } else {
    // Read from stdin
    input = fs.readFileSync(0, "utf-8");
  }

  const state = JSON.parse(input) as DashboardState;
  const date = state.dailyMetrics.date || "unknown";
  const html = htmlPage(state, date);

  const outPath = process.argv[3] || process.argv[2]?.replace(".json", ".html") || null;
  if (outPath && outPath.endsWith(".html")) {
    fs.writeFileSync(outPath, html, "utf-8");
    console.error(`Wrote ${outPath}`);
  } else {
    process.stdout.write(html);
  }
}
