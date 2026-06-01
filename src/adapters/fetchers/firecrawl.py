import ipaddress
import json
import logging
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BRIDGE_SCRIPT = Path.home() / "scripts" / "firecrawl_bridge.py"


def _is_public_hostname(hostname: str) -> bool:
    """Reject loopback, link-local, and private IPs to prevent SSRF."""
    hostname = hostname.rstrip(".").lower()
    if hostname in ("localhost", "localhost.localdomain"):
        return False
    try:
        for _, _, _, _, sockaddr in socket.getaddrinfo(hostname, 80, socket.AF_INET, socket.SOCK_STREAM):
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
    except socket.gaierror:
        return False
    return True


class FirecrawlFetcher:
    """Fetch via Firecrawl API — premium quality, costs credits."""

    @property
    def name(self) -> str:
        return "firecrawl"

    def fetch(self, url: str, *, timeout: int = 30, max_chars: int = 3000) -> str:
        if not url.startswith(("http://", "https://")):
            return ""
        hostname = urlparse(url).hostname
        if not hostname or not _is_public_hostname(hostname):
            return ""
        if not BRIDGE_SCRIPT.exists():
            logger.debug("Firecrawl bridge not found at %s", BRIDGE_SCRIPT)
            return ""

        try:
            # Firecrawl expects timeout in milliseconds; "--" prevents flag injection
            result = subprocess.run(
                ["python3", str(BRIDGE_SCRIPT), "scrape", "--timeout", str(timeout * 1000), "--", url],
                capture_output=True, text=True, timeout=timeout + 10,
            )
            if result.returncode != 0:
                logger.debug("Firecrawl bridge exited %d for %s", result.returncode, hostname)
                return ""

            if result.stdout.startswith("{"):
                data = json.loads(result.stdout)
                if not data.get("ok"):
                    return ""
                return data.get("text", "")[:max_chars]

            return result.stdout.strip()[:max_chars]
        except subprocess.TimeoutExpired:
            logger.debug("FirecrawlFetcher timeout for %s", hostname)
            return ""
        except Exception:
            logger.debug("FirecrawlFetcher failed for %s", hostname, exc_info=True)
            return ""
