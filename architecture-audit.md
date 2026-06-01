# AI Daily 架构审计报告

审计日期：2026-05-31
审计范围：`src/` 全部代码 + `config.yaml` + `DESIGN.md v2.1`
审计目的：评估当前实现与 v2.1 设计之间的差距和冲突

---

## 1. 当前 Pipeline

### 1.1 实际执行流程

```
config.yaml
    │
    ▼
main() ──► ContentRouter.from_config(config)
    │         └── 模块级 set_router()，供 SummarizeStage 内部调用
    │
    ▼
┌────────────────────────────────────────────────────┐
│ PipelineEngine.run()                                │
│   for stage in [Fetch, Filter, Summarize,          │
│                 Synthesize, Output]:               │
│     ctx = stage.process(ctx)                        │
│     save_checkpoint(stage_name)  ← 每阶段后存盘     │
│   return ctx                                        │
└────────────────────────────────────────────────────┘
```

**关键发现**：当前只有一个 PipelineContext 贯穿全流程，所有数据通过字符串 key 读写。引擎负责计时、度量和 checkpoint，不关心 context 中有什么数据。

### 1.2 Stage 明细

#### Stage 1: FetchStage
| 项目 | 值 |
|------|-----|
| 文件 | `src/stages/fetch.py` |
| 类 | `FetchStage` |
| 构造函数依赖 | `RSSAdapter` |
| 输入 context key | `config` |
| 输出 context key | `articles` |
| 数据结构 | `ctx.get("articles")` → `list[Article]` |
| 数据流 | config.feeds → RSSAdapter.fetch() → RawArticle → Article → context |
| LLM 调用 | 无 |
| 抓取类型 | **仅 RSS 元数据（标题+摘要+链接），不抓全文** |

Article 结构（此时 content 为空字符串，score 为 0）：
```python
Article(
    title="...",
    link="...",
    summary="...",       # RSS 摘要
    published=datetime,
    source="Hacker News",
    content="",           # 空
    score=0               # 未评分
)
```

#### Stage 2: FilterStage
| 项目 | 值 |
|------|-----|
| 文件 | `src/stages/filter.py` |
| 类 | `FilterStage` |
| 构造函数依赖 | `LLMAdapter` + `top_n` + `min_score` |
| 输入 context key | `articles` |
| 输出 context key | `articles`（原地覆盖，数量缩减） |
| LLM 调用 | 1 次（评分） |
| 评分维度 | **Impact + Novelty（单维 1-10 分），无 Actionability** |

FilterStage 把 score 写回 Article.score（int），覆盖原值。55 篇 → 10 篇。

**Prompt 位置**：`src/stages/filter.py:39-43`
```python
prompt = (
    "Score each article 1-10 on importance/novelty for a tech "
    "professional's morning briefing.\n"
    "Return JSON only: [{\"index\": 1, \"score\": 7}, ...]\n\n"
    f"{entries}"
)
```
**解决的问题**：从 55 篇中挑出最重要的 10 篇。只做重要性和新颖度的主观排序，不做分桶。

#### Stage 3: SummarizeStage
| 项目 | 值 |
|------|-----|
| 文件 | `src/stages/summarize.py` |
| 类 | `SummarizeStage` |
| 构造函数依赖 | `LLMAdapter` |
| 输入 context key | `articles` |
| 输出 context key | `brief` |
| LLM 调用 | **每篇文章 1 次（共 10 次）** |
| 隐式依赖 | 模块级 `fetch_content()` 函数（通过 `set_router()` 注入） |

**关键架构问题**：SummarizeStage **内置了全文抓取**。`_generate_digest()` 内部调用 `fetch_content()`，成功后用全文做摘要，失败则用 RSS 摘要做 fallback。

**Prompt 位置**：`src/stages/summarize.py:52-59`（有全文时）
```python
prompt = (
    "你是AI行业分析师。针对以下文章输出中文摘要，格式：\n\n"
    "**发生了什么**：一句话简述事件\n"
    "**为什么重要**：一句点出关键意义\n"
    "**影响**：对行业/从业者有什么影响\n\n"
    "约束：每条不超过150字，不编造文章没说的事。\n\n"
    f"标题：{article.title}\n"
    f"正文：{full_text[:3000]}"
)
```
**Prompt 位置**：`src/stages/summarize.py:62-65`（只有 RSS 摘要时）
```python
prompt = (
    "用一句中文简述以下AI新闻，点出它为什么值得关注：\n\n"
    f"标题：{article.title}\n"
    f"摘要：{(article.summary or '')[:500]}"
)
```
**解决的问题**：为每篇文章生成可读摘要。但 3 段式（发生了什么+为什么重要+影响）是"信息复述"而非"决策信号"。

