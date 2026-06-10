"""Tests for L0CaptureStage — config-driven artifact capture."""
import tempfile
from datetime import datetime, timezone

import pytest

from src.stages.artifact_capture import L0CaptureStage, _canonicalize, _infer_artifact_type
from src.pipeline.stage import PipelineContext


class FakeConfig:
    class FakeArtifact:
        def __init__(self, enabled=True, sources=None, output_dir=".", timeout=15,
                     screenshot_enabled=True, media_dir="./media"):
            self.enabled = enabled
            self.sources = sources or []
            self.output_dir = output_dir
            self.timeout = timeout
            self.screenshot_enabled = screenshot_enabled
            self.media_dir = media_dir

    def __init__(self, enabled=True, sources=None):
        self.artifact = self.FakeArtifact(enabled=enabled, sources=sources)


def test_skips_when_disabled():
    stage = L0CaptureStage()
    ctx = PipelineContext()
    ctx.set("config", FakeConfig(enabled=False))
    result = stage.process(ctx)
    assert result.get("artifact_refs") == []
    assert result.get("artifacts") == []


def test_skips_when_no_sources():
    stage = L0CaptureStage()
    ctx = PipelineContext()
    ctx.set("config", FakeConfig(enabled=True, sources=[]))
    result = stage.process(ctx)
    assert result.get("artifact_refs") == []


def test_skips_when_no_config():
    stage = L0CaptureStage()
    ctx = PipelineContext()
    result = stage.process(ctx)
    assert result.get("artifact_refs") == []


def test_canonicalize_strips_fragment():
    assert _canonicalize("https://example.com/page#section") == "https://example.com/page"


def test_canonicalize_strips_trailing_slash():
    assert _canonicalize("https://example.com/page/") == "https://example.com/page"


def test_canonicalize_lowercases_scheme_host():
    assert _canonicalize("HTTPS://Example.COM/Page") == "https://example.com/Page"


def test_canonicalize_preserves_query():
    assert _canonicalize("https://example.com/?q=1") == "https://example.com/?q=1"


def test_infer_arxiv():
    assert _infer_artifact_type("https://arxiv.org/abs/2605.12345") == "research_paper"


def test_infer_github_commit():
    assert _infer_artifact_type("https://github.com/user/repo/commit/abc123") == "github_commit"


def test_infer_tweet():
    assert _infer_artifact_type("https://twitter.com/user/status/12345") == "tweet"
    assert _infer_artifact_type("https://x.com/user/status/12345") == "tweet"


def test_infer_youtube():
    assert _infer_artifact_type("https://youtube.com/watch?v=abc") == "video_transcript"


def test_infer_blog():
    assert _infer_artifact_type("https://medium.com/@user/post") == "blog_post"
    assert _infer_artifact_type("https://blog.example.com/post") == "blog_post"


def test_infer_defaults_to_blog_post():
    assert _infer_artifact_type("https://www.anthropic.com/research") == "research_paper"
    assert _infer_artifact_type("https://openai.com/blog/") == "blog_post"


@pytest.mark.integration  # real network — excluded from default run (pytest.ini)
def test_real_url_capture():
    """Integration: capture a real URL and verify artifact integrity."""
    with tempfile.TemporaryDirectory() as d:
        config = FakeConfig(
            enabled=True,
            sources=["https://www.anthropic.com/research"],
        )
        config.artifact.output_dir = d
        config.artifact.media_dir = d  # keep screenshots out of the repo's media/
        config.artifact.timeout = 20

        stage = L0CaptureStage()
        ctx = PipelineContext()
        ctx.set("config", config)
        dates = {datetime.now(timezone.utc).strftime("%Y%m%d")}
        result = stage.process(ctx)
        dates.add(datetime.now(timezone.utc).strftime("%Y%m%d"))

        refs = result.get("artifact_refs", [])
        artifacts = result.get("artifacts", [])

        assert len(refs) >= 1, f"Expected >=1 artifact, got {refs}"
        assert len(artifacts) >= 1

        a = artifacts[0]
        # Artifact IDs are stamped with the UTC date at capture time —
        # mirror that instead of hardcoding (20260603 broke after that day).
        assert any(a.artifact_id.startswith(f"A-{d}-") for d in dates), a.artifact_id
        assert a.content_hash.startswith("sha256:")
        assert len(a.content_hash) == 71  # "sha256:" + 64 hex chars
        assert len(a.raw_content) > 100
        assert a.source_url == "https://www.anthropic.com/research"
        assert a.retrieved_via in ("playwright", "http", "jina"), f"Bad via: {a.retrieved_via}"


@pytest.mark.integration  # real network — excluded from default run (pytest.ini)
def test_idempotent_skip():
    """Second capture of same URL should reuse existing artifact."""
    with tempfile.TemporaryDirectory() as d:
        config = FakeConfig(
            enabled=True,
            sources=["https://www.anthropic.com/research"],
        )
        config.artifact.output_dir = d
        config.artifact.media_dir = d  # keep screenshots out of the repo's media/
        config.artifact.timeout = 20

        # First run
        ctx1 = PipelineContext()
        ctx1.set("config", config)
        r1 = L0CaptureStage().process(ctx1)

        # Second run
        ctx2 = PipelineContext()
        ctx2.set("config", config)
        r2 = L0CaptureStage().process(ctx2)

        assert r1.get("artifact_refs") == r2.get("artifact_refs")
        assert r1.get("artifacts")[0].artifact_id == r2.get("artifacts")[0].artifact_id
