from datetime import datetime
from src.pipeline.stage import PipelineContext
from src.stages.filter import FilterStage
from src.models.article import Article


def make_article(title, link, source="Feed"):
    return Article(
        title=title,
        link=link,
        summary=f"Summary of {title}",
        published=datetime(2026, 5, 30),
        source=source,
    )


def test_filter_stage_calls_llm_and_scores_articles():
    articles = [
        make_article(f"Article {i}", f"https://x.com/{i}") for i in range(10)
    ]
    ctx = PipelineContext()
    ctx.set("articles", articles)
    ctx.set("config", None)

    from src.adapters.llm import DummyAdapter

    stage = FilterStage(llm_adapter=DummyAdapter(), top_n=5, min_score=4)

    result = stage.process(ctx)
    filtered = result.get("articles", [])

    # With DummyAdapter, all articles get score=7 (mid-value fallback in _parse_scores)
    # So all pass min_score=4, and we get top_n=5
    assert len(filtered) == 5
    for a in filtered:
        assert a.score >= 4
    for i in range(len(filtered) - 1):
        assert filtered[i].score >= filtered[i + 1].score


def test_filter_stage_respects_min_score():
    articles = [
        make_article(f"A{i}", f"https://x.com/{i}") for i in range(5)
    ]
    ctx = PipelineContext()
    ctx.set("articles", articles)
    ctx.set("config", None)

    from src.adapters.llm import DummyAdapter

    stage = FilterStage(llm_adapter=DummyAdapter(), top_n=3, min_score=6)
    result = stage.process(ctx)

    assert len(result.get("articles", [])) <= 3


def test_filter_stage_handles_empty_input():
    ctx = PipelineContext()
    ctx.set("articles", [])
    ctx.set("config", None)

    from src.adapters.llm import DummyAdapter

    stage = FilterStage(llm_adapter=DummyAdapter(), top_n=5, min_score=2)
    result = stage.process(ctx)

    assert result.get("articles", []) == []
