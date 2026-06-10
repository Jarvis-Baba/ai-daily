"""Role Assigner v1.0 — Deterministic narrative role assignment.

Consumes InsightBrief.event_ledger and assigns each event a narrative role
(Hook/Context/Pivot/Amplifier/Contradiction/Closer) or marks it unassigned.

v1.0: OBSERVATION ONLY. All events are retained. No discard.
Telemetry is written for cross-day editorial fingerprinting.

Part of EDITORIAL-ABI-v1.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from src.models.article import EventLedgerItem, StructuralShift, SignalMapItem

logger = logging.getLogger(__name__)

# ── Role definitions ──
ROLE_DEFINITIONS = {
    "hook": "开篇锚点——最具冲突/意外/断裂感的事件",
    "context": "为什么今天重要——解释结构性背景的事件",
    "pivot": "结构性变化的具体案例——structural_shift的触发事件",
    "amplifier": "独立来源的验证信号——强化Pivot方向的事件",
    "contradiction": "与主流叙事形成张力的事件",
    "closer": "结尾金句素材——具有前瞻/行动导向的事件",
}

# Event types that are natural Hook candidates
HOOK_TYPES = {"capability", "research_result"}

# Event types that are natural Contradiction candidates
CONTRADICTION_TYPES = {"governance", "behavioral"}

# Keywords indicating forward-looking / actionable quality (for Closer)
FORWARD_LOOKING_KEYWORDS = [
    "将", "未来", "预计", "趋势", "转向", "改变", "重塑",
    "新", "发布", "推出", "开源", "上线", "启动",
    "will", "launch", "release", "announce",
]

# Keywords indicating contradiction / tension with positive narratives
CONTRADICTION_KEYWORDS = [
    "漏洞", "攻击", "泄露", "失败", "下降", "损失", "滥用",
    "风险", "警告", "限制", "禁止", "调查", "违规",
    "hack", "breach", "vulnerability", "attack", "fail",
    "risk", "warning", "ban", "restrict",
]


@dataclass
class SelectionResult:
    """Output of role assignment. v1.0: all events retained."""

    roles: dict[str, EventLedgerItem]  # role_name → event
    unassigned: list[EventLedgerItem]
    date_str: str = ""

    @property
    def candidate_count(self) -> int:
        return len(self.roles) + len(self.unassigned)

    @property
    def selected_count(self) -> int:
        return len(self.roles)

    @property
    def selection_ratio(self) -> float:
        return 1.0  # v1.0: no discard

    @property
    def has_contradiction(self) -> bool:
        return "contradiction" in self.roles


# ── Matching helpers ──

def _text_overlap(a: str, b: str) -> float:
    """Jaccard overlap on character bigrams (robust to word order)."""
    if not a or not b:
        return 0.0
    a_bigrams = {a[i:i + 2] for i in range(len(a) - 1)}
    b_bigrams = {b[i:i + 2] for i in range(len(b) - 1)}
    if not a_bigrams or not b_bigrams:
        return 0.0
    return len(a_bigrams & b_bigrams) / len(a_bigrams | b_bigrams)


def _source_matches_structural_trigger(
    event: EventLedgerItem, shifts: list[StructuralShift]
) -> bool:
    """Check if event's source or title matches any structural_shift trigger."""
    for shift in shifts:
        trigger = (shift.trigger or "").lower()
        title = (event.title or "").lower()
        source = (event.source or "").lower()
        if not trigger:
            continue
        # Title-level match
        if _text_overlap(title, trigger) > 0.25:
            return True
        # Source-level match
        if source and source in trigger:
            return True
        # Named entity overlap (Anthropic, OpenAI, etc.)
        trigger_words = set(trigger.split())
        title_words = set(title.split())
        common = trigger_words & title_words
        if len(common) >= 2:
            return True
    return False


def _theme_related(event: EventLedgerItem, theme_id: str) -> bool:
    """Check if event type maps to the given theme."""
    # Theme-to-type soft mapping
    THEME_TYPE_MAP = {
        "anthropic_scaling": {"research_result", "capability"},
        "openai_evolution": {"capability", "ecosystem"},
        "ai_hardware": {"capital", "capability"},
        "agent_stack": {"capability", "behavioral", "research_result"},
        "regulation": {"governance"},
        "opensource_ai": {"ecosystem", "capability"},
    }
    expected_types = THEME_TYPE_MAP.get(theme_id, set())
    return event.type in expected_types


def _event_matches_shift(event: EventLedgerItem, shift: StructuralShift) -> bool:
    """Check if event is the trigger for a structural_shift."""
    trigger = (shift.trigger or "").lower()
    title = (event.title or "").lower()
    source = (event.source or "").lower()
    shift_source = (shift.source or "").lower()

    if not trigger:
        return False

    # Source match (primary)
    if source and shift_source and (source in shift_source or shift_source in source):
        return True

    # Title-trigger overlap
    if _text_overlap(title, trigger) > 0.3:
        return True

    return False


