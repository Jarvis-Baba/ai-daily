from datetime import datetime, date
from src.pipeline.stage import PipelineContext
from src.stages.summarize import SummarizeStage
from src.models.article import Article


def make_article(title, link, source="Feed", score=8):
    return Article(
        title=title,
        link=link,
        summary=f"Summary of {title}",
        published=datetime(2026, 5, 30),
        source=source,
        score=score,
    )


def test_summarize_stage_produces_brief():
    articles = [
        make_article("AI Breakthrough", "https://x.com/1", "TechCrunch", 9),
        make_article("Market Update", "https://x.com/2", "Bloomberg", 7),
        make_article("Startup Funding", "https://x.com/3", "TechCrunch", 8),
    ]

    ctx = PipelineContext()
    ctx.set("articles", articles)
    ctx.set("config", None)

    from src.adapters.llm import DummyAdapter

    stage = SummarizeStage(llm_adapter=DummyAdapter())

    result = stage.process(ctx)
    brief = result.get("brief")

    assert brief is not None
    assert brief.date == date.today()
    assert len(brief.items) == 3


def test_summarize_stage_handles_empty_articles():
    ctx = PipelineContext()
    ctx.set("articles", [])
    ctx.set("config", None)

    from src.adapters.llm import DummyAdapter

    stage = SummarizeStage(llm_adapter=DummyAdapter())

    result = stage.process(ctx)
    brief = result.get("brief")

    assert brief is not None
    assert brief.date == date.today()
    assert brief.items == []
