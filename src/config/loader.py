from dataclasses import dataclass, field
import os
import re
from pathlib import Path
import yaml


@dataclass
class FeedConfig:
    name: str
    url: str
    enabled: bool = True


@dataclass
class FetchConfig:
    timeout: int = 30
    max_articles_per_feed: int = 20


@dataclass
class RetryConfig:
    max_attempts: int = 3
    backoff_seconds: float = 1.0


@dataclass
class LLMConfig:
    provider: str = "dummy"
    model: str = "dummy"
    api_key: str = ""
    base_url: str | None = None


@dataclass
class FilterConfig:
    top_n: int = 10
    min_score: int = 6


@dataclass
class OutputConfig:
    dir: str = "./output"
    filename: str = "morning-{date}.md"
    template: str = "# AI 早报 — {date}\n\n{items}"


@dataclass
class ContentConfig:
    fetch_fulltext: bool = True
    timeout: int = 8
    max_chars: int = 3000


@dataclass
class AppConfig:
    feeds: list[FeedConfig]
    fetch: FetchConfig
    retry: RetryConfig
    llm: LLMConfig
    filter: FilterConfig
    output: OutputConfig
    content: ContentConfig = field(default_factory=ContentConfig)


_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _load_dotenv(dotenv_path: Path) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ. No-op if file doesn't exist."""
    if not dotenv_path.exists():
        return
    with open(dotenv_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:  # don't override existing env
                os.environ[key] = value


def _substitute_env_vars(value: str) -> str:
    def _replace(match):
        var_name = match.group(1)
        return os.environ.get(var_name, "")
    return _ENV_VAR_RE.sub(_replace, value)


def _walk_and_substitute(obj):
    if isinstance(obj, dict):
        return {k: _walk_and_substitute(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_and_substitute(v) for v in obj]
    if isinstance(obj, str):
        return _substitute_env_vars(obj)
    return obj


def load_config(path: str) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    # Load .env file if it exists (before env var substitution)
    _load_dotenv(config_path.parent / ".env")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    raw = _walk_and_substitute(raw)

    feeds = [FeedConfig(**f) for f in raw.get("feeds", [])]
    fetch = FetchConfig(**raw.get("fetch", {}))
    retry = RetryConfig(**raw.get("retry", {}))
    llm = LLMConfig(**raw.get("llm", {}))
    filter_cfg = FilterConfig(**raw.get("filter", {}))
    output = OutputConfig(**raw.get("output", {}))
    content = ContentConfig(**raw.get("content", {}))

    return AppConfig(
        feeds=feeds,
        fetch=fetch,
        retry=retry,
        llm=llm,
        filter=filter_cfg,
        output=output,
        content=content,
    )
