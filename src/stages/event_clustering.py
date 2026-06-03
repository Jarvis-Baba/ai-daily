"""Stage 1.5: Event Pre-Assembler — groups Evidence into proto-events via clustering.

Jaccard similarity on word sets + entity overlap bonus groups semantically
related claims. Each cluster becomes a candidate event hypothesis for L2 synthesis.

Purpose: fix the "many-to-one missing" gap. The Event Compiler (L2) currently acts
as a filter (1-2 evidence → 1 event). This stage adds latent grouping so L2 can
operate as a set-to-event compressor instead.

Deterministic — no embedding dependency, no API calls.
"""

import logging
import math
from collections import defaultdict

from src.pipeline.stage import PipelineContext
from src.models.evidence import Evidence

logger = logging.getLogger(__name__)

# ── Tuning constants ──
_CLUSTER_THRESHOLD = 0.28   # Jaccard+entity composite score threshold
_MIN_CLUSTER_SIZE = 2        # fewer evidence → remains an orphan
_MAX_CLUSTER_SIZE = 6        # prevent topic collapse into mega-clusters
_ENTITY_WEIGHT = 0.3         # weight for entity overlap in composite score
_JACCARD_WEIGHT = 0.7        # weight for word Jaccard in composite score

# ── Layer 2: TF-IDF second-pass (orphan absorption) ──
_TFIDF_ABSORB_THRESHOLD = 0.15   # cosine threshold: orphan → existing cluster
_TFIDF_NEW_CLUSTER_THRESHOLD = 0.25  # cosine threshold: orphan → new cluster
_MAX_ABSORB_PER_CLUSTER = 2      # max orphans to absorb into any single cluster
_NEW_CLUSTER_MIN_SIZE = 2        # min orphans for a new second-pass cluster
_N_GRAMS = (1, 2)                # use unigrams + bigrams for TF-IDF

# ── Entity lexicon (ORG / PRODUCT / MODEL names relevant to AI domain) ──
_ENTITIES = {
    # Organizations
    "openai", "anthropic", "google", "meta", "microsoft", "github",
    "deepseek", "apple", "amazon", "mistral", "hugging", "nvidia",
    # Products
    "chatgpt", "gpt-4", "gpt-5", "codex", "copilot", "claude",
    "gemini", "llama", "dall-e", "midjourney", "cursor", "copilot+",
    # Model families
    "gpt", "gemma", "qwen", "deepseek-r1", "deepseek-v3", "o3",
    "o4", "sonnet", "opus", "haiku",
}


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokenization, dropping short tokens."""
    return {w.strip(",.!?;:()[]{}\"'") for w in text.lower().split() if len(w) > 2}


def _extract_entities(tokens: set[str]) -> set[str]:
    """Extract known entities from a token set (also catches multi-word via joined check)."""
    return tokens & _ENTITIES


def _entity_overlap_score(tokens_a: set[str], tokens_b: set[str]) -> float:
    """Fraction of entities shared between two token sets."""
    ents_a = _extract_entities(tokens_a)
    ents_b = _extract_entities(tokens_b)
    if not ents_a and not ents_b:
        return 0.0
    union = ents_a | ents_b
    if not union:
        return 0.0
    return len(ents_a & ents_b) / len(union)


def _cluster_score(tokens_a: set[str], tokens_b: set[str]) -> float:
    """Composite similarity: 0.7 * Jaccard + 0.3 * entity overlap."""
    if not tokens_a or not tokens_b:
        return 0.0
    jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
    entity = _entity_overlap_score(tokens_a, tokens_b)
    return _JACCARD_WEIGHT * jaccard + _ENTITY_WEIGHT * entity


# ── Layer 2: TF-IDF semantic second-pass ──

def _ngrams(tokens: list[str], n: int) -> set[str]:
    """Generate n-grams from a token sequence."""
    return {" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def _tokenize_ordered(text: str) -> list[str]:
    """Tokenize preserving order (for n-gram generation)."""
    return [w.strip(",.!?;:()[]{}\"'") for w in text.lower().split() if len(w) > 2]


def _build_tfidf_vectors(statements: list[str]) -> list[dict[str, float]]:
    """Compute TF-IDF vectors for a list of statements.

    Uses unigram+bigram features, sublinear TF scaling (log), standard IDF.
    Returns list of {term: tfidf} sparse vectors.
    """
    # Tokenize all documents
    all_terms: list[set[str]] = []
    all_tf: list[dict[str, float]] = []
    doc_count = len(statements)

    for stmt in statements:
        tokens = _tokenize_ordered(stmt)
        terms = set()
        for n in _N_GRAMS:
            terms.update(_ngrams(tokens, n))
        all_terms.append(terms)

        # Raw TF with sublinear (log) scaling
        tf = {}
        for n in _N_GRAMS:
            for gram in _ngrams(tokens, n):
                tf[gram] = tf.get(gram, 0) + 1
        for gram in tf:
            tf[gram] = 1.0 + math.log(tf[gram])
        all_tf.append(tf)

    # IDF
    idf: dict[str, float] = {}
    for terms in all_terms:
        for gram in terms:
            idf[gram] = idf.get(gram, 0) + 1
    for gram in idf:
        idf[gram] = math.log((doc_count + 1) / (idf[gram] + 1)) + 1.0

    # TF-IDF vectors
    vectors = []
    for tf in all_tf:
        vec = {gram: tf[gram] * idf.get(gram, 0.0) for gram in tf}
        vectors.append(vec)
    return vectors


def _cosine(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Cosine similarity between two sparse TF-IDF vectors."""
    if not vec_a or not vec_b:
        return 0.0
    dot = 0.0
    for gram, v in vec_a.items():
        dot += v * vec_b.get(gram, 0.0)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _cluster_centroid(tfidf_vecs: list[dict[str, float]]) -> dict[str, float]:
    """Average TF-IDF vector for a cluster (centroid)."""
    if not tfidf_vecs:
        return {}
    n = len(tfidf_vecs)
    centroid: dict[str, float] = defaultdict(float)
    for vec in tfidf_vecs:
        for gram, v in vec.items():
            centroid[gram] += v
    for gram in centroid:
        centroid[gram] /= n
    return dict(centroid)


