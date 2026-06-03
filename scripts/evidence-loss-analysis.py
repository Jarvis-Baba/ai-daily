#!/usr/bin/env python3
"""Evidence Loss Analysis — classify why 98.6% of Evidence doesn't become Events.

Heuristic classification of dropped evidence:
  aggregated      — multiple evidence rolled into one event (not really dropped)
  duplicate       — near-identical statements from same source
  too_granular    — atomic claim too narrow to be an event
  opinion         — source_statement with opinion markers (声称/认为/可能)
  low_confidence  — evidence_strength < 0.4 or source_reliability < 0.5
  index_page      — from low-density index/nav pages
  no_event_match  — verifiable_fact that doesn't match any event (true ontology gap)

Also computes:
  aggregation_ratio = supporting_evidence_pool / event_count
  (approximated by source-domain evidence available per event)

Usage:
    PYTHONPATH=. python3 scripts/evidence-loss-analysis.py

Output:
    output/artifacts/calibration/dropped_evidence_report.json
"""

import json
import sys
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models.evidence import (
    Evidence, EvidenceSource, EvidenceConfidence, SupportingMaterial,
)

# ── Classification rules ──

# Known low-density index pages (no fact-bearing content)
INDEX_PAGE_PATTERNS = [
    "github.blog/",
    "simonwillison.net/",
]

# Opinion markers in Chinese statements
OPINION_MARKERS = [
    "认为", "可能", "将", "预计", "有望", "或许", "也许",
    "应该", "可以预见", "趋势", "未来", "前景", "意义",
    "重要", "关键", "核心", "根本", "本质",
]

# Event type keywords for ontology mapping
EVENT_TYPE_KEYWORDS = {
    "capital": ["融资", "估值", "投资", "收购", "IPO", "上市", "基金", "亿美元", "亿元", "募资"],
    "capability": ["发布", "推出", "开源", "上线", "更新", "升级", "新版", "发布", "模型"],
    "behavioral": ["用户", "开发者", "采用", "迁移", "增长", "下降", "使用率"],
    "research_result": ["论文", "基准", "测试", "性能", "准确率", "F1", "BLEU", "experiment", "benchmark"],
    "governance": ["安全", "漏洞", "攻击", "政策", "合规", "许可", "隐私", "泄露", "CVE"],
    "ecosystem": ["合作", "伙伴", "平台", "生态", "标准", "联盟", "集成"],
}

# Statements that are metadata about the source, not actual claims
METADATA_PATTERNS = [
    r"^.*(has a|页面|网站|blog|website|homepage|research page).*$",
    r"^.*(URL|网址|链接).*$",
    r"^.*(available at|可在|访问).*$",
]


def load_all_evidence(base_dir: str) -> list[Evidence]:
    evidence_dir = Path(base_dir) / "evidence"
    if not evidence_dir.exists():
        return []
    result = []
    for ef in sorted(evidence_dir.glob("E-*.json")):
        try:
            data = json.loads(ef.read_text())
            src = data["source"]
            conf = data["confidence"]
            sup = data.get("supporting_material", {})
            result.append(Evidence(
                evidence_id=data["evidence_id"],
                fact_type=data.get("fact_type", "source_statement"),
                source=EvidenceSource(
                    name=src.get("name", ""), type=src.get("type", "unknown"),
                    url=src.get("url", ""), published_at=src.get("published_at", ""),
                ),
                statement=data.get("statement", ""),
                attribution=data.get("attribution", ""),
                supporting_material=SupportingMaterial(
                    quote=sup.get("quote", ""),
                    artifact_refs=sup.get("artifact_refs", []),
                    screenshot_refs=sup.get("screenshot_refs", []),
                ),
                confidence=EvidenceConfidence(
                    source_reliability=conf.get("source_reliability", 0.5),
                    evidence_strength=conf.get("evidence_strength", 0.5),
                    verification_status=conf.get("verification_status", "direct_source"),
                ),
            ))
        except Exception:
            pass
    return result


def load_events_from_telemetry(base_dir: str) -> list[dict]:
    """Load event_ledger from ontology_telemetry.json or ab-replay data."""
    # Try ontology telemetry first
    telemetry_path = Path(base_dir) / "calibration" / "ontology_telemetry.json"
    if telemetry_path.exists():
        tel = json.loads(telemetry_path.read_text())
        return [
            {"title": a.get("event_title", ""),
             "source": a.get("event_source", ""),
             "link": a.get("event_link", ""),
             "type": a.get("event_type", "")}
            for a in tel.get("attribution_log", [])
        ]

    # Try A/B replay for v2 events
    replay_files = sorted(Path(base_dir).glob("calibration/ab-replay-*.json"))
    if replay_files:
        replay = json.loads(replay_files[-1].read_text())
        # We only have type_distribution, not full event_ledger. Use event-replay instead.
    replay_files = sorted(Path(base_dir).glob("calibration/event-replay-*.json"))
    if replay_files:
        replay = json.loads(replay_files[-1].read_text())
        t0 = replay.get("temperatures", {}).get("t0.0", {})
        events_json = t0.get("events", [])
        if events_json:
            return events_json
    return []


