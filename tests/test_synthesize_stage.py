import json
import os
import tempfile
from datetime import date
from unittest.mock import MagicMock

from src.pipeline.stage import PipelineContext
from src.stages.synthesize import SynthesizeStage
from src.models.article import Article, Brief, BriefItem, InsightBrief
from src.models.scored_article import ScoredArticle, Bucket


def make_article(title="Test", source="Feed", link="https://x.com/1",
                 content="Some content text about AI.", summary="AI summary"):
    return Article(
        title=title, link=link, summary=summary,
        published=date.today(), source=source, content=content,
    )


def make_scored(article=None, impact=7, novelty=5, actionability=5,
                bucket=Bucket.BETA, theme_id=None, trajectory="NEW"):
    if article is None:
        article = make_article()
    return ScoredArticle(
        article=article, impact=impact, novelty=novelty,
        actionability=actionability, bucket=bucket,
        theme_id=theme_id, trajectory=trajectory,
    )


# ── v3 scored_articles path ──

def test_synthesize_from_scored_articles():
    """v3 path: scored_articles → InsightBrief with triad structural_shifts, typed events, etc."""
    sa1 = make_scored(
        make_article(title="Copilot goes token-based", source="TC", link="https://x.com/1",
                     content="GitHub Copilot switches from subscription to token-based pricing."),
        impact=9, novelty=8, actionability=8, bucket=Bucket.ALPHA,
        theme_id="anthropic_scaling", trajectory="ACCELERATE",
    )
    sa2 = make_scored(
        make_article(title="Groq raises $650M", source="TC2", link="https://x.com/2",
                     content="AI chip startup Groq raises $650M to challenge NVIDIA."),
        impact=7, novelty=6, actionability=5, bucket=Bucket.BETA,
        theme_id="ai_hardware",
    )

    llm = MagicMock()
    llm.chat.return_value = json.dumps({
        "executive_judgment": "AI工具层从订阅制向token经济迁移，开发者工具定价权被重新分配。",
        "structural_shifts": [
            {
                "title": "AI工具定价模型迁移",
                "mechanism": "GitHub Copilot从订阅转向token计费，开发者锁定成本上升",
                "trigger": "GitHub正式推出token计费模式",
                "consequence": "企业AI工具开支结构从固定成本→可变成本，中小团队可能被挤出",
                "impact": "high",
                "time_horizon": "medium",
                "source": "TC",
                "link": "https://x.com/1",
            }
        ],
        "event_ledger": [
            {"type": "capability", "title": "GitHub Copilot转向token计费", "source": "TC", "link": "https://x.com/1"},
            {"type": "capital", "title": "Groq完成6.5亿美元融资", "source": "TC2", "link": "https://x.com/2"},
        ],
        "signal_map": [
            {
                "hypothesis": "AI基础设施定价权从用户向平台转移",
                "supporting_events": ["GitHub Copilot转向token计费", "Groq完成6.5亿美元融资"],
                "mechanism": "工具层token计费+硬件层资本密集→平台和芯片商掌握定价主导权，用户选择空间收窄",
            }
        ],
        "risks": [
            {"type": "bubble", "horizon": "immediate", "description": "AI芯片融资热度远超实际营收增长", "related_theme": "ai_hardware"},
            {"type": "structural", "horizon": "structural", "description": "token计费可能加速开发者向开源工具迁移", "related_theme": "anthropic_scaling"},
        ],
        "decision_hooks": [
            {"trigger_condition": "当GitHub Copilot正式公布token单价时", "action": "计算团队月度成本变化并制定预算调整方案", "rationale": "定价窗口期有限，先动者有迁移时间优势", "audience": "开发者", "level": "L1"},
            {"trigger_condition": "当Groq估值超过NVIDIA市值的5%时", "action": "重新评估AI硬件投资组合的风险敞口", "rationale": "独角兽估值加速暗示泡沫风险积累", "audience": "投资人", "level": "L2"},
            {"trigger_condition": "当至少2家主要AI工具商转为token计费时", "action": "启动内部AI工具成本审计并制定替代方案", "rationale": "行业级定价迁移一旦形成，替代成本将大幅上升", "audience": "创业者", "level": "L2"},
        ],
    })

    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = os.path.join(tmpdir, ".theme-memory.json")
        with open(mem_path, "w") as f:
            json.dump({
                "themes": {
                    "ai_hardware": {"strength": 0.85, "consecutive_days": 3},
                }
            }, f)

        ctx = PipelineContext()
        ctx.set("scored_articles", [sa1, sa2])
        stage = SynthesizeStage(llm, memory_path=mem_path)
        result = stage.process(ctx)

        insight = result.get("insight_brief")
        assert insight is not None

        # Executive judgment
        assert "token" in insight.executive_judgment

        # Structural shifts — triad required
        assert len(insight.structural_shifts) == 1
        s = insight.structural_shifts[0]
        assert s.mechanism
        assert s.trigger
        assert s.consequence
        assert s.impact == "high"

        # Event ledger — typed
        assert len(insight.event_ledger) == 2
        types = {e.type for e in insight.event_ledger}
        assert "capital" in types
        assert "capability" in types

        # Signal map — derivation chain
        assert len(insight.signal_map) == 1
        sig = insight.signal_map[0]
        assert sig.mechanism  # causal chain required
        assert len(sig.supporting_events) == 2

        # Risks — horizon required, LLM (2) + memory-driven (1 structural)
        assert len(insight.risks) >= 2
        risk_types = {r.type for r in insight.risks}
        assert "bubble" in risk_types

        # Decision hooks — trigger condition required
        assert len(insight.decision_hooks) == 3
        audiences = {h.audience for h in insight.decision_hooks}
        assert len(audiences) == 3  # all 3 audiences covered
        for h in insight.decision_hooks:
            assert h.trigger_condition
            assert h.rationale

        # Today themes
        assert len(insight.today_themes) == 2


