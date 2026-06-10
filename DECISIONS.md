# 决策记录 (DECISIONS.md)
> 记录关键决策及理由，防止半年后重新讨论、重新踩坑。只记影响方向的决策。最新在最上。

## [2026-06-10] 停用 ai-daily-l0.timer：集成前脚手架，主管线已含 L0
- 决定：systemctl --user stop + disable ai-daily-l0.timer（保留单元文件不删除，可随时回滚）。
- 原因：时间线证实其为遗留——timer 创建于 06-03 19:25，L0CaptureStage 于 06-04 01:29（commit 34b26bf）合入主管线，此后每天 L0 重复执行两次；l0-daily-run.sh 从未入 git。
- 考虑过的替代方案：保留作冗余备份。被否决——两个 timer 无 systemd 依赖关系、启动顺序随机，l0 脚本的 lockfile 不防主管线，是竞态来源而非冗余。
- 状态：生效中。注意：systemd 层变更 git 管不到，回滚方式为 `systemctl --user enable --now ai-daily-l0.timer`。

## [2026-06-10] 保留 daily_pipeline.py → visual-compiler 的跨 skill 快照写入
- 决定：保留 daily_pipeline.py 向 `~/.claude/skills/wechat-article-engine/visual-compiler/snapshots/` 写入快照的耦合。
- 原因：该目录是 visual-compiler 四个模块（runner/governor/repair/snapshot）的约定接口，其 diff/governor 机制依赖它，现在拆除是制造问题而非解决问题。
- 考虑过的替代方案：快照改存本项目 output/snapshots/ 由对方来读。被否决——需要改动对方 skill 内部，收益不抵风险。
- 风险（排障线索）：该 skill 不受本项目版本控制，其内部变更会静默破坏本管线。若 daily_pipeline 步骤无故失败，先查 visual-compiler 是否有变更。
- 状态：生效中

## [2026-06-04] EDITORIAL-ABI v1.0 冻结：v1.0 只观测不丢弃
- 决定：在 L2 (Content Compiler) 和 L3 (Article Compiler) 之间插入 Narrative Selection 层（L3.5）。v1.0 阶段只标注叙事角色，不丢弃任何事件。所有事件仍全量进入文章。
- 原因：L3 目前只做渲染不做编辑抉择。需要先积累 telemetry 数据（哪个 source 产出的事件被反复分配为 hook/pivot/amplifier），再靠数据决定丢弃阈值。
- 考虑过的替代方案：直接启用 Narrative Discard。被否决——没有 telemetry 数据就设阈值等于瞎猜。
- 状态：生效中（v1.0 FROZEN）。v2.0 启用丢弃，阈值由 editorial_fingerprint.json 反推。

## [2026-06-03] Pipeline Observability：四段 Yield 链替代单一 adoption rate
- 决定：从只盯 adoption rate 改为追踪四段 Yield 链（Evidence Yield → Event Yield → Adoption Yield → Domain Adoption）。
- 原因：adoption 是管线最后环节。单看它无法回答"系统在变好还是信息在被丢掉"。四段链让每层的吞信息量可见。
- 考虑过的替代方案：保留单一 adoption 指标。被否决——无法定位瓶颈。
- 状态：生效中（ACTIVE v1.0）

## [2026-06-03] ONTOLOGY v2：事件分类从 3 类扩展到 6 类
- 决定：将 event_ledger 分类从 {capital, capability, behavioral} 改为 {announcement, research_result, observation, benchmark, policy, ecosystem}。
- 原因：v1 三分类在 36-evidence 生产运行中 adoption rate = 0%。sources 实际产出的信息结构与三分类不匹配。
- 考虑过的替代方案：保留三分类并修改 sources 产出格式。被否决——应该让分类适配真实信息结构，而非反之。
- 状态：生效中（ACTIVE v2.0）。已替代 v1.0。

## [2026-06-03] EVIDENCE-ABI v1.0：三层对象分离
- 决定：定义 Artifact（原材料）/ Evidence（结构化事实）/ Package（已组装证据包）三层分离。Evidence Layer 保留冲突，不自行裁决。
- 原因：之前 Artifact 和 Evidence 混在一起，无法追溯"这个事实来自哪个源"。冲突裁决应由上层（L2）执行。
- 考虑过的替代方案：在 L1 做冲突裁决。被否决——L1 应该保留真相全貌，裁决会提前丢弃信息。
- 状态：生效中（FROZEN v1.0）