def evidence_matches_event(ev: Evidence, events: list[dict]) -> bool:
    """Check if evidence could support any event (keyword + domain overlap)."""
    ev_domain = ev.source.name.lower()
    ev_stmt = ev.statement.lower()
    ev_words = set(ev_stmt.split())

    for event in events:
        event_src = event.get("source", "").lower()
        event_title = event.get("title", "").lower()
        event_words = set(event_title.split())

        # Domain-level match (loose)
        domain_match = (
            ev_domain in event_src
            or event_src in ev_domain
            or any(w in ev_domain for w in event_src.split() if len(w) > 3)
        )
        if not domain_match:
            continue

        # Keyword overlap between evidence statement and event title
        if not ev_words or not event_words:
            continue
        overlap = len(ev_words & event_words) / max(min(len(ev_words), len(event_words)), 1)
        if overlap > 0.15:
            return True

        # Named entity check: same product/company name
        # Extract potential named entities (>3 chars, capitalized or Chinese)
        ev_entities = {w for w in ev_words if len(w) > 3}
        event_entities = {w for w in event_words if len(w) > 3}
        if ev_entities & event_entities:
            return True

    return False


def classify_evidence(ev: Evidence, all_evidence: list[Evidence],
                      events: list[dict]) -> str:
    """Classify why this evidence was dropped (or aggregated into an event)."""

    stmt = ev.statement.strip()
    stmt_lower = stmt.lower()
    source_url = ev.source.url.lower()

    # 1. Index page check
    for pattern in INDEX_PAGE_PATTERNS:
        if pattern in source_url:
            return "index_page"

    # 2. Aggregated: evidence could support an existing event
    if events and evidence_matches_event(ev, events):
        return "aggregated"

    # 3. Metadata/boilerplate
    for pat in METADATA_PATTERNS:
        if re.match(pat, stmt, re.IGNORECASE):
            return "too_granular"

    # 4. Too granular
    if len(stmt) < 60:
        return "too_granular"

    # 5. Low confidence
    if ev.confidence.evidence_strength < 0.4:
        return "low_confidence"
    if ev.confidence.source_reliability < 0.5:
        return "low_confidence"

    # 6. Opinion markers
    if ev.fact_type == "source_statement":
        opinion_count = sum(1 for m in OPINION_MARKERS if m in stmt)
        if opinion_count >= 2:
            return "opinion"

    # 7. Duplicate check
    for other in all_evidence:
        if other.evidence_id == ev.evidence_id:
            continue
        if other.source.name.lower() != ev.source.name.lower():
            continue
        words_a = set(stmt_lower.split())
        words_b = set(other.statement.lower().split())
        if not words_a or not words_b:
            continue
        overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
        if overlap > 0.7:
            return "duplicate"

    # 8. Ontology mismatch
    keyword_hits = 0
    for etype, keywords in EVENT_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in stmt:
                keyword_hits += 1
                break
    if keyword_hits == 0:
        return "ontology_mismatch"

    if ev.fact_type == "verifiable_fact":
        return "ontology_mismatch"

    return "other"


def compute_aggregation_ratio(evidence_list: list[Evidence],
                               event_ledger: list[dict],
                               stage=None) -> dict:
    """Compute how many evidence items could support each event.

    Returns {event_title: supporting_evidence_count} and overall ratio.
    """
    event_support = {}
    for event in event_ledger:
        src = event.get("source", "").lower()
        title = event.get("title", "")

        # Count evidence from matching source domains
        supporting = []
        for ev in evidence_list:
            domain = ev.source.name.lower()
            # Source domain match
            if stage and stage._source_matches_evidence(
                event.get("source", ""), event.get("link", ""),
                ev.source.name, ev.source.url,
            ):
                supporting.append(ev.evidence_id)
            elif not stage:
                # Fallback: domain substring match
                if src in domain or domain in src:
                    supporting.append(ev.evidence_id)

        event_support[title] = {
            "supporting_count": len(supporting),
            "supporting_ids": supporting[:10],  # cap at 10 for readability
        }

    total_supporting = sum(v["supporting_count"] for v in event_support.values())
    return {
        "per_event": event_support,
        "total_supporting_evidence": total_supporting,
        "event_count": len(event_ledger),
        "aggregation_ratio": total_supporting / max(len(event_ledger), 1),
        "evidence_pool_coverage": total_supporting / max(len(evidence_list), 1),
    }


