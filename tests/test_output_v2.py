import os
import tempfile
from datetime import date
from src.pipeline.stage import PipelineContext
from src.stages.fetch import FeedHealth, HealthReport
from src.stages.output import OutputStage, _render_insight_v3, _render_decision_hooks, _render_health
from src.policy.output_policy import normalize_audience, should_render_action, safe_value
from src.models.article import (
    StructuralShift, EventLedgerItem, SignalMapItem, RiskItem, DecisionHook, InsightBrief,
)


def make_insight(**overrides) -> InsightBrief:
    defaults = dict(
        date=date.today(),
        executive_judgment="",
        structural_shifts=[],
        event_ledger=[],
        signal_map=[],
        risks=[],
        decision_hooks=[],
        today_themes=[],
    )
    defaults.update(overrides)
    return InsightBrief(**defaults)


# ── audience normalization (policy layer) ──

def test_normalize_audience_developer():
    assert normalize_audience("开发者") == "developer"
    assert normalize_audience("engineer") == "developer"


def test_normalize_audience_builder():
    assert normalize_audience("创业者") == "builder"
    assert normalize_audience("founder") == "builder"


def test_normalize_audience_investor():
    assert normalize_audience("投资人") == "investor"
    assert normalize_audience("VC") == "investor"


def test_normalize_audience_defaults_to_developer():
    assert normalize_audience("未知角色") == "developer"


# ── L3 filtering ──

def test_l3_actions_filtered():
    insight = make_insight(decision_hooks=[
        DecisionHook(trigger_condition="当X时", action="正常操作", rationale="合理", audience="开发者", level="L2"),
        DecisionHook(trigger_condition="当Y时", action="危险操作", rationale="不合理", audience="投资人", level="L3"),
    ])
    output = _render_decision_hooks(insight)
    assert "正常操作" in output
    assert "危险操作" not in output


def test_high_risk_actions_filtered_even_when_l2():
    insight = make_insight(decision_hooks=[
        DecisionHook(trigger_condition="当成本公布时", action="计算团队月度成本变化", rationale="合理", audience="开发者", level="L2"),
        DecisionHook(trigger_condition="当估值变化时", action="增持Anthropic相关投资标的", rationale="过度推导", audience="投资人", level="L2"),
        DecisionHook(trigger_condition="当论文通过评审时", action="成立跨部门科学AI小组", rationale="组织动作过重", audience="创业者", level="L2"),
    ])
    output = _render_decision_hooks(insight)
    assert "计算团队月度成本变化" in output
    assert "增持Anthropic" not in output
    assert "成立跨部门" not in output


def test_health_render_includes_adapter_type():
    ctx = PipelineContext()
    ctx.set("health_report", HealthReport(feeds=[
        FeedHealth(name="Reddit r/ML", priority=2, feed_type="reddit_json", status="degraded", article_count=0),
        FeedHealth(name="Meta AI Blog", priority=1, feed_type="meta_ai_blog", status="failed", article_count=0),
    ]))
    output = _render_health(ctx)
    assert "Reddit r/ML(reddit_json)" in output
    assert "Meta AI Blog(meta_ai_blog)" in output


# ── v3 6-section rendering ──

