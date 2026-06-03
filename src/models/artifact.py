"""EVIDENCE-ABI §2 Artifact object. Raw source capture — no extraction, no analysis."""
from dataclasses import dataclass, field


ARTIFACT_TYPES = frozenset({
    "research_paper", "blog_post", "news_article",
    "tweet", "video_transcript", "github_commit", "screenshot", "pdf",
})


@dataclass
class Artifact:
    artifact_id: str              # "A-YYYYMMDD-NNN"
    artifact_type: str            # One of ARTIFACT_TYPES
    source_url: str               # Original URL as configured
    canonical_url: str            # Normalized URL for dedup
    retrieved_at: str             # ISO-8601
    content_hash: str             # "sha256:<hex>"
    raw_content: str              # Extracted clean text (not a summary)
    content_type: str = ""        # "text/html", "text/markdown", "text/plain"
    source_name: str = ""         # Derived from domain
    title: str = ""               # Extracted from <title> or first heading
    published_at: str = ""        # If discoverable
    authors: list[str] = field(default_factory=list)
    screenshot_refs: list[str] = field(default_factory=list)   # Paths to page screenshots
    retrieved_via: str = ""       # "playwright" | "http" | "jina"
    media_items: list[dict] = field(default_factory=list)      # v0.2: [{type, url, alt}]
