"""Tests for L1EvidenceStage — LLM-based artifact-to-evidence extraction."""
import json
import math
from datetime import datetime, timezone
from unittest.mock import MagicMock
from src.stages.evidence_compiler import (
    L1EvidenceStage, _parse_json, _build_batches, _build_prompt, _clamp,
    _BATCH_SIZE, _BATCH_CHAR_LIMIT,
)
from src.pipeline.stage import PipelineContext
from src.models.artifact import Artifact
from src.models.evidence import (
    Evidence, EvidenceSource, EvidenceConfidence, SupportingMaterial, EvidencePackage,
    FactType, VerificationStatus, SourceType,
    infer_source_type, SOURCE_RELIABILITY_DEFAULTS,
)


def utc_today():
    """Date stamp as the stage generates it (datetime.now(timezone.utc)).
    Capture before AND after the stage call and accept either, so a run
    that crosses UTC midnight still passes — the original hardcoded
    20260603 broke this suite on every later day."""
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def make_artifact(artifact_id="A-20260603-001", source_url="https://example.com/blog",
                  source_name="example.com", artifact_type="blog_post",
                  raw_content="Example content with claims.", title="Test Article"):
    return Artifact(
        artifact_id=artifact_id, artifact_type=artifact_type,
        source_url=source_url, canonical_url=source_url,
        retrieved_at="2026-06-03T00:00:00Z", content_hash="sha256:abc123",
        raw_content=raw_content, source_name=source_name, title=title,
    )


def make_success_response():
    """Return a realistic LLM JSON response for a single artifact."""
    return json.dumps({
        "0": [
            {
                "fact_type": "verifiable_fact",
                "statement": "Company X released Y on 2026-06-03",
                "attribution": "Company X",
                "supporting_quote": "Today we released Y to all customers.",
                "evidence_strength": 0.9,
            },
            {
                "fact_type": "source_statement",
                "statement": "Y achieves 40% improvement over baseline",
                "attribution": "Company X",
                "supporting_quote": "Y improves performance by 40% compared to our previous system.",
                "evidence_strength": 0.6,
            },
            {
                "fact_type": "verifiable_fact",
                "statement": "Y is available in US and EU regions",
                "attribution": "Company X",
                "supporting_quote": "Available today in US and EU.",
                "evidence_strength": 0.85,
            },
        ]
    })


def test_empty_artifacts():
    stage = L1EvidenceStage(llm_adapter=MagicMock())
    ctx = PipelineContext()
    ctx.set("artifacts", [])
    result = stage.process(ctx)
    assert result.get("evidence") == []
    assert result.get("evidence_packages") == []


def test_null_artifacts():
    stage = L1EvidenceStage(llm_adapter=MagicMock())
    ctx = PipelineContext()
    ctx.set("artifacts", None)
    result = stage.process(ctx)
    assert result.get("evidence") == []
    assert result.get("evidence_packages") == []


def test_empty_content_skipped():
    stage = L1EvidenceStage(llm_adapter=MagicMock())
    ctx = PipelineContext()
    ctx.set("artifacts", [make_artifact(raw_content="   \n  ")])
    result = stage.process(ctx)
    assert result.get("evidence") == []


def test_single_artifact_extraction():
    mock_llm = MagicMock()
    mock_llm.chat.return_value = make_success_response()

    stage = L1EvidenceStage(llm_adapter=mock_llm, artifact_base_dir="/tmp/l1-test")
    ctx = PipelineContext()
    ctx.set("artifacts", [make_artifact()])
    result = stage.process(ctx)

    evidence = result.get("evidence", [])
    packages = result.get("evidence_packages", [])

    assert len(evidence) == 3
    assert len(packages) == 1
    assert mock_llm.chat.called