def _second_pass_absorb(
    clusters: list[list[Evidence]],
    orphans: list[Evidence],
) -> tuple[list[list[Evidence]], list[Evidence]]:
    """TF-IDF second pass: absorb orphans into clusters or form new clusters.

    Returns (updated_clusters, remaining_orphans).
    """
    if not orphans:
        return clusters, orphans

    # Build TF-IDF vectors for all orphans + cluster centroids
    all_evidence = [ev for c in clusters for ev in c] + orphans
    all_vecs = _build_tfidf_vectors([ev.statement for ev in all_evidence])

    # Map evidence → vector
    ev_to_vec: dict[str, dict[str, float]] = {}
    for ev, vec in zip(all_evidence, all_vecs):
        ev_to_vec[ev.evidence_id] = vec

    # Build cluster centroids
    cluster_centroids = []
    cluster_absorbed = [0] * len(clusters)
    for c in clusters:
        centroid = _cluster_centroid([ev_to_vec[ev.evidence_id] for ev in c])
        cluster_centroids.append(centroid)

    # Phase 1: absorb orphans into existing clusters
    absorbed: set[str] = set()
    orphan_cluster_assign: dict[str, int] = {}  # orphan_id → cluster_idx

    for orphan in orphans:
        oid = orphan.evidence_id
        o_vec = ev_to_vec.get(oid, {})
        if not o_vec:
            continue
        best_cluster = -1
        best_score = 0.0
        for ci, centroid in enumerate(cluster_centroids):
            if cluster_absorbed[ci] >= _MAX_ABSORB_PER_CLUSTER:
                continue
            if len(clusters[ci]) >= _MAX_CLUSTER_SIZE:
                continue
            score = _cosine(o_vec, centroid)
            if score > _TFIDF_ABSORB_THRESHOLD and score > best_score:
                best_score = score
                best_cluster = ci

        if best_cluster >= 0:
            orphan_cluster_assign[oid] = best_cluster
            cluster_absorbed[best_cluster] += 1
            absorbed.add(oid)

    # Apply absorptions
    for orphan in orphans:
        oid = orphan.evidence_id
        if oid in orphan_cluster_assign:
            ci = orphan_cluster_assign[oid]
            clusters[ci].append(orphan)

    # Phase 2: remaining orphans → try to form new clusters
    remaining = [o for o in orphans if o.evidence_id not in absorbed]
    if len(remaining) < _NEW_CLUSTER_MIN_SIZE:
        return clusters, remaining

    # Greedy clustering on remaining orphans
    orphan_vecs = [ev_to_vec.get(o.evidence_id, {}) for o in remaining]
    assigned_orphan: set[int] = set()
    new_clusters: list[list[Evidence]] = []

    for i, o_vec in enumerate(orphan_vecs):
        if i in assigned_orphan or not o_vec:
            continue
        best_j = -1
        best_score = 0.0
        for j in range(i + 1, len(remaining)):
            if j in assigned_orphan:
                continue
            j_vec = orphan_vecs[j]
            if not j_vec:
                continue
            score = _cosine(o_vec, j_vec)
            if score > _TFIDF_NEW_CLUSTER_THRESHOLD and score > best_score:
                best_score = score
                best_j = j

        if best_j >= 0:
            new_cluster = [remaining[i], remaining[best_j]]
            assigned_orphan.add(i)
            assigned_orphan.add(best_j)
            # Try to add more
            centroid = _cluster_centroid([o_vec, orphan_vecs[best_j]])
            for k in range(len(remaining)):
                if k in assigned_orphan or k == i or k == best_j:
                    continue
                if len(new_cluster) >= _MAX_CLUSTER_SIZE:
                    break
                k_vec = orphan_vecs[k]
                if k_vec and _cosine(k_vec, centroid) > _TFIDF_NEW_CLUSTER_THRESHOLD:
                    new_cluster.append(remaining[k])
                    assigned_orphan.add(k)
            new_clusters.append(new_cluster)

    clusters.extend(new_clusters)
    final_orphans = [remaining[i] for i in range(len(remaining)) if i not in assigned_orphan]

    return clusters, final_orphans