def test_synthesize_structural_signals_from_memory():
    """Rule-based overheated themes produce structural RiskItems with horizon."""
    sa = make_scored(
        make_article(title="Agent hype", source="TC", link="https://x.com/1"),
        impact=9, novelty=7, actionability=8, bucket=Bucket.ALPHA,
        theme_id="agent_stack", trajectory="ACCELERATE",
    )

    llm = MagicMock()
    llm.chat.return_value = json.dumps({
        "executive_judgment": "Agent叙事持续升温。",
        "structural_shifts": [],
        "event_ledger": [{"type": "capability", "title": "OpenAI发布Agent SDK", "source": "TC", "link": "https://x.com/1"}],
        "signal_map": [],
        "risks": [{"type": "bubble", "horizon": "immediate", "description": "Agent赛道估值过热"}],
        "decision_hooks": [
            {"trigger_condition": "当Agent SDK使用率达到20%时", "action": "评估Agent集成方案", "rationale": "早期采用窗口", "audience": "开发者", "level": "L2"},
            {"trigger_condition": "当Agent赛道融资额季度翻倍时", "action": "重新定价Agent投资", "rationale": "泡沫信号", "audience": "投资人", "level": "L2"},
            {"trigger_condition": "当Agent相关开源项目周增长>50时", "action": "启动Agent产品线", "rationale": "市场验证信号", "audience": "创业者", "level": "L2"},
        ],
    })

    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = os.path.join(tmpdir, ".theme-memory.json")
        with open(mem_path, "w") as f:
            json.dump({"themes": {
                "agent_stack": {"strength": 0.85, "consecutive_days": 3},
            }}, f)

        ctx = PipelineContext()
        ctx.set("scored_articles", [sa])
        stage = SynthesizeStage(llm, memory_path=mem_path)
        result = stage.process(ctx)

        insight = result.get("insight_brief")
        # Should have memory-driven structural risk
        struct_risks = [r for r in insight.risks if r.type == "structural"]
        assert len(struct_risks) >= 1
        assert struct_risks[0].horizon == "structural"
        assert "agent_stack" in struct_risks[0].description


def test_synthesize_empty_scored_articles():
    """Empty scored_articles → all fields empty, LLM never called."""
    llm = MagicMock()
    ctx = PipelineContext()
    ctx.set("scored_articles", [])
    stage = SynthesizeStage(llm)
    result = stage.process(ctx)
    insight = result.get("insight_brief")
    assert insight.structural_shifts == []
    assert insight.event_ledger == []
    assert insight.signal_map == []
    assert insight.decision_hooks == []