def test_evidence_structure_complete():
    mock_llm = MagicMock()
    mock_llm.chat.return_value = make_success_response()

    stage = L1EvidenceStage(llm_adapter=mock_llm, artifact_base_dir="/tmp/l1-test")
    ctx = PipelineContext()
    ctx.set("artifacts", [make_artifact()])
    dates = {utc_today()}
    result = stage.process(ctx)
    dates.add(utc_today())

    ev = result.get("evidence", [])[0]
    # Required fields
    assert any(ev.evidence_id.startswith(f"E-{d}-") for d in dates), ev.evidence_id
    assert ev.fact_type in ("source_statement", "verifiable_fact")
    assert isinstance(ev.source, EvidenceSource)
    assert ev.source.name
    assert ev.source.type
    assert ev.source.url
    assert ev.statement
    assert ev.attribution
    assert isinstance(ev.supporting_material, SupportingMaterial)
    assert len(ev.supporting_material.artifact_refs) >= 1
    assert isinstance(ev.confidence, EvidenceConfidence)
    assert 0.0 <= ev.confidence.source_reliability <= 1.0
    assert 0.0 <= ev.confidence.evidence_strength <= 1.0
    assert ev.confidence.verification_status == "direct_source"


def test_evidence_id_format():
    mock_llm = MagicMock()
    mock_llm.chat.return_value = make_success_response()

    stage = L1EvidenceStage(llm_adapter=mock_llm, artifact_base_dir="/tmp/l1-test")
    ctx = PipelineContext()
    ctx.set("artifacts", [make_artifact()])
    dates = {utc_today()}
    result = stage.process(ctx)
    dates.add(utc_today())

    for ev in result.get("evidence", []):
        assert any(ev.evidence_id.startswith(f"E-{d}-") for d in dates), ev.evidence_id
        parts = ev.evidence_id.split("-")
        assert len(parts) == 3
        assert int(parts[-1]) >= 1


def test_source_reliability_from_domain():
    # anthropic.com → official_blog → 0.95
    assert infer_source_type("blog_post", "www.anthropic.com") == "official_blog"
    assert SOURCE_RELIABILITY_DEFAULTS["official_blog"] == 0.95

    # arxiv.org → research_paper → 0.85
    assert infer_source_type("research_paper", "arxiv.org") == "research_paper"
    assert SOURCE_RELIABILITY_DEFAULTS["research_paper"] == 0.85

    # techcrunch.com → news_media → 0.65
    assert infer_source_type("blog_post", "techcrunch.com") == "news_media"
    assert SOURCE_RELIABILITY_DEFAULTS["news_media"] == 0.65

    # simonwillison.net → independent_report → 0.70
    assert infer_source_type("blog_post", "simonwillison.net") == "independent_report"
    assert SOURCE_RELIABILITY_DEFAULTS["independent_report"] == 0.70


def test_confidence_clamping():
    mock_llm = MagicMock()
    # LLM returns out-of-range evidence_strength
    mock_llm.chat.return_value = json.dumps({
        "0": [
            {"fact_type": "source_statement", "statement": "Too high",
             "attribution": "Test", "supporting_quote": "x", "evidence_strength": 2.5},
            {"fact_type": "source_statement", "statement": "Too low",
             "attribution": "Test", "supporting_quote": "x", "evidence_strength": -0.5},
        ]
    })

    stage = L1EvidenceStage(llm_adapter=mock_llm, artifact_base_dir="/tmp/l1-test")
    ctx = PipelineContext()
    ctx.set("artifacts", [make_artifact()])
    result = stage.process(ctx)

    evidence = result.get("evidence", [])
    assert len(evidence) == 2
    assert evidence[0].confidence.evidence_strength == 1.0  # clamped
    assert evidence[1].confidence.evidence_strength == 0.0  # clamped


def test_json_fallback_parsing():
    # Code block
    assert "0" in _parse_json('```json\n{"0": []}\n```')
    # Direct
    assert "0" in _parse_json('{"0": []}')
    # Malformed → empty
    assert _parse_json("not json at all") == {}
    # Empty string → empty
    assert _parse_json("") == {}


def test_batch_processing():
    mock_llm = MagicMock()
    mock_llm.chat.return_value = json.dumps({
        "0": [{"fact_type": "verifiable_fact", "statement": "A", "attribution": "X",
               "supporting_quote": "q", "evidence_strength": 0.8}],
        "1": [{"fact_type": "verifiable_fact", "statement": "B", "attribution": "Y",
               "supporting_quote": "q", "evidence_strength": 0.7}],
        "2": [{"fact_type": "verifiable_fact", "statement": "C", "attribution": "Z",
               "supporting_quote": "q", "evidence_strength": 0.9}],
    })

    stage = L1EvidenceStage(llm_adapter=mock_llm, artifact_base_dir="/tmp/l1-test")
    ctx = PipelineContext()
    ctx.set("artifacts", [
        make_artifact("A-001", "https://a.com", "a.com", "blog_post", "Content A"),
        make_artifact("A-002", "https://b.com", "b.com", "blog_post", "Content B"),
        make_artifact("A-003", "https://c.com", "c.com", "blog_post", "Content C"),
    ])
    result = stage.process(ctx)

    evidence = result.get("evidence", [])
    assert len(evidence) == 3
    packages = result.get("evidence_packages", [])
    assert len(packages) == 3


