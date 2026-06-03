"""Stage 1: L1 Evidence Compiler v0.1. Snapshot-driven, not drift-calibrated.

Reads ctx["artifacts"] from L0, batches them for LLM processing, extracts
structured Evidence objects per EVIDENCE-ABI-v1 §3, and groups into
EvidencePackages per §4. Writes ctx["evidence"] and ctx["evidence_packages"].

System assigns source_reliability (deterministic by domain).
LLM assigns evidence_strength (0.0-1.0).
v0.1: all verification_status = "direct_source".
"""

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone

from src.pipeline.stage import PipelineContext
from src.models.artifact import Artifact
from src.models.evidence import (
    Evidence, EvidenceSource, EvidenceConfidence, SupportingMaterial, EvidencePackage,
    FactType, VerificationStatus,
    infer_source_type, SOURCE_RELIABILITY_DEFAULTS,
)
from src.adapters.evidence_store import (
    save_evidence, save_package, next_evidence_id, next_package_id,
)
from src.adapters.calibration_store import get_reliability

logger = logging.getLogger(__name__)

_MAX_CONTENT_CHARS = 8_000
_BATCH_SIZE = 1
_BATCH_CHAR_LIMIT = 30_000

# ── P2: Granularity gate ──
_MIN_STATEMENT_LENGTH = 60  # chars; below this, require specific attribution


def _has_attribution(attribution: str, source_name: str) -> bool:
    """True if attribution is a specific entity distinct from the source name."""
    if not attribution or not attribution.strip():
        return False
    attr = attribution.strip().lower()
    src = source_name.strip().lower()
    if attr == src:
        return False
    if src in attr or attr in src:
        return False
    return True


def _deduplicate_evidence(evidence_list: list[Evidence]) -> list[Evidence]:
    """P1: Drop near-duplicate statements from same source (>70% word overlap).

    Keeps the evidence with higher evidence_strength. If equal, keeps first.
    """
    by_source: dict[str, list[Evidence]] = defaultdict(list)
    for ev in evidence_list:
        by_source[ev.source.name.lower()].append(ev)

    kept: list[Evidence] = []
    dropped = 0
    for source_name, evs in by_source.items():
        # Sort by strength desc so higher-strength items are kept first
        evs_sorted = sorted(evs, key=lambda e: e.confidence.evidence_strength, reverse=True)
        source_kept: list[Evidence] = []
        for ev in evs_sorted:
            ev_words = set(ev.statement.lower().split())
            if not ev_words:
                source_kept.append(ev)
                continue
            is_dup = False
            for kept_ev in source_kept:
                kept_words = set(kept_ev.statement.lower().split())
                if not kept_words:
                    continue
                overlap = len(ev_words & kept_words) / min(len(ev_words), len(kept_words))
                if overlap > 0.7:
                    is_dup = True
                    break
            if is_dup:
                dropped += 1
            else:
                source_kept.append(ev)
        kept.extend(source_kept)
    if dropped:
        logger.info("L1EvidenceStage: dedup dropped %d near-duplicate statements", dropped)
    return kept

_SYSTEM_PROMPT = """You are a fact extraction engine. Your job: read source content and extract atomic, verifiable claims.

Each claim must be:
- Atomic: exactly one assertion
- Attributed: you know WHO is making the claim
- Self-contained: understandable without original context

You MUST NOT: include analysis, opinions, importance judgments, predictions, or combine multiple claims.

For arXiv papers: focus on claims from the abstract. Claims about methodology/results are "source_statement" (unverified). Publication metadata is "verifiable_fact".

For official blogs: product launches and release dates are "verifiable_fact". Performance claims are "source_statement".

For tech media: relayed claims from third parties are "source_statement" with attribution to the original source.

fact_type values:
- "verifiable_fact": objectively verifiable (dates, version numbers, URLs, publication facts)
- "source_statement": claims made by the source (results, interpretations, assertions)

evidence_strength guidelines:
- 0.7-0.9: Specific quantitative results, benchmarks, dates
- 0.5-0.7: Technical claims about methods/architectures
- 0.3-0.5: Interpretations, significance claims
- 0.1-0.3: Speculation, future predictions

supporting_quote: a verbatim excerpt from the content that supports this claim. Keep under 500 chars.

Extract 3-15 claims per source. Fewer for low-density content. Never fabricate."""

