# 项目指令 (PROJECT.md)
> 项目规则层。不变的东西放这里。
> 其他 agent 接手：先读本文件对齐规则，再读 STATE.md 从断点继续。

## 0. 项目原则

Memory is cache.
Files are source of truth.

任何影响项目连续性的内容，必须落盘到文件。
禁止依赖 Agent 会话记忆。

下面所有结构都是这条原则的产物。

## 1. 项目目标
AI 早报生成器。多源抓取 → LLM 筛选评分 → LLM 结构化合成为 6 板块可行动决策简报。

## 2. 范围与边界
做:
- RSS/Sitemap/GitHub Releases 多源抓取
- 两轮评分 + Impact/Novelty/Actionability 加权加法模型
- Alpha/Beta/Gamma 分桶
- Theme Memory 持久化（跨日主题追踪）
- Counter Signal 检测（与主流叙事对冲）
- Action Framework L1/L2/L3（分级行动建议）
- Content IR 结构化输出（供 Visual Compiler 消费）
- 6 板块 Markdown 简报渲染

不做:
- 中文源自动抓取（受限于反爬）
- 实时通知/推送
- 投资建议（L3 硬阻断）
- 人工验证闭环（当前阶段接受不完美）

## 3. 核心概念与 Schema
- **Alpha**：改变至少一项行业默认假设的事件（Impact≥8, Novelty≥7）
- **Beta**：值得关注但不改变基础假设（总分≥5.0）
- **Gamma**：丢弃（近 Beta 的 Gamma 保留 1 天缓冲）
- **Theme Memory**：项目根 `.theme-memory.json`（gitignored），追踪跨日期主题强度与方向
- **Counter Signal**：与当日主流叙事方向相反的事件/观点
- **Content IR**：Markdown → 结构化 JSON 的中间表示（供 Visual Compiler 消费）
- **Action Framework**：L1 直接行动 / L2 观察 / L3 禁止输出
- 详细定义见**项目根目录**的 spec 文件：DESIGN.md, CONTENT-IR-SPEC-v1.md, EVIDENCE-ABI-v1.md, ONTOLOGY-v2.md 等（docs/ 目前仅为占位，spec 尚未迁入）

## 4. 管线架构
```
L0 (Source) → L1 (Evidence Compiler) → L2 (Content Compiler) → L3 (Article Compiler)
                                                                    ↑
                                                            EDITORIAL-ABI (L3.5)
```
- L0: RSS/Sitemap/GitHub → Artifacts
- L1: Artifacts → Evidence Packages（EVIDENCE-ABI-v1）
- L2: Evidence → Event Ledger → 评分/分桶/Theme/Counter Signal（v2.1 核心）
- L3: Event Ledger → 6 板块 Markdown 简报
- L3.5: Narrative Selection（EDITORIAL-ABI-v1，v1.0 只观测不丢弃）

## 5. 输出规则 (硬约束)
- 输出格式：`output/morning-{date}.md`
- Alpha 硬上限 2 条，没有符合判据的 → 空着，不凑数
- 今日判断只下"有证据支持"的判断
- L3 行动类型（创业/转型/重构建议）硬阻断
- Content IR 与 Markdown 同步输出

## 6. 工作纪律：落盘 (软约束)
   - 每完成一个最小单元：① 更新 STATE.md (只改当前快照) ② CHANGELOG.md 追加一行
   - 历史不进 STATE，知识不进 STATE
   - 任务结束前 STATE 必须反映真实状态，否则任务不算完成
   - Theme Memory 每次生成后更新
   - **会话纪律（硬约束）**：每次会话结束前 ① commit ② 跑 pytest ③ 同步 STATE.md——三者缺一，会话不算结束

## 7. 文件结构
```
ai-daily/
├── src/           # 管线代码（main/models/config/pipeline/adapters/stages）
├── config.yaml    # RSS源 + LLM配置 + 评分阈值
├── output/        # 早报 Markdown + Content IR JSON + .theme-memory.json
├── docs/          # 设计文档、ABI Spec、Ontology、Pipeline Observability
├── tests/         # pytest
└── run.sh         # 入口脚本
```

## 8. 交接说明
真相以文件为准，不依赖任何 agent 记忆。
接手先读 STATE.md 了解当前阶段和下一步。
本文件极少数需要修改——改规则才动 PROJECT.md，改状态只动 STATE.md。
