#!/usr/bin/env python3
"""Event Extraction Replay — measure Event Compiler stability across temperatures.

Replays the SAME evidence through L2 synthesis at temperature=0.0/0.3/0.7,
measuring event_count, type_distribution, and adoption_rate variance.

Usage:
    PYTHONPATH=. python3 scripts/event-replay.py
    PYTHONPATH=. python3 scripts/event-replay.py --runs 3   (3 runs per temperature)

Output:
    output/artifacts/calibration/event-replay-YYYYMMDD-HHMMSS.json
"""

import json
import sys
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.main import build_llm_adapter
from src.config.loader import load_config
from src.models.evidence import (
    Evidence, EvidenceSource, EvidenceConfidence, SupportingMaterial, EvidencePackage,
)
from src.stages.synthesize import SynthesizeStage


def load_all_evidence(base_dir: str) -> list[Evidence]:
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
            )
            evidence_list.append(ev)
        except Exception:
            pass
    return evidence_list


def build_evidence_only_prompt(packages: list[EvidencePackage]) -> str:
    """Build synthesis prompt from evidence packages (same as _process_evidence_only)."""
    evidence_text = SynthesizeStage._format_evidence(packages)

    return (
        "你是AI行业首席策略分析师。以下结构化Evidence供你研判，生成决策输入。\n\n"
        f"{evidence_text}\n"
        "## 输出JSON\n"
        "```json\n"
        "{\n"
        '  "executive_judgment": "今日判断（<=80字）",\n'
        '  "structural_shifts": [{"title":"T","mechanism":"M","trigger":"T","consequence":"C","impact":"high/medium/low","time_horizon":"short/medium/long","source":"S","link":"U"}],\n'
        '  "event_ledger": [{"type":"capital/capability/behavioral/research_result/governance/ecosystem","title":"事件","source":"S","link":"U"}],\n'
        '  "signal_map": [{"hypothesis":"假设","supporting_events":["e1","e2"],"mechanism":"因果链"}],\n'
        '  "risks": [{"type":"bubble/structural/regime","horizon":"immediate/structural/long","description":"D"}],\n'
        '  "decision_hooks": [{"trigger_condition":"当...时","action":"动作","rationale":"为什么","audience":"开发者","level":"L2"}]\n'
        "}\n"
        "```\n"
        "规则：event_ledger必须引用Evidence的source URL和statement。"
        "structural_shifts最多1条(mechanism/trigger/consequence必填)。"
        "event_ledger 3-5条(type必填)。signal_map >=1个(mechanism必填)。"
        "decision_hooks >=3条(开发者/创业者/投资人各>=1条,trigger_condition以当...时开头)。"
        "Evidence优先：verifiable_fact > source_statement。当Evidence间存在冲突时按L2收敛规则处理。中文。"
    )


def call_synthesis(llm, prompt: str, temperature: float = 0.0) -> dict:
    """Call LLM with a specific temperature override."""
    # DeepSeek API uses temperature parameter via extra kwargs
    response = llm.chat(
        [
            {"role": "system", "content": "You are a chief AI strategy analyst. Return valid JSON only. Chinese."},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
    )
    return parse_json_response(response)


def parse_json_response(response: str) -> dict:
    """Parse LLM JSON response, with fallbacks."""
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r'\{[\s\S]*\}', response)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def analyze_run(data: dict, evidence_list: list[Evidence], stage: SynthesizeStage) -> dict:
    """Extract metrics from a single synthesis run."""
    events = data.get("event_ledger", [])
    ev_domains = set(ev.source.name.lower() for ev in evidence_list)

    matched_domains = set()
    for event in events:
        src = event.get("source", "")
        link = event.get("link", "")
        for ev in evidence_list:
            domain = ev.source.name.lower()
            if stage._source_matches_evidence(src, link, ev.source.name, ev.source.url):
                matched_domains.add(domain)
                break

    type_dist = dict(Counter(e.get("type", "unknown") for e in events))

    return {
        "event_count": len(events),
        "type_distribution": type_dist,
        "matched_domains": sorted(matched_domains),
        "domain_adoption_rate": len(matched_domains) / max(len(ev_domains), 1),
        "events_matched": sum(
            1 for e in events
            if any(stage._source_matches_evidence(
                e.get("source", ""), e.get("link", ""),
                ev.source.name, ev.source.url,
            ) for ev in evidence_list)
        ),
    }


