"""Article Compiler v0 — Structured Intelligence → Publishable WeChat Article.

Single LLM call: InsightBrief + EventClusters → Markdown article + Visual Plan → PNGs.
Deterministic visual mapping. Non-fatal: exceptions logged, never block Markdown output.

Output:
  output/articles/YYYYMMDD/
    article.md          LLM-generated WeChat article
    visual_plan.json    V-Kernel input
    phase_0.json        Auto-generated positioning
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
from src.adapters.llm import LLMAdapter

logger = logging.getLogger(__name__)

# ── Constants ──

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

SYSTEM_PROMPT = """You are a senior WeChat public account editor and narrative systems designer.

You do NOT analyze raw data. You ONLY transform structured signals into publishable narrative.

You must maximize:
- clarity of narrative arc (hook → context → events → interpretation → closing)
- compression of technical content into readable insight
- structural coherence across sections

You are NOT allowed to:
- invent new facts beyond what is provided
- add external knowledge or speculation
- change event meaning or type classifications
- merge unrelated clusters unless explicitly connected in the data

Output ONLY valid Markdown. No JSON, no YAML, no commentary."""


# ── Phase 0 ──

def _build_phase_0(insight) -> dict:
    type_counts = Counter(e.type for e in insight.event_ledger)
    dominant = type_counts.most_common(1)[0][0] if type_counts else "capability"
    direction, outcome = DIRECTION_MAP.get(dominant, ("信息", "转发+认知"))
    return {
        "outcome": outcome,
        "direction": direction,
        "dominant_type": dominant,
        "type_distribution": dict(type_counts),
        "today_themes": insight.today_themes,
        "risk_count": len(insight.risks),
        "event_count": len(insight.event_ledger),
    }


# ── Visual template builders ──

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


# ── Cluster formatting ──

def _format_clusters_for_article(clusters, orphans) -> str:
    """Format clusters as readable summaries for the LLM article prompt."""
    if not clusters:
        return "(今日无事件簇)"

    parts = []
    for i, cluster in enumerate(clusters):
        sources = sorted(set(ev.source.name for ev in cluster))
        parts.append(f"### Cluster {i+1} ({len(cluster)}条证据 | 来源: {', '.join(sources[:3])})")
        for ev in cluster:
            parts.append(f"- {ev.statement[:200]}")
        parts.append("")

    if orphans and len(orphans) > 0:
        # Only show top orphans as supplementary context
        parts.append(f"### 补充证据 ({min(len(orphans), 10)}条孤立事实)")
        for ev in orphans[:10]:
            parts.append(f"- [{ev.source.name}] {ev.statement[:150]}")
        parts.append("")

    return "\n".join(parts)


# ── Narrative prompt ──

def _build_narrative_prompt(insight, clusters, orphans) -> str:
    """Build the User prompt for LLM narrative compilation."""

    # ── Event ledger summary ──
    ledger_lines = []
    for e in insight.event_ledger:
        label = EVENT_TYPE_LABELS.get(e.type, e.type)
        ledger_lines.append(f"- [{label}] {e.title}（来源: {e.source}）")
    ledger_text = "\n".join(ledger_lines) if ledger_lines else "(无事件)"

    # ── Signal map summary ──
    signal_lines = []
    for sig in insight.signal_map:
        signal_lines.append(f"- **{sig.hypothesis}** → {sig.mechanism}")
        signal_lines.append(f"  支撑事件: {', '.join(sig.supporting_events[:3])}")
    signal_text = "\n".join(signal_lines) if signal_lines else "(无信号)"

    # ── Structural shifts ──
    shift_lines = []
    for s in insight.structural_shifts:
        shift_lines.append(f"- **{s.title}**: {s.mechanism}（影响: {s.impact}, 时域: {s.time_horizon}）")
    shift_text = "\n".join(shift_lines) if shift_lines else "(无结构性变化)"

    # ── Event clusters ──
    cluster_text = _format_clusters_for_article(clusters, orphans)

    # ── Risks ──
    risk_lines = []
    for r in insight.risks:
        risk_lines.append(f"- [{r.type}] {r.description}（时域: {r.horizon}）")
    risk_text = "\n".join(risk_lines) if risk_lines else "(无风险)"

    return f"""## 今日核心判断（必须驱动整篇文章主线）
{insight.executive_judgment or "AI行业无重大结构性变化"}

