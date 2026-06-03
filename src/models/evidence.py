"""Evidence data models — EVIDENCE-ABI-v1.md Sections 3-4.

ABI status: FROZEN v1.0. Field additions are backward-compatible.
Field renames or removals require a v2 migration.
"""

from dataclasses import dataclass, field
from enum import Enum


class FactType(str, Enum):
    SOURCE_STATEMENT = "source_statement"
    VERIFIABLE_FACT = "verifiable_fact"


class VerificationStatus(str, Enum):
    DIRECT_SOURCE = "direct_source"
    CROSS_REFERENCED = "cross_referenced"
    UNVERIFIED = "unverified"
    DISPUTED = "disputed"


class SourceType(str, Enum):
    OFFICIAL_BLOG = "official_blog"
    RESEARCH_PAPER = "research_paper"
    NEWS_MEDIA = "news_media"
    SOCIAL_MEDIA = "social_media"
    CORPORATE_FILING = "corporate_filing"
    INDEPENDENT_REPORT = "independent_report"
    UNKNOWN = "unknown"


@dataclass
class EvidenceSource:
    name: str           # e.g. "Anthropic Research"
    type: str           # SourceType value
    url: str            # source URL
    published_at: str   # ISO-8601 or ""


@dataclass
class EvidenceConfidence:
    source_reliability: float       # 0.0-1.0, deterministic by domain
    evidence_strength: float        # 0.0-1.0, LLM-assigned per claim
    verification_status: str        # VerificationStatus value


@dataclass
class SupportingMaterial:
    quote: str = ""
    screenshot_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    media_refs: list[str] = field(default_factory=list)


@dataclass
class Evidence:
    evidence_id: str
    fact_type: str                  # FactType value
    source: EvidenceSource
    statement: str
    attribution: str
    supporting_material: SupportingMaterial
    confidence: EvidenceConfidence


@dataclass
class EvidencePackage:
    package_id: str          # "PKG-YYYYMMDD-NNN"
    topic: str               # e.g. "Anthropic NLA Paper Release"
    generated_at: str        # ISO-8601
    artifacts: list[str]     # artifact_id refs
    evidence: list[Evidence] # embedded Evidence objects


# ── System-assigned source reliability (deterministic, not LLM) ──

SOURCE_RELIABILITY_DEFAULTS: dict[str, float] = {
    "official_blog": 0.95,
    "research_paper": 0.85,
    "corporate_filing": 0.80,
    "independent_report": 0.70,
    "news_media": 0.65,
    "social_media": 0.35,
    "unknown": 0.50,
}

# Domains that override artifact_type-based source type inference
_OFFICIAL_DOMAINS = {
    "anthropic.com", "openai.com", "blog.google", "blog.research.google",
    "ai.meta.com", "github.blog",
}
_RESEARCH_DOMAINS = {"arxiv.org", "transformer-circuits.pub"}
_NEWS_DOMAINS = {"techcrunch.com", "theverge.com", "arstechnica.com", "wired.com", "venturebeat.com"}
_INDEPENDENT_DOMAINS = {"simonwillison.net", "lilianweng.github.io"}


def infer_source_type(artifact_type: str, source_name: str) -> str:
    """Map (artifact_type, domain) to SourceType for Evidence confidence assignment."""
    domain = source_name.lower()
    if domain in _OFFICIAL_DOMAINS or any(d in domain for d in _OFFICIAL_DOMAINS):
        return SourceType.OFFICIAL_BLOG.value
    if domain in _RESEARCH_DOMAINS or any(d in domain for d in _RESEARCH_DOMAINS):
        return SourceType.RESEARCH_PAPER.value
    if domain in _NEWS_DOMAINS or any(d in domain for d in _NEWS_DOMAINS):
        return SourceType.NEWS_MEDIA.value
    if domain in _INDEPENDENT_DOMAINS or any(d in domain for d in _INDEPENDENT_DOMAINS):
        return SourceType.INDEPENDENT_REPORT.value
    mapping = {
        "research_paper": SourceType.RESEARCH_PAPER.value,
        "blog_post": SourceType.INDEPENDENT_REPORT.value,
        "news_article": SourceType.NEWS_MEDIA.value,
        "tweet": SourceType.SOCIAL_MEDIA.value,
        "github_commit": SourceType.OFFICIAL_BLOG.value,
        "video_transcript": SourceType.SOCIAL_MEDIA.value,
    }
    return mapping.get(artifact_type, SourceType.UNKNOWN.value)
