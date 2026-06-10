import logging
import os
from datetime import datetime
from src.pipeline.stage import PipelineContext
from src.models.article import Brief, InsightBrief
from src.policy.policy_registry import resolve, POLICY_CONSTANTS

logger = logging.getLogger(__name__)

DEEPSEEK_INPUT_PRICE = 2.0
DEEPSEEK_OUTPUT_PRICE = 8.0

IMPACT_LABELS = {"high": "🔴 high", "medium": "🟡 medium", "low": "🟢 low"}
HORIZON_LABELS = {"short": "short", "medium": "medium", "long": "long"}
RISK_TYPE_LABELS = {"bubble": "🫧 bubble", "structural": "🏗 structural", "regime": "🌊 regime"}
RISK_HORIZON_LABELS = {"immediate": "now", "structural": "mid", "long": "long"}
EVENT_TYPE_LABELS = {
    "capital": "💰 Capital",
    "capability": "⚡ Capability",
    "behavioral": "👥 Behavioral",
    "research_result": "🔬 Research",
    "governance": "⚖️ Governance",
    "ecosystem": "🌐 Ecosystem",
}


class OutputStage:
    def process(self, ctx: PipelineContext) -> PipelineContext:
        insight: InsightBrief | None = ctx.get("insight_brief")
        brief: Brief | None = ctx.get("brief")
        output_dir: str = ctx.get("output_dir", "./output")

        os.makedirs(output_dir, exist_ok=True)

        if brief is None:
            brief = Brief(date=insight.date if insight else datetime.now().date(), items=[])

        date_str = brief.date.strftime("%Y-%m-%d")

        # v3 path: structural_shifts with triad or decision_hooks
        if insight and (insight.structural_shifts or insight.decision_hooks or insight.executive_judgment):
            items_md = _render_insight_v3(insight)
        # v2 fallback
        elif insight and (getattr(insight, 'alpha', None) or getattr(insight, 'judgment', None)):
            items_md = _render_insight_v2(insight)
        else:
            items_md = _render_items(brief)

        cost_md = _render_cost(ctx)
        health_md = _render_health(ctx)
        md_content = _assemble(date_str, items_md, health_md, cost_md)

        filename = f"morning-{date_str}.md"
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md_content)

        if insight and insight.event_ledger:
            _write_summary(insight, output_dir, date_str)

        item_count = len(insight.event_ledger) if insight and insight.event_ledger else len(brief.items)
        logger.info("Brief written to %s (%d items)", path, item_count)
        ctx.set("output_path", path)
        return ctx


# ── v3 6-section decision-system render ──

def _render_insight_v3(insight: InsightBrief) -> str:
    sections: list[str] = []

    # 1. Executive Judgment
    sections.append("## 1. 🧭 Executive Judgment\n")
    judgment = insight.executive_judgment or "_None_"
    sections.append(f"> {judgment}")
    if insight.today_themes:
        themes_md = ", ".join(f"`{t}`" for t in insight.today_themes)
        sections.append(f"\n\n**活跃主题**：{themes_md}")

    # 2. Structural Shifts (triad display)
    sections.append("\n\n## 2. ⚙️ Structural Shifts\n")
    if insight.structural_shifts:
        for s in insight.structural_shifts:
            sections.append(_render_structural_shift(s))
    else:
        sections.append("_None_")

    # 3. Event Ledger (grouped by type)
    sections.append("\n## 3. 📦 Event Ledger\n")
    sections.append(_render_event_ledger(insight))

    # 4. Signal Map (derivation chain)
    sections.append("\n## 4. 📡 Signal Map\n")
    if insight.signal_map:
        for s in insight.signal_map:
            sections.append(_render_signal_map_item(s))
    else:
        sections.append("_None_\n")

    # 5. Risk (time-horizoned)
    sections.append("\n## 5. ⚠️ Risk Layer\n")
    if insight.risks:
        for r in insight.risks:
            sections.append(_render_risk_item(r))
    else:
        sections.append("_None_\n")

    # 6. Decision Hooks
    sections.append("\n## 6. 🧾 Decision Hooks\n")
    sections.append(_render_decision_hooks(insight))

    return "\n".join(sections)


def _render_structural_shift(s) -> str:
    impact_label = IMPACT_LABELS.get(s.impact, s.impact)
    horizon_label = HORIZON_LABELS.get(s.time_horizon, s.time_horizon)
    lines = [
        f"### {s.title}",
        f"\n**机制**：{s.mechanism or '_None_'}",
        f"\n**触发**：{s.trigger or '_None_'}",
        f"\n**后果**：{s.consequence or '_None_'}",
        f"\n影响：{impact_label} | 时间维度：{horizon_label}",
        f"\n*{s.source}*",
    ]
    return "\n".join(lines)