_JSON_RE = re.compile(r"\{[\s\S]*\}")

def _repair_truncated_json(raw: str) -> str:
    """Close unclosed brackets in truncated JSON from max_tokens cutoff."""
    # Count open brackets
    open_braces = raw.count("{") - raw.count("}")
    open_brackets = raw.count("[") - raw.count("]")
    if open_braces <= 0 and open_brackets <= 0:
        return ""  # not truncated
    # Drop trailing incomplete fragment (anything after last complete , or " or ] or })
    cut = max(
        raw.rfind(',\n'),
        raw.rfind('",'),
        raw.rfind('],'),
        raw.rfind('}\n'),
    )
    if cut > 0:
        raw = raw[:cut]
    # Close brackets
    repair = raw + "\n" + "  ]" * open_brackets + "\n" + "}" * open_braces
    return repair


def _parse_json(response: str) -> dict:
    """Three-tier JSON parsing + truncated repair. Returns parsed dict or empty dict."""
    text = response.strip()

    # Tier 1: direct
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Tier 2: extract from ```json ``` block
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Tier 3: regex extract outermost { }, with truncation repair
    match = _JSON_RE.search(text)
    if match:
        raw = match.group()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # Truncation repair: try closing the last unclosed array/object
        repaired = _repair_truncated_json(raw)
        if repaired:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass

    return {}


def _build_batches(artifacts: list[Artifact]) -> list[list[Artifact]]:
    batches: list[list[Artifact]] = []
    current: list[Artifact] = []
    current_chars = 0
    for a in artifacts:
        content = a.raw_content[:_MAX_CONTENT_CHARS]
        if len(current) >= _BATCH_SIZE or (current and current_chars + len(content) > _BATCH_CHAR_LIMIT):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(a)
        current_chars += len(content)
    if current:
        batches.append(current)
    return batches


def _build_prompt(batch: list[Artifact]) -> str:
    parts = []
    for i, art in enumerate(batch):
        src_type = infer_source_type(art.artifact_type, art.source_name)
        parts.append(
            f"Source {i}:\n"
            f"  Name: {art.source_name}\n"
            f"  Type: {src_type}\n"
            f"  URL: {art.source_url}\n"
            f"  Published: {art.published_at or 'unknown'}\n"
            f"  Content:\n{art.raw_content[:_MAX_CONTENT_CHARS]}\n"
        )
    parts.append(
        'Return a JSON object keyed by source index. Each value is a list of evidence objects:\n'
        '{"0": [{"fact_type": "...", "statement": "...", "attribution": "...", "supporting_quote": "...", "evidence_strength": 0.85}], ...}\n'
        'Return ONLY the JSON object. No markdown, no explanation.'
    )
    return "\n---\n".join(parts)


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