def _event_in_signal(event: EventLedgerItem, signal: SignalMapItem) -> bool:
    """Check if event is listed as a supporting event in the signal."""
    title = event.title or ""
    # Check in supporting_events list
    for se in signal.supporting_events:
        if _text_overlap(title, se) > 0.3:
            return True
    # Check in hypothesis/mechanism
    combined = f"{signal.hypothesis} {signal.mechanism}".lower()
    if title.lower()[:20] in combined:
        return True
    return False


def _is_contradicting(
    event: EventLedgerItem,
    pivot: Optional[EventLedgerItem],
    shifts: list[StructuralShift],
) -> bool:
    """Check if event creates tension with the pivot or main narrative."""
    title = (event.title or "").lower()
    stmt = title

    # Keyword signal
    contradiction_score = sum(
        1 for kw in CONTRADICTION_KEYWORDS if kw in stmt
    )
    if contradiction_score >= 2:
        return True

    # Type-based: governance/behavioral events often constrain capability claims
    if event.type in CONTRADICTION_TYPES:
        if pivot and pivot.type in ("capability", "research_result"):
            return True

    return False


def _has_forward_looking(event: EventLedgerItem) -> bool:
    """Check if event has forward-looking or actionable quality."""
    title = (event.title or "").lower()
    return any(kw in title for kw in FORWARD_LOOKING_KEYWORDS)


# ── Main assignment function ──

def assign_roles(
    events: list[EventLedgerItem],
    structural_shifts: list[StructuralShift],
    signal_map: list[SignalMapItem],
    active_themes: Optional[list[str]] = None,
) -> SelectionResult:
    """Assign narrative roles to events. Deterministic, no LLM, no weights.

    v1.0: All events retained. Unassigned events are marked but not discarded.

    Args:
        events: event_ledger from InsightBrief
        structural_shifts: from InsightBrief
        signal_map: from InsightBrief
        active_themes: ranked theme IDs from today_themes

    Returns:
        SelectionResult with role assignments and unassigned list
    """
    if not events:
        return SelectionResult(roles={}, unassigned=[])

    roles: dict[str, EventLedgerItem] = {}
    assigned_titles: set[str] = set()

    # ── Hook: capability/research_result matching a structural trigger ──
    for e in events:
        if e.type in HOOK_TYPES:
            if _source_matches_structural_trigger(e, structural_shifts):
                roles["hook"] = e
                assigned_titles.add(e.title)
                break

    # Fallback Hook: first capability/research_result event
    if "hook" not in roles:
        for e in events:
            if e.type in HOOK_TYPES and e.title not in assigned_titles:
                roles["hook"] = e
                assigned_titles.add(e.title)
                break

    # ── Context: event serving the most active theme ──
    top_theme = active_themes[0] if active_themes else None
    if top_theme:
        for e in events:
            if e.title not in assigned_titles and _theme_related(e, top_theme):
                roles["context"] = e
                assigned_titles.add(e.title)
                break

    # Fallback Context: first event in top theme (any type)
    if "context" not in roles and top_theme:
        for e in events:
            if e.title not in assigned_titles:
                roles["context"] = e
                assigned_titles.add(e.title)
                break

    # ── Pivot: event matching a structural_shift trigger ──
    for shift in structural_shifts:
        for e in events:
            if e.title not in assigned_titles and _event_matches_shift(e, shift):
                roles["pivot"] = e
                assigned_titles.add(e.title)
                break
        if "pivot" in roles:
            break

    # Fallback Pivot: first unassigned event
    if "pivot" not in roles:
        for e in events:
            if e.title not in assigned_titles:
                roles["pivot"] = e
                assigned_titles.add(e.title)
                break

    # ── Amplifier: independent source confirming same signal as Pivot ──
    pivot = roles.get("pivot")
    if pivot and signal_map:
        for sig in signal_map:
            for e in events:
                if e.title not in assigned_titles:
                    if e.type != pivot.type and e.source != pivot.source:
                        if _event_in_signal(e, sig):
                            roles["amplifier"] = e
                            assigned_titles.add(e.title)
                            break
            if "amplifier" in roles:
                break

    # ── Contradiction: governance/behavioral event opposing pivot ──
    for e in events:
        if e.title not in assigned_titles and e.type in CONTRADICTION_TYPES:
            if _is_contradicting(e, pivot, structural_shifts):
                roles["contradiction"] = e
                assigned_titles.add(e.title)
                break

    # ── Closer: forward-looking unassigned event ──
    for e in reversed(events):
        if e.title not in assigned_titles and _has_forward_looking(e):
            roles["closer"] = e
            assigned_titles.add(e.title)
            break

    # Fallback Closer: last unassigned event
    if "closer" not in roles:
        for e in reversed(events):
            if e.title not in assigned_titles:
                roles["closer"] = e
                assigned_titles.add(e.title)
                break

    # ── Unassigned: events that didn't match any role (kept, not discarded) ──
    unassigned = [e for e in events if e.title not in assigned_titles]

    return SelectionResult(roles=roles, unassigned=unassigned)