def _render_event_ledger(insight: InsightBrief) -> str:
    if not insight.event_ledger:
        return "_None_\n"

    # Group by type
    groups: dict[str, list] = {}
    for e in insight.event_ledger:
        groups.setdefault(e.type, []).append(e)

    type_order = ("capital", "capability", "behavioral", "research_result", "governance", "ecosystem")
    lines = []
    for type_key in type_order:
        items = groups.get(type_key, [])
        if not items:
            continue
        label = EVENT_TYPE_LABELS.get(type_key, type_key)
        lines.append(f"**{label}**\n")
        for i, e in enumerate(items, 1):
            lines.append(f"{i}. {e.title} *({e.source})*\n")
        lines.append("")

    return "\n".join(lines) if lines else "_None_\n"


def _render_signal_map_item(s) -> str:
    events_md = "、".join(s.supporting_events) if s.supporting_events else "_None_"
    lines = [f"### {s.hypothesis}"]
    lines.append(f"\n**支撑事件**：{events_md}")
    if s.mechanism:
        lines.append(f"\n**因果链**：{s.mechanism}")
    return "\n".join(lines)


def _render_risk_item(r) -> str:
    type_tag = RISK_TYPE_LABELS.get(r.type, r.type)
    horizon_tag = RISK_HORIZON_LABELS.get(r.horizon, r.horizon)
    theme_note = f" [主题:`{r.related_theme}`]" if r.related_theme else ""
    return f"- [{type_tag}] [{horizon_tag}]{theme_note} {r.description}\n"


def _render_decision_hooks(insight: InsightBrief) -> str:
    """Group decision hooks by audience, show trigger→action→rationale."""
    if not insight.decision_hooks:
        return "_None_\n"

    buckets: dict[str, list] = {"developer": [], "builder": [], "investor": []}

    for hook in insight.decision_hooks:
        if not resolve("output.should_render_action")(hook):
            continue
        bucket = resolve("output.normalize_audience")(hook.audience)
        buckets.setdefault(bucket, []).append(hook)

    lines = []
    for bucket_key in ("developer", "builder", "investor"):
        label = POLICY_CONSTANTS["output.audience_labels"][bucket_key]
        items = buckets.get(bucket_key, [])
        if items:
            lines.append(f"**{label}**\n")
            for i, hook in enumerate(items, 1):
                trigger = hook.trigger_condition or "_无触发条件_"
                rationale = f" — *{hook.rationale}*" if hook.rationale else ""
                lines.append(f"{i}. **触发**：{trigger}")
                lines.append(f"   **动作**：{hook.action}{rationale} [`{hook.level}`]")
            lines.append("")
        else:
            lines.append(f"**{label}**\n_None_\n")

    return "\n".join(lines)


# ── v2 legacy render (kept for backward compat) ──

def _render_insight_v2(insight: InsightBrief) -> str:
    sections: list[str] = []

    sections.append("## 1. Judgment（今日判断）\n")
    sections.append(resolve("output.safe_value")(insight.judgment))
    if insight.today_themes:
        themes_md = ", ".join(f"`{t}`" for t in insight.today_themes)
        sections.append(f"\n\n**活跃主题**：{themes_md}")

    sections.append("\n\n## 2. Alpha（结构级变化）\n")
    if insight.alpha:
        for a in insight.alpha:
            sections.append(_render_alpha_item_v2(a))
    else:
        sections.append("_None_")

    sections.append("\n## 3. Beta（重要变化）\n")
    if insight.beta:
        for b in insight.beta:
            theme_tag = f" | 主题:`{b.theme_id}`" if b.theme_id else ""
            sections.append(f"- **{b.title}**：{b.point}{theme_tag} *({b.source})*\n")
    else:
        sections.append("_None_\n")

    sections.append("\n## 4. Signals（趋势信号）\n")
    if insight.signals:
        for s in insight.signals:
            evidence = "、".join(s.evidence) if s.evidence else "None"
            sections.append(f"- **{s.signal}**（证据：{evidence}）\n")
    else:
        sections.append("_None_\n")

    sections.append("\n## 5. Counter Signals（反向信号）\n")
    if insight.counter_signals:
        for cs in insight.counter_signals:
            sections.append(f"- {cs}\n")
    else:
        sections.append("_None_\n")

    sections.append("\n## 6. Actions（行动建议）\n")
    sections.append(_render_actions_v2(insight))

    return "\n".join(sections)


