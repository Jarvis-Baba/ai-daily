#!/usr/bin/env python3
"""A/B replay: compare ontology v1 (3-type) vs v2 (6-type) adoption rates.

Replays the SAME evidence through L2 synthesis with v1 and v2 prompts,
measuring adoption rate independently of source-matching improvements.

Usage:
    PYTHONPATH=. python3 scripts/ab-ontology-replay.py

Output:
    output/artifacts/calibration/ab-replay-YYYYMMDD-HHMMSS.json
"""

import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.main import build_llm_adapter
from src.config.loader import load_config
from src.models.article import EventLedgerItem
from src.models.evidence import Evidence, EvidenceSource, EvidenceConfidence, SupportingMaterial
from src.stages.synthesize import SynthesizeStage


def load_all_evidence(base_dir: str) -> list:
    """Load all evidence files from disk. Returns list of Evidence objects."""
    evidence_dir = Path(base_dir) / "evidence"
    if not evidence_dir.exists():
        return []
    evidence_list = []
    for ef in sorted(evidence_dir.glob("E-*.json")):
        try:
            data = json.loads(ef.read_text())
            src = data["source"]
            conf = data["confidence"]
            sup = data.get("supporting_material", {})
            ev = Evidence(
                evidence_id=data["evidence_id"],
                fact_type=data.get("fact_type", "source_statement"),
                source=EvidenceSource(
                    name=src.get("name", ""),
                    type=src.get("type", "unknown"),
                    url=src.get("url", ""),
                    published_at=src.get("published_at", ""),
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
            )
            evidence_list.append(ev)
        except Exception:
            pass
    return evidence_list


# ── Prompt variants ──

V1_EVENT_TYPE_HINT = (
    'capital/capability/behavioral（三选一，不可混合）'
)

V2_EVENT_TYPE_HINT = (
    'capital/capability/behavioral/research_result/governance/ecosystem（六选一）'
)

V1_HARD_RULE_2 = (
    "2. event_ledger：3-6条。每条type字段必填，从capital/capability/behavioral中严格三选一。"
    "capital=融资/估值/投资，capability=产品/模型/技术发布，behavioral=开发者/用户行为变化。"
    "只收录可验证的具体事件，排除趋势观察和观点评论"
)

V2_HARD_RULE_2 = (
    "2. event_ledger：3-6条。每条type字段必填，从以下六类中严格单选："
    "capital=融资/估值/投资/收购，capability=产品/模型/功能发布，"
    "behavioral=用户/开发者行为变化/采用率迁移，"
    "research_result=研究声明/基准测试/论文性能数据，"
    "governance=安全事件/政策变更/合规/开源许可变更，"
    "ecosystem=合作伙伴/平台战略/行业标准。"
    "Soft-mapping规则：当Evidence声明的类型不完全匹配上述任一类型时，映射到最接近的类型而非丢弃。"
    "只收录可验证的具体事件，排除趋势观察和观点评论"
)


def build_synthesis_prompt(packages, ontology_version="v2"):
    """Build a synthesis prompt with either v1 or v2 ontology hard rules."""
    from src.stages.synthesize import SynthesizeStage

    evidence_text = SynthesizeStage._format_evidence(packages)

    type_hint = V2_EVENT_TYPE_HINT if ontology_version == "v2" else V1_EVENT_TYPE_HINT
    hard_rule_2 = V2_HARD_RULE_2 if ontology_version == "v2" else V1_HARD_RULE_2

    prompt = (
        "你是AI行业首席策略分析师。以下结构化Evidence供你研判，生成决策输入。\n\n"
        f"{evidence_text}\n"
        "## 输出JSON\n"
        "```json\n"
        "{\n"
        '  "executive_judgment": "今日判断（<=80字）",\n'
        '  "structural_shifts": [{"title":"T","mechanism":"M","trigger":"T","consequence":"C","impact":"high/medium/low","time_horizon":"short/medium/long","source":"S","link":"U"}],\n'
        f'  "event_ledger": [{{"type":"{type_hint}","title":"事件","source":"S","link":"U"}}],\n'
        '  "signal_map": [{"hypothesis":"假设","supporting_events":["e1","e2"],"mechanism":"因果链"}],\n'
        '  "risks": [{"type":"bubble/structural/regime","horizon":"immediate/structural/long","description":"D"}],\n'
        '  "decision_hooks": [{"trigger_condition":"当...时","action":"动作","rationale":"为什么","audience":"开发者","level":"L2"}]\n'
        "}\n"
        "```\n"
        "规则：event_ledger必须引用Evidence的source URL和statement。"
        "structural_shifts最多1条(mechanism/trigger/consequence必填)。"
        f"{hard_rule_2}。"
        "event_ledger 3-5条(type必填)。signal_map >=1个(mechanism必填)。"
        "decision_hooks >=3条(开发者/创业者/投资人各>=1条,trigger_condition以当...时开头)。"
        "Evidence优先：verifiable_fact > source_statement。当Evidence间存在冲突时按L2收敛规则处理。中文。"
    )
    return prompt


def call_synthesis(llm, prompt):
    """Call LLM and parse event_ledger from response."""
    from src.stages.synthesize import SynthesizeStage
    stage = SynthesizeStage(llm_adapter=llm)

    response = llm.chat([
        {"role": "system", "content": "You are a chief AI strategy analyst. Return valid JSON only. Chinese."},
        {"role": "user", "content": prompt},
    ])
    data = json.loads(response) if response.strip().startswith("{") else {}
    if not data:
        import re
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if match:
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        if not data:
            match = re.search(r'\{[\s\S]*\}', response)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    pass
    return data.get("event_ledger", [])


def compute_adoption(event_ledger, evidence_list, stage):
    """Compute adoption rate: how many evidence domains are referenced by events."""
    ev_domains = set(ev.source.name.lower() for ev in evidence_list)

    matched_domains = set()
    for event in event_ledger:
        src = event.get("source", "")
        link = event.get("link", "")
        for ev in evidence_list:
            domain = ev.source.name.lower()
            if stage._source_matches_evidence(src, link, ev.source.name, ev.source.url):
                matched_domains.add(domain)
                break

    return {
        "evidence_domains": sorted(ev_domains),
        "matched_domains": sorted(matched_domains),
        "domain_adoption_rate": len(matched_domains) / max(len(ev_domains), 1),
        "event_count": len(event_ledger),
        "events_matched": sum(
            1 for e in event_ledger
            if any(stage._source_matches_evidence(
                e.get("source", ""), e.get("link", ""),
                ev.source.name, ev.source.url
            ) for ev in evidence_list)
        ),
        "type_distribution": dict(Counter(e.get("type", "unknown") for e in event_ledger)),
    }


def main():
    config = load_config("config.yaml")
    llm = build_llm_adapter(config)
    stage = SynthesizeStage(llm_adapter=llm)

    # Load evidence from disk
    base_dir = config.artifact.output_dir if hasattr(config, "artifact") else "./output/artifacts"
    evidence_list = load_all_evidence(base_dir)
    if not evidence_list:
        print("No evidence found on disk. Run the pipeline first.")
        sys.exit(1)

    # Build effective packages list from evidence
    # Group by artifact to create package-like structures
    from collections import defaultdict
    by_artifact = defaultdict(list)
    for ev in evidence_list:
        for ref in ev.supporting_material.artifact_refs:
            by_artifact[ref].append(ev)

    from src.models.evidence import EvidencePackage
    effective_packages = []
    for art_id, evs in by_artifact.items():
        effective_packages.append(EvidencePackage(
            package_id=f"PKG-REPLAY-{art_id}",
            topic=art_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            artifacts=[art_id],
            evidence=evs,
        ))

    print("=== Running A/B replay ===")
    print()

    # ── V1 run ──
    print("--- Ontology V1 (3 types: capital/capability/behavioral) ---")
    prompt_v1 = build_synthesis_prompt(effective_packages, ontology_version="v1")
    events_v1 = call_synthesis(llm, prompt_v1)
    result_v1 = compute_adoption(events_v1, evidence_list, stage)
    print(f"  Events generated: {result_v1['event_count']}")
    print(f"  Types: {result_v1['type_distribution']}")
    print(f"  Domains matched: {result_v1['matched_domains']}")
    print(f"  Domain adoption rate: {result_v1['domain_adoption_rate']:.1%}")
    print(f"  Events matched: {result_v1['events_matched']}/{result_v1['event_count']}")
    print()

    # ── V2 run ──
    print("--- Ontology V2 (6 types: +research_result/governance/ecosystem) ---")
    prompt_v2 = build_synthesis_prompt(effective_packages, ontology_version="v2")
    events_v2 = call_synthesis(llm, prompt_v2)
    result_v2 = compute_adoption(events_v2, evidence_list, stage)
    print(f"  Events generated: {result_v2['event_count']}")
    print(f"  Types: {result_v2['type_distribution']}")
    print(f"  Domains matched: {result_v2['matched_domains']}")
    print(f"  Domain adoption rate: {result_v2['domain_adoption_rate']:.1%}")
    print(f"  Events matched: {result_v2['events_matched']}/{result_v2['event_count']}")
    print()

    # ── Comparison ──
    print("=" * 60)
    print("A/B COMPARISON")
    print("=" * 60)
    delta = result_v2["domain_adoption_rate"] - result_v1["domain_adoption_rate"]
    v1_only = set(result_v1.get("type_distribution", {}).keys())
    v2_only = set(result_v2.get("type_distribution", {}).keys())
    new_types_used = v2_only - v1_only
    print(f"V1 adoption: {result_v1['domain_adoption_rate']:.1%}")
    print(f"V2 adoption: {result_v2['domain_adoption_rate']:.1%}")
    print(f"Delta: {delta:+.1%}")
    print(f"New types used (v2-only): {new_types_used}")
    print(f"V1 types: {result_v1['type_distribution']}")
    print(f"V2 types: {result_v2['type_distribution']}")

    # Write report
    report = {
        "experiment": "ab-ontology-v1-vs-v2",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "evidence_count": len(evidence_list),
        "evidence_domains": sorted(set(ev.source.name for ev in evidence_list)),
        "config": {
            "calibration_weight": stage._CALIBRATION_WEIGHT,
            "source_matching": "three-tier (domain + substring + first-word)",
        },
        "v1": result_v1,
        "v2": result_v2,
        "delta": {
            "domain_adoption_rate": delta,
            "new_types_used": sorted(new_types_used),
        },
    }

    out_dir = Path(base_dir) / "calibration"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = out_dir / f"ab-replay-{ts}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
