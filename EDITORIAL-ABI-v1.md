# EDITORIAL-ABI-v1 — Narrative Selection Contract

**Status**: FROZEN v1.0
**Date**: 2026-06-04
**Successor of**: n/a (new layer, extracted from L3 Article Compiler)

---

## §0 为什么需要这个 ABI

L2（Synthesize）负责"什么能成为事件"——从 evidence 中聚合出 event_ledger。
L3（Article Compiler）目前只做渲染，不做编辑抉择。

本 ABI 定义 L3.5——在 event_ledger 和最终文章之间插入的 Narrative Selection 层。
**v1.0 阶段只观测，不丢弃。** 角色分配是确定性的，且所有事件仍然进入文章。

---

## §1 核心对象

```yaml
editorial_selection:
  candidate_events: int        # event_ledger 长度
  selected_events: int         # 分配了叙事角色的事件数
  unassigned_events: int       # 未分配角色但仍保留的事件数
  discarded_events: int        # v1.0 固定为 0，保留供未来版本
  compressed_groups: int       # 被合并的事件组数
  selection_ratio: float       # selected / candidate (v1.0 = 1.0)
```

---

## §2 叙事角色（6 角色体系）

| 角色 | 定义 | 触发条件 | 每篇文章上限 |
|------|------|---------|:--:|
| **Hook** | 开篇锚点——最具冲突/意外/断裂感的事件 | 类型=capability/research_result 且 impact≥8 | 1 |
| **Context** | "为什么今天重要"——解释结构性背景的事件 | 服务于今日最活跃 theme 的事件 | 1 |
| **Pivot** | 结构性变化的具体案例——structural_shift 的触发事件 | 事件 title/source 与 structural_shift.trigger 匹配 | 1 |
| **Amplifier** | 独立来源的验证信号——强化 Pivot 方向 | 不同类型/不同 source 但指向同一 signal_map hypothesis | 1 |
| **Contradiction** | 与主流叙事形成张力的事件 | 事件结论与 Pivot 方向相反或构成约束 | 0-1 |
| **Closer** | 结尾金句素材——具有前瞻/行动导向的事件 | 事件含 forward-looking 或 actionable 信号 | 1 |

**硬规则**：
- 一个事件最多分配一个角色
- 满足同一角色条件的事件超过 1 个时，取第一个匹配的
- 未分配到任何角色的事件标记为 `unassigned`，**v1.0 不丢弃**

---

## §3 角色分配算法（确定性，无 LLM，无权重）

```python
def assign_roles(events, structural_shifts, signal_map, active_themes):
    roles = {}
    assigned_ids = set()

    # Hook: capability/research_result + highest impact 来源事件
    for e in events:
        if e.type in ("capability", "research_result"):
            if source_matches_structural_trigger(e, structural_shifts):
                roles["hook"] = e
                assigned_ids.add(e.title)
                break

    # Context: 服务于第一活跃主题的事件
    top_theme = active_themes[0] if active_themes else None
    if top_theme:
        for e in events:
            if e.title not in assigned_ids and theme_related(e, top_theme):
                roles["context"] = e
                assigned_ids.add(e.title)
                break

    # Pivot: structural_shift 的触发事件
    for shift in structural_shifts:
        for e in events:
            if e.title not in assigned_ids and event_matches_shift(e, shift):
                roles["pivot"] = e
                assigned_ids.add(e.title)
                break
        if "pivot" in roles:
            break

    # Amplifier: 不同类型/不同source，指向同一 signal hypothesis
    pivot_event = roles.get("pivot")
    if pivot_event and signal_map:
        for sig in signal_map:
            for e in events:
                if e.title not in assigned_ids:
                    if e.type != pivot_event.type and e.source != pivot_event.source:
                        if event_in_signal(e, sig):
                            roles["amplifier"] = e
                            assigned_ids.add(e.title)
                            break
            if "amplifier" in roles:
                break

    # Contradiction: 与 pivot 形成张力的 governance/behavioral 事件
    for e in events:
        if e.title not in assigned_ids and e.type in ("governance", "behavioral"):
            if is_contradicting(e, roles.get("pivot"), structural_shifts):
                roles["contradiction"] = e
                assigned_ids.add(e.title)
                break

    # Closer: 含前瞻信号的最后一个未分配事件
    for e in reversed(events):
        if e.title not in assigned_ids and has_forward_looking(e):
            roles["closer"] = e
            assigned_ids.add(e.title)
            break

    # Remaining events → unassigned (kept, not discarded)
    unassigned = [e for e in events if e.title not in assigned_ids]

    return SelectionResult(roles=roles, unassigned=unassigned)
```

---

## §4 Telemetry（每 run 输出）

```json
{
  "editorial_telemetry_version": "1.0",
  "run_date": "2026-06-04",
  "candidate_events": 8,
  "selected_events": 6,
  "unassigned_events": 2,
  "discarded_events": 0,
  "selection_ratio": 1.0,
  "role_assignment": {
    "hook": {"event": "...", "type": "research_result"},
    "context": {"event": "...", "type": "capability"},
    "pivot": {"event": "...", "type": "research_result"},
    "amplifier": {"event": "...", "type": "ecosystem"},
    "contradiction": {"event": "...", "type": "behavioral"},
    "closer": {"event": "...", "type": "governance"}
  },
  "unassigned": [
    {"event": "...", "type": "research_result", "reason": "no_role_match"}
  ]
}
```

累计文件 `editorial_fingerprint.json` 提供跨天聚合：
```json
{
  "days": 5,
  "role_frequency": {
    "hook": {"Anthropic": 4, "OpenAI": 1},
    "pivot": {"anthropic_scaling": 4, "openai_evolution": 1}
  },
  "role_stability": {
    "hook": 0.8,
    "pivot": 0.8,
    "contradiction": 0.2
  },
  "discard_candidates": [
    {"event_type": "research_result", "count": 12, "avg_relevance": "low"}
  ]
}
```

---

## §5 版本演进路线

| 版本 | 状态 | 行为 |
|------|------|------|
| v1.0 | **FROZEN** | 角色标注 + 全量保留 + Telemetry |
| v1.1 | PLANNED | 基于 Telemetry 加入确定性 relevance scorer |
| v2.0 | PLANNED | 启用 Narrative Discard（阈值由 fingerprint 反推） |

---

## §6 与其他 ABI 的关系

```
EVIDENCE-ABI-v1    → 定义 Evidence/Package 结构
ONTOLOGY-v2        → 定义 6-type 事件分类
L2-CONVERGENCE-SPEC → 定义冲突 convergence 规则
EDITORIAL-ABI-v1   → 定义叙事选择规则（本文档）

EDITORIAL-ABI-v1 不修改上述任何文档的行为。
它只消费 event_ledger，在 L2 输出和 L3 渲染之间插入 Narrative Selection 层。
```
