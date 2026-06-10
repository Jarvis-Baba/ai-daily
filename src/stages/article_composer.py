"""Article Composer — InsightBrief → WeChat Visual Article via V-Kernel.

Deterministic mapping from pipeline output to V-Kernel Visual Plan format.
No LLM calls. Non-fatal: visual failures do not block Markdown output.

Output:
  output/articles/YYYYMMDD/
    visual_plan.json    V-Kernel input
    phase_0.json        Auto-generated positioning
    *.html              V-Kernel compiled HTML
    renderspec.json     V-Kernel metadata
    images/*.png        Rendered PNGs
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from collections import Counter
from datetime import date

from src.pipeline.stage import PipelineContext

logger = logging.getLogger(__name__)

# ── Ontology constants ──

EVENT_TYPE_COLORS = {
    "capital": "#ef4444", "capability": "#3b82f6", "behavioral": "#f59e0b",
    "research_result": "#8b5cf6", "governance": "#10b981", "ecosystem": "#06b6d4",
}

EVENT_TYPE_LABELS = {
    "capital": "资本", "capability": "能力", "behavioral": "行为",
    "research_result": "研究", "governance": "治理", "ecosystem": "生态",
}

DIRECTION_MAP = {
    "capital": ("决策", "转发+询盘"),
    "capability": ("信息", "转发+涨粉"),
    "behavioral": ("影响", "转发+认知"),
    "research_result": ("信息", "认知+涨粉"),
    "governance": ("决策", "转发+询盘"),
    "ecosystem": ("品牌", "认知+品牌"),
}

SIGNAL_COLORS = ["#3b82f6", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6"]

# ── Phase 0 ──

def _build_phase_0(insight) -> dict:
    type_counts = Counter(e.type for e in insight.event_ledger)
    dominant = type_counts.most_common(1)[0][0] if type_counts else "capability"
    direction, outcome = DIRECTION_MAP.get(dominant, ("信息", "转发+认知"))
    return {
        "outcome": outcome,
        "direction": direction,
        "sub_direction": "影响",
        "dominant_type": dominant,
        "type_distribution": dict(type_counts),
        "today_themes": insight.today_themes,
        "risk_count": len(insight.risks),
        "event_count": len(insight.event_ledger),
    }


# ── Template builders ──

def _build_insight_frame(insight, date_str: str) -> dict | None:
    judgment = (insight.executive_judgment or "今日无数据")[:120]
    return {
        "id": "insight_frame",
        "type": "INSIGHT_FRAME",
        "template": "ONE_LINE_TRUTH",
        "priority": "primary",
        "purpose": "今日核心判断",
        "content": {"line1": f"AI日报 · {date_str}", "line2": judgment},
    }


def _build_structure_map(insight, date_str: str) -> dict | None:
    if not insight.signal_map:
        return None
    layers = []
    for i, sig in enumerate(insight.signal_map[:5]):
        layers.append({
            "name": sig.hypothesis[:40],
            "desc": sig.mechanism[:80],
            "tag": f"{len(sig.supporting_events)}条证据",
            "color": SIGNAL_COLORS[i % len(SIGNAL_COLORS)],
        })
    return {
        "id": "structure_map",
        "type": "STRUCTURE_MAP",
        "template": "LAYERED_SYSTEM",
        "priority": "primary",
        "purpose": "信号结构层级图",
        "content": {
            "title": "信号结构图",
            "subtitle": f"{date_str} · {len(insight.signal_map)}个信号",
            "layers": layers,
        },
    }


def _build_comparison_panel(insight, date_str: str) -> dict | None:
    shifts = insight.structural_shifts
    if not shifts:
        return None
    left_items, right_items = [], []
    for s in shifts[:4]:
        left_items.append(s.trigger[:60] or s.title[:60])
        right_items.append(s.consequence[:60] or s.mechanism[:60])
    while len(left_items) < 4:
        left_items.append("—")
        right_items.append("—")
    return {
        "id": "comparison_panel",
        "type": "COMPARISON_PANEL",
        "template": "LEFT_RIGHT_CONTRAST",
        "priority": "primary",
        "purpose": "结构性变化：旧规则 vs 新规则",
        "content": {
            "title": "结构性变化",
            "left": {"label": "旧规则/触发", "items": left_items, "roi": "触发条件"},
            "right": {"label": "新规则/后果", "items": right_items, "roi": "系统后果"},
        },
    }


def _build_data_card(insight) -> dict | None:
    if len(insight.event_ledger) < 2:
        return None
    type_counts = Counter(e.type for e in insight.event_ledger)
    cards = []
    for etype, count in type_counts.most_common(3):
        sample = next(e for e in insight.event_ledger if e.type == etype)
        cards.append({
            "cost": str(count),
            "layer": EVENT_TYPE_LABELS.get(etype, etype),
            "desc": sample.title[:40],
            "color": EVENT_TYPE_COLORS.get(etype, "#64748b"),
        })
    return {
        "id": "event_cards",
        "type": "DATA_CARD",
        "template": "LARGE_NUMBER_FOCUS",
        "priority": "secondary",
        "purpose": "事件分类概览",
        "content": {
            "title": "事件分布",
            "subtitle": f"{len(insight.event_ledger)}个事件 · {len(type_counts)}个类别",
            "cards": cards,
        },
    }


def _build_flow_diagram(insight) -> dict | None:
    for sig in insight.signal_map:
        if not sig.mechanism or not sig.supporting_events:
            continue
        nodes = [{"label": "假设", "desc": sig.hypothesis[:60], "color": "#3b82f6"}]
        for title in sig.supporting_events[:3]:
            nodes.append({"label": "支撑", "desc": title[:60], "color": "#f59e0b"})
        nodes.append({"label": "因果链", "desc": sig.mechanism[:80], "color": "#10b981"})
        return {
            "id": "signal_flow",
            "type": "FLOW_DIAGRAM",
            "template": "VALUE_FLOW",
            "priority": "secondary",
            "purpose": "信号因果链",
            "content": {"title": "信号因果链", "nodes": nodes},
        }
    return None


# ── Orchestrator ──

def _build_visual_plan(insight, date_str: str) -> dict:
    images = []
    for builder in [_build_insight_frame, _build_structure_map, _build_comparison_panel,
                    _build_data_card, _build_flow_diagram]:
        if builder in (_build_insight_frame, _build_structure_map, _build_comparison_panel):
            img = builder(insight, date_str)
        else:
            img = builder(insight)
        if img:
            images.append(img)

    # Enforce max 5 images. Drop FLOW_DIAGRAM first, then DATA_CARD
    drop_order = ["FLOW_DIAGRAM", "DATA_CARD"]
    for drop_type in drop_order:
        while len(images) > 5:
            for i, img in enumerate(images):
                if img["type"] == drop_type:
                    images.pop(i)
                    break
            else:
                break
    return {"images": images}


# ── V-Kernel invocation ──

def _find_vkernel_root() -> str:
    return os.path.expanduser("~/.claude/skills/wechat-article-engine/visual-compiler")


def _invoke_vkernel(plan_path: str, out_dir: str, python_exe: str = None) -> bool:
    root = _find_vkernel_root()
    vkernel_path = os.path.join(root, "vkernel.py")
    if not os.path.exists(vkernel_path):
        logger.warning("V-Kernel not found at %s", vkernel_path)
        return False
    try:
        result = subprocess.run(
            [python_exe or sys.executable, vkernel_path, plan_path, out_dir],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            logger.warning("V-Kernel failed: %s", result.stderr[:200])
        return result.returncode == 0
    except Exception as exc:
        logger.warning("V-Kernel invocation error: %s", exc)
        return False


def _invoke_render(out_dir: str, python_exe: str = None) -> bool:
    root = _find_vkernel_root()
    render_path = os.path.join(root, "render.py")
    if not os.path.exists(render_path):
        logger.warning("Render script not found at %s", render_path)
        return False
    try:
        result = subprocess.run(
            [python_exe or sys.executable, render_path, out_dir],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            logger.warning("Render failed: %s", result.stderr[:200])
        return result.returncode == 0
    except Exception as exc:
        logger.warning("Render invocation error: %s", exc)
        return False


# ── Composition ──

def compose(insight, date_str: str, out_dir: str) -> dict:
    """Standalone entry: InsightBrief → Visual Plan + Phase 0 + V-Kernel + Render.

    Returns {"visual_plan": ..., "phase_0": ..., "out_dir": ..., "images_ok": bool}
    """
    os.makedirs(out_dir, exist_ok=True)

    visual_plan = _build_visual_plan(insight, date_str)
    phase_0 = _build_phase_0(insight)

    plan_path = os.path.join(out_dir, "visual_plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(visual_plan, f, indent=2, ensure_ascii=False)

    with open(os.path.join(out_dir, "phase_0.json"), "w", encoding="utf-8") as f:
        json.dump(phase_0, f, indent=2, ensure_ascii=False)

    images_ok = False
    if _invoke_vkernel(plan_path, out_dir):
        images_ok = _invoke_render(out_dir)

    image_count = len(visual_plan.get("images", []))
    logger.info("Article composed: %d images, %d events, images_ok=%s",
                image_count, phase_0["event_count"], images_ok)

    return {"visual_plan": visual_plan, "phase_0": phase_0, "out_dir": out_dir, "images_ok": images_ok}


# ── Pipeline Stage ──

class ArticleComposerStage:
    """Pipeline Stage: InsightBrief → Visual Plan → V-Kernel → PNGs.

    Insert after SynthesizeStage, before OutputStage.
    Non-fatal: exceptions are logged, never halt the pipeline.
    """

    def process(self, ctx: PipelineContext) -> PipelineContext:
        insight = ctx.get("insight_brief")
        if insight is None:
            logger.info("ArticleComposerStage: no insight_brief, skipping")
            return ctx

        report_date = ctx.get("report_date", date.today())
        if hasattr(report_date, "isoformat"):
            date_str = report_date.isoformat()
        else:
            date_str = str(report_date)

        out_dir = f"output/articles/{date_str}"

        try:
            result = compose(insight, date_str, out_dir)
            ctx.set("visual_plan", result["visual_plan"])
            ctx.set("visual_output_dir", out_dir)
            ctx.set("phase_0", result["phase_0"])
        except Exception as exc:
            logger.warning("ArticleComposerStage failed (non-fatal): %s", exc)

        return ctx


# ── Standalone CLI ──

def main():
    parser = argparse.ArgumentParser(description="Article Composer — InsightBrief → Visual Plan")
    parser.add_argument("--insight", required=True, help="Path to InsightBrief JSON file")
    parser.add_argument("--date", help="Date string YYYY-MM-DD (default: today)")
    parser.add_argument("--out", default=None, help="Output directory")
    args = parser.parse_args()

    date_str = args.date or date.today().isoformat()
    out_dir = args.out or f"output/articles/{date_str}"

    with open(args.insight, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Deserialize InsightBrief from JSON dict
    from src.models.article import (
        InsightBrief, StructuralShift, EventLedgerItem,
        SignalMapItem, RiskItem, DecisionHook,
    )
    insight = InsightBrief(
        date=date.fromisoformat(date_str) if date_str else date.today(),
        executive_judgment=data.get("executive_judgment", ""),
        structural_shifts=[StructuralShift(**s) for s in data.get("structural_shifts", [])],
        event_ledger=[EventLedgerItem(**e) for e in data.get("event_ledger", [])],
        signal_map=[SignalMapItem(**s) for s in data.get("signal_map", [])],
        risks=[RiskItem(**r) for r in data.get("risks", [])],
        decision_hooks=[DecisionHook(**d) for d in data.get("decision_hooks", [])],
        today_themes=data.get("today_themes", []),
    )

    result = compose(insight, date_str, out_dir)
    print(f"Visual plan: {len(result['visual_plan']['images'])} images")
    print(f"Phase 0: {result['phase_0']}")
    print(f"Images OK: {result['images_ok']}")
    print(f"Output: {out_dir}")


if __name__ == "__main__":
    main()