**输出 BriefItem**：
```python
BriefItem(
    title="Anthropic估值近万亿...",
    source="Hacker News",
    score=9,
    digest="**发生了什么**：...\n**为什么重要**：...\n**影响**：...",
    link="https://..."
)
```

#### Stage 4: SynthesizeStage
| 项目 | 值 |
|------|-----|
| 文件 | `src/stages/synthesize.py` |
| 类 | `SynthesizeStage` |
| 构造函数依赖 | `LLMAdapter` |
| 输入 context key | `brief`（10 条 BriefItem） |
| 输出 context key | `insight_brief` |
| LLM 调用 | 1 次（一次合成） |
| 降级策略 | JSON 解析失败则使用空 InsightBrief，OutputStage 回退到 v1 格式 |

**Prompt 位置**：`src/stages/synthesize.py:41-74`
```python
prompt = (
    "你是AI行业首席分析师。以下10条AI新闻摘要供你研判，生成一份决策导向的日报。\n\n"
    ...
    "- Alpha：只选1-2条真正改变行业格局的。每条必须有锐利结论+3个关键变量+1-2条具体行动\n"
    "- Beta：选2-4条重要但非颠覆性的。每条一句话要点\n"
    ...
)
```
**解决的问题**：把 10 条平坦摘要压缩成 Alpha+Beta+Signals+Actions 的分层结构。但**没有输入主题记忆**，**没有 Counter Signal 检测**，**没有 Actionability 评分输入**，**没有分桶标签**。SynthesizeStage 自己在做"隐式分桶"——全凭 LLM 的判断，没有结构化的分数支撑。

**输出 InsightBrief**：
```python
InsightBrief(
    date=date.today(),
    alpha=[AlphaItem, ...],     # 0-2 条
    beta=[BetaItem, ...],       # 0-4 条
    signals=[SignalItem, ...],  # 0-3 条
    actions=[ActionItem, ...],  # 0-3 条
)
```

#### Stage 5: OutputStage
| 项目 | 值 |
|------|-----|
| 文件 | `src/stages/output.py` |
| 类 | `OutputStage` |
| 构造函数依赖 | 无 |
| 输入 context key | `insight_brief`（优先）或 `brief`（回退） |
| 输出 | `output/morning-{date}.md` |
| LLM 调用 | 无 |

输出策略：如果 `insight_brief` 存在且有 Alpha 或 Beta → 渲染 v2 格式（🧠核心变量+⚡次级变化+📉结构信号+🎯行动层）。否则回退到 v1 格式（编号列表）。

---

### 1.3 Stage 间数据流全景

```
PipelineContext (字符串 key 传递)
────────────────────────────────────────────────────────────
config (AppConfig)
    │
    ▼
FetchStage          → ctx.set("articles", list[Article])       [0 LLM calls]
    │
    ▼
FilterStage         → ctx.get("articles") → 原地改 score →     [1 LLM call]
                      ctx.set("articles", list[Article])
    │
    ▼
SummarizeStage      → ctx.get("articles")                       [10 LLM calls]
                      → 逐篇抓全文 (模块级 fetch_content)
                      → 逐篇 LLM 摘要
                      → ctx.set("brief", Brief)
    │
    ▼
SynthesizeStage     → ctx.get("brief")                          [1 LLM call]
                      → ctx.set("insight_brief", InsightBrief)
    │
    ▼
OutputStage         → ctx.get("insight_brief") or ctx.get("brief")
                      → 写 Markdown 文件
────────────────────────────────────────────────────────────
总计：12 次 LLM 调用（1 filter + 10 summarize + 1 synthesize）
```

---

## 2. 当前 Prompt 全景

### 2.1 Filter Prompt
| 位置 | 文件 | 行号 |
|------|------|------|
| 定义 | `src/stages/filter.py` | 39-43 |

