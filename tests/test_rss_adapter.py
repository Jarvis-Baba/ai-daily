from unittest.mock import patch, MagicMock
from datetime import datetime
from src.adapters.rss import RSSAdapter


def make_feed_entry(title, link, summary="", published=None):
    entry = MagicMock()
    entry.title = title
    entry.link = link
    entry.summary = summary
    if published:
        entry.published_parsed = published
    else:
        entry.published_parsed = (2026, 5, 30, 8, 0, 0, 0, 0, 0)

    # Configure .get() to return the right values (implementation uses dict-style access)
    def _get(key, default=""):
        if key == "title":
            return title
        elif key == "link":
            return link
        elif key == "summary":
            return summary
        return default
    entry.get.side_effect = _get

    return entry


def test_fetch_single_feed_returns_articles():
    adapter = RSSAdapter(timeout=30)
    mock_feed = MagicMock()
    mock_feed.entries = [
        make_feed_entry("Article 1", "https://example.com/1", "Summary 1"),
        make_feed_entry("Article 2", "https://example.com/2", "Summary 2"),
    ]
    mock_feed.bozo = 0
    mock_feed.feed.title = "TestFeed"

    with patch("feedparser.parse", return_value=mock_feed) as mock_parse:
        articles = adapter.fetch("https://example.com/rss", "TestFeed")

    assert len(articles) == 2
    assert articles[0].title == "Article 1"
    assert articles[0].link == "https://example.com/1"
    assert articles[0].source == "TestFeed"
    mock_parse.assert_called_once()


def test_fetch_respects_max_articles():
    adapter = RSSAdapter(timeout=30, max_articles=3)
    mock_feed = MagicMock()
    mock_feed.entries = [
        make_feed_entry(f"A{i}", f"https://x.com/{i}") for i in range(10)
    ]
    mock_feed.bozo = 0
    mock_feed.feed.title = "BigFeed"

    with patch("feedparser.parse", return_value=mock_feed):
        articles = adapter.fetch("https://example.com/rss", "BigFeed", max_articles=3)

    assert len(articles) == 3


def test_fetch_timeout_returns_empty_list():
    import urllib.error
    adapter = RSSAdapter(timeout=5)

    with patch("feedparser.parse", side_effect=urllib.error.URLError("timeout")):
        articles = adapter.fetch("https://example.com/rss", "BadFeed")

    assert articles == []


def test_fetch_bad_xml_returns_empty_list():
    adapter = RSSAdapter(timeout=30)
    mock_feed = MagicMock()
    mock_feed.entries = []
    mock_feed.bozo = 1
    mock_feed.bozo_exception = Exception("Malformed XML")

    with patch("feedparser.parse", return_value=mock_feed):
        articles = adapter.fetch("https://example.com/bad", "BadFeed")

    assert articles == []


def test_fetch_missing_title_or_link_skips_entry():
    adapter = RSSAdapter(timeout=30)
    mock_feed = MagicMock()
    mock_feed.entries = [
        make_feed_entry("Good", "https://example.com/good", "Summary"),
        make_feed_entry("", "https://example.com/empty-title", "Summary"),
        make_feed_entry("No Link", "", "Summary"),
        make_feed_entry("Good 2", "https://example.com/good2", "Summary 2"),
    ]
    mock_feed.bozo = 0
    mock_feed.feed.title = "TestFeed"

    with patch("feedparser.parse", return_value=mock_feed):
        articles = adapter.fetch("https://example.com/rss", "TestFeed")

    assert len(articles) == 2
    assert articles[0].title == "Good"
    assert articles[1].title == "Good 2"
