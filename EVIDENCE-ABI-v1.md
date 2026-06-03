# EVIDENCE-ABI-v1 — Evidence Layer Contract

**Status**: FROZEN v1.0
**Date**: 2026-06-03
**Layer**: L1 (Evidence Compiler)
**Depends on**: Source Compiler (L0)
**Consumed by**: Content Compiler (L2), Visual Compiler (L3)

---

## §0 定义

**Evidence Package = 可验证事实集合（Verifiable Facts Bundle）**

它不是文章素材包，不是新闻摘要，不是分析报告。它是一个独立于消费场景的事实载体。

任何 Compiler（Content / Visual / Research / Future Agent）都可以消费。

---

## §1 三层对象分离

```
Artifact（原材料）
  原始网页、PDF、截图、转录文本
  职责：保存来源的完整可验证副本
  禁止：提取、总结、判断

Evidence（结构化事实）
  来源陈述、可验证事实、引用片段、可信度元数据
  职责：把原材料中的事实声明结构化
  禁止：分析、预测、战略建议、重要性排序

Narrative（内容产品）
  分析、推理、战略判断、影响预测
  职责：基于 Evidence 做出解释和判断
  禁止：伪造 Evidence 不支持的结论
```

**硬边界**：每一层不得包含下一层的语义。Artifact 不含 Claim，Evidence 不含 Analysis。

---

## §2 Artifact 对象

```yaml
artifact_id: "A-20260603-001"
artifact_type: research_paper | blog_post | news_article | tweet | video_transcript | github_commit | screenshot | pdf
source_url: "https://..."
retrieved_at: "2026-06-03T07:00:00Z"
content_hash: "sha256:abc123..."      # 内容版本锁定
raw_content: "..."                      # 原文/摘要
screenshot_refs: ["S-001"]             # 关联截图
```

### 必填字段

`artifact_id`, `artifact_type`, `source_url`, `retrieved_at`, `content_hash`

### content_hash 的设计理由

来源内容可能被修改（博客更新、推文删除、网页改版）。没有 Hash，无法追溯 Evidence 引用的是哪个版本。

---

## §3 Evidence 对象

```yaml
evidence_id: "E-20260603-001"
fact_type: source_statement | verifiable_fact

source:
  name: "Anthropic Research"
  type: official_blog | research_paper | news_media | social_media | corporate_filing | independent_report | unknown
  url: "https://..."
  published_at: "2026-06-03"

statement: "NLA 将模型隐层状态无损解码为自然语言"

attribution: "Anthropic Research"       # 谁说的。可以与 source.name 不同（例如第三方转述）

supporting_material:
  quote: "NLA decodes latent states..." # 原文引用
  screenshot_refs: ["S-001"]           # 引用截图
  artifact_refs: ["A-20260603-001"]    # 引用 Artifact
  media_refs: []                       # 引用媒体资源（image/gif/video），可选。为未来 MEDIA-ABI 预留接口

confidence:
  source_reliability: 0.95             # 来源本身的可信度
  evidence_strength: 0.80              # 这条具体声明的强度
  verification_status: direct_source   # direct_source | cross_referenced | unverified | disputed
```

### 必填字段

`evidence_id`, `fact_type`, `source` (含 `name`, `type`, `url`, `published_at`), `statement`, `attribution`, `confidence` (含 `source_reliability`, `evidence_strength`, `verification_status`)

### fact_type 枚举

| 值 | 含义 | 例 |
|----|------|-----|
| `source_statement` | 来源的主张，可能真可能假 | "Anthropic 声称 NLA 效果提升 40%" |
| `verifiable_fact` | 客观可验证的事件 | "OpenAI 于 2026-06-02 发布 Codex 插件" |

### verification_status 枚举

| 值 | 含义 |
|----|------|
| `direct_source` | 从一手来源直接获取并验证 |
| `cross_referenced` | 多个独立来源交叉确认 |
| `unverified` | 单一来源，尚未交叉验证 |
| `disputed` | 不同来源给出冲突信息 |

### 禁止字段

`analysis`, `importance`, `industry_impact`, `opinion`, `takeaway`, `prediction`, `recommendation`

---

## §4 Evidence Package 容器

```yaml
package_id: "PKG-20260603-001"
topic: "Anthropic NLA 论文发布"
generated_at: "2026-06-03T07:30:00Z"
artifacts:
  - A-20260603-001
  - A-20260603-002
evidence:
  - E-20260603-001
  - E-20260603-002
  - E-20260603-003
```