def main():
    from src.config.loader import load_config
    from src.stages.synthesize import SynthesizeStage
    from src.main import build_llm_adapter

    config = load_config("config.yaml")
    base_dir = config.artifact.output_dir if hasattr(config, "artifact") else "./output/artifacts"

    evidence_list = load_all_evidence(base_dir)
    if not evidence_list:
        print("No evidence found. Run the pipeline first.")
        sys.exit(1)

    # Load events from telemetry for evidence-level matching
    events = load_events_from_telemetry(base_dir)
    print(f"Events loaded from telemetry: {len(events)}")
    if events:
        for e in events:
            print(f"  [{e.get('type', '?')}] {e.get('title', '')[:80]} | {e.get('source', '')}")
    print()

    # Use SynthesizeStage for source matching
    llm = build_llm_adapter(config)
    stage = SynthesizeStage(llm_adapter=llm)

    # Classify all evidence
    classification: dict[str, list[dict]] = defaultdict(list)
    for ev in evidence_list:
        reason = classify_evidence(ev, evidence_list, events)
        classification[reason].append({
            "evidence_id": ev.evidence_id,
            "statement": ev.statement[:200],
            "fact_type": ev.fact_type,
            "source": ev.source.name,
            "source_type": ev.source.type,
            "evidence_strength": ev.confidence.evidence_strength,
            "source_reliability": ev.confidence.source_reliability,
            "drop_reason": reason,
        })

    # Distribution
    total = len(evidence_list)
    distribution = {k: len(v) for k, v in sorted(classification.items(), key=lambda x: -len(x[1]))}

    # Print report
    print(f"Total Evidence: {total}")
    print(f"Events available: {len(events)}")
    print(f"Events: {[e.get('title','')[:60] for e in events]}")
    print()
    print("=" * 60)
    print("EVIDENCE DROP DISTRIBUTION")
    print("=" * 60)
    for reason, count in distribution.items():
        pct = count / total * 100
        bar = "█" * int(pct / 2)
        print(f"  {reason:20s}  {count:4d} ({pct:5.1f}%)  {bar}")

    # Top dropped by reason
    print()
    print("=" * 60)
    print("TOP DROPPED EVIDENCE BY REASON (sample)")
    print("=" * 60)
    for reason in distribution:
        if reason == "aggregated":
            continue
        items = classification[reason][:3]
        print(f"\n--- {reason} ({distribution[reason]} total) ---")
        for item in items:
            print(f"  [{item['evidence_id']}] [{item['fact_type']}] {item['source']}")
            print(f"    ES={item['evidence_strength']} SR={item['source_reliability']}")
            print(f"    \"{item['statement'][:150]}\"")

    # Aggregation ratio
    print()
    print("=" * 60)
    print("AGGREGATION ANALYSIS")
    print("=" * 60)

    if events:
        agg = compute_aggregation_ratio(evidence_list, events, stage)
        print(f"Events: {agg['event_count']}")
        print(f"Supporting evidence pool: {agg['total_supporting_evidence']}")
        print(f"Aggregation Ratio: {agg['aggregation_ratio']:.1f}")
        print(f"Evidence Pool Coverage: {agg['evidence_pool_coverage']:.1%}")
        print()
        print("Per-event supporting evidence:")
        for title, info in agg["per_event"].items():
            print(f"  \"{title[:60]}\" → {info['supporting_count']} evidence")
    else:
        agg = {}
        print("No events available for aggregation analysis.")

    # ── Source-level analysis ──
    print()
    print("=" * 60)
    print("PER-SOURCE DROP ANALYSIS")
    print("=" * 60)
    source_evidence = defaultdict(list)
    for ev in evidence_list:
        source_evidence[ev.source.name].append(ev)
    for src_name, evs in sorted(source_evidence.items(), key=lambda x: -len(x[1])):
        src_reasons = Counter(
            classify_evidence(e, evidence_list, events) for e in evs
        )
        aggregated = src_reasons.get("aggregated", 0)
        print(f"  {src_name}: {len(evs)} evidence, {aggregated} aggregated "
              f"({aggregated/max(len(evs),1)*100:.0f}%)")

    # Write report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_evidence": total,
        "total_dropped": total - len(classification.get("aggregated", [])),
        "drop_rate": (total - len(classification.get("aggregated", []))) / max(total, 1),
        "drop_distribution": distribution,
        "drop_distribution_pct": {
            k: round(v / total * 100, 1) for k, v in distribution.items()
        },
        "top_dropped": {
            reason: items[:10] for reason, items in classification.items()
            if reason != "aggregated"
        },
        "aggregation": agg if events else {},
        "verdict": (
            "filtering" if len(classification.get("aggregated", [])) / max(total, 1) < 0.1
            else "aggregating" if len(classification.get("aggregated", [])) / max(total, 1) > 0.3
            else "mixed"
        ),
    }

    out_dir = Path(base_dir) / "calibration"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = out_dir / f"dropped_evidence_report-{ts}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
