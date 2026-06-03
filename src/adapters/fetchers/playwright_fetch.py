"""Playwright headless Chromium fetcher for dynamic/JS-rendered pages.

Returns fully rendered DOM state (HTML + extracted text + screenshot + media list).
This is the primary fetcher for sources that require JS execution (OpenAI, Anthropic,
GitHub, React/SPA sites)."""

import hashlib
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)

# Domains that MUST use Playwright (SPA, JS-rendered, bot-protected)
_PLAYWRIGHT_REQUIRED = re.compile(
    r"(openai\.com|anthropic\.com|github\.com/blog|"
    r"meta\.com|figma\.com|notion\.so|"
    r"web\.whatsapp|twitter\.com|x\.com)"
)

# Max 15s for page load, 5s extra for network idle
_PAGE_TIMEOUT_MS = 15_000
_NETWORK_IDLE_TIMEOUT_MS = 5_000


def needs_playwright(url: str) -> bool:
    """Check if URL is known to require JS rendering."""
    return bool(_PLAYWRIGHT_REQUIRED.search(url))


def _safe_filename(url: str, suffix: str) -> str:
    """Generate a safe filename from URL hash."""
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return f"{h}{suffix}"


def _extract_text_from_html(html: str) -> str:
    """Strip HTML tags, scripts, styles — return plain text."""
    # Remove script/style/noscript blocks
    cleaned = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove remaining HTML tags
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    # Remove HTML entities
    cleaned = re.sub(r"&[a-z]+;", " ", cleaned)
    cleaned = re.sub(r"&#\d+;", " ", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:100_000]


def fetch_with_playwright(url: str, *, output_dir: str = "", capture_screenshot: bool = True, timeout_ms: int = 15000) -> dict:
    """Fetch a URL using headless Chromium. Returns dict with html, text, title, media, screenshot.

    Returns empty dict on failure. Caller handles fallback.
    """
    result = {
        "html": "",
        "text": "",
        "title": "",
        "media": [],
        "screenshot": "",
        "error": "",
    }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        result["error"] = "playwright not installed"
        return result

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    # WSL2/Docker require --no-sandbox because Chromium can't
                    # create user namespaces. The host OS provides isolation.
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )

            context = browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
            )

            page = context.new_page()
            page.set_default_timeout(_PAGE_TIMEOUT_MS)

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                # Give JS a moment to render, but don't wait forever
                try:
                    page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT_MS)
                except Exception:
                    pass  # networkidle timeout is OK
            except Exception as e:
                logger.debug("Playwright page.goto failed for %s: %s", url, e)
                browser.close()
                result["error"] = str(e)[:200]
                return result

            time.sleep(0.5)  # Small grace period for late-rendering content

            result["title"] = page.title()
            result["html"] = page.content()

            # Extract clean text
            result["text"] = _extract_text_from_html(result["html"])

            # Media extraction
            try:
                img_elements = page.query_selector_all("img")
                parsed_base = urlparse(url)
                for img in img_elements:
                    src = img.get_attribute("src")
                    if not src:
                        continue
                    # Resolve relative URLs
                    if src.startswith("//"):
                        src = f"{parsed_base.scheme}:{src}"
                    elif src.startswith("/"):
                        src = urljoin(url, src)
                    elif not src.startswith("http"):
                        src = urljoin(url, src)
                    alt = img.get_attribute("alt") or ""
                    result["media"].append({
                        "type": "image",
                        "url": src,
                        "alt": alt[:200],
                    })
            except Exception:
                logger.debug("Media extraction failed for %s", url, exc_info=True)

            # Screenshot
            if capture_screenshot and output_dir:
                try:
                    os_screenshot_dir = Path(output_dir)
                    os_screenshot_dir.mkdir(parents=True, exist_ok=True)
                    fname = _safe_filename(url, ".png")
                    spath = os_screenshot_dir / fname
                    page.screenshot(path=str(spath), full_page=True)
                    result["screenshot"] = str(spath)
                except Exception:
                    logger.debug("Screenshot failed for %s", url, exc_info=True)

            browser.close()
            return result

    except Exception as e:
        logger.debug("Playwright fetch failed for %s: %s", url, e)
        result["error"] = str(e)[:200]
        return result


import os
