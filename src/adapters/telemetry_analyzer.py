"""L0 Telemetry Analyzer — reads JSONL telemetry and produces distribution reports.

Answers the three pre-L1 questions:
  1. Fetch distribution (playwright / http / jina %)
  2. Artifact size histogram (<5KB / 5-20KB / 20-100KB / >100KB)
  3. Media density (images per artifact, screenshots per run)

Also tracks across-day trends for temporal stability analysis.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

SIZE_BUCKETS = [
    ("<5KB", 0, 5_000),
    ("5-20KB", 5_000, 20_000),
    ("20-100KB", 20_000, 100_000),
    (">100KB", 100_000, float("inf")),
]


def _bucket_size(content_length: int) -> str:
    for label, lo, hi in SIZE_BUCKETS:
        if lo <= content_length < hi:
            return label
    return ">100KB"


def analyze_day(telemetry_dir: str, date_str: str | None = None) -> dict:
    """Analyze a single day's telemetry. Returns a stats dict."""
    # Default to the local date — telemetry filenames are keyed to
    # report_date (local), see telemetry.py.
    date_str = date_str or datetime.now().strftime("%Y%m%d")
    path = Path(telemetry_dir) / f"{date_str}.jsonl"
    if not path.exists():
        return {"date": date_str, "total_attempts": 0, "error": "no telemetry file"}

    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not records:
        return {"date": date_str, "total_attempts": 0, "error": "empty telemetry file"}

    successes = [r for r in records if r.get("status") == "success"]
    failures = [r for r in records if r.get("status") == "failed"]
    skipped = [r for r in records if r.get("status") == "skipped"]
    total_attempts = len([r for r in records if r.get("status") != "skipped"])

    # ── 1. Fetch distribution ──
    fetcher_counts = defaultdict(int)
    for r in successes:
        fetcher_counts[r.get("fetcher", "unknown")] += 1
    fetch_dist = dict(fetcher_counts)
    if total_attempts > 0:
        fetch_dist_pct = {
            k: round(v / total_attempts * 100, 1) for k, v in fetch_dist.items()
        }
    else:
        fetch_dist_pct = {}

    # ── 2. Size histogram ──
    size_buckets = defaultdict(int)
    for r in successes:
        size_buckets[_bucket_size(r.get("content_length", 0))] += 1
    size_histogram = {label: size_buckets.get(label, 0) for label, _, _ in SIZE_BUCKETS}

    # ── 3. Media density ──
    total_images = sum(r.get("media_count", 0) for r in successes)
    total_screenshots = sum(1 for r in successes if r.get("has_screenshot"))
    avg_images = round(total_images / len(successes), 1) if successes else 0

    # ── 4. Latency stats ──
    latencies = [r["latency_ms"] for r in successes if r.get("latency_ms", 0) > 0]
    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0

    # ── 5. Source-level breakdown ──
    source_stats = defaultdict(lambda: {"success": 0, "failed": 0, "fetchers": defaultdict(int)})
    for r in successes:
        src = r.get("source_name", "unknown")
        source_stats[src]["success"] += 1
        source_stats[src]["fetchers"][r.get("fetcher", "?")] += 1
    for r in failures:
        src = r.get("source_name", url_to_source(r.get("url", "")))
        source_stats[src]["failed"] += 1

    # ── 6. Content length stats ──
    content_lengths = [r.get("content_length", 0) for r in successes]
    avg_size = round(sum(content_lengths) / len(content_lengths)) if content_lengths else 0
    min_size = min(content_lengths) if content_lengths else 0
    max_size = max(content_lengths) if content_lengths else 0

    return {
        "date": date_str,
        "total_attempts": total_attempts,
        "successes": len(successes),
        "failures": len(failures),
        "skipped": len(skipped),
        "success_rate": round(len(successes) / total_attempts * 100, 1) if total_attempts else 0,
        "fetch_distribution": fetch_dist_pct,
        "fetch_distribution_raw": fetch_dist,
        "size_histogram": size_histogram,
        "content_length": {"avg": avg_size, "min": min_size, "max": max_size},
        "media": {"total_images": total_images, "total_screenshots": total_screenshots, "avg_images_per_artifact": avg_images},
        "latency": {"p50_ms": p50, "p95_ms": p95, "p99_ms": p99},
        "sources": {k: dict(v) for k, v in source_stats.items()},
    }