class L1EvidenceStage:
    """Stage 1: L1 Evidence Compiler v0.1.

    Extracts structured Evidence from Artifacts using LLM, per EVIDENCE-ABI-v1.
    """

    def __init__(self, llm_adapter, artifact_base_dir: str | None = None):
        self._llm = llm_adapter
        self._artifact_base_dir = artifact_base_dir

    def process(self, ctx: PipelineContext) -> PipelineContext:
        artifacts: list[Artifact] = ctx.get("artifacts", []) or []
        if not artifacts:
            logger.info("L1EvidenceStage: no artifacts, skipping")
            ctx.set("evidence", [])
            ctx.set("evidence_packages", [])
            return ctx

        config = ctx.get("config")
        base_dir = (
            self._artifact_base_dir
            or (getattr(getattr(config, "artifact", None), "output_dir", None) if config else None)
            or "./output/artifacts"
        )
        today_str = datetime.now(timezone.utc).strftime("%Y%m%d")

        # Filter out artifacts with empty content
        valid = [a for a in artifacts if a.raw_content.strip()]
        if not valid:
            logger.info("L1EvidenceStage: all artifacts have empty content, skipping")
            ctx.set("evidence", [])
            ctx.set("evidence_packages", [])
            return ctx

        batches = _build_batches(valid)
        logger.info("L1EvidenceStage: %d artifacts in %d batches", len(valid), len(batches))

        all_evidence: list[Evidence] = []
        total_extracted = 0
        granularity_drops = 0
        dedup_drops = 0

        for batch_idx, batch in enumerate(batches):
            prompt = _build_prompt(batch)
            try:
                response = self._llm.chat([
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ])
                parsed = _parse_json(response)
            except Exception as exc:
                logger.warning("L1EvidenceStage: LLM call failed for batch %d: %s", batch_idx, exc)
                continue

            if not parsed:
                logger.warning("L1EvidenceStage: empty parse for batch %d", batch_idx)
                continue

            batch_count = 0
            for i, art in enumerate(batch):
                claims = parsed.get(str(i), [])
                if not isinstance(claims, list):
                    continue
                source_type = infer_source_type(art.artifact_type, art.source_name)
                static_reliability = SOURCE_RELIABILITY_DEFAULTS.get(source_type, 0.50)
                source_reliability = get_reliability(art.source_name, static_reliability, base_dir)

                for claim in claims:
                    if not isinstance(claim, dict):
                        continue
                    statement = claim.get("statement", "").strip()
                    if not statement:
                        continue

                    # P2: granularity gate — drop fragments without specific attribution
                    attribution = claim.get("attribution", art.source_name)
                    if len(statement) < _MIN_STATEMENT_LENGTH and not _has_attribution(attribution, art.source_name):
                        granularity_drops += 1
                        continue

                    evidence_strength = _clamp(float(claim.get("evidence_strength", 0.5)))
                    fact_type = claim.get("fact_type", "source_statement")
                    if fact_type not in ("source_statement", "verifiable_fact"):
                        fact_type = "source_statement"

                    eid = next_evidence_id(today_str, base_dir)
                    source = EvidenceSource(
                        name=art.source_name,
                        type=source_type,
                        url=art.source_url,
                        published_at=art.published_at or "",
                    )
                    confidence = EvidenceConfidence(
                        source_reliability=source_reliability,
                        evidence_strength=evidence_strength,
                        verification_status=VerificationStatus.DIRECT_SOURCE.value,
                    )
                    supporting = SupportingMaterial(
                        quote=claim.get("supporting_quote", "")[:500],
                        artifact_refs=[art.artifact_id],
                        screenshot_refs=list(art.screenshot_refs),
                    )
                    evidence = Evidence(
                        evidence_id=eid,
                        fact_type=fact_type,
                        source=source,
                        statement=statement,
                        attribution=attribution,
                        supporting_material=supporting,
                        confidence=confidence,
                    )
                    save_evidence(evidence, base_dir)
                    all_evidence.append(evidence)
                    batch_count += 1

            total_extracted += batch_count
            logger.info("L1EvidenceStage: batch %d/%d: %d evidence extracted",
                        batch_idx + 1, len(batches), batch_count)

        # ── P2 log ──
        if granularity_drops:
            logger.info("L1EvidenceStage: granularity gate dropped %d fragments", granularity_drops)

        # ── P1: dedup before packaging ──
        before_dedup = len(all_evidence)
        all_evidence = _deduplicate_evidence(all_evidence)
        dedup_drops = before_dedup - len(all_evidence)

        # ── Build packages (one per artifact) ──
        evidence_by_artifact: dict[str, list[Evidence]] = defaultdict(list)
        for ev in all_evidence:
            for ref in ev.supporting_material.artifact_refs:
                evidence_by_artifact[ref].append(ev)

        packages: list[EvidencePackage] = []
        for art in valid:
            ev_list = evidence_by_artifact.get(art.artifact_id, [])
            if not ev_list:
                continue
            pkg = EvidencePackage(
                package_id=next_package_id(today_str, base_dir),
                topic=art.title or art.source_name,
                generated_at=datetime.now(timezone.utc).isoformat(),
                artifacts=[art.artifact_id],
                evidence=ev_list,
            )
            save_package(pkg, base_dir)
            packages.append(pkg)

        ctx.set("evidence", all_evidence)
        ctx.set("evidence_packages", packages)
        logger.info("L1EvidenceStage: %d evidence (+%d granularity drops +%d dedup drops), %d packages from %d artifacts",
                    total_extracted, granularity_drops, dedup_drops, len(packages), len(valid))
        return ctx
