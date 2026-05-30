import tempfile
import os
from datetime import date
from src.pipeline.stage import PipelineContext
from src.stages.output import OutputStage
from src.models.article import Brief, BriefItem


def test_output_stage_writes_markdown_file():
    items = [
        BriefItem(title="AI News", source="FeedA", score=9,
                  digest="Researchers achieved breakthrough in reasoning.",
                  link="https://x.com/1"),
        BriefItem(title="Markets", source="FeedB", score=7,
                  digest="Tech stocks rally on AI optimism.",
                  link="https://x.com/2"),
    ]
    brief = Brief(date=date(2026, 5, 30), items=items)

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = PipelineContext()
        ctx.set("brief", brief)
        ctx.set("output_dir", tmpdir)
        ctx.set("output_template", "# AI Morning Brief - {date}\n\n{items}\n\n---\n> {timestamp}")

        stage = OutputStage()
        result = stage.process(ctx)

        output_path = result.get("output_path")
        assert output_path is not None
        assert os.path.exists(output_path)

        content = open(output_path).read()
        assert "AI Morning Brief" in content
        assert "2026-05-30" in content
        assert "AI News" in content
        assert "FeedA" in content


def test_output_stage_creates_output_dir():
    items = [
        BriefItem(title="Test", source="FeedA", score=5, digest="Test digest.", link="https://x.com/1"),
    ]
    brief = Brief(date=date(2026, 5, 30), items=items)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = os.path.join(tmpdir, "nested", "output")
        ctx = PipelineContext()
        ctx.set("brief", brief)
        ctx.set("output_dir", out_dir)
        ctx.set("output_template", "# Brief\n\n{items}")

        stage = OutputStage()
        stage.process(ctx)

        assert os.path.isdir(out_dir)


def test_output_stage_empty_brief():
    brief = Brief(date=date(2026, 5, 30), items=[])

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = PipelineContext()
        ctx.set("brief", brief)
        ctx.set("output_dir", tmpdir)
        ctx.set("output_template", "# Brief\n\n{items}")

        stage = OutputStage()
        result = stage.process(ctx)

        content = open(result.get("output_path")).read()
        # Empty brief should still produce valid markdown
        assert "# Brief" in content
