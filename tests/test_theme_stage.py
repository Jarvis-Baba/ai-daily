import json
import os
import tempfile
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from src.pipeline.stage import PipelineContext
from src.stages.theme import ThemeMemory, ThemeStage, ThemeState, SEED_THEMES
from src.models.article import Article
from src.models.scored_article import Bucket, ScoredArticle


def make_scored(title, source, content="", summary="", bucket=Bucket.BETA):
    article = Article(
        title=title, link="https://x.com/1", summary=summary,
        published=date.today(), source=source, content=content,
    )
    return ScoredArticle(
        article=article, impact=7, novelty=6, actionability=5, bucket=bucket,
    )


# ── ThemeMemory tests ──

def test_theme_memory_seeds_on_fresh_start():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, ".theme-memory.json")
        memory = ThemeMemory(path)
        memory.load()

        assert len(memory.themes) == len(SEED_THEMES)
        for tid in SEED_THEMES:
            assert tid in memory.themes
            assert memory.themes[tid].strength == 0.3


def test_theme_memory_save_and_reload():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, ".theme-memory.json")
        memory = ThemeMemory(path)
        memory.load()
        memory.save()

        # Reload
        memory2 = ThemeMemory(path)
        memory2.load()
        assert len(memory2.themes) == len(SEED_THEMES)


def test_theme_memory_match_hit():
    memory = ThemeMemory("/nonexistent/test.json")
    memory.load()  # seeds
    tid, conf = memory.match("Anthropic releases Claude Opus 5 with groundbreaking agent capabilities")
    assert tid == "anthropic_scaling"
    assert conf > 0.4  # "anthropic", "claude", "opus" match → 3/4 = 0.75


def test_theme_memory_match_miss():
    memory = ThemeMemory("/nonexistent/test.json")
    memory.load()
    tid, conf = memory.match("The weather is nice today in San Francisco")
    assert tid is None
    assert conf == 0.0


def test_theme_memory_match_below_threshold():
    memory = ThemeMemory("/nonexistent/test.json")
    memory.load()
    # Only "anthropic" matches → 1/4 = 0.25, still above 0.15
    tid, conf = memory.match("Anthropic is a company")
    assert tid == "anthropic_scaling"
    assert conf == 0.25


def test_theme_memory_match_best_wins():
    memory = ThemeMemory("/nonexistent/test.json")
    memory.load()
    # Both anthropic and agent keywords present, anthropic should have higher confidence
    tid, conf = memory.match(
        "Anthropic releases Claude with new MCP agent tool use capabilities"
    )
    # anthropic_scaling: anthropic+claude = 2/4 = 0.5
    # agent_stack: agent+mcp+"tool use" = 3/5 = 0.6
    assert tid == "agent_stack"


def test_theme_memory_trajectory_new():
    memory = ThemeMemory("/nonexistent/test.json")
    memory.load()
    # A theme that just got seeded with no history
    ts = memory.themes["anthropic_scaling"]
    ts.first_seen = ""
    ts.last_seen = ""
    ts.consecutive_days = 0
    assert memory.trajectory("anthropic_scaling") == "DECAY"


def test_theme_memory_trajectory_accelerate():
    memory = ThemeMemory("/nonexistent/test.json")
    memory.load()
    ts = memory.themes["anthropic_scaling"]
    ts.consecutive_days = 3
    ts.last_seen = str(date.today())
    assert memory.trajectory("anthropic_scaling") == "ACCELERATE"


def test_theme_memory_trajectory_continue():
    memory = ThemeMemory("/nonexistent/test.json")
    memory.load()
    ts = memory.themes["anthropic_scaling"]
    ts.consecutive_days = 1
    ts.last_seen = str(date.today())
    assert memory.trajectory("anthropic_scaling") == "CONTINUE"


def test_theme_memory_trajectory_decay():
    memory = ThemeMemory("/nonexistent/test.json")
    memory.load()
    ts = memory.themes["anthropic_scaling"]
    ts.consecutive_days = 0
    ts.last_seen = str(date.today() - timedelta(days=3))
    assert memory.trajectory("anthropic_scaling") == "DECAY"


def test_theme_memory_update_all_seen():
    memory = ThemeMemory("/nonexistent/test.json")
    memory.load()
    ts = memory.themes["anthropic_scaling"]
    original_strength = ts.strength

    memory.update_all({"anthropic_scaling"})

    assert ts.strength > original_strength
    assert ts.last_seen == str(date.today())
    assert ts.consecutive_days >= 1