# ── Telemetry ──

def build_telemetry(result: SelectionResult, run_date: str) -> dict:
    """Build EDITORIAL-ABI-v1 telemetry dict from a SelectionResult."""
    role_assignment = {}
    for role_name, event in result.roles.items():
        role_assignment[role_name] = {
            "event": event.title[:80],
            "type": event.type,
        }

    unassigned_list = []
    for e in result.unassigned:
        unassigned_list.append({
            "event": e.title[:80],
            "type": e.type,
            "reason": "no_role_match",
        })

    return {
        "editorial_telemetry_version": "1.0",
        "run_date": run_date,
        "candidate_events": result.candidate_count,
        "selected_events": result.selected_count,
        "unassigned_events": len(result.unassigned),
        "discarded_events": 0,
        "selection_ratio": result.selection_ratio,
        "role_assignment": role_assignment,
        "unassigned": unassigned_list,
    }


def save_telemetry(telemetry: dict, base_dir: str) -> str:
    """Save per-run telemetry and update cross-day fingerprint."""
    telemetry_dir = Path(base_dir) / "calibration"
    telemetry_dir.mkdir(parents=True, exist_ok=True)

    # Per-run file
    run_date = telemetry["run_date"]
    run_path = telemetry_dir / f"editorial_telemetry_{run_date}.json"
    run_path.write_text(
        json.dumps(telemetry, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Cross-day fingerprint (accumulate)
    fingerprint_path = telemetry_dir / "editorial_fingerprint.json"
    fingerprint = {"days": 0, "runs": [], "role_frequency": {}, "role_stability": {}}
    if fingerprint_path.exists():
        try:
            fingerprint = json.loads(fingerprint_path.read_text())
        except (json.JSONDecodeError, KeyError):
            pass

    fingerprint["days"] = fingerprint.get("days", 0) + 1
    fingerprint["runs"] = fingerprint.get("runs", []) + [telemetry]

    # Aggregate role frequency
    role_freq = fingerprint.get("role_frequency", {})
    for role_name, info in telemetry.get("role_assignment", {}).items():
        event_title = info.get("event", "")
        if role_name not in role_freq:
            role_freq[role_name] = {}
        # Extract source/org from event title (first word heuristic)
        org = event_title.split("发布")[0].split("：")[0].split("研究")[0].strip()
        if len(org) > 2:
            role_freq[role_name][org] = role_freq[role_name].get(org, 0) + 1
    fingerprint["role_frequency"] = role_freq

    # Role stability (how often each role is filled)
    total_runs = len(fingerprint["runs"])
    role_stability = fingerprint.get("role_stability", {})
    for role_name in ROLE_DEFINITIONS:
        filled = sum(
            1 for r in fingerprint["runs"]
            if role_name in r.get("role_assignment", {})
        )
        role_stability[role_name] = round(filled / total_runs, 2) if total_runs else 0.0
    fingerprint["role_stability"] = role_stability

    fingerprint_path.write_text(
        json.dumps(fingerprint, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(run_path)


# ── Pipeline Stage (Stage Protocol) ──

class RoleAssignerStage:
    """Pipeline stage: deterministic narrative role assignment (observation only).

    Insert between SynthesizeStage and ArticleCompilerStage.
    Reads InsightBrief, assigns roles, writes telemetry.
    Does NOT modify ctx["insight_brief"]. Does NOT discard events.

    v1.0 output channels (observability only):
      ctx["editorial_telemetry"]  — per-run role assignment + unassigned list
    """

    def process(self, ctx) -> dict:
        """Pipeline Stage protocol: process(ctx) -> ctx."""
        insight = ctx.get("insight_brief")
        if insight is None:
            logger.info("RoleAssignerStage: no insight_brief, skipping")
            return ctx

        events = insight.event_ledger or []
        shifts = insight.structural_shifts or []
        signals = insight.signal_map or []
        themes = insight.today_themes or []

        result = assign_roles(events, shifts, signals, themes)

        report_date = ctx.get("report_date", date.today())
        date_str = report_date.isoformat() if hasattr(report_date, "isoformat") else str(report_date)

        telemetry = build_telemetry(result, date_str)

        config = ctx.get("config")
        base_dir = (
            getattr(getattr(config, "artifact", None), "output_dir", None)
            or "./output/artifacts"
        )
        path = save_telemetry(telemetry, base_dir)

        # Expose to downstream stages (observability only, no control)
        ctx.set("editorial_telemetry", telemetry)

        logger.info(
            "RoleAssignerStage: date=%s candidates=%d roles=%d unassigned=%d → %s",
            date_str, result.candidate_count, result.selected_count,
            len(result.unassigned), path,
        )

        return ctx
