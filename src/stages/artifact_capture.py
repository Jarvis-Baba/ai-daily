"""Stage 0: L0 Source Compiler v0.2. Three-tier capture: Playwright -> HTTP -> Jina.

Captures source URLs as verifiable Artifacts with content_hash, screenshots,
and media extraction. Idempotent by canonical URL.
"""
import hashlib
import logging
import re
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from src.pipeline.stage import PipelineContext
from src.models.artifact import Artifact
from src.adapters.artifact_store import save, find_by_url, next_id
from src.adapters.fetchers.raw_fetch import fetch_raw
from src.adapters.fetchers.playwright_fetch import needs_playwright, fetch_with_playwright
from src.adapters.telemetry import write_telemetry

logger = logging.getLogger(__name__)

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

_TYPE_PATTERNS = [
    (re.compile(r"arxiv\.org/abs"), "research_paper"),
    (re.compile(r"github\.com/[^/]+/[^/]+/commit"), "github_commit"),
    (re.compile(r"(twitter\.com|x\.com)/\w+/status"), "tweet"),
    (re.compile(r"youtube\.com|youtu\.be"), "video_transcript"),
    (re.compile(r"\.pdf$"), "pdf"),
    (re.compile(r"(blog\.|medium\.com|substack\.com|dev\.to)"), "blog_post"),
    (re.compile(r"(arxiv|papers|research)"), "research_paper"),
    (re.compile(r"github\.com"), "blog_post"),
]

_JINA_BASE = "https://r.jina.ai"


