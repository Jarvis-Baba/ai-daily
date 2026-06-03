# PIPELINE-OBSERVABILITY — 管线可观测性

**Status**: ACTIVE v1.0
**Date**: 2026-06-03

---

## §0 为什么需要这个文档

系统已进入完整闭环 `L0 → L1 → L2 → Feedback`。在此之前，每次运行我们只盯一个数字（adoption rate）。但 adoption 是管线的最后一个环节——它之前的每一步都在吞信息。

单看 adoption 无法回答：系统在变好，还是信息在被丢掉？

---

## §1 四段 Yield 链

```
Artifact  ──Evidence Yield──→ Evidence  ──Event Yield──→ Event  ──Adoption Yield──→ 被采纳
  (L0)         A→E              (L1)        E→V           (L2)         V→A           (L2→L1)
```

| Yield | 公式 | 含义 | 当前基准 (2026-06-03) |
|-------|------|------|----------------------|
| **Evidence Yield** | evidence / artifacts | L1 从原材料中提取了多少结构化事实 | 199/20 ≈ 10.0x (单篇多 claim) |
| **Event Yield** | events / evidence | L2 将多少 evidence 转化为事件 | 6/199 ≈ 3.0% |
| **Adoption Yield** | adopted / events | 事件中有多少能追溯到原始 evidence 来源 | 4/6 ≈ 66.7% |
| **Domain Adoption** | matched_domains / total_domains | 有多少来源域至少有一条被采纳 | 4/8 = 50.0% |

---

## §2 解读

### Evidence Yield 很高（~10x per artifact）

正常。L1 的职责是从文章中提取多条原子声明。一篇博客产 10 条 claim 是健康的。

### Event Yield 极低（3.0%）

**这是当前的瓶颈段。** 199 条 Evidence 中只有 6 条进了 event_ledger。97% 的 Evidence 在 L2 的语义裁决中被丢弃。

需要回答的核心问题：
- 丢掉的 193 条是噪声（低质 claim）还是信号（被 ontology 拒之门外）？
- 如果是信号 → ontology 或 prompt 需要调整
- 如果是噪声 → L1 提取的 quality threshold 需要提高

### Adoption Yield 66.7%

在进了 event_ledger 的 6 条中，4 条能追溯到 evidence 来源。剩余 2 条的事件来自 RSS feed 而非 evidence（例如 Hacker News 的第三方 URL）。这个数字反映了 source matching 的有效性。

---

## §3 Event Compiler 稳定性

Event Compiler（L2 从 Evidence 生成 event_ledger 的过程）是否稳定？

`scripts/event-replay.py` — 同一批 Evidence (353 items, 8 domains)，Ontology v2，三组 temperature：

| Temperature | Event Count | Type Distribution | Domain Adoption |
|-------------|-------------|-------------------|-----------------|
| 0.0 | 5 | behavioral, capability, research_result, governance, ecosystem | 37.5% |
| 0.3 | 5 | behavioral, capability, research_result, governance, capital | 37.5% |
| 0.7 | 5 | behavioral, capability, research_result, governance, capital | 37.5% |

**判定：STABLE (spread=0)**。Event Compiler 在不同 temperature 下产出数量一致。

但：
- **Event Yield = 1.4%** (5/353) — 98.6% 的 Evidence 在 L2 被丢弃。这是当前系统的核心瓶颈。
- **Type stability = 4/6** (66.7%) — behavioral, capability, research_result, governance 跨温度稳定；capital 和 ecosystem 不稳定。
- ecosystem 仅在 t=0.0 出现，capital 仅在 t≥0.3 出现。这两个类型是 noise-level。

**结论**：Event Compiler 本身稳定，但 Event Yield 极低。瓶颈不在 Compiler 的随机性，在于 Evidence→Event 的语义映射效率。

---

## §4 每日追踪模板

```
YYYY-MM-DD
  L0 artifacts: N
  L1 evidence:  N  | Evidence Yield: X%
  L2 events:    N  | Event Yield:    Y%
     adopted:    N  | Adoption Yield: Z%
  domains:      matched/N (X%)
  type_dist:    {capital:X, capability:Y, ...}
  notes:        [任何异常]
```

---

## §5 红线

| 指标 | 红线 | 含义 |
|------|------|------|
| Evidence Yield | < 1.0 per artifact | L1 提取能力退化 |
| Event Yield | < 2.0% | L2 几乎在拒绝所有 Evidence，检查 ontology 匹配 |
| Event Yield | > 30% | 可能过度提取，检查是否在制造伪事件 |
| Adoption Yield | < 30% | source matching 失效或事件全来自 RSS |
| Event Count Variance | > 3 | Event Compiler 不稳定，冻结所有下游决策 |

---

## §6 与 ABI 晋升的关系

当以下条件连续 7 天满足时，Event Ontology 可进入 ABI 候选讨论：

1. Event Yield 稳定在 3%–30% 区间
2. Event Compiler 稳定性判定为 "stable"（spread ≤ 1）
3. Per-type precision（见 ontology_telemetry.json）中 ≥2 个类型的 precision > 0.3
4. 无 ontology inflation 迹象（连续 7 天无新类型增加）

在此之前，Ontology v2 保持 ACTIVE 但不冻结。