def _render_alpha_item_v2(a) -> str:
    lines = [f"### {a.title}"]
    lines.append(f"\n**结论**：{resolve('output.safe_value')(a.conclusion)}")
    if a.variables:
        lines.append("\n**关键变量**：")
        for v in a.variables:
            lines.append(f"→ {v}")
    else:
        lines.append("\n**关键变量**：_None_")
    if a.actions:
        lines.append("\n**行动**：")
        for act in a.actions:
            lines.append(f"• {act}")
    meta_parts = []
    if a.theme_id:
        meta_parts.append(f"主题:`{a.theme_id}`")
    meta_parts.append(f"*{a.source}*")
    lines.append(f"\n{(' | '.join(meta_parts))}")
    return "\n".join(lines)


def _render_actions_v2(insight: InsightBrief) -> str:
    if not insight.actions:
        return "_None_\n"
    buckets: dict[str, list[tuple[str, str]]] = {"developer": [], "builder": [], "investor": []}
    for action_item in insight.actions:
        if not resolve("output.should_render_action")(action_item):
            continue
        bucket = resolve("output.normalize_audience")(action_item.audience)
        level = getattr(action_item, "level", "L2")
        for act in action_item.actions:
            label = f"{act} [`{level}`]"
            buckets.setdefault(bucket, []).append(label)
    lines = []
    for bucket_key in ("developer", "builder", "investor"):
        label = POLICY_CONSTANTS["output.audience_labels"][bucket_key]
        items = buckets.get(bucket_key, [])
        if items:
            lines.append(f"**{label}**\n")
            for i, item in enumerate(items, 1):
                lines.append(f"{i}. {item}")
            lines.append("")
        else:
            lines.append(f"**{label}**\n_None_\n")
    return "\n".join(lines)


# ── v1 legacy render ──

def _render_items(brief: Brief) -> str:
    if not brief.items:
        return "_No articles today._"

    lines = []
    for i, item in enumerate(brief.items, 1):
        lines.append(
            f"## {i}. {item.title}\n\n"
            f"{item.digest}\n\n"
            f"*{item.source}*  [[原文]({item.link})]\n"
        )
    return "\n".join(lines)


# ── shared helpers ──

def _assemble(date_str: str, items: str, health: str, cost: str) -> str:
    return (
        f"# 🧠 AI Daily Report — {date_str}\n\n"
        f"{items}\n"
        f"---\n"
        f"> 生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{health}"
        f"{cost}\n"
    )


def _render_health(ctx: PipelineContext) -> str:
    report = ctx.get("health_report")
    if report is None:
        return ""
    failed = [f for f in report.feeds if f.status == "failed"]
    degraded = [f for f in report.feeds if f.status == "degraded"]
    lines = [f"> 信源健康：{report.summary}"]
    if failed:
        names = ", ".join(_format_feed_health(f) for f in failed)
        lines.append(f"> 失败：{names}")
    if degraded:
        names = ", ".join(_format_feed_health(f) for f in degraded)
        lines.append(f"> 降级：{names}")
    return "\n".join(lines) + "\n"


def _format_feed_health(feed_health) -> str:
    feed_type = getattr(feed_health, "feed_type", "rss")
    return f"{feed_health.name}({feed_type})"


def _render_cost(ctx: PipelineContext) -> str:
    adapter = ctx.get("llm_adapter")
    if adapter is None or adapter.calls == 0:
        return ""

    cost = (
        adapter.prompt_tokens / 1_000_000 * DEEPSEEK_INPUT_PRICE
        + adapter.completion_tokens / 1_000_000 * DEEPSEEK_OUTPUT_PRICE
    )
    return (
        f"> API 用量：{adapter.calls} 次调用 | "
        f"输入 {adapter.prompt_tokens:,} tokens | "
        f"输出 {adapter.completion_tokens:,} tokens | "
        f"预估费用 ¥{cost:.4f}"
    )


def _write_summary(insight: InsightBrief, output_dir: str, date_str: str) -> None:
    """Write a 3-line daily summary for the human consumer."""
    from collections import Counter

    judgment = (insight.executive_judgment or "_无判断_")[:120]

    sources = Counter(e.source for e in insight.event_ledger)
    top_sources = ", ".join(s for s, _ in sources.most_common(3))

    hooks = insight.decision_hooks or []
    top_hook = None
    for h in hooks:
        if h.level == "L1":
            top_hook = h
            break
    if top_hook is None and hooks:
        top_hook = hooks[0]

    lines = [
        f"今日判断：{judgment}",
        f"事件量：{len(insight.event_ledger)} 条，主要来自：{top_sources or '_无_'}",
    ]

    if top_hook:
        lines.append(f"决策钩子：{len(hooks)} 条，最值得看：{top_hook.action}")
    else:
        lines.append("决策钩子：无")

    path = os.path.join(output_dir, f"summary-{date_str}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