## [2026-06-03] L2 Convergence Spec：冲突收敛规则
- 决定：定义 L2 在收到含冲突 Evidence 时的合法行为空间。冲突裁决必须输出 `converged / disputed / escalated` 三态之一。
- 原因：EVIDENCE-ABI §5 规定冲突保留在 L1、裁决在 L2，但裁决规则从未被定义。同一 Package 两次独立 L2 调用可能产生不同结论。
- 考虑过的替代方案：不做定义，依赖 LLM 自行判断。被否决——不可复现的结果不可验收。
- 状态：DRAFT v0.1

## [2026-06-02] Content IR v1.0：Markdown ↔ Visual Compiler 的结构化桥
- 决定：定义 Content IR JSON schema，作为 AI 日报 Markdown 输出和 Visual Compiler 之间的结构化中间表示。Content IR 只表达语义，不表达视觉。
- 原因：Visual Compiler 需要机器可读的输入。直接从 Markdown 解析不稳定，且 Markdown 结构变化会破坏下游。
- 考虑过的替代方案：Visual Compiler 直接消费 Markdown。被否决——Visual Compiler 不应该依赖 Markdown 的具体排版格式。
- 状态：生效中（SPECIFICATION v1.0）

## [2026-05~06] DESIGN v2.1：多项结构性修正
以下决策在同一轮架构评审中做出，彼此关联：

### Alpha 重定义：从"不可逆"到"新颖密度"
- 决定：移除"不可逆"判据，替换为"新颖密度"（与 Theme Memory 比对是否偏离趋势线）。
- 原因："不可逆"需要预知未来，生成时无法判断。2023 年的 AutoGPT、Humane AI Pin 在当时都会被判"不可逆"，事后证明不是。
- 考虑过的替代方案：保留不可逆但标注"推测"。被否决——不可验证的维度在操作上没有意义。
- 状态：生效中

### 评分模型：乘法 → 加权加法
- 决定：从 `Impact × Novelty × Actionability` 改为 `0.5×I + 0.3×N + 0.2×A`。
- 原因：乘法模型过度惩罚高 Impact 低 Actionability 事件（美国 AI 监管法案 270 分 vs API 开放 378 分）。Actionability 权重隐性过高。
- 考虑过的替代方案：调权重但保留乘法。被否决——乘法分布不可控，中段（100-500）挤了大量内容。
- 状态：生效中

### Action Framework 三级行动体系
- 决定：所有行动建议分为 L1 直接行动 / L2 观察 / L3 禁止输出。L3 硬阻断：禁止建议读者创业/转型/重构/换工作。
- 原因：LLM 存在"建议过拟合"——从融资新闻推导"你应该创业"。证据链条断裂的单点新闻不足以支撑根本改变建议。
- 考虑过的替代方案：让 LLM 自行判断行动合理性。被否决——LLM 天然倾向激进建议以显得"有帮助"。
- 状态：生效中

### Counter Signal 板块
- 决定：每天扫描与主流叙事相反的证据，最多输出 1 条可信 Counter Signal。
- 原因：AI 媒体生态存在结构性乐观偏见（融资/发布天然被放大，失败/质疑天然被淡化）。日报需要对冲视角。
- 考虑过的替代方案：不做 Counter Signal。被否决——单一方向叙事会系统性高估行业乐观度。
- 状态：生效中

### Theme Memory 持久化
- 决定：引入 `output/.theme-memory.json`，追踪跨日期主题强度与方向（accelerating/sustained/decelerating/dormant）。
- 原因：每天独立生成日报，Anthropic 融资和 Claude 更新被视为两个孤立事件，无法形成连续性叙事。
- 考虑过的替代方案：不追踪主题。被否决——日报的连续性价值被放弃。
- 状态：生效中

### Alpha 硬上限 2 条，不凑数
- 决定：Alpha 最多 2 条。没有符合判据的 → 空着。只有 1 条 → 不强制填满 2 条。全天 0 条 → 今日判断写"没有改变基础假设的变量"。
- 原因：Alpha 的定义是"改变行业默认假设的事件"，这种事件本来就不该每天都出现。硬凑 2 条会稀释 Alpha 含义。
- 考虑过的替代方案：软上限（"建议 1-2 条"）。被否决——软约束在 LLM 面前等于无约束。
- 状态：生效中
