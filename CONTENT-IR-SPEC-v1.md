# Content IR Specification v1.0

**Content Intermediate Representation — bridge between AI日报 and Visual Compiler**

## 1. Purpose

Content IR is a structured JSON format that sits between the AI Daily News pipeline and the Visual Compiler. It extracts the semantic structure from a daily report (currently Markdown) into a machine-readable format that the Visual Compiler can consume as a Visual Plan.

## 2. Design Principle

Content IR captures **what the content means**, not how it looks. The Visual Compiler owns all layout decisions. Content IR only provides the structured data — section types, semantic roles, text content — leaving template selection, color, typography, and spacing to the V-Kernel.

## 3. Schema

```json
{
  "content_ir_version": "1.0",
  "pipeline": "ai-daily",
  "date": "2026-05-31",
  "generated_at": "2026-05-31T17:14:11",
  "source_file": "output/morning-2026-05-31.md",

  "executive_judgment": {
    "text": "一句话判断",
    "active_themes": ["theme_key", "..."]
  },

  "structural_shifts": [
    {
      "title": "变化标题",
      "mechanism": "机制描述",
      "trigger": "触发事件",
      "consequence": "后果推演",
      "impact": "high",
      "time_horizon": "medium",
      "source": "来源标签"
    }
  ],

  "events": {
    "capability": [
      {"title": "事件描述", "source": "来源"}
    ],
    "behavioral": [
      {"title": "事件描述", "source": "来源"}
    ]
  },

  "signal_map": {
    "synthesis": "跨事件合成标题",
    "causal_chain": "因果链描述",
    "supporting_events": ["事件1", "事件2"]
  },

  "risk_layer": [
    {
      "type": "bubble",
      "horizon": "now",
      "theme": "主题key",
      "description": "风险描述"
    }
  ],

  "decision_hooks": {
    "developer": [
      {
        "trigger": "触发条件",
        "action": "建议动作",
        "rationale": "理由",
        "priority": "L1"
      }
    ],
    "founder": [...],
    "investor": [...]
  },

  "counter_signal": {
    "main_narrative": "主流叙事方向",
    "counter_event": "反向事件标题",
    "tension": "张力描述",
    "why_matters": "为什么值得注意",
    "source": "来源"
  },

  "meta": {
    "source_health": "🟠",
    "api_calls": 15,
    "input_tokens": 20926,
    "output_tokens": 4170
  }
}
```

### 3.1 Field Types

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content_ir_version` | string | Yes | Schema version for ABI tracking |
| `pipeline` | string | Yes | Source pipeline identifier |
| `date` | string | Yes | Report date (YYYY-MM-DD) |
| `generated_at` | string | No | ISO timestamp of generation |
| `source_file` | string | No | Path to source Markdown |
| `executive_judgment` | object | Yes | Top-level daily judgment |
| `structural_shifts` | array | No | 0-3 structural shift analyses |
| `events` | object | No | Categorized event ledger |
| `signal_map` | object | No | Cross-event synthesis |
| `risk_layer` | array | No | 0-5 risk items |
| `decision_hooks` | object | No | Action items by persona |
| `counter_signal` | object | No | Optional counter-narrative signal |
| `meta` | object | No | Generation metadata |

### 3.2 Impact Values

| Value | Meaning |
|-------|---------|
| `high` | Affects ≥30% of target audience decision space |
| `medium` | Affects a specific segment or use case |
| `low` | Niche or speculative impact |

### 3.3 Risk Types

| Value | Meaning |
|-------|---------|
| `bubble` | Valuation/sentiment bubble risk |
| `structural` | Industry structure change risk |
| `regime` | Regulatory or paradigm shift risk |

### 3.4 Time Horizons

| Value | Meaning |
|-------|---------|
| `now` | Active, requires immediate attention |
| `mid` | 1-6 month window |
| `long` | 6+ month window |

## 4. Visual Compiler Mapping

Content IR sections map to Visual Plan images via these rules:

| Content IR Section | Visual Template | Priority | Mapping Logic |
|-------------------|-----------------|----------|---------------|
| `executive_judgment` | INSIGHT_FRAME | primary | `line1` = "今日判断", `line2` = judgment text |
| `structural_shifts[0]` | STRUCTURE_MAP | primary | Each shift → one layer with mechanism/trigger/consequence |
| `signal_map` | FLOW_DIAGRAM | primary | synthesis + causal chain → node chain |
| `risk_layer` | COMPARISON_PANEL | secondary | bubble risks vs structural/regime risks |
| `events` | DATA_CARD | secondary | Top capability + behavioral events as metrics |
| `decision_hooks` | DATA_CARD | secondary | Priority L1 hooks across personas |

### 4.1 Mapping Constraints

1. **Maximum 5 images** per daily report (visual compiler deep mode cap)
2. **INSIGHT_FRAME is mandatory** — every daily report produces at least 1 image (the judgment frame)
3. **STRUCTURE_MAP only if ≥1 structural shift** — empty shifts → skip
4. **FLOW_DIAGRAM only if signal_map.synthesis exists**
5. **If total images > 5**: drop DATA_CARD images first, then COMPARISON_PANEL

## 5. ABI Stability

Content IR v1.0 is the initial schema. Backward-compatible changes (adding optional fields) do not require a version bump. Breaking changes (removing or renaming required fields) require v2.0.

The Content IR version is independent of the Visual ABI version. A Content IR v1.0 document can be compiled by Visual ABI v1.0 or v1.1.

## 6. Extraction Strategy

Content IR is extracted from ai-daily's Markdown output via `content-bridge.py`. The bridge:

1. Parses Markdown section headers to identify the 6-panel structure
2. Extracts structured fields using regex patterns keyed to each section's format
3. Validates required fields are present
4. Outputs Content IR JSON
5. Optionally generates Visual Plan JSON for direct vkernel consumption

**Fallback behavior**: If Markdown parsing fails on a section, that section is omitted (null/empty) rather than producing malformed data. The visual compiler handles missing sections gracefully.

## 7. Evolution Path

Future versions may:
- Extract Content IR directly from the SynthesizeStage output (before Markdown rendering), eliminating the parse step
- Add `theme_memory` section for cross-day continuity
- Add `diff_from_yesterday` for day-over-day structural comparison
- Support multi-day Content IR batches for trend visualization

---

*Version: 1.0 | Date: 2026-06-02 | Status: SPECIFICATION*
