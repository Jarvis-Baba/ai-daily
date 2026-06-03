# L2-CONVERGENCE-SPEC — Content Compiler 认知收敛规则

**Status**: DRAFT v0.1
**Date**: 2026-06-03
**Layer**: L2 (Content Compiler)
**Depends on**: EVIDENCE-ABI v1.0 §5 (冲突保留)
**Relation**: 本规则定义 L2 在收到含冲突 Evidence 的 Package 时，合法输出空间是什么

---

## §0 问题定义

EVIDENCE-ABI §5 规定：Evidence Layer 保留冲突，裁决发生在 L2。但 L2 的裁决规则从未被定义。

这意味着：**同一个 Evidence Package，如果包含 disputed Evidence，两次独立的 L2 调用可能产生不同结论。** 这是 epistemic convergence 缺口——不是字段缺失，是行为未约束。

本规则定义 L2 在此场景下的合法行为空间。

---

## §1 L2 的输入

L2 接收 Evidence Package。Package 中每条 Evidence 有：

- `statement`：事实声明
- `fact_type`：source_statement | verifiable_fact
- `confidence`：source_reliability + evidence_strength + verification_status
- `media_refs`：可选

L2 不接收：IR 中的 executive_judgment、signal_map、structural_shifts、decision_hooks。这些字段已被架构切分移除。

---

## §2 三种合法行为（Convergence Modes）

当 L2 遇到 Package 中存在 verification_status=disputed 的 Evidence，或存在对同一事实的不同声明时，必须从以下三种行为中选择一种：

### Mode A：ABSTAIN（不输出结论）

```
行为：在该事实上不给出任何结论性陈述。只报告"存在争议"。

输出格式：
  "关于 [topic]，目前存在不同说法。[Source A] 声称 X，而 [Source B] 声称 Y。尚无足够证据判定。"

适用条件：
  - 冲突双方 confidence 接近（source_reliability 差距 < 0.3）
  - 且 evidence_strength 均 < 0.7
  - 且无 cross_referenced 来源可打破僵局

风险：文章可能显得"不确定"，削弱说服力
收益：最大程度保留诚实性，避免传播未确认信息
```

### Mode B：HEDGE（多假设呈现）

```
行为：输出多个可能结论，标注各自的支撑强度。

输出格式：
  "目前有两种主要观点：
   1. [结论A]（支撑：Anthropic 官方数据，cross_referenced by 36氪、GIGAZINE）
   2. [结论B]（支撑：独立基准测试，单一来源，未交叉验证）
   目前更多证据倾向于 A，但 B 尚未被排除。"

适用条件：
  - 某一方在 confidence 上明显占优（source_reliability 差距 ≥ 0.3）
  - 但占优方的 evidence_strength < 0.9（不是压倒性证据）

风险：读者可能只记住一个结论，忽略"多假设"限定
收益：给出方向性判断的同时保留知识诚实
```

### Mode C：WEIGHTED SYNTHESIS（加权合成）

```
行为：基于 confidence 三维度加权，输出单一结论。

输出格式：
  "[结论]。这一判断基于 [N] 个来源的交叉验证，其中最权威的来源为 [Source]，其 verification_status 为 cross_referenced。"

适用条件：
  - 一方在三个 confidence 维度上均明显占优
  - 且占优方的 evidence_strength ≥ 0.8 且 verification_status = cross_referenced
  - 且非占优方的 source_reliability < 0.6（低可信来源）

附加要求：
  - 必须在文章中标注"此结论基于当前可获得的最佳证据，可能随新证据更新"
  - 必须至少引用一条非占优方的 Evidence（不能选择性忽略反方）

风险：如果 confidence 评分有偏，结论会继承偏差
收益：给出明确结论，适合需要 actionable insight 的文章类型
```

---

## §3 模式选择规则

L2 的 Convergence Mode 不是自由选择。它由冲突的**置信度差距**决定：