def test_synthesize_legacy_fallback():
    """When only brief is available, fall back to legacy path producing v3 structure."""
    items = [
        BriefItem(title="AI News", source="Feed", score=7,
                  digest="Something about AI happened.", link="https://x.com/1"),
    ]
    brief = Brief(date=date.today(), items=items)

    llm = MagicMock()
    llm.chat.return_value = json.dumps({
        "executive_judgment": "今日AI行业平稳。",
        "structural_shifts": [],
        "event_ledger": [
            {"type": "capability", "title": "OpenAI发布新模型", "source": "Feed", "link": "https://x.com/1"},
        ],
        "signal_map": [],
        "risks": [{"type": "bubble", "horizon": "immediate", "description": "测试风险"}],
        "decision_hooks": [
            {"trigger_condition": "当新模型API可用时", "action": "测试新模型API", "rationale": "抢占先发优势", "audience": "开发者", "level": "L2"},
            {"trigger_condition": "当竞品发布同类产品时", "action": "重新评估产品路线图", "rationale": "竞争窗口收窄", "audience": "创业者", "level": "L2"},
            {"trigger_condition": "当API定价公布时", "action": "计算投资回报周期", "rationale": "定价低于预期则加仓", "audience": "投资人", "level": "L2"},
        ],
    })

    ctx = PipelineContext()
    ctx.set("brief", brief)
    stage = SynthesizeStage(llm)
    result = stage.process(ctx)

    insight = result.get("insight_brief")
    assert len(insight.event_ledger) == 1
    assert insight.event_ledger[0].type == "capability"
    assert len(insight.decision_hooks) == 3
    assert insight.executive_judgment


def test_synthesize_json_fallback_uses_defaults():
    """When LLM returns garbage, JSON parsing fails gracefully with fallback judgment."""
    sa = make_scored(bucket=Bucket.ALPHA, impact=9, theme_id="agent_stack")
    llm = MagicMock()
    llm.chat.return_value = "not valid json {{{"
    ctx = PipelineContext()
    ctx.set("scored_articles", [sa])
    stage = SynthesizeStage(llm)
    result = stage.process(ctx)
    insight = result.get("insight_brief")
    assert insight.executive_judgment
    assert insight.structural_shifts == []


def test_synthesize_template_echo_discarded():
    """When LLM echoes the prompt template, output is discarded."""
    sa = make_scored(bucket=Bucket.ALPHA, impact=9)
    llm = MagicMock()
    llm.chat.return_value = json.dumps({
        "executive_judgment": "一句话：今天什么结构变了，什么被重新定价。不解释不展开（≤80字）",
        "structural_shifts": [
            {"title": "变化标题", "mechanism": "因果机制——什么底层规则被改写了（≤60字）",
             "trigger": "触发条件——是什么可观测事件激活了这个变化（≤40字）",
             "consequence": "", "impact": "high", "time_horizon": "medium", "source": "", "link": ""}
        ],
        "event_ledger": [],
        "signal_map": [],
        "risks": [],
        "decision_hooks": [],
    })
    ctx = PipelineContext()
    ctx.set("scored_articles", [sa])
    stage = SynthesizeStage(llm)
    result = stage.process(ctx)
    insight = result.get("insight_brief")
    assert insight.structural_shifts == []
    assert insight.executive_judgment


def test_synthesize_today_themes_ranking():
    """Themes ranked by frequency×0.6 + avg_impact×0.4, capped at 3."""
    articles = [
        make_scored(make_article(title="A1"), impact=9, theme_id="agent_stack"),
        make_scored(make_article(title="A2"), impact=7, theme_id="agent_stack"),
        make_scored(make_article(title="B1"), impact=5, theme_id="ai_hardware"),
        make_scored(make_article(title="C1"), impact=3, theme_id="regulation"),
        make_scored(make_article(title="D1"), impact=8, theme_id="opensource_ai"),
    ]
    ranked = SynthesizeStage._rank_themes(articles)
    assert ranked[0] == "agent_stack"
    assert len(ranked) == 3
