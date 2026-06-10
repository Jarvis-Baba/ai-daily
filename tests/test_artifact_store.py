"""Tests for artifact_store.py — save/load/idempotency."""
import tempfile
from pathlib import Path
from src.models.artifact import Artifact
from src.adapters.artifact_store import save, load, find_by_url, next_id


def _make_artifact(aid="A-20260603-001", url="https://example.com", title="", canonical_url=None):
    return Artifact(
        artifact_id=aid, artifact_type="blog_post",
        source_url=url, canonical_url=canonical_url or url,
        retrieved_at="2026-06-03T00:00:00Z",
        content_hash="sha256:abc123", raw_content="hello world",
        source_name="example.com", title=title,
    )


def test_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        a = _make_artifact()
        save(a, d)
        loaded = load("A-20260603-001", d)
        assert loaded is not None
        assert loaded.artifact_id == "A-20260603-001"
        assert loaded.artifact_type == "blog_post"
        assert loaded.canonical_url == "https://example.com"
        assert loaded.content_hash == "sha256:abc123"


def test_load_missing_returns_none():
    with tempfile.TemporaryDirectory() as d:
        assert load("A-99999999-999", d) is None


def test_next_id_first():
    with tempfile.TemporaryDirectory() as d:
        assert next_id("20260603", d) == "A-20260603-001"


def test_next_id_increments():
    with tempfile.TemporaryDirectory() as d:
        Path(d).mkdir(parents=True, exist_ok=True)
        (Path(d) / "A-20260603-001.json").write_text("{}")
        (Path(d) / "A-20260603-002.json").write_text("{}")
        assert next_id("20260603", d) == "A-20260603-003"


def test_next_id_different_dates():
    with tempfile.TemporaryDirectory() as d:
        assert next_id("20260603", d) == "A-20260603-001"
        assert next_id("20260604", d) == "A-20260604-001"


def test_next_id_skips_corrupt():
    with tempfile.TemporaryDirectory() as d:
        Path(d).mkdir(parents=True, exist_ok=True)
        (Path(d) / "A-20260603-xxx.json").write_text("{}")  # not parseable as int
        assert next_id("20260603", d) == "A-20260603-001"


def test_find_by_url_match():
    with tempfile.TemporaryDirectory() as d:
        a = _make_artifact(canonical_url="https://example.com/page")
        save(a, d)
        found = find_by_url("20260603", "https://example.com/page", d)
        assert found is not None
        assert found.artifact_id == "A-20260603-001"


def test_find_by_url_no_match():
    with tempfile.TemporaryDirectory() as d:
        a = _make_artifact()
        save(a, d)
        assert find_by_url("20260603", "https://other.com", d) is None


def test_find_by_url_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        assert find_by_url("20260603", "https://example.com", d) is None


def test_find_by_url_different_date_skipped():
    """artifacts from a different date should not match."""
    with tempfile.TemporaryDirectory() as d:
        a = _make_artifact()
        save(a, d)
        assert find_by_url("20260604", "https://example.com", d) is None


def test_save_creates_directory():
    with tempfile.TemporaryDirectory() as base:
        d = str(Path(base) / "nested" / "artifacts")
        a = _make_artifact()
        save(a, d)
        assert Path(d).exists()
        assert load("A-20260603-001", d) is not None
