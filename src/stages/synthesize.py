import json
import logging
import os
import re
from datetime import date
from pathlib import Path

from src.pipeline.stage import PipelineContext
from src.adapters.llm import LLMAdapter
from src.models.article import (
    Brief, InsightBrief, StructuralShift, EventLedgerItem,
    SignalMapItem, RiskItem, DecisionHook, AlphaItem, BetaItem,
    SignalItem, ActionItem,
)
from src.models.scored_article import ScoredArticle, Bucket
from src.models.evidence import EvidencePackage
from src.models.calibration import DomainStats

logger = logging.getLogger(__name__)


class SynthesizeStage:
    """Cognitive synthesis: scored articles + theme state → InsightBrief (v3).

    Reads ctx["scored_articles"], applies rule-based selection,
    uses LLM for structured decision-input generation.
    """

    def __init__(self, llm_adapter: LLMAdapter, memory_path: str = ".theme-memory.json"):
        self._llm = llm_adapter
        self._memory_path = memory_path

    def process(self, ctx: PipelineContext) -> PipelineContext:
        scored = ctx.get("scored_articles", [])
        packages = ctx.get("evidence_packages", []) or []
        clusters = ctx.get("event_clusters", []) or []
        orphans = ctx.get("event_orphans", []) or []

        if not scored and not packages and not clusters:
            return self._process_legacy(ctx)

        if not scored and not clusters:
            return self._process_evidence_only(ctx, packages)

        # ── rule-based selection ──
        alpha_candidates = [
            sa for sa in scored
            if sa.bucket == Bucket.ALPHA
            or (sa.impact >= 8 and sa.trajectory in ("CONTINUE", "ACCELERATE"))
        ][:2]
        beta_candidates = [sa for sa in scored if sa.bucket == Bucket.BETA][:5]
        high_novelty = [sa for sa in scored if sa.novelty >= 8][:5]

        # ── LLM synthesis ──
        prompt = self._build_prompt(alpha_candidates, beta_candidates, high_novelty, packages, clusters, orphans)
        response = self._llm.chat([
            {"role": "system", "content": "You are a chief AI strategy analyst. Return valid JSON only. Chinese."},
            {"role": "user", "content": prompt},
        ])

        data = self._parse_json(response)
        if data and self._looks_like_template(data):
            logger.debug("Synthesize JSON is template echo, discarding")
            data = {}

        # ── rule-based extras ──
        exec_judgment = data.get("executive_judgment", "") or self._fallback_judgment(scored)
        risks = self._build_risks(data.get("risks", []), alpha_candidates)
        today_themes = self._rank_themes(scored)

        insight = InsightBrief(
            date=ctx.get("report_date", date.today()),
            executive_judgment=exec_judgment,
            structural_shifts=[StructuralShift(
                title=s.get("title", ""),
                mechanism=s.get("mechanism", ""),
                trigger=s.get("trigger", ""),
                consequence=s.get("consequence", ""),
                impact=s.get("impact", "medium"),
                time_horizon=s.get("time_horizon", "medium"),
                source=s.get("source", ""),
                link=s.get("link", ""),
            ) for s in data.get("structural_shifts", [])],
            event_ledger=[EventLedgerItem(
                type=e.get("type", "capability"),
                title=e.get("title", ""),
                source=e.get("source", ""),
                link=e.get("link", ""),
            ) for e in data.get("event_ledger", [])],
            signal_map=[SignalMapItem(
                hypothesis=s.get("hypothesis", ""),
                supporting_events=s.get("supporting_events", []),
                mechanism=s.get("mechanism", ""),
            ) for s in data.get("signal_map", [])],
            decision_hooks=[DecisionHook(
                trigger_condition=d.get("trigger_condition", ""),
                action=d.get("action", ""),
                rationale=d.get("rationale", ""),
                audience=d.get("audience", "开发者"),
                level=d.get("level", "L2"),
            ) for d in data.get("decision_hooks", [])],
            risks=risks,
            today_themes=today_themes,
        )
        ctx.set("insight_brief", insight)
        self._write_calibration(ctx, insight)
        return ctx

    # ── Calibration feedback ──

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract normalized domain from URL for source matching."""
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url if "://" in url else f"https://{url}")
            domain = parsed.netloc or parsed.path.split("/")[0]
            domain = domain.lower().removeprefix("www.")
            return domain
        except Exception:
            return url.lower()

    @staticmethod
    def _source_matches_evidence(event_source: str, event_link: str,
                                  evidence_name: str, evidence_url: str) -> bool:
        """Check if an event_ledger entry matches an evidence source.

        Uses three-tier matching:
        1. Domain extracted from event.link matches evidence source domain
        2. Event source name is substring of evidence source name (or vice versa)
        3. Loose: first meaningful word of event source appears in evidence domain
        """
        ev_src = event_source.lower().strip()
        ev_name = evidence_name.lower().strip()
        ev_url = evidence_url.lower().strip()

        # Tier 1: URL domain match
        try:
            from urllib.parse import urlparse
            ev_domain = SynthesizeStage._extract_domain(event_link)
            if ev_domain and ev_domain in ev_name:
                return True
            ev_parsed = urlparse(ev_url if "://" in ev_url else f"https://{ev_url}")
            ev_domain2 = (ev_parsed.netloc or "").lower().removeprefix("www.")
            if ev_domain and ev_domain2 and (ev_domain in ev_domain2 or ev_domain2 in ev_domain):
                return True
        except Exception:
            pass

        # Tier 2: substring match
        if ev_src in ev_name or ev_name in ev_src:
            return True

        # Tier 3: first-word match
        ev_first = ev_src.split()[0].strip("'\".,")
        if ev_first and len(ev_first) > 2 and ev_first in ev_name:
            return True

        return False

    # Frozen during ontology experimentation. Set to 0.3 to re-enable learning.
    _CALIBRATION_WEIGHT = 0.0

    def _write_calibration(self, ctx, insight):
        """Update source reliability calibration from synthesis output.

        Reads ctx["evidence"] (all Evidence passed to L2), compares against
        insight.event_ledger to determine which sources were adopted.

        v2 additions:
        - Per-type ontology telemetry (which event types capture which evidence)
        - Adoption attribution (source_match / ontology_match / confidence)
        - Frozen calibration (behavioral_weight=0) during ontology experimentation
        """
        from datetime import datetime, timezone
        from src.models.calibration import CalibrationEntry, DomainStats
        from src.adapters.calibration_store import load_calibrations, save_calibrations
        from src.models.evidence import SOURCE_RELIABILITY_DEFAULTS

        all_evidence = ctx.get("evidence", []) or []
        if not all_evidence:
            return

        # Group evidence by source domain
        source_refs: dict[str, int] = {}
        for ev in all_evidence:
            domain = ev.source.name.lower()
            source_refs[domain] = source_refs.get(domain, 0) + 1

        # Per-type telemetry: track which event types capture which evidence
        TYPE_LIST = ["capital", "capability", "behavioral",
                     "research_result", "governance", "ecosystem"]
        type_telemetry: dict[str, dict] = {t: {"generated": 0, "matched": 0} for t in TYPE_LIST}
        for event in insight.event_ledger:
            etype = event.type
            if etype in type_telemetry:
                type_telemetry[etype]["generated"] += 1

        # Adoption attribution tracking
        attribution_log: list[dict] = []

        # Match event_ledger entries against evidence sources
        source_adopted: dict[str, int] = {}
        for event in insight.event_ledger:
            event_src = event.source or ""
            event_link = event.link or ""
            event_type = event.type
            matched = False
            for ev in all_evidence:
                domain = ev.source.name.lower()
                if self._source_matches_evidence(event_src, event_link, ev.source.name, ev.source.url):
                    source_adopted[domain] = source_adopted.get(domain, 0) + 1
                    if not matched:
                        matched = True
                        if event_type in type_telemetry:
                            type_telemetry[event_type]["matched"] += 1
                    attribution_log.append({
                        "event_title": event.title,
                        "event_type": event_type,
                        "event_source": event_src,
                        "evidence_domain": domain,
                        "match_reason": "source_match",
                    })
                    break
            if not matched:
                attribution_log.append({
                    "event_title": event.title,
                    "event_type": event_type,
                    "event_source": event_src,
                    "match_reason": "no_match",
                })

        if not source_refs:
            return

        # Load existing calibrations
        config = ctx.get("config")
        base_dir = ("./output/artifacts" if config is None
                    else getattr(getattr(config, "artifact", None), "output_dir", "./output/artifacts"))
        calibrations = load_calibrations(base_dir)
        now = datetime.now(timezone.utc).isoformat()

        for domain, ref_count in source_refs.items():
            prior = SOURCE_RELIABILITY_DEFAULTS.get(
                self._guess_source_type(domain), 0.50
            )
            adopted = source_adopted.get(domain, 0)
            compressed = ref_count - adopted
            disputed = 0

            existing = calibrations.get(domain)
            if existing:
                stats = DomainStats(
                    referenced=existing.stats.referenced + ref_count,
                    adopted=existing.stats.adopted + adopted,
                    disputed=existing.stats.disputed + disputed,
                    compressed=existing.stats.compressed + compressed,
                )
            else:
                stats = DomainStats(
                    referenced=ref_count, adopted=adopted,
                    disputed=disputed, compressed=compressed,
                )

            behavioral = self._compute_behavioral(stats)
            behavioral = self._entropy_correct(behavioral, ref_count, len(source_refs))
            # Frozen calibration: behavioral_weight=0 during ontology experimentation
            reliability = (1.0 - self._CALIBRATION_WEIGHT) * prior + self._CALIBRATION_WEIGHT * behavioral
            reliability = max(0.1, min(0.99, reliability))

            calibrations[domain] = CalibrationEntry(
                domain=domain, prior=prior, stats=stats,
                behavioral_score=round(behavioral, 4),
                reliability=round(reliability, 4),
                updated_at=now,
            )

        if calibrations:
            # Attach telemetry to calibration output
            telemetry_path = Path(base_dir) / "calibration" / "ontology_telemetry.json"
            telemetry_path.parent.mkdir(parents=True, exist_ok=True)
            telemetry_data = {
                "updated_at": now,
                "calibration_weight": self._CALIBRATION_WEIGHT,
                "ontology_version": "v2",
                "type_telemetry": type_telemetry,
                "attribution_log": attribution_log,
                "summary": {
                    "total_evidence": sum(source_refs.values()),
                    "total_adopted": sum(source_adopted.values()),
                    "total_events": len(insight.event_ledger),
                    "matched_events": sum(1 for a in attribution_log if a.get("match_reason") == "source_match"),
                },
            }
            telemetry_path.write_text(json.dumps(telemetry_data, indent=2, ensure_ascii=False), encoding="utf-8")
            save_calibrations(calibrations, base_dir)

    @staticmethod
    def _compute_behavioral(stats: DomainStats) -> float:
        total = stats.referenced
        if total == 0:
            return 0.5
        adoption = stats.adopted / total
        conflict = stats.disputed / total
        compression = stats.compressed / total
        score = 1.0 * adoption - 0.8 * conflict - 0.5 * compression
        return max(0.0, min(1.0, score))

    @staticmethod
    def _entropy_correct(behavioral: float, ref_count: int, total_domains: int) -> float:
        """Prevent popularity bias: if one domain dominates references, dampen its score."""
        if total_domains <= 1:
            return behavioral
        # Small penalty for being the majority referent
        dominance = min(ref_count / (ref_count + total_domains), 0.5)
        correction = 1.0 - 0.1 * dominance
        return behavioral * correction

    @staticmethod
    def _guess_source_type(domain: str) -> str:
        from src.models.evidence import infer_source_type
        return infer_source_type("blog_post", domain)

    # ── v3 prompt ──

    def _build_prompt(self, alpha_cands, beta_cands, high_novelty, packages=None, clusters=None, orphans=None):
        def _format(sa: ScoredArticle) -> str:
            a = sa.article
            text = a.content if a.content else (a.summary or "")[:600]
            theme_info = f"主题:{sa.theme_id}({sa.trajectory})" if sa.theme_id else "主题:无"
            return (
                f"- 标题：{a.title}\n"
                f"  来源：{a.source} | 链接：{a.link}\n"
                f"  评分：影响力{sa.impact} 新颖度{sa.novelty} 行动性{sa.actionability} | {theme_info}\n"
                f"  内容：{text[:500]}"
            )

        alpha_text = "\n".join(_format(sa) for sa in alpha_cands) if alpha_cands else "（无）"
        beta_text = "\n".join(_format(sa) for sa in beta_cands) if beta_cands else "（无）"
        novelty_text = "\n".join(_format(sa) for sa in high_novelty) if high_novelty else "（无）"

        return (
            "你是AI行业首席策略分析师。你的输出是决策输入，不是新闻摘要。\n\n"
            "## Alpha候选（结构级变化）\n"
            f"{alpha_text}\n\n"
            "## Beta候选（重要事件）\n"
            f"{beta_text}\n\n"
            "## 高新颖度文章（信号源）\n"
            f"{novelty_text}\n\n"
            f"{self._format_clusters(clusters or [], orphans or [])}"
            f"{self._format_evidence(packages)}"
            "## 信息层级纪律\n\n"
            "严格区分三个层级，不可混淆：\n"
            "- **机制层** (structural_shifts)：底层规则如何被改写。每条必须包含mechanism（因果机制）+ trigger（触发条件）+ consequence（系统级后果）三元组\n"
            "- **事实层** (event_ledger)：纯事实，每条必须分类为capital/capability/behavioral之一。只收录可验证的具体事件（融资/发布/收购/政策/合作/数据披露）\n"
            "- **模式层** (signal_map)：推导链必须走 Events → Mechanism → Hypothesis。禁止直接断言\n\n"
            "## 输出JSON\n"
            "```json\n"
            "{\n"
            '  "executive_judgment": "如果你只看一行就能决策，这句话应该是什么（≤80字）。直接说结构性变化和重新定价",\n'
            '  "structural_shifts": [\n'
            '    {\n'
            '      "title": "变化标题",\n'
            '      "mechanism": "因果机制——什么底层规则被改写了（≤60字）",\n'
            '      "trigger": "触发条件——是什么可观测事件激活了这个变化（≤40字）",\n'
            '      "consequence": "系统级后果——这对行业意味着什么（≤60字）",\n'
            '      "impact": "high/medium/low",\n'
            '      "time_horizon": "short/medium/long",\n'
            '      "source": "来源",\n'
            '      "link": "URL"\n'
            '    }\n'
            '  ],\n'
            '  "event_ledger": [\n'
            '    {\n'
            '      "type": "capital/capability/behavioral/research_result/governance/ecosystem（六选一）",\n'
            '      "title": "事件简述（≤30字）",\n'
            '      "source": "来源",\n'
            '      "link": "URL"\n'
            '    }\n'
            '  ],\n'
            '  "signal_map": [\n'
            '    {\n'
            '      "hypothesis": "推导出的假设（≤60字）",\n'
            '      "supporting_events": ["引用event_ledger中的事件title1", "事件title2"],\n'
            '      "mechanism": "连接事件到假设的因果链（≤80字）"\n'
            '    }\n'
            '  ],\n'
            '  "risks": [\n'
            '    {\n'
            '      "type": "bubble/structural/regime（bubble=短期估值过热 structural=中期系统性风险 regime=长期范式转换风险）",\n'
            '      "horizon": "immediate/structural/long",\n'
            '      "description": "风险描述（≤50字）",\n'
            '      "related_theme": "关联主题ID"\n'
            '    }\n'
            '  ],\n'
            '  "decision_hooks": [\n'
            '    {\n'
            '      "trigger_condition": "触发条件——什么信号出现时执行此动作（以「当...时」开头）",\n'
            '      "action": "具体执行动作",\n'
            '      "rationale": "为什么是现在——时机论证（≤40字）",\n'
            '      "audience": "开发者/创业者/投资人",\n'
            '      "level": "L1/L2/L3"\n'
            '    }\n'
            '  ]\n'
            "}\n"
            "```\n\n"
            "## 硬规则（违反则输出无效）\n"
            "1. structural_shifts：最多2条。每条mechanism/trigger/consequence三元组必填，缺一则无效。只保留真正改变竞争规则的事件（定价权转移、生态控制权变更、技术路径锁定）。普通融资/产品更新不属于这里\n"
            "2. event_ledger：3-8条。每条type字段必填，从以下六类中严格单选：capital=融资/估值/投资/收购，capability=产品/模型/功能发布，behavioral=用户/开发者行为变化/采用率迁移，research_result=研究声明/基准测试/论文性能数据，governance=安全事件/政策变更/合规/开源许可变更，ecosystem=合作伙伴/平台战略/行业标准。Soft-mapping规则：当Evidence声明的类型不完全匹配上述任一类型时，映射到最接近的类型而非丢弃。Event Clusters中的每组evidence已预聚合——每个cluster必须合成至少1个concrete event（除非cluster内无独立事件可提取）。核心约束：每个event必须由至少2条独立Evidence支撑，禁止基于单条evidence生成event。只收录可验证的具体事件，排除趋势观察和观点评论\n"
            "3. signal_map：至少1个模式。必须包含mechanism字段（连接events到hypothesis的因果链）。每个hypothesis必须引用2个以上event_ledger中的事件\n"
            "4. risks：至少2条。type和horizon必须匹配：bubble→immediate, structural→structural, regime→long。至少1条bubble+1条structural\n"
            "5. decision_hooks：至少3条，开发者/创业者/投资人各至少1条。每条必须有trigger_condition（以'当...时'开头）、action（动词开头）、rationale（为什么现在）。禁用：关注、调研、评估、建议、制作报告、构建工具、部署监控\n"
            "   额外禁止：投资买卖/增减仓/创业转型/换工作/系统重构/技术栈迁移/成立团队或小组。单条新闻不足以支撑这类重大动作\n"
            "6. executive_judgment：≤80字。不解释背景，直接说结构性变化+重新定价判断\n"
            "7. L1=今天必须做 L2=本周内做 L3=禁止执行。默认L2\n"
            "8. 中文输出\n"
            "9. Evidence优先规则：\n"
            "   - event_ledger优先从Evidence中选取，source字段必须用Evidence的source URL\n"
            "   - verifiable_fact优先于source_statement\n"
            "   - 有Evidence支撑的事件在title末尾标注[E]\n"
            "10. L2收敛规则（证据冲突时）：\n"
            "   - 置信度加权分 = 0.4*source_reliability + 0.3*evidence_strength + 0.3*verification_status_score\n"
            "     (cross_referenced=0.9, direct_source=0.7, unverified=0.3, disputed=0.1)\n"
            "   - 同事实不同声明差距<0.15: 注明存在争议\n"
            "   - 差距0.15-0.35: 给方向性判断但标注另一来源不同说法\n"
            "   - 差距>0.35: 按高置信度结论，risks中注明被压缩的冲突"
        )

    # ── Cluster formatting (Stage 1.5 input) ──

    @staticmethod
    def _format_clusters(clusters, orphans) -> str:
        """Format Event Pre-Assembler output for LLM prompt.

        Each cluster is a proto-event: grouped evidence that the LLM should
        synthesize into 0-2 concrete events. Orphans are singleton claims.
        """
        if not clusters and not orphans:
            return ""
        parts = ["## Event Clusters（事件预组装）\n"]
        total_ev = sum(len(c) for c in clusters) + len(orphans)
        parts.append(f"{len(clusters)}个cluster + {len(orphans)}个orphan，共{total_ev}条Evidence\n")

        for ci, cluster in enumerate(clusters):
            sources = sorted(set(ev.source.name for ev in cluster))
            parts.append(f"### Cluster {ci + 1}: {len(cluster)} claims | sources: {', '.join(sources[:3])}")
            for ev in cluster:
                parts.append(
                    f"- [{ev.evidence_id}] [{ev.fact_type}] "
                    f"\"{ev.statement[:200]}\" | "
                    f"attr={ev.attribution[:40]} | "
                    f"SR={ev.confidence.source_reliability:.2f} "
                    f"ES={ev.confidence.evidence_strength:.2f}"
                )
            parts.append("")

        if orphans:
            parts.append(f"### Orphans ({len(orphans)} singletons)")
            for ev in orphans[:20]:  # cap orphans to avoid prompt bloat
                parts.append(
                    f"- [{ev.evidence_id}] [{ev.fact_type}] "
                    f"\"{ev.statement[:150]}\" | "
                    f"attr={ev.attribution[:40]}"
                )
            if len(orphans) > 20:
                parts.append(f"  ... +{len(orphans) - 20} more orphans")
            parts.append("")

        return "\n".join(parts) + "\n"

    # ── Evidence formatting (legacy) ──

    @staticmethod
    def _format_evidence(packages):
        if not packages:
            return ""
        total = sum(len(p.evidence) for p in packages)
        parts = [
            f"## Evidence（结构化事实包）\n"
            f"{len(packages)}个事实包，共{total}条Evidence\n",
        ]
        for pkg in packages:
            parts.append(f"### {pkg.topic}")
            parts.append(
                "每条Evidence: statement（声明）、fact_type（source_statement/verifiable_fact）、"
                "confidence（source_reliability + evidence_strength + verification_status）、source URL\n"
            )
            for ev in pkg.evidence:
                parts.append(
                    f"- [{ev.evidence_id}] [{ev.fact_type}] "
                    f"\"{ev.statement[:200]}\" | "
                    f"SR={ev.confidence.source_reliability} "
                    f"ES={ev.confidence.evidence_strength} "
                    f"VS={ev.confidence.verification_status}"
                )
            parts.append("")
        return "\n".join(parts) + "\n"

    def _process_evidence_only(self, ctx, packages):
        evidence_text = self._format_evidence(packages)
        prompt = (
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
        response = self._llm.chat([
            {"role": "system", "content": "You are a chief AI strategy analyst. Return valid JSON only. Chinese."},
            {"role": "user", "content": prompt},
        ])
        data = self._parse_json(response)
        if data and self._looks_like_template(data):
            data = {}

        insight = InsightBrief(
            date=ctx.get("report_date", date.today()),
            executive_judgment=data.get("executive_judgment", ""),
            structural_shifts=[StructuralShift(
                title=s.get("title", ""), mechanism=s.get("mechanism", ""),
                trigger=s.get("trigger", ""), consequence=s.get("consequence", ""),
                impact=s.get("impact", "medium"), time_horizon=s.get("time_horizon", "medium"),
                source=s.get("source", ""), link=s.get("link", ""),
            ) for s in data.get("structural_shifts", [])],
            event_ledger=[EventLedgerItem(
                type=e.get("type", "capability"), title=e.get("title", ""),
                source=e.get("source", ""), link=e.get("link", ""),
            ) for e in data.get("event_ledger", [])],
            signal_map=[SignalMapItem(
                hypothesis=s.get("hypothesis", ""), supporting_events=s.get("supporting_events", []),
                mechanism=s.get("mechanism", ""),
            ) for s in data.get("signal_map", [])],
            decision_hooks=[DecisionHook(
                trigger_condition=d.get("trigger_condition", ""), action=d.get("action", ""),
                rationale=d.get("rationale", ""),
                audience=d.get("audience", "开发者"), level=d.get("level", "L2"),
            ) for d in data.get("decision_hooks", [])],
            risks=[RiskItem(
                type=r.get("type", "bubble"), horizon=r.get("horizon", "immediate"),
                description=r.get("description", ""),
            ) for r in data.get("risks", [])],
        )
        ctx.set("insight_brief", insight)
        return ctx

    # ── risks (LLM + rule-based) ──

    def _build_risks(self, llm_risks: list[dict],
                     alpha_cands: list[ScoredArticle]) -> list[RiskItem]:
        risks: list[RiskItem] = []

        # LLM-generated risks
        for r in llm_risks:
            risks.append(RiskItem(
                type=r.get("type", "bubble"),
                horizon=r.get("horizon", "immediate"),
                description=r.get("description", ""),
                related_theme=r.get("related_theme", ""),
            ))

        # Rule-based: overheated themes from memory
        theme_state = self._load_theme_memory()
        if theme_state:
            seen_themes = {sa.theme_id for sa in alpha_cands if sa.theme_id}
            for tid in seen_themes:
                ts = theme_state.get(tid, {})
                strength = ts.get("strength", 0)
                consec = ts.get("consecutive_days", 0)
                if strength > 0.7 and consec >= 2:
                    risks.append(RiskItem(
                        type="structural",
                        horizon="structural",
                        description=(
                            f"主题「{tid}」连续{consec}天加速(strength={strength:.2f})，"
                            f"主流叙事可能过热，建议反向审视该方向的风险与盲区"
                        ),
                        related_theme=tid,
                    ))

        return risks

    def _load_theme_memory(self) -> dict:
        if not os.path.exists(self._memory_path):
            return {}
        try:
            with open(self._memory_path) as f:
                return json.load(f).get("themes", {})
        except (json.JSONDecodeError, KeyError):
            return {}

    # ── today_themes ──

    @staticmethod
    def _rank_themes(scored: list[ScoredArticle]) -> list[str]:
        theme_articles: dict[str, list[ScoredArticle]] = {}
        for sa in scored:
            if sa.theme_id:
                theme_articles.setdefault(sa.theme_id, []).append(sa)

        if not theme_articles:
            return []

        scored_themes = []
        for tid, articles in theme_articles.items():
            avg_impact = sum(sa.impact for sa in articles) / len(articles)
            score = len(articles) * 0.6 + avg_impact * 0.4
            scored_themes.append((tid, score))

        scored_themes.sort(key=lambda x: x[1], reverse=True)
        return [tid for tid, _ in scored_themes[:3]]

    # ── fallbacks ──

    @staticmethod
    def _fallback_judgment(scored: list[ScoredArticle]) -> str:
        alphas = sum(1 for sa in scored if sa.bucket == Bucket.ALPHA)
        themes = {sa.theme_id for sa in scored if sa.theme_id}
        if alphas:
            return f"今日{len(themes)}个主题活跃，{alphas}条Alpha级信号，建议重点关注。"
        return f"今日{len(themes)}个主题活跃，无Alpha级信号，以跟踪观察为主。"

    def _process_legacy(self, ctx: PipelineContext) -> PipelineContext:
        """Fallback: use Brief when scored_articles unavailable."""
        brief: Brief | None = ctx.get("brief")
        if not brief or not brief.items:
            ctx.set("insight_brief", InsightBrief(date=date.today()))
            return ctx

        items_text = "\n\n".join(
            f"### {i+1}. {item.title}\n"
            f"来源：{item.source}\n"
            f"链接：{item.link}\n"
            f"摘要：{item.digest}"
            for i, item in enumerate(brief.items)
        )

        prompt = (
            "你是AI行业首席策略分析师。以下AI新闻供你研判，生成决策输入。\n\n"
            f"{items_text}\n\n"
            "## 输出JSON\n"
            "```json\n"
            "{\n"
            '  "executive_judgment": "今日判断（≤80字）",\n'
            '  "structural_shifts": [{"title":"T","mechanism":"因果机制","trigger":"触发条件","consequence":"系统级后果","impact":"high/medium/low","time_horizon":"short/medium/long","source":"S","link":"U"}],\n'
            '  "event_ledger": [{"type":"capital/capability/behavioral/research_result/governance/ecosystem","title":"事件简述","source":"S","link":"U"}],\n'
            '  "signal_map": [{"hypothesis":"假设","supporting_events":["e1","e2"],"mechanism":"因果链"}],\n'
            '  "risks": [{"type":"bubble/structural/regime","horizon":"immediate/structural/long","description":"D"}],\n'
            '  "decision_hooks": [{"trigger_condition":"当...时","action":"具体动作","rationale":"为什么现在","audience":"开发者","level":"L2"}]\n'
            "}\n"
            "```\n"
            "规则：structural_shifts最多1条(mechanism/trigger/consequence必填)，event_ledger 3-5条(type必填)，signal_map至少1个(mechanism必填)，decision_hooks至少3条(开发者/创业者/投资人各至少1条,trigger_condition以'当...时'开头)。中文。"
        )

        response = self._llm.chat([
            {"role": "system", "content": "You are a chief AI strategy analyst. Return valid JSON only. Chinese."},
            {"role": "user", "content": prompt},
        ])

        data = self._parse_json(response)
        if data and self._looks_like_template(data):
            data = {}

        insight = InsightBrief(
            date=ctx.get("report_date", date.today()),
            executive_judgment=data.get("executive_judgment", ""),
            structural_shifts=[StructuralShift(
                title=s.get("title", ""), mechanism=s.get("mechanism", ""),
                trigger=s.get("trigger", ""), consequence=s.get("consequence", ""),
                impact=s.get("impact", "medium"), time_horizon=s.get("time_horizon", "medium"),
                source=s.get("source", ""), link=s.get("link", ""),
            ) for s in data.get("structural_shifts", [])],
            event_ledger=[EventLedgerItem(
                type=e.get("type", "capability"), title=e.get("title", ""),
                source=e.get("source", ""), link=e.get("link", ""),
            ) for e in data.get("event_ledger", [])],
            signal_map=[SignalMapItem(
                hypothesis=s.get("hypothesis", ""), supporting_events=s.get("supporting_events", []),
                mechanism=s.get("mechanism", ""),
            ) for s in data.get("signal_map", [])],
            decision_hooks=[DecisionHook(
                trigger_condition=d.get("trigger_condition", ""), action=d.get("action", ""),
                rationale=d.get("rationale", ""),
                audience=d.get("audience", "开发者"), level=d.get("level", "L2"),
            ) for d in data.get("decision_hooks", [])],
            risks=[RiskItem(
                type=r.get("type", "bubble"), horizon=r.get("horizon", "immediate"),
                description=r.get("description", ""),
            ) for r in data.get("risks", [])],
        )
        ctx.set("insight_brief", insight)
        return ctx

    # ── shared helpers ──

    def _looks_like_template(self, data: dict) -> bool:
        """Detect LLM echoing the prompt template instead of generating content."""
        shifts = data.get("structural_shifts", [])
        if shifts:
            for s in shifts:
                title = s.get("title", "")
                mechanism = s.get("mechanism", "")
                trigger = s.get("trigger", "")
                if title and title not in ("变化标题", "标题", "T", "") and \
                   mechanism and mechanism not in ("因果机制——什么底层规则被改写了（≤60字）", "因果机制", "机制", "") and \
                   trigger and trigger not in ("触发条件——是什么可观测事件激活了这个变化（≤40字）", "触发条件", ""):
                    return False
            return True
        # Also check legacy v2 template echo
        for a in data.get("alpha", []):
            title = a.get("title", "")
            if title in ("新闻标题", "标题", ""):
                continue
            conclusion = a.get("conclusion", "")
            if conclusion and conclusion not in ("一句话结论", "结论", ""):
                return False
        if data.get("alpha"):
            return True
        return False

    def _parse_json(self, response: str) -> dict:
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
        logger.warning("Failed to parse synthesize JSON, response preview: %s", response[:200])
        return {}