**当前解决的问题**：从 55 篇中挑出 Top 10。"importance/novelty" 两个维度的主观排序。

**v2.1 差距**：不评 Actionability。不分 Alpha/Beta/Gamma 桶。输出是排序后的 Article 列表，不是分类后的分桶结果。

### 2.2 Summarize Prompt
| 位置 | 文件 | 行号 |
|------|------|------|
| 定义（有全文） | `src/stages/summarize.py` | 52-59 |
| 定义（无全文） | `src/stages/summarize.py` | 62-65 |

**当前解决的问题**：把长文章压缩成 3 段式中文摘要。

**v2.1 差距**：摘要格式是"信息复述"，不是"决策信号提炼"。没有输出结构性评分。全文抓取和摘要生成耦合在同一个方法里。

### 2.3 Synthesize Prompt
| 位置 | 文件 | 行号 |
|------|------|------|
| 定义 | `src/stages/synthesize.py` | 41-74 |

**当前解决的问题**：10 条摘要 → Alpha/Beta/Signals/Actions 的分层简报。LLM 自己做隐式分桶。

**v2.1 差距**：
- 没有主题记忆输入（不知道 Anthropic 是第 14 次出现）
- 没有分桶标签输入（10 条都喂给 LLM，不做预分桶）
- 没有 Counter Signal 检测指令
- 没有行动分级（Level 1/2/3）
- "今日判断"板块未实现
- 输出结构是 4 板块（Alpha/Beta/Signals/Actions），缺少 🧭今日判断 和 ⚡反向信号

---

## 3. 当前数据结构

### 3.1 完整 Schema 链

```
RawArticle                  ← RSSAdapter 输出
├── title: str
├── link: str
├── summary: str            ← RSS feed 的 description/summary 字段
├── published: datetime
└── source: str             ← FeedConfig.name

        ↓ (FetchStage 转换，content="" score=0)

Article                     ← 管线内主数据结构
├── title: str
├── link: str
├── summary: str
├── published: datetime
├── source: str
├── content: str = ""       ← SummarizeStage 抓取后填入（但当前未回写 Article，只在 local var）
└── score: int = 0          ← FilterStage 写入（唯一评分维度，1-10 整数）

        ↓ (SummarizeStage 转换)

BriefItem                   ← 单篇摘要
├── title: str
├── source: str
├── score: int              ← 继承自 Article.score（单维整数）
├── digest: str             ← LLM 生成的 3 段式摘要
└── link: str

Brief                       ← 摘要集合
├── date: date
└── items: list[BriefItem]

        ↓ (SynthesizeStage 转换)

InsightBrief                ← v2 分层简报（当前用此模型）
├── date: date
├── alpha: list[AlphaItem]
│   ├── title: str
│   ├── source: str
│   ├── link: str
│   ├── conclusion: str     ← "判断"字段
│   ├── variables: list[str] ← "变量"字段
│   └── actions: list[str]  ← "行动"字段（未分级）
├── beta: list[BetaItem]
│   ├── title: str
│   ├── source: str
│   ├── link: str
│   └── point: str           ← "要点"字段
├── signals: list[SignalItem]
│   ├── signal: str
│   └── evidence: list[str]
└── actions: list[ActionItem]
    ├── audience: str        ← "开发者/创业者/投资人"
    └── actions: list[str]   ← 行动列表（未分级，含可能危险的 Level 3 内容）

        ↓ (OutputStage 渲染)

morning-{date}.md           ← 最终 Markdown 文件
```

### 3.2 PipelineContext 的隐式契约

`PipelineContext` 是 `dict[str, Any]`。各 stage 通过字符串 key 读写，没有任何类型约束。当前使用的 key：

| Key | 写入者 | 读取者 | 类型 |
|-----|--------|--------|------|
| `config` | main() | Fetch, Summarize | `AppConfig` |
| `articles` | Fetch, Filter | Filter, Summarize | `list[Article]` |
| `brief` | Summarize | Synthesize, Output | `Brief` |
| `insight_brief` | Synthesize | Output | `InsightBrief` |
| `output_dir` | main() | Output | `str` |
| `output_path` | Output | main() | `str` |
| `llm_adapter` | main() | Output（算成本） | `LLMAdapter` |

### 3.3 模型缺失项对照

