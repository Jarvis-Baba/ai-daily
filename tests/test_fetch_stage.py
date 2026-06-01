from unittest.mock import MagicMock
from datetime import datetime
from src.pipeline.stage import PipelineContext
from src.stages.fetch import FetchStage
from src.models.article import RawArticle, Article


def make_raw(title, link, source, summary=""):
    return RawArticle(
        title=title,
        link=link,
        summary=summary,
        published=datetime(2026, 5, 30),
        source=source,
    )


def test_fetch_stage_queries_enabled_feeds():
    ctx = PipelineContext()
    ctx.set("config", MagicMock())
    ctx.get("config").feeds = [
        MagicMock(name="FeedA", url="https://a.com/rss", enabled=True),
        MagicMock(name="FeedB", url="https://b.com/rss", enabled=False),
    ]
    ctx.get("config").fetch = MagicMock(timeout=30, max_articles_per_feed=10)

    stage = FetchStage(rss_adapter=MagicMock())
    stage._rss.fetch.side_effect = [
        [make_raw("A1", "https://a.com/1", "FeedA")],
        [],
    ]

    result = stage.process(ctx)
    articles = result.get("articles", [])

    assert len(articles) == 1
    assert articles[0].source == "FeedA"
    assert stage._rss.fetch.call_count == 1


def test_fetch_stage_dedup_by_url():
    ctx = PipelineContext()
    ctx.set("config", MagicMock())
    ctx.get("config").feeds = [
        MagicMock(name="FeedA", url="https://a.com/rss", enabled=True),
    ]
    ctx.get("config").fetch = MagicMock(timeout=30, max_articles_per_feed=10)

    stage = FetchStage(rss_adapter=MagicMock())
    stage._rss.fetch.return_value = [
        make_raw("T1", "https://x.com/same-url", "FeedA"),
        make_raw("T2", "https://x.com/same-url", "FeedA"),
        make_raw("T3", "https://x.com/other", "FeedA"),
    ]

    result = stage.process(ctx)
    articles = result.get("articles", [])

    assert len(articles) == 2


def test_fetch_stage_converts_raw_to_article():
    ctx = PipelineContext()
    ctx.set("config", MagicMock())
    ctx.get("config").feeds = [
        MagicMock(name="FeedA", url="https://a.com/rss", enabled=True),
    ]
    ctx.get("config").fetch = MagicMock(timeout=30, max_articles_per_feed=10)

    stage = FetchStage(rss_adapter=MagicMock())
    stage._rss.fetch.return_value = [
        make_raw("Title", "https://x.com/1", "FeedA", "Summary text"),
    ]

    result = stage.process(ctx)
    articles = result.get("articles", [])

    assert len(articles) == 1
    a = articles[0]
    assert isinstance(a, Article)
    assert a.title == "Title"
    assert a.link == "https://x.com/1"
    assert a.source == "FeedA"
    assert a.summary == "Summary text"


def test_fetch_stage_health_marks_feed_type():
    ctx = PipelineContext()
    ctx.set("config", MagicMock())
    feed = MagicMock(name="RedditML", url="MachineLearning top week", enabled=True)
    feed.priority = 2
    feed.feed_type = "reddit_json"
    ctx.get("config").feeds = [feed]
    ctx.get("config").fetch = MagicMock(timeout=30, max_articles_per_feed=10)

    stage = FetchStage(rss_adapter=MagicMock())
    stage._rss.fetch.return_value = []

    result = stage.process(ctx)
    report = result.get("health_report")

    assert report.feeds[0].feed_type == "reddit_json"
    assert report.feeds[0].status == "degraded"