def test_package_building():
    mock_llm = MagicMock()
    mock_llm.chat.return_value = make_success_response()

    stage = L1EvidenceStage(llm_adapter=mock_llm, artifact_base_dir="/tmp/l1-test")
    ctx = PipelineContext()
    ctx.set("artifacts", [make_artifact()])
    dates = {utc_today()}
    result = stage.process(ctx)
    dates.add(utc_today())

    packages = result.get("evidence_packages", [])
    assert len(packages) == 1
    pkg = packages[0]
    assert isinstance(pkg, EvidencePackage)
    assert any(pkg.package_id.startswith(f"PKG-{d}-") for d in dates), pkg.package_id
    assert pkg.topic
    assert len(pkg.artifacts) == 1
    assert pkg.artifacts[0] == "A-20260603-001"
    assert len(pkg.evidence) == 3


def test_fact_type_enum_values():
    assert FactType.SOURCE_STATEMENT == "source_statement"
    assert FactType.VERIFIABLE_FACT == "verifiable_fact"


def test_verification_status_values():
    assert VerificationStatus.DIRECT_SOURCE == "direct_source"
    assert VerificationStatus.CROSS_REFERENCED == "cross_referenced"
    assert VerificationStatus.UNVERIFIED == "unverified"
    assert VerificationStatus.DISPUTED == "disputed"


def test_llm_call_failure_graceful():
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = RuntimeError("API down")

    stage = L1EvidenceStage(llm_adapter=mock_llm, artifact_base_dir="/tmp/l1-test")
    ctx = PipelineContext()
    ctx.set("artifacts", [make_artifact()])
    result = stage.process(ctx)

    # Should not crash, just produce no evidence
    assert result.get("evidence") == []


def test_clamp():
    assert _clamp(0.5) == 0.5
    assert _clamp(2.0) == 1.0
    assert _clamp(-0.5) == 0.0


def test_invalid_fact_type_defaults():
    mock_llm = MagicMock()
    mock_llm.chat.return_value = json.dumps({
        "0": [{"fact_type": "invalid_type", "statement": "x", "attribution": "y",
               "supporting_quote": "z", "evidence_strength": 0.5}]
    })

    stage = L1EvidenceStage(llm_adapter=mock_llm, artifact_base_dir="/tmp/l1-test")
    ctx = PipelineContext()
    ctx.set("artifacts", [make_artifact()])
    result = stage.process(ctx)

    evidence = result.get("evidence", [])
    assert len(evidence) == 1
    assert evidence[0].fact_type == "source_statement"  # defaulted


def test_build_batches():
    artifacts = [make_artifact(f"A-{i:03d}", raw_content="x" * 1000) for i in range(12)]
    batches = _build_batches(artifacts)
    # Expectations derive from the implementation constants instead of a
    # hardcoded split: the original "3 per batch" assumption broke when
    # _BATCH_SIZE was retuned to 1. Invariants first, exact count second.
    flat = [a.artifact_id for b in batches for a in b]
    assert flat == [a.artifact_id for a in artifacts]  # nothing lost/reordered
    assert all(len(b) <= _BATCH_SIZE for b in batches)
    for b in batches:
        if len(b) > 1:
            assert sum(len(a.raw_content) for a in b) <= _BATCH_CHAR_LIMIT
    if _BATCH_SIZE * 1000 <= _BATCH_CHAR_LIMIT:  # char limit non-binding here
        assert len(batches) == math.ceil(len(artifacts) / _BATCH_SIZE)


def test_build_prompt():
    artifacts = [make_artifact("A-001", "https://x.com", "x.com", "blog_post", "Hello world")]
    prompt = _build_prompt(artifacts)
    assert "Source 0" in prompt
    assert "x.com" in prompt
    assert "Hello world" in prompt
    assert "Return a JSON object" in prompt