Package 只做索引。不做语义加工。

---

## §5 冲突处理规则

Evidence Layer 不裁决冲突。如果两个来源给出矛盾信息，两份 Evidence 同时保留。

```yaml
E-005:
  statement: "NLA 效果提升 40%"
  source:
    name: "Anthropic Research"
  confidence:
    verification_status: unverified

E-006:
  statement: "NLA 效果提升 8%"
  source:
    name: "Independent Benchmark"
  confidence:
    verification_status: cross_referenced
```

裁决发生在 Content Compiler（L2）。Evidence Compiler 的职责是忠实记录，不是判断真伪。

---

## §6 可信度模型

Confidence 不是人工拍脑袋的单点数字。每个 Evidence 的 `confidence` 由三个独立维度构成：

| 维度 | 含义 | 取值范围 |
|------|------|---------|
| `source_reliability` | 来源类型的历史可信度 | 0.0–1.0 |
| `evidence_strength` | 这条具体声明的可验证程度 | 0.0–1.0 |
| `verification_status` | 当前已验证状态 | 枚举值 |

### 典型组合

| 场景 | source_reliability | evidence_strength | verification_status |
|------|-------------------|-------------------|---------------------|
| OpenAI 官方博客的发布公告 | 0.95 | 0.90 | direct_source |
| 论文作者声称的性能数据 | 0.85 | 0.60 | unverified |
| 第三方媒体的转述 | 0.65 | 0.50 | unverified |
| 社交媒体爆料 | 0.35 | 0.30 | unverified |
| 多来源交叉确认的事件 | 0.90 | 0.90 | cross_referenced |
| 两个来源冲突 | (各自保持) | (各自保持) | disputed |

---

## §7 从 AI 日报 IR 到 Evidence Package

当前 AI 日报 IR 是 L0.5+L2 混合体。迁移路径：

```
当前 IR:
  events[].title          → Evidence.statement
  events[].source         → Evidence.source.name
  [缺失]                  → Evidence.source.url
  [缺失]                  → Artifact (source_url + content_hash)
  structural_shifts[].mechanism  → 拆成多个 Evidence（一个 Claim 一个对象）
  structural_shifts[].consequence → 移到 L2 Content
  executive_judgment      → 移到 L2 Content
  signal_map              → 移到 L2 Content
  decision_hooks          → 移到 L2 Content
```

### 一个 IR 事件的拆解示例

**IR 原条目**（一条 mechanism 混了 3 个 Claim + 1 个分析）：

> "NLA将模型隐层状态无损解码为自然语言，使内部推理过程可读、可审计、可干预，从分析转向编辑"

**拆成 Evidence**：

```
E-001: fact_type=verifiable_fact
       statement="Anthropic 发布 NLA 论文"
       verification_status=direct_source

E-002: fact_type=source_statement
       statement="NLA 将隐层状态解码为自然语言"
       verification_status=unverified

E-003: fact_type=source_statement
       statement="NLA 使内部推理可读可审计可干预"
       verification_status=unverified
```

"从分析转向编辑" → 属于判断，不进 Evidence，留给 L2 Content。

---

## §8 版本兼容性

- 新增 `fact_type` 枚举值：向后兼容（旧 Consumer 忽略未知类型）
- 新增 `verification_status` 枚举值：向后兼容
- 新增 Evidence 可选字段：向后兼容
- 删除或重命名必填字段：需升 v2
- 修改三层边界定义（例如允许 Evidence 含 Analysis）：需升 v2

---

## §9 与 Visual Compiler 的接口

Visual Compiler (L3) 消费 Evidence 的 `screenshot_refs` 和 `supporting_material.quote`。

```yaml
# Visual ABI v1 中的证据追溯
visual:
  visual_type: data_card
  evidence_refs: ["E-001", "E-002"]    # 图片可追溯到 Evidence
  source_quote: "NLA decodes latent states..."
```

每张图片必须能追溯到至少一条 Evidence。不能从空气里生成视觉内容。

---

## §10 冻结声明

本文档定义 Evidence ABI v1.0。所有修改需经过 ABI 版本评审。L1 Evidence Compiler 的任何实现必须遵守 §2–§6 的对象约束和字段必填规则。

**下一评审窗口**: 至少 3 个 Evidence Package 在生产链路中验证后。