def cluster_entropy(clusters: list[list[Evidence]], orphans: list[Evidence]) -> float:
    """Shannon entropy of cluster size distribution (includes orphans as size-1 bins).

    Higher entropy → more uniform distribution. Lower → few mega-clusters dominate.
    Stable entropy across days indicates structural invariance.
    """
    sizes = [len(c) for c in clusters] + [1] * len(orphans)
    total = sum(sizes)
    if total == 0:
        return 0.0
    entropy = 0.0
    for s in sizes:
        if s > 0:
            p = s / total
            entropy -= p * math.log(p)
    return entropy


def build_clusters(evidence_list: list[Evidence]) -> tuple[list[list[Evidence]], list[Evidence]]:
    """Greedy clustering of evidence into proto-event groups.

    Returns (clusters, orphans) where each cluster is a list of Evidence items
    and orphans are unclustered singletons.
    """
    if not evidence_list:
        return [], []

    # Pre-compute token sets
    token_sets = [(_tokenize(ev.statement) | _tokenize(ev.attribution)) for ev in evidence_list]

    # Greedy clustering: assign each item to the first cluster with score > threshold,
    # respecting max_cluster_size. Sort by evidence_strength desc so stronger items seed clusters.
    indices = sorted(range(len(evidence_list)),
                     key=lambda i: evidence_list[i].confidence.evidence_strength, reverse=True)

    clusters: list[list[int]] = []  # lists of indices into evidence_list
    assigned: set[int] = set()

    for idx in indices:
        if idx in assigned:
            continue
        tok_i = token_sets[idx]
        best_cluster = -1
        best_score = 0.0
        for ci, cluster_idxs in enumerate(clusters):
            if len(cluster_idxs) >= _MAX_CLUSTER_SIZE:
                continue
            # Score against the cluster's centroid: average similarity to all members
            scores = [_cluster_score(tok_i, token_sets[m]) for m in cluster_idxs]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            if avg_score > _CLUSTER_THRESHOLD and avg_score > best_score:
                best_score = avg_score
                best_cluster = ci

        if best_cluster >= 0:
            clusters[best_cluster].append(idx)
            assigned.add(idx)
        else:
            # Start a new cluster (may later become orphan if no other evidence joins)
            clusters.append([idx])
            assigned.add(idx)

    # Separate into valid clusters (≥ min_size) and orphans
    result_clusters: list[list[Evidence]] = []
    orphans: list[Evidence] = []

    for cluster_idxs in clusters:
        cluster_evs = [evidence_list[i] for i in cluster_idxs]
        if len(cluster_evs) >= _MIN_CLUSTER_SIZE:
            result_clusters.append(cluster_evs)
        else:
            orphans.extend(cluster_evs)

    # ── Layer 2: TF-IDF second-pass orphan absorption ──
    before_orphans = len(orphans)
    result_clusters, orphans = _second_pass_absorb(result_clusters, orphans)
    absorbed = before_orphans - len(orphans)
    if absorbed:
        logger.debug("TF-IDF second pass: absorbed %d orphans, %d remain",
                     absorbed, len(orphans))

    return result_clusters, orphans


class EventClusteringStage:
    """Stage 1.5: Event Pre-Assembler.

    Reads ctx["evidence"], writes ctx["event_clusters"] and ctx["event_orphans"].
    Deterministic clustering — no LLM calls.
    """

    def process(self, ctx: PipelineContext) -> PipelineContext:
        evidence_list: list[Evidence] = ctx.get("evidence", []) or []
        if not evidence_list:
            logger.info("EventClusteringStage: no evidence, skipping")
            ctx.set("event_clusters", [])
            ctx.set("event_orphans", [])
            return ctx

        clusters, orphans = build_clusters(evidence_list)

        total_in_clusters = sum(len(c) for c in clusters)
        orphan_pct = len(orphans) / max(len(evidence_list), 1) * 100
        logger.info("EventClusteringStage: %d evidence → %d clusters (%d evidence, %.0f%%) + %d orphans (%.0f%%)",
                    len(evidence_list), len(clusters), total_in_clusters,
                    total_in_clusters / max(len(evidence_list), 1) * 100,
                    len(orphans), orphan_pct)

        for i, cluster in enumerate(clusters):
            logger.debug("  Cluster %d: %d evidence | sources=%s",
                         i, len(cluster),
                         sorted(set(ev.source.name for ev in cluster)))

        ctx.set("event_clusters", clusters)
        ctx.set("event_orphans", orphans)
        return ctx
