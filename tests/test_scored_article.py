from datetime import datetime
from src.models.article import Article
from src.models.scored_article import Bucket, ScoredArticle


def test_bucket_enum_values():
    assert Bucket.ALPHA == "ALPHA"
    assert Bucket.BETA == "BETA"
    assert Bucket.GAMMA == "GAMMA"
    assert len(Bucket) == 3


def test_bucket_is_string_compatible():
    assert isinstance(Bucket.ALPHA, str)
    assert Bucket.ALPHA == "ALPHA"


def test_scored_article_creation():
    article = Article(
        title="Test",
        link="https://x.com/1",
        summary="summary",
        published=datetime(2026, 5, 30),
        source="FeedX",
    )
    sa = ScoredArticle(
        article=article,
        impact=9,
        novelty=7,
        actionability=8,
        bucket=Bucket.ALPHA,
    )
    assert sa.article is article
    assert sa.impact == 9
    assert sa.novelty == 7
    assert sa.actionability == 8
    assert sa.bucket == Bucket.ALPHA


def test_total_score_formula():
    article = Article(
        title="T",
        link="https://x.com/2",
        summary="s",
        published=datetime(2026, 5, 30),
        source="X",
    )
    # 0.5×9 + 0.3×7 + 0.2×8 = 4.5 + 2.1 + 1.6 = 8.2
    sa = ScoredArticle(
        article=article,
        impact=9,
        novelty=7,
        actionability=8,
        bucket=Bucket.BETA,
    )
    assert sa.total_score == 8.2


def test_total_score_minimum():
    article = Article(
        title="T",
        link="https://x.com/3",
        summary="s",
        published=datetime(2026, 5, 30),
        source="X",
    )
    sa = ScoredArticle(
        article=article,
        impact=1,
        novelty=1,
        actionability=1,
        bucket=Bucket.GAMMA,
    )
    assert sa.total_score == 1.0  # 0.5+0.3+0.2


def test_total_score_maximum():
    article = Article(
        title="T",
        link="https://x.com/4",
        summary="s",
        published=datetime(2026, 5, 30),
        source="X",
    )
    sa = ScoredArticle(
        article=article,
        impact=10,
        novelty=10,
        actionability=10,
        bucket=Bucket.ALPHA,
    )
    assert sa.total_score == 10.0


def test_article_content_accessible_through_wrapper():
    article = Article(
        title="Full Story",
        link="https://x.com/5",
        summary="Brief",
        published=datetime(2026, 5, 30),
        source="FeedY",
    )
    article.content = "Full text here."
    sa = ScoredArticle(
        article=article,
        impact=6,
        novelty=5,
        actionability=4,
        bucket=Bucket.GAMMA,
    )
    assert sa.article.content == "Full text here."
    assert sa.article.id == article.id


def test_scored_article_does_not_mutate_article():
    article = Article(
        title="Original",
        link="https://x.com/6",
        summary="s",
        published=datetime(2026, 5, 30),
        source="X",
    )
    original_score = article.score
    ScoredArticle(
        article=article,
        impact=8,
        novelty=8,
        actionability=8,
        bucket=Bucket.ALPHA,
    )
    # Article.score remains untouched
    assert article.score == original_score
    assert article.score == 0
