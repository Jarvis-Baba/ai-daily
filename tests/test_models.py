from datetime import datetime, date
from src.models.article import RawArticle, Article, BriefItem, Brief


def test_raw_article_creation():
    a = RawArticle(
        title="Test Title",
        link="https://example.com/article",
        summary="A test summary",
        published=datetime(2026, 5, 30, 8, 0),
        source="TestFeed",
    )
    assert a.title == "Test Title"
    assert a.link == "https://example.com/article"


def test_article_id_is_link_hash():
    a1 = Article(
        title="A",
        link="https://x.com/1",
        summary="s",
        published=datetime(2026, 5, 30),
        source="X",
    )
    a2 = Article(
        title="B",
        link="https://x.com/2",
        summary="s",
        published=datetime(2026, 5, 30),
        source="Y",
    )
    assert a1.id != a2.id
    assert len(a1.id) == 64  # sha256 hex digest
    assert a1.score == 0


def test_article_id_deterministic():
    a = Article(
        title="A",
        link="https://x.com/1",
        summary="s",
        published=datetime(2026, 5, 30),
        source="X",
    )
    b = Article(
        title="A",
        link="https://x.com/1",
        summary="s",
        published=datetime(2026, 5, 30),
        source="X",
    )
    assert a.id == b.id


def test_brief_item_creation():
    item = BriefItem(
        title="Article A",
        source="FeedX",
        score=8,
        digest="Important news about AI.",
        link="https://x.com/1",
    )
    assert item.score == 8


def test_brief_creation():
    items = [
        BriefItem(title="A", source="X", score=8, digest="d1", link="https://x.com/1"),
        BriefItem(title="B", source="Y", score=7, digest="d2", link="https://y.com/2"),
    ]
    brief = Brief(date=date(2026, 5, 30), items=items)
    assert brief.date == date(2026, 5, 30)
    assert len(brief.items) == 2