## 事件账本（事实约束，共{len(insight.event_ledger)}条）
{ledger_text}

## 信号结构（信息源关系）
{signal_text}

## 事件簇（原始证据分组，共{len(clusters)}个cluster + {len(orphans)}个orphan）
{cluster_text}

## 结构性变化（宏观规则变化，共{len(insight.structural_shifts)}条）
{shift_text}

## 风险提示
{risk_text}

---

TASK:

基于以上结构化数据，生成一篇微信公众号文章。输出 **严格的 Markdown** 格式。

### 输出结构要求：

# [标题]
- 不超过25个汉字
- 必须编码冲突/变化/断裂感
- 不能是陈述句，要有张力

## [开头钩子]
- 不超过80字
- 高张力开场，只暗示不解释
- 让读者产生"发生了什么"的好奇

## [背景压缩]
- 不超过100字
- 回答"为什么今天重要"——只讲结构性原因

## [核心事件]
- ⚠️ 从全部{len(clusters)}个cluster中精选5-7个信息增量最大的，不重要的必须丢弃
- 选择标准（在脑内评估，不输出评分）：
  1. 新颖性 — 是否揭示了新结构/新现象/新断裂
  2. 因果中心性 — 是否驱动或解释了其他事件
  3. 跨cluster连接性 — 是否串联起多个cluster形成故事线
- ⚠️ 未入选的cluster：严禁展开为独立段落。压缩为1-2句归入"背景动态"，或直接丢弃
- 入选的cluster每段包含：事实概括 + 洞察压缩
- 保留事件类型区分（资本/能力/行为/研究/治理/生态）

## [含义解读]
- 3个要点，bullet list
- 面向读者：行业从业者/创业者/投资者
- 每条必须可行动或可思考

## [结尾金句]
- 一句话
- 可独立转发、可截图引用