def url_to_source(url: str) -> str:
    """Crude hostname extraction for failed records without source_name."""
    from urllib.parse import urlparse
    try:
        return urlparse(url).hostname or url
    except Exception:
        return url


def analyze_range(telemetry_dir: str, days: int = 7) -> list[dict]:
    """Analyze the last N days of telemetry. Returns list of daily stats dicts."""
    from datetime import timedelta
    results = []
    today = datetime.now()  # local — matches telemetry filename keys
    for i in range(days):
        d = (today - timedelta(days=i)).strftime("%Y%m%d")
        stats = analyze_day(telemetry_dir, d)
        results.append(stats)
    return list(reversed(results))


def format_report(stats: dict) -> str:
    """Format a single-day stats dict as a readable report."""
    if stats.get("error"):
        return f"  {stats['date']}: {stats['error']}"

    lines = [
        f"  {stats['date']} | attempts={stats['total_attempts']} "
        f"success={stats['successes']} failed={stats['failures']} "
        f"rate={stats['success_rate']}%",
        f"  Fetch: {stats['fetch_distribution']}",
        f"  Size:  {stats['size_histogram']} | avg={stats['content_length']['avg']}B "
        f"min={stats['content_length']['min']}B max={stats['content_length']['max']}B",
        f"  Media: {stats['media']['total_images']} imgs, "
        f"{stats['media']['total_screenshots']} screenshots, "
        f"avg {stats['media']['avg_images_per_artifact']} imgs/artifact",
        f"  Latency: p50={stats['latency']['p50_ms']}ms "
        f"p95={stats['latency']['p95_ms']}ms p99={stats['latency']['p99_ms']}ms",
    ]

    if stats.get("sources"):
        lines.append("  Sources:")
        for src, s in sorted(stats["sources"].items()):
            fetchers = ", ".join(f"{k}:{v}" for k, v in s.get("fetchers", {}).items())
            extra = f" failed={s['failed']}" if s.get("failed") else ""
            lines.append(f"    {src}: {s['success']} ok{extra} [{fetchers}]")

    return "\n".join(lines)


def format_trend(daily_stats: list[dict]) -> str:
    """Format multi-day stats as a trend report."""
    valid = [s for s in daily_stats if not s.get("error") and s.get("total_attempts", 0) > 0]
    if not valid:
        return "  No data yet."

    lines = ["## L0 Trend Summary", ""]

    # Success rate trend
    rates = [s["success_rate"] for s in valid]
    lines.append(f"Success rate: {rates} → avg {round(sum(rates)/len(rates),1)}%")

    # Fetch distribution consolidation
    fetch_totals = defaultdict(int)
    for s in valid:
        for fetcher, count in s.get("fetch_distribution_raw", {}).items():
            fetch_totals[fetcher] += count
    total = sum(fetch_totals.values())
    fetch_str = ", ".join(f"{k}: {round(v/total*100,1)}%" for k, v in sorted(fetch_totals.items()))
    lines.append(f"Fetch distribution (all days): {fetch_str}")

    # Size
    all_sizes = [s["content_length"]["avg"] for s in valid]
    lines.append(f"Avg content length range: {min(all_sizes)}–{max(all_sizes)} chars")

    # Media
    all_imgs = [s["media"]["avg_images_per_artifact"] for s in valid]
    lines.append(f"Avg images/artifact range: {min(all_imgs)}–{max(all_imgs)}")

    # Sources
    source_set = set()
    for s in valid:
        source_set.update(s.get("sources", {}).keys())
    lines.append(f"Unique sources: {len(source_set)} — {', '.join(sorted(source_set))}")

    lines.append("")
    lines.append(f"Days of data: {len(valid)}")
    return "\n".join(lines)
