import pytest
import tempfile
import os


@pytest.fixture
def sample_config_yaml():
    return """
feeds:
  - name: "TestFeed"
    url: "https://example.com/rss"
    enabled: true
  - name: "DisabledFeed"
    url: "https://example.com/disabled"
    enabled: false
fetch:
  timeout: 30
  max_articles_per_feed: 10
retry:
  max_attempts: 3
  backoff_seconds: 1
llm:
  provider: dummy
  model: dummy
  api_key: ""
  base_url: null
filter:
  top_n: 5
  min_score: 6
output:
  dir: "./output"
  filename: "morning-{date}.md"
  template: "# AI Morning Brief — {date}\\n\\n{items}"
"""


@pytest.fixture
def config_file(sample_config_yaml):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(sample_config_yaml)
        path = f.name
    yield path
    os.unlink(path)