```
差距 = |source_A.confidence加权 - source_B.confidence加权|

confidence加权 = 0.4 × source_reliability
               + 0.3 × evidence_strength
               + 0.3 × verification_status_score

verification_status_score:
  cross_referenced = 0.9
  direct_source     = 0.7
  unverified        = 0.3
  disputed          = 0.1
```

| 差距范围 | 合法 Mode | 典型场景 |
|---------|----------|---------|
| < 0.15 | ABSTAIN 或 HEDGE | 两个高质量来源给出不同数字 |
| 0.15 – 0.35 | HEDGE | 官方数据 vs 独立测试 |
| > 0.35 | WEIGHTED SYNTHESIS | 一手来源 vs 小型博客 |

**当差距正好在阈值边界（±0.05）时，默认向更保守的模式回落。** 例如差距 0.14 → ABSTAIN，而非 HEDGE。

---

## §4 硬约束

### 必须做的事

1. **每个收敛决策必须可追溯**：文章中可以没有引用标记，但 L2 的内部决策日志必须记录"此结论基于 E-001 到 E-005，其中 E-003 因 SR=0.55 被降权"
2. **必须提及反方存在**：任何 Mode 下，如果存在 disputed 或冲突的 source_statement，文章必须至少提及"有其他来源给出了不同说法"
3. **confidence 来源必须在文章中可感知**："Anthropic 官方宣布" vs "据某科技博客报道"——读者不需知道 SR 数值，但需知道来源类型

### 禁止做的事

1. ❌ 忽略冲突方，只报道有利方（选择性引用）
2. ❌ 将 source_statement 伪装成 verifiable_fact（去掉 attribution）
3. ❌ 在 ABSTAIN 模式下使用确定语气（"显然""毫无疑问"）
4. ❌ 手动 override confidence 评分来改变 Mode 选择（想用 Mode C 就调高 SR——这是数据污染）

---

## §5 与文章类型的绑定

不同文章类型对不确定性的容忍度不同：

| 文章类型 | 默认 Mode | 可降级到 |
|---------|----------|---------|
| AI 日报 (fast) | HEDGE | ABSTAIN（不确定时不硬给结论） |
| 深度分析 (deep) | WEIGHTED SYNTHESIS | HEDGE（需要明确观点但保留余地） |
| 研究报告 | HEDGE | ABSTAIN（严谨性优先于可读性） |
| 公众号推文 | WEIGHTED SYNTHESIS | HEDGE（读者期望明确结论） |

文章类型由 Phase 0 的 Direction 字段确定。

---

## §6 一个具体示例

```
输入：Evidence Package #001 中的 D-002

E-007: "16% eval awareness in destructive coding tests"
  SR=0.85, ES=0.65, VS=cross_referenced
  confidence加权 = 0.4×0.85 + 0.3×0.65 + 0.3×0.9 = 0.805

E-020: "14% of hidden behaviors surfaced"
  SR=0.55, ES=0.40, VS=unverified
  confidence加权 = 0.4×0.55 + 0.3×0.40 + 0.3×0.3 = 0.430

差距 = 0.805 - 0.430 = 0.375 → > 0.35

→ Mode: WEIGHTED SYNTHESIS
→ 输出: "在破坏性编码测试中，NLA 检测到了 16% 的评估意识（Anthropic 官方数据，已被多家科技媒体交叉确认）。
         另有报道提到 14% 的隐藏行为检出率，但该数字的统计口径与 16% 可能不同，且仅来自单一来源。"
→ 偏差标注: 已内联标注。被压缩方（E-020, SR=0.55）置信度远低于保留方，压缩风险可控。
→ 标注级别: INLINE
```

---

## §8 压缩披露规则（Compression Disclosure Rules）

SYNTHESIS 是唯一允许选择性丢失信息的 Mode。当 L2 将多个冲突声明压缩为单一叙述时，必须标注：**哪些信息被压缩了，为什么。**

### 三级披露强度