def _canonicalize(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.hostname.lower() if parsed.hostname else parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


def _infer_artifact_type(url: str) -> str:
    for pattern, atype in _TYPE_PATTERNS:
        if pattern.search(url):
            return atype
    return "blog_post"


def _extract_title_from_html(html: str) -> str:
    m = _TITLE_RE.search(html)
    if m:
        title = m.group(1).strip()
        title = title.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        title = title.replace("&quot;", '"').replace("&#39;", "'")
        return title[:300]
    return ""


def _extract_text_from_http(raw_bytes: bytes, content_type: str) -> str:
    if "text/html" in content_type:
        from src.adapters.fetchers.basic import _TextExtractor
        html_str = raw_bytes.decode("utf-8", errors="replace")[:500_000]
        extractor = _TextExtractor()
        extractor.feed(html_str)
        text = extractor.get_text()
        return text[:100_000]
    return raw_bytes.decode("utf-8", errors="replace")[:100_000]


def _jina_fetch(url: str, *, timeout: int = 15, max_chars: int = 100_000) -> str:
    try:
        req = urllib.request.Request(
            f"{_JINA_BASE}/{url}",
            headers={"Accept": "text/markdown", "User-Agent": "ai-daily/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")[:max_chars]
    except Exception:
        logger.debug("Jina fallback failed for %s", url, exc_info=True)
        return ""


def _extract_title_from_markdown(text: str) -> str:
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("# ") and len(line) > 2:
            return line[2:].strip()[:300]
    return ""


# ── Three-tier fetch dispatcher ──

def _fetch_playwright(url: str, output_dir: str, timeout: int) -> dict:
    """Try Playwright. Returns dict with text/html/title/media/screenshot keys."""
    result = fetch_with_playwright(
        url,
        output_dir=output_dir,
        capture_screenshot=True,
        timeout_ms=timeout * 1000,
    )
    if result.get("text") and not result.get("error"):
        result["content_type"] = "text/html; playwright"
        result["retrieved_via"] = "playwright"
        return result
    return {}


def _fetch_http(url: str, timeout: int) -> dict:
    """Try raw HTTP. Returns dict with text/content_type or empty."""
    raw_bytes, content_type = fetch_raw(url, timeout=timeout)
    if raw_bytes:
        text = _extract_text_from_http(raw_bytes, content_type)
        if text.strip():
            title = ""
            if "text/html" in content_type:
                title = _extract_title_from_html(raw_bytes.decode("utf-8", errors="replace"))
            return {
                "text": text,
                "title": title,
                "content_type": content_type,
                "retrieved_via": "http",
                "raw_bytes": raw_bytes,
            }
    return {}


def _fetch_jina(url: str, timeout: int) -> dict:
    """Try Jina Reader. Returns dict with text/content_type or empty."""
    jina_text = _jina_fetch(url, timeout=timeout)
    if jina_text.strip():
        return {
            "text": jina_text,
            "title": _extract_title_from_markdown(jina_text),
            "content_type": "text/markdown",
            "retrieved_via": "jina",
        }
    return {}


# ── Stage ──

class L0CaptureStage:
    """Stage 0: L0 Source Compiler v0.2. Three-tier capture with media support.

    Routing:
      - Playwright-first for known JS-heavy domains (openai.com, anthropic.com, etc.)
      - HTTP for static pages
      - Jina as fallback
      - Playwright as last-resort for all URLs if HTTP+Jina both fail

    Idempotent: skips URLs already captured today (by canonical_url).
    """

    def __init__(self, artifact_base_dir: str | None = None):
        self._artifact_base_dir = artifact_base_dir

    def process(self, ctx: PipelineContext) -> PipelineContext:
        config = ctx.get("config")
        if config is None:
            logger.warning("L0CaptureStage: no config in context, skipping")
            ctx.set("artifact_refs", [])
            ctx.set("artifacts", [])
            return ctx

        artifact_cfg = getattr(config, "artifact", None)
        if artifact_cfg is None or not getattr(artifact_cfg, "enabled", False):
            logger.info("L0CaptureStage: artifact capture disabled, skipping")
            ctx.set("artifact_refs", [])
            ctx.set("artifacts", [])
            return ctx

        base_dir = self._artifact_base_dir or getattr(artifact_cfg, "output_dir", "./output/artifacts")
        sources = getattr(artifact_cfg, "sources", []) or []
        if not sources:
            logger.info("L0CaptureStage: no source URLs configured, skipping")
            ctx.set("artifact_refs", [])
            ctx.set("artifacts", [])
            return ctx

        timeout = getattr(artifact_cfg, "timeout", 15)
        screenshot_enabled = getattr(artifact_cfg, "screenshot_enabled", True)
        media_dir = getattr(artifact_cfg, "media_dir", f"{base_dir}/media")
        today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        artifacts: list[Artifact] = []

        for url in sources:
            canonical_url = _canonicalize(url)
            t0 = time.monotonic()

            # Idempotency
            existing = find_by_url(today_str, canonical_url, base_dir)
            if existing is not None:
                logger.info("L0CaptureStage: skip %s (already %s)", url, existing.artifact_id)
                artifacts.append(existing)
                write_telemetry({
                    "url": url, "canonical_url": canonical_url, "status": "skipped",
                    "artifact_id": existing.artifact_id, "latency_ms": 0,
                    "fetcher": existing.retrieved_via,
                }, base_dir)
                continue

            # ── Three-tier fetch ──
            result = {}

            # Tier 1: Playwright for known JS-heavy domains
            if needs_playwright(url):
                logger.info("L0CaptureStage: playwright-first for %s", url)
                result = _fetch_playwright(url, media_dir if screenshot_enabled else "", timeout)

            # Tier 2: HTTP (if not Playwright-first, or Playwright failed)
            if not result:
                logger.info("L0CaptureStage: trying HTTP for %s", url)
                result = _fetch_http(url, timeout)

            # Tier 3: Jina fallback
            if not result:
                logger.info("L0CaptureStage: trying Jina for %s", url)
                result = _fetch_jina(url, timeout)

            # Tier 4: Playwright as last resort for all URLs
            if not result:
                logger.info("L0CaptureStage: last-resort Playwright for %s", url)
                result = _fetch_playwright(url, media_dir if screenshot_enabled else "", timeout)

            latency_ms = int((time.monotonic() - t0) * 1000)

            if not result or not result.get("text", "").strip():
                logger.warning("L0CaptureStage: all tiers failed for %s", url)
                write_telemetry({
                    "url": url, "canonical_url": canonical_url, "status": "failed",
                    "latency_ms": latency_ms, "fetcher": "none",
                }, base_dir)
                continue

            text = result["text"]
            title = result.get("title", "")
            content_type = result.get("content_type", "")
            retrieved_via = result.get("retrieved_via", "unknown")
            media_items = result.get("media", [])
            screenshot_path = result.get("screenshot", "")

            # Content hash: use text content for consistency across fetchers
            content_hash = f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"

            # If no title from fetcher, extract from text
            if not title and "text/html" in content_type:
                raw_bytes = result.get("raw_bytes")
                if raw_bytes:
                    title = _extract_title_from_html(raw_bytes.decode("utf-8", errors="replace"))
            if not title:
                title = _extract_title_from_markdown(text)

            parsed = urlparse(canonical_url)
            source_name = parsed.hostname or url

            screenshot_refs = [screenshot_path] if screenshot_path else []
            artifact_id = next_id(today_str, base_dir)

            artifact = Artifact(
                artifact_id=artifact_id,
                artifact_type=_infer_artifact_type(canonical_url),
                source_url=url,
                canonical_url=canonical_url,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                content_hash=content_hash,
                raw_content=text,
                content_type=content_type,
                source_name=source_name,
                title=title,
                screenshot_refs=screenshot_refs,
                retrieved_via=retrieved_via,
                media_items=media_items,
            )

            save(artifact, base_dir)
            artifacts.append(artifact)
            media_info = f", {len(media_items)} imgs" if media_items else ""
            screenshot_info = ", +screenshot" if screenshot_path else ""
            logger.info("L0CaptureStage: %s -> %s via %s (%s%s%s)",
                        url, artifact_id, retrieved_via,
                        artifact.artifact_type, media_info, screenshot_info)

            write_telemetry({
                "url": url,
                "canonical_url": canonical_url,
                "status": "success",
                "artifact_id": artifact_id,
                "fetcher": retrieved_via,
                "latency_ms": latency_ms,
                "content_length": len(text),
                "content_hash": content_hash,
                "media_count": len(media_items),
                "has_screenshot": bool(screenshot_path),
                "artifact_type": artifact.artifact_type,
                "source_name": source_name,
            }, base_dir)

        ctx.set("artifact_refs", [a.artifact_id for a in artifacts])
        ctx.set("artifacts", artifacts)
        logger.info("L0CaptureStage: %d artifacts captured", len(artifacts))
        return ctx
