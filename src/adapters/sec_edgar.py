"""SEC EDGAR adapter — fetch AI company filings via data.sec.gov API."""

import json
import logging
import urllib.request
from datetime import datetime, timezone

from src.models.article import RawArticle

logger = logging.getLogger(__name__)

# User-Agent required by SEC: must identify the requestor
USER_AGENT = "ai-daily/1.0 (contact@jarvis.dev)"

# Major AI companies + CIK numbers
AI_CIKS = {
    "0000320193": "Apple",
    "0000789019": "Microsoft",
    "0001652044": "Alphabet (Google)",
    "0001326801": "Meta",
    "0001045810": "NVIDIA",
    "0001018724": "Amazon",
    "0001820876": "OpenAI",          # may not have CIK yet
    "0002000694": "Anthropic",       # may not have CIK yet
}

FILING_TYPES = ["8-K", "10-K", "10-Q", "S-1", "4", "13F", "SD"]


class SECEdgarAdapter:
    """Fetch recent SEC filings for AI companies.

    Implements RSSAdapter-compatible interface:
        fetch(url, source_name, max_articles) -> list[RawArticle]
    """

    def fetch(self, url: str = "", source_name: str = "SEC EDGAR",
              max_articles: int | None = None) -> list[RawArticle]:
        limit = max_articles or 20
        articles = []

        for cik, name in AI_CIKS.items():
            try:
                filings = self._fetch_filings(cik, name, limit=5)
                articles.extend(filings)
            except Exception as e:
                logger.debug("SEC fetch failed for %s (%s): %s", name, cik, e)

        articles.sort(key=lambda a: a.published, reverse=True)
        logger.info("SEC EDGAR: %d filings from %d companies", len(articles), len(AI_CIKS))
        return articles[:limit]

    def _fetch_filings(self, cik: str, name: str, limit: int = 5) -> list[RawArticle]:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Host": "data.sec.gov",
        })

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                data = json.loads(raw.decode())
        except Exception as e:
            logger.debug("SEC request failed for %s: %s", cik, e)
            return []

        filings = data.get("filings", {}).get("recent", {})
        if not filings:
            return []

        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        descriptions = filings.get("primaryDocument", [])
        acc_numbers = filings.get("accessionNumber", [])

        articles = []
        for i in range(min(len(forms), 200)):
            form_type = forms[i]
            if form_type not in FILING_TYPES:
                continue

            date_str = dates[i] if i < len(dates) else ""
            doc = descriptions[i] if i < len(descriptions) else ""
            acc = acc_numbers[i] if i < len(acc_numbers) else ""

            # Build EDGAR link
            acc_clean = acc.replace("-", "")
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{acc_clean}/{doc}"

            published = self._parse_date(date_str)

            form_label = {"8-K": "重大事项", "10-K": "年报", "10-Q": "季报", "S-1": "IPO申请", "4": "内幕交易", "13F": "机构持仓", "SD": "专项披露"}.get(form_type, form_type)
            title = f"[{form_type}] {name} {form_label}"

            articles.append(RawArticle(
                title=title[:200],
                link=filing_url,
                summary=f"{name} filed {form_type} on {date_str}",
                published=published,
                source="SEC EDGAR",
            ))

            if len(articles) >= limit:
                break

        return articles

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)
