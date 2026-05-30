import os
import pytest
from src.config.loader import load_config, AppConfig, FeedConfig


def test_load_config_parses_feeds(config_file):
    cfg = load_config(config_file)
    assert len(cfg.feeds) == 2
    assert cfg.feeds[0].name == "TestFeed"
    assert cfg.feeds[0].enabled is True
    assert cfg.feeds[1].enabled is False


def test_load_config_parses_fetch(config_file):
    cfg = load_config(config_file)
    assert cfg.fetch.timeout == 30
    assert cfg.fetch.max_articles_per_feed == 10


def test_load_config_parses_llm(config_file):
    cfg = load_config(config_file)
    assert cfg.llm.provider == "deepseek"
    assert cfg.llm.model == "deepseek-chat"


def test_load_config_parses_filter(config_file):
    cfg = load_config(config_file)
    assert cfg.filter.top_n == 5
    assert cfg.filter.min_score == 6


def test_load_config_parses_output(config_file):
    cfg = load_config(config_file)
    assert cfg.output.dir == "./output"
    assert cfg.output.filename == "morning-{date}.md"
    assert "{date}" in cfg.output.template


def test_env_var_substitution(config_file):
    os.environ["TEST_KEY"] = "sk-test-12345"
    # Re-write config file with env var reference
    import tempfile
    yaml_content = """
feeds: []
fetch:
  timeout: 30
  max_articles_per_feed: 20
llm:
  provider: openai
  model: gpt-4o-mini
  api_key: ${TEST_KEY}
  base_url: null
filter:
  top_n: 10
  min_score: 6
output:
  dir: "./out"
  filename: "test.md"
  template: "test"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        tmp_path = f.name
    try:
        cfg = load_config(tmp_path)
        assert cfg.llm.api_key == "sk-test-12345"
    finally:
        os.unlink(tmp_path)


def test_missing_config_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.yaml")