| 级别 | 标注方式 | 触发条件 | 示例 |
|------|---------|---------|------|
| **INLINE** | 同一段落内标注。使用"另有[X]报道称[Y]，但该来源[可信度说明]"句式。 | 被压缩方 confidence加权 < 保留方 60%，或被压缩方 SR < 0.6 | "Anthropic 报告 FVE 为 0.6-0.8，另有独立评测给出了不同的数值，但该评测尚未被其他来源交叉确认。" |
| **CALLOUT** | 独立段落，位于得出结论的段落后。标题使用"⚠️ 需要注意的分歧"或"关于此结论的不确定性"。 | 被压缩方 confidence加权 ≥ 保留方 60%，或被压缩方包含 cross_referenced 来源 | "**关于此结论的不确定性**：一家独立基准测试机构给出了较低的评估数值。该机构的历史可信度评级为中等，目前尚无其他来源复现其结果。我们选择了官方数据作为主要引用，但读者应注意这一分歧尚未解决。" |
| **SECTION** | 文章末尾独立"局限与不确定性"小节。列出所有被压缩的冲突及压缩理由。 | 一次 SYNTHESIS 操作压缩了 ≥3 条 confidence加权 > 保留方 50% 的冲突 Evidence | 见 §8.1 示例 |

### 分级决策表

```
被压缩方的最高 confidence加权 / 保留方的 confidence加权

< 0.5   → INLINE 或可省略（被压缩方远不可靠）
0.5–0.7 → INLINE（必须标注）
0.7–0.85 → CALLOUT（必须显著标注，独立段落）
> 0.85 → 不应使用 SYNTHESIS，回落至 HEDGE
```

### 禁止行为

1. ❌ **Silent compression**：使用 SYNTHESIS 但不在任何位置标注冲突方存在
2. ❌ **Asymmetric labeling**：对被压缩方使用"据称""有人声称"模糊修辞，而对保留方使用"事实是""数据显示"确定修辞——这种不对称本身就是偏差
3. ❌ **Invisible weighting**：confidence 加权决定了选择，但文章未让读者感知到选择的存在。读者不需要知道公式，但需要知道"这个结论是如何做出的"

### 设计理由

SYNTHESIS = 信息压缩 + 选择性丢失。所有系统性偏差最终都从压缩操作中产生。

本规则不禁止压缩——没有压缩就没有可读的叙述。但它要求压缩操作是**可追溯的**：一个读者看完文章后，应该能够感知到：（1）存在被压缩的信息，（2）压缩的理由，（3）被压缩的信息可能改变结论的程度。

这是"高质量总结器"和"可审计认知系统"的分界线。

### §8.1 SECTION 级披露示例

```
## ⚠️ 局限与不确定性

本文中以下结论基于加权综合判断，而非单一来源：

1. "NLA 的审计效率提升为 4-5 倍"
   - 保留：Anthropic 官方数据（<3% → 12-15%），cross_referenced by 36氪、GIGAZINE
   - 压缩：Quantum Zeitgeist 的 "14%" 数字（单一来源，SR=0.55，与官方统计口径可能不同）
   - 理由：14% 与 16% 可能指不同指标；三来源交叉确认了 12-15% 的范围

2. [其他被压缩的冲突...]
```

本规则当前为 DRAFT v0.1。冻结条件：

- 至少 3 次 L2 运行中实际遇到了需要 Mode 选择的场景
- 其中至少 1 次触发了 SYNTHESIS + CALLOUT 或更高级别的披露
- epistemic convergence 的触发条件被满足（见 PROMOTION-RULES §11）

**未冻结前**：L2 按本规则的 §3 模式选择表和 §8 披露规则执行。如果遇到表中未覆盖的情况，默认回落到 ABSTAIN。

v0.2 变更：新增 §8 压缩披露规则（INLINE / CALLOUT / SECTION 三级标注）。

---

*本规则是 PROMOTION RULES §11 中 "epistemic convergence" 缺口的实现方案。它不定义新 Schema——它定义 L2 在不确定性存在时，是否以及如何"发言"。*