def test_render_insight_v3_has_6_sections():
    insight = make_insight(
        executive_judgment="AI工具层从订阅制向token经济迁移，开发者工具定价权被重新分配。",
        structural_shifts=[
            StructuralShift(
                title="AI工具定价模型迁移",
                mechanism="GitHub Copilot从订阅转向token计费，开发者锁定成本上升",
                trigger="GitHub正式宣布token计费模式上线",
                consequence="企业AI工具开支结构从固定成本→可变成本，中小团队可能被挤出",
                impact="high",
                time_horizon="medium",
                source="TechCrunch AI",
                link="https://x.com/1",
            )
        ],
        event_ledger=[
            EventLedgerItem(type="capability", title="GitHub Copilot转向token计费", source="TechCrunch AI", link="https://x.com/1"),
            EventLedgerItem(type="capital", title="Groq完成6.5亿美元融资", source="TechCrunch AI", link="https://x.com/2"),
            EventLedgerItem(type="behavioral", title="开发者社区对token计费表示强烈不满", source="Hacker News", link="https://x.com/3"),
        ],
        signal_map=[
            SignalMapItem(
                hypothesis="AI基础设施定价权从用户向平台转移",
                supporting_events=["GitHub Copilot转向token计费", "Groq完成6.5亿美元融资"],
                mechanism="工具层token计费+硬件层资本密集→平台和芯片商掌握定价主导权",
            )
        ],
        risks=[
            RiskItem(type="bubble", horizon="immediate", description="AI芯片融资热度远超实际营收增长", related_theme="ai_hardware"),
            RiskItem(type="structural", horizon="structural", description="token计费可能加速开发者向开源工具迁移", related_theme="anthropic_scaling"),
        ],
        decision_hooks=[
            DecisionHook(trigger_condition="当GitHub Copilot公布token单价时", action="计算团队月度成本变化", rationale="定价窗口期有限", audience="开发者", level="L1"),
            DecisionHook(trigger_condition="当2家以上AI工具商转为token计费时", action="启动内部AI成本审计", rationale="行业级迁移一旦形成替代成本上升", audience="创业者", level="L2"),
            DecisionHook(trigger_condition="当Groq估值超NVIDIA市值5%时", action="重新评估AI硬件风险敞口", rationale="独角兽估值暗示泡沫积累", audience="投资人", level="L2"),
        ],
        today_themes=["agent_stack", "ai_hardware"],
    )

    md = _render_insight_v3(insight)

    # 6 sections present
    assert "## 1. 🧭 Executive Judgment" in md
    assert "## 2. ⚙️ Structural Shifts" in md
    assert "## 3. 📦 Event Ledger" in md
    assert "## 4. 📡 Signal Map" in md
    assert "## 5. ⚠️ Risk Layer" in md
    assert "## 6. 🧾 Decision Hooks" in md

    # Structural shift triad
    assert "**机制**" in md
    assert "**触发**" in md
    assert "**后果**" in md
    assert "GitHub正式宣布" in md

    # Event types
    assert "💰 Capital" in md
    assert "⚡ Capability" in md
    assert "👥 Behavioral" in md

    # Signal derivation chain
    assert "**因果链**" in md

    # Risk horizon
    assert "now" in md  # immediate → now
    assert "mid" in md  # structural → mid

    # Decision hooks — trigger conditions displayed
    for hook in insight.decision_hooks:
        assert hook.trigger_condition in md

    # Theme display
    assert "`agent_stack`" in md


def test_render_empty_fields_show_none():
    insight = make_insight()
    md = _render_insight_v3(insight)
    assert "_None_" in md


def test_render_structural_shift_triad():
    insight = make_insight(
        structural_shifts=[
            StructuralShift(
                title="定价权转移",
                mechanism="从订阅制→token制",
                trigger="平台宣布新计费模式",
                consequence="用户迁移成本上升",
                impact="high",
                time_horizon="short",
                source="Feed",
                link="https://x.com/1",
            )
        ],
    )
    md = _render_insight_v3(insight)
    assert "从订阅制→token制" in md
    assert "平台宣布新计费模式" in md
    assert "用户迁移成本上升" in md


def test_render_event_ledger_grouped_by_type():
    insight = make_insight(
        event_ledger=[
            EventLedgerItem(type="capital", title="融资1亿美元", source="A", link="https://x.com/1"),
            EventLedgerItem(type="capability", title="发布新模型", source="B", link="https://x.com/2"),
        ],
    )
    md = _render_insight_v3(insight)
    assert "💰 Capital" in md
    assert "⚡ Capability" in md
    assert "融资1亿美元" in md
    assert "发布新模型" in md


