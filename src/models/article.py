from dataclasses import dataclass, field
from datetime import datetime, date
from hashlib import sha256


@dataclass
class RawArticle:
    title: str
    link: str
    summary: str
    published: datetime
    source: str


@dataclass
class Article:
    title: str
    link: str
    summary: str
    published: datetime
    source: str
    content: str = ""
    score: int = 0

    @property
    def id(self) -> str:
        return sha256(self.link.encode()).hexdigest()


@dataclass
class BriefItem:
    title: str
    source: str
    score: int
    digest: str
    link: str


@dataclass
class Brief:
    date: date
    items: list[BriefItem]


# ── v3 decision-system models ──


@dataclass
class StructuralShift:
    """Mechanism-level change with causal structure. Not news — a rule rewrite."""
    title: str
    mechanism: str       # causal explanation, not opinion
    trigger: str         # observable condition or event that activated this
    consequence: str     # system-level effect
    impact: str          # high / medium / low
    time_horizon: str    # short / medium / long
    source: str
    link: str


@dataclass
class EventLedgerItem:
    """Classified event. One type only — no mixed categories."""
    type: str            # capital / capability / behavioral
    title: str           # short description (≤30 chars)
    source: str
    link: str


@dataclass
class SignalMapItem:
    """Derivation chain: Events → Mechanism → Hypothesis. Not assertion."""
    hypothesis: str
    supporting_events: list[str]   # references to event_ledger titles
    mechanism: str                 # causal link connecting events to hypothesis


@dataclass
class RiskItem:
    """Risk with time horizon. Type × horizon = decision urgency."""
    type: str            # bubble / structural / regime
    horizon: str         # immediate / structural / long
    description: str
    related_theme: str = ""


@dataclass
class DecisionHook:
    """Decision trigger, not a task. Answers: what signal, what action, why now."""
    trigger_condition: str   # observable condition that activates this
    action: str              # specific execution
    rationale: str           # "why now" — timing justification
    audience: str
    level: str = "L2"        # L1=immediate L2=this-week L3=prohibited


# ── v2 models (retained for legacy fallback) ──


@dataclass
class AlphaItem:
    title: str
    source: str
    link: str
    conclusion: str
    variables: list[str]
    actions: list[str]
    theme_id: str = ""


@dataclass
class BetaItem:
    title: str
    source: str
    link: str
    point: str
    theme_id: str = ""


@dataclass
class SignalItem:
    signal: str
    evidence: list[str]


@dataclass
class ActionItem:
    audience: str
    actions: list[str]
    level: str = "L2"


# ── unified insight (v3 primary) ──


@dataclass
class InsightBrief:
    date: date
    executive_judgment: str = ""
    structural_shifts: list[StructuralShift] = field(default_factory=list)
    event_ledger: list[EventLedgerItem] = field(default_factory=list)
    signal_map: list[SignalMapItem] = field(default_factory=list)
    risks: list[RiskItem] = field(default_factory=list)
    decision_hooks: list[DecisionHook] = field(default_factory=list)
    today_themes: list[str] = field(default_factory=list)
