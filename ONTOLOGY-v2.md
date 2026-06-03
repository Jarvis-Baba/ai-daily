# ONTOLOGY-v2 — Event Ledger 分类体系

**Status**: ACTIVE v2.0
**Date**: 2026-06-03
**Supersedes**: v1.0 (capital/capability/behavioral only)

---

## §0 升级理由

v1 ontology `{capital, capability, behavioral}` 在 36-evidence 生产运行中表现为 0% adoption rate。根本原因：sources 产出的 claim 类型空间与 event_ledger 类型空间的交集 ≈ 0。

v1 的三分类覆盖了"资本市场事件 + 产品发布事件 + 用户行为事件"，但 sources 实际产出的是：

```
announcement     → 产品公告、功能更新
research claim   → 论文声明、基准数据
observation      → 技术观察、模式识别
benchmark result → 性能评测
policy statement → 政策/安全/合规声明
```

v2 从 3 类扩展到 6 类，使 event_ledger 能吸收 sources 的实际信息结构。

---

## §1 六类事件定义

| type | 中文名 | 定义 | 典型来源 |
|------|--------|------|---------|
| `capital` | 资本事件 | 融资/估值/投资/收购/IPO | SEC filings, TechCrunch, 官方公告 |
| `capability` | 能力事件 | 产品发布/模型发布/新功能上线/版本升级 | 官方博客, GitHub Release |
| `behavioral` | 行为事件 | 用户/开发者行为变化、采用率迁移、市场偏好转移 | 调查报告, 平台数据披露 |
| `research_result` | 研究声明 | 论文核心声明/基准测试结果/性能数据/消融实验 | arXiv, 论文博客, 技术报告 |
| `governance` | 治理事件 | 安全事件/漏洞披露/政策变更/合规动作/开源许可变更 | 安全公告, 监管文件, 官方政策页 |
| `ecosystem` | 生态事件 | 合作伙伴关系/平台战略调整/行业标准制定/联盟成立 | 合作公告, 行业联盟声明 |

---

## §2 Soft-Mapping 规则

当 Evidence 的 claim 类型不完全匹配上述六类时，LLM 应将其映射到最接近的类型，而非丢弃。

```
优先级（同级内按语义距离选择）：
  announcement → capability（如果是产品）或 governance（如果是政策）
  benchmark   → research_result
  observation → behavioral（如果是行为模式）或 research_result（如果是技术发现）
  policy      → governance
  partnership → ecosystem
  security    → governance
```

**反规则**：不得因"不完全匹配"而将 Evidence 排除在 event_ledger 之外。soft-mapping 的目的是最大化 adoption rate，使 calibration 能产生有意义的差异化信号。

---

## §3 与 v1 的兼容性

- v1 的 `capital`, `capability`, `behavioral` 定义不变
- 新类型 `research_result`, `governance`, `ecosystem` 为增量
- `EventLedgerItem.type` 字段类型仍为 `str`（无代码级破坏性变更）
- 已有 EventLedgerItem 实例向后兼容

---

## §4 A/B 实验结果 (2026-06-03)

同一批 Evidence (353 items, 8 domains) 重放：

| Metric | V1 (3 types) | V2 (6 types) | Delta |
|--------|-------------|-------------|-------|
| Domain adoption | 12.5% (1/8) | 50.0% (4/8) | **+37.5%** |
| Event types generated | capital ×1, capability ×2, behavioral ×2 | capability ×3, governance ×1, research_result ×1 | 新类型直接启用 |
| Domains matched | github.blog only | arxiv.org, github.blog, openai.com, anthropic.com | 3 个新 domain 解锁 |

**关键发现**：
- `research_result` 类型解锁了 arxiv.org 的论文声明
- `governance` 类型解锁了安全/政策类事件
- Domain adoption 从 12.5% → 50%，提升 3x，全部来自 ontology 扩张

**Calibration 状态**：冻结（`_CALIBRATION_WEIGHT=0.0`）。在 ontology 稳定前不做 reliability 学习。

---

## §5 预期效果

- **adoption rate**: 从 ~0% 提升至 >10%（至少部分 research_result 和 governance 类型 evidence 可被采纳）
- **calibration 分化**: 不同 domain 因产出的事件类型分布不同，开始出现差异化的 reliability score
- **语义投影损失**: 从 ~100%（全拒绝）降至 <90%（部分吸收）
