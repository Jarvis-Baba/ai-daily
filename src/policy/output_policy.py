"""Output rendering policies — the single source of truth for presentation rules.

Pure functions with zero pipeline dependencies. OutputStage delegates all
business-rule decisions to this module.
"""

from __future__ import annotations

from typing import Any

# Canonical buckets → Chinese display labels
AUDIENCE_LABELS: dict[str, str] = {
    "developer": "开发者",
    "builder": "创业者",
    "investor": "投资人",
}

# Keyword hints for mapping free-form audience strings → canonical buckets.
# Checked in order; first match wins. Keys are substrings matched case-insensitively.
_AUDIENCE_KEYWORDS: list[tuple[str, str]] = [
    ("开发", "developer"),
    ("developer", "developer"),
    ("engineer", "developer"),
    ("创业", "builder"),
    ("builder", "builder"),
    ("founder", "builder"),
    ("entrepreneur", "builder"),
    ("startup", "builder"),
    ("投资", "investor"),
    ("investor", "investor"),
    ("vc", "investor"),
    ("capital", "investor"),
]

_PROHIBITED_ACTION_KEYWORDS = (
    "增持",
    "减持",
    "买入",
    "卖出",
    "加仓",
    "减仓",
    "建仓",
    "清仓",
    "仓位",
    "投资标的",
    "创业",
    "转型",
    "换工作",
    "辞职",
    "重构系统",
    "重构架构",
    "架构重构",
    "迁移技术栈",
    "成立团队",
    "成立小组",
    "成立跨部门",
    "restructure",
    "buy ",
    "sell ",
    "increase position",
    "decrease position",
)


def _action_text(action_item: Any) -> str:
    parts: list[str] = []
    for attr in ("trigger_condition", "action", "rationale"):
        value = getattr(action_item, attr, "")
        if value:
            parts.append(str(value))
    actions = getattr(action_item, "actions", None)
    if actions:
        parts.extend(str(action) for action in actions)
    return " ".join(parts).lower()


def should_render_action(action_item: Any) -> bool:
    """Return False for L3 and high-risk overreach actions."""
    level = getattr(action_item, "level", "L2")
    if level == "L3":
        return False
    text = _action_text(action_item)
    return not any(keyword.lower() in text for keyword in _PROHIBITED_ACTION_KEYWORDS)


def normalize_audience(audience: str) -> str:
    """Map a free-form audience string to a canonical bucket."""
    if audience in AUDIENCE_LABELS:
        return audience
    audience_lower = audience.lower()
    for keyword, bucket in _AUDIENCE_KEYWORDS:
        if keyword in audience_lower:
            return bucket
    return "developer"


def safe_value(x: Any) -> str:
    """Return a safe display string. Uses '_None_' for None / '' / []."""
    if x in (None, "", []):
        return "_None_"
    return str(x)
