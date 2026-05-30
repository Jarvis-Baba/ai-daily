import os
import tempfile
from unittest.mock import MagicMock
from datetime import datetime
from src.main import build_pipeline, run_pipeline
from src.pipeline.stage import PipelineContext
from src.config.loader import AppConfig, FeedConfig, FetchConfig, LLMConfig, FilterConfig, OutputConfig
from src.models.article import RawArticle


def make_raw(title, link, source, summary=""):
    return RawArticle(
        title=title,
        link=link,
        summary=summary,
        published=datetime(2026, 5, 30),
        source=source,
    )


def test_full_pipeline_integration():
    """End-to-end: config -> pipeline -> markdown file"""
    config = AppConfig(
        feeds=[
            FeedConfig(name="FeedA", url="https://a.com/rss", enabled=True),
            FeedConfig(name="FeedB", url="https://b.com/rss", enabled=True),
        ],
        fetch=FetchConfig(timeout=30, max_articles_per_feed=10),
        llm=LLMConfig(provider="dummy", model="dummy", api_key=""),
        filter=FilterConfig(top_n=3, min_score=4),
        output=OutputConfig(
            dir=tempfile.gettempdir(),
            filename="morning-{date}.md",
            template="# AI Morning Brief — {date}\n\n{items}\n\n---\n> {timestamp}",
        ),
    )

    mock_rss = MagicMock()
    mock_rss.fetch.side_effect = [
        [
            make_raw("AI News 1", "https://x.com/1", "FeedA", "AI breakthrough"),
            make_raw("AI News 2", "https://x.com/2", "FeedA", "New model release"),
        ],
        [
            make_raw("Market Update", "https://x.com/3", "FeedB", "Stocks rally"),
        ],
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        config.output.dir = tmpdir
        pipeline = build_pipeline(config, rss_adapter=mock_rss)
        ctx = PipelineContext()
        ctx.set("config", config)
        ctx.set("output_dir", tmpdir)
        ctx.set("output_template", config.output.template)

        result = run_pipeline(pipeline, ctx)

        output_path = result.get("output_path")
        assert os.path.exists(output_path)

        content = open(output_path).read()
        assert "AI Morning Brief" in content
        assert "AI News" in content or "Market" in content


def test_build_pipeline_returns_4_stages():
    config = AppConfig(
        feeds=[FeedConfig(name="F", url="https://f.com/rss", enabled=True)],
        fetch=FetchConfig(),
        llm=LLMConfig(provider="dummy", model="dummy", api_key=""),
        filter=FilterConfig(),
        output=OutputConfig(),
    )
    pipeline = build_pipeline(config)
    assert len(pipeline._stages) == 4