def test_theme_memory_update_all_unseen():
    memory = ThemeMemory("/nonexistent/test.json")
    memory.load()
    ts = memory.themes["anthropic_scaling"]
    ts.last_seen = str(date.today() - timedelta(days=3))
    ts.consecutive_days = 2
    original_strength = ts.strength

    memory.update_all(set())  # nothing seen

    assert ts.strength < original_strength
    assert ts.consecutive_days == 0


# ── ThemeStage tests ──

def test_theme_stage_tags_articles():
    scored = [
        make_scored("Anthropic raises $10B for Claude Opus", "FeedA",
                    content="Anthropic announced a massive funding round for Claude Opus development."),
        make_scored("New GPU from NVIDIA breaks records", "FeedB",
                    content="NVIDIA's latest GPU doubles inference performance for large models."),
        make_scored("Random tech news", "FeedC",
                    content="Some unrelated technology news."),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, ".theme-memory.json")
        # Pre-seed memory so we control state
        memory = ThemeMemory(path)
        memory.load()
        memory.save()

        ctx = PipelineContext()
        ctx.set("scored_articles", scored)

        stage = ThemeStage(memory_path=path)
        result = stage.process(ctx)

        tagged = result.get("scored_articles")
        assert len(tagged) == 3

        # First article should match anthropic
        assert tagged[0].theme_id == "anthropic_scaling"
        # keywords: ["anthropic", "claude", "opus", "sonnet"]
        # "Anthropic raises $10B for Claude Opus" → anthropic ✓, claude ✓, opus ✓ = 3/4 = 0.75
        assert tagged[0].theme_confidence == 0.75

        # Second article should match hardware
        assert tagged[1].theme_id == "ai_hardware"
        # "New GPU from NVIDIA breaks records" + "NVIDIA's latest GPU..." → gpu ✓, nvidia ✓ = 2/6 = 0.33
        assert tagged[1].theme_confidence > 0.3

        # Third article shouldn't match anything
        assert tagged[2].theme_id is None
        assert tagged[2].theme_confidence == 0.0


def test_theme_stage_empty_articles():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, ".theme-memory.json")
        ctx = PipelineContext()
        ctx.set("scored_articles", [])

        stage = ThemeStage(memory_path=path)
        result = stage.process(ctx)

        assert result.get("scored_articles") == []


def test_theme_stage_trajectory_assignment():
    scored = [
        make_scored("Anthropic Claude continues to grow", "FeedA",
                    content="Anthropic's Claude is seeing massive adoption."),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, ".theme-memory.json")
        memory = ThemeMemory(path)
        memory.load()
        # Simulate the theme has been seen for 3 consecutive days
        ts = memory.themes["anthropic_scaling"]
        ts.consecutive_days = 3
        ts.last_seen = str(date.today())
        memory.save()

        ctx = PipelineContext()
        ctx.set("scored_articles", scored)

        stage = ThemeStage(memory_path=path)
        result = stage.process(ctx)

        tagged = result.get("scored_articles")
        assert tagged[0].theme_id == "anthropic_scaling"
        assert tagged[0].trajectory == "ACCELERATE"


def test_theme_stage_persists_memory():
    scored = [
        make_scored("OpenAI launches GPT-6 with Codex integration", "FeedA",
                    content="OpenAI's latest model includes Codex and Operator for agentic tasks."),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, ".theme-memory.json")
        ctx = PipelineContext()
        ctx.set("scored_articles", scored)

        stage = ThemeStage(memory_path=path)
        stage.process(ctx)

        # Memory should be persisted
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert "openai_evolution" in data["themes"]
        ts = data["themes"]["openai_evolution"]
        assert ts["last_seen"] == str(date.today())
        assert ts["strength"] > 0.3  # was boosted


def test_theme_stage_does_not_mutate_article():
    scored = [
        make_scored("Anthropic news", "FeedA", content="Anthropic releases Claude."),
    ]
    original_score = scored[0].article.score
    original_content = scored[0].article.content

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, ".theme-memory.json")
        ctx = PipelineContext()
        ctx.set("scored_articles", scored)

        stage = ThemeStage(memory_path=path)
        result = stage.process(ctx)

        tagged = result.get("scored_articles")
        assert tagged[0].article.score == original_score
        assert tagged[0].article.content == original_content