v2.1 需要的字段在现有模型中的状态：

| v2.1 需求 | 现有模型 | 状态 |
|----------|---------|------|
| 分维评分 (I/N/A) | `Article.score: int` | **不兼容**。只有一个 int，需要拆成 3 个字段或新建 ScoredArticle |
| Alpha/Beta/Gamma 标签 | 无 | **缺失**。SynthesizeStage 隐式做，没有明确标签 |
| 行动分级 (L1/L2/L3) | `ActionItem.actions: list[str]` | **缺失**。actions 是纯字符串列表，无等级字段 |
| 今日判断 | 无 | **缺失**。InsightBrief 无 judgment 字段 |
| Counter Signal | 无 | **缺失**。InsightBrief 无 counter_signal 字段 |
| 主题元数据 | 无 | **缺失**。Article 无 theme_id/trajectory 字段 |
| 行动支撑来源 | 无 | **不完整**。ActionItem 无 source_articles 字段 |
| ContentConfig | 存在 | OK |

---

## 4. 当前扩展点

### 4.1 如果实现 v2.1：各组件插入位置

```
当前管线                      v2.1 目标管线
────────                     ────────────
Fetch (RSS metadata)
    │                         Fetch (RSS metadata)       ← 不变
    ▼                            │
Filter (Impact 1-10)              ▼
    │                         FilterStage [重写]          ← 改为两维初筛
    ▼                            │ 评分：I+N，筛选 ≥12
Summarize                          │ 输出：15-20 篇 → context["candidates"]
  ├ 抓全文 (隐式)                 ▼
  ├ LLM 摘要                   FetchStage [NEW·提取]      ← 从 Summarize 中拆出
  └ → Brief                      │ 输入：candidates
    │                            │ 抓全文 → content 字段
    ▼                            │ 输出：candidates (含全文)
Synthesize (隐式分桶)              ▼
  └ → InsightBrief             ScoringStage [NEW]         ← 核心新增
    │                            │ 输入：candidates (含全文)
    ▼                            │ 评分：I+N+A 三维
Output (4板块)                   │ 分桶：Alpha/Beta/Gamma 标签
                                 │ 输出：scored_articles (含标签+分数)
                                 ▼
                               ThemeStage [NEW]            ← 核心新增
                                 │ 输入：scored_articles + .theme-memory.json
                                 │ 匹配主题 → 更新 memory
                                 │ 标注文章 theme_id + trajectory
                                 │ 输出：scored_articles + 主题元数据
                                 ▼
                               SynthesizeStage [重写]      ← 大幅重写
                                 │ 输入：Alpha + Beta + 主题上下文
                                 │ 1. 生成今日判断
                                 │ 2. Alpha 判断+变量+行动
                                 │ 3. Beta 一句话要点
                                 │ 4. Counter Signal 检测
                                 │ 5. 结构趋势提取
                                 │ 6. 分级行动清单 (L1/L2)
                                 │ 输出：InsightBriefV2 (新模型)
                                 ▼
                               OutputStage [重写]          ← 6板块渲染
                                 │ 输入：InsightBriefV2
                                 │ 渲染 6 板块
                                 │ 字数校验 + Level 3 过滤
                                 │ 输出：morning-{date}.md
```

### 4.2 为什么这样插入

| 组件 | 插入位置 | 原因 |
|------|---------|------|
| **FetchStage (NEW)** | Filter 之后，Scoring 之前 | Scoring 需要全文才能准确评估 Actionability。全文抓取现在藏在 SummarizeStage 里，必须先拆出来。抓 15-20 篇而非 55 篇（Filter 已初筛），成本可控 |
| **ScoringStage (NEW)** | Fetch 之后，Theme 之前 | 分桶（Alpha/Beta/Gamma）必须在合成之前完成。SynthesizeStage 只处理 Alpha+Beta，Gamma 不进合成。目前 SynthesizeStage 隐式做分桶，没有结构化标签 |
| **ThemeStage (NEW)** | Scoring 之后，Synthesize 之前 | Theme 需要知道哪些文章是 Alpha/Beta（Gamma 不追踪主题）。主题标注后，Synthesize 可以引用连续性和趋势方向 |
| **Counter Signal** | SynthesizeStage 内部 | 依赖当日 Alpha+Beta 的归纳结果（主流叙事），需要在合成阶段完成 |
| **行动分级** | SynthesizeStage 内部 | 属于合成时的约束，通过 prompt + 后处理检查清单实现 |