### 严格规则：
- 不编造不在数据中的事件
- 不合并无关联的cluster
- 保留event_ledger中的类型区分
- 所有判断必须有数据中的事件支撑
- 输出纯Markdown，不输出JSON/YAML/额外解释"""


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


# ── Article Compiler ──

class ArticleCompiler:
    """Single LLM call: Structured Intelligence → Markdown Article + Visual Plan.

    Inputs (all pre-structured, NO raw text):
      - InsightBrief (executive_judgment, event_ledger, signal_map, structural_shifts, risks)
      - Event clusters + orphans (from EventClusteringStage)

    Outputs:
      - article.md       LLM-generated WeChat article in Markdown
      - visual_plan.json V-Kernel visual plan
      - phase_0.json     Auto-positioning metadata
      - images/*.png     V-Kernel rendered PNGs
    """

    def __init__(self, llm_adapter: LLMAdapter):
        self._llm = llm_adapter

    def compile(self, insight, clusters, orphans, date_str: str, out_dir: str) -> dict:
        """Run full compilation: LLM article + Visual Plan + V-Kernel + Render.

        Returns {"article_md": ..., "visual_plan": ..., "phase_0": ..., "out_dir": ..., "images_ok": bool}
        """
        os.makedirs(out_dir, exist_ok=True)

        # ── 1. LLM Narrative Compilation ──
        article_md = ""
        try:
            prompt = _build_narrative_prompt(insight, clusters, orphans)
            article_md = self._llm.chat([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ], temperature=0.7, max_tokens=2500)
            article_md = (article_md or "").strip()
            logger.info("ArticleCompiler: LLM narrative generated (%d chars)", len(article_md))
        except Exception as exc:
            logger.warning("ArticleCompiler: LLM narrative failed: %s", exc)
            article_md = f"# AI日报 {date_str}\n\n> 今日内容生成失败，请查看原始数据。\n"

        # ── 2. Write article.md ──
        article_path = os.path.join(out_dir, "article.md")
        with open(article_path, "w", encoding="utf-8") as f:
            f.write(article_md)

        # ── 3. Visual Plan (deterministic, no LLM) ──
        visual_plan = _build_visual_plan(insight, date_str)
        phase_0 = _build_phase_0(insight)

        plan_path = os.path.join(out_dir, "visual_plan.json")
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(visual_plan, f, indent=2, ensure_ascii=False)

        with open(os.path.join(out_dir, "phase_0.json"), "w", encoding="utf-8") as f:
            json.dump(phase_0, f, indent=2, ensure_ascii=False)

        # ── 4. V-Kernel + Render ──
        images_ok = False
        if _invoke_vkernel(plan_path, out_dir):
            images_ok = _invoke_render(out_dir)

        image_count = len(visual_plan.get("images", []))
        logger.info("ArticleCompiler: %d images, %d events, md=%d chars, images_ok=%s",
                    image_count, phase_0["event_count"], len(article_md), images_ok)

        return {
            "article_md": article_md,
            "visual_plan": visual_plan,
            "phase_0": phase_0,
            "out_dir": out_dir,
            "images_ok": images_ok,
        }


# ── Pipeline Stage ──

class ArticleCompilerStage:
    """Pipeline Stage: InsightBrief + Clusters → Article + PNGs.

    Insert after SynthesizeStage, before OutputStage.
    Non-fatal: exceptions logged, never halt the pipeline.
    """

    def __init__(self, llm_adapter: LLMAdapter):
        self._compiler = ArticleCompiler(llm_adapter)

    def process(self, ctx: PipelineContext) -> PipelineContext:
        insight = ctx.get("insight_brief")
        if insight is None:
            logger.info("ArticleCompilerStage: no insight_brief, skipping")
            return ctx

        clusters = ctx.get("event_clusters", []) or []
        orphans = ctx.get("event_orphans", []) or []

        report_date = ctx.get("report_date", date.today())
        if hasattr(report_date, "isoformat"):
            date_str = report_date.isoformat()
        else:
            date_str = str(report_date)

        out_dir = f"output/articles/{date_str}"

        try:
            result = self._compiler.compile(insight, clusters, orphans, date_str, out_dir)
            ctx.set("article_md", result["article_md"])
            ctx.set("visual_plan", result["visual_plan"])
            ctx.set("visual_output_dir", out_dir)
            ctx.set("phase_0", result["phase_0"])
        except Exception as exc:
            logger.warning("ArticleCompilerStage failed (non-fatal): %s", exc)

        return ctx


# ── Standalone CLI ──

def main():
    parser = argparse.ArgumentParser(description="Article Compiler v0 — InsightBrief → WeChat Article")
    parser.add_argument("--insight", required=True, help="Path to InsightBrief JSON file")
    parser.add_argument("--date", help="Date string YYYY-MM-DD (default: today)")
    parser.add_argument("--out", default=None, help="Output directory")
    parser.add_argument("--llm", default="dummy", choices=["dummy", "deepseek"],
                        help="LLM backend (default: dummy)")
    args = parser.parse_args()

    date_str = args.date or date.today().isoformat()
    out_dir = args.out or f"output/articles/{date_str}"

    with open(args.insight, "r", encoding="utf-8") as f:
        data = json.load(f)

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

    if args.llm == "deepseek":
        from src.adapters.llm import OpenAILikeAdapter
        from src.config.loader import load_config
        config = load_config("config.yaml")
        llm = OpenAILikeAdapter(
            model=config.llm.model,
            api_key=config.llm.api_key,
            base_url=config.llm.base_url,
        )
    else:
        from src.adapters.llm import DummyAdapter
        llm = DummyAdapter()

    compiler = ArticleCompiler(llm)
    # Standalone CLI re-processing: we don't have clusters/orphans, pass empty
    result = compiler.compile(insight, [], [], date_str, out_dir)
    print(f"Article: {len(result['article_md'])} chars")
    print(f"Visual plan: {len(result['visual_plan']['images'])} images")
    print(f"Phase 0: {result['phase_0']}")
    print(f"Images OK: {result['images_ok']}")
    print(f"Output: {out_dir}")


if __name__ == "__main__":
    main()