def test_render_decision_hooks_show_trigger_rationale():
    insight = make_insight(
        decision_hooks=[
            DecisionHook(trigger_condition="当API定价公布时", action="计算成本", rationale="窗口期3天", audience="开发者", level="L1"),
        ],
    )
    md = _render_decision_hooks(insight)
    assert "当API定价公布时" in md
    assert "计算成本" in md
    assert "窗口期3天" in md


# ── full OutputStage v3 path ──

def test_output_stage_v3_writes_6_section_markdown():
    insight = make_insight(
        executive_judgment="Agent标准化的叙事从共识期→质疑期转折。",
        structural_shifts=[
            StructuralShift(
                title="Agent协议信任危机",
                mechanism="MCP协议在上下文消耗和可靠性方面的缺陷暴露",
                trigger="Quandri发布实验报告质疑MCP可靠性",
                consequence="协议定价权从标准制定者向实现者转移",
                impact="high",
                time_horizon="medium",
                source="Hacker News",
                link="https://x.com/1",
            )
        ],
        event_ledger=[
            EventLedgerItem(type="capability", title="Quandri发布MCP可靠性实验报告", source="HN", link="https://x.com/1"),
            EventLedgerItem(type="capital", title="OpenRouter完成1.13亿美元B轮融资", source="HN", link="https://x.com/2"),
        ],
        signal_map=[
            SignalMapItem(
                hypothesis="中间层协议信任危机可能驱动API层价值重估",
                supporting_events=["Quandri发布MCP可靠性实验报告", "OpenRouter完成1.13亿美元B轮融资"],
                mechanism="协议层受质疑→资本流向API聚合层→中间件价值从协议向API转移",
            )
        ],
        risks=[
            RiskItem(type="bubble", horizon="immediate", description="AI模型聚合平台估值可能脱离基本面", related_theme="agent_stack"),
        ],
        decision_hooks=[
            DecisionHook(trigger_condition="当至少2篇独立报告质疑MCP可靠性时", action="列出MCP替代方案技术路径图", rationale="协议信任一旦破裂，迁移成本将被重新定价", audience="开发者", level="L1"),
            DecisionHook(trigger_condition="当OpenRouter估值突破20亿美元时", action="评估API聚合层是否进入泡沫区间", rationale="估值增长脱离用户增速是典型泡沫前兆", audience="投资人", level="L2"),
            DecisionHook(trigger_condition="当主要云厂商推出自研Agent协议时", action="评估对当前产品架构的兼容性影响", rationale="云厂商入局将重塑协议标准竞争格局", audience="创业者", level="L2"),
        ],
        today_themes=["agent_stack"],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = PipelineContext()
        ctx.set("insight_brief", insight)
        ctx.set("output_dir", tmpdir)
        ctx.set("llm_adapter", None)

        stage = OutputStage()
        result = stage.process(ctx)

        output_path = result.get("output_path")
        assert os.path.exists(output_path)

        content = open(output_path).read()
        assert "🧠 AI Daily Report" in content
        assert "## 1. 🧭 Executive Judgment" in content
        assert "## 2. ⚙️ Structural Shifts" in content
        assert "## 3. 📦 Event Ledger" in content
        assert "## 4. 📡 Signal Map" in content
        assert "## 5. ⚠️ Risk Layer" in content
        assert "## 6. 🧾 Decision Hooks" in content
        assert "Agent协议信任危机" in content
        assert "MCP替代方案" in content
        assert "bubble" in content.lower()


def test_output_stage_v3_falls_back_to_v1_when_no_insight():
    """When insight_brief is absent, fall back to Brief-based v1 render."""
    from src.models.article import Brief, BriefItem
    items = [
        BriefItem(title="Old School News", source="FeedA", score=7,
                  digest="Legacy digest text.", link="https://x.com/1"),
    ]
    brief = Brief(date=date.today(), items=items)

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = PipelineContext()
        ctx.set("brief", brief)
        ctx.set("output_dir", tmpdir)

        stage = OutputStage()
        result = stage.process(ctx)

        content = open(result.get("output_path")).read()
        assert "Old School News" in content
        assert "## 1. 🧭 Executive Judgment" not in content