---

## 5. 风险分析：v2.1 与现有代码的冲突

### 5.1 结构性冲突

#### C1: 全文抓取嵌入 SummarizeStage

**严重程度：高**

`SummarizeStage._generate_digest()` 内部调用 `fetch_content()`。如果不拆出来，ScoringStage 无法获取全文（它排在 Summarize 之前）。

**影响**：必须重写 SummarizeStage 或把 Fetch 提取为独立 Stage。这会影响最多代码行数。

**当前状态**：FetchStage 只抓 RSS 元数据。真正的全文抓取是 SummarizeStage 的内部实现细节。

#### C2: Article.score 是单维 int

**严重程度：高**

`Article.score: int = 0` 只能存一个分数。v2.1 需要三维评分 (Impact, Novelty, Actionability) 和分桶标签 (Alpha/Beta/Gamma)。

**方案 A**：在 Article 上加 `impact`, `novelty`, `actionability`, `bucket` 字段。改动 article.py，影响所有引用 Article 的代码。
**方案 B**：新建 `ScoredArticle` dataclass，在 ScoringStage 输出时创建，不修改 Article。下游代码需适配新类型。

#### C3: InsightBrief 模型不完整

**严重程度：中**

当前 `InsightBrief` 缺少 v2.1 需要的字段：
- `judgment: str` — 今日判断
- `counter_signal: CounterSignalItem | None` — 反向信号
- `actions` 中的 level 字段 — 行动分级
- `alpha` 中的 `theme_trajectory` — 主题轨迹

**影响**：模型需要加字段。现有的 OutputStage 渲染逻辑需要对应更新。

#### C4: PipelineContext 无类型安全

**严重程度：中**

所有 stage 通过字符串 key 读写 `PipelineContext`。新增 ScoringStage 和 ThemeStage 意味着新增更多字符串 key 契约（`candidates`, `scored_articles`, `theme_context`），没有编译时检查。

**影响**：Stage 之间的数据契约全靠约定。加两个新 Stage 后，"数据是哪个 Stage 写入的"变得难以追踪。

#### C5: SummarizeStage=抓取+摘要 耦合

**严重程度：中**

目前 SummarizeStage 做三件事：(a) 抓全文，(b) LLM 摘要，(c) 输出 Brief。如果拆出 Fetch，Summarize 的输入要从 Article（含全文）变成 Article（已抓全文），输出仍然是 Brief。但 BriefItem.digest 格式需要改为更短的"决策简报"风格。

#### C6: 输出模板硬编码

**严重程度：低**

`OutputStage._assemble()` 和 `_render_insight()` 中的格式硬编码在 Python 代码中。v2.1 要改成 6 板块格式，需要改渲染函数。但 config.yaml 的 `output.template` 字段已不再使用（v1.5 开始就没用了）。

### 5.2 Prompt 层面冲突

#### P1: Filter 评分维度不匹配

当前：`"Score each article 1-10 on importance/novelty"` → 单维 1-10
需要：Impact(1-10) + Novelty(1-10) 两维，输出 `[{"index":1, "impact":8, "novelty":7}]`

#### P2: Synthesize 缺少 v2.1 指令

当前 Synthesize prompt 缺失：
- "今日判断"板块指令
- Counter Signal 检测指令
- 行动分级（Level 1/2/3）指令
- 主题连续性引用指令
- Actionability 评分输入（目前只看到摘要文本）

#### P3: Summarize 输出格式需调整

当前摘要格式是 3 段式长文（发生了什么+为什么重要+影响），每条约 150-300 字。v2.1 要求 Alpha ≤120 字、Beta ≤50 字。Summarize 的输出是 Synthesize 的输入，过长的摘要会撑大 Synthesize 的 prompt。需要将 Summarize 改为输出更紧凑的"要点提炼"而非"复述式摘要"。

### 5.3 文件层面冲突