def compute_yields(evidence_count: int, artifact_count: int, run_data: dict) -> dict:
    """Compute the three yield metrics."""
    event_count = len(run_data.get("event_ledger", []))
    matched = sum(
        1 for e in run_data.get("event_ledger", [])
        if e.get("source")  # has a source = potentially adopted
    )
    return {
        "evidence_yield": evidence_count / max(artifact_count, 1),
        "event_yield": event_count / max(evidence_count, 1),
        "adoption_yield": matched / max(event_count, 1),
    }


def main():
    config = load_config("config.yaml")
    llm = build_llm_adapter(config)
    stage = SynthesizeStage(llm_adapter=llm)

    base_dir = config.artifact.output_dir if hasattr(config, "artifact") else "./output/artifacts"
    evidence_list = load_all_evidence(base_dir)

    if not evidence_list:
        print("No evidence found on disk. Run the pipeline first.")
        sys.exit(1)

    # Count artifacts on disk
    artifact_count = len(list(Path(base_dir).glob("A-*.json")))

    # Build packages from evidence
    from collections import defaultdict
    by_artifact = defaultdict(list)
    for ev in evidence_list:
        for ref in ev.supporting_material.artifact_refs:
            by_artifact[ref].append(ev)

    packages = []
    for art_id, evs in by_artifact.items():
        packages.append(EvidencePackage(
            package_id=f"PKG-REPLAY-{art_id}",
            topic=art_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            artifacts=[art_id],
            evidence=evs,
        ))

    print(f"Evidence: {len(evidence_list)} items, Artifacts: {artifact_count}")
    print(
        f"Evidence Yield: {len(evidence_list)}/{artifact_count} = "
        f"{len(evidence_list)/max(artifact_count,1):.1%}"
    )
    print()

    prompt = build_evidence_only_prompt(packages)
    temperatures = [0.0, 0.3, 0.7]
    results = {}

    for temp in temperatures:
        print(f"--- Temperature={temp} ---")
        data = call_synthesis(llm, prompt, temperature=temp)
        run = analyze_run(data, evidence_list, stage)
        yields = compute_yields(len(evidence_list), artifact_count, data)

        print(f"  Events: {run['event_count']}")
        print(f"  Types: {run['type_distribution']}")
        print(f"  Domains matched: {run['matched_domains']}")
        print(f"  Domain adoption: {run['domain_adoption_rate']:.1%}")
        print(f"  Event Yield: {yields['event_yield']:.1%}")
        print(f"  Adoption Yield: {yields['adoption_yield']:.1%}")

        results[f"t{temp}"] = {**run, "yields": yields}
        print()

    # ── Stability analysis ──
    event_counts = [results[f"t{t}"]["event_count"] for t in temperatures]
    type_sets = [set(results[f"t{t}"]["type_distribution"].keys()) for t in temperatures]
    common_types = type_sets[0] & type_sets[1] & type_sets[2]
    all_types = type_sets[0] | type_sets[1] | type_sets[2]

    print("=" * 60)
    print("STABILITY ANALYSIS")
    print("=" * 60)
    print(f"Event count range: {min(event_counts)}–{max(event_counts)} "
          f"(spread={max(event_counts)-min(event_counts)})")
    print(f"Types common across all temps: {common_types}")
    print(f"Types appearing at any temp: {all_types}")
    print(f"Type stability: {len(common_types)}/{len(all_types)} types stable")

    if max(event_counts) - min(event_counts) > 3:
        print("⚠️  HIGH VARIANCE: Event Compiler not stable — event_count varies by >3")
    elif max(event_counts) - min(event_counts) > 1:
        print("⚡ MODERATE VARIANCE: Event Compiler somewhat sensitive to temperature")
    else:
        print("✓ LOW VARIANCE: Event Compiler stable across temperatures")

    # Write report
    report = {
        "experiment": "event-extraction-replay",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "evidence_count": len(evidence_list),
        "artifact_count": artifact_count,
        "evidence_domains": sorted(set(ev.source.name for ev in evidence_list)),
        "evidence_yield": len(evidence_list) / max(artifact_count, 1),
        "temperatures": results,
        "stability": {
            "event_count_range": [min(event_counts), max(event_counts)],
            "event_count_spread": max(event_counts) - min(event_counts),
            "types_common": sorted(common_types),
            "types_total": sorted(all_types),
            "type_stability": len(common_types) / max(len(all_types), 1),
            "verdict": (
                "stable" if max(event_counts) - min(event_counts) <= 1
                else "moderate" if max(event_counts) - min(event_counts) <= 3
                else "unstable"
            ),
        },
    }

    out_dir = Path(base_dir) / "calibration"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = out_dir / f"event-replay-{ts}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
