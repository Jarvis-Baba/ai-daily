import json
from unittest.mock import MagicMock, patch

from src.adapters.github_search import GitHubSearchAdapter
from src.adapters.meta_ai_blog import MetaAIBlogAdapter
from src.adapters.reddit_json import RedditJsonAdapter
from src.adapters.blog_scraper import CompositeFeedAdapter


def _mock_response(payload: str):
    resp = MagicMock()
    resp.read.return_value = payload.encode("utf-8")
    resp.__enter__.return_value = resp
    return resp


def test_reddit_json_adapter_smoke_parses_listing():
    payload = {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "New ML paper discussion",
                        "permalink": "/r/MachineLearning/comments/abc/new_ml_paper/",
                        "created_utc": 1780000000,
                        "score": 123,
                        "num_comments": 45,
                        "selftext": "Interesting result.",
                        "url": "https://arxiv.org/abs/1234.5678",
                    }
                }
            ]
        }
    }

    with patch("urllib.request.urlopen", return_value=_mock_response(json.dumps(payload))):
        articles = RedditJsonAdapter().fetch("MachineLearning top week", "Reddit r/ML", 5)

    assert len(articles) == 1
    assert articles[0].title == "New ML paper discussion"
    assert articles[0].link == "https://www.reddit.com/r/MachineLearning/comments/abc/new_ml_paper/"
    assert "score=123" in articles[0].summary
    assert "External: https://arxiv.org/abs/1234.5678" in articles[0].summary


def test_github_search_adapter_smoke_parses_repositories():
    payload = {
        "items": [
            {
                "full_name": "owner/ai-project",
                "html_url": "https://github.com/owner/ai-project",
                "description": "AI project",
                "stargazers_count": 1200,
                "forks_count": 80,
                "language": "Python",
                "pushed_at": "2026-05-31T08:00:00Z",
            }
        ]
    }

    with patch("urllib.request.urlopen", return_value=_mock_response(json.dumps(payload))):
        articles = GitHubSearchAdapter().fetch("stars:>100 topic:llm", "GitHub AI Search", 5)

    assert len(articles) == 1
    assert articles[0].title == "owner/ai-project"
    assert articles[0].link == "https://github.com/owner/ai-project"
    assert "stars=1200" in articles[0].summary
    assert "language=Python" in articles[0].summary


def test_meta_ai_blog_adapter_smoke_parses_sitemap():
    sitemap = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://ai.meta.com/blog/frontier-ai-research/</loc>
    <lastmod>2026-05-30T00:00:00Z</lastmod>
  </url>
  <url>
    <loc>https://ai.meta.com/blog/</loc>
    <lastmod>2026-05-29T00:00:00Z</lastmod>
  </url>
</urlset>
"""

    with patch("urllib.request.urlopen", return_value=_mock_response(sitemap)):
        articles = MetaAIBlogAdapter().fetch("https://ai.meta.com/blog/", "Meta AI Blog", 5)

    assert len(articles) == 1
    assert articles[0].title == "Frontier Ai Research"
    assert articles[0].link == "https://ai.meta.com/blog/frontier-ai-research/"


def test_composite_adapter_dispatches_hard_sources():
    class DummyRss:
        def fetch(self, url, source_name, max_articles=None):
            return []

    composite = CompositeFeedAdapter(DummyRss())
    with patch("src.adapters.reddit_json.RedditJsonAdapter.fetch", return_value=["reddit"]) as reddit, \
         patch("src.adapters.github_search.GitHubSearchAdapter.fetch", return_value=["github"]) as github, \
         patch("src.adapters.meta_ai_blog.MetaAIBlogAdapter.fetch", return_value=["meta"]) as meta:
        assert composite.fetch("MachineLearning top week", "Reddit", 1, feed_type="reddit_json") == ["reddit"]
        assert composite.fetch("stars:>100", "GitHub", 1, feed_type="github_search") == ["github"]
        assert composite.fetch("https://ai.meta.com/blog/", "Meta", 1, feed_type="meta_ai_blog") == ["meta"]

    reddit.assert_called_once()
    github.assert_called_once()
    meta.assert_called_once()