| 文件 | v2.1 需要的改动 | 风险 |
|------|---------------|------|
| `src/models/article.py` | 新增 `ScoredArticle`, `CounterSignalItem`, 扩展 `ActionItem` 加 `level` 字段，扩展 `InsightBrief` 加 `judgment`/`counter_signal` | 向后兼容。现有模型可保留 |
| `src/stages/filter.py` | 重写 prompt 为两维评分 (I+N)。输出候选数从 10 放宽到 15-20 | 低。逻辑结构不变 |
| `src/stages/summarize.py` | 拆出 `fetch_content` 调用。改变摘要输出格式（更短）。 | 高。核心代码重构 |
| `src/stages/synthesize.py` | 大幅重写 prompt。增加 Counter Signal 检测。增加行动分级。引入 Theme 上下文输入 | 高。prompt 和逻辑都变 |
| `src/stages/output.py` | 6 板块渲染。字数校验。Level 3 过滤 | 中。渲染逻辑重写 |
| `src/main.py` | 新增 ScoringStage、ThemeStage、FetchStage 到 pipeline | 低。增加 stage 实例化 |
| `src/stages/fetch.py` | **不动**。继续只抓 RSS 元数据 | 无 |
| `src/stages/fetch_fulltext.py` | **[NEW]** 新建文件。从 SummarizeStage 中提取全文抓取逻辑 | 新建 |
| `src/stages/scoring.py` | **[NEW]** 三维评分+分桶 | 新建 |
| `src/stages/theme.py` | **[NEW]** 主题匹配+ThemeMemory 读写 | 新建 |
| `config.yaml` | 新增 theme 配置段、scoring 配置段 | 低 |
| 测试文件 | 4 个测试需更新（integration, output_stage） | 低。测试覆盖有限 |

### 5.4 LLM 调用数变化

| Stage | 当前调用 | v2.1 预估 | 变化 |
|-------|---------|----------|------|
| Filter | 1 | 1 | 不变 |
| Summarize | 10 | 15-20 | **增多**（候选池放大） |
| Scoring | 不存在 | 1 | **新增** |
| Theme | 不存在 | 1 | **新增** |
| Synthesize | 1 | 1 | 不变 |
| **总计** | **12** | **20-24** | **约翻倍** |

费用影响：当前约 ¥0.04/次，v2.1 预估 ¥0.06-0.08/次。仍然极低。

---

## 6. 已解决的设计问题（v2.0 → v2.1 对照）

| v2.0 设计问题 | 当前代码体现 | v2.1 修复方向 |
|-------------|-------------|-------------|
| Actionability 缺失 | FilterStage 只评 I+N | ScoringStage 加 A 维度 |
| 无分桶 | Synthesize 隐式做 | ScoringStage 显式分桶 |
| 无主题记忆 | 每天独立，context 不跨天 | ThemeStage + .theme-memory.json |
| 无 Counter Signal | Synthesize 只做正向归纳 | 在 Synthesize prompt 中加 CS 检测 |
| 行动建议无分级 | ActionItem.actions 不区分等级 | ActionItem 加 level 字段 + prompt 约束 |

---

## 7. 总结

**当前架构的强项**：
- Stage 接口统一（`process(ctx) → ctx`），插入新 Stage 成本低
- Checkpoint 机制已工作，新 Stage 自动受益
- 模型层和 Stage 层分离清晰，新增模型不破坏现有 Stage

**当前架构的弱点**：
- 全文抓取藏在 SummarizeStage 内部，是最大的重构障碍
- Article.score 单维 int 无法承载三维评分
- PipelineContext 无类型，5 个以上的 Stage 时数据流向难以追踪
- InsightBrief 模型需要扩展才能承载 v2.1 的 6 板块输出

**实现 v2.1 的最小路径**：
1. 拆出 FetchStage（从 Summarize 中提取全文抓取） → 影响 1 个文件
2. 扩展数据模型（ScoredArticle、CounterSignalItem、扩展 InsightBrief） → 影响 1 个文件
3. 新建 ScoringStage → 新建 1 个文件
4. 新建 ThemeStage → 新建 1 个文件
5. 重写 SynthesizeStage prompt → 影响 1 个文件
6. 重写 OutputStage 渲染 → 影响 1 个文件
7. 更新 main.py 管线组装 → 影响 1 个文件

预计改动 5 个现有文件 + 新建 2 个文件。核心风险在步骤 1（Fetch 提取）和步骤 5（Synthesize prompt 质量）。
