import json
from datetime import datetime
from unittest.mock import MagicMock
from src.pipeline.stage import PipelineContext
from src.stages.scoring import ScoringStage
from src.models.article import Article
from src.models.scored_article import Bucket, ScoredArticle


def make_article(title, link, source, content="", summary=""):
    return Article(
        title=title,
        link=link,
        summary=summary,
        published=datetime(2026, 5, 30),
        source=source,
        content=content,
    )


def test_scoring_stage_produces_scored_articles():
    articles = [
        make_article("Alpha news", "https://x.com/1", "FeedA",
                     content="Game-changing AI breakthrough with immediate practical applications."),
        make_article("Beta news", "https://x.com/2", "FeedB",
                     content="Important but not earth-shattering development in AI."),
        make_article("Gamma noise", "https://x.com/3", "FeedC",
                     content="Minor update to an existing tool."),
    ]

    mock_llm = MagicMock()
    mock_llm.chat.return_value = json.dumps([
        {"index": 1, "impact": 9, "novelty": 8, "actionability": 7},
        {"index": 2, "impact": 6, "novelty": 5, "actionability": 4},
        {"index": 3, "impact": 3, "novelty": 2, "actionability": 2},
    ])

    ctx = PipelineContext()
    ctx.set("articles", articles)

    stage = ScoringStage(llm_adapter=mock_llm)
    result = stage.process(ctx)

    scored = result.get("scored_articles")
    assert len(scored) == 3

    # Alpha: impact=9 (>=8) + novelty=8 (>=7)
    assert scored[0].bucket == Bucket.ALPHA
    assert scored[0].impact == 9
    assert scored[0].novelty == 8
    assert scored[0].actionability == 7
    assert scored[0].article is articles[0]

    # Beta: impact=6 (>=5, but actionability=4 <6)
    assert scored[1].bucket == Bucket.BETA
    assert scored[1].impact == 6

    # Gamma: impact=3 (<5)
    assert scored[2].bucket == Bucket.GAMMA
    assert scored[2].impact == 3


def test_scoring_stage_bucket_rules():
    """Verify deterministic bucket assignment rules."""
    # Assign bucket via static method
    assert ScoringStage._assign_bucket(impact=10, novelty=10, actionability=1) == Bucket.ALPHA
    assert ScoringStage._assign_bucket(impact=8, novelty=7, actionability=1) == Bucket.ALPHA
    assert ScoringStage._assign_bucket(impact=8, novelty=6, actionability=10) == Bucket.BETA  # novelty < 7
    assert ScoringStage._assign_bucket(impact=7, novelty=10, actionability=10) == Bucket.BETA  # impact < 8
    assert ScoringStage._assign_bucket(impact=5, novelty=5, actionability=5) == Bucket.BETA  # total_score >= 5
    assert ScoringStage._assign_bucket(impact=4, novelty=5, actionability=10) == Bucket.BETA  # total_score >= 5
    assert ScoringStage._assign_bucket(impact=4, novelty=5, actionability=1) == Bucket.GAMMA
    assert ScoringStage._assign_bucket(impact=1, novelty=1, actionability=1) == Bucket.GAMMA


def test_scoring_stage_clamps_values():
    articles = [
        make_article("Test", "https://x.com/1", "Feed", content="Some text."),
    ]
    mock_llm = MagicMock()
    mock_llm.chat.return_value = json.dumps([
        {"index": 1, "impact": 15, "novelty": -3, "actionability": 99},
    ])

    ctx = PipelineContext()
    ctx.set("articles", articles)
    stage = ScoringStage(llm_adapter=mock_llm)
    result = stage.process(ctx)

    scored = result.get("scored_articles")
    assert scored[0].impact == 10     # clamped to 10
    assert scored[0].novelty == 1     # clamped to 1
    assert scored[0].actionability == 10  # clamped to 10


def test_scoring_stage_empty_articles():
    ctx = PipelineContext()
    ctx.set("articles", [])

    mock_llm = MagicMock()
    stage = ScoringStage(llm_adapter=mock_llm)
    result = stage.process(ctx)

    assert result.get("scored_articles") == []
    mock_llm.chat.assert_not_called()


def test_scoring_stage_json_fallback():
    articles = [
        make_article("A", "https://x.com/1", "Feed", content="text"),
        make_article("B", "https://x.com/2", "Feed", content="text"),
    ]
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "not json at all, just some text"

    ctx = PipelineContext()
    ctx.set("articles", articles)
    stage = ScoringStage(llm_adapter=mock_llm)
    result = stage.process(ctx)

    scored = result.get("scored_articles")
    assert len(scored) == 2
    # All fall back to neutral (5,5,5), impact=5 → BETA
    for sa in scored:
        assert sa.impact == 5
        assert sa.novelty == 5
        assert sa.actionability == 5
        assert sa.bucket == Bucket.BETA


def test_scoring_stage_parses_code_block():
    articles = [
        make_article("A", "https://x.com/1", "Feed", content="text"),
    ]
    mock_llm = MagicMock()
    mock_llm.chat.return_value = (
        "Here are the scores:\n"
        "```json\n"
        '[{"index": 1, "impact": 7, "novelty": 6, "actionability": 5}]\n'
        "```\n"
        "These scores reflect careful analysis."
    )

    ctx = PipelineContext()
    ctx.set("articles", articles)
    stage = ScoringStage(llm_adapter=mock_llm)
    result = stage.process(ctx)

    scored = result.get("scored_articles")
    assert len(scored) == 1
    assert scored[0].impact == 7
    assert scored[0].novelty == 6
    assert scored[0].actionability == 5
    assert scored[0].bucket == Bucket.BETA  # impact 7 >= 5, but (7>=8=False)


def test_scoring_stage_does_not_mutate_article():
    articles = [
        make_article("Original", "https://x.com/1", "FeedX",
                     content="Full article text here.", summary="RSS summary"),
    ]
    original_score = articles[0].score
    original_content = articles[0].content

    mock_llm = MagicMock()
    mock_llm.chat.return_value = json.dumps([
        {"index": 1, "impact": 8, "novelty": 9, "actionability": 7},
    ])

    ctx = PipelineContext()
    ctx.set("articles", articles)
    stage = ScoringStage(llm_adapter=mock_llm)
    result = stage.process(ctx)

    scored = result.get("scored_articles")
    assert scored[0].article.score == original_score
    assert scored[0].article.content == original_content
    assert scored[0].article is articles[0]


def test_scoring_stage_alpha_boundary():
    """impact=8, novelty=7 is the exact Alpha threshold."""
    assert ScoringStage._assign_bucket(impact=8, novelty=7, actionability=1) == Bucket.ALPHA
    assert ScoringStage._assign_bucket(impact=7, novelty=7, actionability=10) == Bucket.BETA
    assert ScoringStage._assign_bucket(impact=8, novelty=6, actionability=10) == Bucket.BETA
